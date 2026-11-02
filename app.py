#!/usr/bin/env python3
"""Native GTK gallery for local folders and Immich."""
from pathlib import Path
import sys
import time

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, Gio, GLib, Graphene, Gsk, Gtk

from layout import justified_rows
from panels import AlbumTree, Uploads, import_sheet, preferences, share_sheet
from viewer import Viewer
from timeline import Mosaic
from search_ui import SearchPanel
from data_ui import LibraryUI
from admin import administration
from library import ImmichClient, LibraryError
from collections_ui import collection_view
from vault_ui import unlock_folder


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


class GalleryWindow(LibraryUI,Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Galeria", default_width=1280, default_height=820)
        Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(Path(__file__).parent / "icons"))
        self.current_page = "library"
        self.viewer_index = 0
        self.viewer = None
        self.library_mode='immich'
        self.searching=False
        self.grid_page=True
        self.init_data()
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
        self.update_account_ui()

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
        header.set_title_widget(label("Galeria", "heading"))
        self.search_toggle=Gtk.ToggleButton(icon_name='system-search-symbolic',tooltip_text='Search',css_classes=['flat'])
        self.search_toggle.connect('toggled',lambda widget:self.set_searching(widget.get_active()))
        header.pack_start(self.search_toggle)
        menu = Gio.Menu()
        self.hamburger_menu=menu
        menu.append("Choose library…", "win.source")
        menu.append("Refresh library", "win.refresh")
        menu.append('Folder sync','win.sync')
        menu.append("Preferences", "win.preferences")
        menu.append("About Galeria", "win.about")
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
                line = Gtk.Box(spacing=10, margin_start=0, margin_end=0)
                line.append(Gtk.Image(icon_name=icon, pixel_size=16))
                line.append(label(title, xalign=0, hexpand=True))
                row.set_child(line)
                nav.append(row)
                self.rows[key] = row
            nav.connect("row-activated", self.navigate)
            body.append(nav)
            self.lists.append(nav)
            if heading=='Pinned':
                self.pin_nav=nav
                self.pin_rows=[]
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
                               ("admin",lambda:administration(self)),("refresh",self.refresh_library),
                               ('sync',self.show_folder_sync),
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
        avatar = Adw.Avatar(size=28, text="Galeria", show_initials=False)
        account = Gtk.MenuButton(child=avatar, tooltip_text="Account and library", width_request=34, height_request=34, valign=Gtk.Align.CENTER)
        self.avatar=avatar
        account.add_css_class("flat")
        account.add_css_class("avatar-button")
        account.add_css_class("circular")
        account.set_create_popup_func(lambda _:self.account_menu())
        self.account_button = account
        self.account_wrapper=Gtk.AspectFrame(child=account,ratio=1,obey_child=False,halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER)
        header.pack_end(self.account_wrapper)
        self.upload_button=button("cloud-deploy-symbolic", "Upload files", lambda _: self.choose_uploads())
        header.pack_end(self.upload_button)
        self.album_share_button=button('gallery-share-symbolic','Share album',lambda _:self.share_current_album())
        self.album_share_button.set_visible(False);header.pack_end(self.album_share_button)
        self.select_button=Gtk.ToggleButton(icon_name='object-select-symbolic',tooltip_text='Select items')
        self.select_button.add_css_class('flat')
        self.select_button.connect('toggled',lambda w:self.mosaic.set_selection(w.get_active()))
        header.pack_end(self.select_button)
        self.lock_button=button('changes-prevent-symbolic','Lock folder',lambda _:self.lock_folder())
        self.lock_button.set_visible(False)
        header.pack_end(self.lock_button)
        self.toolbar.add_top_bar(header)
        self.search = SearchPanel(self)
        self.search.set_key_capture_widget(self)
        self.stack = Gtk.Stack()
        self.toolbar.set_content(self.stack)
        self.scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        adjustment=self.scroller.get_vadjustment()
        adjustment.connect('value-changed',self.scroll_changed)
        adjustment.connect('changed',self.load_visible_thumbnails)
        self.scroller.add_css_class("timeline")
        self.mosaic = Mosaic(self.open_viewer,[])
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
        self.status.set_icon_name('folder-pictures-symbolic')
        self.status.set_title('Choose your library')
        self.status.set_description('Connect Immich or open folders on this device.')
        self.status_actions.set_visible(False)
        self.stack.set_visible_child_name('status')
        self.load_more=Gtk.Button(label='Load more',halign=Gtk.Align.CENTER,visible=False,
                                  margin_top=6,margin_bottom=6)
        self.load_more.connect('clicked',lambda _:self.search_library(append=True))
        self.toolbar.add_bottom_bar(self.load_more)
        self.selection_title=label('Select items','heading')
        self.selection_bar=Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_UP)
        actionbar=Gtk.ActionBar()
        select_all=Gtk.Button(label='Select all')
        select_all.connect('clicked',lambda _:self.mosaic.select_all())
        actionbar.pack_start(select_all)
        cancel=Gtk.Button(label='Cancel')
        cancel.connect('clicked',lambda _:self.mosaic.set_selection(False))
        actionbar.pack_start(cancel)
        for icon,title,callback in [
            ('gallery-share-symbolic','Share selected',lambda _:share_sheet(self,len(self.mosaic.selected))),
            ('list-add-symbolic','Add to album',lambda _:self.add_selected_to_album()),
            ('starred-symbolic','Favorite selected',lambda _:self.selected_action('favorite')),
            ('user-trash-symbolic','Trash or restore selected',lambda _:self.selected_action('trash')),
        ]:
            actionbar.pack_end(button(icon,title,callback))
        self.selection_bar.set_child(actionbar)
        self.toolbar.add_bottom_bar(self.selection_bar)
        self.mosaic.on_selection=self.selection_changed
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.key_pressed)
        self.add_controller(keys)

    def key_pressed(self, _controller, keyval, _keycode, state):
        if self.viewer:
            return self.viewer.on_key(_controller, keyval, _keycode, state)
        if keyval==Gdk.KEY_Escape and self.searching:
            self.set_searching(False);return True
        if keyval == Gdk.KEY_f and state & Gdk.ModifierType.CONTROL_MASK:
            self.search.set_search_mode(True)
            return True
        if keyval == Gdk.KEY_a and state & Gdk.ModifierType.CONTROL_MASK and not isinstance(self.get_focus(),Gtk.Editable):
            self.mosaic.select_all()
            return True
        if keyval == Gdk.KEY_Escape and self.mosaic.selection_mode:
            self.mosaic.set_selection(False)
            return True
        return False

    def selection_changed(self):
        active=self.mosaic.selection_mode
        self.select_button.set_active(active)
        self.selection_bar.set_reveal_child(active)
        self.selection_title.set_label(f'{len(self.mosaic.selected)} selected' if self.mosaic.selected else 'Select items')
        self.update_header()

    def update_header(self):
        active=self.mosaic.selection_mode
        is_library=self.current_page=='library'
        self.period.set_visible(not self.searching and not active and is_library)
        self.switcher.set_visible(not self.searching and not active and is_library)
        self.account_wrapper.set_visible(not self.searching)
        self.upload_button.set_visible(not self.searching)
        self.album_share_button.set_visible(not self.searching and bool(self.client) and self.current_page.startswith('album-'))
        self.select_button.set_visible(not self.searching and self.grid_page)
        self.lock_button.set_visible(not self.searching and bool(self.client and self.client.locked_until>time.monotonic()))
        self.sidebar_button.set_visible(not self.searching and self.split.get_collapsed())
        self.header.set_title_widget(self.search if self.searching else self.selection_title if active else self.switcher if is_library else self.page_title)

    def set_searching(self,active):
        self.searching=active
        self.search_toggle.set_active(active)
        if not hasattr(self,'search'):return
        self.update_header()
        if active:GLib.idle_add(self.search.entry.grab_focus)
        else:
            self.search.popover.popdown()
            self.search.entry.set_text('')
            self.search.clear()

    def update_account_ui(self):
        admin=bool(self.client and self.client.user.get('isAdmin'))
        self.lookup_action('admin').set_enabled(admin)
        self.hamburger_menu.remove_all()
        for title,action in [('Choose library…','source'),('Refresh library','refresh'),('Folder sync','sync')]+([('Administration','admin')] if admin else [])+[('Preferences','preferences'),('About Galeria','about')]:
            self.hamburger_menu.append(title,'win.'+action)
        self.avatar.set_text(self.client.user.get('name','') if self.client else 'Galeria')
        self.avatar.set_show_initials(bool(self.client))

    def account_menu(self):
        popover=Gtk.Popover()
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6,margin_top=12,margin_bottom=12,margin_start=12,margin_end=12,width_request=220)
        if self.client:
            box.append(label(self.client.user.get('name','Account'),'heading',xalign=0))
            box.append(label(self.client.user.get('email',''),'dim-label',xalign=0,ellipsize=3))
        for title,callback in ([('Folder sync',self.show_folder_sync),('Preferences',lambda:preferences(self)),('Switch library…',self.welcome),('Sign out',self.sign_out)] if self.client else [('Choose library…',self.welcome),('Preferences',lambda:preferences(self))]):
            item=Gtk.Button(label=title,css_classes=['flat'],halign=Gtk.Align.FILL)
            item.connect('clicked',lambda _,callback=callback:(self.account_button.popdown(),callback()))
            box.append(item)
        popover.set_child(box);self.account_button.set_popover(popover)

    def show_folder_sync(self):
        from sync_ui import folder_sync
        folder_sync(self)

    def share_current_album(self):
        from sharing_ui import share_album
        album_id=self.current_page.removeprefix('album-')
        album=next((album for album in getattr(self.album_tree,'albums',[]) if album['id']==album_id),None)
        if album:share_album(self,album)

    def collapsed(self, *_):
        self.update_header()

    def navigate(self, nav, row):
        if self.current_page=='locked' and row.key!='locked':self.lock_folder(refresh=False)
        self.search_generation+=1
        self.load_more.set_visible(False)
        self.mosaic.set_selection(False)
        self.current_page = row.key
        self.scope_filters={}
        self.collection_items=None
        if nav != self.album_tree:
            self.album_tree.get_model().unselect_all()
        for other in self.lists:
            if other != nav:
                other.unselect_all()
        if self.split.get_collapsed():
            self.split.set_show_sidebar(False)
        is_library = row.key == "library"
        has_grid = is_library or row.key in ("photos", "videos", "screenshots", "live") or row.key.startswith("album-") or bool(self.client) and row.key in ('favorites','archive','trash') or row.key=='locked' and bool(self.client and self.client.locked_until>time.monotonic())
        self.select_button.set_visible(has_grid)
        self.grid_page=has_grid
        self.switcher.set_visible(is_library)
        self.period.set_visible(is_library)
        self.page_title.set_label(self.page_titles[row.key])
        self.header.set_title_widget(self.switcher if is_library else self.page_title)
        self.update_header()
        self.stack.set_visible_child_name("library" if has_grid else "status")
        self.status_actions.set_visible(row.key == "locked")
        if row.key in ('albums','people','tags','duplicates','sharing','map','pinned'):
            if row.key=='pinned':self.manage_pins();return
            collection_view(self,row.key);return
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
        if has_grid:
            self.search_library()

    def change_mode(self, *_):
        if not hasattr(self, "mosaic"):
            return
        self.mosaic.set_mode(self.switcher.get_active_name())
        if self.client and self.bucket_scope:
            self.bucket_scope={};self.search_library()
        self.scroller.get_vadjustment().set_value(0)
        newest=self.media_items[0].created if self.media_items else None
        self.period.set_label({'all':newest.strftime('%B %Y') if newest else 'Library',
                               'months':newest.strftime('%Y') if newest else 'Library','years':'Library'}[self.mosaic.mode])

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
        dialog = Adw.AboutDialog(application_name="Galeria", application_icon="com.neg-zero.Galeria",
                                 version="0.5.0", developer_name="Negative Zero",
                                 comments="A native gallery for local folders and Immich.")
        dialog.present(self)

    def welcome(self):
        dialog=Adw.Dialog(title='Welcome to Galeria',content_width=360)
        body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=20,
                     margin_top=24,margin_bottom=24,margin_start=24,margin_end=24)
        self.welcome_illustration=Gtk.Picture(can_shrink=True,content_fit=Gtk.ContentFit.CONTAIN,
                                             height_request=140)
        self.welcome_illustration.add_css_class('illustration-slot')
        body.append(self.welcome_illustration)
        body.append(label('Do you want to use Immich?','title-2',wrap=True,justify=Gtk.Justification.CENTER))
        body.append(label('Connect to your Immich library, or choose folders on this device.',
                          wrap=True,justify=Gtk.Justification.CENTER))
        actions=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        for response,title in [('immich','Yes, use Immich'),('local','No, choose folders')]:
            choice=Gtk.Button(label=title,height_request=44)
            if response=='immich':
                choice.add_css_class('suggested-action')
            choice.connect('clicked',lambda _,value=response:(dialog.close(),self.welcome_response(dialog,value)))
            actions.append(choice)
        body.append(actions)
        dialog.set_child(body)
        self.dialog=dialog
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
        paths = [folders.get_item(i).get_path() for i in range(folders.get_n_items())]
        if paths and all(paths):
            self.connect_local(paths)

    def login(self):
        dialog = Adw.Dialog(title="Sign in to Immich", content_width=440, content_height=490)
        active={'value':True}
        dialog.connect('closed',lambda *_:active.update(value=False))
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        body.add_css_class("login-body")
        body.append(Gtk.Image(icon_name="folder-pictures-symbolic", pixel_size=52, margin_top=8, margin_bottom=4))
        body.append(label("Your Immich library", "title-2"))
        group = Adw.PreferencesGroup()
        self.server_entry = Adw.EntryRow(title="Server address")
        self.server_entry.set_text(self.preferences.get('server',''))
        self.server_entry.set_input_purpose(Gtk.InputPurpose.URL)
        self.email_entry = Adw.EntryRow(title="Email")
        self.email_entry.set_text(self.preferences.get('email',''))
        self.email_entry.set_input_purpose(Gtk.InputPurpose.EMAIL)
        self.password_entry = Adw.PasswordEntryRow(title="Password")
        for row in (self.server_entry, self.email_entry, self.password_entry):
            group.add(row)
        body.append(group)
        remember=Adw.SwitchRow(title='Remember this account',active=True,subtitle='Store the session in the system keyring')
        remember_group=Adw.PreferencesGroup();remember_group.add(remember);body.append(remember_group)
        sign_in = Gtk.Button(label="Sign in", height_request=44)
        sign_in.add_css_class("suggested-action")
        sign_in.add_css_class("pill")
        message = label("", "dim-label", wrap=True, justify=Gtk.Justification.CENTER)
        def submit(_):
            try:
                client=ImmichClient(self.server_entry.get_text())
                email=self.email_entry.get_text().strip()
                password=self.password_entry.get_text()
                if not email or not password:
                    raise LibraryError('Enter your email and password.')
            except LibraryError as error:
                message.set_label(str(error));return
            sign_in.set_sensitive(False)
            message.set_label('Signing in…')
            self.password_entry.set_text('')
            def connected(_user):
                if not active['value'] or self.dialog!=dialog:return
                dialog.close()
                self.preferences['remember']=remember.get_active()
                self.connect_immich(client)
                if remember.get_active():self.remember_account(client)
            def failed(error):
                if not active['value'] or self.dialog!=dialog:return
                sign_in.set_sensitive(True)
                message.set_label(error)
            self.background(lambda:client.login(email,password),connected,failed)
        sign_in.connect('clicked',submit)
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
        super().__init__(application_id="com.neg-zero.Galeria", flags=Gio.ApplicationFlags.HANDLES_OPEN)

    def ensure_window(self):
        if self.get_active_window():
            self.get_active_window().present()
            return False
        provider = Gtk.CssProvider()
        provider.load_from_path(str(Path(__file__).with_name("style.css")))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.window = GalleryWindow(self)
        self.window.present()
        return True

    def do_activate(self):
        if self.ensure_window():GLib.idle_add(self.window.restore_last_library)

    def do_open(self,files,_count,_hint):
        self.ensure_window()
        paths=[file.get_path() for file in files if file.get_path()]
        if paths:self.window.connect_local(paths,focus_first=len(paths)==1)
        else:self.window.notice('Open device files or connect an Immich library.')


if __name__ == "__main__":
    raise SystemExit(Gallery().run(sys.argv))
