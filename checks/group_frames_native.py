"""Exact intermediate folder/card geometry and readable tier captions; private display only."""
import os,sys,tempfile,time
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import *
from timeline import Mosaic
from library import MediaItem
from PIL import Image,ImageDraw
app=Adw.Application(application_id='com.neg-zero.Galeria.GroupFramesTest',flags=Gio.ApplicationFlags.NON_UNIQUE)
items=[]
for month in range(120):
 year=2026-month//12;number=12-month%12
 for i in range(150):items.append(MediaItem(f'{month}-{i}',str(i),datetime(year,number,1),1.5))
phase=0;start=time.monotonic();errors=[];paints=[0];wait_paint=0
shots=Path(os.environ.get('GALERIA_CHECK_SHOTS','/tmp/gallery-app-identification'))
def freeze(value):
 global wait_paint
 if m.tick:m.remove_tick_callback(m.tick);m.tick=0
 m.p=value;m.queue_resize();w.queue_draw();wait_paint=paints[0]+1
def shot(name):
 snap=Gtk.Snapshot();Gtk.WidgetPaintable.new(w).snapshot(snap,w.get_width(),w.get_height());node=snap.to_node()
 if node:w.get_renderer().render_texture(node,Graphene.Rect().init(0,0,w.get_width(),w.get_height())).save_to_png(str(shots/(name+'.png')))
def check():
 global phase,direction
 try:
  assert time.monotonic()-start<20,phase
  if phase and (paints[0]<wait_paint or m.rendered!=m.positions(m.last_width)[0]):return True
  if phase==0 and m.rendered:
   m.expand_month(m.months[0][0]);freeze(.1);phase=1
  elif phase==1:
   check_folder();shot('groups-opening-tenth');freeze(1);phase=2
  elif phase==2:
   assert m.rendered[m.panel_month][3]>2000,(m.p,m.rendered[m.panel_month],m.last_width,m.target_layout(m.last_width)[0][m.panel_month])
   m.expand_month(m.months[0][0]);freeze(.5);phase=3
  elif phase==3:
   check_folder();shot('groups-closing-half');freeze(.9);phase=4
  elif phase==4:
   check_folder();shot('groups-closing-nine-tenths');freeze(1);phase=5
  elif phase==5:
   m.set_mode('all');freeze(.5);phase=6
  elif phase==6:
   check_captions();shot('groups-months-to-all-half');freeze(1);phase=7
  elif phase==7:
   m.set_mode('months');freeze(.5);phase=8
  elif phase==8:
   check_captions();shot('groups-all-to-months-half')
   m.expand_month(m.months[0][0]);freeze(.5);phase=12
  elif phase==12:
   target,_=m.target_layout(m.last_width)
   outgoing=[heading for heading in m.headings if heading in m.from_map and heading not in target]
   assert outgoing and all(abs(m.rendered[heading][4]-m.from_map[heading][4]*.5)<.01 for heading in outgoing)
   freeze(1);phase=13
  elif phase==13:
   m.expand_month(m.months[0][0]);freeze(1);phase=9
  elif phase==9:
   m.set_mode('years');freeze(.5);phase=10
  elif phase==10:
   check_captions();shot('groups-months-to-years-half');freeze(1);phase=11
  elif phase==11:
   print('ALL120 DATE CARDS RETAIN START GEOMETRY; EVERY LOWER ROW INTERPOLATES; PANEL GAP STAYS NONNEGATIVE; TIER CAPTIONS VISIBLE WITH COVER PICTURES HIDDEN; MID-FRAME SHOTS PASSED',flush=True)
   m.dispose();w.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);m.dispose();w.close();app.quit();return False
 return True
def check_folder():
 target,_=m.target_layout(m.last_width)
 cards=list(m.month_cards.values())
 assert all(card in m.from_map for card in cards)
 # Previously offscreen cards fell out of from_map and jumped near their final y.
 for card in cards:
  old=m.from_map[card];new=target[card];rect=m.rendered[card]
  assert abs(rect[1]-(old[1]+(new[1]-old[1])*m.p))<.01
 panel=m.rendered[m.panel_month];first_lower=cards[max(1,int((m.last_width-8+14)/164))]
 assert m.rendered[first_lower][1]>=panel[1]+panel[3]-.01,(m.p,panel,m.rendered[first_lower])
 assert sum(tile.button is not None for tile in m.tiles)<500
def check_captions():
 cards=[card for card in m.snapshot_widgets if card in m.card_pictures and m.rendered[card][4]>.1]
 assert cards
 assert all(card.get_opacity()>.1 for card in cards)
 assert all(picture.get_opacity()==0 for card in cards for picture in m.card_pictures[card])
def activate(app):
 global w,m
 Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
 css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
 w=Adw.ApplicationWindow(application=app,default_width=1400,default_height=850)
 m=Mosaic(lambda *_:None,items);m.mode='months';textures=[]
 colors=['#3a6070','#805048','#506048','#665080','#6b643a']
 for i in range(120):
  image=Image.new('RGBA',(160,100),colors[i%len(colors)]);draw=ImageDraw.Draw(image);draw.text((10,35),items[i*150].created.strftime('%B %Y'),fill='white')
  texture=Gdk.MemoryTexture.new(160,100,Gdk.MemoryFormat.R8G8B8A8,GLib.Bytes.new(image.tobytes()),640);textures.append(texture)
 for tile in m.tiles:
  texture=textures[tile.index//150];tile.media_texture=texture
  for picture in m.cover_slots.get(tile,[]):picture.set_paintable(texture)
 m.cached_texture=lambda item:textures[int(item.id.split('-')[0])]
 w.set_content(Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,child=m));w.present()
 w.get_frame_clock().connect('after-paint',lambda *_:paints.__setitem__(0,paints[0]+1));GLib.timeout_add(80,check)
app.connect('activate',activate);app.run([])
assert not errors
