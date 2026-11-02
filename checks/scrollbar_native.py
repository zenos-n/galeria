"""Real pointer/drag check on a private X11 display; requires xdotool."""
import os,sys,time,subprocess,shutil
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gi
for name,version in [('Gtk','4.0'),('Gdk','4.0'),('GdkX11','4.0'),('Adw','1')]:gi.require_version(name,version)
from gi.repository import Adw,Gdk,GdkX11,Gio,GLib,Graphene,Gtk
from year_scroll_ui import YearScrollbar
assert os.environ.get('DISPLAY')==':91','Use the private Xvfb :91 display'
xdotool=os.environ.get('GALERIA_XDOTOOL') or shutil.which('xdotool')
assert xdotool,'Set GALERIA_XDOTOOL to an xdotool executable'
app=Adw.Application(application_id='com.neg-zero.Galeria.ScrollbarCheck',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=0;start=time.monotonic();errors=[]

def input(*args):subprocess.run([xdotool,*map(str,args)],check=True,timeout=3)
def move(x,y):
 dx,dy=window.get_surface_transform()
 input('mousemove','--window',GdkX11.X11Surface.get_xid(window.get_surface()),round(x+dx),round(y+dy))
def bounds(widget):
 ok,rect=widget.compute_bounds(window);assert ok;return rect

def screenshot(name):
 directory=os.environ.get('GALERIA_CHECK_SHOTS')
 if not directory:return
 snap=Gtk.Snapshot();paint=Gtk.WidgetPaintable.new(window);paint.snapshot(snap,window.get_width(),window.get_height());node=snap.to_node()
 if node:
  rect=Graphene.Rect();rect.init(0,0,window.get_width(),window.get_height())
  window.get_renderer().render_texture(node,rect).save_to_png(str(Path(directory)/(name+'.png')))

def find(widget,name):
 if widget.get_css_name()==name:return widget
 child=widget.get_first_child()
 while child:
  found=find(child,name)
  if found:return found
  child=child.get_next_sibling()

def check():
 global phase,collapsed,expanded,full_width,rail_rect,first_hint,first_cursor
 try:
  assert time.monotonic()-start<20,(phase,rail.hovered,rail.held)
  if not rail.get_visible():return True
  if phase==0:
   move(100,100);phase=1
  elif phase==1:
   assert not rail.ticks.get_visible() and not rail.hint_card.get_visible()
   assert rail.bar.has_css_class('overlay-indicator') and not rail.bar.has_css_class('hovering')
   full_width=window.view.get_width();assert window.scroller.get_width()==full_width
   collapsed=rail.bar.get_width();rail_rect=bounds(rail);screenshot('scrollbar-rest')
   move(rail_rect.get_x()+rail_rect.get_width()/2,rail_rect.get_y()+rail_rect.get_height()*.25);phase=2
  elif phase==2:
   assert rail.hovered and rail.hint_card.get_visible() and rail.ticks.get_visible()
   expanded=rail.bar.get_width();assert expanded>collapsed,(collapsed,expanded)
   assert window.scroller.get_width()==full_width
   first_cursor=rail.pointer_y;first_hint=bounds(rail.hint_card).get_y()
   assert not rail.hint_layer.get_can_target() and not rail.hint_card.get_can_target()
   screenshot('scrollbar-hover')
   move(rail_rect.get_x()+rail_rect.get_width()/2,rail_rect.get_y()+rail_rect.get_height()*.75);phase=3
  elif phase==3:
   assert rail.pointer_y>first_cursor+rail.get_height()*.4
   assert bounds(rail.hint_card).get_y()>first_hint+rail.get_height()*.35
   assert abs(bounds(rail.hint_card).get_y()+rail.hint_card.get_height()/2-(rail_rect.get_y()+rail.pointer_y))<2
   slider=find(rail.bar,'slider');assert slider
   rect=bounds(slider);move(rect.get_x()+rect.get_width()/2,rect.get_y()+rect.get_height()/2)
   input('mousedown',1);phase=4
  elif phase==4:
   assert rail.held and rail.bar.has_css_class('dragging')
   move(rail_rect.get_x()+rail_rect.get_width()/2,rail_rect.get_y()+rail_rect.get_height()*.65);phase=5
  elif phase==5:
   assert rail.held and window.scroller.get_vadjustment().get_value()>0
   assert abs(bounds(rail.hint_card).get_y()+rail.hint_card.get_height()/2-(rail_rect.get_y()+rail.pointer_y))<2
   hint=bounds(rail.hint_card);move(hint.get_x()+hint.get_width()/2,hint.get_y()+hint.get_height()/2);phase=6
  elif phase==6:
   assert rail.held and not rail.hovered and rail.ticks.get_visible() and rail.hint_card.get_visible()
   node=window.pick(bounds(rail.hint_card).get_x()+rail.hint_card.get_width()/2,bounds(rail.hint_card).get_y()+rail.hint_card.get_height()/2,Gtk.PickFlags.DEFAULT)
   assert node is not rail.hint_card and node is not rail.hint
   before=window.scroller.get_vadjustment().get_value();window._before_hint_drag=before
   move(bounds(rail.hint_card).get_x()+rail.hint_card.get_width()/2,rail_rect.get_y()+rail.pointer_y+70);phase=8
  elif phase==8:
   assert rail.held and window.scroller.get_vadjustment().get_value()!=window._before_hint_drag
   input('mouseup',1);phase=7
  elif phase==7:
   assert not rail.held and not rail.hovered
   assert not rail.ticks.get_visible() and not rail.hint_card.get_visible()
   assert rail.bar.get_width()==collapsed,(rail.bar.get_width(),collapsed)
   assert window.scroller.get_width()==full_width
   print('REAL POINTER: overlay width preserved; native track/expansion',collapsed,'->',expanded,'; hint follows cursor/drag; ticks hide; release collapses',flush=True)
   window.close();app.quit();return False
 except Exception as error:
  import traceback;traceback.print_exc();errors.append(error);input('mouseup',1);window.close();app.quit();return False
 return True

def activate(app):
 global window,rail
 Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
 window=Adw.ApplicationWindow(application=app,default_width=800,default_height=700)
 window.scroller=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,hexpand=True,vexpand=True)
 canvas=Gtk.DrawingArea(height_request=60000)
 def draw(widget,context,width,height):
  context.set_source_rgb(.17,.17,.18);context.paint()
 canvas.set_draw_func(draw);window.scroller.set_child(canvas)
 window.mosaic=SimpleNamespace(indexed=True,mode='all',month_extents={'2026-01':(0,50000),'2018-01':(50000,60000)})
 rail=YearScrollbar(window);window.view=Gtk.Overlay(child=window.scroller);window.view.add_overlay(rail);rail.attach(window.view)
 window.set_content(window.view);window.present();GLib.timeout_add(250,check)
app.connect('activate',activate);app.run([]);assert not errors
