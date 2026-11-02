from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
from tempfile import TemporaryDirectory
import json,unittest
from cache import MediaCache
from library import ImmichClient


class ProfileTests(unittest.TestCase):
    def test_authenticated_profile_read_cache_and_multipart_change(self):
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_GET(self):
                requests.append((self.command,self.path,self.headers.get('Authorization'),None))
                self.send_response(200);self.end_headers();self.wfile.write(b'profile')
            def do_POST(self):
                body=self.rfile.read(int(self.headers['Content-Length']))
                requests.append((self.command,self.path,self.headers.get('Authorization'),body))
                self.send_response(201);self.end_headers();self.wfile.write(json.dumps({'profileChangedAt':'new','profileImagePath':'profile.jpg'}).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with TemporaryDirectory() as root:
                client=ImmichClient(f'http://127.0.0.1:{server.server_port}');client.token='fixture';client.user={'id':'user','profileChangedAt':'old'};client.cache=MediaCache('fixture',root=root)
                self.assertEqual(client.profile_image(),b'profile');self.assertEqual(client.profile_image(),b'profile')
                self.assertEqual(len(requests),1);self.assertEqual(requests[0][1:3],('/api/users/user/profile-image','Bearer fixture'))
                client.upload_profile_image(b'new-picture','photo.png')
                self.assertEqual(requests[1][1],'/api/users/profile-image');self.assertIn(b'name="file"',requests[1][3]);self.assertIn(b'new-picture',requests[1][3])
                self.assertEqual(client.user['profileChangedAt'],'new');self.assertIsNone(client.profile_image(cached=True))
                self.assertEqual(client.profile_image(),b'profile');self.assertEqual(len(requests),3)
        finally:server.shutdown();server.server_close();thread.join()
