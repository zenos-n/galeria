"""On-photo strokes and editable text with move, rotate and scale handles."""
import math
from gi.repository import Gdk,Gtk
from text_vector import outline,paint,snap_rotation

PALETTE={'white':'#ffffff','black':'#000000','red':'#ed333b','blue':'#3584e4','yellow':'#f8e45c'}


class Markup(Gtk.Overlay):
    def __init__(self,changed,notice):
        super().__init__(hexpand=True,vexpand=True,visible=False)
        self.strokes=[];self.tool='Pen';self.color=PALETTE['white'];self.active=None;self.selected=None;self.moved=False
        self.changed=changed;self.notice=notice;self.cache={};self.select_color=lambda color:None
        self.canvas=Gtk.DrawingArea(hexpand=True,vexpand=True);self.canvas.set_draw_func(self.draw);self.set_child(self.canvas)
        self.set_cursor_from_name('crosshair')
        self.entry=Gtk.Entry(placeholder_text='Text',max_length=256,width_chars=16,halign=Gtk.Align.START,valign=Gtk.Align.START,visible=False)
        self.entry.connect('changed',self.typing);self.entry.connect('activate',lambda *_:self.finish_text());self.add_overlay(self.entry)
        focus=Gtk.EventControllerFocus();focus.connect('leave',lambda *_:self.finish_text());self.entry.add_controller(focus)
        drag=Gtk.GestureDrag(button=1);drag.connect('drag-begin',self.begin);drag.connect('drag-update',self.update);drag.connect('drag-end',self.end);self.canvas.add_controller(drag)
        click=Gtk.GestureClick(button=1);click.connect('released',self.place_text);self.canvas.add_controller(click);click.group(drag)

    def point(self,x,y):return max(0,min(1,x/max(1,self.get_width()))),max(0,min(1,y/max(1,self.get_height())))
    def redraw(self):self.canvas.queue_draw()

    def geometry(self,stroke):
        key=stroke.get('text','')
        if key not in self.cache:
            if len(self.cache)>=16:self.cache.clear()
            self.cache[key]=outline(key)
        shape=self.cache[key];_,tw,th=shape
        factor=min(self.get_width(),self.get_height())*.045*stroke.get('scale',1)/96
        return shape,tw*factor,th*factor,factor

    def local(self,stroke,x,y):
        cx,cy=stroke['points'][0];dx=x-cx*self.get_width();dy=y-cy*self.get_height();a=math.radians(stroke.get('rotation',0))
        return dx*math.cos(a)+dy*math.sin(a),-dx*math.sin(a)+dy*math.cos(a)

    def hit_text(self,x,y):
        for index in range(len(self.strokes)-1,-1,-1):
            stroke=self.strokes[index]
            if stroke['tool']!='Text':continue
            _,w,h,_=self.geometry(stroke);px,py=self.local(stroke,x,y)
            if index==self.selected:
                if math.hypot(px,py+h/2+24)<12:return index,'rotate'
                if math.hypot(px-w/2,py-h/2)<14:return index,'scale'
            if abs(px)<w/2+8 and abs(py)<h/2+8:return index,'move'
        return None,None

    def begin(self,gesture,x,y):
        self.moved=False;self.start=(x,y)
        if self.tool=='Text':
            self.finish_text();index,mode=self.hit_text(x,y);self.selected=index
            if index is None:self.active=None;return
            stroke=self.strokes[index];self.color=stroke['color'];self.select_color(self.color);self.active=(stroke,mode,stroke['points'][0],stroke.get('scale',1),stroke.get('rotation',0));self.redraw();return
        self.finish_text();self.selected=None
        self.active={'tool':self.tool,'color':self.color,'width':.03 if self.tool=='Highlight' else .008,'points':[self.point(x,y)]}
        self.strokes.append(self.active);gesture.set_state(Gtk.EventSequenceState.CLAIMED);self.redraw()

    def update(self,gesture,dx,dy):
        if self.active is None:return
        self.moved=self.moved or math.hypot(dx,dy)>3
        if isinstance(self.active,tuple):
            stroke,mode,center,scale,rotation=self.active;cx,cy=center[0]*self.get_width(),center[1]*self.get_height()
            if mode=='move':stroke['points']=[self.point(cx+dx,cy+dy)]
            elif mode=='scale':
                before=max(1,math.hypot(self.start[0]-cx,self.start[1]-cy));stroke['scale']=max(.2,min(8,scale*math.hypot(self.start[0]+dx-cx,self.start[1]+dy-cy)/before))
            else:stroke['rotation']=snap_rotation(rotation+math.degrees(math.atan2(self.start[1]+dy-cy,self.start[0]+dx-cx)-math.atan2(self.start[1]-cy,self.start[0]-cx)))
            if self.moved:gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        else:
            point=self.point(self.start[0]+dx,self.start[1]+dy)
            if self.active['tool']=='Redact':self.active['points']=self.active['points'][:1]+[point]
            elif math.dist(point,self.active['points'][-1])>.001:self.active['points'].append(point)
        self.redraw()

    def end(self,gesture,dx,dy):
        if self.active is None:return
        self.update(gesture,dx,dy);self.active=None;self.redraw();self.changed()

    def place_text(self,gesture,count,x,y):
        if self.tool!='Text' or self.moved:return
        self.finish_text();index,_=self.hit_text(x,y)
        if index is None:
            self.strokes.append({'tool':'Text','color':self.color,'text':'','scale':1,'rotation':0,'width':.008,'points':[self.point(x,y)]});index=len(self.strokes)-1;edit=True
        else:edit=count==2
        self.selected=index;self.color=self.strokes[index]['color'];self.select_color(self.color);self.redraw();self.notice('Drag to move · corner to scale · top handle to rotate. Double-click to edit.')
        if edit:
            stroke=self.strokes[index];self.entry.set_text(stroke['text']);cx,cy=stroke['points'][0]
            self.entry.set_margin_start(max(0,min(self.get_width()-180,round(cx*self.get_width()-90))))
            self.entry.set_margin_top(max(0,min(self.get_height()-36,round(cy*self.get_height()-18))))
            self.entry.set_visible(True);self.entry.grab_focus()

    def typing(self,entry):
        if self.selected is not None and self.selected<len(self.strokes):self.strokes[self.selected]['text']=entry.get_text();self.redraw()

    def finish_text(self):
        if not self.entry.get_visible():return
        self.entry.set_visible(False)
        if self.selected is not None and self.selected<len(self.strokes) and not self.strokes[self.selected].get('text','').strip():self.strokes.pop(self.selected);self.selected=None
        self.redraw();self.changed()

    def set_color(self,color):
        self.color=color
        if self.tool=='Text' and self.selected is not None:self.strokes[self.selected]['color']=color;self.redraw();self.changed()

    def clear(self):self.entry.set_visible(False);self.strokes.clear();self.cache.clear();self.active=None;self.selected=None;self.redraw();self.changed()

    def draw(self,_widget,ctx,width,height):
        ctx.save();ctx.rectangle(0,0,width,height);ctx.clip()
        for index,stroke in enumerate(self.strokes):
            points=[(x*width,y*height) for x,y in stroke['points']]
            if not points:continue
            color=Gdk.RGBA();color.parse(stroke['color']);tool=stroke['tool']
            ctx.set_source_rgba(color.red,color.green,color.blue,.35 if tool=='Highlight' else 1)
            ctx.set_line_width(max(1,stroke['width']*min(width,height)));ctx.set_line_cap(1);ctx.set_line_join(1)
            if tool=='Redact':
                a,b=points[0],points[-1];ctx.set_source_rgb(0,0,0);ctx.rectangle(min(a[0],b[0]),min(a[1],b[1]),abs(a[0]-b[0]),abs(a[1]-b[1]));ctx.fill()
            elif tool=='Text':
                if self.entry.get_visible() and self.selected==index:continue
                shape,w,h,factor=self.geometry(stroke)
                paint(ctx,shape,*points[0],factor,stroke.get('rotation',0))
                ctx.save();ctx.translate(*points[0]);ctx.rotate(math.radians(stroke.get('rotation',0)))
                if self.tool=='Text' and index==self.selected:
                    ctx.set_source_rgba(.8,.6,1,1);ctx.set_line_width(1.5);ctx.rectangle(-w/2,-h/2,w,h);ctx.stroke();ctx.move_to(0,-h/2);ctx.line_to(0,-h/2-24);ctx.stroke()
                    for x,y in ((w/2,h/2),(0,-h/2-24)):ctx.arc(x,y,6,0,math.tau);ctx.fill()
                ctx.restore()
            elif len(points)==1:
                x,y=points[0];ctx.arc(x,y,ctx.get_line_width()/2,0,math.tau);ctx.fill()
            else:
                ctx.move_to(*points[0])
                for point in points[1:]:ctx.line_to(*point)
                ctx.stroke()
        ctx.restore()
