"""Native interactive map with the Immich style and clustered photo markers."""
import json
import gi
gi.require_version('Shumate','1.0')
from gi.repository import Adw,GLib,Gtk,Shumate
from collection_widgets import cover
from map_geometry import clusters,fit,valid_points


def supported_style(value):
    # Shumate renders script labels but has no MapLibre script-detection operator.
    if isinstance(value,list):
        if value and value[0]=='is-supported-script':return True
        return [supported_style(item) for item in value]
    if isinstance(value,dict):return {key:supported_style(item) for key,item in value.items()}
    return value


class PhotoMap(Gtk.Overlay):
    def __init__(self,window,client,values):
        super().__init__(hexpand=True,vexpand=True)
        self.window=window;self.client=client;self.points=valid_points(values);self.pending=0;self.generation=0
        self.simple=Shumate.SimpleMap.new();self.simple.set_show_zoom_buttons(True);self.set_child(self.simple)
        self.map=self.simple.get_map();self.viewport=self.simple.get_viewport()
        registry=Shumate.MapSourceRegistry.new_with_defaults();self.simple.set_map_source(registry.get_by_id('osm-mapnik'))
        self.layer=Shumate.MarkerLayer.new(self.viewport);self.simple.add_overlay_layer(self.layer)
        self.viewport.connect('notify',lambda *_:self.schedule())
        self.size_watch=Gtk.WidgetPaintable.new(self.simple);self.size_handler=0;self.did_fit=False
        self.connect('map',self.mapped)
        tools=Gtk.Box(spacing=6,halign=Gtk.Align.END,valign=Gtk.Align.START,margin_top=100,margin_end=12,css_classes=['toolbar','osd'])
        fit_button=Gtk.Button(icon_name='find-location-symbolic',tooltip_text='Fit all photos',css_classes=['flat'])
        fit_button.connect('clicked',lambda _:self.fit_all());tools.append(fit_button);self.add_overlay(tools)
        self.note=Gtk.Label(label='Loading map…',halign=Gtk.Align.CENTER,valign=Gtk.Align.START,margin_top=12,
                            css_classes=['osd','map-note'],can_target=False)
        self.add_overlay(self.note)
        self.connect('unmap',self.unmapped)
        self.style_manager=Adw.StyleManager.get_default()
        self.theme_handler=0;self.requested_dark=None
        self.load_style()

    def alive(self):return self.window.current_page=='map' and self.window.stack.get_child_by_name('collections')==self

    def load_style(self):
        dark=self.style_manager.get_dark()
        self.requested_dark=dark
        def ready(style):
            if not self.alive() or dark!=self.style_manager.get_dark():return
            try:
                source=Shumate.VectorRenderer.new('galeria-immich-'+('dark' if dark else 'light'),json.dumps(supported_style(style)))
                source.set_license('© OpenStreetMap contributors')
                self.simple.set_map_source(source)
                self.note.set_visible(not self.points);self.note.set_label('No geotagged photos found')
                self.schedule()
            except GLib.Error:self.style_failed('')
        self.window.background(lambda:self.client.map_style(dark),ready,self.style_failed)

    def style_failed(self,_message):
        if self.alive():
            self.note.set_label('OpenStreetMap · server style unavailable' if self.points else 'No geotagged photos found')
            self.note.set_visible(True)

    def unmapped(self,*_):
        if self.pending:GLib.source_remove(self.pending);self.pending=0
        if self.theme_handler:self.style_manager.disconnect(self.theme_handler);self.theme_handler=0
        if self.size_handler:self.size_watch.disconnect(self.size_handler);self.size_handler=0
        self.generation+=1

    def mapped(self,*_):
        self.theme_handler=self.style_manager.connect('notify::dark',lambda *_:self.load_style())
        self.size_handler=self.size_watch.connect('invalidate-size',lambda *_:self.schedule())
        if self.requested_dark!=self.style_manager.get_dark():self.load_style()
        if not self.did_fit:self.did_fit=True;GLib.idle_add(self.fit_all)
        else:self.schedule()

    def schedule(self):
        if not self.pending:self.pending=GLib.timeout_add(90,self.rebuild)

    def fit_all(self):
        if not self.get_mapped():return False
        source=self.simple.get_map_source()
        latitude,longitude,zoom=fit(self.points,self.get_width(),self.get_height(),source.get_tile_size())
        self.map.go_to_full_with_duration(latitude,longitude,zoom,300)
        self.schedule();return False

    def rebuild(self):
        self.pending=0
        if not self.get_mapped():return False
        self.generation+=1;generation=self.generation;self.layer.remove_all()
        source=self.simple.get_map_source()
        groups=clusters(self.points,self.viewport.get_latitude(),self.viewport.get_longitude(),self.viewport.get_zoom_level(),
                        self.get_width(),self.get_height(),source.get_tile_size(),self.viewport.get_rotation())
        for group in groups:
            marker=Shumate.Marker.new();marker.set_location(group['latitude'],group['longitude'])
            count=len(group['ids'])
            if count==1:
                image=Adw.Avatar(size=50,show_initials=False)
                button=Gtk.Button(child=image,tooltip_text='Open photo',css_classes=['map-photo','circular'],width_request=56,height_request=56)
                cover(self.window,self.client,group['ids'][0],image,lambda generation=generation:self.alive() and generation==self.generation)
            else:
                text=f'{count:,}' if count<100000 else f'{count//1000}k'
                button=Gtk.Button(label=text,tooltip_text=f'{count:,} photos · zoom in',css_classes=['map-cluster','circular'],width_request=56,height_request=56)
            button.set_overflow(Gtk.Overflow.HIDDEN)
            button.connect('clicked',lambda _,group=group:self.open_group(group))
            marker.set_child(button);self.layer.add_marker(marker)
        self.groups=groups
        return False

    def open_group(self,group):
        if len(group['ids'])>1 and self.viewport.get_zoom_level()<17:
            self.map.go_to_full_with_duration(group['latitude'],group['longitude'],min(18,self.viewport.get_zoom_level()+2),250)
        else:self.window.open_collection('Photos at this location',{'id':group['ids'] if len(group['ids'])>1 else group['ids'][0],'visibility':None})
