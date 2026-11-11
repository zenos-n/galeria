"""Selection/viewer trash, archive and Locked snapshots target their actual icons."""
import os,sys,tempfile,time,threading
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=tempfile.TemporaryDirectory(prefix='galeria-actions-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
from library import MediaItem,ImmichClient,LibraryError
from PIL import Image
from imaging import decode_image
path=Path(root.name)/'original.png';Image.new('RGB',(100,70),'purple').save(path);original=path.read_bytes()
items=[MediaItem(str(i),'original.png',datetime(2026,11,30-i%20),10/7,metadata={'visibility':'timeline'}) for i in range(80)]
class Client(ImmichClient):
 def __init__(self):super().__init__('https://fixture.invalid');self.token='fixture';self.user={'id':'fixture'};self.locked_until=time.monotonic()+600;self.calls=[];self.fail=False;self.release=threading.Event();self.waiting=threading.Event()
 def image_bytes(self,*args,**kwargs):return original
 def update_assets(self,ids,fields):
  if self.fail:raise LibraryError('Fixture server failure')
  if fields.get('visibility')=='archive':self.waiting.set();assert self.release.wait(4),'Archive waited for acknowledgement before animating'
  self.calls.append((ids,fields))
 def trash_assets(self,ids):
  self.waiting.set();assert self.release.wait(4),'Trash waited for acknowledgement before animating'
  self.calls.append((ids,{'trash':True}))
client=Client();cases=[(mode,action) for action in ('trash','archive','locked') for mode in ('selection','viewer')]
app=Adw.Application(application_id='com.neg-zero.Galeria.ActionTargets',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=0;case=0;start=time.monotonic();errors=[];mark=0;notices=[]
def check():
 global phase,case,target,count,before,mark
 try:
  assert time.monotonic()-start<20,(phase,case,len(w.media_items))
  mode,action=cases[min(case,len(cases)-1)]
  if phase==0 and not w.loading_more and w.mosaic.rendered:
   before=len(w.media_items);count=2 if mode=='selection' else 1
   if mode=='viewer':w.open_viewer(0);phase=1
   else:
    w.mosaic.selected={0,1};w.mosaic.set_selection(True);mark=time.monotonic();phase=1
  elif phase==1:
   if mode=='viewer' and w.viewer.stage.progress<1:return True
   if mode=='selection' and time.monotonic()-mark<.25:return True
   target=getattr(w.viewer,'lock' if action=='locked' else action) if mode=='viewer' else w.selection_controls[action]
   if mode=='viewer':
    controls=[w.viewer.download,w.viewer.share,w.viewer.info,w.viewer.edit_button,w.viewer.fullscreen_button]
    positions=[control.compute_bounds(w)[1].get_x() for control in controls]
    assert positions==sorted(positions) and positions[0]>w.get_width()/2,positions
   client.release.clear();client.waiting.clear()
   mark=time.monotonic()
   target.emit('clicked');phase=2
  elif phase==2:
   dialog=w.get_visible_dialog()
   if isinstance(dialog,Adw.AlertDialog):mark=time.monotonic();dialog.emit('response','trash');dialog.close()
   motion=getattr(w,'action_motion',None)
   if motion is None or not .1<motion.progress<.9:return True
   assert motion.frames and motion.destination is target
   assert time.monotonic()-mark<.4,('Action feedback exceeded 400 ms',mode,action)
   if mode=='selection':
    assert len(w.media_items)==before-count,('Grid still waits for flight',action,len(w.media_items),before)
    assert w.mosaic.tick and 0<w.mosaic.p<1,('No concurrent reflow',action,w.mosaic.p)
    final=w.mosaic.target_layout(w.mosaic.last_width)[0]
    assert any(tile in final and tile in w.mosaic.rendered and start[:4]!=final[tile][:4] and w.mosaic.rendered[tile][:4]!=start[:4] and w.mosaic.rendered[tile][:4]!=final[tile][:4] for tile,start in w.mosaic.from_map.items() if tile in w.mosaic.tile_set),('Remaining tiles did not move during flight',action)
    assert w.selection_bar.get_child_revealed() and target.get_mapped()
   ok,bounds=target.get_child().compute_bounds(w.root_overlay);assert ok
   expected=(bounds.get_x()+bounds.get_width()/2,bounds.get_y()+bounds.get_height()/2)
   assert all(abs(a-b)<1 for a,b in zip(expected,motion.target)),(mode,action,expected,motion.target)
   assert motion.target[0]<w.get_width()/2 if mode=='viewer' else motion.target[0]>w.get_width()/2
   assert motion.target[1]<65 if mode=='viewer' else motion.target[1]>w.get_height()-65
   if action in ('archive','trash'):
    assert client.waiting.is_set() and len(client.calls)==case,('Animation waited for server',mode,action)
    client.release.set()
   phase=3
  elif phase==3 and len(w.media_items)==before-count and not w.loading_more and not w.mosaic.tick and not w.media_action_pending:
   assert not w.mosaic.selection_mode
   if mode=='viewer':
    assert w.viewer is not None and not w.viewer.closing
    w.viewer.dismiss_action()
   else:assert w.viewer is None
   assert all(tile.media_texture is not None for tile in w.mosaic.active_widgets & w.mosaic.tile_set)
   case+=1
   if case<len(cases):phase=0;return True
   client.fail=True;before=len(w.media_items);w.mosaic.selected={0};w.mosaic.set_selection(True);w.selected_action('archive');phase=4
  elif phase==4 and any('Fixture server failure' in text for text in notices) and not w.media_action_pending and not w.mosaic.tick:
   assert len(w.media_items)==before and getattr(w,'action_motion',None) is None and path.read_bytes()==original
   assert len(client.calls)==6
   client.fail=False;client.release.set();Gtk.Settings.get_default().set_property('gtk-enable-animations',False)
   w.mosaic.selected=set(range(len(w.mosaic.tiles)));w.mosaic.set_selection(True);w.selected_action('archive');phase=5
  elif phase==5 and not w.media_items and not w.media_action_pending:
   assert not w.mosaic.selection_mode and not w.selection_bar.get_reveal_child()
   assert path.read_bytes()==original and len(client.calls)==7
   print('CONCURRENT SELECTION REFLOW/FLIGHT; EMPTY GRID/REDUCED MOTION; ALL SIX SELECTION/VIEWER TRASH/ARCHIVE/LOCKED MOTIONS TARGET ACTUAL BUTTON ICONS; PIXELS RETAINED; FAILED MUTATION LEAVES GRID/ORIGINAL INTACT PASSED',flush=True)
   w.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);w.close();app.quit();return False
 return True
def activate(app):
 global w
 css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
 w=GalleryWindow(app);w.set_default_size(1200,800);w.present();w.client=client;w.notice=notices.append
 GLib.source_remove(w.refresh_timer);w.refresh_timer=0
 texture=w.texture_from_pixels(decode_image(path))
 for item in items:w.texture_cache[w.texture_key(item)]=texture
 w.set_library_items(items);GLib.timeout_add(25,check)
app.connect('activate',activate);app.run([]);assert not errors
