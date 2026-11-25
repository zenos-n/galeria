import unittest
from types import SimpleNamespace
from hdr_media import texture_hdr,aligned_rect,video_transfer


class HdrMediaTests(unittest.TestCase):
    def test_only_explicit_hdr_transfers_enable_photo_offload(self):
        for transfer in (1,8,13,16,18):
            params=SimpleNamespace(get_transfer_function=lambda t=transfer:t)
            texture=SimpleNamespace(get_color_state=lambda p=params:SimpleNamespace(create_cicp_params=lambda:p))
            self.assertEqual(texture_hdr(texture),transfer in (16,18))
        texture=SimpleNamespace(get_color_state=lambda:SimpleNamespace(create_cicp_params=lambda:None))
        self.assertFalse(texture_hdr(texture))

    def test_geometry_fits_and_has_integral_logical_and_device_bounds(self):
        for scale in (1.,1.25,4/3,1.5,5/3,1.75,2.):
            for origin in ((0.,0.),(.5,12.5),(17.,23.)):
                original=(0.,0.,1231.4,811.8)
                x,y,w,h=aligned_rect(*original,scale,origin)
                self.assertGreaterEqual(x,-1e-7);self.assertGreaterEqual(y,-1e-7)
                self.assertLessEqual(x+w,original[2]+1e-7);self.assertLessEqual(y+h,original[3]+1e-7)
                for value in (x+origin[0],y+origin[1],w,h):
                    self.assertAlmostEqual(value,round(value),places=6)
                    self.assertAlmostEqual(value*scale,round(value*scale),places=6)

    def test_only_tagged_hdr_video_caps_select_hdr(self):
        import gi
        gi.require_version('Gst','1.0')
        from gi.repository import Gst
        Gst.init(None)
        for name,expected in [('bt709',None),('sRGB',None),('bt2020-10',None),('bt2100-pq',16),('bt2100-hlg',18)]:
            caps=Gst.Caps.from_string('video/x-raw,format=P010_10LE,width=32,height=32,colorimetry='+name)
            self.assertEqual(video_transfer(caps),expected,name)
        self.assertIsNone(video_transfer(None));self.assertIsNone(video_transfer(Gst.Caps.new_empty()))
