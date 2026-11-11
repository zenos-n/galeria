"""Large-library bulk archive paints before HTTP acknowledgement and reuses cells."""
import json
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

assert os.environ.get('DISPLAY') == ':91'
sys.path.insert(0, os.environ.get('GALERIA_CHECK_SOURCE_ROOT', str(Path(__file__).resolve().parents[1])))
root = tempfile.TemporaryDirectory(prefix='galeria-bulk-archive-')
for key in ('XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_STATE_HOME'):
    os.environ[key] = root.name + '/' + key

from app import *
from imaging import decode_image
from library import ImmichClient, MediaItem
from timeline_index import TimelineIndex
from PIL import Image

gi.require_version('GdkX11', '4.0')
from gi.repository import GdkX11

release = threading.Event()
received = threading.Event()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_PUT(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert self.path == '/api/assets' and body['visibility'] == 'archive'
        received.set()
        assert release.wait(12)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'[]')


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
app = Adw.Application(application_id='com.neg-zero.Galeria.BulkArchive', flags=Gio.ApplicationFlags.NON_UNIQUE)
app.register(None)
css = Gtk.CssProvider()
css.load_from_path(str(Path(sys.modules['app'].__file__).with_name('style.css')))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
w = GalleryWindow(app)
w.set_default_size(1400, 900)
w.present()
w.client = ImmichClient(f'http://127.0.0.1:{server.server_port}')
w.client.user = {'id': 'fixture'}
w.client.token = 'fixture'
GLib.source_remove(w.refresh_timer)
w.refresh_timer = 0
context = GLib.MainContext.default()
count = int(os.environ.get('GALERIA_BULK_ITEMS', '8000'))
items = [MediaItem(str(i), 'photo.png', datetime(2026, 11, 30)-timedelta(minutes=i), 10/7) for i in range(count)]
path = Path(root.name) / 'photo.png'
Image.new('RGB', (100, 70), 'purple').save(path)
texture = w.texture_from_pixels(decode_image(path))
for item in items[:600]:
    w.texture_cache[w.texture_key(item)] = texture
started = None
painted = None
selected = 0
samples = []


def pump(until, timeout=12):
    deadline = time.monotonic()+timeout
    while not until():
        assert time.monotonic() < deadline, ('Bulk archive timed out', selected, len(w.media_items))
        context.iteration(False)
        time.sleep(.002)


def frame(*_):
    global painted
    motion = getattr(w, 'action_motion', None)
    if started and painted is None and motion and motion.frames and motion.get_mapped() and len(w.media_items) == count-selected:
        painted = (time.monotonic()-started)*1000


try:
    pump(w.get_mapped)
    w.get_frame_clock().connect('after-paint', frame)
    for selected in (20, 2, 200):
        for repeat in range(3):
            index = TimelineIndex([{'timeBucket': '2026-11-01', 'count': count}])
            index.apply('2026-11', items)
            w.timeline_index = index
            w.timeline_buckets = [{'timeBucket': '2026-11-01', 'count': count}]
            w.set_library_items(index.items, append=True, reflow=True)
            pump(lambda: not w.loading_more and not w.mosaic.tick and bool(w.mosaic.rendered))
            w.mosaic.selected = set(range(selected))
            w.mosaic.set_selection(True)
            pump(w.selection_bar.get_child_revealed)
            before = {tile.media_item.id: tile for tile in w.mosaic.tiles}
            target = w.selection_controls['archive']
            ok, bounds = target.compute_bounds(w)
            assert ok and target.get_mapped()
            dx, dy = w.get_surface_transform()
            xid = str(GdkX11.X11Surface.get_xid(w.get_surface()))
            received.clear()
            release.clear()
            painted = None
            started = time.monotonic()
            subprocess.run(['/tmp/gallery-app-identification/xdotool/bin/xdotool', 'windowfocus', xid,
                            'mousemove', '--window', xid,
                            str(round(bounds.get_x()+bounds.get_width()/2+dx)),
                            str(round(bounds.get_y()+bounds.get_height()/2+dy)), 'click', '--delay', '0', '1'], check=True)
            pump(lambda: painted is not None, .4)
            assert painted < 400, painted
            samples.append({'selected': selected, 'paint_ms': round(painted, 2)})
            print(json.dumps(samples[-1]), flush=True)
            assert all(before[tile.media_item.id] is tile for tile in w.mosaic.tiles), 'Bulk removal rebuilt unchanged cells'
            pump(received.is_set)
            assert not release.is_set()
            release.set()
            pump(lambda: not w.pending_mutations and not w.action_motions and not w.mosaic.tick)
            started = None
    print(json.dumps({'items': count, 'median_paint_ms': statistics.median(sample['paint_ms'] for sample in samples), 'samples': samples}), flush=True)
finally:
    release.set()
    server.shutdown()
    server.server_close()
    w.stop_data()
    w.destroy()
