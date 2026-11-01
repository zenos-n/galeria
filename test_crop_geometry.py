import unittest
from crop_geometry import drag_crop

class CropTests(unittest.TestCase):
    def test_handle_changes_bounds(self):
        self.assertEqual(drag_crop((0,0,1,1),'nw',.2,.3),(.2,.3,1,1))
    def test_move_preserves_size_and_stays_inside(self):
        self.assertEqual(drag_crop((.1,.2,.5,.7),'move',2,2),(.6,.5,1,1))
    def test_handles_cannot_cross(self):
        a,b,c,d=drag_crop((0,0,1,1),'nw',3,3)
        self.assertGreaterEqual(c-a,.039)
        self.assertGreaterEqual(d-b,.039)
    def test_aspect_locked_and_bounded(self):
        for handle in ['nw','ne','sw','se']:
            for dx,dy in [(.3,.4),(-.9,-.9),(2,2)]:
                a,b,c,d=drag_crop((.1,.1,.9,.9),handle,dx,dy,ratio=1)
                self.assertTrue(0<=a<c<=1 and 0<=b<d<=1)
                self.assertAlmostEqual(c-a,d-b)
    def test_vertical_corner_drag_resizes_locked_crop(self):
        a,b,c,d=drag_crop((0,0,1,1),'se',0,-.25,ratio=1)
        self.assertAlmostEqual(c-a,.75)
        self.assertAlmostEqual(d-b,.75)

if __name__=='__main__':unittest.main()
