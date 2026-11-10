import threading,unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
import gi
gi.require_version('Adw','1');gi.require_version('Gtk','4.0')
from gi.repository import GLib
from library import MediaItem
from pending_uploads import manager,ui_call


class PendingUploadTests(unittest.TestCase):
    def setUp(self):
        self.window=SimpleNamespace(client=SimpleNamespace(),data_stopped=False,data_generation=1,current_page='library',viewer=None,media_items=[],texture_cache={},mosaic=SimpleNamespace(active_widgets=set(),tile_set=set()))
        self.window.texture_key=lambda item:(item.id,str(item.metadata.get('updatedAt','')))
        self.publishes=[]
        self.window.set_library_items=lambda items,**kwargs:self.publishes.append(items)
        self.uploads=manager(self.window)
        self.source=MediaItem('','paste.png',datetime(2026,11,1),1.5)
    def test_pending_pixels_are_adopted_by_confirmed_metadata_without_duplicate(self):
        transfer=lambda *_:('server-id',True)
        entry=self.uploads.add(self.source,'pixels',transfer);key=entry['item'].id
        self.assertTrue(self.uploads.active());self.assertTrue(entry['item'].metadata['placeholder'])
        self.assertEqual(len(self.uploads.merge([])),1)
        self.uploads.complete(entry,'server-id');self.assertFalse(self.uploads.active())
        self.assertEqual(entry['item'].id,'server-id');self.assertFalse(entry['item'].metadata['placeholder']);self.assertEqual(entry['item'].path,'')
        actual=MediaItem('server-id','server.png',datetime.now(),metadata={'updatedAt':'revision'})
        self.assertEqual(self.uploads.merge([actual]),[actual]);self.assertFalse(self.uploads.entries)
        self.assertEqual(self.window.texture_cache[('server-id','revision')],'pixels');self.assertNotIn((key,''),self.window.texture_cache)
    def test_progress_does_not_rebuild_grid_and_failures_can_retry(self):
        entry=self.uploads.add(self.source,'pixels',lambda *_:None)
        self.uploads.progress(entry,1,2)
        context=GLib.MainContext.default()
        while context.pending():context.iteration(False)
        self.assertEqual(entry['item'].metadata['upload_progress'],.5);self.assertFalse(self.publishes)
        self.uploads.fail(entry,'network failed');self.assertEqual(entry['item'].metadata['upload_state'],'failed');self.assertFalse(self.uploads.active())
        with patch('import_ui.start_upload') as retry:
            self.uploads.retry(entry['item'].metadata['upload_key']);retry.assert_called_once_with(self.window,retry_entry=entry)
    def test_account_changes_clear_transient_state_and_locked_tiles_stay_private(self):
        private=MediaItem('','private.png',datetime.now(),metadata={'visibility':'locked'})
        self.uploads.add(private,'pixels');self.assertEqual(self.uploads.merge([]),[])
        self.window.current_page='locked';self.assertEqual(len(self.uploads.merge([])),1)
        self.window.client=object();self.assertIsNone(manager(self.window,False));self.assertIsNone(self.window.upload_previews)
        with patch('import_ui.start_upload') as retry:
            self.uploads.retry(next(iter(self.uploads.entries)));retry.assert_not_called()
    def test_ui_handoff_is_cancelled_after_window_stops(self):
        self.window.data_stopped=True;calls=[];errors=[]
        def work():
            try:ui_call(self.window,lambda:calls.append('unexpected'),threading.Event())
            except InterruptedError:errors.append('cancelled')
        thread=threading.Thread(target=work);thread.start();context=GLib.MainContext.default()
        while thread.is_alive():context.iteration(False);thread.join(.01)
        self.assertEqual(errors,['cancelled']);self.assertEqual(calls,[])

    def test_metadata_prefetch_stops_after_the_visible_and_next_screen(self):
        from data_ui import LibraryUI
        from timeline_index import TimelineIndex
        w=self.window;w.timeline_index=TimelineIndex([{'timeBucket':month+'-01','count':2} for month in ('2026-11','2026-10','2026-09','2026-08')])
        w.timeline_pending=set();w.mosaic.indexed=True;w.mosaic.mode='all'
        w.mosaic.month_extents={'2026-11':(0,300),'2026-10':(300,1000),'2026-09':(1000,1600),'2026-08':(1600,2000)}
        w.mosaic.visible_range=lambda:(0,400);work=[];requests=[]
        w.background=lambda callback,*args:work.append(callback)
        w.client.time_bucket=lambda key,**kwargs:(requests.append(key),[])[1]
        LibraryUI.request_timeline_metadata(w)
        for callback in work:callback()
        self.assertEqual(set(requests),{'2026-11','2026-10'});self.assertEqual(len(work),2)
    def test_acknowledged_preview_does_not_refresh_the_whole_grid(self):
        from data_ui import LibraryUI
        self.uploads.add(self.source,'pixels');calls=[]
        self.window.refresh_remote=lambda:calls.append('global refresh')
        LibraryUI.upload_finished(self.window,self.window.client)
        self.assertFalse(calls);self.assertEqual(self.window.client.refresh_serial,1)
