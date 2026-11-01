#!/usr/bin/env python3
"""Native, data-free design prototype for Gallery."""
from pathlib import Path
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gsk, Gtk

from layout import justified_rows
from panels import AlbumTree, Uploads, import_sheet, preferences, unlock_folder
from viewer import Viewer


def button(icon, tooltip, callback):
    widget = Gtk.Button(icon_name=icon, tooltip_text=tooltip)
    widget.add_css_class("flat")
    widget.connect("clicked", callback)
    return widget


def label(text, css=None, **kwargs):
    widget = Gtk.Label(label=text, **kwargs)
    if css:
        widget.add_css_class(css)
    return widget


# The blocks show layout only; no local files or network requests are involved.
RATIOS = [1.2, 1.78, 1, .72, .56, 1.6, .48, .55, 1.35, .8, 1.7, .6,
          1, 1.8, .65, .5, 1.3, 1.5, .8, 1.65, .6, 1, .7, 1.6, .6, 1.8]


class Mosaic(Gtk.Widget):
    """Height-for-width layout with native, keyboard-focusable photo buttons."""
    __gtype_name__ = "GalleryMosaic"

    def __init__(self, open_photo):
        super().__init__()
        self.open_photo = open_photo
        self.groups = []
        self.widgets = []
        self.target = 154
        self.mode = "all"
        self.show_durations = True
        self.tiles = []
        self.set_hexpand(True)
        self.set_margin_start(10)
        self.set_margin_end(10)
        self.rebuild()

    def clear(self):
        for widget in self.widgets:
            widget.unparent()
        self.widgets.clear()
        self.groups.clear()
        self.tiles.clear()

    def rebuild(self):
        self.clear()
        if self.mode == "years":
            sections = [("2026", RATIOS[:6]), ("2025", RATIOS[6:12]), ("2024", RATIOS[12:18])]
        elif self.mode == "months":
            sections = [("January 2026", RATIOS[:7]), ("December 2025", RATIOS[7:14]), ("November 2025", RATIOS[14:21])]
        else:
            sections = [("Today", RATIOS[:12]), ("Yesterday", RATIOS[12:]), ("Sunday, 25 January", RATIOS[4:18])]
        index = 0
        for title, ratios in sections:
            heading = label(title, "day-heading", xalign=0)
            heading.set_parent(self)
            self.widgets.append(heading)
            tiles = []
            for ratio in ratios:
                overlay = Gtk.Overlay()
                placeholder = Gtk.Box(halign=Gtk.Align.FILL, valign=Gtk.Align.FILL)
                placeholder.add_css_class("placeholder")
                placeholder.add_css_class(f"shade-{index % 5}")
                overlay.set_child(placeholder)
                symbol = Gtk.Image.new_from_icon_name("image-x-generic-symbolic")
                symbol.set_pixel_size(23)
                symbol.set_halign(Gtk.Align.CENTER)
                symbol.set_valign(Gtk.Align.CENTER)
                symbol.add_css_class("placeholder-icon")
                overlay.add_overlay(symbol)
                if self.show_durations and index in (1, 4, 9, 17, 23):
                    duration = label("▷ 0:31", "video-duration", halign=Gtk.Align.END, valign=Gtk.Align.START)
                    overlay.add_overlay(duration)
                tile = Gtk.Button(child=overlay, tooltip_text="Open photo preview")
                tile.photo_ratio = ratio
                tile.add_css_class("photo-tile")
                tile.connect("clicked", self.clicked, index)
                tile.set_parent(self)
                tiles.append(tile)
                self.widgets.append(tile)
                self.tiles.append(tile)
                index += 1
            self.groups.append((heading, ratios, tiles))
        self.queue_resize()

    def clicked(self, _button, index):
        self.open_photo(index, _button)

    def positions(self, width):
        result, y = [], 0
        target = {"all": self.target, "months": 210, "years": 280}[self.mode]
        for heading, ratios, tiles in self.groups:
            result.append((heading, 2, y + 8, max(1, width - 4), 28))
            y += 40
            positions = justified_rows(ratios, width, target=target)
            for index, x, dy, w, h in positions:
                result.append((tiles[index], x, y + dy, w, h))
            y += max((dy + h for _, _, dy, _, h in positions), default=0) + 12
        return result, y

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return 200, 900, -1, -1
        _, height = self.positions(max(200, for_size))
        return height, height, -1, -1

    def do_size_allocate(self, width, height, baseline):
        for widget, x, y, w, h in self.positions(width)[0]:
            widget.measure(Gtk.Orientation.HORIZONTAL, -1)
            widget.measure(Gtk.Orientation.VERTICAL, w)
            point = Graphene.Point()
            point.init(x, y)
            transform = Gsk.Transform.new().translate(point)
            widget.allocate(w, h, -1, transform)

    def do_snapshot(self, snapshot):
        for widget in self.widgets:
            self.snapshot_child(widget, snapshot)

    def do_dispose(self):
        self.clear()


class GalleryWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Gallery", default_width=1280, default_height=820)
        Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(Path(__file__).parent / "icons"))
        self.current_page = "library"
        self.viewer_index = 0
        self.viewer = None
        self.toast = Adw.ToastOverlay()
        self.set_content(self.toast)
        self.split = Adw.OverlaySplitView(min_sidebar_width=220, max_sidebar_width=220)
        self.split.set_sidebar_width_unit(Adw.LengthUnit.PX)
        self.root_overlay = Gtk.Overlay(child=self.split)
        self.toast.set_child(self.root_overlay)
        self.make_sidebar()
        self.make_content()
        breakpoint = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 720sp"))
        breakpoint.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(breakpoint)
        self.split.connect("notify::collapsed", self.collapsed)
        self.dialog = None
        self.make_drop_target()

    def notice(self, text):
        self.toast.add_toast(Adw.Toast.new(text))

    def make_drop_target(self):
        self.drop_hint = Adw.StatusPage(icon_name="gallery-upload-symbolic", title="Drop to add media",
                                       description="Files and folders", visible=False)
        self.drop_hint.add_css_class("drop-hint")
        self.drop_hint.set_can_target(False)
        self.root_overlay.add_overlay(self.drop_hint)
        self.drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        self.drop_target.connect("accept", lambda *_: self.viewer is None)
        self.drop_target.connect("enter", self.drop_enter)
        self.drop_target.connect("leave", lambda *_: self.drop_hint.set_visible(False))
        self.drop_target.connect("drop", self.drop_files)
        self.root_overlay.add_controller(self.drop_target)

    def drop_enter(self, *_):
        self.drop_hint.set_visible(True)
        return Gdk.DragAction.COPY

    def drop_files(self, _target, value, *_):
        self.drop_hint.set_visible(False)
        files = value.get_files()
        if not files:
            return False
        import_sheet(self, files)
        return True

    def reveal_tile(self, tile):
        ok, bounds = tile.compute_bounds(self.mosaic)
        if not ok:
            return
        adjustment = self.scroller.get_vadjustment()
        top, bottom = bounds.get_y(), bounds.get_y()+bounds.get_height()
        value, page = adjustment.get_value(), adjustment.get_page_size()
        if top < value:
            adjustment.set_value(top)
        elif bottom > value+page:
            adjustment.set_value(bottom-page)

    def make_sidebar(self):
        toolbar = Adw.ToolbarView()
        toolbar.add_css_class("gallery-sidebar")
        self.split.set_sidebar(toolbar)
        header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
        header.set_title_widget(label("Gallery", "heading"))
        header.pack_start(button("system-search-symbolic", "Search", lambda _: self.search.set_search_mode(True)))
        menu = Gio.Menu()
        menu.append("Choose library…", "win.source")
        menu.append("Preferences", "win.preferences")
        menu.append("About Gallery", "win.about")
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        menu_button.add_css_class("flat")
        header.pack_end(menu_button)
        toolbar.add_top_bar(header)
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_scroll.set_child(body)
        sidebar.append(sidebar_scroll)
        toolbar.set_content(sidebar)
        self.rows = {}
        self.lists = []
        self.page_titles = {}
        for heading, items in [
            (None, [("library", "Library", "folder-pictures-symbolic"), ("favorites", "Favorites", "starred-symbolic"),
                    ("map", "Map", "find-location-symbolic"), ("sharing", "Sharing", "emblem-shared-symbolic")]),
            ("Pinned", [("pinned", "Pin an album…", "view-pin-symbolic")]),
            ("Collections", []),
            ("Media types", [("photos", "Photos", "image-x-generic-symbolic"), ("videos", "Videos", "video-x-generic-symbolic"),
                              ("screenshots", "Screenshots", "camera-photo-symbolic"), ("live", "Live Photos", "media-playback-start-symbolic")]),
            ("Utilities", [("duplicates", "Review duplicates", "edit-copy-symbolic"),
                           ("people", "People", "gallery-people-symbolic"), ("tags", "Tags", "gallery-tag-symbolic"),
                           ("trash", "Trash", "user-trash-symbolic")]),
            ("More", [("archive", "Archive", "folder-symbolic"), ("locked", "Locked folder", "changes-prevent-symbolic")]),
        ]:
            if heading:
                body.append(label(heading, "sidebar-section", xalign=0))
            nav = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
            nav.add_css_class("navigation-sidebar")
            nav.set_activate_on_single_click(True)
            for key, title, icon in items:
                row = Gtk.ListBoxRow()
                row.key = key
                self.page_titles[key] = title
                line = Gtk.Box(spacing=10, margin_start=10, margin_end=8)
                line.append(Gtk.Image(icon_name=icon, pixel_size=16))
                line.append(label(title, xalign=0, hexpand=True))
                row.set_child(line)
                nav.append(row)
                self.rows[key] = row
            nav.connect("row-activated", self.navigate)
            body.append(nav)
            self.lists.append(nav)
            if heading == "Collections":
                self.album_tree = AlbumTree(self)
                body.append(self.album_tree)
        self.uploads = Uploads(self)
        sidebar.append(self.uploads)
        self.source_label = label("No library connected", "source-label", xalign=0)
        sidebar.append(self.source_label)
        self.rows["library"].get_parent().select_row(self.rows["library"])
        for name, callback in [("source", self.welcome), ("density", self.density),
                               ("appearance", self.appearance), ("about", self.about),
                               ("preferences", lambda: preferences(self))]:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, cb=callback: cb())
            self.add_action(action)

    def make_content(self):
        self.toolbar = Adw.ToolbarView()
        self.split.set_content(self.toolbar)
        header = Adw.HeaderBar()
        self.header = header
        self.sidebar_button = button("sidebar-show-symbolic", "Show sidebar", lambda _: self.split.set_show_sidebar(True))
        self.sidebar_button.set_visible(False)
        header.pack_start(self.sidebar_button)
        self.period = label("January 2026", "timeline-date", margin_start=14)
        header.pack_start(self.period)
        self.switcher = Adw.ToggleGroup()
        self.switcher.add_css_class("round")
        for name, title in [("years", "Years"), ("months", "Months"), ("all", "All Photos")]:
            self.switcher.add(Adw.Toggle(name=name, label=title))
        self.switcher.set_active_name("all")
        self.switcher.connect("notify::active-name", self.change_mode)
        header.set_title_widget(self.switcher)
        self.page_title = label("", "heading")
        avatar = Adw.Avatar(size=28, text="Gallery", show_initials=False)
        account = Gtk.Button(child=avatar, tooltip_text="Account and library", width_request=34, height_request=34, valign=Gtk.Align.CENTER)
        account.add_css_class("flat")
        account.add_css_class("avatar-button")
        account.add_css_class("circular")
        account.connect("clicked", lambda _: self.welcome())
        self.account_button = account
        header.pack_end(Gtk.AspectFrame(child=account,ratio=1,obey_child=False,
                                       halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER))
        header.pack_end(button("gallery-upload-arrow-symbolic", "Upload files", lambda _: self.choose_uploads()))
        self.toolbar.add_top_bar(header)
        self.search = Gtk.SearchBar()
        entry = Gtk.SearchEntry(placeholder_text="Search your photos", hexpand=True)
        self.search.set_child(entry)
        self.search.connect_entry(entry)
        entry.connect("search-changed", lambda _: self.notice("Search will be available when a library is connected.") if entry.get_text() else None)
        self.search.set_key_capture_widget(self)
        self.toolbar.add_top_bar(self.search)
        self.stack = Gtk.Stack()
        self.toolbar.set_content(self.stack)
        self.scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        self.scroller.add_css_class("timeline")
        self.mosaic = Mosaic(self.open_viewer)
        self.scroller.set_child(self.mosaic)
        self.stack.add_named(self.scroller, "library")
        self.status = Adw.StatusPage()
        self.status_actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER)
        self.unlock_button = Gtk.Button(label="Unlock folder")
        self.unlock_button.add_css_class("suggested-action")
        self.unlock_button.add_css_class("pill")
        self.unlock_button.connect("clicked", lambda _: unlock_folder(self))
        self.status_actions.append(self.unlock_button)
        self.encryption_note = label("Synced copies on this device must be encrypted.", "dim-label", wrap=True)
        self.status_actions.append(self.encryption_note)
        self.status.set_child(self.status_actions)
        self.stack.add_named(self.status, "status")
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.key_pressed)
        self.add_controller(keys)

    def key_pressed(self, _controller, keyval, _keycode, state):
        if self.viewer:
            return self.viewer.on_key(_controller, keyval, _keycode, state)
        if keyval == Gdk.KEY_f and state & Gdk.ModifierType.CONTROL_MASK:
            self.search.set_search_mode(True)
            return True
        return False

    def collapsed(self, *_):
        self.sidebar_button.set_visible(self.split.get_collapsed())

    def navigate(self, nav, row):
        self.current_page = row.key
        if nav != self.album_tree:
            self.album_tree.get_model().unselect_all()
        for other in self.lists:
            if other != nav:
                other.unselect_all()
        if self.split.get_collapsed():
            self.split.set_show_sidebar(False)
        is_library = row.key == "library"
        has_grid = is_library or row.key in ("photos", "videos", "screenshots", "live") or row.key.startswith("album-")
        self.switcher.set_visible(is_library)
        self.period.set_visible(is_library)
        self.page_title.set_label(self.page_titles[row.key])
        self.header.set_title_widget(self.switcher if is_library else self.page_title)
        self.stack.set_visible_child_name("library" if has_grid else "status")
        self.status_actions.set_visible(row.key == "locked")
        if not has_grid:
            titles = {
                "favorites": ("starred-symbolic", "Your favorites", "The photos you love will live here."),
                "map": ("find-location-symbolic", "Your places", "A map of the places in your library."),
                "sharing": ("emblem-shared-symbolic", "Shared with you", "Your shared albums, together in one place."),
                "pinned": ("view-pin-symbolic", "Keep an album close", "Pin albums here for quick access."),
                "albums": ("folder-pictures-symbolic", "Your albums", "A home for your collections."),
                "duplicates": ("edit-copy-symbolic", "Review duplicates", "Compare similar photos side by side."),
                "archive": ("folder-symbolic", "Your archive", "Photos kept out of the main library."),
                "locked": ("changes-prevent-symbolic", "Locked folder", "A private space for your photos."),
                "people": ("gallery-people-symbolic", "People", "The faces in your library."),
                "tags": ("gallery-tag-symbolic", "Tags", "Organize photos with tags."),
                "trash": ("user-trash-symbolic", "Trash", "Deleted items will appear here before removal."),
            }
            icon, title, description = titles[row.key]
            self.status.set_icon_name(icon)
            self.status.set_title(title)
            self.status.set_description(description)

    def change_mode(self, *_):
        if not hasattr(self, "mosaic"):
            return
        self.mosaic.mode = self.switcher.get_active_name()
        self.mosaic.rebuild()
        self.scroller.get_vadjustment().set_value(0)
        self.period.set_label({"all": "January 2026", "months": "2026", "years": "Library"}[self.mosaic.mode])

    def density(self):
        self.set_density({154: 210, 210: 112, 112: 154}[self.mosaic.target])

    def set_density(self, value):
        self.mosaic.target = value
        self.mosaic.queue_resize()

    def set_durations(self, value):
        self.mosaic.show_durations = value
        self.mosaic.rebuild()

    def appearance(self):
        manager = Adw.StyleManager.get_default()
        manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT if manager.get_dark() else Adw.ColorScheme.FORCE_DARK)

    def about(self):
        dialog = Adw.AboutDialog(application_name="Gallery", application_icon="folder-pictures-symbolic",
                                 version="0.1 · Design preview", developer_name="Gallery",
                                 comments="A native libadwaita gallery. This preview uses layout placeholders only.")
        dialog.present(self)

    def welcome(self):
        dialog = Adw.AlertDialog(heading="Do you want to use Immich?",
                                body="Connect to your Immich library, or choose folders on this device.")
        self.welcome_illustration = Gtk.Picture(can_shrink=True,content_fit=Gtk.ContentFit.CONTAIN,
                                               height_request=140)
        self.welcome_illustration.add_css_class('illustration-slot')
        dialog.set_extra_child(self.welcome_illustration)
        dialog.add_response("local", "No, choose folders")
        dialog.add_response("immich", "Yes, use Immich")
        dialog.set_response_appearance("immich", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("immich")
        dialog.set_close_response("cancel")
        dialog.connect("response", self.welcome_response)
        self.dialog = dialog
        dialog.present(self)
        return GLib.SOURCE_REMOVE

    def welcome_response(self, _dialog, response):
        if response == "immich":
            self.login()
        elif response == "local":
            self.choose_folders()

    def choose_folders(self):
        dialog = Gtk.FileDialog(title="Choose photo folders", accept_label="Choose folders")
        dialog.select_multiple_folders(self, None, self.folders_selected)

    def choose_uploads(self):
        dialog = Gtk.FileDialog(title="Add files", accept_label="Add files")
        dialog.open_multiple(self, None, self.uploads_selected)

    def uploads_selected(self, dialog, result):
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            return
        import_sheet(self, [files.get_item(i) for i in range(files.get_n_items())])

    def folders_selected(self, dialog, result):
        try:
            folders = dialog.select_multiple_folders_finish(result)
        except GLib.Error:
            return
        names = [folders.get_item(i).get_basename() for i in range(folders.get_n_items())]
        if names:
            self.source_label.set_label(names[0] if len(names) == 1 else f"{len(names)} folders")
            self.notice("Folders selected. This preview does not load photos yet.")

    def login(self):
        dialog = Adw.Dialog(title="Sign in to Immich", content_width=440, content_height=490)
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        body.add_css_class("login-body")
        body.append(Gtk.Image(icon_name="folder-pictures-symbolic", pixel_size=52, margin_top=8, margin_bottom=4))
        body.append(label("Your Immich library", "title-2"))
        group = Adw.PreferencesGroup()
        self.server_entry = Adw.EntryRow(title="Server address")
        self.server_entry.set_input_purpose(Gtk.InputPurpose.URL)
        self.email_entry = Adw.EntryRow(title="Email")
        self.email_entry.set_input_purpose(Gtk.InputPurpose.EMAIL)
        self.password_entry = Adw.PasswordEntryRow(title="Password")
        for row in (self.server_entry, self.email_entry, self.password_entry):
            group.add(row)
        body.append(group)
        sign_in = Gtk.Button(label="Sign in", height_request=44)
        sign_in.add_css_class("suggested-action")
        sign_in.add_css_class("pill")
        message = label("", "dim-label", wrap=True, justify=Gtk.Justification.CENTER)
        sign_in.connect("clicked", lambda _: message.set_label("Sign-in is not connected in this design preview."))
        body.append(sign_in)
        body.append(message)
        toolbar.set_content(body)
        dialog.set_child(toolbar)
        self.dialog = dialog
        dialog.present(self)

    def open_viewer(self, index, source=None):
        if self.viewer:
            return
        source = source or self.mosaic.tiles[index % len(self.mosaic.tiles)]
        self.viewer = Viewer(self, index, source)
        self.viewer.show()


class Gallery(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.gallery.DesignPreview", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        if self.get_active_window():
            self.get_active_window().present()
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(Path(__file__).with_name("style.css")))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.window = GalleryWindow(self)
        self.window.present()
        GLib.idle_add(self.window.welcome)


if __name__ == "__main__":
    raise SystemExit(Gallery().run(sys.argv))
