"""Replace a warm date catalog while three old metadata jobs remain in flight."""
import os,sys,tempfile,time,threading
from pathlib import Path
from datetime import datetime
from io import BytesIO
assert os.environ.get('DISPLAY')==':91' and os.environ.get('GDK_BACKEND')=='x11'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=tempfile.TemporaryDirectory(prefix='galeria-reconnect-index-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
from library import MediaItem
from timeline_index import TimelineIndex
from PIL import Image
from imaging import decode_image
png=BytesIO();Image.new('RGB',(90,60),'purple').save(png,format='PNG');png=png.getvalue()
rows={f'2026-{month:02}':[MediaItem(f'{month}-{i}',str(i),datetime(2026,month,20-i),1.5,metadata={'visibility':'timeline'}) for i in range(3)] for month in (12,11,10,9)}
old_buckets=[{'timeBucket':key+'-01','count':len(values)} for key,values in rows.items()]
new_rows=[MediaItem('arrival','new',datetime(2026,12,25),1.5,metadata={'visibility':'timeline'})]+rows['2026-12']
new_buckets=[{'timeBucket':'2026-12-01','count':4}]+old_buckets[1:]
dates=threading.Event();old_jobs=threading.Event();incoming=threading.Event();started=[];fresh_started=threading.Event()
class Client(ImmichClient):
 def __init__(self):super().__init__('https://fixture.invalid');self.user={'id':'fixture'};self.token='fixture'
 def albums(self):return []
 def time_buckets(self,**kwargs):assert dates.wait(10);return new_buckets
 def time_bucket(self,key,fresh=False,**kwargs):
  if key=='2026-12':
   assert fresh,'Changed populated month must bypass the stale disk snapshot'
   fresh_started.set();assert incoming.wait(10);return new_rows
  started.append(key);assert old_jobs.wait(10);return rows[key]
 def image_bytes(self,*args,**kwargs):return png
app=Adw.Application(application_id='com.neg-zero.Galeria.ReconnectIndexTest',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=0;start=time.monotonic();errors=[];mark=0
def check():
 global phase,mark
 try:
  assert time.monotonic()-start<15,phase
  if phase==0 and len(started)>=2 and len(w.timeline_pending)==3:
   assert w.timeline_index is initial
   # A populated range can be refreshing without belonging to loaded.
   initial.loaded.discard('2026-12')
   dates.set();phase=1
  elif phase==1 and w.timeline_index is not initial:
   assert w.timeline_index.items[0].id=='12-0'
   assert w.mosaic.tiles[0].media_item.id=='12-0'
   assert '2026-12' in w.timeline_index.refresh_keys
   old_jobs.set();mark=time.monotonic();phase=2
  elif phase==2 and fresh_started.is_set() and time.monotonic()-mark>.2:
   assert w.mosaic.tiles[0].media_item.id=='12-0' and w.mosaic.tiles[0].media_texture
   assert not any(item.metadata.get('placeholder') for item in w.media_items[:3])
   incoming.set();phase=3
  elif phase==3 and len(w.timeline_index.loaded)==4 and not w.timeline_pending and not w.loading_more:
   assert w.media_items[0].id=='arrival'
   assert all(not tile.media_item.metadata.get('placeholder') for tile in w.mosaic.tiles)
   assert not w.timeline_index.refresh_keys and len(w.media_items)==13
   assert all(tile.media_texture for tile in w.mosaic.active_widgets & w.mosaic.tile_set)
   print('THREE STALE METADATA REQUESTS RELEASED; WARM PHOTOS REMAIN VISIBLE DURING CHANGED-CATALOG RECONNECT; NEW MONTH DATA FETCHES FRESH; ALL PHOTOS/TEXTURES LOAD PASSED',flush=True)
   w.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);dates.set();old_jobs.set();incoming.set();w.close();app.quit();return False
 return True
def activate(app):
 global w,initial
 w=GalleryWindow(app);w.set_default_size(1100,760);w.present();w.client=Client();w.library_mode='immich'
 GLib.source_remove(w.refresh_timer);w.refresh_timer=0
 initial=TimelineIndex(old_buckets);initial.apply('2026-12',rows['2026-12'])
 w.timeline_index=initial;w.timeline_buckets=old_buckets;w.dates_ready=True
 texture=w.texture_from_pixels(decode_image(png))
 for item in rows['2026-12']:w.texture_cache[w.texture_key(item)]=texture
 w.refresh_connected_library();w.set_library_items(initial.items)
 GLib.timeout_add(30,check)
app.connect('activate',activate);app.run([])
assert not errors
