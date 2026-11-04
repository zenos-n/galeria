from datetime import datetime
from threading import Event
from tempfile import TemporaryDirectory
import unittest
from cache import MediaCache
from date_motion import groups,cover_area
from image_queue import ImageQueue
from library import MediaItem
from timeline_index import TimelineIndex


class TimelineIndexTests(unittest.TestCase):
    def test_full_scroll_slots_and_compact_sizes_removal(self):
        index=TimelineIndex([{'timeBucket':'2026-01-01','count':3},{'timeBucket':'2018-02-01','count':2}])
        self.assertEqual(len(index.items),5);self.assertTrue(all(item.metadata['placeholder'] for item in index.items))
        values=[MediaItem(str(i),str(i),datetime(2026,1,3-i),ratio) for i,ratio in enumerate([.5,1,2])]
        self.assertFalse(index.apply('2026-01',values));self.assertEqual([item.ratio for item in index.items[:3]],[.5,1,2])
        self.assertTrue(index.apply('2018-02',[MediaItem('old','old',datetime(2018,2,1))]))
        self.assertEqual(len(index.items),4)
        result=index.without(['1']);self.assertEqual(result.ranges,{'2026-01':(0,2),'2018-02':(2,3)})
        self.assertNotIn('1',[item.id for item in result.items]);self.assertEqual(len(index.items),4)

    def test_every_month_flows_into_its_year_inside_final_cover(self):
        source=[('jan','a',(0,0,150,150,1)),('dec','b',(165,0,150,150,1)),('old','c',(330,0,150,150,1))]
        target=[('jan','a',(5,5,69,70.5,1))]
        cards={'2026':(0,0,150,182,1),'2025':(165,0,150,182,1)}
        planned=groups(source,target,{'jan':'2026-01','dec':'2025-12','old':'2025-11'},'years',cards)
        self.assertEqual({key:len(images) for key,images,_,_ in planned},{'2026':1,'2025':2})
        for key,images,start,end in planned:
            self.assertEqual(end,cover_area(cards[key]))
            for _,_,_,rect in images:
                self.assertGreaterEqual(rect[0],end[0]);self.assertGreaterEqual(rect[1],end[1])
                self.assertLessEqual(rect[0]+rect[2],end[0]+end[2]);self.assertLessEqual(rect[1]+rect[3],end[1]+end[3])

    def test_pending_downloads_reprioritize_and_shutdown_cancels(self):
        pool=ImageQueue(1);gate=Event();started=Event();order=[];priorities={'old':0,'visible':10}
        first=pool.submit(lambda:(started.set(),gate.wait(3)))
        self.assertTrue(started.wait(1))
        a=pool.submit(lambda:order.append('old'),lambda:priorities['old'])
        b=pool.submit(lambda:order.append('visible'),lambda:priorities['visible'])
        priorities.update(old=10,visible=0);gate.set();first.result(3);a.result(3);b.result(3)
        pool.shutdown();self.assertEqual(order,['visible','old'])

    def test_cache_clear_blocks_inflight_and_new_locked_thumbnail_writes(self):
        with TemporaryDirectory() as root:
            cache=MediaCache('fixture',root=root);started=Event();gate=Event();pool=ImageQueue(1)
            def load():started.set();gate.wait(3);return b'private'
            future=pool.submit(lambda:cache.fetch('asset:thumbnail',load));self.assertTrue(started.wait(1))
            cache.put('keep:thumbnail',b'public');cache.put('stale-metadata',b'private name')
            cache.forbid(['asset:'],preserve=['keep:thumbnail','asset:preview']);gate.set();future.result(3);pool.shutdown()
            self.assertEqual(cache.get('keep:thumbnail'),b'public')
            self.assertIsNone(cache.get('stale-metadata'))
            self.assertEqual(MediaCache('fixture',root=root).get('keep:thumbnail'),b'public')
            self.assertIsNone(cache.get('asset:thumbnail'))
            cache.put('asset:preview',b'private');self.assertIsNone(cache.get('asset:preview'))

    def test_abandoned_image_jobs_are_reaped_in_one_pass(self):
        pool=ImageQueue(1);started=Event();gate=Event();evaluated=[];work=[]
        first=pool.submit(lambda:(started.set(),gate.wait(3)));self.assertTrue(started.wait(1))
        stale=[pool.submit(lambda:work.append('stale'),lambda:(evaluated.append(1),None)[1]) for _ in range(1000)]
        visible=pool.submit(lambda:work.append('visible'),0)
        gate.set();first.result(3);visible.result(3)
        self.assertTrue(all(future.result(3) is None for future in stale))
        pool.shutdown();self.assertEqual(len(evaluated),1000);self.assertEqual(work,['visible'])


if __name__=='__main__':unittest.main()
