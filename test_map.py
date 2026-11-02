import unittest
from map_geometry import clusters,fit,valid_points


class MapTests(unittest.TestCase):
    def test_invalid_coordinates_are_rejected(self):
        self.assertEqual(valid_points([{'id':'a','lat':20,'lon':10},{'id':'bad','lat':95,'lon':0},{'id':'nan','lat':'nan','lon':0}]),[('a',20.,10.)])

    def test_clusters_split_when_zooming_and_exclude_offscreen(self):
        points=[('a',20,10),('b',20,10.01),('c',-70,-100)]
        wide=clusters(points,20,10,2,800,600)
        self.assertTrue(any(set(group['ids'])=={'a','b'} for group in wide))
        close=clusters(points,20,10,18,800,600)
        self.assertEqual([g['ids'] for g in close],[['a']])

    def test_fit_handles_dateline_and_dense_libraries_stay_bounded(self):
        latitude,longitude,zoom=fit([('a',20,179),('b',21,-179)],1000,700)
        self.assertLess(abs(abs(longitude)-180),1);self.assertGreater(zoom,5)
        self.assertGreater(fit([('a',20,10),('b',20,10)],1000,700)[2],10)
        points=[(str(i),-70+(i%140),-180+(i%360)) for i in range(8000)]
        grouped=clusters(points,0,0,2,1200,800)
        self.assertLess(len(grouped),400)
        self.assertLessEqual(sum(len(group['ids']) for group in grouped),8000)


if __name__=='__main__':unittest.main()
