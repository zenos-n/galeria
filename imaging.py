"""Decode on workers, including Immich's WebP/AVIF, independent of GTK loaders."""
from io import BytesIO
from PIL import Image, ImageOps


def decode_image(source,limit=360):
    with Image.open(BytesIO(source) if isinstance(source,bytes) else source) as original:
        image=ImageOps.exif_transpose(original)
        image.thumbnail((limit,limit))
        image=image.convert('RGBA')
        return image.width,image.height,image.tobytes()


def decode_texture(source):
    """Worker-only, sandboxed decode retaining bit depth, CICP and ICC colors."""
    import gi
    gi.require_version('Gly','2');gi.require_version('GlyGtk4','2')
    from gi.repository import Gly,GlyGtk4,Gio,GLib
    loader=(Gly.Loader.new_for_bytes(GLib.Bytes.new(source)) if isinstance(source,bytes)
            else Gly.Loader.new(Gio.File.new_for_path(str(source))))
    return GlyGtk4.frame_get_texture(loader.load().next_frame())


def editor_pixels(texture,limit=2400):
    # The existing Pillow editor is SDR; keep its conversion out of the viewer.
    from gi.repository import Gdk
    downloader=Gdk.TextureDownloader.new(texture)
    downloader.set_format(Gdk.MemoryFormat.R8G8B8A8)
    downloader.set_color_state(Gdk.ColorState.get_srgb())
    data,stride=downloader.download_bytes()
    image=Image.frombytes('RGBA',(texture.get_width(),texture.get_height()),data.get_data(),'raw','RGBA',stride)
    if limit:image.thumbnail((limit,limit))
    return image.width,image.height,image.tobytes()


def image_ratio(path):
    with Image.open(path) as image:
        w,h=image.size
        if image.getexif().get(274) in (5,6,7,8):w,h=h,w
        return w/max(1,h)


def thumbnail_bytes(path):
    try:w,h,data=decode_image(path)
    except (OSError,ValueError):w,h,data=editor_pixels(decode_texture(path),360)
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
