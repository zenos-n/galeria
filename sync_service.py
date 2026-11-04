"""Per-user background upload service; configured only by Galeria's sync UI."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from cache import atomic_write
from library import ImmichClient,LibraryError
from session_store import secret_get
from sync_engine import SyncEngine,SyncJournal

UNIT='gallery-folder-sync.service'


def config_path():return Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'gallery'/'folder-sync.json'
def state_dir():return Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'gallery'


def read_config():
    try:return json.loads(config_path().read_text())
    except (OSError,ValueError):return {'accounts':{}}


def save_config(value):atomic_write(config_path(),json.dumps(value).encode())


def read_status():
    try:return json.loads((state_dir()/'sync-status.json').read_text())
    except (OSError,ValueError):return {}


def command(args,check=True):
    result=subprocess.run(args,capture_output=True,text=True,timeout=30)
    if check and result.returncode:raise LibraryError('Could not update the background service: '+result.stderr.strip()[:300])
    return result


def runtime_command():
    source=Path(__file__).resolve()
    if str(source).startswith('/nix/store/'):
        return [str(source.parents[2]/'bin/galeria-sync')]
    return [sys.executable,str(source)]


def install_service():
    executable=runtime_command()
    unit_dir=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'systemd'/'user'
    quote=lambda value:'"'+value.replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'
    text='[Unit]\nDescription=Galeria folder uploads\nAfter=network-online.target\n\n[Service]\nType=simple\nExecStart='+ ' '.join(quote(part) for part in executable)+'\nRestart=on-failure\nRestartSec=15\nTimeoutStopSec=25\n\n[Install]\nWantedBy=default.target\n'
    atomic_write(unit_dir/UNIT,text.encode())
    if executable[0].startswith('/nix/store/'):
        root=state_dir()/'sync-runtime'
        root.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if root.is_symlink():root.unlink()
        command(['nix-store','--add-root',str(root),'--indirect','--realise',str(Path(executable[0]).parents[1])])
    command(['systemctl','--user','daemon-reload'])
    command(['systemctl','--user','enable','--now',UNIT])


def wake_service():return command(['systemctl','--user','kill','-s','USR1',UNIT],check=False)
def request_sync():
    unit=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'systemd'/'user'/UNIT
    try:outdated=runtime_command()[0] not in unit.read_text()
    except OSError:outdated=True
    active=command(['systemctl','--user','is-active','--quiet',UNIT],check=False).returncode==0
    if outdated or not active:
        install_service()
        if outdated and active:command(['systemctl','--user','restart',UNIT])
    elif wake_service().returncode:raise LibraryError('Could not wake the folder sync service.')


def stop_service():return command(['systemctl','--user','disable','--now',UNIT],check=False)


def disable_account(identity):
    config=read_config()
    if identity not in config.get('accounts',{}):return
    config['accounts'][identity]['enabled']=False;save_config(config)
    if any(account.get('enabled') for account in config['accounts'].values()):wake_service()
    else:stop_service()


def run_cycle(config,journal,cancel,client_factory=ImmichClient,token_lookup=secret_get,valid_rule=None):
    status={'running':True,'active':True,'pid':os.getpid(),'updated':time.time(),'accounts':{}}
    for identity,account in config.get('accounts',{}).items():
        if cancel.is_set():break
        if not account.get('enabled'):continue
        current={'folders':[],'error':'','busy':True};status['accounts'][identity]=current
        def publish():
            status['updated']=time.time();atomic_write(state_dir()/'sync-status.json',json.dumps(status).encode())
        publish()
        try:
            client=client_factory(account['server'])
            client.token=token_lookup(identity,'session')
            if not client.token:raise LibraryError('Sign in to this account again to resume syncing.')
            client.user=client.request('/users/me')
            if client.identity!=identity:raise LibraryError('The saved session belongs to another account.')
            client.detect_version()
            last_progress=[0]
            def progress(counts):
                changed=bool(current.get('progress',{}).get('uploading'))!=bool(counts.get('uploading'))
                current['progress']=counts
                if changed or time.monotonic()-last_progress[0]>.2:last_progress[0]=time.monotonic();publish()
            engine=SyncEngine(client,journal,cancel,progress=progress,valid_rule=(lambda rule:valid_rule(identity,rule)) if valid_rule else None)
            for rule in account.get('folders',[]):
                if cancel.is_set():break
                if rule.get('enabled',True):
                    current['current_folder']=rule['path'];current['progress']={};publish()
                    current['folders'].append(engine.run_folder(rule));current['progress']={}
                    status['updated']=time.time();atomic_write(state_dir()/'sync-status.json',json.dumps(status).encode())
        except Exception as error:
            current['error']=str(error) if isinstance(error,LibraryError) else 'Sync could not run; check the account and folders.'
        current['busy']=False
    status['active']=False;status['updated']=time.time()
    atomic_write(state_dir()/'sync-status.json',json.dumps(status).encode())
    return status


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    stop=threading.Event();wake=threading.Event()
    def terminate(*_):stop.set();wake.set()
    signal.signal(signal.SIGTERM,terminate);signal.signal(signal.SIGINT,terminate)
    signal.signal(signal.SIGUSR1,lambda *_:wake.set())
    journal=SyncJournal(state_dir()/'folder-sync.sqlite')
    lock_fd=os.open(state_dir()/'sync.lock',os.O_CREAT|os.O_RDWR,0o600)
    try:fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock_fd);journal.close();return
    from folder_watch import FolderWatch
    watcher=None if args.once else FolderWatch(config_path(),wake.set)
    try:
        while not stop.is_set():
            def current(identity,rule):
                account=read_config().get('accounts',{}).get(identity,{})
                return account.get('enabled',False) and rule in account.get('folders',[])
            wake.clear();config=read_config();result=run_cycle(config,journal,stop,valid_rule=current)
            if args.once:break
            pending=any(folder.get('pending') for value in result['accounts'].values() for folder in value.get('folders',[]))
            errors=any(value.get('error') or any(folder.get('errors') for folder in value.get('folders',[])) for value in result['accounts'].values())
            wake.wait(2.2 if pending else 30 if errors else 600)
    finally:
        if watcher:watcher.close()
        journal.close()
        os.close(lock_fd)
        status=read_status();status['running']=False
        atomic_write(state_dir()/'sync-status.json',json.dumps(status).encode())


if __name__=='__main__':main()
