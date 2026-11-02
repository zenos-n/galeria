import json
import os
from http.server import ThreadingHTTPServer
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch
from test_library import ImmichFixture,ASSETS
from library import ImmichClient


class SharingFixture(ImmichFixture):
    links=[]
    members=[]
    album_count=1
    def handle_request(self):
        if self.path.startswith('/api/people/') and self.path.endswith('/thumbnail'):return self.respond(self.thumbnail)
        special=self.path.startswith('/api/shared-links') or self.path.startswith('/api/albums/album') or self.path=='/api/users' or self.path.startswith('/api/assets/')
        if self.path=='/api/albums':
            return self.respond([{'id':'album'+str(i) if i else 'album','albumName':'Trips '+str(i),'ownerId':'user','assetCount':2,'albumThumbnailAssetId':'cover'+str(i)} for i in range(self.album_count)])
        if not special:return super().handle_request()
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or b'null')
        self.requests.append((self.command,self.path,body,self.headers.get('Authorization')))
        if self.headers.get('Authorization')!='Bearer test-session':return self.respond({},401)
        if self.path.startswith('/api/assets/'):
            return self.respond(self.thumbnail if '/thumbnail' in self.path else dict(ASSETS[0],id=self.path.split('/')[3]))
        if self.path=='/api/users':return self.respond([{'id':'user','name':'Owner','email':'owner@example.invalid'},{'id':'alice','name':'Alice','email':'alice@example.invalid'},{'id':'bob','name':'Bob','email':'bob@example.invalid'}])
        if self.path.startswith('/api/shared-links'):
            if self.command=='POST':
                value=dict(body,id='link'+str(len(self.links)),key='fixture-public-key',assets=[dict(ASSETS[0],id=id) for id in body.get('assetIds',[])])
                self.links.append(value);return self.respond(value,201)
            if self.command=='DELETE':
                self.links[:]=[link for link in self.links if link['id']!=self.path.rsplit('/',1)[-1]];return self.respond(None,204)
            return self.respond(self.links)
        if '/user/' in self.path:
            user_id=self.path.rsplit('/',1)[-1]
            if self.command=='DELETE':self.members[:]=[m for m in self.members if m['user']['id']!=user_id]
            else:
                for member in self.members:
                    if member['user']['id']==user_id:member['role']=body['role']
            return self.respond(None,204)
        if self.path.endswith('/users'):
            for user in body['albumUsers']:self.members.append({'user':{'id':user['userId'],'name':'Bob'},'role':user['role']})
        return self.respond({'id':'album','albumName':'Trips','ownerId':'user','albumUsers':self.members,'assetCount':2})
    do_GET=handle_request;do_POST=handle_request;do_PUT=handle_request;do_DELETE=handle_request


class SharingTests(unittest.TestCase):
    def setUp(self):
        self.cache=TemporaryDirectory();self.addCleanup(self.cache.cleanup)
        env=patch.dict(os.environ,{'XDG_CACHE_HOME':self.cache.name});env.start();self.addCleanup(env.stop)
        SharingFixture.requests=[];SharingFixture.links=[];SharingFixture.members=[{'user':{'id':'user','name':'Owner'},'role':'editor'}]
        self.server=ThreadingHTTPServer(('127.0.0.1',0),SharingFixture)
        self.thread=Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
        self.client=ImmichClient(f'http://127.0.0.1:{self.server.server_port}');self.client.login('test@example.invalid','test-password')

    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()

    def test_album_link_create_list_revoke_and_subpath_url(self):
        link=self.client.share_album('album',{'allowDownload':False,'password':'fixture','expiresAt':None})
        self.assertEqual(link['type'],'ALBUM');self.assertEqual(link['albumId'],'album')
        self.assertEqual(self.client.shared_links('album')[0]['id'],link['id'])
        self.assertIn('/api/shared-links?albumId=album',[record[1] for record in SharingFixture.requests])
        self.assertEqual(self.client.share_url(link),self.client.base.removesuffix('/api')+'/share/fixture-public-key')
        other=ImmichClient('https://example.invalid/photos/api')
        self.assertEqual(other.share_url({'slug':'my album'}),'https://example.invalid/photos/share/my%20album')
        self.client.revoke_link(link['id']);self.assertEqual(self.client.shared_links(),[])

    def test_individual_links_and_album_collaborators(self):
        link=self.client.share_assets(['a','b'],{'allowDownload':True})
        self.assertEqual((link['type'],link['assetIds']),('INDIVIDUAL',['a','b']))
        self.client.invite_album('album','bob','viewer')
        self.assertEqual(self.client.album_info('album')['albumUsers'][-1]['role'],'viewer')
        self.client.album_member('album','bob','editor')
        self.assertEqual(self.client.album_info('album')['albumUsers'][-1]['role'],'editor')
        self.client.album_member('album','bob',remove=True)
        self.assertEqual(len(self.client.album_info('album')['albumUsers']),1)
        self.assertTrue(all(record[3]=='Bearer test-session' for record in SharingFixture.requests[1:]))


if __name__=='__main__':unittest.main()
