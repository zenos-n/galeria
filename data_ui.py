"""Background I/O and GTK handoff for connected libraries."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk
from library import ImmichClient, LibraryError, scan_folders
from timeline import Mosaic


class LibraryUI:
    def init_data(self):
        self.client=None
        self.media_items=[]
        self.local_items=[]
        self.local_roots=[]
        self.next_page=None
        self.album_items=[]
        self.album_result_id=None
        self.data_generation=0
        self.search_generation=0
        self.texture_cache={}
        self.io=ThreadPoolExecutor(max_workers=3,thread_name_prefix='gallery-io')
        self.images=ThreadPoolExecutor(max_workers=4,thread_name_prefix='gallery-images')
        self.connect('close-request',self.stop_data)

    def stop_data(self,*_):
        self.data_generation+=1
        self.io.shutdown(wait=False,cancel_futures=True)
        self.images.shutdown(wait=False,cancel_futures=True)
        if self.client:
            self.client.token=None
        return False

    def background(self,work,done,failed=None,images=False):
        generation=self.data_generation
        def execute():
            if generation!=self.data_generation:
                return None
            return work()
        future=(self.images if images else self.io).submit(execute)
        def completed(result):
            if result.cancelled():
                return
            try:
                value=result.result()
            except Exception as error:
                message=str(error) if isinstance(error,LibraryError) else 'Could not load this data.'
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
        self.load_more.set_sensitive(True)
        self.status_actions.set_visible(False)
        self.status.set_icon_name('dialog-error-symbolic')
        self.status.set_title('Could not load the library')
        self.status.set_description(message)
        self.stack.set_visible_child_name('status')
        self.notice(message)

    def connect_local(self,paths):
        self.data_generation+=1
        self.client=None
        self.local_items=[]
        self.library_mode='local'
        self.local_roots=paths
        self.texture_cache.clear()
        self.search.set_mode('local')
        self.album_tree.set_albums([])
        self.navigate(self.rows['library'].get_parent(),self.rows['library'])
        self.busy_library('Reading your folders…')
        def probe(path):
            try:info,width,height=GdkPixbuf.Pixbuf.get_file_info(path)
            except GLib.Error:return 1.5
            return width/height if info and height else 1.5
        def loaded(value):
            self.local_items,errors=value
            self.source_label.set_label(Path(paths[0]).name if len(paths)==1 else f'{len(paths)} folders')
            self.search_library()
            if errors:
                self.notice(f'{len(errors)} files or folders could not be read.')
        self.background(lambda:scan_folders(paths,probe),loaded,self.library_failed)

    def connect_immich(self,client):
        self.data_generation+=1
        self.search_generation+=1
        self.client=client
        self.library_mode='immich'
        self.local_items=[]
        self.texture_cache.clear()
        self.search.set_mode('immich')
        self.source_label.set_label(client.user.get('name') or client.user.get('email') or 'Immich')
        self.current_page='library'
        self.background(client.albums,self.album_tree.set_albums)
        self.navigate(self.rows['library'].get_parent(),self.rows['library'])

    def refresh_library(self):
        if self.client:
            self.background(self.client.albums,self.album_tree.set_albums)
            self.search_library()
        elif self.local_roots:
            self.connect_local(self.local_roots)
        else:
            self.welcome()

    def search_library(self,append=False):
        if self.viewer:
            return
        if self.current_page not in ('library','photos','videos','screenshots','live','favorites','archive','trash') and not self.current_page.startswith('album-'):
            return
        self.search_generation+=1
        request_id=self.search_generation
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
            self.set_library_items(items[:count])
            return
        if not self.client:
            return
        if self.current_page.startswith('album-'):
            album_id=self.current_page.removeprefix('album-')
            client=self.client
            if append and self.album_result_id==album_id:
                count=len(self.media_items)+100
                self.next_page=count if len(self.album_items)>count else None
                self.set_library_items(self.album_items[:count])
                return
            self.busy_library('Loading album…')
            self.next_page=None
            def loaded(items):
                if request_id!=self.search_generation:return
                self.album_items=items
                self.album_result_id=album_id
                self.next_page=100 if len(items)>100 else None
                self.set_library_items(items[:100])
            self.background(lambda:client.album(album_id),
                            loaded,
                            lambda error:self.library_failed(error) if request_id==self.search_generation else None)
            return
        client=self.client
        try:
            filters,query=self.search.request_filters()
        except ValueError as error:
            self.notice(str(error));return
        page=self.current_page
        if page in ('photos','videos'):filters['type']='IMAGE' if page=='photos' else 'VIDEO'
        if page=='screenshots':filters['originalFileName']='Screenshot'
        if page=='live':filters['isMotion']=True
        if page=='favorites':filters['isFavorite']=True
        if page=='archive':filters['visibility']='archive'
        if page=='trash':filters.pop('visibility',None);filters['isTrashed']=True
        next_page=int(self.next_page) if append and self.next_page else 1
        if not append:self.busy_library('Loading your photos…')
        self.load_more.set_sensitive(False)
        def loaded(value):
            if request_id!=self.search_generation:return
            items,self.next_page=value
            self.set_library_items(self.media_items+items if append else items)
        def failed(message):
            if request_id==self.search_generation:self.library_failed(message)
        self.background(lambda:client.search(filters,query,next_page),loaded,failed)

    def set_library_items(self,items):
        self.media_items=sorted({item.id:item for item in items}.values(),key=lambda item:item.created,reverse=True)
        old=self.mosaic
        mosaic=Mosaic(self.open_viewer,self.media_items)
        mosaic.mode=self.switcher.get_active_name() if self.current_page=='library' else 'all'
        mosaic.target=old.target
        mosaic.show_durations=old.show_durations
        mosaic.rebuild()
        mosaic.on_selection=self.selection_changed
        self.mosaic=mosaic
        self.scroller.set_child(mosaic)
        old.dispose()
        self.selection_changed()
        self.change_mode()
        self.load_more.set_visible(bool(self.next_page))
        self.load_more.set_sensitive(True)
        self.stack.set_visible_child_name('library' if self.media_items else 'status')
        self.status_actions.set_visible(False)
        if not self.media_items:
            self.status.set_icon_name('folder-pictures-symbolic')
            self.status.set_title('No media found')
            self.status.set_description('Choose another folder or change your search.')
        ids={item.id for item in self.media_items}
        self.texture_cache={key:value for key,value in self.texture_cache.items() if key in ids}
        for tile in mosaic.tiles:
            cached=self.texture_cache.get(tile.media_item.id)
            if cached:
                self.apply_texture(tile,cached)
            elif tile.media_item.kind=='IMAGE' or self.client:
                self.load_thumbnail(tile,mosaic)

    def load_thumbnail(self,tile,mosaic):
        item=tile.media_item
        client=self.client
        def load():
            if item.path:
                return GdkPixbuf.Pixbuf.new_from_file_at_scale(item.path,360,360,True).apply_embedded_orientation()
            return client.thumbnail(item.id)
        def ready(value):
            if self.mosaic!=mosaic:return
            try:
                texture=Gdk.Texture.new_from_bytes(GLib.Bytes.new(value)) if isinstance(value,bytes) else Gdk.Texture.new_for_pixbuf(value)
                self.texture_cache[item.id]=texture
                self.apply_texture(tile,texture)
            except GLib.Error:
                tile.set_tooltip_text(item.filename+' · Thumbnail unavailable')
        self.background(load,ready,lambda _:tile.set_tooltip_text(item.filename+' · Thumbnail unavailable'),images=True)

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
        def load():
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(item.path,2400,2400,True).apply_embedded_orientation() if item.path else client.thumbnail(item.id,True)
        def ready(value):
            if not self.viewer or self.viewer.stage!=stage:return
            try:
                texture=Gdk.Texture.new_from_bytes(GLib.Bytes.new(value)) if isinstance(value,bytes) else Gdk.Texture.new_for_pixbuf(value)
                stage.set_texture(texture)
            except GLib.Error:pass
        self.background(load,ready,lambda _:self.notice('The full preview could not be loaded.'),images=True)
