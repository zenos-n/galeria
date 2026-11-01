import unittest

from layout import justified_rows


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


if __name__ == "__main__":
    unittest.main()
