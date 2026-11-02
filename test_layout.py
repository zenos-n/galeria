import unittest

from layout import RowLayout,justified_rows


class LayoutTest(unittest.TestCase):
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
