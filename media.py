"""Thumbnail-to-viewer morph using the source thumbnail's actual rendering."""
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk
from crop_ui import CropOverlay


class PhotoStage(Gtk.Widget):
    __gtype_name__ = "GalleryPhotoStage"

    def __init__(self, source, index):
        super().__init__(hexpand=True, vexpand=True)
        self.ratio = source.photo_ratio
        self.progress = 0.0
        self.source_rect = None
        self.tick = 0
        self.geometry_tick = 0
        self.geometry_rect = None
        self.last_rect = None
        self.set_opacity(0)
        self.zoom=1.;self.pan_x=self.pan_y=0.
        self.rotation = 0
        self.flipped = False
        self.crop_ratio = None
        self.render_ratio = None
        self.top_inset = 52
        self.bottom_inset = 0
        self.immersive = False
        self.frozen_destination = None
        self.video_player=None
        self.picture = Gtk.Overlay()
        self.material = Gtk.Overlay(hexpand=True, vexpand=True)
        self.material.add_css_class("expanded-photo")
        self.material.add_css_class(f"shade-{index % 5}")
        self.surface = Gtk.Box(hexpand=True, vexpand=True)
        self.material.set_child(self.surface)
        self.picture.set_child(self.material)
        self.symbol = Gtk.Image(icon_name="image-x-generic-symbolic", pixel_size=58,
                                halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.symbol.add_css_class("placeholder-icon")
        self.picture.add_overlay(self.symbol)
        self.crop_frame = CropOverlay()
        self.crop_frame.aspect=self.ratio
        self.crop_frame.set_visible(False)
        self.picture.add_overlay(self.crop_frame)
        # Capture before hiding the grid tile; this is the exact endpoint image.
        paintable = Gtk.WidgetPaintable.new(source.get_child()).get_current_image() if hasattr(source,'get_child') else None
        self.thumbnail = Gtk.Picture(paintable=paintable, can_shrink=True, content_fit=Gtk.ContentFit.FILL)
        self.thumbnail.set_can_target(False)
        self.picture.add_overlay(self.thumbnail)
        self.material.set_opacity(1)
        self.symbol.set_opacity(0)
        self.image=Gtk.Picture(can_shrink=True,content_fit=Gtk.ContentFit.COVER)
        self.image.set_overflow(Gtk.Overflow.HIDDEN)
        self.material.set_child(self.image)
        self.material.add_overlay(self.surface)
        self.surface.set_can_target(False)
        if getattr(source,'media_texture',None):
            self.set_texture(source.media_texture)
        self.picture.set_parent(self)

    def set_texture(self,texture):
        self.ratio=texture.get_intrinsic_width()/texture.get_intrinsic_height()
        self.image.set_paintable(texture)
        self.symbol.set_visible(False)
        self.queue_allocate()

    def set_video(self,uri):
        from video_ui import VideoPlayer
        if self.video_player:
            self.video_player.stop();self.material.remove_overlay(self.video_player)
        self.video_player=VideoPlayer(uri)
        self.material.add_overlay(self.video_player)
        self.symbol.set_visible(False)

    def destination(self, width, height):
        if self.frozen_destination:
            return self.frozen_destination
        ratio = self.render_ratio or self.crop_ratio or self.ratio
        if self.render_ratio is None and self.rotation % 180:
            ratio = 1 / ratio
        margin = 0 if self.immersive else 20
        bottom = self.bottom_inset() if callable(self.bottom_inset) else self.bottom_inset
        available_height = max(1, height-self.top_inset-bottom-margin*2)
        w = min(max(1, width-margin*2), available_height*ratio)
        h = w / ratio
        return (width-w)/2, self.top_inset + margin + (available_height-h)/2, w, h

    def rect(self, width, height):
        if self.geometry_rect is not None:
            return self.geometry_rect
        end = self.destination(width, height)
        if not self.source_rect:
            return end
        sx, sy, sw, sh = self.source_rect
        ex, ey, ew, eh = end
        sx, sy, ex, ey = sx+sw/2, sy+sh/2, ex+ew/2, ey+eh/2
        dx, dy = ex-sx, ey-sy
        cx, cy = (sx+ex)/2 + dy*.22, (sy+ey)/2-max(48, abs(dx)*.28)
        p = self.progress
        x = (1-p)**2*sx + 2*(1-p)*p*cx + p*p*ex
        y = (1-p)**2*sy + 2*(1-p)*p*cy + p*p*ey
        w, h = sw+(ew-sw)*p, sh+(eh-sh)*p
        return x-w/2, y-h/2, w, h

    def animate(self, source, reverse, on_progress, complete):
        if self.geometry_tick:
            self.remove_tick_callback(self.geometry_tick)
            self.geometry_tick=0
            self.geometry_rect=None
        if self.tick:
            self.remove_tick_callback(self.tick)
        start_time, settled = None, False
        initial = self.progress
        self.source_rect = None
        if reverse:
            self.frozen_destination = self.destination(self.get_width(), self.get_height())
        duration = 360000 if Gtk.Settings.get_default().get_property("gtk-enable-animations") else 1

        def frame(_widget, clock):
            nonlocal start_time, settled
            if settled:
                self.tick = 0
                complete()
                return GLib.SOURCE_REMOVE
            if self.get_width() < 1:
                return GLib.SOURCE_CONTINUE
            if self.source_rect is None:
                ok, bounds = source.compute_bounds(self) if source is not None else (False,None)
                self.source_rect = ((bounds.get_x(), bounds.get_y(), bounds.get_width(), bounds.get_height())
                                    if ok else self.destination(self.get_width(), self.get_height()))
                self.set_opacity(1)
            now = clock.get_frame_time()
            if start_time is None:
                start_time = now
            t = min(1, (now-start_time)/duration)
            ease = t*t*(3-2*t)
            self.progress = initial + ((0 if reverse else 1)-initial)*ease
            if source is None:self.set_opacity(self.progress)
            self.thumbnail.set_opacity((1-self.progress)**5)
            self.material.set_opacity(1)
            self.symbol.set_opacity(self.progress)
            self.symbol.set_pixel_size(round(23+35*self.progress))
            on_progress(self.progress)
            self.queue_allocate()
            # Render the exact endpoint for a frame before revealing the tile.
            settled = t >= 1
            return GLib.SOURCE_CONTINUE

        self.tick = self.add_tick_callback(frame)

    def animate_geometry(self, previous=None, duration_ms=260, dynamic=False):
        if self.progress < 1 or self.tick:
            return
        if self.geometry_tick:
            self.remove_tick_callback(self.geometry_tick)
        start = previous or self.last_rect or self.destination(self.get_width(),self.get_height())
        end = self.destination(self.get_width(),self.get_height())
        self.geometry_rect=start
        started = None
        duration = duration_ms*1000 if Gtk.Settings.get_default().get_property('gtk-enable-animations') else 1
        def frame(_widget, clock):
            nonlocal started
            now = clock.get_frame_time()
            if started is None:
                started = now
            t = min(1,(now-started)/duration)
            p = t*t*(3-2*t)
            target=self.destination(self.get_width(),self.get_height()) if dynamic else end
            self.geometry_rect = tuple(a+(b-a)*p for a,b in zip(start,target))
            self.queue_allocate()
            if t>=1:
                self.geometry_tick=0
                self.geometry_rect=None
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        self.geometry_tick=self.add_tick_callback(frame)

    def dispose(self):
        if self.video_player:self.video_player.stop()
        if self.geometry_tick:
            self.remove_tick_callback(self.geometry_tick)
            self.geometry_tick=0
        if self.tick:
            self.remove_tick_callback(self.tick)
            self.tick = 0
        if self.picture.get_parent():
            self.picture.unparent()

    def do_measure(self, orientation, for_size):
        return 0, 0, -1, -1

    def do_size_allocate(self, width, height, baseline):
        x,y,w,h = self.rect(width,height)
        base_w,base_h=w,h
        x+=(w-w*self.zoom)/2+self.pan_x;y+=(h-h*self.zoom)/2+self.pan_y
        self.last_rect=(x,y,w*self.zoom,h*self.zoom)
        self.picture.measure(Gtk.Orientation.HORIZONTAL,-1)
        self.picture.measure(Gtk.Orientation.VERTICAL,round(w))
        point=Graphene.Point()
        point.init(x,y)
        self.picture.allocate(max(1,round(base_w)),max(1,round(base_h)),-1,Gsk.Transform.new().translate(point).scale(self.zoom,self.zoom))

    def do_snapshot(self,snapshot):
        snapshot.push_clip(Graphene.Rect().init(0,0,self.get_width(),self.get_height()))
        self.snapshot_child(self.picture,snapshot);snapshot.pop()
