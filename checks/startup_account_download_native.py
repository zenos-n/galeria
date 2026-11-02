"""Offline native cold-process/warm-cache and chosen-destination integration."""
import os,sys,tempfile,time,threading
from pathlib import Path
from datetime import datetime
from io import BytesIO
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=tempfile.TemporaryDirectory(prefix='galeria-native-batch-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
from library import ImmichClient,MediaItem
from cache import MediaCache
from PIL import Image
from sync_service import save_config,state_dir
from session_store import preferences_write
from cache import atomic_write
import data_ui,json
server='https://fixture.invalid/api';identity=server+'|user';gate=threading.Event();requests=[];pickers=[]
png=BytesIO();Image.new('RGB',(80,40),'purple').save(png,format='PNG');png=png.getvalue()
items=[MediaItem(str(i),f'photo{i}.png',datetime(2026,2 if i<4 else 1,8-i),2,metadata={'visibility':'timeline'}) for i in range(8)]
buckets=[{'timeBucket':'2026-02-01','count':4},{'timeBucket':'2026-01-01','count':4}]
cache=MediaCache(identity)
for item in items:cache.put(item.id+'::thumbnail',png)
profile_path=Path(root.name)/'new-profile.png';profile_path.write_bytes(png)
class Client(ImmichClient):
 def __init__(self,*_):super().__init__(server);self.cache=cache;self.profile=png;self.uploaded=None
 def request(self,path,*args,**kwargs):
  requests.append(path)
  if path=='/users/me':gate.wait(10);return {'id':'user','name':'Fixture','isAdmin':True,'profileChangedAt':'old'}
  raise AssertionError(path)
 def detect_version(self):pass
 def lock_session(self):self.server_lock_pending=False
 def time_buckets(self,*args,**kwargs):return buckets
 def time_bucket(self,key,**kwargs):return [item for item in items if item.created.strftime('%Y-%m')==key]
 def albums(self):return []
 def profile_image(self,**kwargs):return self.profile
 def image_bytes(self,*args,**kwargs):return png
 def upload_profile_image(self,data,name):self.uploaded=data;self.profile=data;self.user['profileChangedAt']='new';return self.user
 def open_original(self,item):
  body=('original:'+item.id).encode();stream=BytesIO(body);stream.headers={'Content-Length':str(len(body))};return stream
class Picker:
 def __init__(self,**kwargs):self.title=kwargs.get('title')
 def set_initial_name(self,name):pass
 def set_filters(self,*_):pass
 def save(self,window,cancel,callback):pickers.append('save');GLib.idle_add(callback,self,None)
 def save_finish(self,result):return Gio.File.new_for_path(root.name+'/chosen-original.png')
 def select_folder(self,window,cancel,callback):pickers.append('folder');GLib.idle_add(callback,self,None)
 def select_folder_finish(self,result):return Gio.File.new_for_path(root.name+'/chosen-folder')
 def open(self,window,cancel,callback):pickers.append('profile');GLib.idle_add(callback,self,None)
 def open_finish(self,result):return Gio.File.new_for_path(str(profile_path))
data_ui.ImmichClient=Client;data_ui.secret_get=lambda *_:'fixture'
preferences_write({'mode':'immich','remember':True,'server':server,'user_id':'user','last_user':{'id':'user','name':'Fixture','profileChangedAt':'old'}})
app=Adw.Application(application_id='com.neg-zero.Galeria.NativeBatch',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=0;start=time.monotonic();errors=[];busy=[]
def close_dialog():
 dialog=window.get_visible_dialog()
 if dialog:dialog.close()
def check():
 global phase,mosaic_before,buckets
 try:
  assert time.monotonic()-start<25,(phase,busy,requests)
  if phase==0 and window.client and len(window.media_items)==8 and window.mosaic.rendered:
   assert window.client.restoring and requests==['/users/me'],requests
   assert window.stack.get_visible_child_name()=='library' and not busy,busy
   assert all(tile.media_texture is not None for tile in window.mosaic.tiles)
   assert window.source_label.get_parent() is None
   mosaic_before=window.mosaic;gate.set();phase=1
  elif phase==1 and not window.client.restoring and window.avatar.get_custom_image():
   assert window.mosaic is mosaic_before
   m=window.mosaic;m.selected={0};m.selection_mode=True;m.update_selection()
   assert window.select_scope_button.get_label()=='Select month';m.select_all();assert len(m.selected)==4
   m.selected={0,4};m.update_selection();assert window.select_scope_button.get_label()=='Select all from selected months'
   m.select_all();assert len(m.selected)==8
   window.download_items([items[0]]);phase=2
  elif phase==2 and Path(root.name+'/chosen-original.png').exists():
   assert Path(root.name+'/chosen-original.png').read_bytes()==b'original:0'
   close_dialog();Path(root.name+'/chosen-folder').mkdir();window.download_selected_button.emit('clicked');phase=3
  elif phase==3 and len(list(Path(root.name+'/chosen-folder').iterdir()))==8:
   close_dialog();window.change_profile_photo();phase=4
  elif phase==4 and window.client.uploaded:
   assert window.client.uploaded==png and window.avatar.get_custom_image()
   assert window.preferences['last_user']['profileChangedAt']=='new'
   save_config({'accounts':{identity:{'enabled':True,'folders':[{'path':'/fixture'}]}}})
   atomic_write(state_dir()/'sync-status.json',json.dumps({'active':True,'updated':time.time(),'accounts':{identity:{'busy':True,'progress':{'uploaded':2}}}}).encode())
   window.uploads.requested();window.uploads.sync_requested_at=0;window.uploads.poll_sync()
   assert window.uploads.get_visible() and window.uploads.summary.get_label()=='Syncing folders…'
   phase=40
  elif phase==40:
   ok,bounds=window.uploads.compute_bounds(window);assert ok
   bottom=window.get_height()-bounds.get_y()-bounds.get_height()
   assert abs(bottom-10)<1,bottom
   window.uploads.popup();assert window.uploads.get_popover().get_visible()
   atomic_write(state_dir()/'sync-status.json',json.dumps({'active':False,'updated':time.time(),'accounts':{identity:{'busy':False,'folders':[{'uploaded':2}]}}}).encode())
   window.uploads.poll_sync();assert not window.uploads.get_visible() and not window.uploads.get_popover().get_visible()
   assert pickers==['save','folder','profile'],pickers
   window.mosaic.set_selection(False)
   items.insert(0,MediaItem('background-photo','new.png',datetime(2027,1,1),2,metadata={'visibility':'timeline'}))
   buckets=[{'timeBucket':'2027-01-01','count':1}]+buckets
   window.is_active=lambda:False;window.refresh_remote();phase=5
  elif phase==5 and len(window.media_items)==9 and window.media_items[0].id=='background-photo':
   print('CACHE-FIRST PIXELS BEFORE AUTH/NO LOADING PAGE; NO GRID RESET; MONTH SCOPES; SINGLE/BULK CHOSEN DESTINATIONS; PROFILE LOAD/CHANGE; SIDEBAR SYNC/NO USER FOOTER; UNFOCUSED REMOTE REFRESH PASSED',flush=True)
   window.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);gate.set();window.close();app.quit();return False
 return True
def activate(app):
 global window
 provider=Gtk.CssProvider();provider.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
 window=GalleryWindow(app);window.set_default_size(1280,820);window.present()
 original=window.busy_library
 def loading(title):busy.append(title);return original(title)
 window.busy_library=loading
 GLib.idle_add(window.restore_last_library);GLib.timeout_add(100,check)
with patch.object(Gtk,'FileDialog',Picker):app.connect('activate',activate);app.run([])
assert not errors
