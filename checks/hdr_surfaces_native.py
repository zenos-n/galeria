"""Wayland test: SDR UI parent, independent explicitly HDR media surfaces."""
import os,sys,tempfile,time,json,subprocess
from pathlib import Path
from datetime import datetime
private=tempfile.TemporaryDirectory(prefix='galeria-hdr-surfaces-')
for key in ('HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):
    os.environ[key]=private.name+'/'+key;Path(os.environ[key]).mkdir()
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import *
from hdr_fixture import png,video
from imaging import decode_image
from hdr_media import texture_hdr
from library import MediaItem
from PIL import Image
root=Path(private.name);Image.new('RGB',(64,32),'purple').save(root/'sdr.png')
paths=[root/'sdr.png',png(root/'pq.png',(9,16,0,1),(1920,1080)),png(root/'hlg.png',(9,18,0,1)),video(root/'pq.mp4','smpte2084'),video(root/'hlg.mp4','arib-std-b67')]
subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-f','lavfi','-i','testsrc2=size=160x90:rate=15','-t','2',
    '-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709',str(root/'sdr.mp4')],check=True)
paths.append(root/'sdr.mp4')
items=[MediaItem(str(i),p.name,datetime(2026,11,25),16/9,'VIDEO' if p.suffix=='.mp4' else 'IMAGE',str(p)) for i,p in enumerate(paths)]
app=Adw.Application(application_id='com.neg_zero.Galeria.HdrSurfaces',flags=Gio.ApplicationFlags.NON_UNIQUE)
phase=-1;deadline=time.monotonic()+30;errors=[];settled=0;gaps=[];last=time.monotonic()
def heartbeat():
    global last
    now=time.monotonic();gaps.append((phase,now-last));last=now;return True

def check():
    global phase,settled
    try:
        assert time.monotonic()<deadline,('Surface test timeout',phase)
        if phase==-1:
            if not w.mosaic.rendered:return True
            print('SURFACE PHASE SDR library',flush=True);w.open_viewer(0);phase=0;return True
        viewer=w.viewer;stage=viewer.stage
        if stage.progress<1 or viewer.media_stack.get_transition_running():return True
        if phase<3:
            if not viewer.photo_editor.original:return True
            expected=phase>0
            assert stage.image_offload.get_enabled()==(Gtk.GraphicsOffloadEnabled.ENABLED if expected else Gtk.GraphicsOffloadEnabled.DISABLED)
            assert texture_hdr(stage.image.get_paintable())==expected
        else:
            player=stage.video_player
            if player is None or player.hdr_sink.get_static_pad('sink').get_current_caps() is None:return True
            player.loop_switch.set_active(True)
            from hdr_media import video_transfer
            transfer=video_transfer(player.hdr_sink.get_static_pad('sink').get_current_caps())
            if phase<5 and transfer!=16:return True
            assert player.media_offload is not None
            expected=Gtk.GraphicsOffloadEnabled.ENABLED if phase<5 else Gtk.GraphicsOffloadEnabled.DISABLED
            if player.media_offload.get_enabled()!=expected:return True
            if phase==5:assert transfer is None and player.hlg_filter is None
            if player.video.get_opacity()<1:return True
        if not settled:
            settled=time.monotonic();print('SURFACE PHASE',paths[phase].name,flush=True);return True
        if time.monotonic()-settled<.6:return True
        print('SURFACE SETTLED',paths[phase].name,flush=True)
        phase+=1;settled=0
        if phase<len(paths):print('SURFACE BEGIN',paths[phase].name,flush=True);viewer.move(1);return True
        gtk=sorted(set(line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines() if '/libgtk-4.so.' in line))
        assert len(gtk)==1,gtk
        assert max(g for _,g in gaps)<.4,('UI loop exceeded 400ms',sorted(gaps,key=lambda a:a[1],reverse=True)[:3])
        print(json.dumps({'gtk':gtk,'max_loop_gap_ms':round(max(g for _,g in gaps)*1000,1),'largest_gaps':[(p,round(g*1000,1)) for p,g in sorted(gaps,key=lambda a:a[1],reverse=True)[:5]]}),flush=True)
        w.stop_data();w.destroy();app.quit();return False
    except Exception as e:
        import traceback;traceback.print_exc();errors.append(e);w.stop_data();w.destroy();app.quit();return False

def activate(app):
    global w
    css=Gtk.CssProvider();css.load_from_path(str(Path(__file__).resolve().parents[1]/'style.css'))
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    w=GalleryWindow(app);w.library_mode='local';w.client=None;w.local_items=items
    GLib.source_remove(w.refresh_timer);w.refresh_timer=0
    texture=w.texture_from_pixels(decode_image(root/'sdr.png'))
    for item in items:w.texture_cache[w.texture_key(item)]=texture
    w.set_library_items(items)
    m=next((m for m in Gdk.Display.get_default().get_monitors() if m.get_connector()=='DP-2'),None)
    if m and not os.environ.get('GALERIA_HDR_WINDOWED'):w.fullscreen_on_monitor(m)
    else:w.set_default_size(1200,820)
    w.present();GLib.timeout_add(10,heartbeat);GLib.timeout_add(25,check)
app.connect('activate',activate);app.run([]);assert not errors
