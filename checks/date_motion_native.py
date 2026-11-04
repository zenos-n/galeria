"""Exact shared glyph coordinates and fast-scroll toolbar-only fallback."""
import os,sys,time,tempfile
from pathlib import Path
from datetime import datetime
assert os.environ.get('DISPLAY')==':91'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
root=tempfile.TemporaryDirectory(prefix='galeria-date-motion-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
from app import *
from library import MediaItem
from PIL import Image
from imaging import decode_image
path=Path(root.name)/'photo.png';Image.new('RGB',(80,50),'purple').save(path)
items=[MediaItem(str(i),'photo.png',datetime(2016,8-i//80,25-i%20),1.6,path=str(path)) for i in range(160)]
app=Adw.Application(application_id='com.neg-zero.Galeria.DateMotionTest',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=0;start=time.monotonic();errors=[];steps=0;mark=0;positions=[]
def shot(name):
 snap=Gtk.Snapshot();Gtk.WidgetPaintable.new(w).snapshot(snap,w.get_width(),w.get_height());node=snap.to_node()
 if node:w.get_renderer().render_texture(node,Graphene.Rect().init(0,0,w.get_width(),w.get_height())).save_to_png('/tmp/gallery-app-identification/'+name+'.png')
def check():
 global phase,mark,steps,initial,positions
 try:
  assert time.monotonic()-start<15,(phase,w.date_motion.draws)
  motion=w.date_motion;scroll=w.scroller.get_vadjustment()
  if phase==0 and not w.loading_more and w.mosaic.rendered and motion.shared:
   heading,x,y,p=motion.shared;assert p<.02,(x,y,p)
   ok,source=heading.compute_point(motion,Graphene.Point().init(*heading.get_layout_offsets()));assert ok
   assert abs(x-source.x)<1 and abs(y-source.y)<1
   assert w.mosaic.floating_heading==heading and w.period.get_opacity()==0
   initial=(x,y);scroll.set_value(10);phase=1
  elif phase==1:
   heading,x,y,p=motion.shared
   if motion.pinned:phase=2;return True
   assert 0<p<1 and abs(y-(initial[1]-scroll.get_value()))<1,(initial,motion.shared,scroll.get_value())
   assert motion.draws[0][0] is heading.get_layout() and motion.draws[0][4] is None
   positions.append((x,y));shot('date-shared-middle');scroll.set_value(scroll.get_value()+10);steps+=1
   if motion.pinned:phase=2
  elif phase==2:
   assert motion.shared[3]==1 and len(motion.draws)==1
   shot('date-shared-header');scroll.set_value(20);phase=3
  elif phase==3:
   assert motion.shared and 0<motion.shared[3]<1
   scroll.set_value(0);phase=4
  elif phase==4:
   assert motion.shared[3]<.02 and abs(motion.shared[2]-initial[1])<1
   scroll.set_value(w.mosaic.month_extents['2016-07'][0]+200);phase=5
  elif phase==5:
   assert motion.shared is None and motion.pinned and w.period.get_label()=='July 2016'
   assert motion.draws and all(draw[4] is not None for draw in motion.draws)
   assert len({round(draw[1],1) for draw in motion.draws})==1
   shot('date-fast-header');mark=time.monotonic();phase=6
  elif phase==6 and time.monotonic()-mark>.25:
   assert not motion.motion and not motion.tick
   w.mosaic.set_selection(True);assert not motion.draws and w.mosaic.floating_heading is None
   assert all(positions[i][1]>positions[i+1][1] for i in range(len(positions)-1))
   print('ONE GLYPH RUN: EXACT SOURCE POSITION, SCROLL-LINKED Y, CONTINUOUS REVERSE, PINNED ENDPOINT; FAST JUMP CLIPS VERTICAL MOTION TO HEADER; SELECTION RELEASE PASSED',flush=True)
   w.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);w.close();app.quit();return False
 return True
def activate(app):
 global w
 css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
 w=GalleryWindow(app);w.set_default_size(1200,800);w.present();w.library_mode='local';w.local_items=items
 GLib.source_remove(w.refresh_timer);w.refresh_timer=0
 texture=w.texture_from_pixels(decode_image(path))
 for item in items:w.texture_cache[w.texture_key(item)]=texture
 w.set_library_items(items);GLib.timeout_add(80,check)
app.connect('activate',activate);app.run([]);assert not errors
