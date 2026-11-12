"""Cached thumbnails bypass blocked HTTP; metadata hydration keeps scroll stable."""
import os,sys,tempfile,time,threading
from pathlib import Path
from datetime import datetime
from io import BytesIO
assert os.environ.get('DISPLAY')==':91' and os.environ.get('GDK_BACKEND')=='x11'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=tempfile.TemporaryDirectory(prefix='galeria-cache-scroll-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
from library import MediaItem
from timeline_index import TimelineIndex
from PIL import Image
png=BytesIO();Image.new('RGB',(90,60),'purple').save(png,format='PNG');png=png.getvalue()
items=[MediaItem(str(i),str(i),datetime(2026,12-i//80,20-i%20),1.5,metadata={'visibility':'timeline'}) for i in range(240)]
buckets=[{'timeBucket':f'2026-{month:02}-01','count':80} for month in (12,11,10)]
metadata=threading.Event();network=threading.Event();started=[]
class Client(ImmichClient):
 def __init__(self):super().__init__('https://fixture.invalid');self.user={'id':'fixture'};self.token='fixture'
 def time_bucket(self,key,**kwargs):
  assert metadata.wait(10)
  return [item for item in items if item.created.strftime('%Y-%m')==key]
 def image_bytes(self,*args,**kwargs):raise AssertionError('Warm cache must not fetch HTTP')
app=Adw.Application(application_id='com.neg-zero.Galeria.CacheScrollTest',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=0;start=time.monotonic();errors=[];mark=0
def check():
 global phase,old,mark,held,scroll
 try:
  assert time.monotonic()-start<15,phase
  if phase==0 and w.mosaic.rendered and len(started)==4:
   old=w.mosaic;w.scroller.get_vadjustment().set_value(900);metadata.set();phase=1
  elif phase==1 and w.timeline_index.loaded=={'2026-12','2026-11'} and all(tile.media_texture for tile in w.mosaic.active_widgets & w.mosaic.tile_set):
   assert w.mosaic is old and not w.mosaic.tick
   assert not network.is_set() and len(started)==4
   assert w.scroller.get_vadjustment().get_value()==900
   print('CACHED PIXELS READY WITH ALL FOUR HTTP WORKERS BLOCKED; ONLY VISIBLE/PREFETCH MONTHS HYDRATE WITHOUT MOTION OR SCROLL RESET',flush=True)
   w.set_library_items(w.timeline_index.items,append=True)
   def wheel():
    w.user_scrolled();w.scroller.get_vadjustment().set_value(1300);return False
   GLib.timeout_add(5,wheel);mark=time.monotonic();phase=2
  elif phase==2 and time.monotonic()-mark>.15:
   assert w.scroller.get_vadjustment().get_value()==1300,w.scroller.get_vadjustment().get_value()
   w.year_scrollbar.refresh();w.year_scrollbar.held=True
   w.mosaic.update_bucket('2026-12',[MediaItem(item.id,item.filename,item.created,.8,metadata=item.metadata) for item in w.timeline_index.items[:80]])
   w.scroller.get_vadjustment().set_value(1700);mark=time.monotonic();phase=3
  elif phase==3 and time.monotonic()-mark>.15:
   assert w.scroller.get_vadjustment().get_value()==1700,w.scroller.get_vadjustment().get_value()
   print('DEFERRED RESTORE YIELDS TO NEW WHEEL INPUT AND HELD YEAR SCROLLBAR PASSED',flush=True)
   network.set();w.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);metadata.set();network.set();w.close();app.quit();return False
 return True
def activate(app):
 global w
 w=GalleryWindow(app);w.set_default_size(1200,800);w.present();w.client=Client();w.library_mode='immich'
 GLib.source_remove(w.refresh_timer);w.refresh_timer=0
 for item in items:w.client.media_cache().put(w.client.image_key(item),png)
 def blocked():started.append(1);network.wait(10)
 for _ in range(4):w.images.submit(blocked,0)
 w.timeline_buckets=buckets;w.timeline_index=TimelineIndex(buckets);w.dates_ready=True;w.set_library_items(w.timeline_index.items)
 GLib.timeout_add(20,check)
app.connect('activate',activate);app.run([])
assert not errors
