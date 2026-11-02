"""Idempotent upload-only folder synchronization. Never modifies source files."""
from datetime import datetime,timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from urllib.parse import quote
from urllib.request import Request
from library import LibraryError,media_paths


def signature(stat):return stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns


def upload_file(client,path,checksum,expected,cancel):
    boundary='gallery-'+secrets.token_hex(16)
    stamp=datetime.fromtimestamp(expected.st_mtime,timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
    fields={'fileCreatedAt':stamp,'fileModifiedAt':stamp,'filename':path.name}
    if not client.modern_search:
        fields.update(deviceId='gallery-folder-sync',deviceAssetId=checksum)
    prefix=b''
    for name,value in fields.items():
        prefix+=f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
    mime=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    filename='upload'+path.suffix
    prefix+=(f'--{boundary}\r\nContent-Disposition: form-data; name="assetData"; filename="{filename}"; filename*=UTF-8\'\'{quote(path.name)}\r\nContent-Type: {mime}\r\n\r\n').encode()
    suffix=f'\r\n--{boundary}--\r\n'.encode()
    def chunks():
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as stream:
            if signature(os.fstat(stream.fileno()))!=signature(expected):raise LibraryError('File changed before upload; retrying later.')
            yield prefix
            remaining=expected.st_size
            while remaining:
                if cancel.is_set():raise InterruptedError('Sync cancelled')
                chunk=stream.read(min(1024*1024,remaining))
                if not chunk:raise LibraryError('File changed during upload; retrying later.')
                remaining-=len(chunk);yield chunk
            yield suffix
    request=Request(client.base+'/assets',data=chunks(),headers={
        'Authorization':'Bearer '+client.token,'Content-Type':'multipart/form-data; boundary='+boundary,
        'Content-Length':str(len(prefix)+expected.st_size+len(suffix)),'x-immich-checksum':checksum},method='POST')
    try:
        with client.http.open(request,timeout=60) as response:result=json.loads(response.read(1024*1024))
    except InterruptedError:raise
    except Exception as error:
        if hasattr(error,'close'):error.close()
        raise LibraryError('Upload failed; the original is untouched and will be retried.') from None
    if signature(path.stat())!=signature(expected):raise LibraryError('File changed during upload; retrying later.')
    if not result.get('id'):raise LibraryError('Immich did not confirm the uploaded asset.')
    return result['id']


class SyncJournal:
    def __init__(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(path,os.O_CREAT|os.O_RDWR,0o600);os.close(fd)
        self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS files (account TEXT, rule TEXT, path TEXT, size INTEGER, mtime INTEGER, checksum TEXT, asset TEXT, destination TEXT, PRIMARY KEY(account,rule,path))')
        self.db.execute('CREATE TABLE IF NOT EXISTS albums (account TEXT, rule TEXT, name TEXT, album TEXT, PRIMARY KEY(account,rule))')

    def known(self,account,rule,path,stat,destination):
        row=self.db.execute('SELECT size,mtime,destination FROM files WHERE account=? AND rule=? AND path=?',(account,rule,str(path))).fetchone()
        return row==(stat.st_size,stat.st_mtime_ns,destination)

    def record(self,account,rule,path,stat,checksum,asset,destination):
        self.db.execute('INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?,?)',(account,rule,str(path),stat.st_size,stat.st_mtime_ns,checksum,asset,destination));self.db.commit()

    def close(self):self.db.close()


class SyncEngine:
    def __init__(self,client,journal,cancel=None,progress=None,valid_rule=None):
        self.client=client;self.journal=journal;self.cancel=cancel or threading.Event()
        self.progress=progress or (lambda _:None)
        self.valid_rule=valid_rule or (lambda _:True)

    def destination(self,rule):
        if rule.get('album_id'):return rule['album_id']
        name=rule.get('album_name','').strip()
        if not name:return ''
        row=self.journal.db.execute('SELECT name,album FROM albums WHERE account=? AND rule=?',(self.client.identity,rule['id'])).fetchone()
        if row and row[0]==name:return row[1]
        existing=next((album for album in self.client.albums() if album.get('albumName')==name and (album.get('ownerId',self.client.user['id'])==self.client.user['id'])),None)
        album=existing or self.client.request('/albums',{'albumName':name})
        self.journal.db.execute('INSERT OR REPLACE INTO albums VALUES (?,?,?,?)',(self.client.identity,rule['id'],name,album['id']));self.journal.db.commit()
        return album['id']

    def run_folder(self,rule):
        root=Path(rule['path']);counts={'uploaded':0,'existing':0,'unchanged':0,'errors':[],'pending':0,'path':str(root)}
        if self.cancel.is_set() or not self.valid_rule(rule):return counts
        if not root.is_absolute() or not root.is_dir():
            counts['errors']=['Folder is unavailable.'];return counts
        recursive=rule.get('recursive',True);depth=int(rule.get('max_depth',0))
        if depth<0:raise LibraryError('Subfolder depth must be non-negative.')
        destination=self.destination(rule)
        def failed(_error):counts['errors'].append('A folder could not be read.')
        for path in media_paths(root,recursive,depth,failed):
            if self.cancel.is_set() or not self.valid_rule(rule):break
            try:
                stat=path.stat()
                if self.journal.known(self.client.identity,rule['id'],path,stat,destination):counts['unchanged']+=1;continue
                if time.time()-stat.st_mtime<2:counts['pending']+=1;continue
                digest=hashlib.sha1()
                fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
                with os.fdopen(fd,'rb') as stream:
                    if signature(os.fstat(stream.fileno()))!=signature(stat):counts['pending']+=1;continue
                    while chunk:=stream.read(1024*1024):
                        if self.cancel.is_set():raise InterruptedError()
                        digest.update(chunk)
                if signature(path.stat())!=signature(stat):counts['pending']+=1;continue
                if self.cancel.is_set() or not self.valid_rule(rule):break
                checksum=digest.hexdigest()
                check=self.client.request('/assets/bulk-upload-check',{'assets':[{'id':str(path),'checksum':checksum}]})
                result=check['results'][0]
                if result.get('isTrashed'):
                    self.journal.record(self.client.identity,rule['id'],path,stat,checksum,result.get('assetId',''),destination)
                    counts['existing']+=1;continue
                asset=result.get('assetId')
                if not asset:
                    if result.get('action')!='accept':raise LibraryError('Immich rejected this file.')
                    asset=upload_file(self.client,path,checksum,stat,self.cancel);counts['uploaded']+=1
                else:counts['existing']+=1
                if destination:self.client.request('/albums/'+quote(destination,safe='')+'/assets',{'ids':[asset]},method='PUT')
                self.journal.record(self.client.identity,rule['id'],path,stat,checksum,asset,destination)
                self.progress(dict(counts))
            except InterruptedError:break
            except Exception as error:
                if len(counts['errors'])<10:counts['errors'].append(f'{path.name}: '+(str(error) if isinstance(error,LibraryError) else 'Could not read or upload this file.'))
        return counts
