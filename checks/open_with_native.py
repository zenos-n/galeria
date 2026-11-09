"""Actual desktop Exec/GApplication handoff must preserve the Immich library."""
import os,sys,time,tempfile,subprocess
from pathlib import Path
from datetime import datetime
assert os.environ.get('DISPLAY')==':91'
sys.path.insert(0,os.environ.get('GALERIA_CHECK_SOURCE_ROOT',str(Path(__file__).resolve().parents[1])))
if '--desktop-client' not in sys.argv:
 root=tempfile.TemporaryDirectory(prefix='galeria-open-with-')
 for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
 runtime=Path(root.name)/'run';runtime.mkdir(mode=0o700);os.environ['XDG_RUNTIME_DIR']=str(runtime)
from app import *
from library import MediaItem,ImmichClient
from imaging import decode_image
import session_store
from session_store import preferences_write,PREFERENCES
from PIL import Image

class FixtureGallery(Gallery):
 def __init__(self):
  super().__init__();self.set_application_id('com.neg-zero.Galeria.OpenWithCheck');self.restores=0
 def do_startup(self):
  Gallery.do_startup(self);Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)


if '--desktop-client' in sys.argv:
 sys.exit(FixtureGallery().run([sys.argv[0],*sys.argv[2:]]))

folder=Path(root.name)/'device files';folder.mkdir()
photos=[folder/'first photo.png',folder/'second photo.png']
for path in photos:Image.new('RGB',(160,100),'purple').save(path)
clip=folder/'clip.mp4'
subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=purple:size=160x100:rate=10','-t','0.5','-pix_fmt','yuv420p','-threads','1',str(clip)],check=True)
saved={'mode':'immich','remember':True,'server':'https://fixture.invalid/api','user_id':'fixture','last_user':{'id':'fixture','name':'Fixture'},'folders':['/previous/device/folder']}
preferences_write(saved);before=PREFERENCES.read_bytes()
cached=ImmichClient(saved['server']);cached.user=saved['last_user'];cached.media_cache().put('profile:fixture:',photos[0].read_bytes())
items=[MediaItem(str(i),'remote.png',datetime(2026,11,1),1.6,path=str(photos[0])) for i in range(40)]
class Client(ImmichClient):
 def __init__(self):super().__init__(saved['server']);self.token='fixture';self.user=saved['last_user'].copy()
 def profile_image(self,**kwargs):return photos[0].read_bytes()
 def request(self,*args,**kwargs):raise AssertionError('Opening device files must not issue remote account requests')
def restore(window,done=None):
 assert window.preferences['mode']=='immich' and window.preferences['remember']
 window.get_application().restores+=1;window.client=Client();window.library_mode='immich';window.update_account_ui()
 GLib.source_remove(window.refresh_timer);window.refresh_timer=0
 texture=window.texture_from_pixels(decode_image(photos[0]))
 for item in items:window.texture_cache[window.texture_key(item)]=texture
 window.set_library_items(items)
 if done:done()
 return False
GalleryWindow.restore_last_library=restore
app=FixtureGallery();app.register(None)
def pump(until,timeout=15):
 deadline=time.monotonic()+timeout;context=GLib.MainContext.default()
 while not until():
  assert time.monotonic()<deadline,'Timed out'
  context.iteration(False);time.sleep(.005)
 for _ in range(4):context.iteration(False)
desktop=Path(root.name)/'galeria-open-with.desktop'
desktop.write_text('[Desktop Entry]\nType=Application\nName=Galeria fixture\nExec='+GLib.shell_quote(sys.executable)+' '+GLib.shell_quote(__file__)+' --desktop-client %U\nTerminal=false\nMimeType=image/png;video/mp4;\n')
launcher=Gio.DesktopAppInfo.new_from_filename(str(desktop));assert launcher
def walk(widget):
 yield widget
 child=widget.get_first_child()
 while child:yield from walk(child);child=child.get_next_sibling()
def snapshot(window,name):
 snap=Gtk.Snapshot();Gtk.WidgetPaintable.new(window).snapshot(snap,window.get_width(),window.get_height());node=snap.to_node()
 texture=window.get_renderer().render_texture(node,Graphene.Rect().init(0,0,window.get_width(),window.get_height()))
 path='/tmp/gallery-app-identification/'+name+'.png';texture.save_to_png(path);return Image.open(path).convert('RGB')
def windows():return [window for window in app.get_windows() if isinstance(window,GalleryWindow)]
def launch(paths,focused=True):
 previous=set(windows());assert launcher.launch([Gio.File.new_for_path(str(path)) for path in paths],None)
 pump(lambda:bool(set(windows())-previous))
 window=next(iter(set(windows())-previous))
 pump(lambda:not window.loading_more and bool(window.media_items) and (not focused or window.viewer is not None and window.viewer.stage.progress==1))
 return window
try:
 first=launch([photos[0]])
 heading=next(widget for widget in walk(first) if isinstance(widget,Gtk.Label) and widget.get_label()=='Collections')
 assert heading.get_style_context().get_margin().left==18,'Cold Open With omitted sidebar CSS'
 pump(lambda:not first.viewer.stage.tick)
 image=snapshot(first,'open-with-cold-focus-0143')
 assert max(image.getpixel((first.get_width()-12,150)))<20,'Cold Open With omitted focus darkening'
 assert first.avatar.get_text()=='Fixture','Preview lost remembered account identity'
 pump(lambda:first.avatar.get_custom_image() is not None)
 assert first.client is None,'Device-file actions must not use the cloud client'
 for widget in (first.viewer.lock,first.viewer.trash,first.viewer.archive,first.viewer.fullscreen_button,first.viewer.share,first.viewer.download):
  ok,bounds=widget.compute_bounds(first);assert ok and bounds.get_x()+bounds.get_width()<first.get_width()/2,widget.get_tooltip_text()
 for widget in (first.viewer.info,first.viewer.edit_button):
  ok,bounds=widget.compute_bounds(first);assert ok and bounds.get_x()>first.get_width()/2

 assert PREFERENCES.read_bytes()==before,'Open With replaced saved Immich preferences'
 assert app.window is None and not app.restores and first.external_preview
 assert first.viewer.source.media_item.path==str(photos[0])
 first.viewer.close();pump(lambda:first.viewer is None);first.refresh_library()
 pump(lambda:not first.loading_more and bool(first.media_items));assert PREFERENCES.read_bytes()==before
 first.account_menu()
 open_library=next(widget for widget in walk(first.account_button.get_popover()) if isinstance(widget,Gtk.Button) and widget.get_label()=='Open Immich library')
 open_library.emit('clicked');pump(lambda:app.window is not None and app.window.client is not None and not app.window.loading_more)
 main=app.window;client=main.client;mosaic=main.mosaic;media=main.media_items;main.current_page='favorites'
 main.texture_cache[('keep','fixture')]=main.texture_from_pixels(decode_image(photos[0]))
 main.scroller.get_vadjustment().set_value(80);position=main.scroller.get_vadjustment().get_value()
 second=launch([photos[1]]);video=launch([clip]);batch=launch(photos,False);directory=launch([folder],False)
 assert app.window is main and main.client is client and client.token=='fixture'
 assert main.mosaic is mosaic and main.media_items is media and main.current_page=='favorites'
 assert ('keep','fixture') in main.texture_cache and main.scroller.get_vadjustment().get_value()==position
 assert PREFERENCES.read_bytes()==before and main.preferences==saved
 assert second.avatar.get_text()=='Fixture' and second.client is None
 pump(lambda:second.avatar.get_custom_image() is not None)
 route=[];open_library=app.open_library;app.open_library=lambda page=None:route.append(page)
 second.navigate(second.rows['library'].get_parent(),second.rows['library'])
 app.open_library=open_library;assert route==['library'] and second.client is None
 main.client=None;main.preferences.update(mode=None,remember=False);main.update_account_ui()
 assert second.avatar.get_text()=='Galeria' and second.avatar.get_custom_image() is None
 main.client=client;main.preferences.update(saved);main.update_account_ui()
 assert second.avatar.get_text()=='Fixture'
 assert second.viewer.source.media_item.path==str(photos[1]) and video.viewer.source.media_item.kind=='VIDEO'
 assert len(batch.media_items)==2 and len(directory.media_items)==3
 app.set_background(True)
 for preview in [first,second,video,batch,directory]:preview.close()
 pump(lambda:all(preview.data_stopped for preview in [first,second,video,batch,directory]))
 assert windows()==[main] and main.client is client and PREFERENCES.read_bytes()==before
 app.activate();assert app.window is main and app.restores==1
 # Explicit Choose folders retains its existing persistent-library behavior.
 main.connect_local([str(folder)]);pump(lambda:not main.loading_more and len(main.media_items)==3)
 assert session_store.preferences_read()['mode']=='local' and session_store.preferences_read()['folders']==[str(folder)]
 preview=launch([photos[0]]);preview.viewer.set_editing(True);editor=preview.viewer.photo_editor
 pump(lambda:editor.original is not None);editor.values['Brightness']=20;editor.queue(0)
 app.force_quit();pump(lambda:preview.viewer.exit_dialog is not None)
 assert not app.quitting and not main.data_stopped
 dialog=preview.viewer.exit_dialog;dialog.emit('response','cancel');dialog.close()
 assert preview.viewer.editing and not main.data_stopped
 app.force_quit();pump(lambda:preview.viewer.exit_dialog is not None)
 dialog=preview.viewer.exit_dialog;dialog.emit('response','discard');dialog.close()
 pump(lambda:not windows());assert main.data_stopped and preview.data_stopped
 print('DESKTOP OPEN WITH: COLD CSS/BACKDROP/LEFT ACTIONS; CACHED/LIVE ACCOUNT/AVATAR/PRIMARY LIBRARY ROUTING/SIGNOUT; COLD/WARM IMAGE/VIDEO/MULTI/FOLDER PREVIEWS/REFRESH KEEP SAVED IMMICH ACCOUNT AND LIVE CLIENT/GRID/CACHE/SCROLL; BACKGROUND CLOSE DISPOSES; EXPLICIT FOLDERS PERSIST; QUIT GUARDS/CLEANS ALL WINDOWS PASSED',flush=True)
finally:
 for window in windows():window.stop_data();window.destroy()
 app.quit()
