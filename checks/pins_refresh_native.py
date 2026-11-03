"""Private-display album pins and atomic, animated upload arrival; no real account."""
import os,sys,tempfile,time,subprocess,threading
from pathlib import Path
from datetime import datetime
from io import BytesIO
assert os.environ.get('DISPLAY')==':91' and os.environ.get('GDK_BACKEND')=='x11'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=tempfile.TemporaryDirectory(prefix='galeria-pins-refresh-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
gi.require_version('GdkX11','4.0')
from gi.repository import GdkX11
from PIL import Image
from library import MediaItem
from timeline_index import TimelineIndex
from collections_ui import collection_view
from session_store import preferences_read
from imaging import decode_image
blob=BytesIO();Image.new('RGB',(120,80),'purple').save(blob,format='PNG');png=blob.getvalue()
items=[MediaItem(str(i),str(i)+'.png',datetime(2026-i//80//12,12-i//80%12,20-i%20),1.5,metadata={'visibility':'timeline'}) for i in range(1440)]
albums=[{'id':'a','albumName':'First album','ownerId':'fixture','assetCount':2}, {'id':'b','albumName':'Second album','ownerId':'fixture','assetCount':2}]
gate=threading.Event();gate.set();entered=threading.Event()
class Client(ImmichClient):
 def __init__(self):super().__init__('https://fixture.invalid');self.user={'id':'fixture','name':'Fixture'};self.token='fixture';self.modern_search=True;self.block=False;self.fail=False
 def collection(self,kind):assert kind=='albums';return albums
 def albums(self):return albums
 def time_buckets(self,**kwargs):
  counts={}
  for item in items:
   key=item.created.strftime('%Y-%m-01');counts[key]=counts.get(key,0)+1
  return [{'timeBucket':key,'count':count} for key,count in counts.items()]
 def time_bucket(self,key,**kwargs):
  if self.block:entered.set();gate.wait(10)
  if self.fail:raise LibraryError('Fixture temporarily unavailable')
  return [item for item in items if item.created.strftime('%Y-%m')==key]
 def image_bytes(self,*args,**kwargs):return png
 def search(self,*args,**kwargs):return items[:4],None
client=Client()
app=Adw.Application(application_id='com.neg-zero.Galeria.PinsRefreshTest',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=0;start=time.monotonic();errors=[];busy=[];mark=0
def walk(widget):
 yield widget
 child=widget.get_first_child()
 while child:yield from walk(child);child=child.get_next_sibling()
def action(popover,title):return next(widget for widget in walk(popover) if isinstance(widget,Gtk.Button) and widget.get_label()==title)
def pointer(widget,click=False):
 ok,bounds=widget.compute_bounds(w);assert ok
 cmd=[os.environ.get('GALERIA_XDOTOOL','/tmp/gallery-app-identification/xdotool/bin/xdotool'),'mousemove','--window',str(GdkX11.X11Surface.get_xid(w.get_surface())),str(round(bounds.get_x()+bounds.get_width()/2)),str(round(bounds.get_y()+bounds.get_height()/2))]
 if click:cmd+=['click','3']
 subprocess.run(cmd,check=True)
def popover(widget):return next((child for child in walk(widget) if isinstance(child,Gtk.Popover) and child.get_visible()),None)
def freeze(value):
 m=w.mosaic
 if m.tick:m.remove_tick_callback(m.tick);m.tick=0
 m.p=value;m.queue_resize()
def shot(name):
 snap=Gtk.Snapshot();Gtk.WidgetPaintable.new(w).snapshot(snap,w.get_width(),w.get_height());node=snap.to_node()
 if node:w.get_renderer().render_texture(node,Graphene.Rect().init(0,0,w.get_width(),w.get_height())).save_to_png('/tmp/gallery-app-identification/'+name+'.png')
def check():
 global phase,menu,opener,mark,old,old_ids,selection,anchor,offset,new
 try:
  assert time.monotonic()-start<35,phase
  if phase==0:
   menus=[widget for widget in walk(w) if isinstance(widget,Gtk.MenuButton) and widget.get_tooltip_text()=='Collection actions']
   if not menus:return True
   assert not w.pin_section.get_visible() and not w.pin_rows
   labels={widget.get_label():widget for widget in walk(w.split.get_sidebar()) if isinstance(widget,Gtk.Label) and widget.has_css_class('sidebar-section')}
   def gap(title):
    heading=labels[title];nav=heading.get_next_sibling();row=nav.get_first_child()
    ok,a=heading.compute_bounds(w);ok,b=row.compute_bounds(w);return b.get_y()-a.get_y()-a.get_height()
   assert abs(gap('Collections')-gap('Media types'))<=2,(gap('Collections'),gap('Media types'))
   menu=menus[0];opener=next(widget for widget in walk(w) if isinstance(widget,Gtk.Button) and widget.has_css_class('collection-open'))
   menu.popup();action(menu.get_popover(),'Pin album').emit('clicked');phase=1
  elif phase==1 and w.pin_rows:
   assert w.pin_section.get_visible() and preferences_read()['pins'][client.identity]==['a']
   client.user['id']='other';w.refresh_pins();assert not w.pin_section.get_visible()
   client.user['id']='fixture';w.refresh_pins();assert w.pin_section.get_visible()
   pointer(opener,True);phase=2
  elif phase==2:
   context=popover(opener.get_parent())
   if not context:return True
   action(context,'Unpin album').emit('clicked');phase=3
  elif phase==3 and not w.pin_section.get_visible():
   menu.popup();action(menu.get_popover(),'Pin album').emit('clicked');phase=4
  elif phase==4 and w.pin_rows:
   pointer(w.pin_rows[0],True);phase=5
  elif phase==5:
   context=popover(w.pin_rows[0])
   if not context:return True
   action(context,'Unpin album').emit('clicked');phase=6
  elif phase==6 and not w.pin_rows:
   assert not w.pin_section.get_visible() and preferences_read()['pins'][client.identity]==[]
   title=next(widget for widget in walk(w.album_tree) if isinstance(widget,Gtk.Label) and widget.get_label()=='First album')
   pointer(title.get_parent(),True);phase=61
  elif phase==61:
   context=popover(w.album_tree)
   if not context:return True
   action(context,'Pin album').emit('clicked');phase=62
  elif phase==62 and w.pin_rows:
   menu.popup();action(menu.get_popover(),'Unpin album').emit('clicked');phase=63
  elif phase==63 and not w.pin_rows:
   w.navigate(w.rows['library'].get_parent(),w.rows['library'])
   phase=60
  elif phase==60 and not w.loading_more:
   index=TimelineIndex(client.time_buckets())
   for key in list(index.ranges):index.apply(key,client.time_bucket(key))
   w.timeline_index=index;w.timeline_buckets=client.time_buckets();w.dates_ready=True
   texture=w.texture_from_pixels(decode_image(png))
   for item in items[:768]:w.texture_cache[w.texture_key(item)]=texture
   w.set_library_items(index.items);phase=7
  elif phase==7 and not w.loading_more and w.mosaic.rendered:
   busy.clear()
   old=w.mosaic;old_ids=[item.id for item in w.media_items]
   old.selected={1};old.selection_mode=True;old.update_selection()
   selection=old.tiles[1].media_item.id
   new=MediaItem('incoming','incoming.png',datetime(2026,12,25),1.5,metadata={'visibility':'timeline'})
   items.insert(0,new);client.block=True;gate.clear();entered.clear()
   w.refresh_remote();mark=time.monotonic();phase=8
  elif phase==8 and entered.is_set() and time.monotonic()-mark>.3:
   assert w.mosaic is old and [item.id for item in w.media_items]==old_ids
   assert not busy and all(tile.media_texture for tile in old.active_widgets & old.tile_set),(busy,[tile.media_item.id for tile in old.active_widgets & old.tile_set if not tile.media_texture])
   gate.set();client.block=False;phase=9
  elif phase==9 and w.mosaic is not old:
   assert all(not item.metadata.get('placeholder') for item in w.media_items)
   assert w.mosaic.motion_kind=='reflow' and w.mosaic.p<1
   assert {w.mosaic.tiles[i].media_item.id for i in w.mosaic.selected}=={selection}
   assert w.texture_key(new) in w.texture_cache
   freeze(.5);phase=10
  elif phase==10 and w.mosaic.rendered==w.mosaic.positions(w.mosaic.last_width)[0]:
   m=w.mosaic;target,_=m.target_layout(m.last_width)
   tile=next(tile for tile in m.tiles if tile.media_item.id=='incoming');rect=m.rendered[tile]
   assert abs(rect[4]-.5)<.01 and rect[2:4]==target[tile][2:4],(rect,target[tile])
   for tile in m.active_widgets & m.tile_set:
    if tile.media_item.id!='incoming':assert m.rendered[tile][4]==1 and tile.media_texture
   shot('upload-insertion-half');freeze(1);phase=11
  elif phase==11 and not w.loading_more:
   w.mosaic.set_selection(False);adjustment=w.scroller.get_vadjustment()
   adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size()-20);mark=time.monotonic();phase=12
  elif phase==12 and time.monotonic()-mark>.15:
   old=w.mosaic;top=w.scroller.get_vadjustment().get_value()
   visible=[tile for tile in old.active_widgets & old.tile_set if tile in old.rendered and old.rendered[tile][1]+old.rendered[tile][3]>=top]
   tile=min(visible,key=lambda tile:(old.rendered[tile][1],old.rendered[tile][0]));anchor=tile.media_item.id;offset=top-old.rendered[tile][1]
   items.insert(0,MediaItem('new-month','newmonth.png',datetime(2027,1,1),1.5,metadata={'visibility':'timeline'}))
   w.refresh_remote();phase=13
  elif phase==13 and w.mosaic is not old and not w.loading_more and not w.mosaic.tick:
   tile=next(tile for tile in w.mosaic.tiles if tile.media_item.id==anchor)
   top=w.scroller.get_vadjustment().get_value();assert abs(top-w.mosaic.rendered[tile][1]-offset)<=2,(top,w.mosaic.rendered[tile],offset)
   assert not busy and all(tile.media_texture for tile in w.mosaic.active_widgets & w.mosaic.tile_set)
   old=w.mosaic;items.insert(0,MediaItem('retry','retry.png',datetime(2027,1,2),1.5,metadata={'visibility':'timeline'}));client.fail=True
   w.refresh_remote();mark=time.monotonic();phase=14
  elif phase==14 and not w.timeline_refresh_pending and time.monotonic()-mark>.15:
   assert w.mosaic is old and 'retry' not in {item.id for item in w.media_items}
   client.fail=False;w.refresh_remote();phase=15
  elif phase==15 and w.mosaic is not old and not w.loading_more:
   assert 'retry' in {item.id for item in w.media_items} and not busy
   print('PINS VIA ELLIPSIS/REAL RIGHT CLICK/ROW; ACCOUNT PREFERENCES; EMPTY SECTION HIDDEN; EQUAL SECTION GAPS; BLOCKED UPLOAD RETAINS GRID; COMPLETE MONTH INSERTION FADES AT FULL SIZE; RAM TEXTURES/SELECTION/SCROLL ANCHOR; NEW MONTH; FAILURE/RETRY PASSED',flush=True)
   w.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);gate.set();w.close();app.quit();return False
 return True
def activate(app):
 global w
 Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
 css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
 w=GalleryWindow(app);w.set_default_size(1400,850);w.client=client;w.library_mode='immich'
 GLib.source_remove(w.refresh_timer);w.refresh_timer=0
 w.album_tree.set_albums(albums);w.current_page='albums';w.collection_cache['albums']=albums
 w.busy_library=lambda message:busy.append(message)
 collection_view(w,'albums');w.present();GLib.timeout_add(30,check)
app.connect('activate',activate);app.run([])
assert not errors
