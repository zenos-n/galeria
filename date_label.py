"""One date glyph run shared by the scrolling heading and toolbar."""
import time
from gi.repository import Graphene,Gtk


class DateLabel(Gtk.Widget):
    def __init__(self,window):
        super().__init__(can_target=False)
        self.window=window;self.owner=None;self.draws=[];self.tick=0
        self.sample=None;self.fast_key=None;self.key=None;self.header_state=None;self.motion=None
        self.shared=None;self.pinned=False;self.direction=1

    def release(self):
        if self.owner:
            self.owner.floating_heading=None;self.owner.queue_draw();self.owner=None

    def clear(self):
        self.release();self.draws=[];self.shared=None;self.pinned=False
        self.sample=None;self.fast_key=None;self.key=None;self.header_state=None;self.motion=None
        if self.tick:self.remove_tick_callback(self.tick);self.tick=0
        self.queue_draw()

    def origin(self,widget):
        ok,point=widget.compute_point(self,Graphene.Point().init(0,0))
        return (point.x,point.y) if ok else None

    def update(self,sample=True):
        w=self.window;m=w.mosaic
        if w.data_stopped or w.current_page!='library' or w.searching or m.selection_mode or m.tick or w.stack.get_visible_child_name()!='library':
            self.clear();return
        if m.mode!='all':
            self.clear();cards=m.year_cards if m.mode=='years' else m.month_cards;top,height=m.visible_range()
            key=next((key for key,card in cards.items() if (r:=m.rendered.get(card)) and r[1]+r[3]>top and r[1]<top+height),None)
            w.period.set_label(key[:4] if key else '');w.period.set_opacity(1);return
        w.period.set_opacity(0)
        origin=self.origin(m);viewport=self.origin(w.scroller)
        if not origin or not viewport:return
        top,_=m.visible_range();origin=(origin[0],viewport[1]-top);now=time.monotonic();rows=[]
        for month,heading in zip(m.months,m.headings):
            if m.header_first and heading==m.headings[0]:
                rows.append((month[0],heading,origin[0]+2,float('-inf'),viewport[1]+8));continue
            rect=m.rendered.get(heading)
            if rect:
                dx,dy=heading.get_layout_offsets()
                rows.append((month[0],heading,origin[0]+rect[0]+dx,origin[1]+rect[1]+dy,viewport[1]+8+dy))
        if not rows:self.clear();return
        row=next((row for row in reversed(rows) if row[3]<=row[4]+.5),rows[0])
        key,heading,sx,sy,start=row;title=heading.get_label()
        w.period.set_label(title)
        target=self.origin(w.period)
        if not target:return
        dx,dy=w.period.get_layout_offsets();hx,hy=target[0]+dx,target[1]+dy
        newest=m.header_first and heading==m.headings[0]
        if newest:sy=hy
        if sample and (not self.sample or top!=self.sample[0]):
            if self.sample and self.sample[2] is m:
                movement=top-self.sample[0];self.direction=1 if movement>0 else -1
                delta=abs(movement);elapsed=max(1/60,now-self.sample[1])
                if delta>max(24,start-hy) or delta>5 and delta/elapsed>1600:self.fast_key=key
            self.sample=(top,now,m)
        if self.fast_key and self.fast_key!=key:self.fast_key=None
        if self.fast_key==key and (sy>=start or sy<=hy):
            # Keep the skipped-source policy for this update; endpoints can resume shared motion next time.
            fast=True;self.fast_key=None
        else:fast=self.fast_key==key or self.motion is not None
        self.release();self.draws=[];self.shared=None
        pinned=newest or (sy<viewport[1] if fast else sy<=hy)
        shared=not fast and sy<=start
        current=(key,heading.get_layout(),hx,hy) if pinned else None
        previous=self.header_state
        if fast and (key!=self.key or bool(current)!=bool(previous)):
            self.motion=(now,previous,current,self.direction)
        elif not fast:self.motion=None
        self.key=key;self.header_state=current;self.pinned=pinned
        if shared:
            self.owner=m;m.floating_heading=heading;m.queue_draw()
            progress=max(0,min(1,(start-sy)/max(1,start-hy)))
            x=hx;y=max(hy,sy);opacity=.65+.35*progress
            self.shared=(heading,x,y,progress)
            self.draws.append((heading.get_layout(),x,y,opacity,None))
        elif fast and current:
            self.owner=m;m.floating_heading=heading;m.queue_draw()
        if fast:
            clip_origin=self.origin(w.header)
            clip=(*clip_origin,w.header.get_width(),w.header.get_height()) if clip_origin else None
            if self.motion:
                begun,old,new,direction=self.motion;t=min(1,(now-begun)/.16) if Gtk.Settings.get_default().get_property('gtk-enable-animations') else 1;p=1-(1-t)**3
                if old:self.draws.append((old[1],hx,hy-direction*12*p,1-p,clip))
                if new:self.draws.append((new[1],hx,hy+direction*12*(1-p),p,clip))
                if t>=1:self.motion=None
            elif current:self.draws.append((current[1],hx,hy,1,clip))
        if self.motion and not self.tick:self.tick=self.add_tick_callback(self.frame)
        self.queue_draw()

    def frame(self,*_):
        self.update(False)
        if self.motion:return True
        self.tick=0;return False

    def do_snapshot(self,snapshot):
        color=self.window.period.get_color()
        for layout,x,y,opacity,clip in self.draws:
            if clip:snapshot.push_clip(Graphene.Rect().init(*clip))
            snapshot.save();snapshot.push_opacity(opacity);snapshot.translate(Graphene.Point().init(x,y))
            snapshot.append_layout(layout,color);snapshot.pop();snapshot.restore()
            if clip:snapshot.pop()
