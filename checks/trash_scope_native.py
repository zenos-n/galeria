"""Actual scope dialog -> cloud API fixture and reversible desktop Trash."""
import os,sys,tempfile,time,hashlib
from pathlib import Path
from datetime import datetime
assert os.environ.get('DISPLAY')==':91'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=tempfile.TemporaryDirectory(prefix='galeria-trash-scope-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME','XDG_DATA_HOME'):os.environ[key]=root.name+'/'+key
from app import *
from PIL import Image
from library import MediaItem
from imaging import decode_image
from local_media import remember_copy
cases=[('both','selection'),('local','selection'),('cloud','viewer'),('local','device')]
notices=[];calls=[];errors=[];phase=0;case=0;start=time.monotonic()
class Client(ImmichClient):
 def __init__(self):super().__init__('https://fixture.invalid');self.user={'id':'fixture'};self.token='fixture'
 def image_bytes(self,*args,**kwargs):return original
 def trash_assets(self,ids):calls.append(ids)
app=Adw.Application(application_id='com.neg-zero.Galeria.TrashScopeCheck',flags=Gio.ApplicationFlags.NON_UNIQUE)
def walk(widget):
 yield widget
 child=widget.get_first_child()
 while child:yield from walk(child);child=child.get_next_sibling()
def check():
 global phase,case,path,original,item,cloud_calls,mark
 try:
  assert time.monotonic()-start<20,(phase,case,notices)
  scope,mode=cases[case]
  if phase==0:
   path=Path(root.name)/('photo'+str(case)+'.png');Image.new('RGB',(60,40),'purple').save(path);original=path.read_bytes()
   w.client=client if mode!='device' else None;cloud_calls=len(calls)
   item=MediaItem('asset'+str(case),path.name,datetime.now(),1.5,path=str(path) if mode=='device' else None,metadata={'visibility':'timeline'})
   if w.client:remember_copy(client,path,item.id,hashlib.sha1(original).hexdigest(),path.stat())
   w.texture_cache[w.texture_key(item)]=w.texture_from_pixels(decode_image(path));w.set_library_items([item]);w.local_items=[item] if mode=='device' else [];mark=time.monotonic();phase=1
  elif phase==1 and w.mosaic.rendered and time.monotonic()-mark>.2:
   if mode=='viewer':w.open_viewer(0);phase=2
   else:w.mosaic.selected={0};w.mosaic.set_selection(True);w.selected_action('trash');phase=3
  elif phase==2 and w.viewer.stage.progress==1:
   w.viewer.trash.emit('clicked');phase=3
  elif phase==3:
   dialog=w.get_visible_dialog()
   if not isinstance(dialog,Adw.AlertDialog):return True
   row=next(widget for widget in walk(dialog) if isinstance(widget,Adw.ComboRow));model=row.get_model();options=[model.get_string(i) for i in range(model.get_n_items())]
   if not hasattr(dialog,'paint_after'):dialog.paint_after=time.monotonic()+.25
   if time.monotonic()<dialog.paint_after:return True
   if case==0:
    from PIL import ImageGrab
    ImageGrab.grab(xdisplay=':91').save('/tmp/gallery-app-identification/trash-scope-0144.png')
   if mode!='device':assert options==['This device and Immich','This device only','Immich only'] and row.get_selected()==0
   row.set_selected(options.index({'both':'This device and Immich','local':'This device only','cloud':'Immich only'}[scope]));dialog.emit('response','trash');dialog.close();phase=4
  elif phase==4 and len(notices)>case and not w.media_action_pending:
   if scope=='cloud':assert path.read_bytes()==original and not w.media_items and w.viewer is None
   else:
    assert not path.exists()
    trashed=list((Path(os.environ['XDG_DATA_HOME'])/'Trash/files').glob(path.name+'*'));assert any(file.read_bytes()==original for file in trashed)
    if mode=='device' or scope=='both':assert not w.media_items
    else:assert len(w.media_items)==1
   assert len(calls)==cloud_calls+int(scope!='local')
   if w.viewer:w.viewer.close();phase=5
   else:phase=5
  elif phase==5 and w.viewer is None:
   case+=1
   if case<len(cases):phase=0;return True
   print('NATIVE BOTH/LOCAL/CLOUD SCOPE; BOTH DEFAULT; REAL DESKTOP TRASH RESTORABLE BYTES; CLOUD FIXTURE CALLS; CLOUD-ONLY KEEPS ORIGINAL; LOCAL-ONLY KEEPS CLOUD GRID; SELECTION/FOCUS/LOCAL DEVICE PATHS PASSED',flush=True)
   w.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);w.close();app.quit();return False
 return True
def activate(app):
 global w,client
 css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
 client=Client();w=GalleryWindow(app);w.set_default_size(1200,800);w.notice=notices.append;w.present();GLib.source_remove(w.refresh_timer);w.refresh_timer=0;GLib.timeout_add(30,check)
app.connect('activate',activate);app.run([]);assert not errors
