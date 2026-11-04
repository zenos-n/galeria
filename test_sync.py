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

    def test_upload_activity_excludes_scans_and_duplicates(self):
        events=[];engine=SyncEngine(self.client,self.journal,progress=lambda value:events.append(value))
        def upload(*args):
            self.assertEqual(events[-1].get('uploading'),self.path.name)
            return 'asset'
        with patch('sync_engine.upload_file',side_effect=upload):engine.run_folder(self.rule)
        self.assertTrue(any(value.get('uploading') for value in events));self.assertNotIn('uploading',events[-1])
        events.clear();engine.run_folder(self.rule);self.assertFalse(any(value.get('uploading') for value in events))
        other=self.path.with_name('downloaded.png');other.write_bytes(self.path.read_bytes());os.utime(other,(0,0))
        self.client.duplicate=True;events.clear()
        with patch('sync_engine.upload_file') as upload:engine.run_folder(self.rule);upload.assert_not_called()
        self.assertFalse(any(value.get('uploading') for value in events))

    def test_new_files_after_first_scan_are_uploaded_without_restarting(self):
        engine=SyncEngine(self.client,self.journal)
        with patch('sync_engine.upload_file',return_value='asset') as upload:
            self.assertEqual(engine.run_folder(self.rule)['uploaded'],1)
            clips=self.root/'Clips';clips.mkdir();clip=clips/'new.mp4';clip.write_bytes(b'new clip')
            os.utime(clip,(time.time()-10,time.time()-10))
            counts=engine.run_folder(self.rule)
            self.assertEqual(counts['uploaded'],1);self.assertEqual(counts['unchanged'],1)
            self.assertEqual(upload.call_args.args[1],clip)
            self.assertEqual(engine.run_folder(self.rule)['unchanged'],2)
            self.assertEqual(upload.call_count,2);self.assertEqual(clip.read_bytes(),b'new clip')

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
            self.assertFalse(any('kill' in call.args[0] for call in command.call_args_list))

    def test_request_upgrades_an_active_old_runtime_but_only_wakes_the_current_one(self):
        import sync_service
        from types import SimpleNamespace
        config=Path(self.temp.name)/'config';unit=config/'systemd/user'/sync_service.UNIT
        unit.parent.mkdir(parents=True);unit.write_text('ExecStart="/tmp/old-runtime"')
        with patch.dict(os.environ,{'XDG_CONFIG_HOME':str(config)}),patch.object(sync_service,'runtime_command',return_value=['/tmp/new-runtime']),patch.object(sync_service,'command',return_value=SimpleNamespace(returncode=0)) as command,patch.object(sync_service,'install_service') as install:
            sync_service.request_sync();install.assert_called_once()
            self.assertIn((['systemctl','--user','restart',sync_service.UNIT],),[call.args for call in command.call_args_list])
            install.reset_mock();command.reset_mock();unit.write_text('ExecStart="/tmp/new-runtime"')
            sync_service.request_sync();install.assert_not_called()
            self.assertIn((['systemctl','--user','kill','-s','USR1',sync_service.UNIT],),[call.args for call in command.call_args_list])


if __name__=='__main__':unittest.main()
