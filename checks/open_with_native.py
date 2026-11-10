"""Real desktop Exec: one library window, local focus, checked save on exit."""
import os,sys,time,tempfile,subprocess,threading,hashlib,json
from pathlib import Path
from datetime import datetime
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from email.parser import BytesParser
from email.policy import default
assert os.environ.get('DISPLAY')==':91'
sys.path.insert(0,os.environ.get('GALERIA_CHECK_SOURCE_ROOT',str(Path(__file__).resolve().parents[1])))
if '--desktop-client' not in sys.argv:
 root=tempfile.TemporaryDirectory(prefix='galeria-open-with-')
 for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
 runtime=Path(root.name)/'run';runtime.mkdir(mode=0o700);os.environ['XDG_RUNTIME_DIR']=str(runtime)
from app import *
from library import MediaItem
from session_store import preferences_write,PREFERENCES
from PIL import Image
import data_ui

def walk(widget):
 yield widget
 child=widget.get_first_child()
 while child:yield from walk(child);child=child.get_next_sibling()

class FixtureGallery(Gallery):
 def __init__(self):super().__init__();self.set_application_id('com.neg-zero.Galeria.OpenWithCheck')
 def do_startup(self):
  Gallery.do_startup(self);Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
if '--desktop-client' in sys.argv:sys.exit(FixtureGallery().run([sys.argv[0],*sys.argv[2:]]))

if '--cold-start' in sys.argv:
 from time import monotonic_ns
 path=Path(root.name)/'cold.png';Image.new('RGB',(100,70),'purple').save(path)
 preferences_write({'mode':'immich','remember':True,'server':'https://fixture.invalid/api','user_id':'fixture'})
 class Offline(ImmichClient):
  def request(self,*args,**kwargs):time.sleep(1.2);raise LibraryError('Fixture connection unavailable')
 data_ui.ImmichClient=Offline;data_ui.secret_get=lambda *args:'fixture'
 cold=FixtureGallery();paint=[]
 def added(_app,window):
  def mapped(window):
   def frame(*_):
    if not paint and any(isinstance(node,Gtk.Label) and node.get_mapped() and node.get_text()=='Opening file…' for node in walk(window)):
     paint.append((monotonic_ns()-int(os.environ['GALERIA_TEST_PROCESS_START_NS']))/1e6)
     print(json.dumps({'process_cold_open_feedback_ms':paint[0]}),flush=True);GLib.idle_add(cold.force_quit)
   window.get_frame_clock().connect('after-paint',frame)
  window.connect('map',mapped)
 cold.connect('window-added',added);GLib.timeout_add_seconds(4,cold.force_quit)
 cold.run([sys.argv[0],str(path)]);assert paint and paint[0]<400,paint;sys.exit()


folder=Path(root.name)/'device files';folder.mkdir()
photos=[folder/name for name in ('renamed duplicate.png','new photo.png','discard.png','quit.png')]
for path,color in zip(photos,['purple','orange','green','blue']):Image.new('RGB',(160,100),color).save(path)
mib=int(os.environ.get('GALERIA_OPEN_TEST_MIB','0'))
with photos[0].open('ab') as stream:stream.write(bytes(mib*1024*1024))
originals={path:path.read_bytes() for path in photos}
clip=folder/'clip.mp4';subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=purple:size=160x100:rate=10','-t','0.5','-pix_fmt','yuv420p','-threads','1',str(clip)],check=True)
assets={hashlib.sha1(originals[photos[0]]).hexdigest():'existing'};posts=[];checks=[];gates={'restore':threading.Event(),'check':threading.Event(),'save':threading.Event()};fail=[False];fail_upload=[False];rejected=[];restores=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*_):pass
 def do_POST(self):
  body=self.rfile.read(int(self.headers['Content-Length']));message=BytesParser(policy=default).parsebytes(('Content-Type: '+self.headers['Content-Type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+body)
  data=next(part.get_payload(decode=True) for part in message.iter_parts() if part.get_param('name',header='content-disposition')=='assetData')
  checksum=hashlib.sha1(data).hexdigest();assert checksum==self.headers['x-immich-checksum']
  if fail_upload[0]:rejected.append(data);self.send_response(500);self.end_headers();return
  posts.append(data)
  assert gates['save'].wait(10);asset=f'asset-{len(posts)}';assets[checksum]=asset
  self.send_response(201);self.end_headers();self.wfile.write(json.dumps({'id':asset}).encode())
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
user={'id':'fixture','name':'Fixture','email':'','profileImagePath':None,'profileChangedAt':None}
saved={'mode':'immich','remember':True,'server':f'http://127.0.0.1:{server.server_port}/api','user_id':'fixture','email':'','last_user':user,'modern_search':True,'folders':['/previous/device/folder']}
preferences_write(saved);before=PREFERENCES.read_bytes()
items=[MediaItem(str(i),'remote.png',datetime(2026,11,1),1.6) for i in range(int(os.environ.get('GALERIA_OPEN_TEST_ITEMS','40')))]
class Client(ImmichClient):
 def profile_image(self,**kwargs):return originals[photos[0]]
 def detect_version(self):pass
 def lock_session(self):pass
 def albums(self):return []
 def time_buckets(self,cached=False,**kwargs):return None if cached else [{'timeBucket':'2026-11-01','count':len(items)}]
 def time_bucket(self,*args,**kwargs):return items
 def image_bytes(self,*args,**kwargs):return originals[photos[0]]
 def search(self,*args,**kwargs):return items[:30],None
 def request(self,path,body=None,**kwargs):
  if path=='/users/me':restores.append(True);assert gates['restore'].wait(10);return user.copy()
  assert path=='/assets/bulk-upload-check',path
  checksum=body['assets'][0]['checksum'];checks.append(checksum)
  assert gates['check'].wait(10)
  if fail[0]:raise LibraryError('Fixture connection failed')
  asset=assets.get(checksum);return {'results':[{'action':'reject','assetId':asset} if asset else {'action':'accept'}]}
data_ui.ImmichClient=Client;data_ui.secret_get=lambda identity,kind:'fixture'
app=FixtureGallery();app.register(None)
cold_paints=[]
def added(_app,window):
 def mapped(window):
  window.get_frame_clock().connect('after-paint',lambda *_:cold_paints.append(time.monotonic()) if not cold_paints and any(isinstance(node,Gtk.Label) and node.get_mapped() and node.get_text()=='Opening file…' for node in walk(window)) else None)
 window.connect('map',mapped)
app.connect('window-added',added)
context=GLib.MainContext.default()
def pump(until,timeout=15):
 deadline=time.monotonic()+timeout
 while not until():
  assert time.monotonic()<deadline,'Timed out'
  context.iteration(False);time.sleep(.004)
 for _ in range(3):context.iteration(False)
def windows():return [w for w in app.get_windows() if isinstance(w,GalleryWindow)]
desktop=Path(root.name)/'galeria-open-with.desktop'
desktop.write_text('[Desktop Entry]\nType=Application\nName=Galeria fixture\nExec='+GLib.shell_quote(sys.executable)+' '+GLib.shell_quote(__file__)+' --desktop-client %U\nTerminal=false\nMimeType=image/png;video/mp4;\n')
launcher=Gio.DesktopAppInfo.new_from_filename(str(desktop));assert launcher
def launch(*paths):assert launcher.launch([Gio.File.new_for_path(str(path)) for path in paths],None)
def focused(path):
 pump(lambda:app.window and app.window.viewer and app.window.viewer.source.media_item.path==str(path) and app.window.viewer.stage.progress==1)
 assert windows()==[app.window] and app.window.viewer.device_file
 return app.window.viewer

def prompt(v,heading='Save to Immich?'):
 pump(lambda:v.file_exit.dialog is not None and v.file_exit.dialog.get_mapped());dialog=v.file_exit.dialog
 assert dialog.get_heading()==heading
 return dialog

def respond(dialog,value):dialog.emit('response',value);dialog.close()

def painted(window,predicate,action,timeout=.4):
 times=[];clock=window.get_frame_clock()
 handler=clock.connect('after-paint',lambda *_:times.append(time.monotonic()) if predicate() and not times else None)
 mark=time.monotonic();action();pump(lambda:bool(times),timeout);clock.disconnect(handler)
 elapsed=(times[0]-mark)*1000;assert elapsed<400,elapsed;return elapsed

try:
 mark=time.monotonic();launch(photos[0]);pump(lambda:app.window is not None and app.window.get_mapped(),.4);w=app.window
 pump(lambda:bool(cold_paints),.4)
 cold_ms=(cold_paints[0]-mark)*1000;assert cold_ms<400,cold_ms
 assert windows()==[w] and not w.client and not posts
 cold_beats=[time.monotonic()];cold_timer=GLib.timeout_add(16,lambda:(cold_beats.append(time.monotonic()),True)[1])
 gates['restore'].set();v=focused(photos[0]);pump(lambda:w.client is not None and w.media_items and w.media_items[0].id=='0' and not w.media_items[0].metadata.get('placeholder'))
 GLib.source_remove(cold_timer);cold_gap=max(b-a for a,b in zip(cold_beats,cold_beats[1:]))*1000;assert cold_gap<400,cold_gap
 assert w.avatar.get_text()=='Fixture' and w.current_page=='library' and w.mosaic.hidden_tile is None
 assert not v.favorite.get_visible() and not v.archive.get_visible() and not v.lock.get_visible() and not v.share.get_visible()
 assert PREFERENCES.read_bytes()==before and len(restores)==1
 GLib.source_remove(w.refresh_timer);w.refresh_timer=0
 client=w.client;grid=w.mosaic;media=w.media_items
 check_ms=painted(w,lambda:v.title.get_subtitle()=='Checking Immich…',v.close)
 pump(lambda:len(checks)==1);assert v.file_exit.dialog is None and w.viewer is v and not posts
 beats=[];timer=GLib.timeout_add(16,lambda:(beats.append(time.monotonic()),True)[1]);until=time.monotonic()+.7;pump(lambda:time.monotonic()>=until);GLib.source_remove(timer)
 assert len(beats)>15 and max(b-a for a,b in zip(beats,beats[1:]))<.4
 gates['check'].set();pump(lambda:w.viewer is None);assert not posts and v.file_exit.dialog is None
 assert w.client is client and w.mosaic is grid and w.media_items is media

 launch(photos[1]);v=focused(photos[1]);v.close();dialog=prompt(v)
 assert checks[-1]==hashlib.sha1(originals[photos[1]]).hexdigest() and not posts
 respond(dialog,'cancel');pump(lambda:v.file_exit.dialog is None);assert w.viewer is v and not posts
 v.close();dialog=prompt(v);save_ms=painted(w,lambda:v.title.get_subtitle()=='Saving to Immich…',lambda:respond(dialog,'save'))
 pump(lambda:len(posts)==1);assert posts==[originals[photos[1]]] and w.viewer is v
 assert any(item.metadata.get('upload_state')=='uploading' for item in w.media_items)
 gates['save'].set();pump(lambda:w.viewer is None);assert any(item.id=='asset-1' for item in w.media_items)
 launch(photos[1]);v=focused(photos[1]);v.close();pump(lambda:w.viewer is None);assert len(posts)==1

 launch(photos[2]);v=focused(photos[2]);v.close();fail_upload[0]=True;respond(prompt(v),'save')
 pump(lambda:len(rejected)==1 and not v.file_exit.busy)
 assert w.viewer is v and not v.file_exit.resolved and rejected==[originals[photos[2]]]
 assert not any(item.filename==photos[2].name for item in w.media_items)
 fail_upload[0]=False;v.close();respond(prompt(v),'discard');pump(lambda:w.viewer is None)

 launch(photos[2],clip);v=focused(photos[2]);fail[0]=True;v.close();dialog=prompt(v,'Could not check Immich');assert len(posts)==1
 fail[0]=False;respond(dialog,'save');dialog=prompt(v);respond(dialog,'discard');v=focused(clip)
 assert v.source.media_item.kind=='VIDEO' and v.stage.video_player
 v.close();respond(prompt(v),'discard');pump(lambda:w.viewer is None)
 row=w.rows['photos'];row.get_parent().emit('row-activated',row)
 pump(lambda:w.current_page=='photos' and not w.loading_more);assert windows()==[w] and w.client is client and len(restores)==1
 assert PREFERENCES.read_bytes()==before and all(path.read_bytes()==data for path,data in originals.items())

 app.set_background(True);launch(photos[2]);v=focused(photos[2]);w.close();respond(prompt(v),'discard');pump(lambda:not w.get_visible())
 assert app.window is w and w.viewer is None and w.client is client
 launch(photos[3]);v=focused(photos[3]);app.force_quit();dialog=prompt(v);respond(dialog,'cancel');pump(lambda:v.file_exit.dialog is None)
 assert not app.quitting and windows()==[w] and w.viewer is v
 app.force_quit();respond(prompt(v),'save');pump(lambda:not windows());assert w.data_stopped
 assert posts==[originals[photos[1]],originals[photos[3]]] and PREFERENCES.read_bytes()==before
 print(json.dumps({'cold_open_feedback_ms':cold_ms,'exit_check_feedback_ms':check_ms,'save_feedback_ms':save_ms,'library_items':len(items),'file_padding_mib':mib,'cold_restore_heartbeat_ms':cold_gap,'slow_check_heartbeat_ms':max(b-a for a,b in zip(beats,beats[1:]))*1000}),flush=True)
 print('REAL DESKTOP OPEN WITH: SAME RESTORED IMMICH WINDOW/LIBRARY; NO SIDEBAR WINDOW; DUPLICATE SKIP; CHECK BEFORE PROMPT; CANCEL/RETRY/DISCARD/SAVE ORIGINAL; IMAGE/VIDEO/BATCH; WINDOW/BACKGROUND/QUIT GUARDS PASSED',flush=True)
finally:
 for gate in gates.values():gate.set()
 for w in windows():w.stop_data();w.destroy()
 app.quit();server.shutdown();server.server_close()
