"""Real pointer input, held HTTP replies and painted concurrent focus/removal."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

assert os.environ.get('DISPLAY') == ':91'
sys.path.insert(0, os.environ.get('GALERIA_CHECK_SOURCE_ROOT', str(Path(__file__).resolve().parents[1])))
root = tempfile.TemporaryDirectory(prefix='galeria-optimistic-actions-')
for key in ('XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_STATE_HOME'):
    os.environ[key] = root.name + '/' + key

from app import *
from imaging import decode_image
from library import ImmichClient, MediaItem
from timeline_index import TimelineIndex
from PIL import Image

gi.require_version('GdkX11', '4.0')
from gi.repository import GdkX11

photo = Path(root.name) / 'photo.png'
Image.new('RGB', (160, 100), 'purple').save(photo)
requests = {}
request_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def mutate(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        record = {'release': threading.Event(), 'status': 200, 'method': self.command}
        with request_lock:
            requests[body['ids'][0]] = record
        if not record['release'].wait(12):
            self.send_error(504)
            return
        self.send_response(record['status'])
        self.end_headers()
        self.wfile.write(b'[]')

    do_PUT = mutate
    do_DELETE = mutate


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()


class Client(ImmichClient):
    def __init__(self):
        super().__init__(f'http://127.0.0.1:{server.server_port}')
        self.token = 'fixture'
        self.user = {'id': 'fixture'}

    def image_bytes(self, *_args, **_kwargs):
        return photo.read_bytes()


app = Adw.Application(application_id='com.neg-zero.Galeria.OptimisticActions', flags=Gio.ApplicationFlags.NON_UNIQUE)
app.register(None)
css = Gtk.CssProvider()
css.load_from_path(str(Path(sys.modules['app'].__file__).with_name('style.css')))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
w = GalleryWindow(app)
w.set_default_size(1200, 800)
w.present()
w.client = Client()
notices = []
w.notice = notices.append
GLib.source_remove(w.refresh_timer)
w.refresh_timer = 0
context = GLib.MainContext.default()
measurements = []
expected_paint = None
painted = None


def pump(until, timeout=5):
    deadline = time.monotonic() + timeout
    while not until():
        assert time.monotonic() < deadline, ('Timed out', notices, len(w.media_items), w.viewer is not None)
        context.iteration(False)
        time.sleep(.002)


def frame(*_):
    global painted
    if expected_paint is None or painted is not None:
        return
    started, count, next_id = expected_paint
    motions = getattr(w, 'action_motions', ()) or ([w.action_motion] if getattr(w, 'action_motion', None) else [])
    if len(w.media_items) != count or not any(motion.get_mapped() and motion.frames for motion in motions):
        return
    if next_id is not None and (not w.viewer or w.viewer.source.media_item.id != next_id or not w.viewer.stage.get_mapped()):
        return
    painted = (time.monotonic() - started) * 1000


pump(w.get_mapped)
w.get_frame_clock().connect('after-paint', frame)
texture = w.texture_from_pixels(decode_image(photo))


def click(widget):
    assert widget.get_mapped(), widget
    ok, bounds = widget.compute_bounds(w)
    assert ok
    dx, dy = w.get_surface_transform()
    xid = str(GdkX11.X11Surface.get_xid(w.get_surface()))
    subprocess.run(['/tmp/gallery-app-identification/xdotool/bin/xdotool', 'windowfocus', xid,
                    'mousemove', '--window', xid,
                    str(round(bounds.get_x() + bounds.get_width() / 2 + dx)),
                    str(round(bounds.get_y() + bounds.get_height() / 2 + dy)), 'click', '--delay', '0', '1'], check=True)


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child)
        child = child.get_next_sibling()


try:
    for case, (mode, action) in enumerate((mode, action) for action in ('archive', 'trash') for mode in ('focus', 'selection', 'fullscreen')):
        if w.viewer:
            w.viewer.dismiss_action()
        values = [MediaItem(f'{case}-{i}', f'photo-{i}.png', datetime(2026, 11, 20-i), 1.6) for i in range(12)]
        index = TimelineIndex([{'timeBucket': '2026-11-01', 'count': len(values)}])
        index.apply('2026-11', values)
        w.timeline_index = index
        w.timeline_buckets = [{'timeBucket': '2026-11-01', 'count': len(values)}]
        for item in values:
            w.texture_cache[w.texture_key(item)] = texture
        w.set_library_items(index.items)
        pump(lambda: not w.loading_more and bool(w.mosaic.rendered))
        viewer = None
        if mode != 'selection':
            w.open_viewer(0)
            pump(lambda: w.viewer.stage.progress == 1)
            viewer = w.viewer
            if mode == 'fullscreen':
                viewer.set_immersive(True)
                viewer.show_chrome(True)
                pump(lambda: not viewer.fullscreen_tick)
        for number in (0, 1):
            if mode == 'selection':
                w.mosaic.selected = {0}
                w.mosaic.set_selection(True)
                pump(w.selection_bar.get_child_revealed)
            target = w.selection_controls[action] if mode == 'selection' else getattr(viewer, action)
            painted = None
            expected_paint = (time.monotonic(), len(values)-number-1, None if mode == 'selection' else values[number+1].id)
            click(target)
            if action == 'trash':
                expected_paint = None
                pump(lambda: isinstance(w.get_visible_dialog(), Adw.AlertDialog))
                dialog = w.get_visible_dialog()
                confirm = next(node for node in walk(dialog) if isinstance(node, Gtk.Button) and node.get_label() == 'Move to trash')
                pump(confirm.get_mapped)
                # Metadata can replace the grid while the scope dialog is open.
                w.set_library_items(w.media_items, append=True)
                expected_paint = (time.monotonic(), len(values)-number-1, None if mode == 'selection' else values[number+1].id)
                click(confirm)
            pump(lambda: painted is not None, .4)
            assert painted < 400, (mode, action, painted)
            pump(lambda: values[number].id in requests)
            assert not requests[values[number].id]['release'].is_set()
            if viewer:
                assert w.viewer is viewer and not viewer.closing
                assert viewer.media_stack.get_transition_running(), 'Next-media motion did not overlap the flight'
                assert viewer.immersive == (mode == 'fullscreen')
            measurements.append({'mode': mode, 'action': action, 'number': number, 'paint_ms': round(painted, 2)})
            expected_paint = None
        assert len(w.pending_mutations) == 2
        pump(lambda: not w.action_motions)
        assert not w.media_action_pending
        assert len(w.media_items) == len(values)-2
        # A stale server page must not reinsert pending removals.
        w.set_library_items(index.items, append=True)
        assert not {values[0].id, values[1].id} & {item.id for item in w.media_items}
        requests[values[1].id]['release'].set()
        pump(lambda: len(w.pending_mutations) == 1)
        requests[values[0].id]['status'] = 500
        requests[values[0].id]['release'].set()
        pump(lambda: not w.pending_mutations and not w.pending_removals)
        assert {item.id for item in w.media_items} == {item.id for item in values if item.id != values[1].id}
        assert {item.id for item in w.timeline_index.items} == {item.id for item in values if item.id != values[1].id}
        if viewer:
            assert w.viewer is viewer and viewer.source.media_item.id == values[2].id
        print('HELD REAL HTTP, POINTER CLICK, CONCURRENT FLIGHT/NEXT FOCUS, REPEATED ACTION, OUT-OF-ORDER ROLLBACK', mode, action, flush=True)
    print(json.dumps(measurements), flush=True)
finally:
    for record in requests.values():
        record['release'].set()
    server.shutdown()
    server.server_close()
    w.stop_data()
    w.destroy()
