"""A snapshot of selected tiles flies into the sidebar Trash icon."""
from gi.repository import GLib,Graphene,Gtk


class TrashMotion(Gtk.Widget):
    def __init__(self,window,tiles,done):
        super().__init__(hexpand=True,vexpand=True,can_target=False)
        self.frames=[];self.progress=0
        for tile in tiles:
            ok,bounds=tile.compute_bounds(window.root_overlay)
            if ok:
                self.frames.append((Gtk.WidgetPaintable.new(tile.get_child()).get_current_image(),
                    (bounds.get_x(),bounds.get_y(),bounds.get_width(),bounds.get_height())))
                tile.set_opacity(0)
        ok,bounds=window.rows['trash'].compute_bounds(window.root_overlay)
        self.target=(bounds.get_x()+16,max(20,min(window.root_overlay.get_height()-24,bounds.get_y()+bounds.get_height()/2))) if ok else (30,window.root_overlay.get_height()-30)
        window.root_overlay.add_overlay(self)
        started=None
        def frame(widget,clock):
            nonlocal started
            now=clock.get_frame_time()
            if started is None:started=now
            self.progress=min(1,(now-started)/450000) if Gtk.Settings.get_default().get_property('gtk-enable-animations') else 1
            self.queue_draw()
            if self.progress>=1:
                window.root_overlay.remove_overlay(self);done();return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        self.add_tick_callback(frame)

    def do_measure(self,orientation,for_size):return 0,0,-1,-1

    def do_snapshot(self,snapshot):
        p=self.progress;p=p*p*(3-2*p)
        tx,ty=self.target
        for paintable,(x,y,w,h) in self.frames:
            width=w*(1-p)+12*p;height=h*(1-p)+12*p
            px=x*(1-p)+(tx-width/2)*p;py=y*(1-p)+(ty-height/2)*p-100*4*p*(1-p)
            snapshot.save();point=Graphene.Point();point.init(px,py);snapshot.translate(point)
            snapshot.push_opacity(1-p**4);paintable.snapshot(snapshot,width,height);snapshot.pop();snapshot.restore()
