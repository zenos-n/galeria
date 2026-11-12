"""Archive setting persists; cloud ACK gates verified local Trash without blocking motion."""
import os,sys,tempfile,time,threading,hashlib
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import patch
assert os.environ.get('DISPLAY')==':91'
sys.path.insert(0,os.environ.get('GALERIA_CHECK_SOURCE_ROOT',str(Path(__file__).resolve().parents[1])))
root=tempfile.TemporaryDirectory(prefix='galeria-archive-local-')
for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME','XDG_DATA_HOME'):os.environ[key]=root.name+'/'+key
from app import *
from panels import preferences
from library import ImmichClient,MediaItem,LibraryError
from sync_engine import SyncJournal
from local_media import journal_path,remember_copy,fingerprint
from session_store import preferences_read
from imaging import decode_image
from PIL import Image
folder=Path(root.name)/'synced';folder.mkdir()
paths=[folder/f'photo-{i}.png' for i in range(4)]
for path in paths:Image.new('RGB',(160,112),'purple').save(path)
original=paths[0].read_bytes()
items=[MediaItem(str(i),path.name,datetime(2026,11,12)-timedelta(minutes=i),10/7) for i,path in enumerate(paths)]
class Client(ImmichClient):
    def __init__(self):
        super().__init__('https://fixture.invalid');self.user={'id':'fixture'};self.token='fixture'
        self.ack=threading.Event();self.requested=threading.Event();self.fail=False;self.calls=[]
    def image_bytes(self,*args,**kwargs):return original
    def update_assets(self,ids,fields):
        self.requested.set();assert self.ack.wait(8)
        if self.fail:raise LibraryError('Fixture archive failed')
        self.calls.append((ids,fields))
client=Client();journal=SyncJournal(journal_path())
for item,path in zip(items,paths):journal.record(client.identity,'folder-rule',path,path.stat(),hashlib.sha1(original).hexdigest(),item.id,'')
other=folder/'other-account.png';other.write_bytes(original)
journal.record('other-account','folder-rule',other,other.stat(),hashlib.sha1(original).hexdigest(),'0','');journal.close()
download=Path(root.name)/'download.png';download.write_bytes(original);remember_copy(client,download,'0',hashlib.sha1(original).hexdigest(),download.stat())
app=Adw.Application(application_id='com.neg-zero.Galeria.ArchiveLocalCheck',flags=Gio.ApplicationFlags.NON_UNIQUE);app.register(None)
w=GalleryWindow(app);w.set_default_size(1200,800);w.present();w.client=client;notices=[];w.notice=notices.append
GLib.source_remove(w.refresh_timer);w.refresh_timer=0
texture=w.texture_from_pixels(decode_image(paths[0]))
for item in items:w.texture_cache[w.texture_key(item)]=texture
context=GLib.MainContext.default()
def pump(test,seconds=8):
    end=time.monotonic()+seconds
    while not test():
        assert time.monotonic()<end,notices
        context.iteration(False);time.sleep(.002)
def walk(widget):
    yield widget
    child=widget.get_first_child()
    while child:
        yield from walk(child);child=child.get_next_sibling()
def setting():
    preferences(w)
    return next(row for row in walk(w.dialog) if isinstance(row,Adw.SwitchRow) and row.get_title()=='Remove synced local files when archiving')
def close_dialog():
    w.dialog.close();pump(lambda:w.get_visible_dialog() is None)
def reset(page='library'):
    if w.viewer:w.viewer.close();pump(lambda:w.viewer is None)
    w.current_page=page;w.set_library_items(items,append=True,reflow=True)
    pump(lambda:not w.loading_more and not w.mosaic.tick and bool(w.mosaic.rendered))
    client.ack.clear();client.requested.clear()
def start(indices,focus=False):
    if focus:
        w.open_viewer(indices[0]);pump(lambda:w.viewer.stage.progress==1 and w.viewer.photo_editor.original is not None)
        target=w.viewer.archive
    else:
        w.mosaic.selected=set(indices);w.mosaic.set_selection(True);pump(w.selection_bar.get_child_revealed)
        target=w.selection_controls['archive']
    target.emit('clicked');pump(client.requested.is_set)
def finish():pump(lambda:not w.pending_mutations and not w.action_motions and not w.mosaic.tick)
try:
    reset();row=setting();assert not row.get_active() and not w.preferences.get('archive_delete_local',False);close_dialog()
    start([0]);assert paths[0].exists()
    # Changing the preference after clicking must not expand that operation's scope.
    w.preferences['archive_delete_local']=True;client.ack.set();finish();assert paths[0].exists()
    row=setting();row.set_active(False);assert preferences_read()['archive_delete_local'] is False
    row.set_active(True);assert preferences_read()['archive_delete_local'] is True;close_dialog()
    reset();hashing=threading.Event();release_hash=threading.Event()
    def held_hash(path,*args,**kwargs):
        hashing.set();assert release_hash.wait(8)
        return fingerprint(path,*args,**kwargs)
    with patch('local_media.fingerprint',side_effect=held_hash):
        start([0,1]);assert not hashing.is_set() and paths[0].exists() and paths[1].exists()
        client.ack.set();pump(hashing.is_set)
        finish();assert paths[0].exists() and paths[1].exists() and len(w.media_items)==2
        assert download.exists() and other.exists()
        release_hash.set();pump(lambda:not paths[0].exists() and not paths[1].exists())
    assert any(path.read_bytes()==original for path in (Path(os.environ['XDG_DATA_HOME'])/'Trash/files').iterdir())
    reset();start([2],focus=True);assert paths[2].exists();client.ack.set()
    pump(lambda:not paths[2].exists());finish();assert w.viewer and w.viewer.source.media_item.id!='2'
    reset();client.fail=True;start([3]);client.ack.set();finish()
    assert paths[3].read_bytes()==original and any('Fixture archive failed' in message for message in notices)
    client.fail=False;reset('archive');start([3]);client.ack.set();finish();assert paths[3].exists()
    reset();Image.new('RGB',(160,112),'green').save(paths[3]);changed=paths[3].read_bytes()
    start([3]);client.ack.set();finish();pump(lambda:any('files kept' in message for message in notices))
    assert paths[3].read_bytes()==changed and '3' not in {item.id for item in w.media_items}
    assert download.exists() and other.exists()
    print('DEFAULT OFF/PERSISTED; SUCCESS-ONLY FOLDER SYNC CLEANUP; BULK/FOCUS; HASHING DOES NOT HOLD ANIMATION; CLOUD FAILURE/UNARCHIVE/CHANGED FILES KEPT; PRIVATE REAL TRASH BYTES RESTORABLE PASSED',flush=True)
finally:
    client.ack.set()
    if 'release_hash' in globals():release_hash.set()
    w.stop_data();w.destroy()
