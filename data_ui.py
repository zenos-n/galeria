"""Background I/O and GTK handoff for connected libraries."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from collections import OrderedDict
import json
import threading
import time
import errno
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk
from library import ImmichClient, LibraryError, scan_folders
from timeline import Mosaic
from cache import MediaCache
from imaging import decode_image,image_ratio,thumbnail_bytes
from session_store import preferences_read,preferences_write,secret_get,secret_put,secret_clear
from image_queue import ImageQueue


class LibraryUI:
    def init_data(self):
        self.client=None
        self.data_stopped=False
        self.preferences=preferences_read()
        self.collection_items=None
        self.media_items=[]
        self.local_items=[]
        self.local_roots=[]
        self.next_page=None
        self.album_items=[]
        self.album_result_id=None
        self.data_generation=0
        self.search_generation=0
        self.texture_cache=OrderedDict()
        self.page_cache=OrderedDict();self.collection_cache={};self.date_cover_cache=OrderedDict();self.collection_textures=OrderedDict()
        self.refresh_timer=GLib.timeout_add_seconds(15,self.refresh_remote)
        self.pending_images=set()
        self.loading_more=False
        self.scroll_input_serial=0
        self.pending_media=None
        self.vault=None
        self.sync_cancel=threading.Event()
        self.scope_filters={}
        self.timeline_buckets=[]
        self.timeline_index=None;self.timeline_pending=set()
        self.dates_ready=True
        self.bucket_scope={}
        self.io=ThreadPoolExecutor(max_workers=3,thread_name_prefix='gallery-io')
        self.images=ImageQueue(4);self.image_wanted={}
        self.cached_images=ImageQueue(2)
        self.previews=ThreadPoolExecutor(max_workers=2,thread_name_prefix='gallery-preview')
        self.video_io=ThreadPoolExecutor(max_workers=2,thread_name_prefix='gallery-video')
        self.video_proxy=None;self.video_prefetch=set()
        self.connect('close-request',self.request_close)

    def request_close(self,*_):
        app=self.get_application()
        if getattr(app,'background_enabled',False) and not getattr(app,'quitting',False):
            if self.viewer and self.viewer.stage.video_player:self.viewer.stage.video_player.pause()
            if self.client and self.client.locked_until:self.lock_folder(refresh=self.current_page=='locked')
            self.set_visible(False);app.emit_state();return True
        if getattr(app,'window',None)==self:app.window=None
        return self.stop_data()

    def stop_data(self,*_):
        if self.data_stopped:return False
        from copy_ui import clear_locked_clipboard
        clear_locked_clipboard(self)
        self.data_stopped=True
        if self.refresh_timer:GLib.source_remove(self.refresh_timer);self.refresh_timer=0
        self.data_generation+=1
        self.io.shutdown(wait=False,cancel_futures=True)
        self.images.shutdown(wait=False,cancel_futures=True)
        self.cached_images.shutdown(wait=False,cancel_futures=True)
        self.previews.shutdown(wait=False,cancel_futures=True)
        self.video_io.shutdown(wait=False,cancel_futures=True)
        if self.viewer and self.viewer.stage.video_player:self.viewer.stage.video_player.stop()
        if self.video_proxy:threading.Thread(target=self.video_proxy.close,daemon=True).start()
        self.sync_cancel.set()
        if self.client:
            self.client.token=None
        return False

    def save_preferences(self):preferences_write(self.preferences)

    def user_scrolled(self,*_):
        self.scroll_input_serial+=1
        return False

    def get_video_proxy(self):
        if self.video_proxy is None:
            from video_proxy import VideoProxy
            self.video_proxy=VideoProxy()
        return self.video_proxy

    def preload_video(self,item,job_key=None):
        key=self.texture_key(item)
        if key in self.video_prefetch:return
        self.video_prefetch.add(key)
        client=self.client;vault=self.vault
        proxy=self.get_video_proxy() if client else None
        def work():
            if job_key is not None and job_key not in self.image_wanted:self.video_prefetch.discard(key);return
            if item.path:
                with open(item.path,'rb') as stream:stream.read(2*1024*1024)
            else:proxy.preload(client,item,vault)
        self.background(work,lambda _:None,lambda _:None,images='video')

    def remember_account(self,client):
        def store():
            if not secret_put(client.identity,'session',client.token):raise LibraryError('The system keyring could not save this account.')
        self.background(store,lambda _:None,lambda message:self.notice(message))

    def sign_out(self):
        from copy_ui import clear_locked_clipboard
        clear_locked_clipboard(self)
        client=self.client
        if not client:return
        from sync_service import disable_account
        token=client.token;client.token=None;client.locked_until=0
        if self.viewer:
            self.root_overlay.remove_overlay(self.viewer);self.viewer.stage.dispose()
            self.viewer=None;self.split.set_can_target(True)
        self.sync_cancel.set();self.vault=None
        self.data_generation+=1
        self.client=None;self.media_items=[];self.local_items=[];self.local_roots=[]
        self.timeline_buckets=[];self.bucket_scope={};self.dates_ready=True
        self.timeline_index=None;self.timeline_pending=set()
        self.page_cache.clear();self.collection_cache.clear();self.date_cover_cache.clear();self.collection_textures.clear();self.texture_cache.clear();self.pending_images.clear()
        self.preferences.update(mode=None,remember=False);self.save_preferences()
        self.album_tree.set_albums([]);self.source_label.set_label('No library connected')
        self.update_account_ui();self.set_searching(False)
        self.set_library_items([])
        def clear_session():
            try:disable_account(client.identity)
            finally:secret_clear(client.identity,'session')
            logout=ImmichClient(client.base);logout.token=token
            logout.request('/auth/logout',{},method='POST')
        self.background(clear_session,lambda _:None,lambda _:None)
        self.welcome()

    def restore_last_library(self,done=None):
        mode=self.preferences.get('mode')
        if mode=='local' and self.preferences.get('folders'):
            self.connect_local(self.preferences['folders'])
            if done:done()
            return False
        if mode=='immich' and self.preferences.get('remember'):
            self.stack.set_visible_child_name('library')
            if self.get_visible() and self.scroller.get_width()<=0:
                GLib.timeout_add(16,self.restore_last_library,done);return False
            width=max(900,self.scroller.get_width()-20);height=max(400,self.scroller.get_height())
            def validate(client):
                user=client.request('/users/me')
                if user['id']!=self.preferences['user_id']:raise LibraryError('The saved session belongs to another account.')
                client.detect_version();client.lock_session();return user
            def restore():
                client=ImmichClient(self.preferences['server'])
                client.token=secret_get(client.base+'|'+self.preferences['user_id'],'session')
                if not client.token:return None
                client.user=dict(self.preferences.get('last_user') or {'id':self.preferences['user_id'],'name':self.preferences.get('email','Immich')})
                client.user['id']=self.preferences['user_id'];client.user['isAdmin']=False
                client.modern_search=self.preferences.get('modern_search',True)
                from startup_cache import restore as cached_restore
                client.bootstrap=cached_restore(client,width,height) if client.modern_search else None
                client.restoring=bool(client.bootstrap)
                if not client.bootstrap:
                    GLib.idle_add(self.busy_library,'Reconnecting to your library…')
                    client.user=validate(client)
                return client
            self.stack.set_visible_child_name('library')
            def finished(client):
                if client:
                    self.connect_immich(client)
                    if client.restoring:
                        def validated(user):
                            if self.client is not client:return
                            client.user=user;client.restoring=False;self.remember_user();self.update_account_ui()
                            self.refresh_connected_library();self.load_visible_thumbnails()
                        self.background(lambda:validate(client),validated,lambda message:self.notice('Showing cached photos. '+message))
                else:self.welcome()
                if done:done()
            self.background(restore,finished,lambda _:finished(None))
        else:
            self.welcome()
            if done:done()
        return False

    def activate_album(self,album_id):
        key='album-'+album_id
        node=self.rows.get(key)
        if not node:return
        selection=self.album_tree.get_model()
        for i in range(selection.get_n_items()):
            if selection.get_item(i).get_item().key==key:
                selection.set_selected(i);break
        self.navigate(self.album_tree,node)

    def refresh_pins(self):
        if not hasattr(self,'pin_nav'):return
        for row in self.pin_rows:self.pin_nav.remove(row)
        self.pin_rows=[]
        selected=self.preferences.get('pins',{}).get(self.client.identity,[]) if self.client else []
        for album in getattr(self.album_tree,'albums',[]):
            if album['id'] not in selected:continue
            row=Gtk.ListBoxRow();row.key='album-'+album['id']
            body=Gtk.Box(spacing=10)
            body.append(Gtk.Image(icon_name='folder-pictures-symbolic',pixel_size=16))
            body.append(Gtk.Label(label=album.get('albumName','Untitled album'),xalign=0,ellipsize=3,hexpand=True))
            row.set_child(body);self.pin_nav.append(row);self.pin_rows.append(row)
            from collection_widgets import album_context
            album_context(self,row,lambda album=album:album)
        self.pin_section.set_visible(bool(self.pin_rows))

    def toggle_album_pin(self,album_id):
        if not self.client:return
        pins=self.preferences.setdefault('pins',{}).setdefault(self.client.identity,[])
        if album_id in pins:pins.remove(album_id)
        else:pins.append(album_id)
        self.save_preferences();self.refresh_pins()

    def open_collection(self,title,filters=None,items=None):
        self.search_generation+=1
        self.current_page='collection'
        self.grid_page=True
        self.collection_items=items
        self.scope_filters=filters or {}
        self.page_title.set_label(title)
        self.header.set_title_widget(self.page_title)
        self.switcher.set_visible(False);self.period.set_visible(False)
        self.select_button.set_visible(True)
        self.search_library()

    def check_locked_expiry(self):
        if not self.client or not self.client.locked_until:return False
        if self.client.locked_until<=time.monotonic():self.lock_folder();return False
        return True

    def lock_folder(self,refresh=True):
        from copy_ui import clear_locked_clipboard
        clear_locked_clipboard(self)
        self.timeline_pending=set()
        client=self.client
        self.sync_cancel.set();self.vault=None
        self.data_generation+=1
        self.page_cache.clear();self.collection_cache.clear();self.date_cover_cache.clear();self.collection_textures.clear();self.texture_cache.clear();self.pending_images.clear()
        self.lock_button.set_visible(False)
        if client:
            client.locked_until=0
            client.server_lock_pending=True
            self.background(client.lock_session,lambda _:None)
        if refresh:
            if self.viewer:
                viewer=self.viewer
                self.root_overlay.remove_overlay(viewer);viewer.stage.dispose()
                self.viewer=None;self.split.set_can_target(True)
                self.pending_media=None
            self.set_library_items([])
            self.status.set_icon_name('changes-prevent-symbolic');self.status.set_title('Locked folder')
            self.status.set_description('A private space for your photos.')
            self.status_actions.set_visible(True)

    def selected_action(self,action,items=None):
        if not self.client:self.notice('Local files are read-only.');return
        ids=[item.id for item in items] if items is not None else [self.mosaic.tiles[i].media_item.id for i in self.mosaic.selected]
        if not ids:return
        mosaic=self.mosaic
        restore=action=='trash' and self.current_page=='trash'
        unarchive=action=='archive' and self.current_page=='archive'
        def perform():
            if action=='favorite':return self.client.update_assets(ids,{'isFavorite':True})
            if action=='archive':return self.client.update_assets(ids,{'visibility':'timeline' if unarchive else 'archive'})
            return self.client.restore_assets(ids) if restore else self.client.trash_assets(ids)
        def done(_):
            self.page_cache.clear();self.collection_cache.clear()
            if action=='trash' or action=='archive' and not unarchive:self.remove_from_timeline(ids)
            self.client.refresh_serial=getattr(self.client,'refresh_serial',0)+1
            if self.mosaic==mosaic:
                def remove():
                    if self.mosaic==mosaic:self.set_library_items(self.timeline_index.items if self.timeline_index and mosaic.indexed else [item for item in self.media_items if item.id not in ids],append=True,reflow=True)
                if action in ('trash','archive') and self.viewer:
                    self.pending_media=([item for item in self.media_items if item.id not in ids],True)
                    self.viewer.close()
                elif action=='trash' and not restore:
                    from trash_motion import TrashMotion
                    TrashMotion(self,[tile for tile in mosaic.tiles if tile.media_item.id in ids],remove)
                elif restore or action=='archive':remove()
                else:
                    for item in self.media_items:
                        if item.id in ids:item.metadata['isFavorite']=True
                self.mosaic.set_selection(False)
            self.notice('Items restored.' if restore else 'Favorites updated.' if action=='favorite' else 'Items removed from archive.' if unarchive else 'Items archived.' if action=='archive' else 'Items moved to trash.')
        if action=='trash' and not restore:
            confirm=Adw.AlertDialog(heading=f'Move {len(ids)} items to trash?',body='You can restore them from Trash.')
            confirm.add_response('cancel','Cancel');confirm.add_response('trash','Move to trash')
            confirm.set_response_appearance('trash',Adw.ResponseAppearance.DESTRUCTIVE)
            confirm.connect('response',lambda _,value:self.background(perform,done) if value=='trash' else None)
            confirm.present(self)
        else:self.background(perform,done)

    def add_selected_to_album(self):
        if not self.client:self.notice('Connect Immich to add items to albums.');return
        ids=[self.mosaic.tiles[i].media_item.id for i in self.mosaic.selected]
        dialog=Adw.PreferencesDialog(title='Add to album',content_width=440,content_height=500)
        page=Adw.PreferencesPage();group=Adw.PreferencesGroup()
        for album in getattr(self.album_tree,'albums',[]):
            row=Adw.ActionRow(title=album.get('albumName','Untitled album'),use_markup=False,activatable=True)
            row.connect('activated',lambda _,album=album:self.background(
                lambda:self.client.request('/albums/'+album['id']+'/assets',{'ids':ids},method='PUT'),
                lambda _:(dialog.close(),self.notice('Items added to album.'))))
            group.add(row)
        page.add(group);dialog.add(page);dialog.present(self)

    def move_selected_to_locked(self):
        if not self.client:self.notice('Connect Immich to use the locked folder.');return
        client=self.client;mosaic=self.mosaic
        ids=[mosaic.tiles[i].media_item.id for i in mosaic.selected if not mosaic.tiles[i].media_item.metadata.get('placeholder')]
        if not ids:return
        def move():
            if self.client!=client:return
            def done(_):
                self.data_generation+=1
                self.remove_from_timeline(ids)
                self.page_cache.clear();self.collection_cache.clear();self.date_cover_cache.clear();self.collection_textures.clear();self.texture_cache.clear();self.pending_images.clear()
                if self.mosaic==mosaic:
                    self.mosaic.set_selection(False);self.set_library_items(self.timeline_index.items if self.timeline_index and mosaic.indexed else [item for item in self.media_items if item.id not in ids],append=True,reflow=True)
                self.notice('Items moved to the locked folder.')
            def work():
                result=client.update_assets(ids,{'visibility':'locked'})
                client.media_cache().forbid(id+':' for id in ids)
                client.video_cache().forbid('video-prefix:'+id for id in ids)
                return result
            self.background(work,done)
        if client.locked_until<=time.monotonic():
            from vault_ui import unlock_folder
            unlock_folder(self,after=move)
        else:move()

    def remove_from_timeline(self,ids):
        if self.timeline_index:
            self.timeline_index=self.timeline_index.without(ids);self.timeline_pending=set()
            self.timeline_buckets=[{'timeBucket':key+'-01','count':b-a} for key,(a,b) in self.timeline_index.ranges.items()]

    def background(self,work,done,failed=None,images=False,priority=10):
        generation=self.data_generation
        def execute():
            if generation!=self.data_generation:
                return None
            return work()
        future=(self.cached_images if images=='cached' else self.images).submit(execute,priority) if images is True or images=='cached' else (self.video_io if images=='video' else self.previews if images=='preview' else self.io).submit(execute)
        def completed(result):
            if result.cancelled():
                return
            try:
                value=result.result()
            except Exception as error:
                message=str(error) if isinstance(error,LibraryError) else 'Not enough free space to save device copies.' if isinstance(error,OSError) and error.errno==errno.ENOSPC else f'Could not load this data ({type(error).__name__}).'
                GLib.idle_add(deliver,failed or self.notice,message)
            else:
                GLib.idle_add(deliver,done,value)
        def deliver(callback,value):
            if generation==self.data_generation:
                callback(value)
            return False
        future.add_done_callback(completed)

    def busy_library(self,title):
        self.status_actions.set_visible(False)
        self.status.set_icon_name('content-loading-symbolic')
        self.status.set_title(title)
        self.status.set_description('')
        self.stack.set_visible_child_name('status')

    def library_failed(self,message):
        self.loading_more=False
        self.load_more.set_sensitive(True)
        self.status_actions.set_visible(False)
        self.status.set_icon_name('dialog-error-symbolic')
        self.status.set_title('Could not load the library')
        self.status.set_description(message)
        self.stack.set_visible_child_name('status')
        self.notice(message)

    def connect_local(self,paths,focus_first=False):
        from copy_ui import clear_locked_clipboard
        clear_locked_clipboard(self)
        self.timeline_index=None;self.timeline_pending=set()
        self.sync_cancel.set();self.vault=None;self.pending_media=None
        self.lock_button.set_visible(False)
        self.data_generation+=1
        self.client=None
        self.media_items=[]
        self.video_prefetch.clear()
        self.update_account_ui()
        self.timeline_buckets=[];self.dates_ready=True;self.bucket_scope={}
        self.local_items=[]
        self.library_mode='local'
        self.local_roots=paths
        self.preferences.update(mode='local',folders=paths)
        self.save_preferences()
        self.page_cache.clear();self.collection_cache.clear();self.date_cover_cache.clear();self.collection_textures.clear();self.texture_cache.clear()
        self.pending_images.clear()
        self.disk_cache=MediaCache('local')
        self.search.set_mode('local')
        self.album_tree.set_albums([])
        self.navigate(self.rows['library'].get_parent(),self.rows['library'])
        self.busy_library('Reading your folders…')
        def probe(path):
            try:return image_ratio(path)
            except (OSError,ValueError):return 1.5
        def loaded(value):
            self.local_items,errors=value
            self.source_label.set_label(Path(paths[0]).name if len(paths)==1 else f'{len(paths)} folders')
            self.search_library()
            if focus_first and self.media_items:
                generation=self.data_generation
                def focus():
                    if generation==self.data_generation and not self.viewer and self.mosaic.tiles:self.open_viewer(0,self.mosaic.tiles[0])
                    return False
                GLib.timeout_add(80,focus)
            if errors:
                self.notice(f'{len(errors)} files or folders could not be read.')
        self.background(lambda:scan_folders(paths,probe),loaded,self.library_failed)

    def connect_immich(self,client):
        from copy_ui import clear_locked_clipboard
        clear_locked_clipboard(self)
        self.timeline_index=None;self.timeline_pending=set()
        self.sync_cancel.set();self.vault=None;self.pending_media=None
        self.lock_button.set_visible(False)
        self.data_generation+=1
        self.search_generation+=1
        self.client=client
        self.media_items=[]
        self.video_prefetch.clear()
        self.timeline_buckets=[];self.dates_ready=False;self.bucket_scope={}
        client.media_cache()
        bootstrap=getattr(client,'bootstrap',None)
        if bootstrap:self.timeline_buckets,self.timeline_index,pixels=bootstrap;self.dates_ready=True
        self.library_mode='immich'
        self.local_items=[]
        self.page_cache.clear();self.collection_cache.clear();self.date_cover_cache.clear();self.collection_textures.clear();self.texture_cache.clear()
        self.pending_images.clear()
        if bootstrap:
            for id,pixel in pixels.items():self.texture_cache[id]=self.texture_from_pixels(pixel)
            client.bootstrap=None
        self.preferences.update(mode='immich',server=client.base,user_id=client.user['id'],email=client.user.get('email',''))
        self.remember_user()
        self.save_preferences()
        self.search.set_mode('immich')
        self.source_label.set_label(client.user.get('name') or client.user.get('email') or 'Immich')
        self.update_account_ui()
        self.current_page='library'
        self.navigate(self.rows['library'].get_parent(),self.rows['library'])
        if not getattr(client,'restoring',False):self.refresh_connected_library()

    def remember_user(self):
        self.preferences['last_user']={key:self.client.user.get(key) for key in ('id','name','email','profileImagePath','profileChangedAt')}
        self.preferences['modern_search']=getattr(self.client,'modern_search',True);self.save_preferences()

    def refresh_connected_library(self):
        client=self.client
        from sync_service import read_config
        sync_account=read_config().get('accounts',{}).get(client.identity,{})
        if sync_account.get('enabled') and sync_account.get('folders'):self.request_folder_sync()
        self.background(client.albums,self.album_tree.set_albums)
        def dates_loaded(buckets):
            previous=self.timeline_index
            if previous and buckets==self.timeline_buckets:
                self.dates_ready=True
                key=next(iter(previous.ranges),None)
                if key:previous.loaded.discard(key);self.timeline_refresh_key=key
                self.request_timeline_metadata();return
            self.timeline_buckets=buckets;self.dates_ready=True
            if hasattr(client,'time_bucket') and client.modern_search:
                from timeline_index import TimelineIndex
                self.timeline_index=TimelineIndex(buckets)
                if previous:
                    for key,(a,b) in list(self.timeline_index.ranges.items()):
                        if key in previous.loaded and key in previous.ranges:
                            old_a,old_b=previous.ranges[key]
                            if b-a==old_b-old_a:self.timeline_index.apply(key,previous.items[old_a:old_b])
            if self.current_page=='library':self.search_library(force=bool(self.media_items))
        def dates_failed(message):
            self.dates_ready=True;self.notice('Date index unavailable: '+message)
            if self.current_page=='library':self.search_library()
        self.background(client.time_buckets,dates_loaded,dates_failed)

    def open_date_bucket(self,kind,key):
        from datetime import datetime,timedelta
        if not self.client:return
        if self.timeline_index and self.mosaic.indexed:
            self.request_timeline_metadata();return
        start=datetime.strptime(key,'%Y' if kind=='year' else '%Y-%m')
        end=datetime(start.year+1,1,1) if kind=='year' or start.month==12 else datetime(start.year,start.month+1,1)
        self.bucket_scope={'takenAfter':start.isoformat(timespec='milliseconds')+'Z',
                           'takenBefore':(end-timedelta(milliseconds=1)).isoformat(timespec='milliseconds')+'Z'}
        self.search_library(preserve_folder=True)

    def refresh_library(self):
        self.page_cache.clear();self.collection_cache.clear();self.date_cover_cache.clear();self.collection_textures.clear()
        if self.client:
            self.client.media_cache().remove('albums')
            # Clear short-lived query snapshots while keeping expensive images.
            self.client.refresh_serial=getattr(self.client,'refresh_serial',0)+1
            self.background(self.client.albums,self.album_tree.set_albums)
            self.search_library()
        elif self.local_roots:
            self.connect_local(self.local_roots)
        else:
            self.welcome()

    def search_library(self,append=False,preserve_folder=False,force=False):
        if self.viewer:
            return
        if self.client and self.current_page=='library' and not self.dates_ready:
            self.busy_library('Loading library dates…');return
        if self.current_page not in ('library','photos','videos','screenshots','live','favorites','archive','trash','locked','collection') and not self.current_page.startswith('album-'):
            return
        if append and (self.loading_more or not self.next_page):return
        self.loading_more=True
        self.search_generation+=1
        request_id=self.search_generation
        if self.current_page=='collection' and self.collection_items is not None:
            query=self.search.entry.get_text().casefold()
            items=[item for item in self.collection_items if query in item.filename.casefold()]
            count=len(self.media_items)+100 if append else 100
            self.next_page=count if len(items)>count else None
            self.set_library_items(items[:count],append);return
        if self.library_mode=='local':
            items=self.local_items
            page=self.current_page
            if page=='videos':items=[item for item in items if item.kind=='VIDEO']
            elif page=='photos':items=[item for item in items if item.kind=='IMAGE']
            elif page=='screenshots':items=[item for item in items if 'screenshot' in item.filename.lower()]
            elif page not in ('library','photos','videos','screenshots'):items=[]
            query=self.search.entry.get_text().casefold()
            items=[item for item in items if query in item.filename.casefold()]
            self.filtered_local=items
            count=len(self.media_items)+100 if append else 100
            self.next_page=count if len(items)>count else None
            self.set_library_items(items[:count],append=append)
            return
        if not self.client:
            return
        client=self.client
        try:
            filters,query=self.search.request_filters()
        except ValueError as error:
            self.notice(str(error));return
        page=self.current_page
        if page=='library' and not filters and not query and not self.bucket_scope and self.timeline_index:
            self.next_page=None
            self.set_library_items(self.timeline_index.items,append=preserve_folder or force)
            self.request_timeline_metadata();return
        if page.startswith('album-'):
            filters['albumIds']=[page.removeprefix('album-')]
            filters['visibility']=None
        filters.update(self.scope_filters if page=='collection' else {})
        if page=='library':filters.update(self.bucket_scope)
        if page in ('photos','videos'):filters['type']='IMAGE' if page=='photos' else 'VIDEO'
        if page=='screenshots':filters['originalFileName']='Screenshot'
        if page=='live':filters['isMotion']=True
        if page=='favorites':filters['isFavorite']=True
        if page=='archive':filters['visibility']='archive'
        if page=='locked':filters['visibility']='locked'
        if page=='trash':filters.pop('visibility',None);filters['isTrashed']=True
        cache_key=json.dumps([page,filters,query],sort_keys=True)
        if not append and not force and page!='locked' and cache_key in self.page_cache:
            items,self.next_page=self.page_cache[cache_key];self.page_cache.move_to_end(cache_key)
            self.set_library_items(items);return
        next_page=self.next_page if append and self.next_page else 1
        if not append and not preserve_folder and not self.media_items:self.busy_library('Loading your photos…')
        self.load_more.set_sensitive(False)
        def loaded(value):
            if request_id!=self.search_generation:return
            items,self.next_page=value
            result=self.media_items+items if append else items
            if page!='locked':
                self.page_cache[cache_key]=(result,self.next_page);self.page_cache.move_to_end(cache_key)
                while len(self.page_cache)>24:self.page_cache.popitem(last=False)
            if force and result==self.media_items:
                self.loading_more=False;self.load_more.set_sensitive(True);return
            if self.viewer:
                self.pending_media=(result,append)
                self.loading_more=False
            else:self.set_library_items(result,append=append or force,reflow=force)
        def failed(message):
            if request_id==self.search_generation:
                if force:self.loading_more=False;self.notice(message)
                else:self.library_failed(message)
        count=len(self.media_items) if force else 0
        def load():
            items,cursor=client.search(filters,query,next_page)
            while force and cursor and len(items)<count:
                batch,cursor=client.search(filters,query,cursor);items.extend(batch)
            return items,cursor
        self.background(load,loaded,failed)

    def refresh_remote(self,*_):
        if self.data_stopped:return False
        if not self.client or getattr(self.client,'restoring',False) or self.viewer or self.loading_more or not self.get_visible():return True
        if self.current_page in ('albums','people','tags','duplicates','sharing','map'):
            if self.current_page!='map':
                from collections_ui import collection_view
                collection_view(self,self.current_page,refresh=True)
            return True
        if self.current_page not in ('library','photos','videos','favorites','archive','trash') and not self.current_page.startswith('album-'):return True
        self.client.refresh_serial=getattr(self.client,'refresh_serial',0)+1
        if self.current_page=='library':
            if self.timeline_index and self.mosaic.indexed:
                index=self.timeline_index;client=self.client;generation=self.search_generation
                if getattr(self,'timeline_refresh_pending',None) is index:return True
                self.timeline_refresh_pending=index
                def current():return self.timeline_index is index and self.client is client and self.current_page=='library' and self.search_generation==generation and self.mosaic.indexed
                def failed(_):
                    if self.timeline_refresh_pending is index:self.timeline_refresh_pending=None
                def refresh(buckets):
                    if not current():failed(None);return
                    if buckets!=self.timeline_buckets:
                        from timeline_index import TimelineIndex
                        replacement=TimelineIndex(buckets)
                        counts={key:b-a for key,(a,b) in index.ranges.items()}
                        def populated(key):
                            a,b=index.ranges.get(key,(0,0))
                            return a<b and not index.items[a].metadata.get('placeholder')
                        changed=[key for key,(a,b) in replacement.ranges.items() if counts.get(key)!=b-a and (populated(key) or key==next(iter(replacement.ranges)))]
                        top,height=self.mosaic.visible_range()
                        visible={key for key,(a,b) in self.mosaic.month_extents.items() if b>=top and a<=top+height}
                        if self.mosaic.expanded_month:visible.add(self.mosaic.expanded_month)
                        if top==0:visible.add(next(iter(replacement.ranges),''))
                        existing={item.id for item in index.items}
                        def load():
                            updates={key:client.time_bucket(key,fresh=True) for key in changed};pixels={}
                            incoming=[item for key,items in updates.items() if key in visible for item in items if item.id not in existing][:24]
                            for item in incoming:
                                try:pixels[self.texture_key(item)]=decode_image(client.image_bytes(item))
                                except (LibraryError,OSError,ValueError):pass
                            return updates,pixels
                        def ready(value):
                            failed(None)
                            if not current():return
                            updates,pixels=value
                            for tile in self.mosaic.active_widgets & self.mosaic.tile_set:
                                key=self.texture_key(tile.media_item)
                                if key in self.texture_cache:self.texture_cache.move_to_end(key)
                            for key,pixel in pixels.items():self.texture_cache[key]=self.texture_from_pixels(pixel)
                            while len(self.texture_cache)>768:self.texture_cache.popitem(last=False)
                            # Publish complete changed months together; never blank a loaded month.
                            for key,(a,b) in list(replacement.ranges.items()):
                                if key in updates:replacement.apply(key,updates[key])
                                elif populated(key) and counts.get(key)==b-a:
                                    start,end=index.ranges[key];replacement.apply(key,index.items[start:end])
                            self.timeline_index=replacement;self.timeline_pending=set();self.timeline_buckets=buckets
                            self.page_cache.clear()
                            for key in changed:
                                self.date_cover_cache.pop(('months',key),None);self.date_cover_cache.pop(('years',key[:4]),None)
                            if self.viewer:self.pending_media=(replacement.items,True)
                            else:self.set_library_items(replacement.items,append=True,reflow=True)
                            self.request_timeline_metadata()
                        self.background(load,ready,failed)
                    else:
                        failed(None)
                        top,height=self.mosaic.visible_range()
                        key=next((key for key,(a,b) in self.mosaic.month_extents.items() if b>=top),next(iter(index.ranges),None))
                        if key:
                            index.loaded.discard(key);self.timeline_refresh_key=key
                    self.request_timeline_metadata()
                self.background(lambda:client.time_buckets(fresh=True),refresh,failed)
                return True
            def dates(buckets):
                if buckets!=self.timeline_buckets:
                    self.timeline_buckets=buckets
                    if not self.viewer:self.set_library_items(self.media_items,append=True)
            self.background(self.client.time_buckets,dates,lambda _:None)
        self.search_library(preserve_folder=True,force=True)
        return True

    def request_timeline_metadata(self):
        index=self.timeline_index;client=self.client
        if not index or not client or getattr(client,'restoring',False) or self.current_page!='library' or not self.mosaic.indexed:return
        preferred=[]
        if self.mosaic.indexed:
            top,height=self.mosaic.visible_range()
            if self.mosaic.mode=='all':
                preferred=[key for key,(a,b) in self.mosaic.month_extents.items() if b>=top-height*2 and a<=top+height*3]
            elif self.mosaic.expanded_month:preferred=[self.mosaic.expanded_month]
            elif self.mosaic.expanded_year:preferred=[key for key in index.ranges if key.startswith(self.mosaic.expanded_year)]
        for key in dict.fromkeys([*preferred,*index.ranges]):
            if len(self.timeline_pending)>=3:break
            if key in index.loaded or key in self.timeline_pending or time.monotonic()<index.failed.get(key,0):continue
            self.timeline_pending.add(key)
            def loaded(items,key=key):
                if self.timeline_index is not index:return
                self.timeline_pending.discard(key)
                a,b=index.ranges[key];previous=index.items[a:b];changed=index.apply(key,items)
                if self.mosaic.indexed and self.current_page=='library':
                    if self.viewer:self.pending_media=(index.items,True)
                    elif changed or previous and not previous[0].metadata.get('placeholder') and [item.id for item in previous]!=[item.id for item in index.items[index.ranges[key][0]:index.ranges[key][1]]]:self.set_library_items(index.items,append=True,reflow=True)
                    elif previous!=index.items[index.ranges[key][0]:index.ranges[key][1]]:
                        a,b=index.ranges[key];self.media_items[a:b]=index.items[a:b]
                        self.mosaic.update_bucket(key,index.items[a:b])
                self.request_timeline_metadata();self.load_visible_thumbnails()
            def failed(_message,key=key):
                if self.timeline_index is index:
                    self.timeline_pending.discard(key);index.failed[key]=time.monotonic()+60;self.request_timeline_metadata()
            fresh=getattr(self,'timeline_refresh_key',None)==key
            if fresh:self.timeline_refresh_key=None
            expected=index.ranges[key][1]-index.ranges[key][0]
            def load(key=key,fresh=fresh,expected=expected):
                items=client.time_bucket(key,fresh=fresh)
                return client.time_bucket(key,fresh=True) if len(items)!=expected and not fresh else items
            self.background(load,loaded,failed)

    def set_library_items(self,items,append=False,reflow=False):
        scroll_input=self.scroll_input_serial
        position=self.scroller.get_vadjustment().get_value() if append or self.bucket_scope else 0
        self.loading_more=True
        self.media_items=sorted({item.id:item for item in items}.values(),key=lambda item:item.created,reverse=True)
        old=self.mosaic
        buckets=self.timeline_buckets if self.current_page=='library' and not self.search.entry.get_text() else None
        mosaic=Mosaic(self.open_viewer,self.media_items,buckets,self.open_date_bucket if buckets else None)
        mosaic.cached_texture=lambda item:self.texture_cache.get(self.texture_key(item))
        from copy_ui import media_menu
        mosaic.on_context=lambda item,x,y:media_menu(self,mosaic,item,x,y)
        if append:
            selected={old.tiles[i].media_item.id for i in old.selected}
            mosaic.selection_mode=old.selection_mode
            mosaic.selected={i for i,tile in enumerate(mosaic.tiles) if tile.media_item.id in selected}
        mosaic.mode=self.switcher.get_active_name() if self.current_page=='library' else 'all'
        mosaic.target=old.target
        mosaic.show_durations=old.show_durations
        for tile in mosaic.tiles:
            if tile.media_item and self.texture_key(tile.media_item) in self.texture_cache:self.apply_texture(tile,self.texture_cache[self.texture_key(tile.media_item)])
        mosaic.expanded_month=old.expanded_month
        mosaic.expanded_year=old.expanded_year
        self.populate_date_covers(mosaic)
        mosaic.rebuild()
        animate=reflow or old.tick or mosaic.mode!='all' and (mosaic.expanded_month or mosaic.expanded_year)
        anchor=None
        if reflow and position>0 and old.mode=='all':
            visible=[tile for tile in old.active_widgets & old.tile_set if tile in old.rendered and old.rendered[tile][1]+old.rendered[tile][3]>=position]
            if visible:
                tile=min(visible,key=lambda tile:(old.rendered[tile][1],old.rendered[tile][0]))
                anchor=(tile.media_item.id,position-old.rendered[tile][1])
        mosaic.on_selection=self.selection_changed
        mosaic.on_window=lambda:GLib.idle_add(self.load_visible_thumbnails)
        self.mosaic=mosaic
        self.pending_images.clear()
        self.scroller.set_child(mosaic)
        if anchor:
            tile=next((tile for tile in mosaic.tiles if tile.media_item.id==anchor[0]),None)
            rect=mosaic.target_layout(old.last_width)[0].get(tile)
            if rect:
                position=rect[1]+anchor[1]
                mosaic._target_cache.clear()
        if animate:mosaic.continue_from(old,'reflow' if reflow else None,scroll_shift=position-self.scroller.get_vadjustment().get_value())
        old.dispose()
        mosaic.update_selection()
        self.selection_changed()
        newest=self.media_items[0].created if self.media_items else None
        self.period.set_label('Library' if mosaic.mode=='years' else newest.strftime('%Y' if mosaic.mode=='months' else '%B %Y') if newest else 'Library')
        self.load_more.set_visible(False)
        self.load_more.set_sensitive(True)
        self.stack.set_visible_child_name('library' if self.media_items or buckets and mosaic.mode!='all' else 'status')
        self.status_actions.set_visible(False)
        if not self.media_items:
            self.status.set_icon_name('folder-pictures-symbolic')
            self.status.set_title('No media found')
            self.status.set_description('Choose another folder or change your search.')
        for tile in mosaic.tiles:
            cached=self.texture_cache.get(self.texture_key(tile.media_item))
            if cached:
                self.apply_texture(tile,cached)
        def settle():
            if self.mosaic!=mosaic:return False
            self.loading_more=False
            if self.scroll_input_serial==scroll_input and not self.year_scrollbar.held:self.scroller.get_vadjustment().set_value(position)
            self.load_visible_thumbnails()
            return False
        GLib.timeout_add(32,settle)

    def texture_key(self,item):return item.id+str(item.metadata.get('updatedAt',''))

    def load_visible_thumbnails(self,*_):
        if not hasattr(self,'mosaic') or not hasattr(self,'load_more'):return
        self.year_scrollbar.queue_refresh()
        adjustment=self.scroller.get_vadjustment()
        top=adjustment.get_value();height=adjustment.get_page_size()
        mosaic=self.mosaic
        if mosaic.indexed:self.request_timeline_metadata()
        wanted={}
        tiles=[]
        for tile in mosaic.active_widgets & mosaic.tile_set:
            rect=mosaic.rendered.get(tile)
            if not rect or tile.media_item.metadata.get('placeholder'):continue
            distance=abs(rect[1]+rect[3]/2-top-height/2)/max(1,height)
            key=(id(mosaic),tile.media_item.id);wanted[key]=distance
            tiles.append((distance,tile,key))
        self.image_wanted=wanted
        if self.client and mosaic.mode!='all':self.load_date_covers(mosaic,top,height,wanted)
        for _,tile,key in sorted(tiles,key=lambda row:row[0]):
            if tile.media_texture is None and self.texture_key(tile.media_item) in self.texture_cache:self.apply_texture(tile,self.texture_cache[self.texture_key(tile.media_item)])
            if tile.media_texture is None and not getattr(self.client,'restoring',False) and time.monotonic()>=getattr(tile,'retry_after',0) and (tile.media_item.kind=='IMAGE' or self.client):
                key=(id(mosaic),tile.media_item.id)
                if key not in self.pending_images:
                    self.pending_images.add(key);self.load_thumbnail(tile,mosaic,key)
            if tile.media_item.kind=='VIDEO' and not getattr(self.client,'restoring',False):self.preload_video(tile.media_item,job_key=key)

    def load_date_covers(self,mosaic,top,height,wanted):
        from datetime import datetime,timedelta
        client=self.client
        cards=mosaic.year_cards if mosaic.mode=='years' else mosaic.month_cards
        for key,card in cards.items():
            rect=mosaic.rendered.get(card)
            if not rect or rect[1]+rect[3]<max(0,top-height*2) or rect[1]>top+height*3:continue
            job_key=(id(mosaic),'cover',mosaic.mode,key)
            wanted[job_key]=abs(rect[1]+rect[3]/2-top-height/2)/max(1,height)
            if getattr(card,'covers_requested',False):continue
            if time.monotonic()<getattr(card,'retry_after',0):continue
            card.covers_requested=True
            cache_key=(mosaic.mode,key)
            if cache_key in self.date_cover_cache:
                values=self.date_cover_cache[cache_key]
                for i,picture in enumerate(mosaic.card_pictures[card]):
                    if values:
                        picture.media_id,texture=values[min(i,len(values)-1)];picture.set_paintable(texture)
                continue
            start=datetime.strptime(key,'%Y' if mosaic.mode=='years' else '%Y-%m')
            end=datetime(start.year+1,1,1) if mosaic.mode=='years' or start.month==12 else datetime(start.year,start.month+1,1)
            filters={'takenAfter':start.isoformat(timespec='milliseconds')+'Z','takenBefore':(end-timedelta(milliseconds=1)).isoformat(timespec='milliseconds')+'Z'}
            def load(filters=filters,job_key=job_key):
                if self.mosaic!=mosaic or job_key not in self.image_wanted:return None
                items,_=client.search(filters,size=4)
                values=[]
                for item in items:
                    if job_key not in self.image_wanted:return None
                    values.append((item.id,decode_image(client.image_bytes(item),240)))
                return values
            def ready(values,card=card,cache_key=cache_key):
                if self.mosaic!=mosaic:return
                if values is None:card.covers_requested=False;return
                values=[(asset,self.texture_from_pixels(value)) for asset,value in values]
                self.date_cover_cache[cache_key]=values;self.date_cover_cache.move_to_end(cache_key)
                while len(self.date_cover_cache)>96:self.date_cover_cache.popitem(last=False)
                if cache_key[0]=='months':
                    year=cache_key[1][:4]
                    newest=next((month[0] for month in mosaic.months if month[2]==year),None)
                    if newest==cache_key[1]:self.date_cover_cache[('years',year)]=values
                for i,picture in enumerate(mosaic.card_pictures[card]):
                    if values:
                        picture.media_id,texture=values[min(i,len(values)-1)];picture.set_paintable(texture)
                self.populate_date_covers(mosaic)
            def failed(_message,card=card):card.covers_requested=False;card.retry_after=time.monotonic()+60
            self.background(load,ready,failed,images=True,priority=lambda job_key=job_key:self.image_wanted.get(job_key))

    def populate_date_covers(self,mosaic):
        for mode,cards in [('months',mosaic.month_cards),('years',mosaic.year_cards)]:
            for key,card in cards.items():
                values=self.date_cover_cache.get((mode,key),[])
                for i,picture in enumerate(mosaic.card_pictures[card]):
                    if values:
                        picture.media_id,texture=values[min(i,len(values)-1)];picture.set_paintable(texture)

    def scroll_changed(self,*_):
        self.mosaic.queue_allocate()
        self.load_visible_thumbnails()
        if not self.client and not self.local_items:return
        if self.stack.get_visible_child_name()!='library' or self.viewer:return
        adjustment=self.scroller.get_vadjustment()
        if self.next_page and not self.loading_more and adjustment.get_value()>0 and adjustment.get_value()+adjustment.get_page_size()>=adjustment.get_upper()-400:
            self.search_library(append=True)

    def flush_pending_media(self):
        if self.pending_media:
            items,append=self.pending_media;self.pending_media=None
            if self.mosaic.indexed and self.timeline_index and len(self.mosaic.tiles)==len(self.timeline_index.items):
                for key,(a,b) in self.timeline_index.ranges.items():
                    if self.media_items[a:b]!=self.timeline_index.items[a:b]:self.mosaic.update_bucket(key,self.timeline_index.items[a:b])
                self.load_visible_thumbnails();return
            self.set_library_items(items,append)

    def load_thumbnail(self,tile,mosaic,pending_key=None):
        item=tile.media_item
        client=self.client
        vault=self.vault
        cache=(vault if item.metadata.get('visibility')=='locked' else client.media_cache()) if client and not item.path else None
        if cache and not item.metadata.get('visibility') and (client.locked_until or client.server_lock_pending):cache=None
        cached=cache and cache.has(client.image_key(item))
        proxy=self.get_video_proxy() if client and item.kind=='VIDEO' else None
        def load():
            if self.mosaic!=mosaic or pending_key not in self.image_wanted:return None
            if cached:
                data=cache.get(client.image_key(item))
                if data is None:return None
            elif item.path:
                stat=Path(item.path).stat()
                data=self.disk_cache.fetch(f'{item.path}:{stat.st_mtime_ns}:{stat.st_size}',lambda:thumbnail_bytes(item.path))
            else:
                try:data=client.image_bytes(item,vault=vault)
                except LibraryError as error:
                    if item.kind!='VIDEO' or error.status!=404:raise
                    from video_edit import Edits,frame
                    uri=proxy.register(client,item,vault)
                    try:data=frame(uri,Edits(0,1))
                    finally:proxy.unregister(uri)
            try:return decode_image(data)
            except (OSError,ValueError):
                storage=vault if item.metadata.get('visibility')=='locked' else client.media_cache() if client else self.disk_cache
                storage.remove(client.image_key(item) if client else f'{item.path}:{stat.st_mtime_ns}:{stat.st_size}') if storage else None
                raise LibraryError('The image could not be decoded. Refresh to retry.') from None
        def ready(value):
            self.pending_images.discard(pending_key)
            if self.mosaic!=mosaic:return
            if value is None:
                if pending_key in self.image_wanted:GLib.idle_add(self.load_visible_thumbnails)
                return
            texture=self.texture_from_pixels(value)
            key=self.texture_key(item)
            self.texture_cache[key]=texture
            self.texture_cache.move_to_end(key)
            while len(self.texture_cache)>768:self.texture_cache.popitem(last=False)
            self.apply_texture(tile,texture)
        def failed(message):
            self.pending_images.discard(pending_key)
            tile.retry_after=time.monotonic()+60
            tile.set_tooltip_text(item.filename+' · '+message)
            tile.media_icon.set_from_icon_name('dialog-error-symbolic')
        self.background(load,ready,failed,images='cached' if cached else True,priority=lambda:self.image_wanted.get(pending_key))

    def texture_from_pixels(self,value):
        width,height,data=value
        return Gdk.MemoryTexture.new(width,height,Gdk.MemoryFormat.R8G8B8A8,GLib.Bytes.new(data),width*4)

    def apply_texture(self,tile,texture):
        tile.media_texture=texture
        tile.photo_picture.set_paintable(texture)
        tile.media_icon.set_visible(False)
        tile.set_tooltip_text(tile.filename)
        for picture in self.mosaic.cover_slots.get(tile,[]):
            picture.media_id=tile.media_item.id;picture.set_paintable(texture)

    def load_preview(self,stage,source):
        item=source.media_item
        if not item or item.kind!='IMAGE':return
        client=self.client
        vault=self.vault
        def load():
            if not self.viewer or self.viewer.stage!=stage:return None
            return decode_image(item.path if item.path else client.image_bytes(item,True,vault),2400)
        def ready(value):
            if not self.viewer or self.viewer.stage!=stage:return
            stage.set_texture(self.texture_from_pixels(value))
        self.background(load,ready,lambda message:self.notice('Preview could not load: '+message),images='preview')
