"""Real wheel/Space input, simulated pinch, player loop/replay and favorite writes."""
import os,sys,tempfile,time,subprocess
from pathlib import Path
from datetime import datetime
assert os.environ.get('DISPLAY')==':91'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=tempfile.TemporaryDirectory(prefix='galeria-viewer-controls-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
gi.require_version('GdkX11','4.0');gi.require_version('Clapper','0.0')
from gi.repository import GdkX11,Clapper
from library import MediaItem
from session_store import preferences_read
from PIL import Image
from imaging import decode_image
image=Path(root.name)/'photo.png';Image.new('RGB',(320,240),'purple').save(image)
video=Path(root.name)/'clip.mp4';subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc=size=160x90:rate=15','-t','1.2','-pix_fmt','yuv420p','-threads','1',str(video)],check=True)
items=[MediaItem('photo','photo.png',datetime(2026,11,4),4/3,path=str(image)),MediaItem('video','clip.mp4',datetime(2026,11,3),16/9,'VIDEO',str(video))]
class Client:
 identity='fixture';refresh_serial=0;locked_until=0;server_lock_pending=False
 def __init__(self):self.calls=[]
 def update_assets(self,ids,fields):self.calls.append((ids,fields))
client=Client();app=Adw.Application(application_id='com.neg-zero.Galeria.ViewerControls',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=0;start=time.monotonic();errors=[];mark=0;tool='/tmp/gallery-app-identification/xdotool/bin/xdotool'
def keys(key):
 xid=str(GdkX11.X11Surface.get_xid(w.get_surface()));subprocess.run([tool,'windowfocus',xid,'key',key],check=True)
def check():
 global phase,mark,width,zoom,player,positions
 try:
  assert time.monotonic()-start<22,(phase,w.viewer.stage.video_player.player.get_state() if w.viewer and w.viewer.stage.video_player else None)
  if phase==0 and not w.loading_more and w.mosaic.rendered:w.open_viewer(0);phase=1
  elif phase==1 and w.viewer.stage.progress==1:
   v=w.viewer;assert v.favorite.get_sensitive();v.favorite.set_active(True);phase=2
  elif phase==2 and client.calls:
   v=w.viewer;assert client.calls==[(['photo'],{'isFavorite':True})] and v.source.media_item.metadata['isFavorite']
   assert v.favorite.get_icon_name()=='starred-symbolic';v.favorite.set_active(False);phase=3
  elif phase==3 and len(client.calls)==2:
   v=w.viewer;assert client.calls[-1][1]=={'isFavorite':False}
   width=v.stage.picture.get_width();ok,bounds=v.stage.picture.compute_bounds(w);assert ok
   dx,dy=w.get_surface_transform();xid=str(GdkX11.X11Surface.get_xid(w.get_surface()))
   subprocess.run([tool,'mousemove','--window',xid,str(round(bounds.get_x()+bounds.get_width()*.65+dx)),str(round(bounds.get_y()+bounds.get_height()*.5+dy)),'click','4'],check=True)
   mark=time.monotonic();phase=4
  elif phase==4 and time.monotonic()-mark>.1:
   v=w.viewer;assert v.stage.zoom>1 and v.stage.picture.get_width()==width
   class Pinch:
    def get_bounding_box_center(self):return True,v.stage.get_width()*.65,v.stage.get_height()*.5
   pinch=Pinch();v.zoom_controls.pinch_begin(pinch);v.zoom_controls.pinch(pinch,2);assert v.stage.zoom>2
   v.zoom_controls.pan_start=(v.stage.pan_x,v.stage.pan_y);v.zoom_controls.pan(None,200,100);assert v.stage.pan_x or v.stage.pan_y
   v.zoom_controls.reset();assert v.stage.zoom==1 and v.stage.pan_x==v.stage.pan_y==0
   v.move(1);phase=5
  elif phase==5 and w.viewer.stage.progress==1 and w.viewer.stage.video_player and w.viewer.stage.video_player.player.get_state()==Clapper.PlayerState.PLAYING:
   player=w.viewer.stage.video_player
   popover=player.loop_switch.get_parent()
   while not isinstance(popover,Gtk.PopoverMenu):popover=popover.get_parent()
   menu=popover.get_menu_model().get_item_link(0,Gio.MENU_LINK_SECTION)
   assert menu.get_item_attribute_value(1,'custom',None).get_string()=='galeria-loop'
   assert [menu.get_item_attribute_value(i,'label',None).get_string() for i in (2,3)]==['Audio','Subtitles']
   w.viewer.close_button.grab_focus();keys('space');mark=time.monotonic();phase=6
  elif phase==6 and time.monotonic()-mark>.15:
   assert w.viewer is not None and player.player.get_state()==Clapper.PlayerState.PAUSED
   keys('space');phase=7
  elif phase==7 and player.player.get_state()==Clapper.PlayerState.PLAYING:
   player.loop_switch.set_active(True)
   assert preferences_read()['video_loop'] is True
   from video_ui import VideoPlayer
   other=VideoPlayer(video.as_uri(),w)
   assert other.loop_switch.get_active() and other.player.get_queue().get_progression_mode()==Clapper.QueueProgressionMode.REPEAT_ITEM
   other.stop()
   player.player.seek(1.05);mark=time.monotonic();positions=[];phase=8
  elif phase==8:
   positions.append(player.player.get_position())
   if time.monotonic()-mark<.65:return True
   assert player.player.get_state()==Clapper.PlayerState.PLAYING and any(value<.5 for value in positions),positions
   player.loop_switch.set_active(False);assert preferences_read()['video_loop'] is False;player.player.seek(1.1);mark=time.monotonic();phase=9
  elif phase==9 and time.monotonic()-mark>.4:
   assert player.end_replay.get_visible(),(player.player.get_state(),player.player.get_position())
   player.end_replay.emit('clicked');mark=time.monotonic();phase=10
  elif phase==10 and time.monotonic()-mark>.15:
   assert player.player.get_state()==Clapper.PlayerState.PLAYING and player.player.get_position()<.8
   print('FAVORITE ADD/REMOVE PERSISTS; REAL WHEEL ZOOM/UNCHANGED ALLOCATION; SIMULATED PINCH/PAN/RESET; SPACE PAUSE/PLAY KEEPS FOCUS; REAL LOOP/EOS REPLAY PASSED',flush=True)
   w.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);w.close();app.quit();return False
 return True
def activate(app):
 global w
 css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
 w=GalleryWindow(app);w.set_default_size(1200,800);w.present();w.client=client;w.library_mode='local';w.local_items=items
 GLib.source_remove(w.refresh_timer);w.refresh_timer=0
 texture=w.texture_from_pixels(decode_image(image))
 for item in items:w.texture_cache[w.texture_key(item)]=texture
 w.set_library_items(items);GLib.timeout_add(40,check)
app.connect('activate',activate);app.run([]);assert not errors
