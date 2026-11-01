"""Private, bounded, account-separated disk cache. Locked media is encrypted."""
import hashlib
import json
import os
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
            if self.key:
                nonce=os.urandom(12)
                data=nonce+AESGCM(self.key).encrypt(nonce,data,key.encode())
            atomic_write(self.path(key),data)
            self.prune()

    def fetch(self,key,loader,max_age=None):
        with self.lock:
            lock=self.key_locks.setdefault(key,threading.Lock())
        with lock:
            data=self.get(key,max_age)
            if data is None:
                data=loader();self.put(key,data)
            return data

    def json(self,key,loader,ttl=60):
        return json.loads(self.fetch(key,lambda:json.dumps(loader()).encode(),ttl))

    def prune(self):
        files=sorted((p for p in self.root.iterdir() if p.is_file()),key=lambda p:p.stat().st_mtime)
        total=sum(p.stat().st_size for p in files)
        for path in files:
            if total<=self.budget:break
            total-=path.stat().st_size;path.unlink(missing_ok=True)

    def remove(self,key):self.path(key).unlink(missing_ok=True)

    def clear(self):
        with self.lock:
            for path in self.root.iterdir():
                if path.is_file():path.unlink(missing_ok=True)

    def sync_encrypted(self,key,response,cancel):
        """Stream an original to authenticated ciphertext; never create plaintext files."""
        if not self.key:raise ValueError('Encryption key required')
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
                output.write(encryptor.finalize());output.write(encryptor.tag)
            os.replace(name,self.path(key))
        finally:
            if os.path.exists(name):os.unlink(name)

    def has(self,key):return self.path(key).is_file()
