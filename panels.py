"""Native album navigation and utility panels; writes remain preview controls."""
import gi
import time
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk


def text(value, css=None, **kwargs):
    widget = Gtk.Label(label=value, **kwargs)
    if css:
        for name in css.split():
            widget.add_css_class(name)
    return widget


def icon_button(icon, title, callback):
    widget = Gtk.Button(icon_name=icon, tooltip_text=title)
    widget.add_css_class("flat")
    widget.connect("clicked", callback)
    return widget


class Uploads(Gtk.MenuButton):
    def __init__(self, window):
        super().__init__()
        self.set_visible(False)
        self.window = window
        self.add_css_class("upload-indicator")
        self.set_direction(Gtk.ArrowType.RIGHT)
        summary = Gtk.Box(spacing=8)
        self.ring = Gtk.DrawingArea(content_width=18, content_height=18)
        self.ring.add_css_class("upload-ring")
        self.ring.set_draw_func(self.draw_ring)
        self.summary = text("Folder sync", xalign=0, hexpand=True)
        summary.append(self.ring)
        summary.append(self.summary)
        self.set_child(summary)
        popover = Gtk.Popover(position=Gtk.PositionType.RIGHT)
        popover.add_css_class("upload-popover")
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9, margin_top=12,
                       margin_bottom=12, margin_start=12, margin_end=12, width_request=330)
        line = Gtk.Box(spacing=16)
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)
        self.title = text("Folder sync", xalign=0)
        self.progress = Gtk.ProgressBar()
        self.count = text("", "caption dim-label", xalign=0)
        column.append(self.title)
        column.append(self.progress)
        column.append(self.count)
        line.append(column)
        cancel = icon_button("process-stop-symbolic", "Cancel upload", lambda _: self.cancel())
        cancel.add_css_class("circular")
        cancel.add_css_class("upload-cancel")
        cancel.set_valign(Gtk.Align.CENTER)
        line.append(cancel)
        body.append(line)
        self.note=text('', 'caption dim-label',xalign=0,wrap=True);body.append(self.note)
        popover.set_child(body)
        self.set_popover(popover)
        self.sync_requested_at=0;self.manual=False;self.request_error=None
        GLib.timeout_add_seconds(1,self.poll_sync)
        from sync_service import state_dir
        try:
            self.status_monitor=Gio.File.new_for_path(str(state_dir()/'sync-status.json')).monitor_file(Gio.FileMonitorFlags.WATCH_MOVES,None)
            self.status_monitor.connect('changed',lambda *_:self.poll_sync())
        except GLib.Error:self.status_monitor=None


    def requested(self):
        self.request_error=None
        self.sync_requested_at=time.time()

    def failed(self,message):
        client=self.window.client
        self.sync_requested_at=0;self.request_error=(client.identity,message) if client else None
        self.poll_sync();self.window.notice(message)

    def poll_sync(self):
        if getattr(self.window,'data_stopped',False):return False
        client=getattr(self.window,'client',None)
        if not client:
            if not self.manual:self.set_visible(False)
            return True
        from sync_service import read_config,read_status
        account=read_config().get('accounts',{}).get(client.identity,{})
        status=read_status();value=status.get('accounts',{}).get(client.identity,{})
        from pending_uploads import sync_previews
        sync_previews(self.window,status)
        if self.manual:return True
        pending=self.sync_requested_at and status.get('updated',0)<self.sync_requested_at
        enabled=account.get('enabled') and account.get('folders')
        request_error=self.request_error[1] if self.request_error and self.request_error[0]==client.identity else ''
        if not enabled and not pending and not request_error:
            if not self.manual:self.set_visible(False)
            return True
        folders=value.get('folders',[])+([value.get('progress',{})] if value.get('busy') else [])
        uploaded=sum(row.get('uploaded',0) for row in folders)
        errors=[str(error) for row in folders for error in row.get('errors',[])];error=request_error or value.get('error') or (errors[0] if errors else '')
        busy=status.get('active',False) and value.get('busy',False) and bool(value.get('progress',{}).get('uploading'))
        if not busy and not error and not self.manual:
            self.popdown();self.set_visible(False);return True
        self.set_visible(True)
        title='Sync needs attention' if error else 'Uploading files…' if busy else 'Folders up to date'
        self.summary.set_label(title);self.title.set_label(title)
        self.count.set_label(f'{uploaded} uploaded · '+str(sum(row.get('existing',0)+row.get('unchanged',0) for row in folders))+' already saved')
        self.note.set_label(error or value.get('current_folder','') if busy else error or 'New and changed files upload automatically. Originals are unchanged.')
        self.progress.pulse() if busy else self.progress.set_fraction(0 if error else 1)
        self.ring.set_visible(busy)
        return True

    def manual_progress(self,name,count,total):
        self.manual=True;self.set_visible(True);self.ring.set_visible(True)
        self.summary.set_label('Uploading files…');self.title.set_label(name)
        self.count.set_label(f'{count} / {total}');self.progress.set_fraction(count/max(1,total))
        self.note.set_label('Original files stay on this device.')

    def manual_finished(self):
        self.manual=False;self.popdown();self.set_visible(False);self.poll_sync()

    def cancel(self):
        if self.manual:
            if getattr(self.window,'upload_cancel',None):self.window.upload_cancel.set()
            self.manual_finished();return
        self.sync_requested_at=0;self.request_error=None
        if self.window.client and not self.manual:
            from sync_service import disable_account
            self.window.background(lambda:disable_account(self.window.client.identity),lambda _:self.poll_sync())
        self.popdown()
        self.set_visible(False)
        self.title.set_label("No uploads in progress")
        self.progress.set_fraction(0)
        self.count.set_label("0 / 0")
        self.summary.set_label("No uploads")

    def draw_ring(self, widget, context, width, height):
        color = widget.get_color()
        context.set_line_width(2)
        context.set_source_rgba(color.red, color.green, color.blue, .3)
        context.arc(width/2, height/2, 7, 0, 6.283185)
        context.stroke()
        context.set_source_rgba(color.red, color.green, color.blue, 1)
        context.arc(width/2, height/2, 7, -1.570796, 0)
        context.stroke()

    def preview(self, count=4, popup=True):
        self.manual=True
        self.set_visible(count>0)
        self.title.set_label(f"Uploading {count} items")
        self.progress.set_fraction(.25)
        self.count.set_label(f"1 / {count}")
        self.summary.set_label(f"Uploading {count} items")
        self.ring.set_visible(True)
        self.get_popover().set_position(Gtk.PositionType.RIGHT)
        if popup:
            self.popup()


class AlbumNode(GObject.Object):
    def __init__(self, key, name, children=None):
        super().__init__()
        self.key, self.name, self.children = key, name, children


class AlbumTree(Gtk.ListView):
    def __init__(self, window):
        self.window=window
        children = Gio.ListStore.new(AlbumNode)
        self.children=children
        root = AlbumNode("albums", "Albums", children)
        window.rows[root.key] = root
        window.page_titles[root.key] = root.name
        roots = Gio.ListStore.new(AlbumNode)
        roots.append(root)
        tree = Gtk.TreeListModel.new(roots, False, True, lambda node: node.children)
        selection = Gtk.SingleSelection(model=tree, autoselect=False, can_unselect=True)
        selection.set_selected(Gtk.INVALID_LIST_POSITION)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self.setup)
        factory.connect("bind", self.bind)
        factory.connect('unbind',self.unbind)
        super().__init__(model=selection, factory=factory, single_click_activate=True)
        self.add_css_class("navigation-sidebar")
        self.add_css_class("album-tree")
        self.connect("activate", lambda view, position: window.navigate(view, tree.get_item(position).get_item()))
        motion=Gtk.EventControllerMotion()
        def restore_selection(*_):
            active=next((i for i in range(tree.get_n_items()) if tree.get_item(i).get_item().key==window.current_page),Gtk.INVALID_LIST_POSITION)
            selection.set_selected(active)
        motion.connect('leave',restore_selection);self.add_controller(motion)

    def set_albums(self,albums):
        if getattr(self,'albums',None)==albums:return
        self.albums=albums
        for key in list(self.window.rows):
            if key.startswith('album-'):
                self.window.rows.pop(key,None)
                self.window.page_titles.pop(key,None)
        self.children.remove_all()
        for album in albums:
            node=AlbumNode('album-'+album['id'],album.get('albumName') or 'Untitled album')
            self.children.append(node)
            self.window.rows[node.key]=node
            self.window.page_titles[node.key]=node.name
        self.window.refresh_pins()

    def setup(self, _factory, item):
        line = Gtk.Box(spacing=10,margin_end=0,height_request=34)
        item.icon = Gtk.Image(pixel_size=16)
        item.title = text("", xalign=0, hexpand=True, ellipsize=3)
        line.append(item.icon)
        line.append(item.title)
        item.arrow=Gtk.Button(icon_name='pan-down-symbolic',tooltip_text='Expand or collapse albums',css_classes=['flat','album-disclosure'],valign=Gtk.Align.CENTER)
        item.arrow.connect('clicked',lambda _:item.tree_row.set_expanded(not item.tree_row.get_expanded()))
        line.append(item.arrow)
        item.set_child(line)
        from collection_widgets import album_context
        album_context(self.window,line,lambda:next((album for album in getattr(self,'albums',[]) if item.get_item() and 'album-'+album['id']==item.get_item().get_item().key),None))

    def bind(self, _factory, item):
        row = item.get_item()
        node = row.get_item()
        item.tree_row=row
        item.get_child().set_margin_start(0 if node.key=='albums' else 18)
        item.arrow.set_visible(node.key=='albums')
        def update(*_):item.arrow.set_icon_name('pan-down-symbolic' if row.get_expanded() else 'pan-end-symbolic')
        item.tree_handler=row.connect('notify::expanded',update);update()
        item.icon.set_from_icon_name("folder-pictures-symbolic" if node.key=='albums' else "gallery-image-symbolic")
        item.title.set_label(node.name)

    def unbind(self,_factory,item):
        if getattr(item,'tree_handler',None):
            item.tree_row.disconnect(item.tree_handler);item.tree_handler=None


def share_sheet(window,count=1):
    from sharing_ui import share_media
    share_media(window)


def import_sheet(window,files):
    from import_ui import import_sheet as show
    show(window,files)


def preferences(window):
    dialog = Adw.PreferencesDialog(title="Preferences", content_width=620, content_height=650)
    general = Adw.PreferencesPage(title="General", icon_name="preferences-system-symbolic")
    appearance = Adw.PreferencesGroup(title="Appearance")
    theme = Adw.ComboRow(title="Color scheme", model=Gtk.StringList.new(["System", "Light", "Dark"]))
    manager = Adw.StyleManager.get_default()
    theme.set_selected({Adw.ColorScheme.DEFAULT: 0, Adw.ColorScheme.FORCE_LIGHT: 1,
                        Adw.ColorScheme.FORCE_DARK: 2}.get(manager.get_color_scheme(), 0))
    theme.connect("notify::selected", lambda w, _: manager.set_color_scheme(
        [Adw.ColorScheme.DEFAULT, Adw.ColorScheme.FORCE_LIGHT, Adw.ColorScheme.FORCE_DARK][w.get_selected()]))
    appearance.add(theme)
    density = Adw.ComboRow(title="Grid density", model=Gtk.StringList.new(["Compact", "Comfortable", "Large"]))
    density.set_selected({112: 0, 154: 1, 210: 2}[window.mosaic.target])
    density.connect("notify::selected", lambda w, _: window.set_density([112, 154, 210][w.get_selected()]))
    appearance.add(density)
    durations = Adw.SwitchRow(title="Show video duration", active=window.mosaic.show_durations)
    durations.connect("notify::active", lambda w, _: window.set_durations(w.get_active()))
    appearance.add(durations)
    general.add(appearance)
    app=window.get_application()
    if hasattr(app,'login_startup'):
        startup=Adw.PreferencesGroup(title='Startup')
        login=Adw.SwitchRow(title='Start at login',subtitle='Start in the background when you sign in',active=app.login_startup.enabled(),sensitive=not app.login_startup.managed())
        if app.login_startup.managed():login.set_subtitle('Controlled by your ZenOS configuration')
        changing={'value':False}
        def startup_changed(row,_param):
            if changing['value']:return
            enabled=row.get_active();row.set_sensitive(False)
            def done(_):row.set_sensitive(True)
            def failed(message):
                changing['value']=True;row.set_active(not enabled);changing['value']=False
                row.set_sensitive(True);window.notice(message)
            window.background(lambda:app.login_startup.set_enabled(enabled),done,failed)
        login.connect('notify::active',startup_changed);startup.add(login)
        background=Adw.SwitchRow(title='Keep running in the background',subtitle='Keep Galeria available from Quick Settings after closing its window',active=app.background_enabled)
        app.bind_property('background-enabled',background,'active',GObject.BindingFlags.SYNC_CREATE)
        background.connect('notify::active',lambda row,_:app.set_background(row.get_active(),persist=True))
        startup.add(background);general.add(startup)
    source = Adw.PreferencesGroup(title="Library")
    library = Adw.ActionRow(title="Library source", subtitle=window.source_label.get_label())
    choose = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
    choose.connect("clicked", lambda _: (dialog.close(), window.welcome()))
    library.add_suffix(choose)
    source.add(library)
    general.add(source)
    cache_group=Adw.PreferencesGroup(title='Storage')
    cache_row=Adw.ActionRow(title='Media cache',subtitle='512 MB for images · 128 MB for video preloads · encrypted copies kept separately')
    clear=Gtk.Button(label='Clear cache',valign=Gtk.Align.CENTER)
    def clear_cache(_):
        from cache import MediaCache
        client=window.client;cache=client.media_cache() if client else MediaCache('local')
        def clear():
            if client:client.video_cache().clear()
            cache.clear()
        window.background(clear,lambda _:(window.texture_cache.clear(),window.notice('Media cache cleared.')))
    clear.connect('clicked',clear_cache);cache_row.add_suffix(clear);cache_group.add(cache_row)
    archive_local=Adw.SwitchRow(title='Remove synced local files when archiving',subtitle='Move unchanged Folder sync originals to this device’s Trash after archiving in Immich',active=window.preferences.get('archive_delete_local',False))
    archive_local.connect('notify::active',lambda row,_:(window.preferences.update(archive_delete_local=row.get_active()),window.save_preferences()))
    cache_group.add(archive_local)
    general.add(cache_group)
    dialog.add(general)
    privacy = Adw.PreferencesPage(title="Privacy", icon_name="changes-prevent-symbolic")
    locked = Adw.PreferencesGroup(title="Locked folder", description="Locked-folder copies synced to this device must be encrypted locally.")
    sync = Adw.SwitchRow(title="Keep an encrypted copy on this device", subtitle="Requires the system keyring; sync starts when the folder is unlocked", active=window.preferences.get('vault_sync',True))
    sync.connect('notify::active',lambda row,_:(window.preferences.update(vault_sync=row.get_active()),window.save_preferences()))
    locked.add(sync)
    encryption = Adw.ActionRow(title="On-device encryption", subtitle="Required for locked-folder files and thumbnails")
    encryption.add_suffix(text("Required", "dim-label"))
    locked.add(encryption)
    locked.add(Adw.SwitchRow(title="Lock when Galeria closes", active=True))
    timeout = Adw.ComboRow(title="Lock when inactive", model=Gtk.StringList.new(["Immediately", "After 5 minutes", "After 15 minutes"]))
    timeout.set_selected(1)
    locked.add(timeout)
    privacy.add(locked)
    dialog.add(privacy)
    window.dialog = dialog
    dialog.present(window)
