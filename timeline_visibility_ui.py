"""Timeline visibility preferences and background rule updates."""
from copy import deepcopy
from pathlib import Path
from gi.repository import Adw,GLib,Gtk
from timeline_visibility import TimelineVisibility,rules_for,screenshot_name


def identity(window):return window.client.identity if window.client else 'local'


def rules(window):return rules_for(window.preferences,identity(window))


def after_paint(window,callback):
    clock=window.get_frame_clock()
    if clock:
        def painted(clock):
            clock.disconnect(handler)
            if not window.data_stopped:callback()
        handler=clock.connect_after('after-paint',painted);window.queue_draw()
    else:callback()


def update(window,values,done=lambda _success:None):
    key=identity(window);old=deepcopy(rules(window));client=window.client
    previous=getattr(client,'timeline_visibility',None) if client else None
    policy=TimelineVisibility(values)
    window.preferences.setdefault('timeline_visibility',{})[key]=values
    window.save_preferences()
    window.pending_visibility_refresh=None
    window.search_generation+=1
    window.page_cache.clear();window.date_cover_cache.clear()
    if not client:
        source=window.local_items;window.timeline_visibility_pending=True
        toast=Adw.Toast(title='Updating timeline…',timeout=0);window.toast.add_toast(toast)
        def current_local():return window.client is None and window.local_items is source and TimelineVisibility(rules(window)).cache_key==policy.cache_key
        def ready_local(items):
            toast.dismiss()
            if not current_local():done(False);return
            window.timeline_visibility_pending=False
            window.local_visibility_cache=(source,policy.cache_key,items)
            window.search_library(preserve_folder=True,force=True);done(True)
        def failed_local(message):
            toast.dismiss()
            if not current_local():done(False);return
            window.timeline_visibility_pending=False
            window.preferences['timeline_visibility'][key]=old;window.save_preferences()
            window.notice('Could not update timeline: '+message);done(False)
        after_paint(window,lambda:window.background(lambda:policy.filter(source),ready_local,failed_local) if current_local() else toast.dismiss())
        return
    client.timeline_visibility=policy
    window.timeline_visibility_pending=True
    toast=Adw.Toast(title='Updating timeline…',timeout=0);window.toast.add_toast(toast)
    def progress(count):
        if window.client is client and client.timeline_visibility is policy and window.timeline_visibility_pending:
            toast.set_title(f'Updating timeline… {count:,} items checked')
        return False
    policy.on_progress=lambda count:GLib.idle_add(progress,count)
    client.refresh_serial=getattr(client,'refresh_serial',0)+1
    loaded=set(window.timeline_index.loaded) if window.timeline_index else set()
    def work():
        from timeline_index import TimelineIndex
        buckets=client.time_buckets(fresh=True)
        index=TimelineIndex(buckets) if client.modern_search else None
        if index:
            for month in loaded & index.ranges.keys():
                items=client.time_bucket(month,cached=True)
                if items is not None:index.apply(month,items)
        return buckets,index
    def ready(value):
        if window.client is not client or client.timeline_visibility is not policy:toast.dismiss();done(False);return
        window.timeline_buckets,window.timeline_index=value
        window.timeline_pending=set();window.dates_ready=True
        def finished():
            toast.dismiss();window.timeline_visibility_pending=False;done(True)
        def rebuild():
            if window.client is not client or client.timeline_visibility is not policy:return
            if window.viewer and not window.viewer.device_file:
                window.pending_visibility_refresh=rebuild;finished();return
            if not window.filtering_timeline():finished();return
            if window.timeline_index is None:
                finished();window.search_library(preserve_folder=True,force=True);return
            from layout import prepare_timeline
            from pending_uploads import manager
            window.timeline_visibility_pending=True
            index=window.timeline_index;mosaic=window.mosaic
            def state():
                uploads=manager(window,False)
                pending=tuple((key,id(entry['item'])) for key,entry in uploads.entries.items()) if uploads else ()
                removing=frozenset(id for generation,ids in window.pending_removals.values() if generation==window.data_generation for id in ids)
                return (window.mosaic.last_width,window.mosaic.target,window.mosaic.mode,window.mosaic.expanded_month,window.mosaic.expanded_year),pending,removing
            captured=state();dimensions,pending,removing=captured
            uploads=manager(window,False);values=uploads.merge(index.items) if uploads else list(index.items)
            buckets=list(window.timeline_buckets)
            def plan():
                width,target,mode,month,year=dimensions
                return prepare_timeline(policy.filter(values),buckets,width,target,removed=removing,mode=mode,expanded_month=month,expanded_year=year)
            def applied(prepared):
                if window.client is not client or client.timeline_visibility is not policy:toast.dismiss();done(False);return
                if window.mosaic is not mosaic or window.timeline_index is not index or captured!=state() or not window.filtering_timeline() or window.viewer and not window.viewer.device_file:
                    rebuild();return
                window.set_library_items(prepared['items'],append=True,reflow=True,prepared=prepared)
                finished();window.request_timeline_metadata()
            window.background(plan,applied,failed,executor=window.layout_io)
        rebuild()
    def failed(message):
        toast.dismiss()
        if window.client is not client or client.timeline_visibility is not policy:return
        client.timeline_visibility=previous;window.timeline_visibility_pending=False
        window.preferences['timeline_visibility'][key]=old;window.save_preferences()
        if window.current_page=='library':window.search_library(preserve_folder=True,force=True)
        window.notice('Could not update timeline: '+message);done(False)
    def start():
        if not window.data_stopped and window.client is client and client.timeline_visibility is policy:
            window.background(work,ready,failed)
        else:toast.dismiss();done(False)
        return False
    after_paint(window,start)


def toggle_album(window,album_id):
    values=deepcopy(rules(window));hidden=values.setdefault('albums',[])
    if album_id in hidden:hidden.remove(album_id)
    else:hidden.append(album_id)
    update(window,values)


def preferences_group(window):
    group=Adw.PreferencesGroup(title='Timeline',description='Visibility on this computer only. Hidden items remain in albums and search.')
    screenshots=Adw.SwitchRow(title='Hide screenshots',subtitle='Screenshot filenames and screenshot albums stay out of the main timeline',active=bool(rules(window).get('screenshots')))
    changing=False
    def changed(row,_):
        nonlocal changing
        if changing:return
        values=deepcopy(rules(window));values['screenshots']=row.get_active();group.set_sensitive(False)
        def finished(success):
            nonlocal changing
            changing=True;row.set_active(bool(rules(window).get('screenshots')));changing=False
            group.set_sensitive(True)
        update(window,values,finished)
    screenshots.connect('notify::active',changed);group.add(screenshots)
    manage=Adw.ActionRow(title='Albums in timeline' if window.client else 'Hidden folders',activatable=True)
    manage.add_suffix(Gtk.Image(icon_name='go-next-symbolic'))
    manage.connect('activated',lambda _:manage_visibility(window))
    group.add(manage)
    return group


def manage_visibility(window):
    client=window.client
    dialog=Adw.PreferencesDialog(title='Albums in timeline' if client else 'Hidden folders',content_width=520,content_height=560)
    page=Adw.PreferencesPage()
    group=Adw.PreferencesGroup(description='These settings affect only the main timeline in Galeria on this computer.')
    page.add(group);dialog.add(page)
    if client:
        albums=list(getattr(window.album_tree,'albums',[]))
        def populate(albums):
            for album in albums:
                automatic=bool(rules(window).get('screenshots') and screenshot_name(album.get('albumName','')))
                row=Adw.SwitchRow(title=album.get('albumName','Untitled album'),use_markup=False,
                    subtitle='Hidden by “Hide screenshots”' if automatic else '',
                    active=not automatic and album['id'] not in rules(window).get('albums',[]),sensitive=not automatic)
                changing={'value':False}
                def changed(row,_,album=album,changing=changing):
                    if changing['value']:return
                    values=deepcopy(rules(window));hidden=values.setdefault('albums',[])
                    if row.get_active():
                        if album['id'] in hidden:hidden.remove(album['id'])
                    elif album['id'] not in hidden:hidden.append(album['id'])
                    group.set_sensitive(False)
                    def finished(success):
                        changing['value']=True;row.set_active(album['id'] not in rules(window).get('albums',[]));changing['value']=False
                        group.set_sensitive(True)
                    update(window,values,finished)
                row.connect('notify::active',changed);group.add(row)
            if not albums:group.add(Adw.ActionRow(title='No albums available'))
        if albums:populate(albums)
        else:
            loading=Adw.ActionRow(title='Loading albums…');group.add(loading)
            def ready(albums):group.remove(loading);populate(albums)
            def failed(message):loading.set_title('Could not load albums');loading.set_subtitle(message)
            window.background(client.albums,ready,failed)
    else:
        rows=[]
        def populate():
            for row in rows:group.remove(row)
            rows.clear()
            for folder in rules(window).get('folders',[]):
                row=Adw.ActionRow(title=Path(folder).name or folder,subtitle=folder,use_markup=False)
                remove=Gtk.Button(icon_name='list-remove-symbolic',tooltip_text='Show folder in timeline',valign=Gtk.Align.CENTER)
                def show(_button,folder=folder):
                    values=deepcopy(rules(window));values['folders'].remove(folder)
                    update(window,values,lambda _:populate())
                remove.connect('clicked',show);row.add_suffix(remove);rows.append(row);group.add(row)
        populate()
        add=Adw.ActionRow(title='Hide folder…',activatable=True)
        add.add_prefix(Gtk.Image(icon_name='folder-new-symbolic'))
        def choose(_):
            chooser=Gtk.FileDialog(title='Hide folder from timeline')
            def chosen(chooser,result):
                try:folder=chooser.select_folder_finish(result).get_path()
                except Exception:return
                if not folder:return
                values=deepcopy(rules(window));folders=values.setdefault('folders',[])
                if folder not in folders:folders.append(folder)
                update(window,values,lambda _:populate())
            chooser.select_folder(window,None,chosen)
        add.connect('activated',choose);group.add(add)
    dialog.present(window)
    return dialog
