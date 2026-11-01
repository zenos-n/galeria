"""Read-only local media discovery and Immich's HTTP API; no GTK dependency."""
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class LibraryError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


@dataclass
class MediaItem:
    id: str
    filename: str
    created: datetime
    ratio: float = 1.5
    kind: str = 'IMAGE'
    path: str = ''
    metadata: dict = field(default_factory=dict)


def media_from_asset(asset):
    exif = asset.get('exifInfo') or {}
    width = asset.get('width') or exif.get('exifImageWidth') or 3
    height = asset.get('height') or exif.get('exifImageHeight') or 2
    date = asset.get('localDateTime') or asset.get('fileCreatedAt') or asset.get('createdAt', '')
    try:
        created = datetime.fromisoformat(date.replace('Z', '+00:00')).replace(tzinfo=None)
    except (ValueError, TypeError):
        created = datetime(1970, 1, 1)
    return MediaItem(asset['id'], asset.get('originalFileName') or asset['id'], created,
                     max(.1, min(10, width / max(1, height))), asset.get('type', 'IMAGE'), metadata=asset)


IMAGE_TYPES = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.heic', '.avif'}
VIDEO_TYPES = {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v'}


def scan_folders(paths, probe=None):
    items, seen, errors = [], set(), []
    def failed(error):
        errors.append(str(error))
    for root in paths:
        root = Path(root).expanduser()
        if not root.is_dir():
            errors.append(f'Folder unavailable: {root.name}')
            continue
        for directory, _, files in os.walk(root, followlinks=False, onerror=failed):
            for name in files:
                path = Path(directory) / name
                suffix = path.suffix.lower()
                if suffix not in IMAGE_TYPES | VIDEO_TYPES or path.is_symlink():
                    continue
                absolute = str(path.absolute())
                if absolute in seen:
                    continue
                seen.add(absolute)
                try:
                    stat = path.stat()
                    ratio = probe(absolute) if probe and suffix in IMAGE_TYPES else 16 / 9
                    items.append(MediaItem(absolute, name, datetime.fromtimestamp(stat.st_mtime),
                                           ratio or 1.5, 'VIDEO' if suffix in VIDEO_TYPES else 'IMAGE', absolute))
                except (OSError, ValueError) as error:
                    errors.append(f'{name}: {error}')
    return sorted(items, key=lambda item: item.created, reverse=True), errors


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        # Never forward a session token or login password to a redirected host.
        return None


class ImmichClient:
    def __init__(self, address):
        parts = urlsplit(address.strip())
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise LibraryError('Enter an http:// or https:// server address without credentials or query parameters.')
        path = parts.path.rstrip('/')
        if not path.endswith('/api'):
            path += '/api'
        self.base = urlunsplit((parts.scheme, parts.netloc, path, '', ''))
        self.token = None
        self.user = None
        self.http = build_opener(NoRedirects())

    def request(self, path, data=None, method=None, binary=False):
        headers = {'Accept': 'application/octet-stream' if binary else 'application/json'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        payload = None if data is None else json.dumps(data).encode()
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        request = Request(self.base + path, data=payload, headers=headers, method=method)
        try:
            with self.http.open(request, timeout=20) as response:
                limit = 32 * 1024 * 1024 if binary else 16 * 1024 * 1024
                body = response.read(limit + 1)
                if len(body) > limit:
                    raise LibraryError('The server response is too large.')
                return body if binary else json.loads(body) if body else None
        except HTTPError as error:
            messages = {401: 'Your session is invalid or expired. Sign in again.',
                        403: 'This account does not have permission for this operation.',
                        404: 'This endpoint is unavailable on your Immich server.',
                        400: 'Immich rejected the request. Check your search fields or server version.'}
            raise LibraryError(messages.get(error.code, f'Immich returned HTTP {error.code}.'), error.code) from None
        except (URLError, TimeoutError, OSError):
            raise LibraryError('Could not reach Immich. Check the server address and connection.') from None
        except (ValueError, UnicodeError):
            raise LibraryError('The server returned an invalid response. Check that this is an Immich server.') from None

    def login(self, email, password):
        response = self.request('/auth/login', {'email': email.strip(), 'password': password})
        if not isinstance(response, dict) or not response.get('accessToken'):
            raise LibraryError('Immich did not return a session token.')
        self.token = response['accessToken']
        self.user = self.request('/users/me')
        return self.user

    def search(self, filters=None, query='', page=1):
        body = {'size': 100, 'page': page, 'order': 'desc', 'withExif': True, 'visibility': 'timeline'}
        body.update(filters or {})
        if body.get('visibility') is None or body.get('isTrashed'):
            body.pop('visibility',None)
        path = '/search/metadata'
        if query:
            path = '/search/smart'
            body['query'] = query
        response = self.request(path, body)
        assets = response.get('assets', {})
        items=[media_from_asset(asset) for asset in assets.get('items', []) if asset.get('visibility')!='locked']
        return items, assets.get('nextPage')

    def albums(self):
        return self.request('/albums')

    def album(self, album_id):
        return [media_from_asset(asset) for asset in self.request('/albums/' + quote(album_id, safe='')).get('assets', []) if asset.get('visibility')!='locked']

    def thumbnail(self, asset_id, preview=False):
        return self.request('/assets/' + quote(asset_id, safe='') + '/thumbnail?size=' + ('preview' if preview else 'thumbnail'), binary=True)

    def admin_section(self, section):
        if not self.user or not self.user.get('isAdmin'):
            raise LibraryError('Sign in with an Immich administrator account.', 403)
        if section == 'overview':
            return {key: self.request(path) for key, path in [('about', '/server/about'), ('storage', '/server/storage'), ('statistics', '/server/statistics')]}
        if section == 'users':
            return self.request('/admin/users')
        try:
            return self.request('/queues')
        except LibraryError as error:
            if error.status != 404:
                raise
            legacy = self.request('/jobs')
            return [{'name': name, 'isPaused': value.get('queueStatus', {}).get('isPaused', False),
                     'statistics': value.get('jobCounts', {}), 'legacy': True} for name, value in legacy.items()]

    def pause_queue(self, name, paused):
        if not self.user or not self.user.get('isAdmin'):
            raise LibraryError('Administrator access required.', 403)
        return self.request('/queues/' + quote(name, safe=''), {'isPaused': paused}, method='PUT')
