"""Normalized on-photo pen, highlighter, redaction and text gestures."""
import math
from gi.repository import Gdk,Gtk

PALETTE={'white':'#ffffff','black':'#000000','red':'#ed333b','blue':'#3584e4','yellow':'#f8e45c'}


class Markup(Gtk.DrawingArea):
    def __init__(self,changed,notice):
        super().__init__(hexpand=True,vexpand=True,visible=False)
        self.strokes=[];self.tool='Pen';self.color=PALETTE['white'];self.text='';self.active=None
        self.changed=changed;self.notice=notice
        self.set_draw_func(self.draw)
        self.set_cursor_from_name('crosshair')
        drag=Gtk.GestureDrag(button=1)
        drag.connect('drag-begin',self.begin);drag.connect('drag-update',self.update);drag.connect('drag-end',self.end)
        self.add_controller(drag)
        click=Gtk.GestureClick(button=1);click.connect('pressed',self.place_text);self.add_controller(click)

    def point(self,x,y):return max(0,min(1,x/max(1,self.get_width()))),max(0,min(1,y/max(1,self.get_height())))

    def begin(self,gesture,x,y):
        if self.tool=='Text':return
        self.start=(x,y)
        self.active={'tool':self.tool,'color':self.color,'width':.03 if self.tool=='Highlight' else .008,'points':[self.point(x,y)]}
        self.strokes.append(self.active);gesture.set_state(Gtk.EventSequenceState.CLAIMED);self.queue_draw()

    def update(self,_gesture,dx,dy):
        if self.active is None:return
        point=self.point(self.start[0]+dx,self.start[1]+dy)
        if self.tool=='Redact':self.active['points']=self.active['points'][:1]+[point]
        elif math.dist(point,self.active['points'][-1])>.001:self.active['points'].append(point)
        self.queue_draw()

    def end(self,gesture,dx,dy):
        if self.active is None:return
        self.update(gesture,dx,dy);self.active=None;self.queue_draw();self.changed()

    def place_text(self,gesture,_count,x,y):
        if self.tool!='Text':return
        if not self.text.strip():self.notice('Enter text, then click the photo.');return
        self.strokes.append({'tool':'Text','color':self.color,'width':.008,'text':self.text.strip(),'points':[self.point(x,y)]})
        gesture.set_state(Gtk.EventSequenceState.CLAIMED);self.queue_draw();self.changed()

    def undo(self):
        if self.strokes:self.strokes.pop();self.active=None;self.queue_draw();self.changed()

    def clear(self):self.strokes.clear();self.active=None;self.queue_draw();self.changed()

    def draw(self,_widget,ctx,width,height):
        ctx.save();ctx.rectangle(0,0,width,height);ctx.clip()
        for stroke in self.strokes:
            points=[(x*width,y*height) for x,y in stroke['points']]
            if not points:continue
            color=Gdk.RGBA();color.parse(stroke['color']);tool=stroke['tool']
            ctx.set_source_rgba(color.red,color.green,color.blue,.35 if tool=='Highlight' else 1)
            ctx.set_line_width(max(1,stroke['width']*min(width,height)))
            ctx.set_line_cap(1);ctx.set_line_join(1)
            if tool=='Redact':
                a,b=points[0],points[-1];ctx.set_source_rgb(0,0,0)
                ctx.rectangle(min(a[0],b[0]),min(a[1],b[1]),abs(a[0]-b[0]),abs(a[1]-b[1]));ctx.fill()
            elif tool=='Text':
                ctx.select_font_face('Sans');ctx.set_font_size(max(8,min(width,height)*.045))
                extents=ctx.text_extents(stroke['text']);x,y=points[0]
                ctx.move_to(x-extents.width/2-extents.x_bearing,y-extents.height/2-extents.y_bearing);ctx.show_text(stroke['text'])
            elif len(points)==1:
                x,y=points[0];ctx.arc(x,y,ctx.get_line_width()/2,0,math.tau);ctx.fill()
            else:
                ctx.move_to(*points[0])
                for point in points[1:]:ctx.line_to(*point)
                ctx.stroke()
        ctx.restore()
