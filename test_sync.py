import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from sync_engine import SyncEngine,SyncJournal,upload_file
from library import ImmichClient


class Client:
    identity='fixture-account'
    user={'id':'user'}
    modern_search=True

    def __init__(self):self.requests=[];self.duplicate=False
    def request(self,path,body=None,method='POST'):
        self.requests.append((path,body,method))
        if path.endswith('bulk-upload-check'):
            return {'results':[{'action':'reject','assetId':'existing'} if self.duplicate else {'action':'accept'}]}
        return {}


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'photos';self.root.mkdir()
        self.path=self.root/'original.jpg';self.path.write_bytes(b'original')
        os.utime(self.path,(time.time()-10,time.time()-10))
        self.journal=SyncJournal(Path(self.temp.name)/'state'/'sync.sqlite');self.addCleanup(self.journal.close)
        self.client=Client();self.rule={'id':'rule','path':str(self.root),'recursive':True,'max_depth':0,'album_id':'album'}

    def test_upload_idempotence_change_and_deletion_preserve_originals(self):
        engine=SyncEngine(self.client,self.journal)
        with patch('sync_engine.upload_file',return_value='asset') as upload:
            self.assertEqual(engine.run_folder(self.rule)['uploaded'],1)
            self.assertEqual(engine.run_folder(self.rule)['unchanged'],1)
            self.assertEqual(upload.call_count,1)
            self.assertEqual(self.path.read_bytes(),b'original')
            self.path.write_bytes(b'changed');os.utime(self.path,(time.time()-10,time.time()-10))
            self.assertEqual(engine.run_folder(self.rule)['uploaded'],1)
            self.path.unlink();self.assertEqual(engine.run_folder(self.rule)['uploaded'],0)
        self.assertFalse(any(method=='DELETE' for _,_,method in self.client.requests))

    def test_duplicates_added_without_upload_and_pause_stops_pass(self):
        self.client.duplicate=True
        with patch('sync_engine.upload_file') as upload:
            self.assertEqual(SyncEngine(self.client,self.journal).run_folder(self.rule)['existing'],1)
            upload.assert_not_called()
        self.assertTrue(any(path=='/albums/album/assets' for path,_,_ in self.client.requests))
        self.client.requests.clear()
        SyncEngine(self.client,self.journal,valid_rule=lambda _:False).run_folder(self.rule)
        self.assertEqual(self.client.requests,[])

    def test_folders_map_to_separate_albums_and_respect_depth(self):
        child=self.root/'Trips';child.mkdir();photo=child/'photo.jpg';photo.write_bytes(b'child');os.utime(photo,(time.time()-10,time.time()-10))
        deep=child/'deep';deep.mkdir();nested=deep/'photo.jpg';nested.write_bytes(b'deep');os.utime(nested,(time.time()-10,time.time()-10))
        engine=SyncEngine(self.client,self.journal);destinations=[]
        def destination(rule):destinations.append((rule['id'],rule['album_name']));return rule['album_name']
        rule={**self.rule,'folder_albums':True,'max_depth':1}
        with patch.object(engine,'destination',side_effect=destination),patch('sync_engine.upload_file',return_value='asset'):
            self.assertEqual(engine.run_folder(rule)['uploaded'],2)
            self.assertEqual({name for _,name in destinations},{'photos','photos / Trips'})
            self.assertEqual(engine.run_folder(rule)['unchanged'],2)
        self.assertEqual(nested.read_bytes(),b'deep');self.assertFalse(any(method=='DELETE' for _,_,method in self.client.requests))

    def test_actual_multipart_upload_and_confirmation(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from threading import Thread,Event
        captured={}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                captured['body']=self.rfile.read(int(self.headers['Content-Length']))
                captured['auth']=self.headers['Authorization'];captured['path']=self.path
                self.send_response(201);self.end_headers();self.wfile.write(b'{"id":"uploaded"}')
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            client=ImmichClient(f'http://127.0.0.1:{server.server_port}');client.token='fixture'
            result=upload_file(client,self.path,'checksum',self.path.stat(),Event())
            self.assertEqual(result,'uploaded');self.assertEqual(captured['path'],'/api/assets')
            self.assertEqual(captured['auth'],'Bearer fixture')
            self.assertIn(b'name="assetData"',captured['body']);self.assertIn(b'original',captured['body'])
            self.assertEqual(self.path.read_bytes(),b'original')
        finally:server.shutdown();server.server_close();thread.join()

    def test_service_installation_is_scoped_and_no_user_activation_in_test(self):
        import sync_service
        config=Path(self.temp.name)/'config'
        with patch.dict(os.environ,{'XDG_CONFIG_HOME':str(config)}),patch.object(sync_service,'runtime_command',return_value=['/tmp/gallery-sync']),patch.object(sync_service,'command') as command:
            sync_service.install_service()
            unit=(config/'systemd/user'/sync_service.UNIT).read_text()
            self.assertIn('ExecStart="/tmp/gallery-sync"',unit)
            self.assertIn('WantedBy=default.target',unit)
            self.assertIn((['systemctl','--user','enable','--now',sync_service.UNIT],),[call.args for call in command.call_args_list])


if __name__=='__main__':unittest.main()
