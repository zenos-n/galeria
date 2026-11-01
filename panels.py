"""UI-only panels. All media, uploads and editing use neutral preview state."""
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
        children = Gio.ListStore.new(AlbumNode)
        for i in range(3):
            node = AlbumNode(f"album-{i}", f"Album {i+1}")
            children.append(node)
            window.rows[node.key] = node
            window.page_titles[node.key] = node.name
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
        super().__init__(model=selection, factory=factory, single_click_activate=True)
        self.add_css_class("navigation-sidebar")
        self.add_css_class("album-tree")
        self.connect("activate", lambda view, position: window.navigate(view, tree.get_item(position).get_item()))

    def setup(self, _factory, item):
        expander = Gtk.TreeExpander()
        expander.set_indent_for_icon(False)
        line = Gtk.Box(spacing=8, margin_start=0, margin_end=6, height_request=34)
        item.icon = Gtk.Image(pixel_size=16)
        item.title = text("", xalign=0, hexpand=True, ellipsize=3)
        line.append(item.icon)
        line.append(item.title)
        expander.set_child(line)
        item.set_child(expander)

    def bind(self, _factory, item):
        row = item.get_item()
        node = row.get_item()
        item.get_child().set_list_row(row)
        item.icon.set_from_icon_name("folder-pictures-symbolic" if node.children else "gallery-image-symbolic")
        item.title.set_label(node.name)


def share_sheet(window,count=1):
    dialog = Adw.Dialog(title="Share photo", content_width=460, content_height=570)
    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22,
                   margin_top=16, margin_bottom=24, margin_start=24, margin_end=24)
    preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, halign=Gtk.Align.CENTER)
    image = Gtk.Image(icon_name="gallery-image-symbolic", pixel_size=44, width_request=100, height_request=75)
    image.add_css_class("share-preview")
    preview.append(image)
    preview.append(text(f"{count} {'photo' if count==1 else 'photos'} selected", "dim-label"))
    body.append(preview)
    group = Adw.PreferencesGroup(title="Share with people")
    group.add(Adw.EntryRow(title="Name or email"))
    album = Adw.ComboRow(title="Add to shared album", model=Gtk.StringList.new(["Choose an album", "Album 1", "Album 2", "Album 3"]))
    group.add(album)
    body.append(group)
    link = Adw.PreferencesGroup(title="Link options")
    link.add(Adw.SwitchRow(title="Allow downloads", active=True))
    link.add(Adw.ComboRow(title="Expires", model=Gtk.StringList.new(["Never", "In 1 day", "In 7 days", "In 30 days"])))
    body.append(link)
    message = text("", "dim-label", wrap=True, justify=Gtk.Justification.CENTER)
    create = Gtk.Button(label="Create share link", height_request=42)
    create.add_css_class("suggested-action")
    create.add_css_class("pill")
    create.connect("clicked", lambda _: message.set_label("Connect Immich to create a share link."))
    body.append(create)
    body.append(message)
    scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=body)
    toolbar.set_content(scroll)
    dialog.set_child(toolbar)
    window.dialog = dialog
    dialog.present(window)


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
    source = Adw.PreferencesGroup(title="Library")
    library = Adw.ActionRow(title="Library source", subtitle=window.source_label.get_label())
    choose = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
    choose.connect("clicked", lambda _: (dialog.close(), window.welcome()))
    library.add_suffix(choose)
    source.add(library)
    general.add(source)
    dialog.add(general)
    privacy = Adw.PreferencesPage(title="Privacy", icon_name="changes-prevent-symbolic")
    locked = Adw.PreferencesGroup(title="Locked folder", description="Locked-folder copies synced to this device must be encrypted locally.")
    sync = Adw.SwitchRow(title="Keep an encrypted copy on this device", subtitle="Local sync is not connected in this preview", active=True)
    locked.add(sync)
    encryption = Adw.ActionRow(title="On-device encryption", subtitle="Required for locked-folder files and thumbnails")
    encryption.add_suffix(text("Required", "dim-label"))
    locked.add(encryption)
    locked.add(Adw.SwitchRow(title="Lock when Gallery closes", active=True))
    timeout = Adw.ComboRow(title="Lock when inactive", model=Gtk.StringList.new(["Immediately", "After 5 minutes", "After 15 minutes"]))
    timeout.set_selected(1)
    locked.add(timeout)
    privacy.add(locked)
    dialog.add(privacy)
    window.dialog = dialog
    dialog.present(window)


def unlock_folder(window):
    dialog = Adw.Dialog(title="Unlock locked folder", content_width=420, content_height=400)
    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, margin_top=22,
                   margin_bottom=28, margin_start=28, margin_end=28)
    body.append(Gtk.Image(icon_name="changes-prevent-symbolic", pixel_size=48))
    body.append(text("Unlock your photos", "title-2"))
    group = Adw.PreferencesGroup()
    password = Adw.PasswordEntryRow(title="Passphrase")
    group.add(password)
    body.append(group)
    unlock = Gtk.Button(label="Unlock", height_request=42)
    unlock.add_css_class("suggested-action")
    unlock.add_css_class("pill")
    message = text("", "dim-label", wrap=True, justify=Gtk.Justification.CENTER)
    unlock.connect("clicked", lambda _: message.set_label("Unlocking is not connected in this design preview."))
    body.append(unlock)
    body.append(message)
    toolbar.set_content(body)
    dialog.set_child(toolbar)
    window.dialog = dialog
    dialog.present(window)
