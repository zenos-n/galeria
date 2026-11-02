"""Loopback byte-range bridge: player URLs never contain Immich credentials."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import re
import secrets
import threading
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request


class VideoProxy:
    def __init__(self):
        self.sources={};self.lock=threading.Lock()
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_GET(self):owner.serve(self,False)
            def do_HEAD(self):owner.serve(self,True)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def register(self,client,item,vault=None):
        key=secrets.token_urlsafe(24)
        with self.lock:self.sources[key]=(client,item,vault)
        return f'http://127.0.0.1:{self.server.server_port}/{key}'

    def close(self):
        with self.lock:self.sources.clear()
        self.server.shutdown();self.server.server_close()

    def authorized(self,client,item):
        return bool(client.token) and (item.metadata.get('visibility')!='locked' or client.locked_until>time.monotonic())

    def prefix_key(self,item):return 'video-prefix:'+item.id+str(item.metadata.get('updatedAt') or item.metadata.get('checksum',''))

    def preload(self,client,item,vault=None):
        if not self.authorized(client,item):return
        cache=vault if item.metadata.get('visibility')=='locked' else client.media_cache()
        if cache is None:return
        key=self.prefix_key(item)
        def load():
            with self.open(client,item,'bytes=0-2097151') as response:
                match=re.match(r'bytes 0-\d+/(\d+)',response.headers.get('Content-Range',''))
                if response.status!=206 or not match:return b''
                body=response.read(2*1024*1024)
                metadata=json.dumps({'total':int(match[1]),'type':response.headers.get('Content-Type','video/mp4')}).encode()
                return len(metadata).to_bytes(4,'big')+metadata+body
        cache.fetch(key,load)

    def open(self,client,item,range_header=None,head=False):
        headers={'Authorization':'Bearer '+client.token}
        if range_header:headers['Range']=range_header
        return client.http.open(Request(client.base+'/assets/'+quote(item.id,safe='')+'/video/playback',headers=headers,method='HEAD' if head else 'GET'),timeout=20)

    def serve(self,handler,head):
        if handler.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}':handler.send_error(403);return
        with self.lock:source=self.sources.get(handler.path.lstrip('/'))
        if not source:handler.send_error(404);return
        client,item,vault=source
        if not self.authorized(client,item):handler.send_error(403);return
        cache=vault if item.metadata.get('visibility')=='locked' else client.media_cache()
        packet=cache.get(self.prefix_key(item)) if cache else None
        prefix=b'';metadata=None
        if packet:
            try:
                size=int.from_bytes(packet[:4],'big');metadata=json.loads(packet[4:4+size]);prefix=packet[4+size:]
            except (ValueError,TypeError):metadata=None
        requested=handler.headers.get('Range')
        try:
            if metadata and prefix:
                total=metadata['total'];start,end=0,total-1
                if requested:
                    match=re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
                    if not match:handler.send_error(416);return
                    start=int(match[1]) if match[1] else max(0,total-int(match[2]))
                    end=min(total-1,int(match[2])) if match[1] and match[2] else total-1
                if start> end or start>=total:
                    handler.send_response(416);handler.send_header('Content-Range',f'bytes */{total}');handler.end_headers();return
                if start<len(prefix):
                    handler.send_response(206 if requested else 200)
                    handler.send_header('Content-Type',metadata['type']);handler.send_header('Accept-Ranges','bytes')
                    handler.send_header('Content-Length',str(end-start+1))
                    if requested:handler.send_header('Content-Range',f'bytes {start}-{end}/{total}')
                    handler.end_headers()
                    if head:return
                    stop=min(end+1,len(prefix));handler.wfile.write(prefix[start:stop])
                    if stop<=end:
                        with self.open(client,item,f'bytes={stop}-{end}') as response:
                            if response.status!=206:return
                            self.copy(response,handler,client,item)
                    return
            with self.open(client,item,requested,head) as response:
                handler.send_response(response.status)
                for name in ('Content-Type','Content-Length','Content-Range','Accept-Ranges'):
                    if response.headers.get(name):handler.send_header(name,response.headers[name])
                handler.end_headers()
                if not head:self.copy(response,handler,client,item)
        except HTTPError as error:
            error.close()
            try:handler.send_error(error.code)
            except OSError:pass
        except (OSError,ValueError):pass

    def copy(self,response,handler,client,item):
        while chunk:=response.read(64*1024):
            if not self.authorized(client,item):return
            handler.wfile.write(chunk)
