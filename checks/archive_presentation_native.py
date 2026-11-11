"""Opt-in compositor frame-drop check with synthetic media and a held mutation."""
import os,sys,tempfile,time,threading,json
from pathlib import Path
from datetime import datetime,timedelta
from collections import defaultdict
connector=os.environ.get('GALERIA_CHECK_MONITOR')
assert connector,'Set GALERIA_CHECK_MONITOR explicitly; this opens a synthetic test window.'
assert os.environ.get('GDK_BACKEND')=='wayland'
sys.path.insert(0,os.environ.get('GALERIA_CHECK_SOURCE_ROOT',str(Path(__file__).resolve().parents[1])))
root=tempfile.TemporaryDirectory(prefix='galeria-presentation-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
from library import ImmichClient,MediaItem
from timeline_index import TimelineIndex
from imaging import decode_image
from PIL import Image
image=Path(root.name)/'image.png';Image.effect_noise((320,224),70).convert('RGB').save(image)
class Client(ImmichClient):
    def __init__(self):
        super().__init__('https://fixture.invalid');self.user={'id':'fixture'};self.token='fixture';self.release=threading.Event()
    def image_bytes(self,*args,**kwargs):return image.read_bytes()
    def update_assets(self,*args):assert self.release.wait(12)
app=Adw.Application(application_id='com.neg-zero.Galeria.PresentationCheck',flags=Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path(sys.modules['app'].__file__).with_name('style.css')))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
w=GalleryWindow(app);w.client=Client()
monitors=Gdk.Display.get_default().get_monitors()
monitor=next((m for i in range(monitors.get_n_items()) if (m:=monitors.get_item(i)).get_connector()==connector),None)
assert monitor
w.fullscreen_on_monitor(monitor);w.present()
GLib.source_remove(w.refresh_timer);w.refresh_timer=0
context=GLib.MainContext.default()
def pump(test):
    end=time.monotonic()+12
    while not test():
        assert time.monotonic()<end
        context.iteration(False);time.sleep(.001)
try:
    selected=int(os.environ.get('GALERIA_BULK_SELECTED','20'))
    items=[MediaItem(str(i),'photo.png',datetime(2026,11,30)-timedelta(days=i),10/7) for i in range(8000)]
    pixels=decode_image(image)
    for item in items[:600]:w.texture_cache[w.texture_key(item)]=w.texture_from_pixels(pixels)
    groups=defaultdict(list)
    for item in items:groups[item.created.strftime('%Y-%m')].append(item)
    buckets=[{'timeBucket':key+'-01','count':len(values)} for key,values in groups.items()]
    index=TimelineIndex(buckets)
    for key,values in groups.items():index.apply(key,values)
    w.timeline_index=index;w.timeline_buckets=buckets;w.set_library_items(index.items)
    pump(lambda:w.get_mapped() and not w.loading_more and bool(w.mosaic.rendered))
    w.mosaic.selected=set(range(selected));w.mosaic.set_selection(True);pump(w.selection_bar.get_child_revealed)
    counters=[];ended=False
    def frame(clock):
        global ended
        if w.action_motions:counters.append(clock.get_frame_counter())
        elif counters and not ended:ended=True;counters.append(clock.get_frame_counter())
    clock=w.get_frame_clock();clock.connect('after-paint',frame)
    w.selection_controls['archive'].emit('clicked');pump(lambda:ended)
    assert w.pending_mutations and not w.client.release.is_set()
    until=time.monotonic()+.1;pump(lambda:time.monotonic()>=until)
    timings=[clock.get_timings(c) for c in counters]
    presented=[t.get_presentation_time() for t in timings if t and t.get_complete() and t.get_presentation_time()>0]
    assert len(presented)>=8,'Compositor presentation feedback unavailable'
    gaps=[(b-a)/1000 for a,b in zip(presented,presented[1:])]
    period=1000000/monitor.get_refresh_rate()
    missed=sum(gap>period*1.5 for gap in gaps)
    print(json.dumps({'selected':selected,'months':len(buckets),'renderer':type(w.get_renderer()).__name__,
                      'refresh_ms':period,'presentation_gaps_ms':gaps,'missed_frames':missed}),flush=True)
    assert not missed,'Compositor reported missed animation frames'
finally:
    w.client.release.set();w.stop_data();w.destroy()
