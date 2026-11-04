"""Moving two assets to Locked retains unrelated RAM/disk pixels and scroll."""
import os,sys,tempfile,time
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=tempfile.TemporaryDirectory(prefix='galeria-locked-retention-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
from library import MediaItem
from timeline_index import TimelineIndex
from cache import MediaCache
from PIL import Image
from imaging import decode_image
path=Path(root.name)/'original.png';Image.new('RGB',(80,50),'purple').save(path);original=path.read_bytes()
items=[MediaItem(str(i),'original.png',datetime(2016,8-i//160,25-i%20),1.6,metadata={'visibility':'timeline','updatedAt':'version'}) for i in range(480)]
class Client(ImmichClient):
 def __init__(self):super().__init__('https://fixture.invalid');self.token='fixture';self.user={'id':'fixture'};self.locked_until=time.monotonic()+600;self.calls=[];self.loads=0
 def update_assets(self,ids,fields):self.calls.append((ids,fields))
 def image_bytes(self,*args,**kwargs):self.loads+=1;raise AssertionError('Existing pixels must not download again')
app=Adw.Application(application_id='com.neg-zero.Galeria.LockedRetentionCheck',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=0;start=time.monotonic();errors=[];client=Client();missing=[]
def check():
 global phase,moved,retained,position,texture,mark
 try:
  assert time.monotonic()-start<15,phase
  m=w.mosaic;scroll=w.scroller.get_vadjustment()
  if phase==0 and not w.loading_more and m.rendered:
   scroll.set_value(500);phase=1
  elif phase==1:
   visible=sorted((tile for tile in m.active_widgets & m.tile_set if m.rendered[tile][1]>=scroll.get_value()),key=lambda tile:tile.index)
   moved=[tile.media_item for tile in visible[:2]];retained=visible[3].media_item
   position=scroll.get_value();m.selected={tile.index for tile in visible[:2]};m.set_selection(True)
   for item in moved:
    w.texture_cache[(item.id,'old')]=texture
    client.media_cache().put(client.image_key(item),b'private')
    client.media_cache().put(item.id+':older:preview',b'private old')
    client.video_cache().put('video-prefix:'+item.id+'version',b'private video')
   client.media_cache().put(client.image_key(retained),b'public pixels');client.media_cache().put('stale-metadata',b'private asset metadata')
   w.date_cover_cache[('months','keep')]=[(retained.id,texture)];w.date_cover_cache[('months','remove')]=[(moved[0].id,texture)]
   w.collection_textures[('asset',retained.id)]=texture;w.collection_textures[('asset',moved[0].id)]=texture
   w.move_selected_to_locked();phase=2
  elif phase==2:
   active=m.active_widgets & m.tile_set
   missing.append(sum(tile.media_texture is None for tile in active))
   if len(w.media_items)!=478 or w.loading_more or m.tick:return True
   assert len(client.calls)==1 and client.calls[0][1]=={'visibility':'locked'}
   assert not any(missing) and not client.loads,(missing,client.loads)
   assert all(item.id not in {tile.media_item.id for tile in m.tiles} for item in moved)
   assert abs(scroll.get_value()-position)<1,(position,scroll.get_value())
   assert client.media_cache().get(client.image_key(retained))==b'public pixels'
   assert MediaCache(client.identity).get(client.image_key(retained))==b'public pixels'
   for item in moved:
    assert w.texture_key(item) not in w.texture_cache and (item.id,'old') not in w.texture_cache
    assert client.media_cache().get(item.id+':older:preview') is None
    assert client.video_cache().get('video-prefix:'+item.id+'version') is None
   assert client.media_cache().get('stale-metadata') is None
   assert ('months','keep') in w.date_cover_cache and ('months','remove') not in w.date_cover_cache
   assert ('asset',retained.id) in w.collection_textures and ('asset',moved[0].id) not in w.collection_textures
   assert path.read_bytes()==original
   print('TWO LOCKED MOVES: ALL OTHER RAM/DISK PIXELS RETAINED, ZERO DOWNLOADS/BLANK CELLS, SCROLL HELD; PRIVATE REVISIONS/METADATA/COVERS PURGED, ORIGINAL UNTOUCHED PASSED',flush=True)
   w.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);w.close();app.quit();return False
 return True
def activate(app):
 global w,texture
 css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
 w=GalleryWindow(app);w.set_default_size(1200,800);w.present();w.client=client
 GLib.source_remove(w.refresh_timer);w.refresh_timer=0
 texture=w.texture_from_pixels(decode_image(path))
 for item in items:w.texture_cache[w.texture_key(item)]=texture
 buckets=[{'timeBucket':f'2016-{month:02}-01','count':160} for month in (8,7,6)]
 w.timeline_buckets=buckets;w.timeline_index=TimelineIndex(buckets)
 for month in (8,7,6):w.timeline_index.apply(f'2016-{month:02}',[item for item in items if item.created.month==month])
 w.set_library_items(w.timeline_index.items);GLib.timeout_add(40,check)
app.connect('activate',activate);app.run([]);assert not errors
