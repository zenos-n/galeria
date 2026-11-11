"""Idempotent upload-only folder synchronization. Never modifies source files."""
from datetime import datetime,timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sqlite3
import stat as file_stat
import threading
import time
from urllib.parse import quote
from urllib.request import Request
from library import LibraryError,media_paths,VIDEO_TYPES


def signature(stat):return stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns

FILE_QUIET_SECONDS=10


def open_writers():
    writers=set()
    try:processes=list(Path('/proc').iterdir())
    except OSError:return writers
    for process in processes:
        if not process.name.isdigit():continue
        try:
            if process.stat().st_uid!=os.getuid():continue
            descriptors=list((process/'fd').iterdir())
        except OSError:continue
        for descriptor in descriptors:
            try:
                info=descriptor.stat()
                if not file_stat.S_ISREG(info.st_mode):continue
                fields=dict(line.split(':',1) for line in (process/'fdinfo'/descriptor.name).read_text().splitlines() if ':' in line)
                if int(fields.get('flags','0').strip(),8)&os.O_ACCMODE:writers.add((info.st_dev,info.st_ino))
            except (OSError,ValueError):continue
    return writers


def post_asset(client,filename,size,modified,checksum,source,cancel,visibility=None,check=None,progress=None):
    boundary='gallery-'+secrets.token_hex(16)
    stamp=datetime.fromtimestamp(modified,timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
    fields={'fileCreatedAt':stamp,'fileModifiedAt':stamp,'filename':filename}
    if visibility:fields['visibility']=visibility
    if not client.modern_search:fields.update(deviceId='gallery-folder-sync',deviceAssetId=checksum)
    prefix=b''
    for name,value in fields.items():
        prefix+=f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
    mime=mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    suffix=Path(filename).suffix
    prefix+=(f'--{boundary}\r\nContent-Disposition: form-data; name="assetData"; filename="upload{suffix}"; filename*=UTF-8\'\'{quote(filename)}\r\nContent-Type: {mime}\r\n\r\n').encode()
    ending=f'\r\n--{boundary}--\r\n'.encode()
    def chunks():
        with source() as stream:
            if check:check(stream)
            if progress:progress(0,size)
            yield prefix;remaining=size
            while remaining:
                if cancel.is_set():raise InterruptedError('Upload cancelled')
                chunk=stream.read(min(1024*1024,remaining))
                if not chunk:raise LibraryError('File changed during upload; retrying later.')
                remaining-=len(chunk);yield chunk
                if progress:progress(size-remaining,size)
            if check:check(stream)
            yield ending
    request=Request(client.base+'/assets',data=chunks(),headers={'Authorization':'Bearer '+client.token,
        'Content-Type':'multipart/form-data; boundary='+boundary,'Content-Length':str(len(prefix)+size+len(ending)),
        'x-immich-checksum':checksum},method='POST')
    try:
        with client.http.open(request,timeout=60) as response:result=json.loads(response.read(1024*1024))
    except InterruptedError:raise
    except Exception as error:
        if hasattr(error,'close'):error.close()
        raise LibraryError('Upload failed; the original is untouched and can be retried.') from None
    if not result.get('id'):raise LibraryError('Immich did not confirm the uploaded asset.')
    return result['id']


def upload_file(client,path,checksum,expected,cancel,visibility=None,progress=None):
    def source():return os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),'rb')
    def check(stream):
        if signature(os.fstat(stream.fileno()))!=signature(expected):raise LibraryError('File changed before upload; retrying later.')
    id=post_asset(client,path.name,expected.st_size,expected.st_mtime,checksum,source,cancel,visibility,check,progress)
    if signature(path.stat())!=signature(expected):raise LibraryError('File changed during upload; retrying later.')
    return id


class SyncJournal:
    def __init__(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(path,os.O_CREAT|os.O_RDWR,0o600);os.close(fd)
        self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS files (account TEXT, rule TEXT, path TEXT, size INTEGER, mtime INTEGER, checksum TEXT, asset TEXT, destination TEXT, PRIMARY KEY(account,rule,path))')
        self.db.execute('CREATE TABLE IF NOT EXISTS albums (account TEXT, rule TEXT, name TEXT, album TEXT, PRIMARY KEY(account,rule))')
        self.db.execute('CREATE TABLE IF NOT EXISTS observations (account TEXT, path TEXT, device INTEGER, inode INTEGER, size INTEGER, mtime INTEGER, since REAL, PRIMARY KEY(account,path))')

    def stable(self,account,path,stat):
        now=time.time();observed=signature(stat)
        row=self.db.execute('SELECT device,inode,size,mtime,since FROM observations WHERE account=? AND path=?',(account,str(path))).fetchone()
        if row and row[:4]==observed and now>=row[4]:return now-row[4]>=FILE_QUIET_SECONDS
        self.db.execute('INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?,?,?)',(account,str(path),*observed,now));self.db.commit()
        return FILE_QUIET_SECONDS==0

    def known(self,account,rule,path,stat,destination):
        row=self.db.execute('SELECT size,mtime,destination FROM files WHERE account=? AND rule=? AND path=?',(account,rule,str(path))).fetchone()
        return row==(stat.st_size,stat.st_mtime_ns,destination)

    def record(self,account,rule,path,stat,checksum,asset,destination):
        self.db.execute('INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?,?)',(account,rule,str(path),stat.st_size,stat.st_mtime_ns,checksum,asset,destination))
        self.db.execute('DELETE FROM observations WHERE account=? AND path=?',(account,str(path)));self.db.commit()

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
        destination=self.destination(rule) if not rule.get('folder_albums') else ''
        writers=open_writers()
        def failed(_error):counts['errors'].append('A folder could not be read.')
        for path in media_paths(root,recursive,depth,failed):
            if self.cancel.is_set() or not self.valid_rule(rule):break
            try:
                if rule.get('folder_albums'):
                    relative=path.parent.relative_to(root).as_posix()
                    name=root.name if relative=='.' else root.name+' / '+relative
                    destination=self.destination(dict(rule,id=rule['id']+':'+relative,album_id='',album_name=name))
                stat=path.stat()
                if self.journal.known(self.client.identity,rule['id'],path,stat,destination):counts['unchanged']+=1;continue
                stable=self.journal.stable(self.client.identity,path,stat)
                if not stable or (stat.st_dev,stat.st_ino) in writers:counts['pending']+=1;continue
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
                    transfer={'key':hashlib.sha1((str(path)+'|'+checksum).encode()).hexdigest(),'path':str(path),'filename':path.name,'created':stat.st_mtime,'size':stat.st_size,'sent':0,'started':time.time(),'kind':'VIDEO' if path.suffix.lower() in VIDEO_TYPES else 'IMAGE','state':'uploading'}
                    history=counts.setdefault('transfers',[]);history.append(transfer);del history[:-128]
                    counts['uploading']=path.name;self.progress(dict(counts))
                    def sent(current,total):
                        transfer['sent']=current;self.progress(dict(counts))
                    try:
                        asset=upload_file(self.client,path,checksum,stat,self.cancel,progress=sent);counts['uploaded']+=1
                        transfer.update(state='complete',asset=asset)
                    except Exception as error:
                        transfer.update(state='failed',error=str(error));raise
                    finally:counts.pop('uploading',None);self.progress(dict(counts))
                else:counts['existing']+=1
                if destination:self.client.request('/albums/'+quote(destination,safe='')+'/assets',{'ids':[asset]},method='PUT')
                self.journal.record(self.client.identity,rule['id'],path,stat,checksum,asset,destination)
                self.progress(dict(counts))
            except InterruptedError:break
            except Exception as error:
                if len(counts['errors'])<10:counts['errors'].append(f'{path.name}: '+(str(error) if isinstance(error,LibraryError) else 'Could not read or upload this file.'))
        return counts
