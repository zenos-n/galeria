#!/usr/bin/env python3
"""Native GTK gallery for local folders and Immich."""
from pathlib import Path
from collections import deque
from types import SimpleNamespace
import os
import sys
import threading
import time

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Graphene, Gsk, Gtk

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
        self.open_paths=[];self.open_items=deque();self.restoring_library=False;self.reading_open_files=False;self.open_notice=None;self.open_serial=0
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
        from date_label import DateLabel
        self.date_motion=DateLabel(self);self.root_overlay.add_overlay(self.date_motion)
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
        self.drop_target.connect("accept", lambda *_: self.get_visible_dialog() is None)
        self.drop_target.connect("enter", self.drop_enter)
        self.drop_target.connect("leave", lambda *_: self.drop_hint.set_visible(False))
        self.drop_target.connect("drop", self.drop_files)
        self.add_controller(self.drop_target)

    def drop_enter(self, *_):
        self.root_overlay.remove_overlay(self.drop_hint);self.root_overlay.add_overlay(self.drop_hint)
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
            ("Pinned", []),
            ("Collections", []),
            ("Media types", [("photos", "Photos", "image-x-generic-symbolic"), ("videos", "Videos", "video-x-generic-symbolic"),
                              ("screenshots", "Screenshots", "camera-photo-symbolic"), ("live", "Live Photos", "media-playback-start-symbolic")]),
            ("Utilities", [("duplicates", "Review duplicates", "edit-copy-symbolic"),
                           ("people", "People", "gallery-people-symbolic"), ("tags", "Tags", "gallery-tag-symbolic"),
                           ("trash", "Trash", "user-trash-symbolic")]),
            ("More", [("archive", "Archive", "folder-symbolic"), ("locked", "Locked folder", "changes-prevent-symbolic")]),
        ]:
            section=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            body.append(section)
            if heading:
                section.append(label(heading, "sidebar-section", xalign=0))
            if heading == "Collections":
                self.album_tree = AlbumTree(self)
                section.append(self.album_tree)
                continue
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
            section.append(nav)
            self.lists.append(nav)
            if heading=='Pinned':
                self.pin_nav=nav
                self.pin_rows=[]
                self.pin_section=section
                section.set_visible(False)
        self.uploads = Uploads(self)
        sidebar.append(self.uploads)
        self.source_label = label("No library connected", "source-label", xalign=0)

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
        self.period = label("", "timeline-date", margin_start=6, xalign=0, halign=Gtk.Align.START)
        self.period.set_opacity(0)
        header.pack_start(self.period)
        self.switcher = Adw.ToggleGroup(valign=Gtk.Align.CENTER)
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
        self.scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True,hexpand=True)
        adjustment=self.scroller.get_vadjustment()
        adjustment.connect('value-changed',self.scroll_changed)
        adjustment.connect('changed',self.load_visible_thumbnails)
        self.scroller.add_css_class("timeline")
        scroll_input=Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.BOTH_AXES,propagation_phase=Gtk.PropagationPhase.CAPTURE)
        scroll_input.connect('scroll',self.user_scrolled);self.scroller.add_controller(scroll_input)
        scroll_keys=Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        scroll_keys.connect('key-pressed',lambda _,key,*args:self.user_scrolled() if key in (Gdk.KEY_Up,Gdk.KEY_Down,Gdk.KEY_Page_Up,Gdk.KEY_Page_Down,Gdk.KEY_Home,Gdk.KEY_End) else False)
        self.scroller.add_controller(scroll_keys)
        self.mosaic = Mosaic(self.open_viewer,[])
        self.scroller.set_child(self.mosaic)
        from year_scroll_ui import YearScrollbar
        self.year_scrollbar=YearScrollbar(self)
        self.library_view=Gtk.Overlay(child=self.scroller)
        self.library_view.add_overlay(self.year_scrollbar)
        self.year_scrollbar.attach(self.library_view)
        self.stack.add_named(self.library_view, "library")
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
        select_all=Gtk.Button(label='Select month');self.select_scope_button=select_all
        select_all.connect('clicked',lambda _:self.mosaic.select_all())
        actionbar.pack_start(select_all)
        cancel=Gtk.Button(label='Cancel')
        cancel.connect('clicked',lambda _:self.mosaic.set_selection(False))
        actionbar.pack_start(cancel)
        self.selection_controls={}
        for icon,title,callback in [
            ('folder-download-symbolic','Download selected',lambda _:self.download_items([self.mosaic.tiles[i].media_item for i in sorted(self.mosaic.selected)])),
            ('gallery-share-symbolic','Share selected',lambda _:share_sheet(self,len(self.mosaic.selected))),
            ('list-add-symbolic','Add to album',lambda _:self.add_selected_to_album()),
            ('starred-symbolic','Favorite selected',lambda _:self.selected_action('favorite')),
            ('folder-symbolic','Archive or unarchive selected',lambda widget:self.selected_action('archive',target=widget)),
            ('changes-prevent-symbolic','Move to locked folder',lambda widget:self.move_selected_to_locked(target=widget)),
            ('user-trash-symbolic','Trash or restore selected',lambda widget:self.selected_action('trash',target=widget)),
        ]:
            control=button(icon,title,callback);actionbar.pack_end(control)
            if title=='Download selected':self.download_selected_button=control
            for action,symbol in [('trash','user-trash-symbolic'),('archive','folder-symbolic'),('locked','changes-prevent-symbolic')]:
                if icon==symbol:self.selection_controls[action]=control
        self.selection_bar.set_child(actionbar)
        self.toolbar.add_bottom_bar(self.selection_bar)
        self.mosaic.on_selection=self.selection_changed
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.key_pressed)
        self.add_controller(keys)

    def key_pressed(self, _controller, keyval, _keycode, state):
        if keyval in (Gdk.KEY_v,Gdk.KEY_V) and state & Gdk.ModifierType.CONTROL_MASK and not state & (Gdk.ModifierType.ALT_MASK|Gdk.ModifierType.SUPER_MASK|Gdk.ModifierType.SHIFT_MASK) and not isinstance(self.get_focus(),(Gtk.Editable,Gtk.TextView)) and not self.get_visible_dialog() and not (self.viewer and (self.viewer.editing or self.viewer.device_file)):
            self.paste_image();return True
        if self.viewer:
            return self.viewer.on_key(_controller, keyval, _keycode, state)
        if keyval in (Gdk.KEY_d,Gdk.KEY_D) and state & Gdk.ModifierType.SHIFT_MASK and not state & (Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.ALT_MASK|Gdk.ModifierType.SUPER_MASK) and not isinstance(self.get_focus(),Gtk.Editable) and not self.get_visible_dialog() and self.mosaic.selection_mode and self.mosaic.selected:
            self.download_items([self.mosaic.tiles[i].media_item for i in sorted(self.mosaic.selected)]);return True
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

    def request_folder_sync(self):
        from sync_service import request_sync
        self.uploads.requested()
        self.background(request_sync,lambda _:self.uploads.poll_sync(),self.uploads.failed)

    def download_items(self,items):
        from download_ui import download_items
        download_items(self,items)

    def selection_changed(self):
        active=self.mosaic.selection_mode
        self.select_button.set_active(active)
        self.selection_bar.set_reveal_child(active)
        self.select_scope_button.set_label('Select all from selected months' if self.mosaic.mode=='all' and len(self.mosaic.selection_months())>1 else 'Select month' if self.mosaic.mode=='all' else 'Select all')
        self.selection_title.set_label(f'{len(self.mosaic.selected)} selected' if self.mosaic.selected else 'Select items')
        self.update_header()

    def update_header(self):
        active=self.mosaic.selection_mode
        is_library=self.current_page=='library'
        self.period.set_visible(not self.searching and not active and is_library)
        self.update_period()
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
        user=self.client.user if self.client else {}
        admin=bool(user.get('isAdmin'))
        self.lookup_action('admin').set_enabled(admin)
        self.hamburger_menu.remove_all()
        entries=[('Choose library…','source'),('Refresh library','refresh'),('Folder sync','sync')]+([('Administration','admin')] if admin else [])
        for title,action in entries+[('Preferences','preferences'),('About Galeria','about')]:
            self.hamburger_menu.append(title,'win.'+action)
        self.avatar.set_text(user.get('name','') if user else 'Galeria')
        self.avatar.set_show_initials(bool(user))
        self.avatar.set_custom_image(None)
        if user:self.load_profile_photo()

    def load_profile_photo(self):
        client=self.client
        if not client:return
        revision=client.user.get('profileChangedAt')
        from imaging import decode_image
        def ready(pixels):
            if self.client is client and pixels is not None and client.user.get('profileChangedAt')==revision:
                self.avatar.set_custom_image(self.texture_from_pixels(pixels))
        def load():
            data=client.profile_image(cached=True) if getattr(client,'restoring',False) else client.profile_image()
            return decode_image(data,96) if data else None
        self.background(load,ready,lambda _:None)

    def change_profile_photo(self):
        client=self.client
        if not client:return
        picker=Gtk.FileDialog(title='Choose your Immich profile photo')
        images=Gtk.FileFilter(name='Images');images.add_mime_type('image/*')
        filters=Gio.ListStore.new(Gtk.FileFilter);filters.append(images);picker.set_filters(filters)
        def chosen(picker,result):
            try:file=picker.open_finish(result)
            except GLib.Error:return
            if not file.get_path():self.notice('Choose an image on this device.');return
            def work():
                with open(file.get_path(),'rb') as stream:data=stream.read(20*1024*1024+1)
                if len(data)>20*1024*1024:raise LibraryError('Choose a profile photo smaller than 20 MB.')
                return client.upload_profile_image(data,file.get_basename())
            self.background(work,lambda _:(self.remember_user(),self.load_profile_photo(),self.notice('Profile photo updated.')))
        picker.open(self,None,chosen)

    def account_menu(self):
        popover=Gtk.Popover()
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6,margin_top=12,margin_bottom=12,margin_start=12,margin_end=12,width_request=220)
        user=self.client.user if self.client else {}
        if user:
            box.append(label(user.get('name','Account'),'heading',xalign=0))
            box.append(label(user.get('email',''),'dim-label',xalign=0,ellipsize=3))
        entries=[('Change profile photo…',self.change_profile_photo),('Folder sync',self.show_folder_sync),('Preferences',lambda:preferences(self)),('Switch library…',self.welcome),('Sign out',self.sign_out)] if self.client else [('Choose library…',self.welcome),('Preferences',lambda:preferences(self))]
        for title,callback in entries:
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
        if row.key in ('albums','people','tags','duplicates','sharing','map'):
            collection_view(self,row.key);return
        if not has_grid:
            titles = {
                "favorites": ("starred-symbolic", "Your favorites", "The photos you love will live here."),
                "map": ("find-location-symbolic", "Your places", "A map of the places in your library."),
                "sharing": ("emblem-shared-symbolic", "Shared with you", "Your shared albums, together in one place."),
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
            self.bucket_scope={};self.search_library(preserve_folder=True)
        self.scroller.get_vadjustment().set_value(getattr(self.mosaic,'transition_scroll',0))
        self.update_period()

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
                                 version="0.14.8", developer_name="Negative Zero",
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

    def paste_image(self):
        from import_ui import paste_image
        paste_image(self)

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

    def clear_open_notice(self):
        if self.open_notice:self.open_notice.dismiss();self.open_notice=None

    def cancel_open_files(self):
        self.open_serial+=1;self.reading_open_files=False
        self.open_paths.clear();self.open_items.clear();self.clear_open_notice()

    def queue_open_files(self,paths):
        self.open_paths.extend(paths)
        if not self.open_notice:
            self.open_notice=Adw.Toast(title='Opening file…',timeout=0);self.toast.add_toast(self.open_notice)
        self.read_open_files()

    def read_open_files(self):
        if self.restoring_library or self.reading_open_files or not self.open_paths:return
        from imaging import image_ratio
        from library import scan_folders
        paths,self.open_paths=self.open_paths,[];self.reading_open_files=True;serial=self.open_serial
        def probe(path):
            try:return image_ratio(path)
            except (OSError,ValueError):return 1.5
        def ready(value):
            if self.data_stopped or self.open_serial!=serial:return
            self.reading_open_files=False;self.clear_open_notice()
            if not self.get_visible():return
            items,errors=value
            self.open_items.extend(items)
            if not items:self.notice(errors[0] if errors else 'No supported photos or videos found.')
            elif self.viewer:
                viewer=self.viewer
                def leave_viewer():
                    if self.data_stopped or self.viewer is not viewer or not self.open_items:return False
                    if viewer.media_stack.get_transition_running():return True
                    viewer.close();return False
                if leave_viewer():GLib.timeout_add(30,leave_viewer)
            else:self.show_next_open_file()
            self.read_open_files()
        def read():
            items={};errors=[]
            for path in dict.fromkeys(paths):
                batch,problems=scan_folders([path],probe);errors.extend(problems)
                for item in batch:items.setdefault(item.id,item)
            return list(items.values()),errors
        def done(future):
            if future.cancelled():return
            try:value=future.result()
            except Exception:value=([],['Could not read the opened file.'])
            GLib.idle_add(ready,value)
        self.previews.submit(read).add_done_callback(done)

    def show_next_open_file(self):
        if self.data_stopped or not self.get_visible() or self.viewer or not self.open_items:return
        dialog=self.get_visible_dialog()
        if dialog:
            if dialog.get_title()=='Welcome to Galeria':dialog.close()
            else:
                handler=dialog.connect('closed',lambda dialog:(dialog.disconnect(handler),GLib.idle_add(self.show_next_open_file)))
                return
        if self.current_page=='locked':
            row=self.rows['library'];self.navigate(row.get_parent(),row)
        item=self.open_items.popleft()
        self.open_viewer(-1,SimpleNamespace(media_item=item,filename=item.filename,photo_ratio=item.ratio),device_file=True)

    def open_viewer(self, index, source=None, device_file=False):
        if self.viewer:
            return
        source = source or self.mosaic.tiles[index % len(self.mosaic.tiles)]
        if source.media_item and source.media_item.metadata.get('placeholder'):return
        self.viewer = Viewer(self, index, source, device_file=device_file)
        self.viewer.show()


class Gallery(Adw.Application):
    background_enabled=GObject.Property(type=bool,default=False)
    def __init__(self):
        super().__init__(application_id="com.neg-zero.Galeria", flags=Gio.ApplicationFlags.HANDLES_OPEN|Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window=None;self.background_enabled=False;self.quitting=False;self.control=None;self.pending_sync=False
        self.open_monitor=None
        self.add_main_option('background',0,GLib.OptionFlags.NONE,GLib.OptionArg.NONE,'Start without opening a window',None)
        self.add_main_option('folder-sync',0,GLib.OptionFlags.NONE,GLib.OptionArg.NONE,'Open folder syncing',None)
        self.add_main_option('monitor',0,GLib.OptionFlags.NONE,GLib.OptionArg.STRING,'Open on this monitor connector','CONNECTOR')
        self.add_main_option(GLib.OPTION_REMAINING,0,GLib.OptionFlags.NONE,GLib.OptionArg.FILENAME_ARRAY,'Media files or folders','FILES')
        quit_action=Gio.SimpleAction.new('quit',None);quit_action.connect('activate',lambda *_:self.force_quit());self.add_action(quit_action)
        self.set_accels_for_action('app.quit',['<Control>q'])

    def do_startup(self):
        Adw.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_path(str(Path(__file__).with_name("style.css")))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        from startup import LoginStartup
        from desktop_control import DesktopControl
        from session_store import preferences_read
        Gtk.Window.set_default_icon_name('com.neg-zero.Galeria')
        self.login_startup=LoginStartup()
        self.set_background(preferences_read().get('background',False))
        self.control=DesktopControl(self,self.get_dbus_connection())
        def refresh_login():
            try:self.login_startup.refresh()
            except (OSError,LibraryError):pass
        threading.Thread(target=refresh_login,daemon=True).start()

    def set_background(self,enabled,persist=False):
        if persist:
            from session_store import preferences_read,preferences_write
            prefs=self.window.preferences if self.window else preferences_read()
            prefs['background']=bool(enabled);preferences_write(prefs)
        if self.background_enabled!=enabled:
            self.background_enabled=bool(enabled)
            self.hold() if enabled else self.release()
        if not enabled and self.window and not self.window.get_visible():self.window.present()
        self.emit_state()

    def emit_state(self):
        if self.control:self.control.emit()

    def force_quit(self):
        windows=[window for window in self.get_windows() if isinstance(window,GalleryWindow)]
        for window in windows:
            if window.viewer and window.viewer.confirm_leave(self.force_quit):return False
        self.quitting=True
        for window in windows:window.close()
        self.quit();return False

    def do_shutdown(self):
        for window in self.get_windows():
            if isinstance(window,GalleryWindow):window.stop_data()
        if self.control:self.control.close()
        Adw.Application.do_shutdown(self)

    def ensure_window(self):
        if self.window is not None and not self.window.data_stopped:
            self.window.present()
            return False
        self.window = GalleryWindow(self)
        self.window.connect('notify::visible',lambda *_:self.emit_state())
        if self.open_monitor:
            monitors=Gdk.Display.get_default().get_monitors()
            monitor=next((monitors.get_item(i) for i in range(monitors.get_n_items()) if monitors.get_item(i).get_connector()==self.open_monitor),None)
            if monitor:
                # Wayland permits choosing a monitor for fullscreen before first map.
                self.window.fullscreen_on_monitor(monitor)
                def mapped(window):
                    window.disconnect(handler)
                    def restore():
                        if self.window:self.window.unfullscreen();GLib.timeout_add(350,verify)
                        return False
                    GLib.timeout_add(250,restore)
                def verify():
                    if not self.window or not self.window.get_surface():return False
                    actual=Gdk.Display.get_default().get_monitor_at_surface(self.window.get_surface())
                    if actual!=monitor:self.window.fullscreen_on_monitor(monitor);GLib.timeout_add(350,verify)
                    else:print('Galeria monitor: '+actual.get_connector()+(' (fullscreen)' if self.window.is_fullscreen() else ' (windowed)'),flush=True)
                    return False
                handler=self.window.connect('map',mapped)
        self.window.present()
        return True

    def do_activate(self):
        if self.ensure_window():
            window=self.window;window.restoring_library=True
            def restored():
                window.restoring_library=False
                self.finish_pending_sync();window.read_open_files()
            GLib.idle_add(window.restore_last_library,restored)
        else:self.finish_pending_sync()

    def open_folder_sync(self):
        self.pending_sync=True;self.activate()

    def finish_pending_sync(self):
        if self.pending_sync and self.window:
            self.pending_sync=False
            if self.window.dialog and self.window.dialog.get_mapped() and self.window.dialog.get_title()=='Welcome to Galeria':self.window.dialog.close()
            self.window.show_folder_sync()

    def do_command_line(self,command_line):
        options=command_line.get_options_dict()
        monitor=options.lookup_value('monitor',None)
        if monitor:self.open_monitor=monitor.unpack()
        values=options.lookup_value(GLib.OPTION_REMAINING,None)
        arguments=[os.fsdecode(value) for value in values.get_bytestring_array()] if values else []
        if options.contains('background'):self.set_background(True)
        if arguments:self.do_open([command_line.create_file_for_arg(value) for value in arguments],len(arguments),'')
        elif options.contains('folder-sync'):self.open_folder_sync()
        elif not options.contains('background'):self.activate()
        return 0

    def do_open(self,files,_count,_hint):
        paths=[file.get_path() for file in files if file.get_path()]
        self.activate()
        if paths:
            self.window.queue_open_files(paths)
        else:self.window.notice('Open device files or connect an Immich library.')


if __name__ == "__main__":
    raise SystemExit(Gallery().run(sys.argv))
