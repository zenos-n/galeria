"""Native editor exit decisions, real save completion/failure and close guards."""
import os,sys,tempfile,time,threading,subprocess
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
assert os.environ.get('DISPLAY')==':91' and os.environ.get('GDK_BACKEND')=='x11'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=tempfile.TemporaryDirectory(prefix='galeria-edit-exit-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
gi.require_version('GdkX11','4.0')
from gi.repository import GdkX11
from PIL import Image
from library import MediaItem,ImmichClient,LibraryError
from imaging import decode_image
photo=Path(root.name)/'photo.png';Image.new('RGB',(320,240),'#708090').save(photo)
clip=Path(root.name)/'clip.mp4'
subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc=size=160x90:rate=15','-t','2.4','-pix_fmt','yuv420p','-threads','1',str(clip)],check=True)
originals={p:p.read_bytes() for p in (photo,clip)}
items=[MediaItem('photo','photo.png',datetime(2026,11,3),4/3,path=str(photo)),MediaItem('other','other.png',datetime(2026,11,2),4/3,path=str(photo)),MediaItem('video','clip.mp4',datetime(2026,11,1),16/9,kind='VIDEO',path=str(clip))]
app=Adw.Application(application_id='com.neg-zero.Galeria.EditorExitCheck',flags=Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
w=GalleryWindow(app);w.set_default_size(1200,900);w.present()
GLib.source_remove(w.refresh_timer);w.refresh_timer=0
client=ImmichClient('https://fixture.invalid');client.token='fixture';client.user={'id':'fixture'};w.client=client;w.upload_finished=lambda _:None
texture=w.texture_from_pixels(decode_image(photo))
for item in items:w.texture_cache[w.texture_key(item)]=texture
w.set_library_items(items)
def pump(until,timeout=12):
 deadline=time.monotonic()+timeout;context=GLib.MainContext.default()
 while not until():
  assert time.monotonic()<deadline,'Timed out'
  context.iteration(False);time.sleep(.005)
 for _ in range(4):context.iteration(False)
def walk(widget):
 yield widget
 child=widget.get_first_child()
 while child:yield from walk(child);child=child.get_next_sibling()
def click(widget):
 native=widget.get_native();ok,bounds=widget.compute_bounds(native);assert ok
 dx,dy=native.get_surface_transform();tool='/tmp/gallery-app-identification/xdotool/bin/xdotool';xid=str(GdkX11.X11Surface.get_xid(native.get_surface()))
 subprocess.run([tool,'windowraise',xid,'windowfocus',xid,'mousemove','--window',xid,str(round(bounds.get_x()+bounds.get_width()/2+dx)),str(round(bounds.get_y()+bounds.get_height()/2+dy)),'click','1'],check=True)
def respond(label):
 pump(lambda:w.viewer.exit_dialog is not None and w.viewer.exit_dialog.get_mapped())
 dialog=w.viewer.exit_dialog
 assert {dialog.get_response_label(name) for name in ('cancel','discard','save')}=={'Cancel','Discard','Save'}
 button=next(widget for widget in walk(dialog) if isinstance(widget,Gtk.Button) and widget.get_label()==label)
 ready=time.monotonic()+.35;pump(lambda:button.get_width()>0 and time.monotonic()>ready);click(button);pump(lambda:w.viewer.exit_dialog is None)
 settled=time.monotonic()+.25;pump(lambda:time.monotonic()>settled)
def screenshot(name):
 from PIL import ImageGrab
 settled=time.monotonic()+.4;pump(lambda:time.monotonic()>settled)
 ImageGrab.grab(xdisplay=':91').save('/tmp/gallery-app-identification/'+name+'.png')

gate=threading.Event();started=threading.Event();fail=[True];uploads=[]
def transfer(client,data,name,modified,cancel,**kwargs):
 started.set();assert gate.wait(8)
 if fail[0]:raise LibraryError('Fixture upload failed')
 uploads.append(data);return 'saved',True
class Picker:
 mode='cancel'
 def __init__(self,**kwargs):pass
 def set_filters(self,*_):pass
 def set_default_filter(self,*_):pass
 def save(self,window,cancel,callback):GLib.idle_add(callback,self,None)
 def save_finish(self,result):
  if self.mode=='cancel':raise GLib.Error('Cancelled')
  return Gio.File.new_for_path(str(Path(root.name)/'edited.mp4'))
try:
 pump(lambda:not w.loading_more and bool(w.mosaic.rendered));w.open_viewer(0);pump(lambda:w.viewer.stage.progress==1)
 v=w.viewer;v.set_editing(True);p=v.photo_editor;pump(lambda:p.original is not None and not p.running)
 assert not p.dirty();v.set_editing(False);assert not v.editing and v.exit_dialog is None
 v.set_editing(True);p.values['Brightness']=20;p.queue(0);v.set_editing(False)
 respond('Cancel');assert v.editing and p.dirty() and p.values['Brightness']==20
 v.on_key(None,Gdk.KEY_Escape);respond('Discard');pump(lambda:not v.editing);assert not p.dirty() and p.values['Brightness']==0
 v.set_editing(True);v.editor_categories.set_active_name('Markup')
 for widget in walk(v.editor):
  if isinstance(widget,Gtk.ToggleButton) and widget.get_tooltip_text()=='Text':widget.set_active(True)
 p.markup.strokes=[{'tool':'Text','text':'Galeria','color':'#ffffff','width':.008,'points':[(.5,.5)],'scale':8,'rotation':0}];p.markup.selected=0;p.markup.tool='Text';p.markup_changed();p.queue(0)
 pump(lambda:not p.running and not p.debounce)
 v.editor_categories.set_active_name('Adjust');pump(lambda:not p.running and not p.debounce);assert p.markup.get_visible() and not p.markup.get_can_target()
 v.editor_categories.set_active_name('Markup');pump(lambda:not p.running and not p.debounce);assert p.markup.get_visible() and p.markup.get_can_target()
 screenshot('editor-vector-text-0140')
 with patch('upload_media.upload_bytes',transfer):
  click(v.close_button);pump(lambda:v.exit_dialog is not None and v.exit_dialog.get_mapped());screenshot('editor-save-prompt-0140');respond('Save')
  pump(started.is_set);assert v.editing and v.exit_saving and not v.get_sensitive()
  assert any(item.metadata.get('upload_state')=='uploading' for item in w.media_items),'Edited copy did not enter the grid before upload completion'
  gate.set();pump(lambda:not v.exit_saving);assert v.editing and p.dirty() and 'failed' in v.tool_message.get_label()
  assert any(entry['item'].metadata.get('upload_state')=='failed' for entry in w.upload_previews.entries.values())
  gate.clear();started.clear();fail[0]=False;v.set_editing(False);respond('Save');pump(started.is_set)
  assert v.editing
  assert any(entry['item'].metadata.get('upload_state')=='uploading' for entry in w.upload_previews.entries.values()),'Edited copy lacks pending upload state'
  gate.set();pump(lambda:not v.editing);assert not p.dirty() and len(uploads)==1
  assert any(entry['asset']=='saved' and entry['item'].metadata.get('upload_state')=='complete' for entry in w.upload_previews.entries.values()),'Edited copy remains pending after acknowledgement'
  v.set_editing(True);v.set_editing(False);assert not v.editing and v.exit_dialog is None
 target=next(i for i,item in enumerate(w.media_items) if item.id=='other');step=target-v.index
 v.set_editing(True);p.values['Brightness']=40;p.queue(0);v.move(step);respond('Cancel');assert v.index==0 and v.editing
 v.move(step);respond('Discard');pump(lambda:v.index==target and v.photo_editor.original is not None)
 p=v.photo_editor;p.values['Brightness']=50;p.queue(0);w.close();respond('Cancel');assert w.get_visible() and v.editing and p.dirty()
 quit_calls=[];fake=SimpleNamespace(window=w,get_windows=lambda:[w],quitting=False,quit=lambda:quit_calls.append(True));fake.force_quit=lambda:Gallery.force_quit(fake)
 fake.force_quit();respond('Cancel');assert not fake.quitting and not quit_calls and w.get_visible()
 v.close();respond('Discard');pump(lambda:w.viewer is None)
 w.open_viewer(next(i for i,item in enumerate(w.media_items) if item.id==items[2].id));pump(lambda:w.viewer.stage.progress==1);v=w.viewer;v.set_editing(True);pump(lambda:bool(v.video_editor.duration))
 e=v.video_editor;assert not e.dirty();e.start.set_value(.4);v.set_editing(False);respond('Cancel');assert v.editing and e.dirty()
 with patch.object(Gtk,'FileDialog',Picker):
  v.set_editing(False);respond('Save');pump(lambda:not v.exit_saving);assert v.editing and e.dirty()
  Picker.mode='save'
  with patch('video_editor.export',side_effect=LibraryError('Fixture export failed')):
   v.set_editing(False);respond('Save');pump(lambda:not v.exit_saving);assert v.editing and e.dirty() and 'failed' in e.message.get_label()
  v.set_editing(False);respond('Save');pump(lambda:not v.editing,20);assert not e.dirty() and (Path(root.name)/'edited.mp4').exists()
 v.set_editing(True);e.start.set_value(.7);v.set_editing(False);respond('Discard');pump(lambda:not v.editing);assert abs(e.start.get_value()-.4)<.01
 assert all(path.read_bytes()==data for path,data in originals.items())
 v.close();pump(lambda:w.viewer is None);w.close()
 print('PHOTO/VIDEO SAVE-CANCEL-DISCARD; REAL PHOTO UPLOAD/VIDEO EXPORT COMPLETION, FAILURE/CHOOSER CANCEL; CLEAN STATE/UNDO BASELINE; DONE/BACK/ESC/NAVIGATION/WINDOW CLOSE/QUIT GUARDS; ORIGINALS PRESERVED PASSED',flush=True)
finally:
 gate.set();w.stop_data();app.quit()
