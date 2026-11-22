import json,os,unittest
from datetime import datetime
from tempfile import TemporaryDirectory
from unittest.mock import patch
from library import MediaItem,LibraryError
from timeline_visibility import TimelineVisibility,rules_for
from checks.visibility_fixture import Client


class TimelineVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.root=TemporaryDirectory();self.env=patch.dict(os.environ,{'XDG_CACHE_HOME':self.root.name});self.env.start()
        self.client=Client()

    def tearDown(self):self.env.stop();self.root.cleanup()

    def test_screenshots_album_members_union_counts_and_raw_cache(self):
        client=self.client;raw=client.time_buckets();client.time_bucket('2026-11')
        policy=client.timeline_visibility=TimelineVisibility({'screenshots':True,'albums':['hidden']})
        self.assertEqual(client.time_buckets(),[{'timeBucket':'2026-11-01','count':1}])
        self.assertEqual(policy.ids,{'shot','numeric','download','ancient'})
        self.assertEqual([item.id for item in client.time_bucket('2026-11')],['camera'])
        self.assertEqual([item.id for item in client.album('hidden')],['shot','download'])
        self.assertEqual(len(client.search()[0]),5)
        client.timeline_visibility=TimelineVisibility()
        self.assertEqual(client.time_buckets(cached=True),raw)
        self.assertEqual(len(client.time_bucket('2026-11',cached=True)),3)
        self.assertFalse(any(method for _,_,method in client.calls))

    def test_cached_restart_without_network_and_changed_membership(self):
        client=self.client;client.timeline_visibility=TimelineVisibility({'screenshots':True})
        expected=client.time_buckets();client.time_bucket('2026-11')
        client.timeline_visibility=TimelineVisibility({'screenshots':True})
        with patch.object(client,'request',side_effect=AssertionError('HTTP during cached restore')):
            self.assertEqual(client.time_buckets(cached=True),expected)
            self.assertEqual([item.id for item in client.time_bucket('2026-11',cached=True)],['camera','download'])
        client.assets[-1]['albums']=['hidden'];client.assets[0]['albums']=['screens']
        client.album_values[0]['assetCount']=3;client.album_values[0]['updatedAt']='2'
        client.media_cache().remove('albums');client.refresh_serial=1
        self.assertEqual(client.time_buckets(),[{'timeBucket':'2026-11-01','count':1}])
        self.assertIn('camera',client.timeline_visibility.ids)

    def test_bucket_change_finds_new_old_dated_screenshot(self):
        client=self.client;client.timeline_visibility=TimelineVisibility({'screenshots':True});client.time_buckets()
        new={**client.assets[0],'id':'new','originalFileName':'screen_shot.png','fileCreatedAt':'1999-01-01T12:00:00Z','localDateTime':'1999-01-01T12:00:00'}
        client.assets.append(new);client.refresh_serial=1
        self.assertEqual(client.time_buckets(fresh=True),[{'timeBucket':'2026-11-01','count':2}])
        self.assertIn('new',client.timeline_visibility.ids)

    def test_local_folder_boundaries_screenshots_and_account_scope(self):
        policy=TimelineVisibility({'folders':['/photos/private'],'screenshots':True})
        def item(path):return MediaItem(path,path.split('/')[-1],datetime.now(),path=path)
        self.assertEqual([x.path for x in policy.filter([item('/photos/private/a.jpg'),item('/photos/private2/b.jpg'),item('/photos/Screenshots/123.png'),item('/photos/Screen Shot.png')])],['/photos/private2/b.jpg'])
        prefs={'timeline_visibility':{'server-a|me':{'albums':['a']}}}
        self.assertEqual(rules_for(prefs,'server-a|me'),{'albums':['a']})
        self.assertEqual(rules_for(prefs,'server-a|other'),{})
        self.assertEqual(rules_for(prefs,'server-b|me'),{})

    def test_filtered_paging_fills_page_and_rejects_loop(self):
        client=self.client;policy=client.timeline_visibility=TimelineVisibility({'screenshots':True});client.time_buckets()
        items,cursor=policy.search(client,{},size=2)
        self.assertEqual([x.id for x in items],['camera','download']);self.assertEqual(cursor,'4')
        with patch.object(client,'search',return_value=([],1)):
            with self.assertRaises(LibraryError):policy.search(client,{},size=2)

    def test_missing_deleted_album_and_same_month_buckets(self):
        client=self.client;policy=TimelineVisibility({'albums':['deleted','hidden']})
        values=policy.buckets(client,[{'timeBucket':'2026-11-01','count':1},{'timeBucket':'2026-11-02','count':2}])
        self.assertEqual(values,[{'timeBucket':'2026-11-01','count':1}])
        bodies=[body for path,body,_ in client.calls if path=='/search/metadata']
        self.assertEqual(bodies[0]['filter']['albumIds']['any'],['hidden'])

    def test_missing_or_corrupt_snapshot_never_leaks_during_cached_restore(self):
        client=self.client;policy=client.timeline_visibility=TimelineVisibility({'screenshots':True})
        self.assertIsNone(client.time_buckets(cached=True))
        client.media_cache().put(policy.cache_key,b'invalid')
        self.assertEqual(client.time_buckets(),[{'timeBucket':'2026-11-01','count':2}])
        client.media_cache().remove(policy.cache_key)
        with patch.object(client,'request',side_effect=AssertionError('Unexpected HTTP')):self.assertIsNone(client.time_buckets(cached=True))

    def test_failed_refresh_preserves_raw_metadata_for_offline_restart(self):
        client=self.client;buckets=client.time_buckets();items=client.time_bucket('2026-11')
        with patch.object(client,'request',side_effect=LibraryError('Offline')):
            with self.assertRaises(LibraryError):client.time_buckets(fresh=True)
            with self.assertRaises(LibraryError):client.time_bucket('2026-11',fresh=True)
            self.assertEqual(client.time_buckets(cached=True),buckets)
            self.assertEqual(client.time_bucket('2026-11',cached=True),items)

    def test_shared_album_outside_main_timeline_does_not_hide_unrelated_photos(self):
        client=self.client
        client.assets.append({**client.assets[0],'id':'shared','ownerId':'other','albums':['hidden']})
        client.album_values[1]['assetCount']=3
        client.timeline_visibility=TimelineVisibility({'albums':['hidden']})
        buckets=client.time_buckets()
        self.assertEqual(sum(bucket['count'] for bucket in buckets),3)
        self.assertNotIn('shared',client.timeline_visibility.ids)
        self.assertEqual([item.id for item in client.time_bucket('2026-11')],['camera'])


if __name__=='__main__':unittest.main()
