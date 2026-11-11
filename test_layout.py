import unittest

from layout import RowLayout,justified_rows,prepare_timeline


class LayoutTest(unittest.TestCase):
    def test_worker_plan_preserves_dates_filtering_and_geometry(self):
        from datetime import datetime,timedelta
        from types import SimpleNamespace
        items=[SimpleNamespace(id=str(i),filename=('Photo' if i%2 else 'Clip')+str(i),
                               created=datetime(2026,2,5)-timedelta(days=i),ratio=.5+i%5*.4)
               for i in range(100)]
        buckets=[{'timeBucket':'2026-02-01','count':5},{'timeBucket':'2026-03-01','count':7}]
        for mode,month,year in [('all',None,None),('months','2026-01',None),('years',None,'2025')]:
            for query in ('','pHoTo'):
                plan=prepare_timeline([*reversed(items),items[0]],buckets,900,removed={'2'},
                                      mode=mode,expanded_month=month,expanded_year=year,query=query)
                self.assertEqual([item.id for item in plan['items']],[item.id for item in items if item.id!='2'])
                self.assertEqual(plan['months'][0],('2026-03','March 2026','2026',0,0))
                self.assertEqual(plan['bucket_counts'],{'2026-02':5,'2026-03':7})
                for key,title,year_key,a,b in plan['months'][1:]:
                    self.assertTrue(all(plan['asset_months'][item.id]==key for item in plan['items'][a:b]))
                    self.assertEqual(title,plan['items'][a].created.strftime('%B %Y'))
                for (_,width,target,_),(ids,rows) in plan['rows'].items():
                    self.assertEqual(width,900 if mode=='all' else 868)
                    values=[plan['items'][i] for i in ids]
                    self.assertTrue(all(query.casefold() in item.filename.casefold() for item in values))
                    self.assertEqual(list(rows.visible(-1,rows.height+1)),justified_rows([item.ratio for item in values],width,target))

    def test_rows_preserve_proportions_and_stay_inside_viewport(self):
        ratios = [1.78, .45, 1, .67, 1.5, .55, 2, 1, .8, 1.3]
        for width in (200, 360, 700, 1040, 1600):
            with self.subTest(width=width):
                positions = justified_rows(ratios, width)
                self.assertEqual(len(positions), len(ratios))
                previous = None
                for index, x, y, w, h in positions:
                    self.assertGreater(w, 0)
                    self.assertGreater(h, 0)
                    self.assertLessEqual(x + w, width)
                    self.assertAlmostEqual(w / h, ratios[index], delta=.035)
                    if previous:
                        px, py, pw, ph = previous
                        self.assertTrue(y >= py + ph or (y == py and x >= px + pw))
                    previous = x, y, w, h

    def test_empty_and_partial_rows(self):
        self.assertEqual(justified_rows([], 800), [])
        self.assertEqual(justified_rows([1], 0), [])
        self.assertEqual(justified_rows([1], 800)[0][3:], (154, 154))

    def test_row_index_matches_existing_geometry_at_all_scroll_positions(self):
        import random
        randomizer=random.Random(17)
        ratios=[randomizer.uniform(.01,4) for _ in range(1500)]
        for width in (200,361,701,1040,1601):
            for target in (96,154,240):
                old=justified_rows(ratios,width,target);rows=RowLayout(ratios,width,target)
                self.assertEqual(rows.height,max(y+h for _,_,y,_,h in old))
                self.assertEqual(list(rows.visible(-100,rows.height+100)),old)
                for top in range(0,rows.height,701):
                    expected=[rect for rect in old if rect[2]<=top+700 and rect[2]+rect[4]>=top]
                    self.assertEqual(list(rows.visible(top,top+700)),expected)
        self.assertEqual(list(RowLayout([],800).visible(0,700)),[])
        self.assertEqual(RowLayout([1],0).height,0)


if __name__ == "__main__":
    unittest.main()
