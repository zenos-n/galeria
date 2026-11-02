"""Native album navigation and utility panels; writes remain preview controls."""
import gi
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
        self.summary = text("Uploading 4 items", xalign=0, hexpand=True)
        summary.append(self.ring)
        summary.append(self.summary)
        self.set_child(summary)
        popover = Gtk.Popover(position=Gtk.PositionType.RIGHT)
        popover.add_css_class("upload-popover")
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9, margin_top=12,
                       margin_bottom=12, margin_start=12, margin_end=12, width_request=330)
        line = Gtk.Box(spacing=16)
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)
        self.title = text("Uploading 4 items", xalign=0)
        self.progress = Gtk.ProgressBar(fraction=.25)
        self.count = text("1 / 4", "caption dim-label", xalign=0)
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
        body.append(text("Progress preview · no files are being uploaded", "caption dim-label", xalign=0))
        popover.set_child(body)
        self.set_popover(popover)

    def cancel(self):
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


def import_sheet(window, files):
    dialog = Adw.Dialog(title="Add to library", content_width=460, content_height=430)
    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=18,
                   margin_bottom=24, margin_start=24, margin_end=24)
    body.append(text(f"{len(files)} items selected", "title-2"))
    group = Adw.PreferencesGroup()
    for file in files[:5]:
        is_folder = file.query_file_type(Gio.FileQueryInfoFlags.NONE, None) == Gio.FileType.DIRECTORY
        row = Adw.ActionRow(title=file.get_basename() or file.get_uri(), subtitle="Folder" if is_folder else "File")
        row.add_prefix(Gtk.Image(icon_name="folder-symbolic" if is_folder else "gallery-image-symbolic"))
        group.add(row)
    if len(files)>5:
        group.add(Adw.ActionRow(title=f"And {len(files)-5} more items"))
    body.append(group)
    body.append(text("Design preview — files and folders stay untouched.", "dim-label", wrap=True))
    add = Gtk.Button(label="Preview import", height_request=42)
    add.add_css_class("suggested-action")
    add.connect("clicked", lambda _: (dialog.close(), window.uploads.preview(len(files))))
    body.append(add)
    toolbar.set_content(Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=body))
    dialog.set_child(toolbar)
    window.dialog=dialog
    dialog.present(window)


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
    cache_row=Adw.ActionRow(title='Media cache',subtitle='Up to 512 MB · encrypted locked-folder copies are kept separately')
    clear=Gtk.Button(label='Clear cache',valign=Gtk.Align.CENTER)
    def clear_cache(_):
        from cache import MediaCache
        cache=window.client.media_cache() if window.client else MediaCache('local')
        window.background(cache.clear,lambda _:(window.texture_cache.clear(),window.notice('Media cache cleared.')))
    clear.connect('clicked',clear_cache);cache_row.add_suffix(clear);cache_group.add(cache_row)
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
