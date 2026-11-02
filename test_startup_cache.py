from datetime import datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from PIL import Image
from cache import MediaCache
from library import ImmichClient,MediaItem
from unittest.mock import patch
import os
from startup_cache import restore


class StartupCacheTests(unittest.TestCase):
    def test_cached_metadata_and_pixels_restore_without_network(self):
        with TemporaryDirectory() as root:
            image=BytesIO();Image.new('RGB',(80,40),'purple').save(image,format='JPEG')
            cache=MediaCache('account',root=root);cache.put('image:one',image.getvalue())
            class Client:
                def media_cache(self):return cache
                def time_buckets(self,cached=False):
                    assert cached;return [{'timeBucket':'2026-01-01','count':1}]
                def time_bucket(self,key,cached=False):
                    assert cached;return [MediaItem('one','one.jpg',datetime(2026,1,1),2,metadata={'visibility':'timeline'})]
                def image_key(self,item):return 'image:'+item.id
            buckets,index,pixels=restore(Client(),1000,700)
            self.assertEqual(index.loaded,{'2026-01'});self.assertEqual(len(index.items),1)
            self.assertEqual(pixels['one'][:2],(80,40));self.assertEqual(len(pixels['one'][2]),80*40*4)
            cache.clear();self.assertIsNone(restore(type('Empty',(),{'time_buckets':lambda _,cached:None})(),1000,700))

    def test_real_client_restores_expired_disk_snapshots_without_http_or_unlock(self):
        with TemporaryDirectory() as root:
            client=ImmichClient('https://fixture.invalid');client.user={'id':'user'}
            client.cache=MediaCache(client.identity,root=root)
            buckets=[{'timeBucket':'2026-01-01','count':1}]
            compact={'id':['one'],'ratio':[2],'fileCreatedAt':['2026-01-01T12:00:00Z'],'isImage':[True],'visibility':['timeline']}
            with patch.object(client,'request',side_effect=[buckets,compact]) as request:
                client.time_buckets();item=client.time_bucket('2026-01')[0]
                self.assertEqual(request.call_count,2)
            image=BytesIO();Image.new('RGB',(80,40),'purple').save(image,format='PNG')
            client.cache.put(client.image_key(item),image.getvalue())
            for path in client.cache.root.iterdir():os.utime(path,(1,1))
            client.server_lock_pending=True
            with patch.object(client,'request',side_effect=AssertionError('HTTP during cached startup')):
                _,index,pixels=restore(client,1000,700)
            self.assertTrue(client.server_lock_pending);self.assertEqual(index.loaded,{'2026-01'})
            self.assertEqual(pixels['one'][:2],(80,40))
