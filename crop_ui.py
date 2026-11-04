"""Interactive crop rectangle for the data-free editor."""
from gi.repository import Gtk
from crop_geometry import drag_crop

class CropOverlay(Gtk.DrawingArea):
    def __init__(self):
        super().__init__(hexpand=True,vexpand=True)
        self.bounds=(0.,0.,1.,1.)
        self.aspect=None
        self.start=None
        self.handle=None;self.changed=lambda:None
        self.set_draw_func(self.draw)
        drag=Gtk.GestureDrag(button=1)
        drag.connect('drag-begin',self.begin)
        drag.connect('drag-update',self.update)
        drag.connect('drag-end',lambda *_:self.changed())
        self.add_controller(drag)
        motion=Gtk.EventControllerMotion()
        motion.connect('motion',self.motion)
        self.add_controller(motion)

    def reset(self):
        self.bounds=(0.,0.,1.,1.)
        self.queue_draw()

    def set_aspect(self,aspect):
        self.aspect=aspect
        if not aspect or not self.get_height():
            return
        ratio=aspect/(self.get_width()/self.get_height())
        w,h=(ratio,1) if ratio<1 else (1,1/ratio)
        self.bounds=((1-w)/2,(1-h)/2,(1+w)/2,(1+h)/2)
        self.queue_draw()

    def hit(self,x,y):
        width,height=self.get_width(),self.get_height()
        a,b,c,d=self.bounds
        for name,px,py in [('nw',a,b),('ne',c,b),('se',c,d),('sw',a,d)]:
            if abs(x-px*width)<=18 and abs(y-py*height)<=18:
                return name
        return 'move' if a*width<=x<=c*width and b*height<=y<=d*height else None

    def begin(self,gesture,x,y):
        self.handle=self.hit(x,y)
        self.start=self.bounds
        if self.handle:
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def update(self,_gesture,dx,dy):
        if not self.start or not self.handle:
            return
        width,height=max(1,self.get_width()),max(1,self.get_height())
        ratio=self.aspect/(width/height) if self.aspect else None
        self.bounds=drag_crop(self.start,self.handle,dx/width,dy/height,
                              min(24/width,.2),min(24/height,.2),ratio)
        self.queue_draw()

    def motion(self,_controller,x,y):
        handle=self.hit(x,y)
        self.set_cursor_from_name('move' if handle=='move' else 'nwse-resize' if handle in ('nw','se') else 'nesw-resize' if handle else 'default')

    def draw(self,_widget,ctx,width,height):
        a,b,c,d=self.bounds
        x0,y0,x1,y1=a*width,b*height,c*width,d*height
        ctx.set_source_rgba(0,0,0,.5)
        for x,y,w,h in [(0,0,width,y0),(0,y1,width,height-y1),(0,y0,x0,y1-y0),(x1,y0,width-x1,y1-y0)]:
            ctx.rectangle(x,y,w,h);ctx.fill()
        ctx.set_source_rgba(1,1,1,.85);ctx.set_line_width(1)
        ctx.rectangle(x0+.5,y0+.5,max(0,x1-x0-1),max(0,y1-y0-1));ctx.stroke()
        ctx.set_source_rgba(1,1,1,.35)
        for fraction in (1/3,2/3):
            x=x0+(x1-x0)*fraction;y=y0+(y1-y0)*fraction
            ctx.move_to(x,y0);ctx.line_to(x,y1);ctx.move_to(x0,y);ctx.line_to(x1,y)
        ctx.stroke()
        ctx.set_source_rgba(1,1,1,1);ctx.set_line_width(3)
        size=min(18,(x1-x0)/5,(y1-y0)/5)
        for x,y,sx,sy in [(x0+1.5,y0+1.5,1,1),(x1-1.5,y0+1.5,-1,1),(x1-1.5,y1-1.5,-1,-1),(x0+1.5,y1-1.5,1,-1)]:
            ctx.move_to(x+sx*size,y);ctx.line_to(x,y);ctx.line_to(x,y+sy*size)
        ctx.stroke()
