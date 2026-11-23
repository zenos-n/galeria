"""Real pointer toggles stay active; cached latest choice beats held stale work."""
import os,sys,time,tempfile,subprocess,json,threading
from unittest.mock import patch
from pathlib import Path
assert os.environ.get('DISPLAY')==':91'
root=tempfile.TemporaryDirectory(prefix='galeria-visibility-rapid-')
for key in ('HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
sys.path.insert(0,os.environ.get('GALERIA_CHECK_SOURCE_ROOT',str(Path(__file__).resolve().parents[1])))
from app import *
from visibility_fixture import Client
from timeline_visibility import TimelineVisibility
from timeline_visibility_ui import manage_visibility,rules
from timeline_index import TimelineIndex
from imaging import decode_image
from session_store import preferences_read
gi.require_version('GdkX11','4.0')
from gi.repository import GdkX11

class HeldClient(Client):
    fail_held=False
    old_failed=False
    def request(self,path,body=None,method=None,binary=False):
        held=path=='/search/metadata' and not self.gate.is_set()
        result=super().request(path,body,method,binary)
        if held and self.fail_held:
            self.fail_held=False;self.old_failed=True;raise LibraryError('Stale request failed')
        return result

application=Adw.Application(application_id='com.neg-zero.Galeria.RapidVisibilityCheck',flags=Gio.ApplicationFlags.NON_UNIQUE);application.register(None)
w=GalleryWindow(application);client=HeldClient();w.client=client;w.library_mode='immich';w.dates_ready=True
GLib.source_remove(w.refresh_timer);w.refresh_timer=0
w.preferences.setdefault('timeline_visibility',{})[client.identity]={'screenshots':True};w.save_preferences()
client.timeline_visibility=TimelineVisibility({'screenshots':True})
w.timeline_buckets=client.time_buckets();w.timeline_index=TimelineIndex(w.timeline_buckets)
for month in w.timeline_index.ranges:w.timeline_index.apply(month,client.time_bucket(month))
for item in w.timeline_index.items:w.texture_cache[w.texture_key(item)]=w.texture_from_pixels(decode_image(client.image_bytes(item)))
w.album_tree.set_albums(client.albums());w.set_library_items(w.timeline_index.items);w.present()
context=GLib.MainContext.default()
def pump(test,seconds=6):
    end=time.monotonic()+seconds
    while not test():
        assert time.monotonic()<end
        context.iteration(False);time.sleep(.001)
def descendants(widget):
    yield widget;child=widget.get_first_child()
    while child:
        yield from descendants(child);child=child.get_next_sibling()
try:
    pump(lambda:not w.loading_more and bool(w.mosaic.rendered));retained=w.texture_cache[('camera','')]
    dialog=manage_visibility(w)
    row=next(row for row in descendants(dialog) if isinstance(row,Adw.SwitchRow) and row.get_title()=='Downloads')
    switch=next(widget for widget in descendants(row) if isinstance(widget,Gtk.Switch))
    pump(lambda:switch.get_mapped() and switch.get_width()>0)
    until=time.monotonic()+.2;pump(lambda:time.monotonic()>until)
    paints=[];gaps=[time.monotonic()];feedback=[]
    clock=w.get_frame_clock();handler=clock.connect('after-paint',lambda *_:paints.append((time.monotonic(),row.get_active())))
    timer=GLib.timeout_add(10,lambda:(gaps.append(time.monotonic()),True)[1])
    tool='/tmp/gallery-app-identification/xdotool/bin/xdotool'
    def click(active):
        assert row.is_sensitive() and switch.is_sensitive(),'Background work disabled the folder controls'
        ok,bounds=switch.compute_bounds(w);assert ok
        dx,dy=w.get_surface_transform();xid=str(GdkX11.X11Surface.get_xid(w.get_surface()))
        started=time.monotonic()
        subprocess.run([tool,'windowfocus',xid,'mousemove','--window',xid,str(round(bounds.get_x()+bounds.get_width()/2+dx)),str(round(bounds.get_y()+bounds.get_height()/2+dy)),'click','1'],check=True)
        pump(lambda:row.get_active()==active and any(stamp>=started and value==active for stamp,value in paints))
        elapsed=(next(stamp for stamp,value in paints if stamp>=started and value==active)-started)*1000
        assert elapsed<400,elapsed;feedback.append(round(elapsed,1))
    client.gate.clear();client.waiting.clear();client.fail_held=True
    click(False);pump(client.waiting.is_set)
    click(True)
    pump(lambda:not w.timeline_visibility_pending and not w.loading_more)
    assert not client.gate.is_set(),'Fixture did not hold the obsolete request'
    assert {item.id for item in w.media_items}=={'camera','download'}
    assert rules(w)=={'screenshots':True,'albums':[]}
    assert w.visibility_update['previous'] is None and not w.visibility_update['callbacks']
    client.gate.set();pump(lambda:client.old_failed)
    until=time.monotonic()+.15;pump(lambda:time.monotonic()>until)
    assert row.get_active() and rules(w)=={'screenshots':True,'albums':[]},'Stale failure rolled back the latest selection'
    click(False);click(True);click(False)
    pump(lambda:not w.timeline_visibility_pending and not w.loading_more)
    assert [item.id for item in w.media_items]==['camera']
    assert preferences_read()['timeline_visibility'][client.identity]['albums']==['hidden']
    assert w.texture_cache[('camera','')] is retained and row.is_sensitive()
    import layout
    original=layout.prepare_timeline;planning=threading.Event();release=threading.Event()
    def held_plan(*args,**kwargs):
        planning.set();assert release.wait(6);return original(*args,**kwargs)
    with patch.object(layout,'prepare_timeline',side_effect=held_plan):
        click(True);pump(planning.is_set)
        assert {item.id for item in w.timeline_index.items}=={'camera','download'}
        assert [item.id for item in w.media_items]==['camera']
        with patch.object(client,'time_buckets',side_effect=LibraryError('Latest request unavailable')):
            click(False);pump(lambda:not w.timeline_visibility_pending and not w.loading_more)
        assert [item.id for item in w.timeline_index.items]==['camera'],'Failed latest update left the intermediate date index active'
        release.set()
    until=time.monotonic()+.2;pump(lambda:time.monotonic()>until)
    assert [item.id for item in w.media_items]==['camera'] and not row.get_active()
    print(json.dumps({'pointer_feedback_ms':feedback,'max_loop_gap_ms':round(max(b-a for a,b in zip(gaps,gaps[1:]))*1000,1),
                      'cached_latest_applied_before_stale_response':True,'stale_failure_ignored':True,'final_selection_applied':True,'partial_index_rollback':True}),flush=True)
    clock.disconnect(handler);GLib.source_remove(timer);dialog.close()
finally:client.gate.set();w.stop_data();w.destroy()
