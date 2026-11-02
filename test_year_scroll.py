import unittest
from year_scroll import YearScale


class YearScrollTests(unittest.TestCase):
    def test_years_get_equal_track_space_despite_different_item_counts(self):
        scale=YearScale({'2026-12':(0,90000),'2026-01':(90000,100000),
                         '2018-12':(100000,100500),'2018-01':(100500,101000)},101000)
        self.assertEqual(scale.scroll(.5),100000)
        self.assertEqual(scale.scroll(.75),100500)
        self.assertEqual(scale.scroll(1),101000)
        for fraction in (0,.1,.4,.5,.75,.99,1):
            self.assertAlmostEqual(scale.fraction(scale.scroll(fraction)),fraction)

    def test_bounds_and_small_last_years(self):
        scale=YearScale({'2026-01':(0,1000),'2018-01':(1000,1100)},900)
        self.assertEqual(scale.scroll(-1),0);self.assertEqual(scale.scroll(2),900)
        self.assertEqual(scale.fraction(900),1)
        self.assertEqual(YearScale({},0).scroll(.5),0)
        self.assertEqual(YearScale({},0).fraction(100),0)
