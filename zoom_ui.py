"""Pointer-anchored wheel/pinch zoom and bounded drag panning in the viewer."""
import math
from gi.repository import Gdk,Gtk


class MediaZoom:
    def __init__(self,viewer):
        self.viewer=viewer;self.pointer=None;self.pan_start=None
        layer=viewer.photo_overlay
        motion=Gtk.EventControllerMotion();motion.connect('motion',lambda _,x,y:setattr(self,'pointer',(x,y)));layer.add_controller(motion)
        scroll=Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL,propagation_phase=Gtk.PropagationPhase.CAPTURE)
        scroll.connect('scroll',self.scroll);layer.add_controller(scroll)
        pinch=Gtk.GestureZoom(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        pinch.connect('begin',self.pinch_begin);pinch.connect('scale-changed',self.pinch);layer.add_controller(pinch);self.gesture=pinch
        pan=Gtk.GestureDrag(button=1,propagation_phase=Gtk.PropagationPhase.CAPTURE);pan.connect('drag-begin',self.pan_begin);pan.connect('drag-update',self.pan);layer.add_controller(pan)
        self.reset_button=Gtk.Button(label='100%',tooltip_text='Reset zoom',visible=False,halign=Gtk.Align.CENTER,valign=Gtk.Align.START,margin_top=52,css_classes=['osd','pill'])
        self.reset_button.connect('clicked',lambda _:self.reset());layer.add_overlay(self.reset_button)

    def usable(self):return not self.viewer.editing and not self.viewer.closing and self.viewer.stage.progress>=1

    def controls_at_pointer(self):
        if not self.pointer:return False
        node=self.viewer.photo_overlay.pick(*self.pointer,Gtk.PickFlags.DEFAULT)
        while node and node!=self.viewer.photo_overlay:
            if isinstance(node,(Gtk.Button,Gtk.Range,Gtk.Editable)):return True
            node=node.get_parent()
        return False

    def clamp(self):
        stage=self.viewer.stage;_,_,w,h=stage.destination(stage.get_width(),stage.get_height())
        bx=max(0,(w*stage.zoom-stage.get_width())/2);by=max(0,(h*stage.zoom-(stage.get_height()-stage.top_inset-40))/2)
        stage.pan_x=max(-bx,min(bx,stage.pan_x));stage.pan_y=max(-by,min(by,stage.pan_y));stage.queue_allocate()
        self.reset_button.set_label(f'{round(stage.zoom*100)}%');self.reset_button.set_visible(stage.zoom>1.001)

    def set_zoom(self,value,anchor=None):
        if not self.usable():return
        stage=self.viewer.stage;x,y,w,h=stage.destination(stage.get_width(),stage.get_height());cx,cy=x+w/2,y+h/2
        ax,ay=anchor or self.pointer or (cx,cy);value=max(1,min(8,value));ratio=value/stage.zoom
        stage.pan_x=(ax-cx)*(1-ratio)+stage.pan_x*ratio;stage.pan_y=(ay-cy)*(1-ratio)+stage.pan_y*ratio;stage.zoom=value;self.clamp()

    def scroll(self,_controller,dx,dy):
        if not self.usable() or self.controls_at_pointer():return False
        pixels=_controller is not None and _controller.get_unit()==Gdk.ScrollUnit.SURFACE
        rate=.003 if pixels else .12
        self.set_zoom(self.viewer.stage.zoom*math.exp(-max(-100,min(100,dy))*rate));return True

    def pinch_begin(self,gesture,*_):self.initial=self.viewer.stage.zoom
    def pinch(self,gesture,scale):
        ok,x,y=gesture.get_bounding_box_center();self.set_zoom(getattr(self,'initial',self.viewer.stage.zoom)*scale,(x,y) if ok else None)
    def pan_begin(self,gesture,x,y):
        self.pan_start=None
        if self.usable() and self.viewer.stage.zoom>1 and not self.controls_at_pointer():
            self.pan_start=(self.viewer.stage.pan_x,self.viewer.stage.pan_y);gesture.set_state(Gtk.EventSequenceState.CLAIMED)
    def pan(self,_gesture,dx,dy):
        if self.pan_start:
            self.viewer.stage.pan_x=self.pan_start[0]+dx;self.viewer.stage.pan_y=self.pan_start[1]+dy;self.clamp()
    def reset(self):
        stage=self.viewer.stage;stage.zoom=1;stage.pan_x=stage.pan_y=0;stage.last_rect=stage.destination(stage.get_width(),stage.get_height());self.clamp()
