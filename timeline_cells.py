"""Light timeline cells: native controls exist only around the viewport."""
import math
from gi.repository import Gdk,Graphene,Gtk
from imaging import duration_label


class Picture:
    def __init__(self,cell):self.cell=cell
    def set_paintable(self,value):
        self.cell.media_texture=value
        if self.cell.image:self.cell.image.set_paintable(value)
    def get_paintable(self):return self.cell.media_texture


class Icon:
    def __init__(self,cell):self.cell=cell;self.name='image-x-generic-symbolic';self.visible=True
    def set_visible(self,value):
        self.visible=value
        if self.cell.icon:self.cell.icon.set_visible(value)
    def set_from_icon_name(self,name):
        self.name=name
        if self.cell.icon:self.cell.icon.set_from_icon_name(name)


class Check:
    def __init__(self,owner,index):self.owner=owner;self.cell=owner.tiles[index];self.cell.check=self;self.widget=None;self.visible=False;self.active=False;self.child_visible=False
    @property
    def index(self):return self.cell.index
    def ensure(self):
        if self.widget is None:
            self.widget=Gtk.CheckButton(tooltip_text='Select photo',css_classes=['media-check'],active=self.index in self.owner.selected)
            self.widget.connect('toggled',lambda widget:self.owner.check_toggled(self.index,widget.get_active()))
            self.widget.set_parent(self.owner)
        return self.widget
    def set_visible(self,value):self.visible=value
    def get_visible(self):
        item=self.owner.tiles[self.index].media_item
        return (self.owner.selection_mode or self.index==self.owner.hovered_index) and not (item and item.metadata.get('placeholder'))
    def set_active(self,value):
        self.active=value
        if self.widget:self.widget.set_active(value)
    def set_child_visible(self,value):
        self.child_visible=value
        if not value and self.widget:self.widget.unparent();self.widget=None
    def get_child_visible(self):return self.child_visible
    def measure(self,*args):return self.ensure().measure(*args)
    def allocate(self,*args):return self.ensure().allocate(*args)
    def compute_bounds(self,*args):return self.ensure().compute_bounds(*args)
    def get_first_child(self):return self.ensure().get_first_child()
    def dispose(self):self.set_child_visible(False)


class Cell(Gtk.Widget):
    @property
    def index(self):return self.owner.cell_indices.get(self.media_item.id,self._index) if self.media_item else self._index
    @index.setter
    def index(self,value):self._index=value

    def __init__(self,owner,index,item,ratio):
        super().__init__(css_classes=['photo-tile'])
        self.owner=owner;self.index=index;self.media_item=item;self.photo_ratio=ratio
        self.filename=item.filename if item else f'Photo {index+1}'
        self.media_texture=None;self.button=None;self.image=None;self.icon=None;self.upload_ring=None;self.upload_state=None
        self.photo_picture=Picture(self);self.media_icon=Icon(self)
        self.set_child_visible(False)

    def rebind(self,owner,index,item,ratio):
        previous=self.media_item
        same=previous.id==item.id and previous.metadata.get('updatedAt')==item.metadata.get('updatedAt')
        rebuild=not same or previous.kind!=item.kind or previous.filename!=item.filename or self.upload_state!=item.metadata.get('upload_state')
        key=previous.metadata.get('upload_key')
        texture=self.media_texture if same or key and key==item.metadata.get('upload_key') else None
        if rebuild:self.release();self.media_texture=texture
        self.owner=owner;self.index=index;self.media_item=item;self.photo_ratio=ratio;self.filename=item.filename

    def ensure(self,defer=False):
        if self.button:return
        if defer and not self.owner.can_build_cell():return
        if self.media_texture is None and self.media_item:self.media_texture=self.owner.cached_texture(self.media_item)
        overlay=Gtk.Overlay()
        self.image=Gtk.Picture(paintable=self.media_texture,can_shrink=True,content_fit=Gtk.ContentFit.COVER,can_target=False,css_classes=[f'shade-{self.index%5}'])
        overlay.set_child(self.image)
        self.icon=Gtk.Image(icon_name=self.media_icon.name,pixel_size=23,visible=self.media_icon.visible and self.media_texture is None,
            halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER,css_classes=['placeholder-icon'])
        overlay.add_overlay(self.icon)
        if self.media_item and self.media_item.kind=='VIDEO' and self.owner.show_durations:
            overlay.add_overlay(Gtk.Label(label='▷ '+duration_label(self.media_item.metadata.get('duration')),
                halign=Gtk.Align.END,valign=Gtk.Align.START,css_classes=['video-duration']))
        metadata=self.media_item.metadata if self.media_item else {}
        self.upload_state=metadata.get('upload_state')
        if metadata.get('upload_state') in ('uploading','failed'):
            if metadata['upload_state']=='failed':
                retry=Gtk.Button(icon_name='view-refresh-symbolic',tooltip_text='Retry upload',css_classes=['circular','upload-tile-status'],halign=Gtk.Align.END,valign=Gtk.Align.END,margin_end=8,margin_bottom=8)
                retry.connect('clicked',lambda _:self.owner.retry_upload(metadata['upload_key']));overlay.add_overlay(retry)
            else:
                ring=Gtk.DrawingArea(content_width=34,content_height=34,halign=Gtk.Align.END,valign=Gtk.Align.END,margin_end=8,margin_bottom=8,can_target=False,tooltip_text='Uploading…')
                def draw(widget,cr,width,height):
                    cx,cy=width/2,height/2;cr.set_source_rgba(0,0,0,.65);cr.arc(cx,cy,16,0,math.tau);cr.fill()
                    cr.set_line_width(3);cr.set_source_rgba(1,1,1,.35);cr.arc(cx,cy,11,0,math.tau);cr.stroke()
                    cr.set_source_rgba(.73,.39,.84,1);cr.arc(cx,cy,11,-math.pi/2,-math.pi/2+math.tau*max(.035,metadata.get('upload_progress',0)));cr.stroke()
                ring.set_draw_func(draw);overlay.add_overlay(ring);self.upload_ring=ring
        self.button=Gtk.Button(child=overlay,tooltip_text=self.filename,css_classes=['photo-tile'])
        self.button.connect('clicked',lambda _:self.owner.clicked(self,self.index))
        click=Gtk.GestureClick(button=1);click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect('pressed',lambda gesture,count,x,y:self.owner.modifier_click(gesture,count,x,y,self.index))
        self.button.add_controller(click);self.button.set_parent(self)

    def release(self):
        if self.button:self.button.unparent();self.button=None;self.image=None;self.icon=None;self.upload_ring=None;self.upload_state=None
        self.media_texture=None

    def get_child(self):self.ensure();return self.button.get_child()
    def grab_focus(self):self.ensure();return self.button.grab_focus()
    def do_measure(self,orientation,for_size):
        if self.button:return self.button.measure(orientation,for_size)
        return 0,0,-1,-1
    def do_size_allocate(self,width,height,baseline):
        self.ensure(defer=True)
        if not self.button:return
        self.button.measure(Gtk.Orientation.HORIZONTAL,-1);self.button.measure(Gtk.Orientation.VERTICAL,width)
        self.button.allocate(width,height,baseline,None)
    def do_snapshot(self,snapshot):
        if self.button:self.snapshot_child(self.button,snapshot)
        else:
            texture=self.media_texture or self.owner.cached_texture(self.media_item) or self.owner.placeholder_paintable
            snapshot.append_texture(texture,Graphene.Rect().init(0,0,self.get_width(),self.get_height()))
