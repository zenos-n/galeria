"""Check feedback and loop gaps for a 45k-item visibility rule update."""
import os,sys,time,tempfile,json
from pathlib import Path
from datetime import datetime,timedelta
assert os.environ.get('DISPLAY')==':91'
root=tempfile.TemporaryDirectory(prefix='galeria-visibility-large-')
for key in ('HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):os.environ[key]=root.name+'/'+key
sys.path.insert(0,os.environ.get('GALERIA_CHECK_SOURCE_ROOT',str(Path(__file__).resolve().parents[1])))
from app import *
from visibility_fixture import Client
from timeline_index import TimelineIndex
from timeline_visibility_ui import update
from imaging import decode_image
from library import MediaItem
from startup_cache import restore
client=Client();client.assets=[];client.album_values=[]
for i in range(45490):
    date=datetime(2026,11,23)-timedelta(days=i//5)
    client.assets.append({'id':str(i),'originalFileName':f'Screenshot-{i}.png' if i%8==0 else f'Photo-{i}.jpg',
                         'fileCreatedAt':date.isoformat()+'Z','localDateTime':date.isoformat(),'type':'IMAGE','visibility':'timeline',
                         'width':150,'height':100,'albums':[]})
application=Adw.Application(application_id='com.neg-zero.Galeria.VisibilityLargeCheck',flags=Gio.ApplicationFlags.NON_UNIQUE);application.register(None)
window=GalleryWindow(application);window.client=client;window.library_mode='immich';window.dates_ready=True
GLib.source_remove(window.refresh_timer);window.refresh_timer=0
window.timeline_buckets=client.time_buckets();window.timeline_index=TimelineIndex(window.timeline_buckets)
newest=next(iter(window.timeline_index.ranges));window.timeline_index.apply(newest,client.time_bucket(newest))
texture=window.texture_from_pixels(decode_image(client.image_bytes(window.timeline_index.items[0])))
for item in window.timeline_index.items[:300]:window.texture_cache[window.texture_key(item)]=texture
window.set_library_items(window.timeline_index.items);window.present();context=GLib.MainContext.default()
def pump(test):
    end=time.monotonic()+30
    while not test():
        assert time.monotonic()<end
        context.iteration(False);time.sleep(.001)
try:
    pump(lambda:not window.loading_more and bool(window.mosaic.rendered))
    marks=[time.monotonic()];painted=[]
    timer=GLib.timeout_add(10,lambda:(marks.append(time.monotonic()),True)[1])
    clock=window.get_frame_clock();handler=clock.connect('after-paint',lambda *_:painted.append(time.monotonic()))
    started=time.monotonic();update(window,{'screenshots':True})
    pump(lambda:not window.timeline_visibility_pending and not window.loading_more)
    end=time.monotonic()+.2;pump(lambda:time.monotonic()>end)
    result={'items_before':45490,'items_after':len(window.media_items),'feedback_ms':round((painted[0]-started)*1000,1),
            'max_loop_gap_ms':round(max(b-a for a,b in zip(marks,marks[1:]))*1000,1),'retained_texture':window.texture_cache[('1','')] is texture}
    print(json.dumps(result),flush=True)
    assert result['feedback_ms']<400 and result['max_loop_gap_ms']<400,result
    assert result['items_after']==45490-len(client.timeline_visibility.ids)
    marks[:]=[time.monotonic()];painted.clear();started=time.monotonic()
    update(window,{})
    pump(lambda:not window.timeline_visibility_pending and not window.loading_more)
    result={'restored_items':len(window.media_items),'feedback_ms':round((painted[0]-started)*1000,1),'max_loop_gap_ms':round(max(b-a for a,b in zip(marks,marks[1:]))*1000,1)}
    print(json.dumps(result),flush=True)
    assert result['restored_items']==45490 and result['feedback_ms']<400 and result['max_loop_gap_ms']<400,result
    update(window,{'screenshots':True});pump(lambda:not window.timeline_visibility_pending and not window.loading_more)
    clock.disconnect(handler);GLib.source_remove(timer)
    restored=[]
    window.background(lambda:restore(client,1040,700),restored.append)
    pump(lambda:bool(restored));bootstrap=restored[0];assert bootstrap
    started=time.monotonic();cold=GalleryWindow(application);created=time.monotonic();GLib.source_remove(cold.refresh_timer);cold.refresh_timer=0
    cold.client=client;cold.library_mode='immich';cold.dates_ready=True;cold.timeline_buckets,cold.timeline_index,_pixels=bootstrap
    cold.set_library_items(cold.timeline_index.items,prepared=cold.timeline_index.prepared);applied=time.monotonic();cold.present()
    marks=[time.monotonic()];timer=GLib.timeout_add(10,lambda:(marks.append(time.monotonic()),True)[1])
    pump(lambda:cold.get_mapped())
    feedback_ms=(time.monotonic()-started)*1000
    assert cold.stack.get_visible_child_name()=='library' or cold.status.get_title()=='Preparing timeline…'
    cold.navigate(cold.rows['library'].get_parent(),cold.rows['library'])
    pump(lambda:not cold.loading_more and cold.mosaic.get_mapped() and bool(cold.mosaic.rendered))
    cold_ms=(time.monotonic()-started)*1000;gap=max(b-a for a,b in zip(marks,marks[1:]))*1000
    print(json.dumps({'cached_window_items':len(cold.media_items),'cached_first_feedback_ms':round(feedback_ms,1),'cached_grid_ready_ms':round(cold_ms,1),'max_loop_gap_ms':round(gap,1)}),flush=True)
    assert feedback_ms<400 and gap<400,(feedback_ms,gap)
    GLib.source_remove(timer)
    cold.client=None;cold.stop_data();cold.destroy()
    local=GalleryWindow(application);GLib.source_remove(local.refresh_timer);local.refresh_timer=0;local.library_mode='local'
    local.local_items=[MediaItem(str(i),f'Photo-{i}.jpg',datetime(2026,11,23),path=str(Path(root.name)/('hidden' if i%2==0 else 'keep')/f'{i}.jpg')) for i in range(45490)]
    for item in local.local_items[:300]:local.texture_cache[local.texture_key(item)]=texture
    local.search_library();local.present();pump(lambda:not local.loading_more and bool(local.mosaic.rendered))
    marks=[time.monotonic()];painted=[];started=time.monotonic()
    timer=GLib.timeout_add(10,lambda:(marks.append(time.monotonic()),True)[1]);clock=local.get_frame_clock();handler=clock.connect('after-paint',lambda *_:painted.append(time.monotonic()))
    update(local,{'folders':[str(Path(root.name)/'hidden')]})
    pump(lambda:not local.timeline_visibility_pending and not local.loading_more)
    result={'local_items':45490,'local_visible_items':len(local.filtered_local),'feedback_ms':round((painted[0]-started)*1000,1),'max_loop_gap_ms':round(max(b-a for a,b in zip(marks,marks[1:]))*1000,1)}
    print(json.dumps(result),flush=True)
    assert result['feedback_ms']<400 and result['max_loop_gap_ms']<400 and result['local_visible_items']==22745,result
    clock.disconnect(handler);GLib.source_remove(timer);local.stop_data();local.destroy()
finally:window.stop_data();window.destroy()
