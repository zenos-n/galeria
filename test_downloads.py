from datetime import datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from downloads import DownloadCancelled,filename,save_original
from library import LibraryError,MediaItem


class DownloadsTest(unittest.TestCase):
    def test_originals_are_streamed_without_overwriting_sources_or_batch_names(self):
        with TemporaryDirectory() as root:
            root=Path(root);source=root/'source.jpg';source.write_bytes(b'original')
            item=MediaItem('one','source.jpg',datetime.now(),path=str(source))
            with self.assertRaises(LibraryError):save_original(None,item,source,Event())
            target=root/'copy.jpg';target.write_bytes(b'keep')
            result=save_original(None,item,target,Event(),overwrite=False)
            self.assertEqual(result.name,'copy (2).jpg');self.assertEqual(result.read_bytes(),b'original')
            self.assertEqual(source.read_bytes(),b'original');self.assertEqual(target.read_bytes(),b'keep')
            self.assertEqual(filename('../../unsafe.jpg'),'unsafe.jpg')
            self.assertEqual(filename('..\\unsafe.jpg'),'unsafe.jpg')

    def test_cancel_and_truncated_transfer_keep_existing_destination(self):
        class Client:
            def check_original_access(self,item):pass
            def open_original(self,item):
                stream=BytesIO(b'new data');stream.headers={'Content-Length':'80'};return stream
        with TemporaryDirectory() as root:
            target=Path(root)/'download.jpg';target.write_bytes(b'existing')
            item=MediaItem('one','one.jpg',datetime.now());cancel=Event()
            with self.assertRaises(LibraryError):save_original(Client(),item,target,cancel)
            self.assertEqual(target.read_bytes(),b'existing')
            cancel.set()
            with self.assertRaises(DownloadCancelled):save_original(Client(),item,target,cancel)
            self.assertEqual(list(Path(root).iterdir()),[target])

    def test_large_original_and_cancellation_during_transfer(self):
        body=b'0123456789'*4000000
        class Client:
            def check_original_access(self,item):pass
            def open_original(self,item):
                stream=BytesIO(body);stream.headers={'Content-Length':str(len(body))};return stream
        with TemporaryDirectory() as root:
            item=MediaItem('one','one.mp4',datetime.now(),kind='VIDEO');target=Path(root)/'video.mp4'
            save_original(Client(),item,target,Event());self.assertEqual(target.read_bytes(),body)
            cancel=Event()
            with self.assertRaises(DownloadCancelled):save_original(Client(),item,target,cancel,lambda *_:cancel.set())
            self.assertEqual(target.read_bytes(),body)
            self.assertEqual(list(Path(root).iterdir()),[target])
