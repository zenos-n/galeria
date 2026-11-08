"""Click-to-painted-viewer budget with slow metadata, plus privacy/stale guards."""
import os,sys,time,tempfile,threading,json,cProfile,pstats
from pathlib import Path
from datetime import datetime
assert os.environ.get('DISPLAY')==':91'
root=tempfile.TemporaryDirectory(prefix='galeria-viewer-latency-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
sys.path.insert(0,os.environ.get('GALERIA_CHECK_SOURCE_ROOT',str(Path(__file__).resolve().parents[1])))
from app import *
from library import ImmichClient,MediaItem,LibraryError
from imaging import decode_image
from PIL import Image
import subprocess
gi.require_version('GdkX11','4.0')
from gi.repository import GdkX11
photo=Path(root.name)/'cached.png';Image.new('RGB',(320,200),'purple').save(photo);pixels=photo.read_bytes()
items=[MediaItem(str(i),'Cached photo',datetime(2026,11,3),1.6,metadata={'visibility':'timeline','timeline_stub':True}) for i in range(12)]
items[3].metadata.pop('timeline_stub');items[3].filename='Already hydrated'
for i in (9,10):items[i].kind='VIDEO';items[i].metadata['type']='VIDEO'
clip=Path(root.name)/'video.mp4'
subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=purple:size=160x100:rate=15','-t','2','-pix_fmt','yuv420p','-threads','1',str(clip)],check=True)
class Client(ImmichClient):
 def __init__(self):super().__init__('https://fixture.invalid');self.token='fixture';self.user={'id':'fixture'};self.requests=[];self.images=[];self.validated={'3'};self.gates={}
 def asset(self,id):
  self.requests.append(id)
  if id in self.gates:assert self.gates[id].wait(12)
  else:time.sleep(1.2)
  if id=='7':raise LibraryError('Fixture metadata unavailable')
  self.validated.add(id)
  return MediaItem(id,'Hydrated '+id,datetime(2026,11,3),1.6,kind='VIDEO' if id in ('9','10') else 'IMAGE',metadata={'visibility':'locked' if id in ('6','9') else 'timeline','isFavorite':True})
 def image_bytes(self,item,preview=False,*_args,**_kwargs):
  assert item.id in self.validated,'Full pixels requested before metadata validation'
  assert item.id not in ('6','9'),'Private full media must never load'
  self.images.append(item.id);return pixels
client=Client();app=Adw.Application(application_id='com.neg-zero.Galeria.ViewerLatency',flags=Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
w=GalleryWindow(app);w.set_default_size(1280,900);w.present();w.client=client;notices=[];w.notice=notices.append
GLib.source_remove(w.refresh_timer);w.refresh_timer=0
timings=[];start=None;painted=None;ui_ms=[];profile=cProfile.Profile();open_viewer=w.open_viewer
def clicked(index,source=None):
 global start
 if start is None:start=time.perf_counter()
 before=time.perf_counter();profile.enable();open_viewer(index,source);profile.disable();ui_ms.append((time.perf_counter()-before)*1000)
w.open_viewer=clicked
texture=w.texture_from_pixels(decode_image(photo))
for item in items:w.texture_cache[w.texture_key(item)]=texture
w.preload_video=lambda *args,**kwargs:None
registered=[]
class Proxy:
 def register(self,client,item,vault):
  assert item.id in client.validated and item.id not in ('6','9')
  registered.append(item.id);return Gio.File.new_for_path(str(clip)).get_uri()
w.get_video_proxy=lambda:Proxy()
w.set_library_items(items)
def pump(until,timeout=12):
 deadline=time.monotonic()+timeout;context=GLib.MainContext.default()
 while not until():
  assert time.monotonic()<deadline,('Timed out',notices)
  context.iteration(False);time.sleep(.003)
 for _ in range(3):context.iteration(False)
def painted_frame(clock):
 global painted
 if start is not None and painted is None and w.viewer and w.viewer.stage.get_mapped() and w.viewer.stage.progress>0:
  painted=(time.perf_counter()-start)*1000
def click(index):
 global start,painted
 start=painted=None
 widget=w.mosaic.tiles[index].get_child();ok,rect=widget.compute_bounds(w);assert ok
 dx,dy=w.get_surface_transform();tool='/tmp/gallery-app-identification/xdotool/bin/xdotool';xid=str(GdkX11.X11Surface.get_xid(w.get_surface()))
 subprocess.run([tool,'windowraise',xid,'windowfocus',xid,'mousemove','--window',xid,str(round(rect.get_x()+rect.get_width()/2+dx)),str(round(rect.get_y()+rect.get_height()/2+dy)),'click','1'],check=True)
 pump(lambda:painted is not None);return painted
def close():
 if w.viewer:w.viewer.close();pump(lambda:w.viewer is None)
try:
 pump(lambda:not w.loading_more and bool(w.mosaic.rendered));w.get_frame_clock().connect('after-paint',painted_frame)
 for index in range(4):
  latency=click(index);timings.append(latency)
  if '--measure-only' not in sys.argv and index<3:
   assert w.viewer.metadata_pending and str(index) not in client.images
   assert w.viewer.stage.image.get_paintable() is texture
   assert not w.viewer.edit_button.get_sensitive() and not w.viewer.download.get_sensitive()
   w.viewer.set_editing(True);assert not w.viewer.editing
   assert w.viewer.on_key(None,Gdk.KEY_D,0,Gdk.ModifierType.SHIFT_MASK)
   w.open_viewer(index);assert client.requests.count(str(index))==1
  pump(lambda:w.viewer.stage.progress==1 and w.viewer.photo_editor.original is not None)
  assert not w.viewer.source.media_item.metadata.get('timeline_stub')
  assert w.viewer.edit_button.get_sensitive() and w.viewer.favorite.get_active()==(index!=3)
  close()
 if '--measure-only' not in sys.argv:
  assert sorted(timings[:3])[1]<250 and max(timings)<500,timings
  assert click(4)<500;pump(lambda:w.viewer.stage.progress==1);w.viewer.move(1)
  assert w.viewer.metadata_pending and not w.viewer.download.get_sensitive()
  pump(lambda:w.viewer.source.media_item.id=='5' and not w.viewer.metadata_pending and w.viewer.photo_editor.original is not None)
  assert '4' not in client.images and '5' in client.images;close()
  assert click(10)<500
  assert w.viewer.metadata_pending and w.viewer.stage.video_player is None
  pump(lambda:w.viewer.stage.video_player is not None and w.viewer.stage.video_player.player.get_position()>.1)
  assert registered==['10'];close()
  for index in (6,9):
   assert click(index)<500
   assert w.viewer.metadata_pending and w.viewer.stage.video_player is None
   pump(lambda:w.viewer is None);assert str(index) not in client.images and str(index) not in registered
  assert any('public timeline' in text for text in notices)
  assert click(7)<500;pump(lambda:any('Fixture metadata unavailable' in text for text in notices))
  assert w.viewer.metadata_pending and not w.viewer.download.get_sensitive();close()
  client.gates['8']=threading.Event();assert click(8)<500
  close();assert click(3)<500;active=w.viewer;client.gates['8'].set()
  until=time.monotonic()+.3;pump(lambda:time.monotonic()>until)
  assert w.viewer is active and active.source.media_item.id=='3' and '8' not in client.images
  close()
 result={'metadata_delay_ms':1200,'click_to_painted_viewer_ms':timings,'synchronous_open_call_ms':ui_ms[:7]}
 print(json.dumps(result),flush=True)
 target=os.environ.get('GALERIA_LATENCY_RESULT')
 if target:Path(target).write_text(json.dumps(result))
 stats=pstats.Stats(profile).sort_stats('cumulative');stats.stream=open(str(Path(target).with_suffix('.profile.txt')) if target else '/tmp/gallery-app-identification/viewer-latency-profile.txt','w');stats.print_stats(12);stats.stream.close()
 print('MEASUREMENT COMPLETE' if '--measure-only' in sys.argv else 'CACHED VIEWER CLICK BUDGET; DETAILS/PREVIEW/ACTIONS VALIDATED; PRIVATE IMAGE/VIDEO BLOCKED; FAILURE/STALE/DUPLICATE GUARDS PASSED',flush=True)
finally:
 for gate in client.gates.values():gate.set()
 w.stop_data();w.destroy();app.quit()
