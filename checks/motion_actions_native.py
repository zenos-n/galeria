"""Private-display regression for interrupted folds, RAM textures and media actions."""
import os,sys,tempfile,time
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=tempfile.TemporaryDirectory(prefix='galeria-motion-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
from library import MediaItem
from PIL import Image
from imaging import decode_image
from copy_ui import copy_media,media_menu
from copy_ui import clear_locked_clipboard
from io import BytesIO
path=Path(root.name)/'original.png';Image.new('RGB',(80,50),'purple').save(path)
items=[MediaItem(str(i),'original.png',datetime(2026-i//40//12,12-(i//40)%12,20-i%20),1.6,path=str(path)) for i in range(480)]
class Client:
 refresh_serial=0;locked_until=0;server_lock_pending=False;identity='fixture'
 def __init__(self):self.calls=[]
 def update_assets(self,ids,body):self.calls.append((ids,body))
 def trash_assets(self,ids):self.calls.append((ids,'trash'))
class LockedClient(Client):
 def image_bytes(self,*_):return path.read_bytes()
 def media_cache(self):raise AssertionError('Locked copy must not use ordinary storage')
 def check_original_access(self,*_):pass
 def open_original(self,*_):
  stream=BytesIO(b'locked original');stream.headers={'Content-Length':'15'};return stream
app=Adw.Application(application_id='com.neg-zero.Galeria.MotionActionsTest',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=0;start=time.monotonic();errors=[];client=Client()
def check():
 global phase
 try:
  assert time.monotonic()-start<25,phase
  m=window.mosaic
  if phase==0 and not window.loading_more and m.rendered:
   window.switcher.set_active_name('months');phase=1
  elif phase==1 and not m.tick:
   assert any(tile.media_texture is None for tile in m.tiles)
   window.switcher.set_active_name('all')
   assert m.tier_images and all(texture.get_intrinsic_width()>1 for texture,_,_ in m.tier_images)
   phase=2
  elif phase==2 and not m.tick:
   assert all(tile.media_texture for tile in m.active_widgets & m.tile_set)
   window.switcher.set_active_name('years');phase=3
  elif phase==3 and not m.tick:
   window.switcher.set_active_name('all');assert all(texture.get_intrinsic_width()>1 for texture,_,_ in m.tier_images);phase=4
  elif phase==4 and not m.tick:
   window.switcher.set_active_name('months');phase=5
  elif phase==5 and not m.tick:m.expand_month(m.months[0][0]);phase=6
  elif phase==6 and not m.tick:
   window.scroller.get_vadjustment().set_value(500)
   m.expand_month(m.months[0][0]);phase=7
  elif phase==7 and .1<m.p<.9:
   window.set_library_items(window.media_items,append=True);m=window.mosaic
   tiles=m.from_map.keys() & m.tile_set;assert tiles
   assert all(m.panel_month in m.folder_membership.get(tile,set()) for tile in tiles)
   phase=8
  elif phase==8 and not m.tick:
   assert not (m.active_widgets & m.tile_set)
   window.switcher.set_active_name('all');phase=9
  elif phase==9 and not m.tick:
   copy_media(window,items[0]);phase=10
  elif phase==10 and window.get_clipboard().get_content():
   formats=window.get_clipboard().get_formats()
   assert formats.contain_gtype(Gdk.Texture.__gtype__) and formats.contain_gtype(Gdk.FileList.__gtype__),formats.to_string()
   media_menu(window,m,items[0],30,60)
   window.client=client;m.set_selection(True);m.toggle(0);window.selected_action('archive');phase=11
  elif phase==11 and len(window.media_items)==479 and not window.loading_more:
   assert client.calls[-1][1]=={'visibility':'archive'}
   window.open_viewer(0);phase=12
  elif phase==12 and window.viewer.stage.progress==1:
   window.viewer.archive.emit('clicked');phase=13
  elif phase==13 and window.viewer is None and len(window.media_items)==478:
   window.open_viewer(0);phase=14
  elif phase==14 and window.viewer.stage.progress==1:
   window.viewer.trash.emit('clicked');window.get_visible_dialog().emit('response','trash');phase=15
  elif phase==15 and window.viewer is None and len(window.media_items)==477:
   assert client.calls[-1][1]=='trash';assert path.exists()
   window.client=LockedClient();window.get_clipboard().set_content(None)
   copy_media(window,MediaItem('locked','locked.png',datetime.now(),metadata={'visibility':'locked'}));phase=16
  elif phase==16 and getattr(window,'locked_clipboard',None):
   assert window.get_clipboard().get_formats().contain_gtype(Gdk.Texture.__gtype__)
   clear_locked_clipboard(window);assert window.get_clipboard().get_content() is None
   copy_media(window,MediaItem('locked-video','locked.mp4',datetime.now(),kind='VIDEO',metadata={'visibility':'locked'}));phase=17
  elif phase==17 and getattr(window,'locked_clipboard',None):
   folder=Path(window.locked_clipboard[1].name);assert (folder/'locked.mp4').read_bytes()==b'locked original'
   clear_locked_clipboard(window);assert not folder.exists() and window.get_clipboard().get_content() is None
   print('MONTH/YEAR -> ALL USES RAM PIXELS; INTERRUPTED FOLD/REBUILD CLIPS ALL PHOTO ROWS; CLOSED FOLDER HAS NO PHOTO CELLS; CLIPBOARD TEXTURE/FILE; BULK/VIEWER ARCHIVE; VIEWER TRASH PASSED',flush=True)
   window.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);window.close();app.quit();return False
 return True
def activate(app):
 global window
 css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
 window=GalleryWindow(app);window.set_default_size(1400,850);window.present()
 GLib.source_remove(window.refresh_timer);window.refresh_timer=0
 window.library_mode='local';window.local_items=items
 texture=window.texture_from_pixels(decode_image(path))
 for item in items:window.texture_cache[window.texture_key(item)]=texture
 window.set_library_items(items);GLib.timeout_add(20,check)
app.connect('activate',activate);app.run([])
assert not errors
