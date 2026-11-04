"""Shared scalable glyph outlines for live markup and final-resolution copies."""
import math
import cairo,gi
gi.require_version('Pango','1.0')
gi.require_version('PangoCairo','1.0')
from gi.repository import Pango,PangoCairo


def snap_rotation(angle):
    nearest=round(angle/90)*90
    return nearest if abs(angle-nearest)<=6 else angle


def outline(text):
    ctx=cairo.Context(cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA,None))
    layout=PangoCairo.create_layout(ctx);font=Pango.FontDescription('DejaVu Sans')
    font.set_absolute_size(96*Pango.SCALE);layout.set_font_description(font);layout.set_text(text or 'Text',-1)
    ink,_=layout.get_pixel_extents();ctx.move_to(4-ink.x,4-ink.y)
    PangoCairo.layout_path(ctx,layout)
    return ctx.copy_path(),max(1,ink.width+8),max(1,ink.height+8)


def paint(ctx,shape,x,y,scale,rotation):
    path,width,height=shape
    ctx.save();ctx.translate(x,y);ctx.rotate(math.radians(rotation));ctx.scale(scale,scale)
    ctx.translate(-width/2,-height/2);ctx.append_path(path);ctx.fill();ctx.restore()
