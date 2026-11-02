"""Read-only local media discovery and Immich's HTTP API; no GTK dependency."""
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
import time
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
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


def media_paths(root,recursive=True,max_depth=0,onerror=None):
    root=Path(root)
    for directory,dirs,files in os.walk(root,followlinks=False,onerror=onerror):
        depth=len(Path(directory).relative_to(root).parts)
        dirs[:]=[name for name in dirs if not (Path(directory)/name).is_symlink()]
        if not recursive or max_depth and depth>=max_depth:dirs.clear()
        for name in files:
            path=Path(directory)/name
            if path.suffix.lower() in IMAGE_TYPES|VIDEO_TYPES and not path.is_symlink():yield path


def scan_folders(paths, probe=None,recursive=True,max_depth=0):
    items, seen, errors = [], set(), []
    def failed(error):
        errors.append(str(error))
    for root in paths:
        root = Path(root).expanduser()
        if root.is_file() and not root.is_symlink():
            candidates=[root] if root.suffix.lower() in IMAGE_TYPES|VIDEO_TYPES else []
        elif root.is_dir():candidates=media_paths(root,recursive,max_depth,failed)
        else:
            errors.append(f'Folder unavailable: {root.name}')
            continue
        for path in candidates:
            absolute=str(path.absolute());suffix=path.suffix.lower()
            if absolute in seen:continue
            seen.add(absolute)
            try:
                stat=path.stat();ratio=probe(absolute) if probe and suffix in IMAGE_TYPES else 16/9
                items.append(MediaItem(absolute,path.name,datetime.fromtimestamp(stat.st_mtime),ratio or 1.5,
                                       'VIDEO' if suffix in VIDEO_TYPES else 'IMAGE',absolute))
            except (OSError,ValueError) as error:errors.append(f'{path.name}: {error}')
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
        self.cache=None
        self.locked_until=0
        self.server_lock_pending=False
        self.modern_search=True

    @property
    def identity(self):return self.base+'|'+str((self.user or {}).get('id',''))

    def media_cache(self):
        if self.cache is None:
            from cache import MediaCache
            self.cache=MediaCache(self.identity)
        return self.cache

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
            status=error.code;error.close()
            raise LibraryError(messages.get(status, f'Immich returned HTTP {status}.'), status) from None
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
        self.detect_version()
        return self.user

    def detect_version(self):
        try:
            version=self.request('/server/about').get('version','')
            match=re.search(r'(\d+)\.(\d+)',str(version))
            if match:self.modern_search=tuple(map(int,match.groups()))>=(3,2)
        except LibraryError:pass

    def search_filter(self,values):
        result={'trashedAt':{'eq':None}}
        for key,value in values.items():
            if key=='isTrashed':result['trashedAt']={'ne' if value else 'eq':None}
            elif key in ('albumIds','personIds','tagIds'):result[key]={'any':value}
            elif key in ('originalFileName','originalPath','description'):result[key]={'like':'%'+value+'%'}
            elif key in ('takenAfter','takenBefore'):result.setdefault('takenAt',{})['gte' if key=='takenAfter' else 'lte']=value
            elif key=='isNotInAlbum':result['hasAlbums']={'eq':not value}
            elif key=='visibility' and value is None:result[key]={'in':['timeline','archive']}
            elif key=='ocr':result[key]={'matches':value}
            else:result[key]={'eq':value}
        return result

    def search(self, filters=None, query='', page=1):
        values={'visibility':'timeline',**(filters or {})}
        if values.get('isTrashed'):values['visibility']=None
        body={'size':100,'page':page,'order':'desc','withExif':True}
        if self.modern_search:body['filter']=self.search_filter(values)
        else:
            body.update(values)
            if body.get('visibility') is None:body.pop('visibility',None)
        path = '/search/metadata'
        if query:
            path = '/search/smart'
            body['query'] = query
        locked=values.get('visibility')=='locked'
        if not locked and self.server_lock_pending:self.lock_session()
        if locked and time.monotonic()>=self.locked_until:
            raise LibraryError('Unlock the locked folder first.',403)
        cache=self.media_cache()
        cache_key='search:'+str(getattr(self,'refresh_serial',0))+path+json.dumps(body,sort_keys=True)
        cached=None if locked else cache.get(cache_key,30)
        if cached:
            response=json.loads(cached)
        else:
            response = self.request(path, body)
            if not locked:
                response['assets']['items']=[asset for asset in response.get('assets',{}).get('items',[]) if asset.get('visibility') not in ('locked','hidden')]
                cache.put(cache_key,json.dumps(response).encode())
        assets = response.get('assets', {})
        items=[media_from_asset(asset) for asset in assets.get('items', []) if asset.get('visibility')!='hidden' and (locked or asset.get('visibility')!='locked')]
        return items, assets.get('nextPage')

    def time_buckets(self,filters=None):
        options={'visibility':'timeline','order':'desc'}
        for key,value in (filters or {}).items():
            if key in ('visibility','isFavorite','isTrashed'):options[key]=str(value).lower() if isinstance(value,bool) else value
            elif key in ('albumIds','personIds','tagIds') and len(value)==1:options[key[:-1]]=value[0]
        path='/timeline/buckets?'+urlencode({key:value for key,value in options.items() if value is not None})
        return self.media_cache().json('buckets:'+path,lambda:self.request(path),30)

    def share_album(self,album_id,options):
        return self.request('/shared-links',dict(options,type='ALBUM',albumId=album_id))

    def share_assets(self,ids,options):
        if not ids:raise LibraryError('Select at least one item to share.')
        return self.request('/shared-links',dict(options,type='INDIVIDUAL',assetIds=ids))

    def shared_links(self,album_id=None):
        return self.request('/shared-links'+('?'+urlencode({'albumId':album_id}) if album_id else ''))

    def revoke_link(self,link_id):return self.request('/shared-links/'+quote(link_id,safe=''),method='DELETE')

    def share_url(self,link):
        key=link.get('slug') or link.get('key')
        if not isinstance(key,str) or not key:raise LibraryError('Immich did not return a share URL.')
        return self.base.removesuffix('/api')+'/share/'+quote(key,safe='')

    def album_info(self,album_id):return self.request('/albums/'+quote(album_id,safe=''))

    def album_member(self,album_id,user_id,role=None,remove=False):
        path='/albums/'+quote(album_id,safe='')+'/user/'+quote(user_id,safe='')
        return self.request(path,None if remove else {'role':role},method='DELETE' if remove else 'PUT')

    def invite_album(self,album_id,user_id,role):
        return self.request('/albums/'+quote(album_id,safe='')+'/users',{'albumUsers':[{'userId':user_id,'role':role}]},method='PUT')

    def albums(self):
        return self.media_cache().json('albums',lambda:self.request('/albums'),30)

    def album(self, album_id):
        items=[];page=1
        while True:
            batch,next_page=self.search({'albumIds':[album_id],'visibility':None},page=page)
            items.extend(batch)
            if not next_page:break
            page=int(next_page)
        return items

    def thumbnail(self, asset_id, preview=False):
        return self.request('/assets/' + quote(asset_id, safe='') + '/thumbnail?size=' + ('preview' if preview else 'thumbnail'), binary=True)

    def image_bytes(self,item,preview=False,vault=None):
        key=self.image_key(item,preview)
        locked=item.metadata.get('visibility')=='locked'
        cache=vault if locked else self.media_cache()
        if not locked and not item.metadata.get('visibility') and (self.locked_until or self.server_lock_pending):cache=None
        def load():
            try:return self.thumbnail(item.id,preview)
            except LibraryError as error:
                if error.status!=404:raise
                return self.request('/assets/'+quote(item.id,safe='')+'/original',binary=True)
        return cache.fetch(key,load) if cache else load()

    def image_key(self,item,preview=False):
        version=item.metadata.get('updatedAt') or item.metadata.get('checksum') or ''
        return f'{item.id}:{version}:{"preview" if preview else "thumbnail"}'

    def collection_cover(self,asset_id):
        cache=self.media_cache();key='cover-info:'+asset_id
        data=cache.get(key,30)
        asset=json.loads(data) if data else self.request('/assets/'+quote(asset_id,safe=''))
        if asset.get('visibility') in ('locked','hidden'):return None
        if not data:cache.put(key,json.dumps(asset).encode())
        return media_from_asset(asset)

    def users_create(self,fields):
        return self.request('/admin/users',fields)

    def users_update(self,user_id,fields):
        return self.request('/admin/users/'+quote(user_id,safe=''),fields,method='PUT')

    def users_delete(self,user_id):
        return self.request('/admin/users/'+quote(user_id,safe=''),{},method='DELETE')

    def user_restore(self,user_id):
        return self.request('/admin/users/'+quote(user_id,safe='')+'/restore',{},method='POST')

    def unlock(self,secret,is_password=False):
        try:self.request('/auth/session/unlock',{'password' if is_password else 'pinCode':secret})
        except LibraryError as error:
            if error.status in (400,401,403):raise LibraryError('Could not unlock. Check your PIN or password and try again.',error.status) from None
            raise
        self.media_cache().clear()
        self.locked_until=time.monotonic()+14*60

    def lock_session(self):
        self.locked_until=0
        self.server_lock_pending=True
        session=next((s for s in self.request('/sessions') if s.get('current')),None)
        if session:self.request('/sessions/'+quote(session['id'],safe='')+'/lock',{},method='POST')
        self.server_lock_pending=False

    def collection(self,kind):
        if self.server_lock_pending:self.lock_session()
        if kind=='people':
            result=self.request('/people?size=1000&withHidden=false')
            return result.get('people',[]) if isinstance(result,dict) else result
        if kind=='tags':return self.request('/tags')
        if kind=='duplicates':return self.request('/duplicates')
        if kind=='sharing':return [album for album in self.albums() if album.get('shared') or album.get('hasSharedLink') or len(album.get('albumUsers',[]))>1]
        if kind=='map':return self.request('/map/markers')
        return self.albums()

    def update_assets(self,ids,fields):
        return self.request('/assets',dict(fields,ids=ids),method='PUT')

    def trash_assets(self,ids):
        return self.request('/assets',{'ids':ids,'force':False},method='DELETE')

    def restore_assets(self,ids):return self.request('/trash/restore/assets',{'ids':ids})

    def admin_section(self, section):
        if not self.user or not self.user.get('isAdmin'):
            raise LibraryError('Sign in with an Immich administrator account.', 403)
        if section == 'overview':
            return {key: self.request(path) for key, path in [('about', '/server/about'), ('storage', '/server/storage'), ('statistics', '/server/statistics')]}
        if section == 'users':
            return self.request('/admin/users?withDeleted=true')
        if section in ('settings','libraries'):
            return self.request('/system-config' if section=='settings' else '/libraries')
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
