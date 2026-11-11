"""First/second tile morphs keep image pixels at both edges of the frame."""
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

assert os.environ.get('DISPLAY') == ':91'
sys.path.insert(0, os.environ.get('GALERIA_CHECK_SOURCE_ROOT', str(Path(__file__).resolve().parents[1])))
root = tempfile.TemporaryDirectory(prefix='galeria-morph-')
for key in ('XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_STATE_HOME'):
    os.environ[key] = root.name + '/' + key

from app import *
from imaging import decode_image
from library import MediaItem
from PIL import Image, ImageGrab

color = (20, 180, 220)
path = Path(root.name) / 'portrait.png'
Image.new('RGB', (800, 600), color).save(path)
items = [MediaItem(str(i), path.name, datetime(2026, 11, 20-i), 1.6, path=str(path)) for i in range(8)]
app = Adw.Application(application_id='com.neg-zero.Galeria.MorphCheck', flags=Gio.ApplicationFlags.NON_UNIQUE)
app.register(None)
css = Gtk.CssProvider()
css.load_from_path(str(Path(sys.modules['app'].__file__).with_name('style.css')))
Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
w = GalleryWindow(app)
w.set_default_size(1200, 900)
w.present()
GLib.source_remove(w.refresh_timer)
w.refresh_timer = 0
texture = w.texture_from_pixels(decode_image(path))
for item in items:
    w.texture_cache[w.texture_key(item)] = texture
w.set_library_items(items)
context = GLib.MainContext.default()
samples = []
errors = []
sampled = set()


def pump(until):
    deadline = time.monotonic() + 4
    while not until():
        assert time.monotonic() < deadline, 'Morph check timed out'
        context.iteration(False)
        time.sleep(.002)
    assert not errors, errors


def painted(*_):
    viewer = w.viewer
    if not viewer or viewer.index in sampled or not .35 < viewer.stage.progress < .65:
        return
    ok, bounds = viewer.stage.picture.compute_bounds(w)
    if not ok:
        return
    dx, dy = w.get_surface_transform()
    y = round(bounds.get_y() + bounds.get_height() / 2 + dy)
    left = round(bounds.get_x() + dx + 3)
    right = round(bounds.get_x() + bounds.get_width() + dx - 4)
    screenshot = ImageGrab.grab(xdisplay=':91')
    pixels = [screenshot.getpixel((x, y))[:3] for x in (left, right)]
    samples.append((viewer.index, viewer.stage.progress, pixels))
    if not all(all(abs(actual-expected) < 8 for actual, expected in zip(pixel, color)) for pixel in pixels):
        errors.append(('Letterbox strips during morph', samples[-1]))
    screenshot.save(f'/tmp/gallery-app-identification/morph-{viewer.index}.png')
    sampled.add(viewer.index)


try:
    pump(lambda: w.get_mapped() and bool(w.mosaic.rendered) and not w.loading_more)
    w.get_frame_clock().connect('after-paint', painted)
    for index in (0, 1):
        w.open_viewer(index)
        pump(lambda: index in sampled)
        pump(lambda: w.viewer.stage.progress == 1)
        assert abs(w.viewer.stage.destination(w.viewer.stage.get_width(), w.viewer.stage.get_height())[2] /
                   w.viewer.stage.destination(w.viewer.stage.get_width(), w.viewer.stage.get_height())[3] - 4/3) < .001
        w.viewer.dismiss_action()
    print('FIRST/SECOND TILE MORPH EDGES CONTAIN IMAGE PIXELS; ACTUAL TEXTURE ASPECT', samples, flush=True)
finally:
    w.stop_data()
    w.destroy()
