"""Delayed real transfers: grid pixels/rings precede backup, no progress reflow."""
import os,sys,tempfile,time,threading,subprocess,json,hashlib
from pathlib import Path
from datetime import datetime
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from unittest.mock import patch
assert os.environ.get('DISPLAY')==':91'
sys.path.insert(0,os.environ.get('GALERIA_CHECK_SOURCE_ROOT',str(Path(__file__).resolve().parents[1])))
root=tempfile.TemporaryDirectory(prefix='galeria-optimistic-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
gi.require_version('GdkX11','4.0');from gi.repository import GdkX11
from PIL import Image,ImageGrab
from library import MediaItem
from timeline_index import TimelineIndex
from imaging import decode_image
from import_ui import start_upload
from sync_engine import SyncEngine,SyncJournal
from sync_service import state_dir
from cache import atomic_write
state_dir().mkdir(parents=True)
photo=Path(root.name)/'clipboard.png';Image.new('RGBA',(120,80),(0,255,0,128)).save(photo)
folder=Path(root.name)/'batch';folder.mkdir();file=folder/'picture.png';Image.new('RGB',(100,80),'blue').save(file)
video=folder/'clip.mp4';subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=purple:size=160x100:rate=10','-t','0.4','-pix_fmt','yuv420p','-threads','1',str(video)],check=True)
failed=Path(root.name)/'retry.png';Image.new('RGB',(90,70),'red').save(failed)
release=threading.Event();posted=threading.Event();assets={};posts=[];errors=[];notices=[];completed=[];fail=False
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*_):pass
 def do_POST(self):
  body=self.rfile.read(int(self.headers['Content-Length']));posts.append(body);posted.set();assert release.wait(12)
  if fail:self.send_response(500);self.end_headers();return
  id='asset-'+str(len(posts));assets[self.headers['x-immich-checksum']]=id
  self.send_response(201);self.end_headers();self.wfile.write(json.dumps({'id':id}).encode())
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
class Client(ImmichClient):
 def __init__(self):super().__init__(f'http://127.0.0.1:{server.server_port}');self.token='fixture';self.user={'id':'fixture'}
 def request(self,path,body=None,**kwargs):
  assert path=='/assets/bulk-upload-check',path
  asset=assets.get(body['assets'][0]['checksum'])
  return {'results':[{'action':'reject','assetId':asset} if asset else {'action':'accept'}]}
 def image_bytes(self,*args,**kwargs):return photo.read_bytes()
app=Adw.Application(application_id='com.neg-zero.Galeria.OptimisticUploadCheck',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=0;start=time.monotonic();sync_thread=None;paint_ms=None

def entries(state=None):
 return [item for item in w.media_items if item.metadata.get('optimistic_upload') and (state is None or item.metadata.get('upload_state')==state)]
def visible(item):
 tile=next((tile for tile in w.mosaic.active_widgets & w.mosaic.tile_set if tile.media_item.id==item.id),None)
 return tile if tile and tile.get_mapped() else None

def check():
 global phase,mark,paint_ms,saved_mosaic,before_posts,fail,sync_thread,entry,pending_tile,original_cells
 try:
  assert time.monotonic()-start<35,(phase,notices,len(posts))
  if phase==0 and w.mosaic.rendered and w.get_mapped():
   w.get_clipboard().set_content(Gdk.ContentProvider.new_for_value(GObject.Value(Gdk.Texture.__gtype__,Gdk.Texture.new_from_filename(str(photo)))))
   xid=str(GdkX11.X11Surface.get_xid(w.get_surface()));w.set_focus(None);original_cells={tile.media_item.id:tile for tile in w.mosaic.tiles};mark=time.monotonic()
   subprocess.run(['/tmp/gallery-app-identification/xdotool/bin/xdotool','windowfocus',xid,'key','--clearmodifiers','ctrl+v'],check=True);phase=1
  elif phase==1:
   pending=entries('uploading')
   if not pending or not (tile:=visible(pending[0])) or not tile.media_texture or not tile.upload_ring:
    assert time.monotonic()-mark<float(os.environ.get('GALERIA_UPLOAD_PAINT_BUDGET','.4')),('No immediate pasted pixels/ring',len(pending));return True
   if paint_ms is None:
    assert time.monotonic()-mark<float(os.environ.get('GALERIA_UPLOAD_PAINT_BUDGET','.4')),'Upload pixels did not paint within400ms';return True
   assert not completed and not release.is_set();assert tile.upload_ring.get_mapped()
   w.mosaic.clicked(tile,tile.index);assert w.viewer is None,'Pending IDs must not issue server actions'
   current_cells={tile.media_item.id:tile for tile in w.mosaic.tiles}
   assert all(current_cells[id] is cell for id,cell in original_cells.items()),'Insertion replaced existing gallery cells'
   pending_tile=tile;saved_mosaic=w.mosaic;phase=2;mark=time.monotonic()
  elif phase==2 and posted.is_set() and time.monotonic()-mark>.2:
   assert w.mosaic is saved_mosaic and entries('uploading')[0].metadata['upload_progress']>.5
   top,height=w.mosaic.visible_range()
   assert all(rect[1]+rect[3]>=top and rect[1]<=top+2*height for tile in w.mosaic.active_widgets & w.mosaic.tile_set if (rect:=w.mosaic.rendered.get(tile))), 'Upload work extends beyond the visible and next screen'
   ImageGrab.grab(xdisplay=':91').save('/tmp/gallery-app-identification/optimistic-upload-0145.png')
   assert not completed;release.set();phase=3
  elif phase==3 and completed and not entries('uploading'):
   assert len(entries('complete'))==1 and entries()[0].id=='asset-1'
   tile=visible(entries()[0])
   if not tile or not tile.button:return True
   assert tile is pending_tile and tile.media_texture and tile.upload_ring is None
   backed=MediaItem('asset-1','server.png',datetime.now(),1.5,metadata={'visibility':'timeline','updatedAt':'server-revision','timeline_slot':True})
   w.timeline_index.apply('2026-11',[backed,*initial]);w.timeline_buckets=[{'timeBucket':'2026-11-01','count':len(initial)+1}]
   w.set_library_items(w.timeline_index.items,append=True,reflow=True)
   assert not entries() and not w.upload_previews.entries
   assert all((item.id,'') in w.texture_cache for item in initial)
   assert ('asset-1','server-revision') in w.texture_cache,'Server adoption lost clipboard pixels'
   posted.clear();release.clear();before_posts=len(posts);start_upload(w,[str(folder)]);phase=4;mark=time.monotonic()
  elif phase==4:
   queued=entries('uploading')
   if len(queued)!=2 or not all(visible(item) and visible(item).upload_ring and visible(item).media_texture for item in queued):
    assert time.monotonic()-mark<1.,('Batch did not appear before upload',len(queued));return True
   assert {item.filename for item in queued}=={'picture.png','clip.mp4'} and not release.is_set()
   assert any(item.kind=='VIDEO' for item in queued)
   if not posted.is_set():return True
   release.set();phase=5
  elif phase==5 and len(completed)==2 and not entries('uploading'):
   assert len(posts)==before_posts+2
   fail=True;release.clear();posted.clear();start_upload(w,[str(failed)]);phase=6
  elif phase==6 and posted.is_set() and entries('uploading'):
   release.set();phase=7;mark=time.monotonic()
  elif phase==7 and entries('failed'):
   item=entries('failed')[0];tile=visible(item)
   if not tile or not tile.media_texture:
    assert time.monotonic()-mark<.7,'Failed upload lost its image';return True
   assert any(isinstance(widget,Gtk.Button) and widget.get_tooltip_text()=='Retry upload' for widget in walk(tile))
   fail=False;release.clear();posted.clear();w.upload_previews.retry(item.metadata['upload_key']);phase=8
  elif phase==8 and posted.is_set() and entries('uploading'):
   release.set();phase=9
  elif phase==9 and len(completed)==3 and not entries('uploading'):
   sync=Path(root.name)/'sync.png';Image.new('RGB',(80,60),'orange').save(sync);os.utime(sync,(time.time()-10,time.time()-10))
   release.clear();posted.clear()
   # A dedicated directory keeps this background job to one original.
   dedicated=Path(root.name)/'sync-only';dedicated.mkdir();sync.rename(dedicated/sync.name)
   def run_sync():
    journal=SyncJournal(state_dir()/'folder-sync.sqlite')
    with patch('sync_engine.time.time',return_value=time.time()-11):
     journal.stable(client.identity,dedicated/sync.name,(dedicated/sync.name).stat())
    def publish(counts):atomic_write(state_dir()/'sync-status.json',json.dumps({'active':True,'updated':time.time(),'accounts':{client.identity:{'busy':True,'progress':counts}}}).encode())
    try:SyncEngine(client,journal,progress=publish).run_folder({'id':'fixture','path':str(dedicated),'recursive':False,'max_depth':0})
    finally:journal.close()
   sync_thread=threading.Thread(target=run_sync,daemon=True);sync_thread.start();phase=10;mark=time.monotonic()
  elif phase==10:
   pending=[item for item in entries('uploading') if item.filename=='sync.png']
   if not pending or not visible(pending[0]) or not visible(pending[0]).upload_ring:
    assert time.monotonic()-mark<1.5,('Folder sync did not create an upload tile',notices);return True
   assert not release.is_set();release.set();phase=11
  elif phase==11 and not sync_thread.is_alive() and not entries('uploading'):
   assert any(item.filename=='sync.png' and item.metadata.get('upload_state')=='complete' for item in entries())
   print(json.dumps({'cached_indexed_items':len(initial),'paste_to_pixels_and_ring_ms':paint_ms,'upload_response_held_until_pixels':True}),flush=True)
   print('OPTIMISTIC PASTE/FILE/FOLDER/VIDEO/SYNC; REAL BYTE PROGRESS WITHOUT GRID REBUILD; ACK REPLACES ID/CLEARS RING; SERVER METADATA ADOPTS PIXELS; FAILURE/RETRY; NO TEMP-ID ACTIONS PASSED',flush=True)
   w.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);release.set();w.close();app.quit();return False
 return True

def walk(widget):
 yield widget
 child=widget.get_first_child()
 while child:yield from walk(child);child=child.get_next_sibling()
def activate(app):
 global w,client,initial
 css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
 w=GalleryWindow(app);w.set_default_size(1200,800);client=Client();w.client=client;w.notice=notices.append;w.upload_finished=lambda client:completed.append(client)
 GLib.source_remove(w.refresh_timer);w.refresh_timer=0
 initial=[MediaItem(str(i),'original.png',datetime(2026,11,1),1.5,metadata={'timeline_slot':True,'visibility':'timeline'}) for i in range(int(os.environ.get('GALERIA_UPLOAD_TEST_ITEMS','1000')))]
 w.timeline_buckets=[{'timeBucket':'2026-11-01','count':len(initial)}];w.timeline_index=TimelineIndex(w.timeline_buckets);w.timeline_index.apply('2026-11',initial)
 texture=w.texture_from_pixels(decode_image(photo))
 for item in initial:w.texture_cache[w.texture_key(item)]=texture
 w.set_library_items(w.timeline_index.items);w.present()
 def painted(clock):
  global paint_ms
  if phase==1 and paint_ms is None:
   pending=entries('uploading')
   if pending and (tile:=visible(pending[0])) and tile.media_texture and tile.upload_ring and tile.upload_ring.get_mapped():paint_ms=(time.monotonic()-mark)*1000
 w.get_frame_clock().connect('after-paint',painted);GLib.timeout_add(15,check)
try:app.connect('activate',activate);app.run([])
finally:
 release.set()
 if sync_thread:sync_thread.join(timeout=3)
 server.shutdown();server.server_close()
assert not errors
