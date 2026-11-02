import os,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
profile=tempfile.TemporaryDirectory(prefix='galeria-editor-native-')
for key in ['XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME']:os.environ[key]=profile.name+'/'+key
import subprocess
clip=Path(profile.name)/'sample.mp4'
subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc=size=160x90:rate=15','-t','2.4','-pix_fmt','yuv420p','-threads','1',str(clip)],check=True)
from app import *
from library import scan_folders
from imaging import image_ratio
app=Adw.Application(application_id='com.neg-zero.Galeria.VideoEditingTest',flags=Gio.ApplicationFlags.NON_UNIQUE)
errors=[];phase=0;started=time.monotonic()
def check():
 global phase
 try:
  assert time.monotonic()-started<35,(phase,window.viewer.video_editor.message.get_label() if window.viewer else '')
  viewer=window.viewer
  if phase==0 and window.media_items:
   window.open_viewer(0);phase=1
  elif phase==1 and viewer.stage.progress==1:
   viewer.set_editing(True);phase=2
  elif phase==2 and viewer.video_editor.duration:
   editor=viewer.video_editor;assert editor.save.get_sensitive()
   editor.start.set_value(.4);editor.end.set_value(1.7);editor.rotate(90);editor.filter_buttons[4].set_active(True)
   viewer.editor_categories.set_active_name('Crop');viewer.stage.crop_frame.bounds=(.1,.1,.9,.9)
   a,b=editor.trim_range.points();assert b>a
   span=max(1,editor.trim_range.get_width()-20)
   for active,value in ((0,.5),(1,1.8)):
    editor.trim_range.active=active;editor.trim_range.adjust(10+span*value/editor.duration)
   assert abs(editor.start.get_value()-.5)<.01 and abs(editor.end.get_value()-1.8)<.01
   editor.position.set_value(.7);editor.toggle_playback();phase=25
  elif phase==25 and viewer.stage.video_player.player.get_position()>.75:
   viewer.video_editor.position.set_value(1.1);phase=26
  elif phase==26 and viewer.stage.video_player.player.get_position()>1.15:
   viewer.video_editor.toggle_playback();assert not viewer.video_editor.playing
   viewer.video_editor.queue_preview();phase=3
  elif phase==3 and time.monotonic()-started>4:
   editor=viewer.video_editor
   if not viewer.stage.image.get_paintable():return True
   editor.render(profile.name+'/edited.mp4');phase=4
  elif phase==4 and not viewer.video_editor.running:
   assert Path(profile.name+'/edited.mp4').exists(),viewer.video_editor.message.get_label()
   viewer.video_editor.render(None,True);phase=5
  elif phase==5 and not viewer.video_editor.running:
   assert viewer.stage.video_player and viewer.stage.video_player.get_visible()
   viewer.set_editing(False);assert viewer.stage.video_player.get_visible()
   viewer.video_editor.close();window.close();app.quit();print('NATIVE TWO-HANDLE TRIM/EDIT PLAYBACK/SCRUB/CROP/ROTATE/FILTER/EXPORT/PREVIEW PASSED',flush=True);return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);window.close();app.quit();return False
 return True
def activate(app):
 global window
 provider=Gtk.CssProvider();provider.load_from_path('/Users/doromiert/Projects/gallery/style.css');Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
 window=GalleryWindow(app);window.present();window.connect_local([str(clip)])
 GLib.timeout_add(100,check)
app.connect('activate',activate);app.run([])
assert not errors
