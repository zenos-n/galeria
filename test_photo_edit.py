import unittest
from PIL import Image,ImageChops
from photo_edit import ADJUSTMENTS,adjust,render,annotate


class PhotoEditTests(unittest.TestCase):
    def setUp(self):
        self.image=Image.new('RGBA',(96,64))
        self.image.putdata([((x*3)%256,(y*5)%256,(x*17+y*13)%256,150+x%100) for y in range(64) for x in range(96)])

    def test_neutral_is_exact_and_tools_have_distinct_effects(self):
        before=self.image.tobytes();outputs=[]
        self.assertEqual(adjust(self.image,{}).tobytes(),before)
        for name in ADJUSTMENTS:
            with self.subTest(name=name):
                output=adjust(self.image,{name:70})
                self.assertNotEqual(output.tobytes(),before)
                self.assertEqual(output.getchannel('A').tobytes(),self.image.getchannel('A').tobytes())
                outputs.append(output.tobytes())
        self.assertEqual(len(set(outputs)),len(ADJUSTMENTS))
        self.assertEqual(self.image.tobytes(),before)

    def test_selective_color_and_combined_values(self):
        image=Image.new('RGB',(2,1));image.putdata([(140,90,60),(30,90,160)])
        skin=adjust(image,{'Skin tone':80});blue=adjust(image,{'Blue tone':80})
        self.assertEqual(skin.getpixel((1,0))[:3],image.getpixel((1,0)))
        self.assertEqual(blue.getpixel((0,0))[:3],image.getpixel((0,0)))
        both=adjust(self.image,{'Brightness':30,'Contrast':50})
        self.assertNotEqual(both.tobytes(),adjust(self.image,{'Brightness':30}).tobytes())
        self.assertNotEqual(both.tobytes(),adjust(self.image,{'Contrast':50}).tobytes())

    def test_markup_pixels_and_crop_rotation_preserve_source(self):
        image=Image.new('RGBA',(200,100),'white');before=image.tobytes()
        strokes=[{'tool':'Pen','color':'red','width':.04,'points':[(.1,.2),(.9,.2)]},
                 {'tool':'Redact','color':'yellow','width':.01,'points':[(.3,.4),(.6,.8)]}]
        output=annotate(image,strokes)
        self.assertEqual(output.getpixel((100,20)),(255,0,0,255))
        self.assertEqual(output.getpixel((80,60)),(0,0,0,255))
        self.assertEqual(image.tobytes(),before)
        highlight=annotate(image,[{'tool':'Highlight','color':'blue','width':.1,'points':[(.1,.2),(.9,.2)]}])
        self.assertGreater(highlight.getpixel((100,20))[0],0)
        self.assertLess(highlight.getpixel((100,20))[0],255)
        text=annotate(image,[{'tool':'Text','color':'black','width':.01,'text':'Galeria','points':[(.5,.5)]}])
        self.assertIsNotNone(ImageChops.difference(text,image).convert('RGB').getbbox())
        cropped=render(image,{},rotation=90,crop=(.25,.25,.75,.75))
        self.assertEqual(cropped.size,(50,100))


if __name__=='__main__':unittest.main()
