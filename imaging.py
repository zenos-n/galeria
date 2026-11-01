"""Decode on workers, including Immich's WebP/AVIF, independent of GTK loaders."""
from io import BytesIO
from PIL import Image, ImageOps


def decode_image(source,limit=360):
    with Image.open(BytesIO(source) if isinstance(source,bytes) else source) as original:
        image=ImageOps.exif_transpose(original)
        image.thumbnail((limit,limit))
        image=image.convert('RGBA')
        return image.width,image.height,image.tobytes()


def image_ratio(path):
    with Image.open(path) as image:
        w,h=image.size
        if image.getexif().get(274) in (5,6,7,8):w,h=h,w
        return w/max(1,h)


def thumbnail_bytes(path):
    w,h,data=decode_image(path)
    output=BytesIO()
    Image.frombytes('RGBA',(w,h),data).save(output,format='PNG')
    return output.getvalue()


def duration_label(value):
    try:
        parts=str(value).split(':')
        seconds=int(sum(float(part)*60**i for i,part in enumerate(reversed(parts)))) if len(parts)>1 else int(float(value)/1000)
    except (ValueError,TypeError,OverflowError):return 'Video'
    hours,remainder=divmod(max(0,seconds),3600)
    minutes,seconds=divmod(remainder,60)
    return f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes}:{seconds:02}'
