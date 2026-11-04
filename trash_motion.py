"""Visible media snapshots converge on the invoked action icon."""
from gi.repository import GLib,Graphene,Gtk


class ActionMotion(Gtk.Widget):
    def __init__(self,window,sources,target,done,viewer=None):
        super().__init__(hexpand=True,vexpand=True,can_target=False)
        self.frames=[];self.progress=0;self.window=window;self.viewer=viewer
        for source in sources:
            if not source or not source.get_mapped():continue
            ok,bounds=source.compute_bounds(window.root_overlay)
            if ok and bounds.get_width()>0 and bounds.get_height()>0:
                self.frames.append((Gtk.WidgetPaintable.new(source).get_current_image(),
                    (bounds.get_x(),bounds.get_y(),bounds.get_width(),bounds.get_height())))
                source.set_opacity(0)
        icon=target.get_child() if isinstance(target,Gtk.Button) else target
        ok,bounds=icon.compute_bounds(window.root_overlay) if icon else (False,None)
        self.target=(bounds.get_x()+bounds.get_width()/2,bounds.get_y()+bounds.get_height()/2) if ok else None
        self.destination=target;window.action_motion=self;window.root_overlay.add_overlay(self)
        started=None
        def frame(widget,clock):
            nonlocal started
            now=clock.get_frame_time()
            if started is None:started=now
            self.progress=min(1,(now-started)/360000) if self.target and self.frames and Gtk.Settings.get_default().get_property('gtk-enable-animations') else 1
            if viewer:
                viewer.backdrop.set_opacity(1-self.progress)
                for arrow in viewer.arrows:arrow.set_opacity(0)
            self.queue_draw()
            if self.progress>=1:
                window.root_overlay.remove_overlay(self);window.action_motion=None;done();return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        self.tick=self.add_tick_callback(frame)

    def cancel(self):
        if self.tick:self.remove_tick_callback(self.tick);self.tick=0
        self.frames.clear()
        if self.get_parent()==self.window.root_overlay:self.window.root_overlay.remove_overlay(self)
        self.window.action_motion=None

    def do_measure(self,orientation,for_size):return 0,0,-1,-1

    def do_snapshot(self,snapshot):
        if self.target is None:return
        p=self.progress;p=p*p*(3-2*p);tx,ty=self.target
        for paintable,(x,y,w,h) in self.frames:
            width=w*(1-p)+8*p;height=h*(1-p)+8*p
            px=x*(1-p)+(tx-width/2)*p;py=y*(1-p)+(ty-height/2)*p-40*4*p*(1-p)
            snapshot.save();snapshot.translate(Graphene.Point().init(px,py));snapshot.push_opacity(1-p**5)
            paintable.snapshot(snapshot,width,height);snapshot.pop();snapshot.restore()
