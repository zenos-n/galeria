"""Real clipboard image + Ctrl+V -> checksum preflight and multipart upload."""
import os,sys,tempfile,time,subprocess,threading,json,hashlib
from pathlib import Path
from io import BytesIO
from datetime import datetime
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from email.parser import BytesParser
from email.policy import default
assert os.environ.get('DISPLAY')==':91'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if '--source' not in sys.argv:
 root=tempfile.TemporaryDirectory(prefix='galeria-paste-')
 for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
from PIL import Image
if '--source' in sys.argv:
 Gtk.init();Gdk.Display.get_default().get_clipboard().set_content(Gdk.ContentProvider.new_for_value(GObject.Value(Gdk.Texture.__gtype__,Gdk.Texture.new_from_filename(sys.argv[-1]))));print('READY',flush=True);GLib.MainLoop().run();sys.exit()
gi.require_version('GdkX11','4.0')
from gi.repository import GdkX11
from library import MediaItem
from imaging import decode_image
photo=Path(root.name)/'clipboard.png';Image.new('RGBA',(31,23),(0,255,0,128)).save(photo)
producer=subprocess.Popen([sys.executable,__file__,'--source',str(photo)],stdout=subprocess.PIPE,text=True);assert producer.stdout.readline().strip()=='READY'
posts=[];checks=[];notices=[];completed=[];failure=False
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*_):pass
 def do_POST(self):
  body=self.rfile.read(int(self.headers['Content-Length']))
  if failure:self.send_response(500);self.end_headers();return
  message=BytesParser(policy=default).parsebytes(('Content-Type: '+self.headers['Content-Type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+body)
  data=next(part.get_payload(decode=True) for part in message.iter_parts() if part.get_param('name',header='content-disposition')=='assetData')
  assert hashlib.sha1(data).hexdigest()==self.headers['x-immich-checksum'];assert Image.open(BytesIO(data)).convert('RGBA').getpixel((0,0))==(0,255,0,128)
  posts.append(data);self.send_response(201);self.end_headers();self.wfile.write(json.dumps({'id':str(len(posts))}).encode())
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
class Client(ImmichClient):
 def __init__(self):super().__init__(f'http://127.0.0.1:{server.server_port}');self.token='fixture';self.user={'id':'fixture'};self.modern_search=True
 def request(self,path,body=None,**kwargs):
  assert path=='/assets/bulk-upload-check',path
  checksum=body['assets'][0]['checksum'];checks.append(checksum);assert body['assets'][0]['id'].startswith('pasted-image-')
  old=next((i for i,data in enumerate(posts,1) if hashlib.sha1(data).hexdigest()==checksum),None)
  return {'results':[{'action':'reject','assetId':str(old)} if old and not failure else {'action':'accept'}]}
app=Adw.Application(application_id='com.neg-zero.Galeria.PasteTest',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=0;start=time.monotonic();errors=[];tool='/tmp/gallery-app-identification/xdotool/bin/xdotool'
def paste():
 xid=str(GdkX11.X11Surface.get_xid(w.get_surface()));subprocess.run([tool,'windowfocus',xid,'key','--clearmodifiers','ctrl+v'],check=True)
def check():
 global phase,failure,entry,mark,before
 try:
  assert time.monotonic()-start<25,(phase,notices,len(posts))
  if phase==0 and w.get_mapped():w.mosaic.grab_focus();paste();phase=1
  elif phase==1 and completed:
   assert len(posts)==1 and len(checks)==1 and any('1 uploaded' in n for n in notices)
   w.mosaic.set_selection(True);paste();phase=2
  elif phase==2 and len(completed)==2:
   assert len(posts)==1 and len(checks)==2 and any('1 already saved' in n for n in notices)
   assert not w.uploads.get_visible();w.mosaic.set_selection(False);w.open_viewer(next(i for i,item in enumerate(w.media_items) if item.id=='fixture'));phase=3
  elif phase==3 and w.viewer.stage.progress==1:
   paste();phase=4
  elif phase==4 and len(completed)==3:
   assert len(posts)==1 and len(checks)==3
   w.viewer.close();phase=5
  elif phase==5 and w.viewer is None:
   w.get_clipboard().set('clipboard text');w.set_searching(True);w.search.entry.grab_focus();paste();phase=6
  elif phase==6 and w.search.entry.get_text()=='clipboard text':
   assert len(checks)==3
   w.set_searching(False);w.set_focus(None);paste();phase=7
  elif phase==7 and any('does not contain an image' in n for n in notices):
   assert len(checks)==3
   w.get_clipboard().set_content(Gdk.ContentProvider.new_for_value(GObject.Value(Gdk.Texture.__gtype__,Gdk.Texture.new_from_filename(str(photo)))));failure=True;paste();phase=8
  elif phase==8 and any(n.startswith('Upload failed') for n in notices):
   assert len(completed)==3 and len(posts)==1 and w.upload_cancel.is_set() and not w.uploads.get_visible(),notices
   # Late clipboard replies cannot upload to an account chosen after Ctrl+V.
   before=len(checks);w.paste_image();w.client=Client();mark=time.monotonic();phase=9
  elif phase==9 and time.monotonic()-mark>.3:
   assert len(checks)==before
   w.client=None;w.paste_image();assert notices[-1]=='Connect Immich to upload an image.'
   print('CROSS-PROCESS IMAGE CLIPBOARD/REAL CTRL+V -> PNG PIXELS+ALPHA/CHECKSUM/MULTIPART; DUPLICATE; SELECTION/FOCUS; NORMAL TEXT PASTE; NONIMAGE/FAILED UPLOAD/ACCOUNT SWITCH/LOCAL GUARDS PASSED',flush=True)
   w.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);w.close();app.quit();return False
 return True
def activate(app):
 global w
 css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
 w=GalleryWindow(app);w.set_default_size(1200,800);w.client=Client();w.notice=notices.append;w.upload_finished=lambda client:completed.append(client)
 GLib.source_remove(w.refresh_timer);w.refresh_timer=0
 item=MediaItem('fixture','clipboard.png',datetime.now(),31/23,path=str(photo));w.texture_cache[w.texture_key(item)]=w.texture_from_pixels(decode_image(photo));w.set_library_items([item]);w.search_library=lambda *args,**kwargs:None;w.present();GLib.timeout_add(35,check)
try:app.connect('activate',activate);app.run([])
finally:producer.terminate();producer.wait();server.shutdown();server.server_close()
assert not errors
