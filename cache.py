"""Private, bounded, account-separated disk cache. Locked media is encrypted."""
import hashlib
import heapq
import json
import os
import shutil
from pathlib import Path
import tempfile
import threading
import time
import weakref
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes


def atomic_write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,name=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


class MediaCache:
    def __init__(self,identity,root=None,budget=512*1024*1024,key=None):
        base=Path(root or os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'gallery'
        self.root=base/hashlib.sha256(identity.encode()).hexdigest()
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.budget=budget
        self.key=key
        self.lock=threading.RLock()
        self.key_locks=weakref.WeakValueDictionary()
        self.epoch=0;self.forbidden=set()
        self.inventory=None;self.eviction=[];self.total_bytes=0;self.scanned_at=0

    def path(self,key):return self.root/hashlib.sha256(key.encode()).hexdigest()

    def get(self,key,max_age=None):
        with self.lock:
            path=self.path(key)
            try:
                if max_age is not None and time.time()-path.stat().st_mtime>max_age:return None
                data=path.read_bytes()
                return AESGCM(self.key).decrypt(data[:12],data[12:],key.encode()) if self.key else data
            except (OSError,ValueError):return None
            except Exception:
                # A corrupt/authentication-failed encrypted entry is never displayed.
                return None

    def put(self,key,data):
        with self.lock:
            if any(key.startswith(prefix) for prefix in self.forbidden):return
            if self.key:
                nonce=os.urandom(12)
                data=nonce+AESGCM(self.key).encrypt(nonce,data,key.encode())
            if self.budget is not None:self._inventory()
            path=self.path(key)
            atomic_write(path,data)
            if self.budget is not None:
                previous=self.inventory.get(path.name,(0,0))
                stamp=path.stat().st_mtime_ns;size=len(data)
                self.total_bytes+=size-previous[1];self.inventory[path.name]=(stamp,size)
                heapq.heappush(self.eviction,(stamp,path.name,size))
            self.prune()

    def fetch(self,key,loader,max_age=None):
        with self.lock:
            lock=self.key_locks.setdefault(key,threading.Lock())
        with lock:
            epoch=self.epoch
            data=self.get(key,max_age)
            if data is None:
                data=loader()
                with self.lock:
                    if epoch==self.epoch:self.put(key,data)
            return data

    def json(self,key,loader,ttl=60):
        return json.loads(self.fetch(key,lambda:json.dumps(loader()).encode(),ttl))

    def prune(self):
        if self.budget is None:return
        with self.lock:
            self._inventory()
            while self.total_bytes>self.budget and self.eviction:
                stamp,name,size=heapq.heappop(self.eviction)
                if self.inventory.get(name)!=(stamp,size):continue
                path=self.root/name
                try:stat=path.stat()
                except FileNotFoundError:stat=None
                if stat and (stat.st_mtime_ns,stat.st_size)!=(stamp,size):
                    self.total_bytes+=stat.st_size-size;self.inventory[name]=(stat.st_mtime_ns,stat.st_size)
                    heapq.heappush(self.eviction,(stat.st_mtime_ns,name,stat.st_size));continue
                path.unlink(missing_ok=True);self.inventory.pop(name,None);self.total_bytes-=size
            if len(self.eviction)>len(self.inventory)*2+128:
                self.eviction=[(stamp,name,size) for name,(stamp,size) in self.inventory.items()];heapq.heapify(self.eviction)

    def _inventory(self):
        # One scan initially, then occasional reconciliation with other processes.
        if self.inventory is not None and time.monotonic()-self.scanned_at<30:return
        entries={}
        with os.scandir(self.root) as files:
            for file in files:
                if len(file.name)!=64 or not file.is_file(follow_symlinks=False):continue
                try:stat=file.stat(follow_symlinks=False)
                except FileNotFoundError:continue
                entries[file.name]=(stat.st_mtime_ns,stat.st_size)
        self.inventory=entries;self.total_bytes=sum(size for _,size in entries.values())
        self.eviction=[(stamp,name,size) for name,(stamp,size) in entries.items()];heapq.heapify(self.eviction)
        self.scanned_at=time.monotonic()

    def remove(self,key):
        with self.lock:
            path=self.path(key);path.unlink(missing_ok=True)
            if self.inventory is not None:self.total_bytes-=self.inventory.pop(path.name,(0,0))[1]

    def clear(self):
        with self.lock:
            self.epoch+=1
            shutil.rmtree(self.root/'clipboard',ignore_errors=True)
            for path in self.root.iterdir():
                if path.is_file():path.unlink(missing_ok=True)
            self.inventory={};self.eviction=[];self.total_bytes=0;self.scanned_at=time.monotonic()

    def forbid(self,prefixes,preserve=()):
        with self.lock:
            self.forbidden.update(prefixes);self.epoch+=1
            keep={self.path(key).name for key in preserve if not any(key.startswith(prefix) for prefix in self.forbidden)}
            shutil.rmtree(self.root/'clipboard',ignore_errors=True)
            for path in self.root.iterdir():
                if path.is_file() and path.name not in keep:path.unlink(missing_ok=True)
            self.inventory=None;self.scanned_at=0


    def sync_encrypted(self,key,response,cancel):
        """Stream an original to authenticated ciphertext; never create plaintext files."""
        if not self.key:raise ValueError('Encryption key required')
        if cancel.is_set():raise InterruptedError('Sync cancelled')
        nonce=os.urandom(12)
        encryptor=Cipher(algorithms.AES(self.key),modes.GCM(nonce)).encryptor()
        encryptor.authenticate_additional_data(key.encode())
        fd,name=tempfile.mkstemp(dir=self.root)
        try:
            with os.fdopen(fd,'wb') as output:
                output.write(nonce)
                while chunk:=response.read(1024*1024):
                    if cancel.is_set():raise InterruptedError('Sync cancelled')
                    output.write(encryptor.update(chunk))
                if cancel.is_set():raise InterruptedError('Sync cancelled')
                output.write(encryptor.finalize());output.write(encryptor.tag)
            os.replace(name,self.path(key))
        finally:
            if os.path.exists(name):os.unlink(name)

    def has(self,key):return self.path(key).is_file()

    def move_video_prefixes(self,destination):
        """Separate old video packets without deleting cached thumbnail pixels."""
        if self.key or destination.key:raise ValueError('Only ordinary caches can be migrated')
        with self.lock,destination.lock:
            for path in self.root.iterdir():
                if len(path.name)!=64 or not path.is_file():continue
                try:
                    with path.open('rb') as stream:
                        length=int.from_bytes(stream.read(4),'big')
                        if not 0<length<256:continue
                        value=json.loads(stream.read(length))
                    if not isinstance(value,dict) or set(value)!={'total','type'} or not isinstance(value['total'],int) or not isinstance(value['type'],str):continue
                    os.replace(path,destination.root/path.name)
                except (OSError,ValueError):continue
            self.inventory=destination.inventory=None
            destination.prune()
