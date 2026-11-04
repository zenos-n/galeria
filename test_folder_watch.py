import json,os,time,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from folder_watch import FolderWatch


class FolderWatchTests(unittest.TestCase):
    def test_new_and_moved_subfolders_notify_without_scan_timer(self):
        with TemporaryDirectory() as temp:
            base=Path(temp);root=base/'photos';root.mkdir();config=base/'sync.json'
            config.write_text(json.dumps({'accounts':{'a':{'enabled':True,'folders':[{'path':str(root),'recursive':True,'max_depth':0}]}}}))
            changed=Event();watch=FolderWatch(config,changed.set)
            try:
                self.assertTrue(watch.ready.wait(3));start=time.monotonic();(root/'new.jpg').write_bytes(b'new')
                self.assertTrue(changed.wait(2));self.assertLess(time.monotonic()-start,2)
                time.sleep(.35);changed.clear();child=root/'new-folder';child.mkdir();(child/'clip.mp4').write_bytes(b'clip')
                self.assertTrue(changed.wait(2));time.sleep(.35);changed.clear()
                (child/'next.jpg').write_bytes(b'next');self.assertTrue(changed.wait(2))
                time.sleep(.35);changed.clear();(root/'ignored.txt').write_text('ignored');self.assertFalse(changed.wait(.6))
            finally:watch.close()
            self.assertFalse(watch.thread.is_alive())

    def test_depth_and_disabled_rules(self):
        with TemporaryDirectory() as temp:
            base=Path(temp);root=base/'photos';deep=root/'one'/'two';deep.mkdir(parents=True);config=base/'sync.json'
            config.write_text(json.dumps({'accounts':{'a':{'enabled':True,'folders':[{'path':str(root),'recursive':True,'max_depth':1}]}}}))
            changed=Event();watch=FolderWatch(config,changed.set)
            try:
                self.assertTrue(watch.ready.wait(3));self.assertNotIn(deep,watch.monitors)
                (deep/'no.jpg').write_bytes(b'no');self.assertFalse(changed.wait(.5))
                (root/'one'/'yes.jpg').write_bytes(b'yes');self.assertTrue(changed.wait(2))
                time.sleep(.35);changed.clear();config.write_text(json.dumps({'accounts':{}}));self.assertTrue(changed.wait(2))
                time.sleep(.35);changed.clear();(root/'quiet.jpg').write_bytes(b'quiet');self.assertFalse(changed.wait(.5))
            finally:watch.close()
