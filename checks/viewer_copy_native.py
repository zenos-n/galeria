"""Real private-display menu clicks and cross-process clipboard reads."""
import os,sys,tempfile,time,subprocess,json
from io import BytesIO
from pathlib import Path
from datetime import datetime
assert os.environ.get('DISPLAY')==':91'
wayland=os.environ.get('GDK_BACKEND')=='wayland'
if wayland:assert os.environ.get('XDG_RUNTIME_DIR')=='/tmp/gallery-app-identification/weston-runtime'
if '--clipboard-read' in sys.argv:
 import gi
 gi.require_version('Gtk','4.0')
 gi.require_version('Gdk','4.0')
 from gi.repository import Gdk,GLib,Gtk
 Gtk.init();loop=GLib.MainLoop();result={}
 clipboard=Gdk.Display.get_default().get_clipboard()
 def ready(clipboard,value):
  try:
   texture=clipboard.read_texture_finish(value);result['size']=[texture.get_width(),texture.get_height()]
   result['has_files']=clipboard.get_formats().contain_gtype(Gdk.FileList.__gtype__);loop.quit()
  except Exception as error:result['error']=str(error);loop.quit()
 def files(clipboard,value):
  try:result['files']=[file.get_path() for file in clipboard.read_value_finish(value).get_files()]
  except Exception as error:result['error']=str(error)
  loop.quit()
 receiver=Gtk.Window(title='Clipboard receiver');receiver.fullscreen();receiver.present()
 GLib.timeout_add(250,lambda:(clipboard.read_texture_async(None,ready),False)[1])
 GLib.timeout_add_seconds(5,lambda:(result.update(error='Clipboard read timed out'),loop.quit(),False)[-1]);loop.run()
 Path(sys.argv[-1]).write_text(json.dumps(result));sys.exit(1 if 'error' in result else 0)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=tempfile.TemporaryDirectory(prefix='galeria-viewer-copy-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
if not wayland:
 gi.require_version('GdkX11','4.0')
 from gi.repository import GdkX11
from PIL import Image
from library import MediaItem
from imaging import decode_image
from copy_ui import clear_locked_clipboard
path=Path(root.name)/'photo.png';Image.new('RGB',(120,80),'purple').save(path)
original=b'fixture original in a format Pillow cannot decode'
items=[MediaItem('local','photo.png',datetime(2026,11,2),1.5,path=str(path)),
       MediaItem('remote','phone.heic',datetime(2026,11,1),1.5,metadata={'visibility':'timeline'})]
class Client(ImmichClient):
 def __init__(self):super().__init__('https://fixture.invalid');self.user={'id':'fixture'};self.token='fixture'
 def image_bytes(self,*_args,**_kwargs):return path.read_bytes()
 def open_original(self,item):
  stream=BytesIO(original);stream.headers={'Content-Length':str(len(original))};return stream
app=Adw.Application(application_id='com.neg-zero.Galeria.ViewerCopyTest',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=0;start=time.monotonic();errors=[];notices=[];downloads=[];shares=[];which=0;mark=0
def walk(widget):
 yield widget
 child=widget.get_first_child()
 while child:yield from walk(child);child=child.get_next_sibling()
def click(widget,number):
 native=widget.get_native();ok,bounds=widget.compute_bounds(native);assert ok
 x=bounds.get_x()+bounds.get_width()/2;y=bounds.get_y()+bounds.get_height()/2
 tool=os.environ.get('GALERIA_XDOTOOL','/tmp/gallery-app-identification/xdotool/bin/xdotool')
 if wayland:
  xid=subprocess.check_output([tool,'search','--class','weston'],text=True).splitlines()[0]
  surface=native.get_surface()
  while isinstance(surface,Gdk.Popup):x+=surface.get_position_x();y+=surface.get_position_y();surface=surface.get_parent()
 else:xid=str(GdkX11.X11Surface.get_xid(native.get_surface()))
 subprocess.run([tool,'windowraise',xid,'mousemove','--window',xid,str(round(x)),str(round(y)),'click',str(number)],check=True)
def check():
 global phase,mark,reader,which
 try:
  assert time.monotonic()-start<30,(phase,notices)
  if phase==0 and not w.loading_more and w.mosaic.rendered:
   w.open_viewer(0);phase=1
  elif phase==1 and w.viewer.stage.progress==1 and not w.viewer.media_stack.get_transition_running() and time.monotonic()-mark>.35:
   click(w.viewer.stage.picture,3);phase=2
  elif phase==2:
   popover=next((widget for widget in walk(w.viewer) if isinstance(widget,Gtk.Popover) and widget.get_visible()),None)
   if not popover:return True
   button=next(widget for widget in walk(popover) if isinstance(widget,Gtk.Button) and widget.get_label()=='Copy media')
   click(button,1);mark=time.monotonic();phase=3
  elif phase==3 and time.monotonic()-mark>.5:
   assert w.viewer and w.get_clipboard().get_content(),notices
   reader=subprocess.Popen([sys.executable,__file__,'--clipboard-read',root.name+'/read.json']);phase=4
  elif phase==4 and reader.poll() is not None:
   result=json.loads(Path(root.name+'/read.json').read_text());assert reader.returncode==0,result
   assert result['size']==[120,80] and not result['has_files'],result
   if which==0:
    which=1;w.get_clipboard().set_content(None);w.viewer.move(1);mark=time.monotonic();phase=1;return True
   click(w.viewer.stage.picture,1);keys('shift+d');phase=5
  elif phase==5 and downloads:
   assert downloads==[['remote']],downloads
   w.viewer.set_editing(True)
   categories=w.viewer.editor_categories
   assert [categories.get_toggle(i).get_name() for i in range(categories.get_n_toggles())]==['Crop','Adjust','Markup']
   assert w.viewer.editor_stack.get_pages().get_n_items()==3 and categories.get_active_name()=='Crop'
   categories.set_active_name('Adjust');phase=6
  elif phase==6 and w.viewer.editor.get_child_revealed():
   contrast=next(widget for widget in walk(w.viewer.editor) if isinstance(widget,Gtk.ToggleButton) and widget.get_label()=='Contrast')
   click(contrast,1);mark=time.monotonic();phase=7
  elif phase==7 and time.monotonic()-mark>.2:
   assert next(widget for widget in walk(w.viewer.editor) if isinstance(widget,Gtk.ToggleButton) and widget.get_label()=='Contrast').get_active()
   snap=Gtk.Snapshot();Gtk.WidgetPaintable.new(w).snapshot(snap,w.get_width(),w.get_height());node=snap.to_node()
   w.get_renderer().render_texture(node,Graphene.Rect().init(0,0,w.get_width(),w.get_height())).save_to_png('/tmp/gallery-app-identification/editor-contrast-0113.png')
   keys('shift+d');mark=time.monotonic();phase=70
  elif phase==70 and time.monotonic()-mark>.15:
   assert downloads==[['remote']],downloads
   w.viewer.set_editing(False);w.viewer.close();phase=8
  elif phase==8 and w.viewer is None:
   w.mosaic.set_selection(True);w.mosaic.selected={0,1};w.mosaic.update_selection()
   w.get_clipboard().set_content(None);click(w.mosaic.tiles[0].get_child(),3);phase=80
  elif phase==80:
   context=next((widget for widget in walk(w.mosaic) if isinstance(widget,Gtk.Popover) and widget.get_visible()),None)
   if not context:return True
   click(next(widget for widget in walk(context) if isinstance(widget,Gtk.Button) and widget.get_label()=='Copy media'),1)
   mark=time.monotonic();phase=81
  elif phase==81 and time.monotonic()-mark>.2:
   keys('shift+d');phase=9
  elif phase==9 and len(downloads)>1:
   assert downloads==[['remote'],['local','remote']],downloads
   assert w.get_clipboard().get_content()
   assert all(w.hamburger_menu.get_item_attribute_value(i,'action',None).unpack()!='app.quit' for i in range(w.hamburger_menu.get_n_items()))
   assert 'Image copied.' in notices
   import sharing_ui
   sharing_ui.share_media=lambda window,items:shares.append([item.id for item in items])
   w.mosaic.set_selection(False);w.open_viewer(0);phase=10
  elif phase==10 and w.viewer.stage.progress==1:
   click(w.viewer.stage.picture,3);phase=11
  elif phase==11:
   context=next((widget for widget in walk(w.viewer) if isinstance(widget,Gtk.Popover) and widget.get_visible()),None)
   if not context:return True
   click(next(widget for widget in walk(context) if isinstance(widget,Gtk.Button) and widget.get_label()=='Share…'),1);phase=12
  elif phase==12 and shares:
   assert shares==[['local']],shares
   from copy_ui import media_menu
   video=MediaItem('video','movie.mp4',datetime(2026,11,1),1.5,kind='VIDEO')
   context=media_menu(w,w.viewer,video,50,150)
   labels=[widget.get_label() for widget in walk(context) if isinstance(widget,Gtk.Button)]
   assert 'Copy media' not in labels and 'Share…' in labels,labels
   phase=13
  elif phase==13:
   context=next((widget for widget in walk(w.viewer) if isinstance(widget,Gtk.Popover) and widget.get_visible()),None)
   if not context or not context.get_mapped():return True
   click(next(widget for widget in walk(context) if isinstance(widget,Gtk.Button) and widget.get_label()=='Share…'),1);phase=14
  elif phase==14 and len(shares)==2:
   assert shares==[['local'],['video']],shares
   print('REAL EXPANDED/GRID COPY; CROSS-PROCESS IMAGE-ONLY READS INCLUDING UNDECODABLE ORIGINAL; SHIFT+D CURRENT/SELECTION; IMAGE/VIDEO CONTEXT SHARE; VIDEO COPY ABSENT; PHOTO CROP/ADJUST/MARKUP ONLY; NO QUIT MENU PASSED',flush=True)
   w.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);w.close();app.quit();return False
 return True
def keys(value):
 tool=os.environ.get('GALERIA_XDOTOOL','/tmp/gallery-app-identification/xdotool/bin/xdotool')
 xid=subprocess.check_output([tool,'search','--class','weston'],text=True).splitlines()[0] if wayland else str(GdkX11.X11Surface.get_xid(w.get_surface()))
 subprocess.run([tool,'windowfocus',xid,'key',value],check=True)
def activate(app):
 global w
 css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
 w=GalleryWindow(app);w.set_default_size(1100,760);w.present();w.notice=lambda message:notices.append(message)
 w.client=Client();w.download_items=lambda values:downloads.append([item.id for item in values])
 if wayland:w.fullscreen()
 GLib.source_remove(w.refresh_timer);w.refresh_timer=0
 w.library_mode='local';w.local_items=items
 w.texture_cache[w.texture_key(items[0])]=w.texture_from_pixels(decode_image(path));w.set_library_items(items)
 GLib.timeout_add(40,check)
app.connect('activate',activate);app.run([])
assert not errors
