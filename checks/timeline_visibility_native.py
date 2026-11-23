"""Real preference input stays responsive during filtering and preserves pixels."""
import os,sys,tempfile,time
from pathlib import Path
assert os.environ.get('DISPLAY')==':91'
root=tempfile.TemporaryDirectory(prefix='galeria-timeline-visibility-')
for key in ('HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
sys.path.insert(0,os.environ.get('GALERIA_CHECK_SOURCE_ROOT',str(Path(__file__).resolve().parents[1])))
from app import *
from visibility_fixture import Client
from timeline_index import TimelineIndex
from timeline_visibility_ui import preferences_group,update,manage_visibility
from startup_cache import restore
from imaging import decode_image
from library import MediaItem
from datetime import datetime
from session_store import preferences_read
from unittest.mock import patch

application=Adw.Application(application_id='com.neg-zero.Galeria.TimelineVisibilityCheck',flags=Gio.ApplicationFlags.NON_UNIQUE)
application.register(None)
css=Gtk.CssProvider();css.load_from_path(str(Path(sys.modules['app'].__file__).with_name('style.css')))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
window=GalleryWindow(application);client=Client();window.client=client
GLib.source_remove(window.refresh_timer);window.refresh_timer=0
window.library_mode='immich';window.dates_ready=True;window.album_tree.set_albums(client.albums())
window.timeline_buckets=client.time_buckets();window.timeline_index=TimelineIndex(window.timeline_buckets)
for month in window.timeline_index.ranges:window.timeline_index.apply(month,client.time_bucket(month))
for item in window.timeline_index.items:
    window.texture_cache[window.texture_key(item)]=window.texture_from_pixels(decode_image(client.image_bytes(item)))
window.set_library_items(window.timeline_index.items)
window.present();context=GLib.MainContext.default()
def pump(test,seconds=8):
    end=time.monotonic()+seconds
    while not test():
        assert time.monotonic()<end
        context.iteration(False);time.sleep(.001)
try:
    pump(lambda:not window.loading_more and bool(window.mosaic.rendered))
    retained=window.texture_cache[('camera','')]
    dialog=Adw.PreferencesDialog(title='Preferences');page=Adw.PreferencesPage();group=preferences_group(window)
    page.add(group);dialog.add(page);dialog.present(window)
    def descendants(widget):
        yield widget
        child=widget.get_first_child()
        while child:
            yield from descendants(child);child=child.get_next_sibling()
    switch=next(row for row in descendants(group) if isinstance(row,Adw.SwitchRow))
    client.gate.clear();started=time.monotonic();painted=[];heartbeats=[]
    clock=window.get_frame_clock();handler=clock.connect('after-paint',lambda *_:painted.append(time.monotonic()))
    timer=GLib.timeout_add(20,lambda:(heartbeats.append(time.monotonic()),True)[1])
    switch.set_active(True)
    pump(lambda:client.waiting.is_set() and bool(painted))
    assert (painted[0]-started)*1000<400
    assert window.timeline_visibility_pending and group.get_sensitive()
    until=time.monotonic()+.45;pump(lambda:time.monotonic()>=until)
    assert len(heartbeats)>=10,'Filtering blocked the UI loop'
    client.gate.set();pump(lambda:not window.timeline_visibility_pending and not window.loading_more)
    assert {item.id for item in window.media_items}=={'camera','download'}
    assert window.timeline_index.ranges.keys()=={'2026-11'}
    assert window.texture_cache[('camera','')] is retained
    assert preferences_read()['timeline_visibility'][client.identity]['screenshots'] is True
    assert {item.id for item in client.album('screens')}=={'shot','numeric'}
    assert len(client.search()[0])==5
    from pending_uploads import manager
    uploads=manager(window);entry=uploads.add(MediaItem('pasted','Screenshot new.png',datetime.now()))
    uploads.publish();pump(lambda:not window.loading_more)
    assert entry['item'].id not in {item.id for item in window.media_items}
    uploads.entries.clear();window.upload_previews=None
    window.search.inputs['Search in'].set_selected(1);window.search.entry.set_text('Screenshot')
    window.search_library();pump(lambda:not window.loading_more)
    assert 'shot' in {item.id for item in window.media_items},'Search inherited timeline exclusions'
    window.search.entry.set_text('');window.search.inputs['Search in'].set_selected(0)
    switch.set_active(False);pump(lambda:not window.timeline_visibility_pending and not window.loading_more)
    assert {item.id for item in window.media_items}=={a['id'] for a in client.assets}
    assert window.texture_cache[('camera','')] is retained
    values={'screenshots':True,'albums':['hidden']};update(window,values)
    pump(lambda:not window.timeline_visibility_pending and not window.loading_more)
    assert [item.id for item in window.media_items]==['camera']
    for mode in ('months','years'):
        window.switcher.set_active_name(mode);pump(lambda:not window.mosaic.tick)
        assert len(window.mosaic.months)==1
    client.timeline_visibility=type(client.timeline_visibility)(values)
    with patch.object(client,'request',side_effect=AssertionError('Network during cached restore')):
        bootstrap=restore(client,1000,700)
        assert bootstrap and {item.id for item in bootstrap[1].items}=={'camera'}
    dialog.close()
    manage=manage_visibility(window)
    rows=[row for row in descendants(manage) if isinstance(row,Adw.SwitchRow)]
    screenshots=next(row for row in rows if row.get_title()=='Pictures / Screenshots')
    assert not screenshots.get_active() and not screenshots.get_sensitive()
    downloads=next(row for row in rows if row.get_title()=='Downloads')
    assert not downloads.get_active();downloads.set_active(True)
    pump(lambda:not window.timeline_visibility_pending and not window.loading_more)
    assert {item.id for item in window.media_items}=={'camera','download'}
    until=time.monotonic()+.15;pump(lambda:time.monotonic()>=until)
    snapshot=Gtk.Snapshot();Gtk.WidgetPaintable.new(window).snapshot(snapshot,window.get_width(),window.get_height())
    window.get_renderer().render_texture(snapshot.to_node(),None).save_to_png('/tmp/galeria-visibility/preferences.png')
    manage.close()
    from collection_widgets import collection_menu
    menu=collection_menu(window,'albums',client.album_values[1],lambda:None)
    action=next(button for button in descendants(menu) if isinstance(button,Gtk.Button) and button.get_label()=='Hide from timeline')
    action.emit('clicked');pump(lambda:not window.timeline_visibility_pending and not window.loading_more)
    assert [item.id for item in window.media_items]==['camera']
    previous=client.timeline_visibility
    with patch.object(client,'time_buckets',side_effect=LibraryError('Fixture unavailable')):
        update(window,{'screenshots':False})
        pump(lambda:not window.timeline_visibility_pending and not window.loading_more)
    assert client.timeline_visibility is previous and preferences_read()['timeline_visibility'][client.identity]==values
    window.switcher.set_active_name('all');pump(lambda:not window.mosaic.tick)
    window.open_viewer(next(tile.index for tile in window.mosaic.tiles if tile.media_item.id=='camera'))
    pump(lambda:window.viewer and window.viewer.stage.progress==1 and not window.viewer.media_stack.get_transition_running())
    update(window,{'screenshots':True});pump(lambda:not window.timeline_visibility_pending)
    assert callable(window.pending_visibility_refresh)
    window.viewer.close();pump(lambda:window.viewer is None and not window.timeline_visibility_pending and not window.loading_more)
    assert {item.id for item in window.media_items}=={'camera','download'}
    local=GalleryWindow(application);local.library_mode='local'
    GLib.source_remove(local.refresh_timer);local.refresh_timer=0
    hidden=str(Path(root.name)/'hidden');keep=str(Path(root.name)/'keep')
    local.local_items=[MediaItem('local-hidden','file.jpg',datetime.now(),path=hidden+'/file.jpg'),MediaItem('local-keep','file.jpg',datetime.now(),path=keep+'/file.jpg')]
    for item in local.local_items:local.texture_cache[local.texture_key(item)]=retained
    local.present();local.search_library();pump(lambda:not local.loading_more)
    update(local,{'folders':[hidden]});pump(lambda:not local.timeline_visibility_pending and not local.loading_more)
    assert [item.id for item in local.media_items]==['local-keep'] and len(local.local_items)==2
    folders=manage_visibility(local)
    remove=next(button for button in descendants(folders) if isinstance(button,Gtk.Button) and button.get_tooltip_text()=='Show folder in timeline')
    remove.emit('clicked');pump(lambda:not local.timeline_visibility_pending and not local.loading_more)
    assert len(local.media_items)==2
    folders.close();local.stop_data();local.destroy()
    clock.disconnect(handler);GLib.source_remove(timer)
    print(f'Visibility native: switch feedback {(painted[0]-started)*1000:.1f}ms, slow-filter heartbeats {len(heartbeats)}, retained pixels/search/albums/uploads/groups/offline/failure/focus/local folders pass')
finally:
    client.gate.set();window.stop_data();window.destroy()
