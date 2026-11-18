"""GNOME button choices override stale GTK layouts and update without write-back."""
import os,sys,tempfile,time
from pathlib import Path

root=tempfile.TemporaryDirectory(prefix='galeria-window-controls-')
for key in ('HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):
    os.environ[key]=str(Path(root.name)/key)
os.environ['GSETTINGS_BACKEND']='memory'
desktop=sys.argv[1] if len(sys.argv)>1 else 'GNOME'
os.environ['XDG_CURRENT_DESKTOP']=desktop
sys.path.insert(0,os.environ.get('GALERIA_CHECK_SOURCE_ROOT',str(Path(__file__).resolve().parents[1])))
from app import *

Adw.init()
settings=Gio.Settings.new('org.gnome.desktop.wm.preferences')
settings.set_string('button-layout',':close')
gtk=Gtk.Settings.get_default()
gtk.set_property('gtk-decoration-layout',':minimize,maximize,close')
application=Gallery()
application.set_application_id('com.neg-zero.Galeria.WindowControlsCheck')
application.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
started=time.monotonic()
application.register(None)
gnome='GNOME' in desktop.split(':')
assert gtk.get_property('gtk-decoration-layout')==(':close' if gnome else ':minimize,maximize,close')
window=GalleryWindow(application)
window.present()
context=GLib.MainContext.default()

def controls(widget):
    found=[]
    if isinstance(widget,Gtk.Button) and widget.get_mapped():
        found.extend(name for name in ('close','minimize','maximize') if widget.has_css_class(name))
    child=widget.get_first_child()
    while child:
        found.extend(controls(child));child=child.get_next_sibling()
    return found

def wait_for(expected):
    started=time.monotonic();end=started+2
    while controls(window)!=expected:
        assert time.monotonic()<end,(controls(window),expected)
        context.iteration(False);time.sleep(.001)
    assert time.monotonic()-started<.4,'Window controls took more than 400ms to update'

try:
    wait_for(['close'] if gnome else ['minimize','maximize','close'])
    feedback_ms=(time.monotonic()-started)*1000
    assert feedback_ms<400,feedback_ms
    if gnome:
        settings.set_string('button-layout','close:')
        wait_for(['close'])
        assert gtk.get_property('gtk-decoration-layout')=='close:'
        settings.set_string('button-layout',':minimize,maximize,close')
        wait_for(['minimize','maximize','close'])
        settings.set_string('button-layout',':close')
        wait_for(['close'])
        window.set_default_size(660,700)
        end=time.monotonic()+2
        while not window.split.get_collapsed():
            assert time.monotonic()<end
            context.iteration(False);time.sleep(.001)
        settings.set_string('button-layout','close:')
        wait_for(['close'])
        settings.set_string('button-layout',':close')
        wait_for(['close'])
        gtk.set_property('gtk-decoration-layout',':maximize,close')
        assert settings.get_string('button-layout')==':close','Layout binding wrote into desktop preferences'
    else:
        settings.set_string('button-layout','close:')
        assert gtk.get_property('gtk-decoration-layout')==':minimize,maximize,close'
    print(f'{desktop}: native controls, startup/live settings and read-only binding pass; first mapped controls {feedback_ms:.1f}ms')
finally:
    window.stop_data();window.destroy()
