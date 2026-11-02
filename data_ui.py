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


class LibraryUI:
    def init_data(self):
        self.client=None
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
        self.pending_images=set()
        self.loading_more=False
        self.pending_media=None
        self.vault=None
        self.sync_cancel=threading.Event()
        self.scope_filters={}
        self.timeline_buckets=[]
        self.dates_ready=True
        self.bucket_scope={}
        self.io=ThreadPoolExecutor(max_workers=3,thread_name_prefix='gallery-io')
        self.images=ThreadPoolExecutor(max_workers=4,thread_name_prefix='gallery-images')
        self.previews=ThreadPoolExecutor(max_workers=2,thread_name_prefix='gallery-preview')
        self.video_io=ThreadPoolExecutor(max_workers=2,thread_name_prefix='gallery-video')
        self.video_proxy=None;self.video_prefetch=set()
        self.connect('close-request',self.stop_data)

    def stop_data(self,*_):
        self.data_generation+=1
        self.io.shutdown(wait=False,cancel_futures=True)
        self.images.shutdown(wait=False,cancel_futures=True)
        self.previews.shutdown(wait=False,cancel_futures=True)
        self.video_io.shutdown(wait=False,cancel_futures=True)
        if self.viewer and self.viewer.stage.video_player:self.viewer.stage.video_player.stop()
        if self.video_proxy:threading.Thread(target=self.video_proxy.close,daemon=True).start()
        self.sync_cancel.set()
        if self.client:
            self.client.token=None
        return False

    def save_preferences(self):preferences_write(self.preferences)

    def get_video_proxy(self):
        if self.video_proxy is None:
            from video_proxy import VideoProxy
            self.video_proxy=VideoProxy()
        return self.video_proxy

    def preload_video(self,item):
        key=self.texture_key(item)
        if key in self.video_prefetch:return
        self.video_prefetch.add(key)
        client=self.client;vault=self.vault
        proxy=self.get_video_proxy() if client else None
        def work():
            if item.path:
                with open(item.path,'rb') as stream:stream.read(2*1024*1024)
            else:proxy.preload(client,item,vault)
        self.background(work,lambda _:None,lambda _:None,images='video')

    def remember_account(self,client):
        def store():
            if not secret_put(client.identity,'session',client.token):raise LibraryError('The system keyring could not save this account.')
        self.background(store,lambda _:None,lambda message:self.notice(message))

    def sign_out(self):
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
        self.texture_cache.clear();self.pending_images.clear()
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

    def restore_last_library(self):
        mode=self.preferences.get('mode')
        if mode=='local' and self.preferences.get('folders'):
            self.connect_local(self.preferences['folders']);return False
        if mode=='immich' and self.preferences.get('remember'):
            def restore():
                client=ImmichClient(self.preferences['server'])
                client.token=secret_get(client.base+'|'+self.preferences['user_id'],'session')
                if not client.token:return None
                client.user=client.request('/users/me')
                client.detect_version()
                client.lock_session()
                return client
            self.busy_library('Reconnecting to your library…')
            self.background(restore,lambda client:self.connect_immich(client) if client else self.welcome(),lambda _:self.welcome())
        else:self.welcome()
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
            body=Gtk.Box(spacing=10,margin_start=10,margin_end=8)
            body.append(Gtk.Image(icon_name='folder-pictures-symbolic',pixel_size=16))
            body.append(Gtk.Label(label=album.get('albumName','Untitled album'),xalign=0,ellipsize=3,hexpand=True))
            row.set_child(body);self.pin_nav.append(row);self.pin_rows.append(row)

    def manage_pins(self):
        if not self.client:self.login();return
        dialog=Adw.PreferencesDialog(title='Pin albums',content_width=460,content_height=500)
        page=Adw.PreferencesPage();group=Adw.PreferencesGroup()
        identity=self.client.identity
        selected=self.preferences.setdefault('pins',{}).setdefault(identity,[])
        for album in getattr(self.album_tree,'albums',[]):
            row=Adw.SwitchRow(title=album.get('albumName','Untitled album'),use_markup=False,active=album['id'] in selected)
            def toggle(row,_param,album=album):
                ids=self.preferences['pins'][identity]
                if row.get_active() and album['id'] not in ids:ids.append(album['id'])
                elif not row.get_active() and album['id'] in ids:ids.remove(album['id'])
                self.save_preferences();self.refresh_pins()
            row.connect('notify::active',toggle);group.add(row)
        page.add(group);dialog.add(page);self.dialog=dialog;dialog.present(self)

    def open_collection(self,title,filters=None,items=None):
        self.search_generation+=1
        self.current_page='collection'
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
        client=self.client
        self.sync_cancel.set();self.vault=None
        self.data_generation+=1
        self.texture_cache.clear();self.pending_images.clear()
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

    def selected_action(self,action):
        if not self.client:self.notice('Local files are read-only.');return
        ids=[self.mosaic.tiles[i].media_item.id for i in self.mosaic.selected]
        if not ids:return
        restore=action=='trash' and self.current_page=='trash'
        def perform():
            if action=='favorite':return self.client.update_assets(ids,{'isFavorite':True})
            return self.client.restore_assets(ids) if restore else self.client.trash_assets(ids)
        def done(_):
            self.mosaic.set_selection(False);self.refresh_library()
            self.notice('Items restored.' if restore else 'Favorites updated.' if action=='favorite' else 'Items moved to trash.')
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

    def background(self,work,done,failed=None,images=False):
        generation=self.data_generation
        def execute():
            if generation!=self.data_generation:
                return None
            return work()
        future=(self.video_io if images=='video' else self.previews if images=='preview' else self.images if images else self.io).submit(execute)
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
        self.sync_cancel.set();self.vault=None;self.pending_media=None
        self.lock_button.set_visible(False)
        self.data_generation+=1
        self.client=None
        self.video_prefetch.clear()
        self.update_account_ui()
        self.timeline_buckets=[];self.dates_ready=True;self.bucket_scope={}
        self.local_items=[]
        self.library_mode='local'
        self.local_roots=paths
        self.preferences.update(mode='local',folders=paths)
        self.save_preferences()
        self.texture_cache.clear()
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
        self.sync_cancel.set();self.vault=None;self.pending_media=None
        self.lock_button.set_visible(False)
        self.data_generation+=1
        self.search_generation+=1
        self.client=client
        self.video_prefetch.clear()
        self.timeline_buckets=[];self.dates_ready=False;self.bucket_scope={}
        client.media_cache()
        self.library_mode='immich'
        self.local_items=[]
        self.texture_cache.clear()
        self.pending_images.clear()
        self.preferences.update(mode='immich',server=client.base,user_id=client.user['id'],email=client.user.get('email',''))
        self.save_preferences()
        self.search.set_mode('immich')
        self.source_label.set_label(client.user.get('name') or client.user.get('email') or 'Immich')
        self.update_account_ui()
        self.current_page='library'
        self.background(client.albums,self.album_tree.set_albums)
        self.navigate(self.rows['library'].get_parent(),self.rows['library'])
        def dates_loaded(buckets):
            self.timeline_buckets=buckets;self.dates_ready=True
            if self.current_page=='library':self.search_library()
        def dates_failed(message):
            self.dates_ready=True;self.notice('Date index unavailable: '+message)
            if self.current_page=='library':self.search_library()
        self.background(client.time_buckets,dates_loaded,dates_failed)

    def open_date_bucket(self,kind,key):
        from datetime import datetime,timedelta
        if not self.client:return
        start=datetime.strptime(key,'%Y' if kind=='year' else '%Y-%m')
        end=datetime(start.year+1,1,1) if kind=='year' or start.month==12 else datetime(start.year,start.month+1,1)
        self.bucket_scope={'takenAfter':start.isoformat(timespec='milliseconds')+'Z',
                           'takenBefore':(end-timedelta(milliseconds=1)).isoformat(timespec='milliseconds')+'Z'}
        self.search_library(preserve_folder=True)

    def refresh_library(self):
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

    def search_library(self,append=False,preserve_folder=False):
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
        next_page=self.next_page if append and self.next_page else 1
        if not append and not preserve_folder:self.busy_library('Loading your photos…')
        self.load_more.set_sensitive(False)
        def loaded(value):
            if request_id!=self.search_generation:return
            items,self.next_page=value
            result=self.media_items+items if append else items
            if self.viewer:
                self.pending_media=(result,append)
                self.loading_more=False
            else:self.set_library_items(result,append=append)
        def failed(message):
            if request_id==self.search_generation:self.library_failed(message)
        self.background(lambda:client.search(filters,query,next_page),loaded,failed)

    def set_library_items(self,items,append=False):
        position=self.scroller.get_vadjustment().get_value() if append or self.bucket_scope else 0
        self.loading_more=True
        self.media_items=sorted({item.id:item for item in items}.values(),key=lambda item:item.created,reverse=True)
        old=self.mosaic
        buckets=self.timeline_buckets if self.current_page=='library' and not self.search.entry.get_text() else None
        mosaic=Mosaic(self.open_viewer,self.media_items,buckets,self.open_date_bucket if buckets else None)
        if append:
            selected={old.tiles[i].media_item.id for i in old.selected}
            mosaic.selection_mode=old.selection_mode
            mosaic.selected={i for i,tile in enumerate(mosaic.tiles) if tile.media_item.id in selected}
        mosaic.mode=self.switcher.get_active_name() if self.current_page=='library' else 'all'
        mosaic.target=old.target
        mosaic.show_durations=old.show_durations
        mosaic.expanded_month=old.expanded_month
        mosaic.expanded_year=old.expanded_year
        mosaic.rebuild()
        mosaic.on_selection=self.selection_changed
        self.mosaic=mosaic
        self.pending_images.clear()
        self.scroller.set_child(mosaic)
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
            self.scroller.get_vadjustment().set_value(position)
            self.load_visible_thumbnails()
            return False
        GLib.timeout_add(32,settle)

    def texture_key(self,item):return item.id+str(item.metadata.get('updatedAt',''))

    def load_visible_thumbnails(self,*_):
        if not hasattr(self,'mosaic') or not hasattr(self,'load_more'):return
        adjustment=self.scroller.get_vadjustment()
        top=adjustment.get_value();height=adjustment.get_page_size()
        mosaic=self.mosaic
        for tile in mosaic.tiles:
            rect=mosaic.rendered.get(tile)
            wanted=bool(rect and rect[1]+rect[3]>=max(0,top-height*2) and rect[1]<=top+height*3)
            if mosaic.mode!='all' and tile in mosaic.cover_slots:wanted=True
            if wanted and tile.media_texture is None and (tile.media_item.kind=='IMAGE' or self.client):
                key=(id(mosaic),tile.media_item.id)
                if key not in self.pending_images:
                    self.pending_images.add(key);self.load_thumbnail(tile,mosaic,key)
            if wanted and tile.media_item.kind=='VIDEO':self.preload_video(tile.media_item)

    def scroll_changed(self,*_):
        self.load_visible_thumbnails()
        if not self.client and not self.local_items:return
        if self.stack.get_visible_child_name()!='library' or self.viewer:return
        adjustment=self.scroller.get_vadjustment()
        if self.next_page and not self.loading_more and adjustment.get_value()>0 and adjustment.get_value()+adjustment.get_page_size()>=adjustment.get_upper()-400:
            self.search_library(append=True)

    def flush_pending_media(self):
        if self.pending_media:
            items,append=self.pending_media;self.pending_media=None
            self.set_library_items(items,append)

    def load_thumbnail(self,tile,mosaic,pending_key=None):
        item=tile.media_item
        client=self.client
        vault=self.vault
        def load():
            if self.mosaic!=mosaic:return None
            if item.path:
                stat=Path(item.path).stat()
                data=self.disk_cache.fetch(f'{item.path}:{stat.st_mtime_ns}:{stat.st_size}',lambda:thumbnail_bytes(item.path))
            else:data=client.image_bytes(item,vault=vault)
            try:return decode_image(data)
            except (OSError,ValueError):
                cache=vault if item.metadata.get('visibility')=='locked' else client.media_cache() if client else self.disk_cache
                cache.remove(client.image_key(item) if client else f'{item.path}:{stat.st_mtime_ns}:{stat.st_size}') if cache else None
                raise LibraryError('The image could not be decoded. Refresh to retry.') from None
        def ready(value):
            self.pending_images.discard(pending_key)
            if self.mosaic!=mosaic:return
            texture=self.texture_from_pixels(value)
            key=self.texture_key(item)
            self.texture_cache[key]=texture
            self.texture_cache.move_to_end(key)
            while len(self.texture_cache)>256:self.texture_cache.popitem(last=False)
            self.apply_texture(tile,texture)
        def failed(message):
            tile.set_tooltip_text(item.filename+' · '+message)
            tile.media_icon.set_from_icon_name('dialog-error-symbolic')
            if not getattr(mosaic,'reported_error',False):
                mosaic.reported_error=True
                self.notice('Media could not load: '+message)
        self.background(load,ready,failed,images=True)

    def texture_from_pixels(self,value):
        width,height,data=value
        return Gdk.MemoryTexture.new(width,height,Gdk.MemoryFormat.R8G8B8A8,GLib.Bytes.new(data),width*4)

    def apply_texture(self,tile,texture):
        tile.media_texture=texture
        tile.photo_picture.set_paintable(texture)
        tile.media_icon.set_visible(False)
        tile.set_tooltip_text(tile.filename)
        for picture in self.mosaic.cover_slots.get(tile,[]):picture.set_paintable(texture)

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
