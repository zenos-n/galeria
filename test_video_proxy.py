from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from threading import Thread
import time
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from cache import MediaCache
from library import ImmichClient,media_from_asset
from video_proxy import VideoProxy


class VideoTests(unittest.TestCase):
    def test_authenticated_range_cache_head_and_revocation(self):
        data=bytes(range(256))*10000;calls=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def respond(self,head=False):
                calls.append((self.headers.get('Range'),self.headers.get('Authorization')))
                if self.headers.get('Authorization')!='Bearer fixture':self.send_error(403);return
                start,end=0,len(data)-1
                if self.headers.get('Range'):
                    match=re.fullmatch(r'bytes=(\d+)-(\d*)',self.headers['Range'])
                    start=int(match[1]);end=min(end,int(match[2])) if match[2] else end
                self.send_response(206 if self.headers.get('Range') else 200)
                self.send_header('Content-Type','video/mp4');self.send_header('Content-Length',str(end-start+1))
                self.send_header('Accept-Ranges','bytes')
                if self.headers.get('Range'):self.send_header('Content-Range',f'bytes {start}-{end}/{len(data)}')
                self.end_headers()
                if not head:self.wfile.write(data[start:end+1])
            def do_GET(self):self.respond()
            def do_HEAD(self):self.respond(True)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start();proxy=VideoProxy()
        try:
            with TemporaryDirectory() as root:
                client=ImmichClient(f'http://127.0.0.1:{server.server_port}');client.token='fixture'
                cache=MediaCache('fixture',root=root);client.media_cache=lambda:cache
                item=media_from_asset({'id':'video','visibility':'timeline','type':'VIDEO'})
                uri=proxy.register(client,item);self.assertNotIn('fixture',uri)
                proxy.preload(client,item);self.assertEqual(len(calls),1)
                with urlopen(Request(uri,headers={'Range':'bytes=10-99'})) as response:
                    self.assertEqual(response.status,206);self.assertEqual(response.read(),data[10:100])
                self.assertEqual(len(calls),1)
                with urlopen(Request(uri,method='HEAD')) as response:self.assertEqual(int(response.headers['Content-Length']),len(data))
                with urlopen(uri) as response:self.assertEqual(response.read(),data)
                self.assertEqual(len(calls),2)
                self.assertTrue(all(auth=='Bearer fixture' for _,auth in calls))
                item.metadata['visibility']='locked';client.locked_until=time.monotonic()-1
                with self.assertRaises(HTTPError) as error:urlopen(uri)
                self.assertEqual(error.exception.code,403);error.exception.close()
                item.metadata['visibility']='timeline';client.token=None
                with self.assertRaises(HTTPError) as error:urlopen(uri)
                self.assertEqual(error.exception.code,403);error.exception.close()
        finally:proxy.close();server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
