"""Streaming, atomic original downloads; never overwrite a source file."""
import os,hashlib
from http.client import HTTPException
from pathlib import Path
import tempfile
from library import LibraryError


class DownloadCancelled(Exception):pass


def filename(value):
    name=str(value).replace('\\','/').rsplit('/',1)[-1].replace('\x00','').strip()
    return name if name not in ('','.','..') else 'download'


def save_original(client,item,destination,cancel,progress=lambda *_:None,overwrite=True):
    destination=Path(destination)
    if item.path and (destination.resolve()==Path(item.path).resolve() or destination.exists() and os.path.samefile(destination,item.path)):
        raise LibraryError('Choose a different file to preserve the original.')
    if cancel.is_set():raise DownloadCancelled()
    temporary=None
    try:
        fd,name=tempfile.mkstemp(prefix='.galeria-download-',dir=destination.parent);temporary=Path(name)
        with os.fdopen(fd,'wb') as output:
            with open(item.path,'rb') if item.path else client.open_original(item) as source:
                total=os.fstat(source.fileno()).st_size if item.path else int(source.headers.get('Content-Length',0))
                written=0;digest=hashlib.sha1()
                while True:
                    if cancel.is_set():raise DownloadCancelled()
                    if not item.path:client.check_original_access(item)
                    chunk=source.read(1024*1024)
                    if not chunk:break
                    output.write(chunk);digest.update(chunk);written+=len(chunk);progress(written,total)
                if total and written!=total:raise LibraryError('The download ended before the file was complete.')
            output.flush();os.fsync(output.fileno())
        if cancel.is_set():raise DownloadCancelled()
        if overwrite:os.replace(temporary,destination)
        else:
            target=destination;number=2
            while True:
                try:os.link(temporary,target);break
                except FileExistsError:
                    target=destination.with_name(destination.stem+f' ({number})'+destination.suffix);number+=1
            destination=target
        if not item.path:
            from local_media import remember_copy
            remember_copy(client,destination,item.id,digest.hexdigest(),destination.stat())
        return destination
    except HTTPException:
        raise LibraryError('The download ended before the file was complete. Try again.') from None
    except OSError as error:
        raise LibraryError('Not enough space to save the download.' if error.errno==28 else 'Could not save the download. Check the selected location.') from None
    finally:
        if temporary:temporary.unlink(missing_ok=True)
