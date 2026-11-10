"""Checksum preflight and original-preserving file uploads shared by imports/edits."""
import hashlib,os
from pathlib import Path
from library import LibraryError
from sync_engine import signature,upload_file,post_asset
from io import BytesIO


def upload(client,path,cancel,visibility=None,progress=None):
    path=Path(path);expected=path.stat();digest=hashlib.sha1()
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),'rb') as source:
        if signature(os.fstat(source.fileno()))!=signature(expected):raise LibraryError('File changed; try uploading it again.')
        while chunk:=source.read(1024*1024):
            if cancel.is_set():raise InterruptedError()
            digest.update(chunk)
    if signature(path.stat())!=signature(expected):raise LibraryError('File changed; try uploading it again.')
    checksum=digest.hexdigest()
    result=client.request('/assets/bulk-upload-check',{'assets':[{'id':str(path),'checksum':checksum}]})['results'][0]
    asset=result.get('assetId');created=not bool(asset)
    if not asset:
        if result.get('action')!='accept':raise LibraryError('Immich rejected this file.')
        if cancel.is_set():raise InterruptedError()
        options={'visibility':visibility}
        if progress is not None:options['progress']=progress
        asset=upload_file(client,path,checksum,expected,cancel,**options)
    from local_media import remember_copy
    remember_copy(client,path,asset,checksum,expected)
    return asset,created


def upload_bytes(client,data,filename,modified,cancel,visibility=None,progress=None):
    if cancel.is_set():raise InterruptedError()
    checksum=hashlib.sha1(data).hexdigest()
    result=client.request('/assets/bulk-upload-check',{'assets':[{'id':filename,'checksum':checksum}]})['results'][0]
    if result.get('assetId'):return result['assetId'],False
    if result.get('action')!='accept':raise LibraryError('Immich rejected this file.')
    return post_asset(client,filename,len(data),modified,checksum,lambda:BytesIO(data),cancel,visibility,progress=progress),True
