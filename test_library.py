import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch
import os
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
        if self.path=='/map-style':return self.respond({'version':8,'sources':{'world':{'type':'vector','url':'/tile-source'}},'layers':[]})
        if self.path=='/tile-source':return self.respond({'tiles':['/tiles/{z}/{x}/{y}.pbf'],'maxzoom':14,'attribution':'Map contributors'})
        if self.headers.get('Authorization')!='Bearer test-session':return self.respond({},401)
        if self.path=='/api/server/config':return self.respond({'mapDarkStyleUrl':f'http://127.0.0.1:{self.server.server_port}/map-style'})
        if self.path.split('?')[0] in self.denied:return self.respond({},403)
        if self.path=='/api/users/me':return self.respond({'id':'user','name':'Test Administrator','email':'test@example.invalid','isAdmin':self.admin})
        if self.path.startswith('/api/search/'):
            structured='filter' in payload
            if structured and any(key in payload for key in ('page','order','visibility','albumIds')):
                return self.respond({'message':'Deprecated fields cannot be combined with filter'},400)
            page=2 if payload.get('cursor')=='opaque-next-page' else payload.get('page',1)
            return self.respond({'assets':{'items':ASSETS[:1] if page==1 else ASSETS[1:],
                'nextPage':None if structured or page!=1 else '2','nextCursor':'opaque-next-page' if structured and page==1 else None}})
        if '/thumbnail?' in self.path:return self.respond(self.thumbnail)
        if self.path=='/api/albums':return self.respond([{'id':'album','albumName':'Trips'}])
        if self.path=='/api/albums/album':return self.respond({'id':'album','albumName':'Trips','assetCount':2})
        if self.path.startswith('/api/timeline/buckets'):return self.respond([{'timeBucket':'2026-03-01','count':1},{'timeBucket':'2018-01-01','count':500}])
        if self.path=='/api/server/about':return self.respond({'version':'3.2.0-fixture'})
        if self.path=='/api/server/statistics':return self.respond({'photos':2,'videos':0,'usage':1000000})
        if self.path=='/api/server/storage':return self.respond({'diskUse':'1 GB','diskAvailable':'9 GB','diskUsagePercentage':10})
        if self.path.startswith('/api/admin/users'):
            if self.path.endswith('/statistics'):return self.respond({'photos':2,'videos':1})
            if self.path.endswith('/sessions'):return self.respond([{'deviceType':'Browser','deviceOS':'Linux'}])
            if self.command in ('POST','PUT'):return self.respond(dict(payload or {},id='new-user'))
            return self.respond([{'id':'user','name':'Test Administrator','email':'test@example.invalid','isAdmin':True,'quotaUsageInBytes':1000000}])
        if self.path=='/api/system-config':return self.respond(payload if self.command=='PUT' else {'logging':{'enabled':True,'level':'log'},'trash':{'days':30}})
        if self.path=='/api/libraries':return self.respond([{'id':'external','name':'Camera','importPaths':['/photos']}])
        if self.path.startswith('/api/libraries/'):return self.respond(payload or {})
        if self.path=='/api/auth/session/unlock':return self.respond(None,204)
        if self.path=='/api/sessions':return self.respond([{'id':'session','current':True}])
        if self.path=='/api/sessions/session/lock':return self.respond(None,204)
        if self.path.startswith('/api/people'):return self.respond({'people':[{'id':'person','name':'Alice'}]})
        if self.path=='/api/tags':return self.respond([{'id':'tag','name':'Travel','value':'Travel'}])
        if self.path=='/api/duplicates':return self.respond([{'duplicateId':'duplicate','assets':ASSETS}])
        if self.path=='/api/queues':
            return self.respond({} if self.legacy else [{'name':'thumbnailGeneration','isPaused':False,'statistics':{'active':1,'waiting':4,'failed':0}}],404 if self.legacy else 200)
        if self.path=='/api/jobs':return self.respond({'thumbnailGeneration':{'queueStatus':{'isPaused':True},'jobCounts':{'waiting':2}}})
        if self.path.startswith('/api/queues/') and self.command=='PUT':return self.respond({'isPaused':payload['isPaused']})
        return self.respond({},404)

    do_GET=handle_request
    do_POST=handle_request
    do_PUT=handle_request


class LibraryTests(unittest.TestCase):
    def test_map_tilejson_is_inlined_cached_and_receives_no_account_token(self):
        with TemporaryDirectory() as root,patch.dict(os.environ,{'XDG_CACHE_HOME':root}):
            client=ImmichClient(self.address);client.token='test-session';client.user={'id':'map-test'}
            ImmichFixture.requests=[]
            style=client.map_style(True)
            source=style['sources']['world']
            self.assertNotIn('url',source)
            self.assertEqual(source['tiles'],[self.address+'/tiles/{z}/{x}/{y}.pbf'])
            self.assertEqual(source['maxzoom'],14)
            count=len(ImmichFixture.requests);self.assertEqual(client.map_style(True),style)
            self.assertEqual(len(ImmichFixture.requests),count)
            external=[entry for entry in ImmichFixture.requests if entry[1] in ('/map-style','/tile-source')]
            self.assertEqual(len(external),2);self.assertTrue(all(entry[3] is None for entry in external))

    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),ImmichFixture)
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.address=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def setUp(self):
        self.cache_root=TemporaryDirectory();self.addCleanup(self.cache_root.cleanup)
        env=patch.dict(os.environ,{'XDG_CACHE_HOME':self.cache_root.name});env.start();self.addCleanup(env.stop)
        ImmichFixture.requests=[];ImmichFixture.admin=True;ImmichFixture.legacy=False;ImmichFixture.denied=set()
        self.client=ImmichClient(self.address+'/api/')

    def login(self):self.client.login('test@example.invalid','test-password')

    def test_login_search_pages_and_authenticated_thumbnail(self):
        self.login()
        items,next_page=self.client.search()
        self.assertEqual((items[0].filename,items[0].ratio,next_page),('mountain.jpg',1.5,'opaque-next-page'))
        items,next_page=self.client.search(page=next_page)
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

    def test_current_filters_trash_album_and_complete_dates(self):
        self.login()
        self.client.search({'isTrashed':True})
        body=ImmichFixture.requests[-1][2]
        self.assertEqual(body['filter']['trashedAt'],{'ne':None})
        self.assertNotIn('isTrashed',body)
        self.client.search({'albumIds':['album'],'visibility':None})
        body=ImmichFixture.requests[-1][2]
        self.assertEqual(body['filter']['albumIds'],{'any':['album']})
        self.assertEqual(body['filter']['trashedAt'],{'eq':None})
        self.assertEqual(body['filter']['visibility'],{'in':['timeline','archive']})
        self.assertEqual(self.client.time_buckets()[-1]['timeBucket'],'2018-01-01')
        self.assertEqual(len(self.client.album('album')),2)
        self.assertFalse(any(r[1]=='/api/albums/album' for r in ImmichFixture.requests))

    def test_structured_paging_and_smart_search_do_not_mix_shapes(self):
        self.login()
        _,cursor=self.client.search()
        body=ImmichFixture.requests[-1][2]
        self.assertNotIn('page',body);self.assertNotIn('order',body)
        self.assertEqual(body['orderBy'],{'field':'fileCreatedAt','direction':'desc'})
        self.client.search(page=cursor)
        self.assertEqual(ImmichFixture.requests[-1][2]['cursor'],'opaque-next-page')
        _,page=self.client.search(query='landscape')
        self.client.search(query='landscape',page=page)
        self.assertEqual(ImmichFixture.requests[-1][2]['page'],2)
        self.assertNotIn('filter',ImmichFixture.requests[-1][2])
        self.client.search({'isTrashed':True},'landscape')
        body=ImmichFixture.requests[-1][2]
        self.assertTrue(body['withDeleted']);self.assertIn('trashedAfter',body)
        self.assertNotIn('isTrashed',body)

    def test_local_subfolder_depth(self):
        with TemporaryDirectory() as root:
            path=Path(root);(path/'one'/'two').mkdir(parents=True)
            for folder in [path,path/'one',path/'one'/'two']:(folder/'photo.jpg').write_bytes(b'image')
            self.assertEqual(len(scan_folders([root],recursive=False)[0]),1)
            self.assertEqual(len(scan_folders([root],max_depth=1)[0]),2)
            self.assertEqual(len(scan_folders([root],max_depth=0)[0]),3)

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

    def test_admin_user_create_update_and_locked_session(self):
        self.login()
        self.client.users_create({'name':'New user','email':'new@example.invalid','password':'dummy','notify':False})
        self.assertEqual(ImmichFixture.requests[-1][0:2],('POST','/api/admin/users'))
        self.client.users_update('new-user',{'name':'Changed','quotaSizeInBytes':1024})
        self.assertEqual(ImmichFixture.requests[-1][0:2],('PUT','/api/admin/users/new-user'))
        with self.assertRaises(LibraryError):self.client.search({'visibility':'locked'})
        self.client.unlock('123456')
        self.client.search({'visibility':'locked'})
        self.client.lock_session()
        self.assertEqual(self.client.locked_until,0)
        self.assertEqual(ImmichFixture.requests[-1][1],'/api/sessions/session/lock')

    def test_images_survive_client_restart_without_refetch(self):
        from library import media_from_asset
        self.login();item=media_from_asset(ASSETS[0])
        first=self.client.image_bytes(item)
        before=len(ImmichFixture.requests)
        client=ImmichClient(self.address);client.token=self.client.token;client.user=self.client.user
        self.assertEqual(client.image_bytes(item),first)
        self.assertEqual(len(ImmichFixture.requests),before)

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

    def test_locked_assets_never_enter_gallery_results(self):
        private=[dict(ASSETS[0],visibility=visibility) for visibility in ('locked','hidden')]
        with patch.object(self.client,'request',return_value={'assets':{'items':private,'nextPage':None}}):
            self.assertEqual(self.client.search(),([],None))
        with patch.object(self.client,'request',return_value={'assets':{'items':private,'nextPage':None}}):
            self.assertEqual(self.client.album('album'),[])
        with patch.object(self.client,'request',return_value=private[0]):
            self.assertIsNone(self.client.collection_cover('private-cover'))
        with patch.object(self.client,'request',return_value=[{'duplicateId':'private','assets':private}]):
            self.assertEqual(self.client.collection('duplicates'),[])
        self.assertIsNone(self.client.media_cache().get('cover-info:private-cover'))

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
