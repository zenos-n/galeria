"""Offline native regression check; run under a private display with fatal GTK criticals."""
import os,sys,tempfile,time,calendar
from datetime import datetime
from io import BytesIO
from pathlib import Path
project=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(project))
root=tempfile.TemporaryDirectory(prefix='galeria-timeline-')
for key in ['XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME']:os.environ[key]=root.name+'/'+key
from PIL import Image
from app import *
from library import MediaItem
from cache import MediaCache
from imaging import decode_image
from layout import justified_rows
items=[];buckets=[]
for n in range(50):
 year=2026-n//12;month=12-n%12;key=f'{year}-{month:02}'
 buckets.append({'timeBucket':key+'-01','count':200})
 for i in range(200):items.append(MediaItem(key+'-'+str(i),key+f'-{i}.jpg',datetime(year,month,28-(i%28)),1.5))
blob=BytesIO();Image.new('RGB',(90,60),'purple').save(blob,format='PNG');blob=blob.getvalue()
class Client:
 token='fixture';user={'id':'fixture','name':'Fixture'};identity='fixture';base='http://example.invalid/api';locked_until=0;server_lock_pending=False;refresh_serial=0
 def __init__(self):self.downloads=[];self.bucket_calls=[];self.modern_search=True;self.calls=[];self.cache=MediaCache('timeline',root=root.name+'/cache')
 def media_cache(self):return self.cache
 def albums(self):return []
 def time_buckets(self,*args,**kwargs):return buckets
 def image_bytes(self,item,*args,**kwargs):
  self.downloads.append(item.id);time.sleep(.01);return blob
 def search(self,filters=None,query='',page=1,size=100):
  self.calls.append((dict(filters or {}),page,size));time.sleep(.04)
  selected=items
  if filters and filters.get('takenAfter'):selected=[i for i in items if filters['takenAfter'][:10]<=i.created.isoformat()[:10]<=filters['takenBefore'][:10]]
  if filters and filters.get('type')=='VIDEO':selected=[]
  offset=0 if page==1 else int(page)
  return selected[offset:offset+size],str(offset+size) if offset+size<len(selected) else None
 def image_key(self,*_):return 'fixture'
 def time_bucket(self,key,fresh=False):
  self.bucket_calls.append(key[:7]);time.sleep(.06)
  return [item for item in items if item.created.strftime('%Y-%m')==key[:7]]

app=Adw.Application(application_id='com.neg-zero.Galeria.IndexedTest',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=0;started=time.monotonic();errors=[]
def check():
 global phase,jumped,at_jump
 try:
  assert time.monotonic()-started<35,(phase,len(window.media_items),len(client.downloads))
  m=window.mosaic
  if phase==0 and len(window.media_items)==10000 and not window.loading_more:
   assert m.indexed and len(m.tiles)==10000
   full_height=sum(52+max((y+h for _,_,y,_,h in justified_rows([m.tiles[i].photo_ratio for i in range(a,b)],m.last_width,m.target)),default=0) for _,_,_,a,b in m.months)
   assert m.target_layout(m.last_width)[1]==full_height,(m.target_layout(m.last_width)[1],full_height)
   live=sum(tile.button is not None for tile in m.tiles)
   assert live<500,live
   assert live<=sum(tile.get_parent() is m for tile in m.tiles)<500
   assert len(m.rendered.keys() & m.tile_set)<500,len(m.rendered)
   adjustment=window.scroller.get_vadjustment();assert adjustment.get_upper()>100000,adjustment.get_upper()
   at_jump=len(client.downloads);adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size()-100);jumped=time.monotonic();phase=1
  elif phase==1 and time.monotonic()-jumped>2:
   live=sum(tile.button is not None for tile in m.tiles);assert live<500,live
   assert live<=sum(tile.get_parent() is m for tile in m.tiles)<500
   assert len(m.rendered.keys() & m.tile_set)<500,len(m.rendered)
   expected=m.months[-1][0]
   recent=client.downloads[-20:];assert recent and sum(id.startswith(expected) for id in recent)>=15,(expected,recent)
   assert not any(size==100 for _,_,size in client.calls),client.calls
   assert expected in client.bucket_calls
   scope=m.selection_months();m.select_all();assert m.selected and all(m.items[i].created.strftime('%Y-%m') in scope for i in m.selected)
   m.set_selection(False);assert not m.selected
   assert len(m._target_cache)<=4 and len(m._row_cache)<=384
   print('10000 sized slots; active native cells',live,'; full scroll height',round(window.scroller.get_vadjustment().get_upper()),'; jump prioritizes visible month',flush=True)
   window.switcher.set_active_name('months');phase=2
  elif phase==2 and not m.tick:
   window.switcher.set_active_name('years');phase=3
  elif phase==3 and m.tick and m.tier_groups:
   assert all(len(key)==4 for key,*_ in m.tier_groups),[g[0] for g in m.tier_groups]
   print('Month images grouped into',len(m.tier_groups),'years',flush=True);phase=4
  elif phase==4 and not m.tick:
   window.switcher.set_active_name('all');phase=5
  elif phase==5 and not m.tick and window.year_scrollbar.get_visible():
   rail=window.year_scrollbar;adjustment=window.scroller.get_vadjustment()
   assert isinstance(rail.bar,Gtk.Scrollbar) and not rail.hint_card.get_visible()
   rail.bar.get_adjustment().set_value(0);assert adjustment.get_value()==0
   rail.bar.get_adjustment().set_value(.96)
   assert abs(adjustment.get_value()-(adjustment.get_upper()-adjustment.get_page_size()))<1
   rail.motion(None,0,rail.get_height()/2);phase=6
  elif phase==6:
   rail=window.year_scrollbar;assert rail.hint_card.get_visible()
   rail.held=True;rail.leave();assert rail.hint_card.get_visible()
   rail.held=False;rail.leave();phase=7
  elif phase==7 and not window.year_scrollbar.hint_card.get_visible():
   window.close();app.quit();print('INDEXED LOD/VIRTUALIZATION/PRIORITY/GROUPS/YEAR RAIL PASSED',flush=True);return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);window.close();app.quit();return False
 return True
def activate(app):
 global window,client
 provider=Gtk.CssProvider();provider.load_from_path(str(project/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
 window=GalleryWindow(app);window.present();client=Client();window.connect_immich(client);GLib.timeout_add(50,check)
app.connect('activate',activate);app.run([])
assert not errors
