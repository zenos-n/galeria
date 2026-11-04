"""Photo adjustments and annotation rendering, independent of GTK."""
import math
from PIL import Image,ImageChops,ImageDraw,ImageEnhance,ImageFilter,ImageFont,ImageOps

ADJUSTMENTS=['Brightness','Contrast','White point','Highlights','Shadows','Black point',
             'Saturation','Warmth','Tint','Skin tone','Blue tone','Pop','Sharpen','Denoise','Vignette','HDR effect']
POSITIVE={'Sharpen','Denoise','HDR effect'}


def adjust(image,values):
    alpha=image.getchannel('A') if image.mode=='RGBA' else None
    image=image.convert('RGB')
    def curve(fn):return image.point([round(max(0,min(255,fn(x)))) for x in range(256)]*3)
    def channels(gains):
        return Image.merge('RGB',[band.point([round(max(0,min(255,x*gain))) for x in range(256)]) for band,gain in zip(image.split(),gains)])
    for name in ADJUSTMENTS:
        amount=float(values.get(name,0))/100
        if not math.isfinite(amount):raise ValueError('Adjustment must be finite')
        amount=max(0 if name in POSITIVE else -1,min(1,amount))
        if not amount:continue
        if name=='Brightness':image=ImageEnhance.Brightness(image).enhance(1+amount)
        elif name=='Contrast':image=ImageEnhance.Contrast(image).enhance(1+amount)
        elif name=='White point':image=curve(lambda x:x+amount*80*(x/255)**3)
        elif name=='Highlights':image=curve(lambda x:x+amount*160*(x/255)**3*(1-x/255))
        elif name=='Shadows':image=curve(lambda x:x+amount*160*(1-x/255)**3*(x/255))
        elif name=='Black point':image=curve(lambda x:x-amount*80*(1-x/255)**3)
        elif name=='Saturation':image=ImageEnhance.Color(image).enhance(1+amount)
        elif name=='Warmth':image=channels((1+.25*amount,1,1-.25*amount))
        elif name=='Tint':image=channels((1+.18*amount,1-.18*amount,1+.18*amount))
        elif name in ('Skin tone','Blue tone'):
            hue,saturation,_=image.convert('HSV').split()
            mask=hue.point([255 if ((h<34 or h>244) if name=='Skin tone' else 125<h<190) else 0 for h in range(256)])
            mask=ImageChops.multiply(mask,saturation.point([min(255,max(0,(x-20)*3)) for x in range(256)]))
            changed=channels((1+.12*amount,1+.04*amount,1-.08*amount) if name=='Skin tone' else (1-.1*amount,1,1+.25*amount))
            image=Image.composite(changed,image,mask)
        elif name=='Pop':
            image=image.filter(ImageFilter.UnsharpMask(radius=12,percent=round(amount*140),threshold=3)) if amount>0 else Image.blend(image,image.filter(ImageFilter.GaussianBlur(2)),-amount*.6)
        elif name=='Sharpen':image=image.filter(ImageFilter.UnsharpMask(radius=1.2,percent=round(amount*200),threshold=1))
        elif name=='Denoise':image=Image.blend(image,image.filter(ImageFilter.MedianFilter(3 if amount<.6 else 5)),amount)
        elif name=='Vignette':
            mask=Image.radial_gradient('L').resize(image.size,Image.Resampling.BILINEAR)
            mask=ImageChops.multiply(mask,mask).point([round(x*abs(amount)*.8) for x in range(256)])
            image=Image.composite(Image.new('RGB',image.size,'black' if amount>0 else 'white'),image,mask)
        elif name=='HDR effect':
            changed=ImageEnhance.Color(ImageEnhance.Contrast(image).enhance(.85).filter(ImageFilter.UnsharpMask(radius=15,percent=100,threshold=3))).enhance(1.15)
            image=Image.blend(image,changed,amount)
    image=image.convert('RGBA')
    if alpha is not None:image.putalpha(alpha)
    return image


def text_tile(stroke):
    font=ImageFont.load_default(size=96)
    box=font.getbbox(stroke.get('text') or 'Text')
    tile=Image.new('RGBA',(max(1,box[2]-box[0]+8),max(1,box[3]-box[1]+8)))
    ImageDraw.Draw(tile).text((4-box[0],4-box[1]),stroke.get('text') or 'Text',fill=stroke['color'],font=font)
    return tile


def annotate(image,strokes):
    image=image.convert('RGBA');width,height=image.size
    for stroke in strokes:
        points=[(x*width,y*height) for x,y in stroke['points']]
        if not points:continue
        tool=stroke['tool'];layer=Image.new('RGBA',image.size);draw=ImageDraw.Draw(layer)
        color=stroke['color'];size=max(1,round(stroke['width']*min(width,height)))
        if tool=='Redact':
            a,b=points[0],points[-1];draw.rectangle((min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])),fill='black')
        elif tool=='Text':
            if not stroke.get('text'):continue
            tile=text_tile(stroke);scale=min(width,height)*.045*stroke.get('scale',1)/96
            angle=math.radians(stroke.get('rotation',0));c=math.cos(angle)/scale;s=math.sin(angle)/scale;x,y=points[0]
            matrix=(c,s,tile.width/2-c*x-s*y,-s,c,tile.height/2+s*x-c*y)
            layer=tile.transform(image.size,Image.Transform.AFFINE,matrix,Image.Resampling.BICUBIC)
        else:
            if tool=='Highlight':color=(*Image.new('RGB',(1,1),color).getpixel((0,0)),90)
            if len(points)>1:draw.line(points,fill=color,width=size,joint='curve')
            radius=size/2
            for x,y in points:draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=color)
        image=Image.alpha_composite(image,layer)
    return image


def render(image,values,strokes=(),rotation=0,flipped=False,straighten=0,crop=None,limit=None):
    image=ImageOps.exif_transpose(image).convert('RGBA')
    if limit:image.thumbnail((limit,limit),Image.Resampling.LANCZOS)
    image=adjust(image,values)
    if rotation:image=image.rotate(-rotation,expand=True)
    if flipped:image=ImageOps.mirror(image)
    if straighten:image=image.rotate(-straighten,resample=Image.Resampling.BICUBIC)
    if strokes:image=annotate(image,strokes)
    if crop:
        a,b,c,d=crop;w,h=image.size
        image=image.crop((round(a*w),round(b*h),max(round(a*w)+1,round(c*w)),max(round(b*h)+1,round(d*h))))
    return image
