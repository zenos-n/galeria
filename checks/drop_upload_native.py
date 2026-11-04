"""Actual cross-window GDK file drag, native review click and multipart uploads."""
import os,sys,tempfile,time,subprocess,threading,json,hashlib
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from email.parser import BytesParser
from email.policy import default
assert os.environ.get('DISPLAY')==':91'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=tempfile.TemporaryDirectory(prefix='galeria-drop-upload-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
gi.require_version('GdkX11','4.0')
from gi.repository import GdkX11,GObject
from PIL import Image
from library import ImmichClient
first=Path(root.name)/'photo.png';folder=Path(root.name)/'folder';folder.mkdir()
Image.new('RGB',(30,20),'purple').save(first);(folder/'duplicate.png').write_bytes(first.read_bytes());Image.new('RGB',(20,30),'blue').save(folder/'other.png')
originals={path:path.read_bytes() for path in (first,folder/'duplicate.png',folder/'other.png')};posts=[];checks=[];notices=[];completed=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*_):pass
 def do_POST(self):
  body=self.rfile.read(int(self.headers['Content-Length']));message=BytesParser(policy=default).parsebytes(('Content-Type: '+self.headers['Content-Type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+body)
  data=next(part.get_payload(decode=True) for part in message.iter_parts() if part.get_param('name',header='content-disposition')=='assetData')
  assert hashlib.sha1(data).hexdigest()==self.headers['x-immich-checksum'];posts.append(data)
  self.send_response(201);self.end_headers();self.wfile.write(json.dumps({'id':str(len(posts))}).encode())
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
class Client(ImmichClient):
 def __init__(self):super().__init__(f'http://127.0.0.1:{server.server_port}');self.token='fixture';self.user={'id':'fixture'};self.modern_search=True
 def request(self,path,body=None,**kwargs):
  assert path=='/assets/bulk-upload-check',path
  checksum=body['assets'][0]['checksum'];checks.append(checksum)
  old=next((i for i,data in enumerate(posts,1) if hashlib.sha1(data).hexdigest()==checksum),None)
  return {'results':[{'action':'reject','assetId':str(old)} if old else {'action':'accept'}]}
app=Adw.Application(application_id='com.neg-zero.Galeria.DropUploadTest',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=0;start=time.monotonic();errors=[];tool='/tmp/gallery-app-identification/xdotool/bin/xdotool'
def click(widget):
 native=widget.get_native();ok,bounds=widget.compute_bounds(native);assert ok;dx,dy=native.get_surface_transform();xid=str(GdkX11.X11Surface.get_xid(native.get_surface()))
 subprocess.run([tool,'windowraise',xid,'mousemove','--window',xid,str(round(bounds.get_x()+bounds.get_width()/2+dx)),str(round(bounds.get_y()+bounds.get_height()/2+dy)),'click','1'],check=True)
def walk(widget):
 yield widget
 child=widget.get_first_child()
 while child:yield from walk(child);child=child.get_next_sibling()
def check():
 global phase,drag
 try:
  assert time.monotonic()-start<15,(phase,len(posts),checks,notices)
  if phase==0 and w.get_mapped() and source.get_mapped():
   main=str(GdkX11.X11Surface.get_xid(w.get_surface()));sid=str(GdkX11.X11Surface.get_xid(source.get_surface()))
   subprocess.run([tool,'windowmove',main,'0','0','windowmove',sid,'1260','40'],check=True)
   drag=subprocess.Popen([tool,'windowraise',sid,'mousemove','--window',sid,'80','60','mousedown','1','sleep','.2','mousemove','--window',sid,'110','65','sleep','.1','mousemove','--window',main,'550','300','sleep','.4','mouseup','1']);phase=1
  elif phase==1 and w.dialog and w.dialog.get_visible():
   assert w.dialog.get_title()=='Upload to Immich';button=next(widget for widget in walk(w.dialog) if isinstance(widget,Gtk.Button) and widget.get_label()=='Upload');click(button);phase=2
  elif phase==2 and completed:
   assert len(posts)==2 and len(checks)==3 and any('2 uploaded' in notice and '1 already saved' in notice for notice in notices),(len(posts),checks,notices)
   assert {hashlib.sha1(data).hexdigest() for data in posts}=={hashlib.sha1(data).hexdigest() for data in originals.values()}
   assert all(path.read_bytes()==data for path,data in originals.items()) and not w.uploads.get_visible()
   print('REAL CROSS-WINDOW FILE/FOLDER DROP -> NATIVE UPLOAD REVIEW -> CHECKSUM PREFLIGHT/MULTIPART IMMICH UPLOAD; DUPLICATE SKIPPED; SOURCE BYTES RETAINED PASSED',flush=True)
   source.close();w.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);source.close();w.close();app.quit();return False
 return True
def activate(app):
 global w,source
 css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
 w=GalleryWindow(app);w.set_default_size(1200,800);w.client=Client();w.notice=notices.append;w.upload_finished=lambda client:completed.append(client);w.present()
 GLib.source_remove(w.refresh_timer);w.refresh_timer=0
 source=Gtk.ApplicationWindow(application=app,title='File source',default_width=220,default_height=160)
 button=Gtk.Button(label='Drag files');source.set_child(button);drag=Gtk.DragSource(actions=Gdk.DragAction.COPY)
 provider=Gdk.ContentProvider.new_for_value(GObject.Value(Gdk.FileList.__gtype__,Gdk.FileList.new_from_list([Gio.File.new_for_path(str(first)),Gio.File.new_for_path(str(folder))])))
 drag.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
 drag.set_content(provider);button.add_controller(drag);source.present();GLib.timeout_add(50,check)
app.connect('activate',activate);app.run([]);server.shutdown();server.server_close();assert not errors
