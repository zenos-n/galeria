"""Album hover and confirmed delete through a loopback API; never production data."""
import os,sys,tempfile,time,subprocess
from pathlib import Path
from io import BytesIO
from http.server import ThreadingHTTPServer
from threading import Thread
assert os.environ.get('DISPLAY')==':91' and os.environ.get('GDK_BACKEND')=='x11','Run pointer checks only on private Xvfb :91'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=tempfile.TemporaryDirectory(prefix='galeria-albums-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
import gi
gi.require_version('GdkX11','4.0')
from gi.repository import GdkX11
from PIL import Image
from library import ImmichClient
from test_sharing import SharingFixture
from collections_ui import collection_view
from collection_widgets import menu_button
blob=BytesIO();Image.new('RGB',(100,100),'purple').save(blob,format='PNG')
SharingFixture.thumbnail=blob.getvalue();SharingFixture.requests=[];SharingFixture.album_count=1
server=ThreadingHTTPServer(('127.0.0.1',0),SharingFixture);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
client=ImmichClient(f'http://127.0.0.1:{server.server_port}');client.login('test@example.invalid','test-password')
app=Adw.Application(application_id='com.neg-zero.Galeria.AlbumActionsTest',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=0;start=time.monotonic();errors=[]
def walk(widget):
 yield widget
 child=widget.get_first_child()
 while child:yield from walk(child);child=child.get_next_sibling()
def delete_button(menu):
 return next(widget for widget in walk(menu.get_popover()) if isinstance(widget,Gtk.Button) and widget.get_label()=='Delete album…')
def shot():
 snap=Gtk.Snapshot();Gtk.WidgetPaintable.new(w).snapshot(snap,w.get_width(),w.get_height());node=snap.to_node()
 p=Path('/tmp/gallery-app-identification/album-single-hover.png');w.get_renderer().render_texture(node,Graphene.Rect().init(0,0,w.get_width(),w.get_height())).save_to_png(str(p))
 return Image.open(p)
def check():
 global phase,menu,opener,mark
 try:
  assert time.monotonic()-start<15,phase
  if phase==0:
   menus=[widget for widget in walk(w) if isinstance(widget,Gtk.MenuButton) and widget.get_tooltip_text()=='Collection actions']
   if not menus:return True
   menu=menus[0];opener=next(widget for widget in walk(w) if isinstance(widget,Gtk.Button) and widget.has_css_class('collection-open'))
   assert delete_button(menu)
   foreign=menu_button(w,'albums',{'id':'other','ownerId':'other','albumName':'Shared'},lambda:None)
   assert not any(isinstance(widget,Gtk.Button) and widget.get_label()=='Delete album…' for widget in walk(foreign.get_popover()))
   ok,bounds=opener.compute_bounds(w);assert ok
   subprocess.run([os.environ.get('GALERIA_XDOTOOL','/tmp/gallery-app-identification/xdotool/bin/xdotool'),'mousemove','--window',str(GdkX11.X11Surface.get_xid(w.get_surface())),str(round(bounds.get_x()+50)),str(round(bounds.get_y()+50))],check=True)
   mark=time.monotonic();phase=1
  elif phase==1 and time.monotonic()-mark>.35:
   assert opener.get_state_flags() & Gtk.StateFlags.PRELIGHT
   image=shot();ok,bounds=opener.compute_bounds(w);x=round(bounds.get_x()+4)
   inside=image.getpixel((x,round(bounds.get_y()+50)));outside=image.getpixel((x,round(bounds.get_y()+bounds.get_height()+14)))
   assert max(abs(a-b) for a,b in zip(inside,outside))<=3,(inside,outside)
   menu.popup();phase=20
  elif phase==20:
   delete_button(menu).emit('clicked');phase=21
  elif phase==21 and w.get_visible_dialog():
   dialog=w.get_visible_dialog();dialog.emit('response','cancel');dialog.close();phase=22
  elif phase==22 and not w.get_visible_dialog():
   assert not any(request[0]=='DELETE' for request in SharingFixture.requests)
   menu.popup();phase=23
  elif phase==23:
   delete_button(menu).emit('clicked');phase=24
  elif phase==24 and w.get_visible_dialog():
   dialog=w.get_visible_dialog();dialog.emit('response','delete');dialog.close();phase=2
  elif phase==2 and SharingFixture.album_count==0 and w.album_tree.children.get_n_items()==0:
   assert w.collection_cache['albums']==[] and w.collection_cache['sharing']==[]
   assert w.preferences['pins'][client.identity]==[]
   deletes=[request for request in SharingFixture.requests if request[0]=='DELETE']
   assert len(deletes)==1 and deletes[0][1]=='/api/albums/album',deletes
   assert w.stack.get_visible_child_name()=='collections'
   print('REAL POINTER: ONE ALBUM HOVER BACKGROUND; OWNER DELETE MENU; CANCEL NO REQUEST; CONFIRM ONLY ALBUM DELETE; CACHE/SIDEBAR/PINS REFRESH; MEDIA API UNTOUCHED PASSED',flush=True)
   w.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);w.close();app.quit();return False
 return True
def activate(app):
 global w
 Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
 css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
 w=GalleryWindow(app);w.set_default_size(1000,760);w.client=client;w.current_page='albums'
 albums=client.albums();w.album_tree.set_albums(albums);w.collection_cache.update(albums=albums,sharing=albums)
 w.preferences['pins']={client.identity:['album']};collection_view(w,'albums');w.present();GLib.timeout_add(100,check)
try:app.connect('activate',activate);app.run([])
finally:server.shutdown();server.server_close();thread.join()
assert not errors
