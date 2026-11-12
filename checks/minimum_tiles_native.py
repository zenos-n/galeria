"""Extreme assets stay usable in all/photo folders, with checks inside each tile."""
import os,sys,time,tempfile
from datetime import datetime,timedelta
from pathlib import Path
assert os.environ.get('DISPLAY')==':91'
sys.path.insert(0,os.environ.get('GALERIA_CHECK_SOURCE_ROOT',str(Path(__file__).resolve().parents[1])))
root=tempfile.TemporaryDirectory(prefix='galeria-minimum-tiles-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
from library import MediaItem
from imaging import decode_image
from PIL import Image
specs=[(3,1800)]*6+[(2400,2)]*2+[(160,112)]*5
items=[];originals={}
for i,(width,height) in enumerate(specs):
    path=Path(root.name)/f'photo-{i}.png';Image.new('RGB',(width,height),['purple','orange','teal'][i%3]).save(path)
    originals[path]=path.read_bytes();items.append(MediaItem(str(i),path.name,datetime(2026,11,12)-timedelta(minutes=i),width/height,path=str(path)))
app=Adw.Application(application_id='com.neg-zero.Galeria.MinimumTilesCheck',flags=Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path(sys.modules['app'].__file__).with_name('style.css')))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
w=GalleryWindow(app);w.set_default_size(1000,800);w.present();w.library_mode='local';w.local_items=items
GLib.source_remove(w.refresh_timer);w.refresh_timer=0
for item in items:w.texture_cache[w.texture_key(item)]=w.texture_from_pixels(decode_image(item.path))
w.set_library_items(items);context=GLib.MainContext.default()
def pump(test):
    end=time.monotonic()+8
    while not test():
        assert time.monotonic()<end
        context.iteration(False);time.sleep(.002)
def check_tiles():
    m=w.mosaic;rects=m.target_layout(m.last_width)[0]
    values=[rects[tile] for tile in m.tiles if tile in rects]
    assert values
    assert all(width>=64 and height>=64 for x,y,width,height,*_ in values),values
    for x,y,width,height,*_ in values:assert x>=0 and x+width<=m.last_width
try:
    pump(lambda:not w.loading_more and bool(w.mosaic.rendered));m=w.mosaic
    for density in (112,154,210):
        w.set_density(density);m.queue_allocate()
        until=time.monotonic()+.06;pump(lambda:time.monotonic()>=until);check_tiles()
    m.selected={0};m.set_selection(True)
    pump(lambda:m.checks[0].widget is not None and m.checks[0].widget.get_width()>0)
    x,y,width,height,*_=m.rendered[m.tiles[0]];ok,bounds=m.checks[0].compute_bounds(m)
    assert ok and bounds.get_x()>=x and bounds.get_y()>=y
    assert bounds.get_x()+bounds.get_width()<=x+width and bounds.get_y()+bounds.get_height()<=y+height
    snapshot=Gtk.Snapshot();Gtk.WidgetPaintable.new(w).snapshot(snapshot,w.get_width(),w.get_height())
    w.get_renderer().render_texture(snapshot.to_node(),None).save_to_png('/tmp/gallery-app-identification/minimum-tiles-01416.png')
    m.set_selection(False)
    for mode in ('months','years'):
        w.switcher.set_active_name(mode);pump(lambda:not m.tick)
        m.expand_month(m.months[0][0]) if mode=='months' else m.expand_year(m.months[0][2])
        pump(lambda:not m.tick);check_tiles()
    w.open_viewer(0);pump(lambda:w.viewer.stage.progress==1)
    assert abs(w.viewer.stage.ratio-specs[0][0]/specs[0][1])<1e-8
    assert all(path.read_bytes()==content for path,content in originals.items())
    print('MIN64x64 AT ALL DENSITIES/EXPANDED MONTH/YEAR; CHECK CONTAINED; FOCUS ASPECT/ORIGINAL BYTES PRESERVED PASSED',flush=True)
finally:w.stop_data();w.destroy()
