import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from library import ImmichClient, LibraryError, scan_folders


ASSETS=[{'id':'a','originalFileName':'mountain.jpg','localDateTime':'2026-03-02T12:00:00',
         'width':1200,'height':800,'type':'IMAGE','visibility':'timeline'},
        {'id':'b','originalFileName':'city.jpg','localDateTime':'2025-12-01T10:00:00',
         'width':800,'height':1000,'type':'IMAGE','visibility':'timeline'}]


class ImmichFixture(BaseHTTPRequestHandler):
    requests=[]
    thumbnail=b'thumbnail'
    admin=True
    legacy=False
    denied=set()

    def log_message(self,*_):pass

    def respond(self,value,status=200):
        self.send_response(status)
        self.send_header('Content-Type','application/octet-stream' if isinstance(value,bytes) else 'application/json')
        self.end_headers()
        self.wfile.write(value if isinstance(value,bytes) else json.dumps(value).encode())

    def handle_request(self):
        payload=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'null')
        self.requests.append((self.command,self.path,payload,self.headers.get('Authorization')))
        if self.path=='/api/auth/login':
            return self.respond({'accessToken':'test-session'} if payload['password']=='test-password' else {},200 if payload['password']=='test-password' else 401)
        if self.path=='/api/redirect':
            self.send_response(302);self.send_header('Location','/api/users/me');self.end_headers();return
        if self.path=='/api/invalid':
            self.send_response(200);self.end_headers();self.wfile.write(b'not JSON');return
        if self.headers.get('Authorization')!='Bearer test-session':return self.respond({},401)
        if self.path in self.denied:return self.respond({},403)
        if self.path=='/api/users/me':return self.respond({'id':'user','name':'Test Administrator','email':'test@example.invalid','isAdmin':self.admin})
        if self.path.startswith('/api/search/'):
            page=payload.get('page',1)
            return self.respond({'assets':{'items':ASSETS[:1] if page==1 else ASSETS[1:], 'nextPage':'2' if page==1 else None}})
        if '/thumbnail?' in self.path:return self.respond(self.thumbnail)
        if self.path=='/api/albums':return self.respond([{'id':'album','albumName':'Trips'}])
        if self.path=='/api/albums/album':return self.respond({'assets':ASSETS})
        if self.path=='/api/server/about':return self.respond({'version':'3.2.0-fixture'})
        if self.path=='/api/server/statistics':return self.respond({'photos':2,'videos':0,'usage':1000000})
        if self.path=='/api/server/storage':return self.respond({'diskUse':'1 GB','diskAvailable':'9 GB','diskUsagePercentage':10})
        if self.path=='/api/admin/users':return self.respond([{'id':'user','name':'Test Administrator','email':'test@example.invalid','isAdmin':True,'quotaUsageInBytes':1000000}])
        if self.path=='/api/queues':
            return self.respond({} if self.legacy else [{'name':'thumbnailGeneration','isPaused':False,'statistics':{'active':1,'waiting':4,'failed':0}}],404 if self.legacy else 200)
        if self.path=='/api/jobs':return self.respond({'thumbnailGeneration':{'queueStatus':{'isPaused':True},'jobCounts':{'waiting':2}}})
        if self.path.startswith('/api/queues/') and self.command=='PUT':return self.respond({'isPaused':payload['isPaused']})
        return self.respond({},404)

    do_GET=handle_request
    do_POST=handle_request
    do_PUT=handle_request


class LibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),ImmichFixture)
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.address=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def setUp(self):
        ImmichFixture.requests=[];ImmichFixture.admin=True;ImmichFixture.legacy=False;ImmichFixture.denied=set()
        self.client=ImmichClient(self.address+'/api/')

    def login(self):self.client.login('test@example.invalid','test-password')

    def test_login_search_pages_and_authenticated_thumbnail(self):
        self.login()
        items,next_page=self.client.search()
        self.assertEqual((items[0].filename,items[0].ratio,next_page),('mountain.jpg',1.5,'2'))
        items,next_page=self.client.search(page=2)
        self.assertEqual((items[0].id,next_page),('b',None))
        self.assertEqual(self.client.thumbnail('a'),b'thumbnail')
        self.assertEqual(self.client.albums()[0]['albumName'],'Trips')
        self.assertEqual(len(self.client.album('album')),2)
        self.assertTrue(all(record[3]=='Bearer test-session' for record in ImmichFixture.requests[1:]))
        self.assertNotIn('test-password',self.client.__dict__.values())

    def test_metadata_and_smart_search_payloads(self):
        self.login()
        self.client.search({'originalFileName':'mountain'})
        self.assertEqual(ImmichFixture.requests[-1][1],'/api/search/metadata')
        self.client.search({'visibility':None},'mountains')
        self.assertEqual(ImmichFixture.requests[-1][1],'/api/search/smart')
        self.assertNotIn('visibility',ImmichFixture.requests[-1][2])
        self.client.search({'isTrashed':True})
        self.assertNotIn('visibility',ImmichFixture.requests[-1][2])

    def test_admin_access_queues_and_legacy_fallback(self):
        self.login()
        self.assertEqual(self.client.admin_section('overview')['statistics']['photos'],2)
        self.assertEqual(len(self.client.admin_section('users')),1)
        self.assertFalse(self.client.admin_section('queues')[0]['isPaused'])
        self.assertEqual(self.client.pause_queue('thumbnailGeneration',True),{'isPaused':True})
        ImmichFixture.legacy=True
        self.assertTrue(self.client.admin_section('queues')[0]['legacy'])
        self.client.user['isAdmin']=False
        before=len(ImmichFixture.requests)
        with self.assertRaises(LibraryError):self.client.admin_section('users')
        self.assertEqual(before,len(ImmichFixture.requests))

    def test_auth_failure_permissions_redirect_and_invalid_response(self):
        with self.assertRaises(LibraryError):self.client.login('test@example.invalid','wrong')
        self.assertIsNone(self.client.token)
        self.login()
        ImmichFixture.denied={'/api/admin/users'}
        with self.assertRaises(LibraryError) as context:self.client.admin_section('users')
        self.assertEqual(context.exception.status,403)
        before=len(ImmichFixture.requests)
        with self.assertRaises(LibraryError):self.client.request('/redirect')
        self.assertEqual(before+1,len(ImmichFixture.requests))
        with self.assertRaises(LibraryError):self.client.request('/invalid')

    def test_url_validation(self):
        for address in ['file:///tmp','https://user:pass@example.invalid','http://example.invalid?token=secret','not-a-url']:
            with self.assertRaises(LibraryError):ImmichClient(address)

    def test_recursive_local_discovery_deduplicates_and_skips_symlinks(self):
        with TemporaryDirectory() as root:
            path=Path(root);(path/'nested').mkdir()
            (path/'nested'/'photo.JPG').write_bytes(b'not decoded by metadata scan')
            (path/'video.mp4').write_bytes(b'video');(path/'notes.txt').write_text('skip')
            (path/'linked.jpg').symlink_to(path/'nested'/'photo.JPG')
            items,errors=scan_folders([root,str(path/'nested')],lambda _:1.25)
            self.assertEqual({item.filename for item in items},{'photo.JPG','video.mp4'})
            self.assertEqual(next(item for item in items if item.kind=='IMAGE').ratio,1.25)
            self.assertEqual(errors,[])


if __name__=='__main__':unittest.main()
