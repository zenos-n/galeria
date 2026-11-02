"""Two-handle trim range backed by the editor's accessible numeric controls."""
from gi.repository import Gdk,Gtk


class TrimRange(Gtk.DrawingArea):
    def __init__(self,start,end):
        super().__init__(content_height=32,hexpand=True,width_request=420,focusable=True,tooltip_text='Drag either handle to trim; Tab switches handles, arrow keys adjust')
        self.start=start;self.end=end;self.duration=1.;self.active=0;self.origin=0
        self.set_draw_func(self.draw)
        self.update_property([Gtk.AccessibleProperty.LABEL],['Video trim range; start and end handles'])
        for control in (start,end):control.connect('value-changed',lambda *_:self.queue_draw())
        drag=Gtk.GestureDrag(button=1);drag.connect('drag-begin',self.begin);drag.connect('drag-update',lambda _,dx,dy:self.adjust(self.origin+dx));self.add_controller(drag)
        keys=Gtk.EventControllerKey();keys.connect('key-pressed',self.key);self.add_controller(keys)
    def set_duration(self,duration):self.duration=max(.01,duration);self.queue_draw()
    def points(self):
        span=max(1,self.get_width()-20)
        return [10+span*control.get_value()/self.duration for control in (self.start,self.end)]
    def begin(self,_gesture,x,_y):
        self.grab_focus();self.origin=x;points=self.points();self.active=0 if abs(x-points[0])<abs(x-points[1]) else 1;self.adjust(x)
    def adjust(self,x):
        value=max(0,min(self.duration,(x-10)/max(1,self.get_width()-20)*self.duration))
        value=min(value,max(0,self.end.get_value()-.1)) if self.active==0 else max(value,min(self.duration,self.start.get_value()+.1))
        (self.start if self.active==0 else self.end).set_value(value)
    def key(self,_controller,key,_code,state):
        if key==Gdk.KEY_Tab:
            backwards=bool(state & Gdk.ModifierType.SHIFT_MASK)
            if self.active==(0 if backwards else 1):return False
            self.active=0 if backwards else 1;self.queue_draw();return True
        if key in (Gdk.KEY_Left,Gdk.KEY_Right,Gdk.KEY_Home,Gdk.KEY_End):
            control=self.start if self.active==0 else self.end
            value=0 if key==Gdk.KEY_Home else self.duration if key==Gdk.KEY_End else control.get_value()+(-.1 if key==Gdk.KEY_Left else .1)
            self.adjust(10+max(1,self.get_width()-20)*value/self.duration);return True
        return False
    def draw(self,widget,context,width,height):
        a,b=self.points();y=height/2
        color=self.get_color();context.set_line_cap(1);context.set_line_width(4)
        context.set_source_rgba(color.red,color.green,color.blue,.25);context.move_to(10,y);context.line_to(width-10,y);context.stroke()
        found,accent=self.get_style_context().lookup_color('accent_bg_color')
        context.set_source_rgba(accent.red,accent.green,accent.blue,1) if found else context.set_source_rgb(.65,.3,.75)
        context.move_to(a,y);context.line_to(b,y);context.stroke()
        for index,x in enumerate((a,b)):
            context.arc(x,y,9,0,6.283185);context.set_source_rgb(1,1,1);context.fill()
            if self.has_focus() and index==self.active:
                context.arc(x,y,12,0,6.283185);context.set_source_rgba(color.red,color.green,color.blue,.5);context.set_line_width(1);context.stroke()
