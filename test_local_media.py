import hashlib,threading,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace
from local_media import copies_for,remember_copy,trash_copies,local_paths
from sync_engine import SyncJournal
from library import LibraryError


class LocalMediaTests(unittest.TestCase):
    def setUp(self):
        self.root=TemporaryDirectory();self.addCleanup(self.root.cleanup);self.path=Path(self.root.name)/'photo.png';self.path.write_bytes(b'original')
        self.journal=Path(self.root.name)/'journal.sqlite';self.patch=patch('local_media.journal_path',return_value=self.journal);self.patch.start();self.addCleanup(self.patch.stop)
        self.client=SimpleNamespace(identity='server|user',trash_assets=lambda ids:None)
        self.item=SimpleNamespace(id='asset',path=None)
        self.remember()
    def remember(self):remember_copy(self.client,self.path,'asset',hashlib.sha1(self.path.read_bytes()).hexdigest(),self.path.stat())
    def test_full_local_paths_are_account_scoped_and_survive_missing_original(self):
        self.assertEqual(local_paths(self.client,self.item),[str(self.path)])
        self.assertEqual(local_paths(SimpleNamespace(identity='other'),self.item),[])
        self.path.unlink()
        self.assertEqual(local_paths(self.client,self.item),[str(self.path)])
        self.assertEqual(local_paths(None,SimpleNamespace(path=str(self.path))),[str(self.path)])
    def test_scope_and_account_isolation(self):
        local,cloud=copies_for(self.client,[self.item]);self.assertEqual(len(local),1);self.assertEqual(cloud,['asset'])
        calls=[];self.client.trash_assets=lambda ids:calls.append(ids)
        trash=lambda path:(calls.append(path),True)[1]
        self.assertEqual(trash_copies(self.client,local,cloud,'cloud',trash),([],True,[]));self.assertEqual(calls,[['asset']]);self.assertTrue(self.path.exists())
        calls.clear();self.assertEqual(trash_copies(self.client,local,cloud,'local',trash),([str(self.path)],False,[]));self.assertEqual(calls,[str(self.path)])
        calls.clear();self.assertEqual(trash_copies(self.client,local,cloud,'both',trash),([str(self.path)],True,[]));self.assertEqual(calls,[['asset'],str(self.path)])
        self.assertEqual(copies_for(SimpleNamespace(identity='other'),[self.item]),([],['asset']))
    def test_changed_or_replaced_files_are_kept(self):
        local,cloud=copies_for(self.client,[self.item]);stat=self.path.stat();self.path.write_bytes(b'modified')
        import os
        os.utime(self.path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        calls=[];removed,remote,errors=trash_copies(self.client,local,cloud,'both',calls.append)
        self.assertEqual(removed,[]);self.assertTrue(remote);self.assertEqual(len(errors),1);self.assertFalse(calls)
        self.path.unlink();other=self.path.with_name('other');other.write_bytes(b'original');self.path.symlink_to(other)
        removed,remote,errors=trash_copies(self.client,local,cloud,'local',calls.append);self.assertFalse(removed);self.assertEqual(len(errors),1);self.assertTrue(other.exists())
    def test_remote_failure_keeps_originals_and_local_failure_is_reported(self):
        local,cloud=copies_for(self.client,[self.item]);calls=[]
        def fail(ids):raise LibraryError('network failed')
        self.client.trash_assets=fail
        with self.assertRaises(LibraryError):trash_copies(self.client,local,cloud,'both',calls.append)
        self.assertFalse(calls);self.assertEqual(self.path.read_bytes(),b'original')
        self.client.trash_assets=lambda ids:None
        result=trash_copies(self.client,local,cloud,'both',lambda path:False)
        self.assertEqual(result[:2],([],True));self.assertEqual(len(result[2]),1)
    def test_sync_journal_and_direct_device_file_associations(self):
        localitem=SimpleNamespace(id='local-id',path=str(self.path));local,cloud=copies_for(self.client,[localitem]);self.assertEqual(cloud,['asset'])
        direct,cloud=copies_for(None,[localitem]);self.assertEqual(len(direct),1);self.assertEqual(cloud,[])
        journal=SyncJournal(self.journal)
        try:journal.record(self.client.identity,'sync-rule',self.path,self.path.stat(),hashlib.sha1(self.path.read_bytes()).hexdigest(),'asset','')
        finally:journal.close()
        local,cloud=copies_for(self.client,[self.item]);self.assertEqual(len(local),1)

    def test_synced_only_excludes_device_copies_and_other_accounts(self):
        self.assertEqual(copies_for(self.client,[self.item],synced_only=True),([],['asset']))
        other=self.path.with_name('other-account.png');other.write_bytes(b'original')
        journal=SyncJournal(self.journal)
        try:
            journal.record(self.client.identity,'folder-rule',self.path,self.path.stat(),hashlib.sha1(self.path.read_bytes()).hexdigest(),'asset','')
            journal.record('other','folder-rule',other,other.stat(),hashlib.sha1(other.read_bytes()).hexdigest(),'asset','')
        finally:journal.close()
        local,cloud=copies_for(self.client,[self.item],synced_only=True)
        self.assertEqual([row[0] for row in local],[str(self.path)])
        self.assertEqual(cloud,['asset'])
        self.assertEqual(copies_for(None,[SimpleNamespace(path=str(other))],synced_only=True),([],[]))

    def test_manual_upload_and_download_record_real_associations(self):
        from upload_media import upload
        from downloads import save_original
        from io import BytesIO
        client=self.client
        client.request=lambda *args,**kwargs:{'results':[{'action':'reject','assetId':'duplicate'}]}
        self.assertEqual(upload(client,self.path,threading.Event()),('duplicate',False))
        local,cloud=copies_for(client,[SimpleNamespace(id='duplicate',path=None)])
        self.assertEqual(len(local),1)
        def source(item):
            stream=BytesIO(b'downloaded bytes');stream.headers={'Content-Length':'16'};return stream
        client.open_original=source;client.check_original_access=lambda item:None
        target=Path(self.root.name)/'download.png';save_original(client,self.item,target,threading.Event())
        local,cloud=copies_for(client,[self.item]);self.assertIn(str(target),[row[0] for row in local])
        self.assertEqual(target.read_bytes(),b'downloaded bytes')

    def test_replaced_fifo_is_kept_without_blocking_the_worker(self):
        import os
        local,cloud=copies_for(self.client,[self.item]);self.path.unlink();os.mkfifo(self.path)
        calls=[];removed,remote,errors=trash_copies(self.client,local,cloud,'local',calls.append)
        self.assertEqual(removed,[]);self.assertFalse(remote);self.assertEqual(len(errors),1);self.assertFalse(calls)
