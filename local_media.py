"""Account-scoped associations between Immich assets and device originals."""
import hashlib,os,sqlite3,stat
from pathlib import Path
from sync_engine import SyncJournal,signature
from library import LibraryError


def journal_path():
    return Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'gallery'/'folder-sync.sqlite'


def remember_copy(client,path,asset,checksum,stat):
    if not getattr(client,'identity',None):return
    journal=SyncJournal(journal_path())
    try:journal.record(client.identity,'device-copy',Path(path).absolute(),stat,checksum,asset,'')
    finally:journal.close()


def local_paths(client,item):
    if item.path:return [str(Path(item.path).absolute())]
    if not client or not journal_path().exists():return []
    db=sqlite3.connect(journal_path())
    try:return [row[0] for row in db.execute('SELECT DISTINCT path FROM files WHERE account=? AND asset=? ORDER BY path',(client.identity,item.id))]
    finally:db.close()


def fingerprint(path,cancel=None):
    path=Path(path)
    if path.is_symlink():raise LibraryError('A local file is now a symbolic link; it was kept.')
    expected=path.stat()
    if not stat.S_ISREG(expected.st_mode):raise LibraryError('The local path is no longer a regular file; it was kept.')
    digest=hashlib.sha1()
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb') as source:
        if signature(os.fstat(source.fileno()))!=signature(expected):raise LibraryError('A local file changed; it was kept.')
        while chunk:=source.read(1024*1024):
            if cancel is not None and cancel.is_set():raise InterruptedError()
            digest.update(chunk)
    if signature(path.stat())!=signature(expected):raise LibraryError('A local file changed; it was kept.')
    return expected,digest.hexdigest()


def copies_for(client,items):
    records=[]
    if client and journal_path().exists():
        db=sqlite3.connect(journal_path())
        try:records=db.execute('SELECT path,size,mtime,checksum,asset FROM files WHERE account=?',(client.identity,)).fetchall()
        finally:db.close()
    ids={item.id for item in items if not item.path};paths={str(Path(item.path).absolute()) for item in items if item.path}
    matches={path:(size,mtime,checksum,asset) for path,size,mtime,checksum,asset in records if asset in ids or path in paths}
    local=[];cloud=set(ids) if client else set()
    for path in paths:
        if path in matches and client and matches[path][3]:cloud.add(matches[path][3])
        else:
            try:
                stat,checksum=fingerprint(path);matches[path]=(stat.st_size,stat.st_mtime_ns,checksum,None)
            except FileNotFoundError:continue
    for path,(size,mtime,checksum,asset) in matches.items():
        if Path(path).exists() or Path(path).is_symlink():local.append((path,size,mtime,checksum))
    return local,sorted(cloud)


def trash_copies(client,local,cloud,scope,trash):
    ready=[];errors=[];removed=[]
    if scope!='cloud':
        for path,size,mtime,checksum in local:
            try:
                stat,digest=fingerprint(path)
                if (stat.st_size,stat.st_mtime_ns,digest)!=(size,mtime,checksum):raise LibraryError('The local file changed; it was kept.')
                ready.append((path,signature(stat)))
            except FileNotFoundError:continue
            except (OSError,LibraryError) as error:errors.append(Path(path).name+': '+str(error))
    if scope!='local' and cloud:client.trash_assets(cloud)
    for path,expected in ready:
        try:
            if Path(path).is_symlink() or signature(Path(path).stat())!=expected:raise LibraryError('The local file changed; it was kept.')
            if not trash(path):raise LibraryError('Could not move the local file to Trash.')
            removed.append(path)
        except Exception as error:errors.append(Path(path).name+': '+str(error))
    return removed,scope!='local' and bool(cloud),errors
