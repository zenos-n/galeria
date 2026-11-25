"""HDR originals survive photo/viewer/editor and 10-bit video presentation."""
import os,sys,tempfile,time,json,re,threading
from pathlib import Path
from datetime import datetime
fixture=tempfile.TemporaryDirectory(prefix='galeria-hdr-native-')
for key in ('HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):
    os.environ[key]=str(Path(fixture.name)/key);Path(os.environ[key]).mkdir()
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import *
from hdr_fixture import png,video,avif
from imaging import decode_texture,editor_pixels,decode_image
from video_ui import VideoPlayer
from library import MediaItem
root=Path(fixture.name)
paths=[png(root/'pq.png'),png(root/'hlg.png',(9,18,0,1)),png(root/'p3.png',(12,13,0,1))]
from PIL import Image
Image.new('RGB',(64,32),'purple').save(root/'sdr.png');paths.append(root/'sdr.png')
videos=[video(root/'pq.mp4','smpte2084'),video(root/'hlg.mp4','arib-std-b67')]
# The decoder must preserve native precision and CICP, including byte sources.
for p,primaries,transfer in zip(paths,[9,9,12,1],[16,18,13,13]):
    texture=decode_texture(p.read_bytes());params=texture.get_color_state().create_cicp_params()
    assert params.get_color_primaries()==primaries
    assert params.get_transfer_function()==transfer
    if p.name!='sdr.png':assert texture.get_format()==Gdk.MemoryFormat.R16G16B16
    assert editor_pixels(texture)[:2]==(64,32)
for name,transfer,tf in [('pq','smpte2084',16),('hlg','arib-std-b67',18)]:
    path=avif(root/(name+'.png'),root/(name+'.avif'),transfer)
    texture=decode_texture(path);params=texture.get_color_state().create_cicp_params()
    assert texture.get_format()==Gdk.MemoryFormat.R16G16B16
    assert params.get_color_primaries()==9 and params.get_transfer_function()==tf
items=[MediaItem(str(i),p.name,datetime(2026,11,25),2,path=str(p)) for i,p in enumerate(paths)]
app=Adw.Application(application_id='com.neg_zero.Galeria.HdrNative',flags=Gio.ApplicationFlags.NON_UNIQUE)
release=threading.Event();started=threading.Event()
phase=0;deadline=time.monotonic()+35;errors=[];player=None;video_index=0;frame_seen=False;gaps=[];feedback=[];last=time.monotonic()
def heartbeat():
    global last
    now=time.monotonic();gaps.append(now-last);last=now;return True

def check():
    global phase,player,video_index,clicked,frame_seen,local_item,held_at
    try:
        assert time.monotonic()<deadline,('HDR fixture timed out',phase)
        if phase==0 and w.mosaic.rendered:
            clicked=time.monotonic();w.open_viewer(0);phase=1
        elif phase==1:
            viewer=w.viewer;photo=viewer.photo_editor
            if not photo.original:return True
            assert viewer.stage.image.get_paintable().get_color_state().create_cicp_params().get_transfer_function()==16
            assert not viewer.stage.image_loading.get_visible()
            assert photo.source_texture==viewer.stage.image.get_paintable()
            if viewer.stage.progress<1:return True
            viewer.set_editing(True);phase=2
        elif phase==2:
            photo=w.viewer.photo_editor
            if photo.running or photo.debounce:return True
            assert w.viewer.stage.image.get_paintable().get_color_state().equal(Gdk.ColorState.get_srgb())
            assert 'SDR' in w.viewer.tool_message.get_label()
            w.viewer.set_editing(False);phase=3
        elif phase==3:
            photo=w.viewer.photo_editor
            if photo.running or photo.debounce:return True
            assert w.viewer.stage.image.get_paintable()==photo.source_texture
            w.viewer.move(1);phase=4
        elif phase==4:
            if not w.viewer.photo_editor.original:return True
            assert w.viewer.stage.image.get_paintable().get_color_state().create_cicp_params().get_transfer_function()==18
            if w.viewer.media_stack.get_transition_running():return True
            from io import BytesIO
            from cache import MediaCache
            from library import ImmichClient
            client=ImmichClient('https://fixture.invalid');client.token='fixture'
            storage=MediaCache('remote-hdr',root/'remote-cache');client.media_cache=lambda:storage
            def original(_):
                started.set();assert release.wait(3),'Metadata gate was not released'
                return BytesIO(paths[0].read_bytes())
            client.open_original=original
            client.thumbnail=lambda *_:(_ for _ in ()).throw(AssertionError('HDR source replaced by rendition'))
            local_item=w.viewer.source.media_item
            w.viewer.source.media_item=MediaItem('remote-hdr','hdr.png',datetime(2026,11,25),2,metadata={'visibility':'timeline'})
            w.client=client;held_at=time.monotonic()
            w.load_preview(w.viewer.stage,w.viewer.source)
            def painted(clock):
                if not feedback:feedback.append((time.monotonic()-held_at)*1000)
                clock.disconnect(paint_id)
            paint_id=w.get_frame_clock().connect('after-paint',painted)
            phase=41
        elif phase==41:
            assert w.viewer.stage.image_loading.get_visible()
            assert w.viewer.stage.image.get_paintable().get_color_state().create_cicp_params().get_transfer_function()==18
            if time.monotonic()-held_at<.32:return True
            assert started.is_set() and feedback and feedback[0]<400
            release.set();phase=42
        elif phase==42:
            if w.viewer.stage.image_loading.get_visible():return True
            assert w.viewer.stage.image.get_paintable().get_color_state().create_cicp_params().get_transfer_function()==16
            w.viewer.source.media_item=local_item;w.client=None
            w.viewer.close();phase=5
        elif phase==5:
            if w.viewer:return True
            # Real Clapper controls with our GTK sink; inspect actual presented frame.
            player=VideoPlayer(videos[video_index].as_uri(),w)
            w.root_overlay.add_overlay(player);player.play();phase=6
        elif phase==6:
            assert not player.error_label.get_visible(),player.error_label.get_label()
            sink=player.hdr_sink;caps=sink.get_static_pad('sink').get_current_caps()
            if caps is None:return True
            paint=sink.get_property('paintable');snapshot=Gtk.Snapshot();paint.snapshot(snapshot,320,180);node=snapshot.to_node()
            if node is None:return True
            text=node.serialize().get_data().decode()
            if 'texture {' not in text:return True
            transfer=16 if video_index==0 else 18
            assert re.search(r'transfer: '+str(transfer)+r';',text),text[:150]
            assert 'primaries: 9;' in text
            assert any(s in text for s in ['P010','YUV420_10','yuv420-10','yuv420_10']),text[:500]
            player.pause();player.stop();w.root_overlay.remove_overlay(player);video_index+=1
            if video_index<2:phase=5
            else:
                assert max(gaps)<.4,('UI loop stalled',max(gaps))
                print(json.dumps({'photos':'16-bit PQ/HLG PNG and AVIF, P3; SDR remains SDR','video':'10-bit PQ/HLG texture color states retained','editor':'SDR copy warning; original HDR restored','held_original_feedback_ms':round(feedback[0],1),'max_loop_gap_ms':round(max(gaps)*1000,1)}),flush=True)
                w.close();app.quit();return False
    except Exception as e:
        import traceback;traceback.print_exc();errors.append(e)
        if player:player.stop()
        w.close();app.quit();return False
    return True

def activate(app):
    global w
    w=GalleryWindow(app);w.library_mode='local';w.client=None;w.local_items=items
    GLib.source_remove(w.refresh_timer);w.refresh_timer=0
    texture=w.texture_from_pixels(decode_image(paths[0]))
    for item in items:w.texture_cache[w.texture_key(item)]=texture
    w.set_library_items(items);w.present();GLib.timeout_add(10,heartbeat);GLib.timeout_add(25,check)
app.connect('activate',activate);app.run([]);assert not errors
