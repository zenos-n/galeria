from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch
from PIL import Image
from cache import MediaCache
from imaging import decode_image,duration_label


class MediaTests(unittest.TestCase):
    def test_webp_avif_jpeg_decode(self):
        for format in ('WEBP','AVIF','JPEG'):
            with self.subTest(format=format):
                stream=BytesIO();Image.new('RGB',(800,400),(40,80,140)).save(stream,format=format)
                width,height,data=decode_image(stream.getvalue())
                self.assertEqual((width,height,len(data)),(360,180,360*180*4))

    def test_duration_milliseconds_and_legacy_clock(self):
        for value,expected in [(31517,'0:31'),(134397,'2:14'),(3601000,'1:00:01'),('00:00:31.517','0:31'),(None,'Video')]:
            self.assertEqual(duration_label(value),expected)

    def test_cache_persists_isolates_accounts_expires_and_bounds(self):
        with TemporaryDirectory() as root:
            a=MediaCache('server|user-a',root,budget=6)
            a.put('one',b'1234');a.put('two',b'5678')
            self.assertIsNone(a.get('one'));self.assertEqual(a.get('two'),b'5678')
            self.assertEqual(MediaCache('server|user-a',root).get('two'),b'5678')
            self.assertIsNone(MediaCache('server|user-b',root).get('two'))
            os.utime(a.path('two'),(0,0));self.assertIsNone(a.get('two',10))

    def test_concurrent_cache_miss_fetches_once(self):
        with TemporaryDirectory() as root:
            cache=MediaCache('account',root);calls=[]
            def load():calls.append(1);time.sleep(.03);return b'image'
            with ThreadPoolExecutor(4) as pool:
                results=list(pool.map(lambda _:cache.fetch('same',load),range(4)))
            self.assertEqual(results,[b'image']*4);self.assertEqual(len(calls),1)

    def test_cache_writes_scan_once_and_keep_eviction_accounting(self):
        with TemporaryDirectory() as root:
            cache=MediaCache('account',root,budget=100)
            with patch('cache.os.scandir',wraps=os.scandir) as scans:
                for i in range(200):cache.put(str(i),b'1234')
                self.assertEqual(scans.call_count,1)
            self.assertEqual(sum(p.stat().st_size for p in cache.root.iterdir()),100)
            self.assertIsNone(cache.get('0'));self.assertEqual(cache.get('199'),b'1234')
            cache.put('199',b'12');cache.remove('198')
            self.assertEqual(cache.total_bytes,94)
            # Another writer is reconciled without evicting an updated entry as stale.
            cache.path('199').write_bytes(b'123456')
            cache.scanned_at=0;cache.prune()
            self.assertEqual(cache.total_bytes,98)
            cache.clear();cache.put('new',b'fresh')
            self.assertEqual(cache.total_bytes,5)

    def test_locked_cache_and_original_are_authenticated_ciphertext(self):
        with TemporaryDirectory() as root:
            cache=MediaCache('vault',root,key=os.urandom(32))
            cache.put('metadata',b'private filename and thumbnail')
            self.assertNotIn(b'private',cache.path('metadata').read_bytes())
            self.assertEqual(cache.get('metadata'),b'private filename and thumbnail')
            cache.sync_encrypted('original',BytesIO(b'private original'*10000),threading.Event())
            self.assertEqual(cache.get('original'),b'private original'*10000)
            data=bytearray(cache.path('original').read_bytes());data[-1]^=1;cache.path('original').write_bytes(data)
            self.assertIsNone(cache.get('original'))
            self.assertEqual(os.stat(cache.path('metadata')).st_mode&0o777,0o600)

    def test_device_copies_are_retained_and_cancelled_writes_are_removed(self):
        with TemporaryDirectory() as root:
            cache=MediaCache('copies',root,key=os.urandom(32),budget=None)
            cache.sync_encrypted('original',BytesIO(b'original'*1000),threading.Event())
            cache.put('thumbnail',b'image')
            self.assertEqual(cache.get('original'),b'original'*1000)
            cancel=threading.Event()
            class CancelledStream(BytesIO):
                def read(self,*args):
                    data=super().read(*args);cancel.set();return data
            with self.assertRaises(InterruptedError):cache.sync_encrypted('cancelled',CancelledStream(b'private'),cancel)
            self.assertFalse(cache.has('cancelled'))
            self.assertEqual(len(list(cache.root.iterdir())),2)


if __name__=='__main__':unittest.main()
