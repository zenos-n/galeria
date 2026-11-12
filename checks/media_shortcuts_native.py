"""Actual key input routes selection/focus shortcuts once and respects editing guards."""
import os,sys,tempfile,time,subprocess
from pathlib import Path
from datetime import datetime,timedelta
assert os.environ.get('DISPLAY')==':91'
sys.path.insert(0,os.environ.get('GALERIA_CHECK_SOURCE_ROOT',str(Path(__file__).resolve().parents[1])))
root=tempfile.TemporaryDirectory(prefix='galeria-media-keys-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME','XDG_DATA_HOME'):os.environ[key]=root.name+'/'+key
from app import *
from panels import preferences
from library import ImmichClient,MediaItem
from imaging import decode_image
from PIL import Image
gi.require_version('GdkX11','4.0')
from gi.repository import GdkX11
path=Path(root.name)/'image.png';Image.new('RGB',(160,112),'purple').save(path);pixels=path.read_bytes()
class Client(ImmichClient):
    def __init__(self):super().__init__('https://fixture.invalid');self.user={'id':'fixture'};self.token='fixture';self.trashes=[]
    def image_bytes(self,*args,**kwargs):return pixels
    def trash_assets(self,ids):self.trashes.append(ids)
app=Adw.Application(application_id='com.neg-zero.Galeria.MediaKeysCheck',flags=Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
w=GalleryWindow(app);w.set_default_size(1200,800);w.client=Client();w.present()
GLib.source_remove(w.refresh_timer);w.refresh_timer=0
items=[MediaItem(str(i),'photo.png',datetime(2026,11,12)-timedelta(minutes=i),10/7) for i in range(4)]
texture=w.texture_from_pixels(decode_image(path))
for item in items:w.texture_cache[w.texture_key(item)]=texture
w.set_library_items(items);context=GLib.MainContext.default()
def pump(test):
    end=time.monotonic()+8
    while not test():
        assert time.monotonic()<end
        context.iteration(False);time.sleep(.002)
def key(value):
    xid=str(GdkX11.X11Surface.get_xid(w.get_surface()))
    subprocess.run(['/tmp/gallery-app-identification/xdotool/bin/xdotool','windowfocus',xid,'key','--clearmodifiers',value],check=True)
    until=time.monotonic()+.045;pump(lambda:time.monotonic()>=until)
calls=[];selected_action=w.selected_action;move_locked=w.move_selected_to_locked
w.selected_action=lambda action,items=None,target=None:calls.append((action,items,target))
w.move_selected_to_locked=lambda items=None,target=None:calls.append(('locked',items,target))
try:
    pump(lambda:not w.loading_more and bool(w.mosaic.rendered))
    w.mosaic.selected={0,1};w.mosaic.set_selection(True);pump(w.selection_bar.get_child_revealed)
    for focus in (False,True):
        if focus:
            w.open_viewer(0);pump(lambda:w.viewer.stage.progress==1 and w.viewer.photo_editor.original is not None)
            w.viewer.close_button.grab_focus()
        else:w.selection_controls['archive'].grab_focus()
        for shortcut,action in [('shift+a','archive'),('Delete','trash'),('shift+l','locked')]:
            before=len(calls);key(shortcut);assert len(calls)==before+1,(focus,shortcut,calls)
            actual,values,target=calls[-1];assert actual==action
            assert target is (getattr(w.viewer,'lock' if action=='locked' else action) if focus else w.selection_controls[action])
            assert [item.id for item in values]==['0'] if focus else values is None
        before=len(calls)
        for shortcut in ('ctrl+shift+a','alt+shift+l','shift+Delete'):key(shortcut)
        assert len(calls)==before
    viewer=w.viewer;before=len(calls)
    viewer.editing=True
    for shortcut in ('shift+a','Delete','shift+l'):key(shortcut)
    viewer.editing=False;assert len(calls)==before
    viewer.metadata_pending=True
    for shortcut in ('shift+a','Delete','shift+l'):key(shortcut)
    viewer.metadata_pending=False;assert len(calls)==before
    entry=Gtk.Entry(text='typed text',halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER)
    w.root_overlay.add_overlay(entry);entry.grab_focus()
    for shortcut in ('shift+a','Delete','shift+l'):key(shortcut)
    assert len(calls)==before and entry.get_text()!='typed text'
    w.root_overlay.remove_overlay(entry)
    preferences(w);pump(lambda:w.get_visible_dialog() is not None)
    for shortcut in ('shift+a','Delete','shift+l'):key(shortcut)
    assert len(calls)==before
    w.dialog.close();pump(lambda:w.get_visible_dialog() is None)
    viewer.close();pump(lambda:w.viewer is None)
    w.current_page='trash';w.mosaic.selected={0};w.mosaic.set_selection(True);w.selection_controls['trash'].grab_focus()
    key('Delete');assert len(calls)==before,'Delete restored an item from Trash'
    w.current_page='library';w.selected_action=selected_action;w.move_selected_to_locked=move_locked
    key('Delete');pump(lambda:isinstance(w.get_visible_dialog(),Adw.AlertDialog))
    assert not w.client.trashes and len(w.media_items)==len(items)
    dialog=w.get_visible_dialog();dialog.emit('response','cancel');dialog.close()
    pump(lambda:w.get_visible_dialog() is None);assert not w.client.trashes
    print('REAL SHIFT+A/DELETE/SHIFT+L IN SELECTION/FOCUS; ONE ACTION/CORRECT ICON; MODIFIER/TEXT/EDITOR/DIALOG/METADATA GUARDS; DELETE CONFIRMATION/CANCEL; NO RESTORE FROM TRASH PASSED',flush=True)
finally:w.stop_data();w.destroy()
