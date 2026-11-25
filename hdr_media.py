"""Only explicitly PQ/HLG-tagged media is eligible for HDR offload."""
def texture_hdr(texture):
    params=texture.get_color_state().create_cicp_params()
    return params is not None and params.get_transfer_function() in (16,18)


def video_transfer(caps):
    if caps is None:return None
    import gi
    gi.require_version('GstVideo','1.0')
    from gi.repository import GstVideo
    value=caps.get_structure(0).get_string('colorimetry') if caps.get_size() else None
    if not value:return None
    color=GstVideo.VideoColorimetry()
    if not color.from_string(value):return None
    if color.transfer==GstVideo.VideoTransferFunction.SMPTE2084:return 16
    if color.transfer==GstVideo.VideoTransferFunction.ARIB_STD_B67:return 18
    return None


def video_hdr(caps):return video_transfer(caps) is not None


def aligned_rect(x,y,width,height,scale,origin=(0.,0.)):
    """Wayland offload needs both logical and device pixel integral bounds."""
    from fractions import Fraction
    step=Fraction(scale).limit_denominator(120).denominator
    from math import ceil,floor
    ox,oy=origin
    left=ceil((x+ox)/step-1e-7)*step;top=ceil((y+oy)/step-1e-7)*step
    right=floor((x+width+ox)/step+1e-7)*step;bottom=floor((y+height+oy)/step+1e-7)*step
    return left-ox,top-oy,max(step,right-left),max(step,bottom-top)


def photo_presentation(texture):
    """Normalize HLG to PQ on the decode worker for PQ-only compositors."""
    params=texture.get_color_state().create_cicp_params()
    if params is None or params.get_transfer_function()!=18:return texture
    from gi.repository import Gdk
    state=Gdk.ColorState.get_rec2100_pq()
    format=Gdk.MemoryFormat.R16G16B16A16_FLOAT
    download=Gdk.TextureDownloader.new(texture);download.set_color_state(state);download.set_format(format)
    data,stride=download.download_bytes()
    builder=Gdk.MemoryTextureBuilder.new()
    builder.set_width(texture.get_width());builder.set_height(texture.get_height())
    builder.set_format(format);builder.set_color_state(state);builder.set_bytes(data);builder.set_stride(stride)
    return builder.build()
