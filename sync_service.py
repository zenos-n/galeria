"""Per-user background upload service; configured only by Gallery's sync UI."""
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
        return [str(source.parents[2]/'bin/gallery-sync')]
    return [sys.executable,str(source)]


def install_service():
    executable=runtime_command()
    unit_dir=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'systemd'/'user'
    quote=lambda value:'"'+value.replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'
    text='[Unit]\nDescription=Gallery folder uploads\nAfter=network-online.target\n\n[Service]\nType=simple\nExecStart='+ ' '.join(quote(part) for part in executable)+'\nRestart=on-failure\nRestartSec=15\nTimeoutStopSec=25\n\n[Install]\nWantedBy=default.target\n'
    atomic_write(unit_dir/UNIT,text.encode())
    if executable[0].startswith('/nix/store/'):
        root=state_dir()/'sync-runtime'
        root.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if root.is_symlink():root.unlink()
        command(['nix-store','--add-root',str(root),'--indirect','--realise',str(Path(executable[0]).parents[1])])
    command(['systemctl','--user','daemon-reload'])
    command(['systemctl','--user','enable','--now',UNIT])
    wake_service()


def wake_service():return command(['systemctl','--user','kill','-s','USR1',UNIT],check=False)
def stop_service():return command(['systemctl','--user','disable','--now',UNIT],check=False)


def disable_account(identity):
    config=read_config()
    if identity not in config.get('accounts',{}):return
    config['accounts'][identity]['enabled']=False;save_config(config)
    if any(account.get('enabled') for account in config['accounts'].values()):wake_service()
    else:stop_service()


def run_cycle(config,journal,cancel,client_factory=ImmichClient,token_lookup=secret_get,valid_rule=None):
    status={'running':True,'pid':os.getpid(),'updated':time.time(),'accounts':{}}
    for identity,account in config.get('accounts',{}).items():
        if cancel.is_set():break
        if not account.get('enabled'):continue
        current={'folders':[],'error':''};status['accounts'][identity]=current
        try:
            client=client_factory(account['server'])
            client.token=token_lookup(identity,'session')
            if not client.token:raise LibraryError('Sign in to this account again to resume syncing.')
            client.user=client.request('/users/me')
            if client.identity!=identity:raise LibraryError('The saved session belongs to another account.')
            client.detect_version()
            engine=SyncEngine(client,journal,cancel,valid_rule=(lambda rule:valid_rule(identity,rule)) if valid_rule else None)
            for rule in account.get('folders',[]):
                if cancel.is_set():break
                if rule.get('enabled',True):
                    current['folders'].append(engine.run_folder(rule))
                    status['updated']=time.time();atomic_write(state_dir()/'sync-status.json',json.dumps(status).encode())
        except Exception as error:
            current['error']=str(error) if isinstance(error,LibraryError) else 'Sync could not run; check the account and folders.'
    status['updated']=time.time()
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
    try:
        while not stop.is_set():
            def current(identity,rule):
                account=read_config().get('accounts',{}).get(identity,{})
                return account.get('enabled',False) and rule in account.get('folders',[])
            wake.clear();config=read_config();run_cycle(config,journal,stop,valid_rule=current)
            if args.once:break
            wake.wait(max(10,min(3600,int(config.get('interval',30)))))
    finally:
        journal.close()
        os.close(lock_fd)
        status=read_status();status['running']=False
        atomic_write(state_dir()/'sync-status.json',json.dumps(status).encode())


if __name__=='__main__':main()
