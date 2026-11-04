from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango
from media import PhotoStage
from panels import text, icon_button, share_sheet
from editor import build_editor


class Viewer(Gtk.Overlay):
    def __init__(self, window, index, source=None):
        super().__init__(hexpand=True, vexpand=True)
        self.window, self.index, self.source = window, index, source
        self.editing = self.closing = self.immersive = False
        self.exit_dialog=None;self.exit_saving=False
        self.chrome_timer = 0
        self.chrome_hovered = False
        self.was_fullscreen = window.is_fullscreen()
        self.fullscreen_mix=0.
        self.fullscreen_tick=0
        self.backdrop = Gtk.Box(hexpand=True,vexpand=True)
        self.backdrop.add_css_class('viewer-backdrop')
        self.set_child(self.backdrop)
        self.blackout=Gtk.Box(hexpand=True,vexpand=True,opacity=0,css_classes=['fullscreen-black'])
        self.add_overlay(self.blackout)
        self.viewer_split = Adw.OverlaySplitView(sidebar_position=Gtk.PackType.END, show_sidebar=False,
                                                min_sidebar_width=280,max_sidebar_width=300)
        self.viewer_split.set_sidebar_width_unit(Adw.LengthUnit.PX)
        self.breakpoint_bin = Adw.BreakpointBin(child=self.viewer_split,width_request=300,height_request=240)
        self.add_overlay(self.breakpoint_bin)
        self.photo_overlay = Gtk.Overlay(hexpand=True,vexpand=True)
        self.media_stack = Gtk.Stack(transition_duration=230, hexpand=True,vexpand=True)
        self.stage = PhotoStage(source,index)
        self.media_stack.add_child(self.stage)
        self.photo_overlay.set_child(self.media_stack)
        self.viewer_split.set_content(self.photo_overlay)
        self.header = Adw.HeaderBar(show_start_title_buttons=False,show_end_title_buttons=False)
        self.header.add_css_class('viewer-header')
        self.close_button = icon_button('go-previous-symbolic','Back to gallery (Esc)',lambda _:self.set_editing(False) if self.editing else self.close())
        self.header.pack_start(self.close_button)
        self.title = Adw.WindowTitle(title='Photo preview',subtitle='January 2026')
        self.header.set_title_widget(self.title)
        self.favorite = Gtk.ToggleButton(icon_name='non-starred-symbolic',tooltip_text='Favorite')
        self.favorite.add_css_class('flat')
        self.favorite_syncing=False
        self.favorite.connect('toggled',self.toggle_favorite)
        self.header.pack_start(self.favorite)
        self.edit_button = Gtk.Button(label='Edit',tooltip_text='Edit image')
        self.edit_button.add_css_class('flat')
        self.edit_button.connect('clicked',lambda _:self.set_editing(not self.editing))
        self.header.pack_end(self.edit_button)
        self.info = Gtk.ToggleButton(icon_name='info-outline-symbolic',tooltip_text='Photo details')
        self.info.add_css_class('flat')
        self.info.connect('toggled',self.toggle_details)
        self.header.pack_end(self.info)
        self.download = icon_button('folder-download-symbolic','Download',lambda _:window.download_items([self.source.media_item]))
        self.share = icon_button('gallery-share-symbolic','Share',lambda _:share_sheet(window))
        self.fullscreen_button = icon_button('view-fullscreen-symbolic','Fullscreen media',lambda _:self.set_immersive(not self.immersive))
        for widget in (self.download,self.share,self.fullscreen_button):
            self.header.pack_end(widget)
        self.archive=icon_button('folder-symbolic','Remove from archive' if window.current_page=='archive' else 'Archive',lambda widget:window.selected_action('archive',[self.source.media_item],target=widget))
        self.trash=icon_button('user-trash-symbolic','Restore from trash' if window.current_page=='trash' else 'Move to trash',lambda widget:window.selected_action('trash',[self.source.media_item],target=widget))
        self.lock=icon_button('changes-prevent-symbolic','Move to locked folder',lambda widget:window.move_selected_to_locked([self.source.media_item],target=widget))
        for widget in (self.archive,self.trash,self.lock):self.header.pack_end(widget)
        self.viewing_controls=[self.favorite,self.info,self.download,self.share,self.fullscreen_button,self.archive,self.trash,self.lock]
        self.header_revealer=Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.CROSSFADE,
                                         transition_duration=300,reveal_child=True,valign=Gtk.Align.START)
        self.header_revealer.set_child(self.header)
        self.photo_overlay.add_overlay(self.header_revealer)
        self.arrows=[]
        self.arrow_revealers=[]
        for step,icon,align in [(-1,'go-previous-symbolic',Gtk.Align.START),(1,'go-next-symbolic',Gtk.Align.END)]:
            arrow=icon_button(icon,'Previous photo' if step<0 else 'Next photo',lambda _,n=step:self.move(n))
            arrow.add_css_class('circular')
            arrow.add_css_class('viewer-arrow')
            reveal=Gtk.Revealer(child=arrow,transition_type=Gtk.RevealerTransitionType.CROSSFADE,
                                transition_duration=300,reveal_child=True,halign=align,valign=Gtk.Align.CENTER)
            self.photo_overlay.add_overlay(reveal)
            self.arrows.append(arrow)
            self.arrow_revealers.append(reveal)
        self.details=Adw.ToolbarView()
        self.details.add_css_class('details-sidebar')
        details_header=Adw.HeaderBar(show_start_title_buttons=False,show_end_title_buttons=False)
        details_header.set_title_widget(text('Details','heading'))
        details_header.pack_end(icon_button('window-close-symbolic','Close details',lambda _:self.info.set_active(False)))
        self.details.add_top_bar(details_header)
        details_body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=24,
                             margin_top=24,margin_bottom=24,margin_start=22,margin_end=22)
        for heading,value in [('Date','January 2026'),('File','Photo preview'),('Location','No location'),('Camera','No camera information')]:
            group=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
            group.append(text(heading,'dim-label',xalign=0))
            group.append(text(value,xalign=0,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,max_width_chars=30,selectable=True))
            details_body.append(group)
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,child=details_body)
        self.details.set_content(scroll)
        self.detail_labels=[]
        child=details_body.get_first_child()
        while child:
            self.detail_labels.append(child.get_last_child())
            child=child.get_next_sibling()
        self.viewer_split.set_sidebar(self.details)
        breakpoint=Adw.Breakpoint.new(Adw.BreakpointCondition.parse('max-width: 760sp'))
        breakpoint.add_setter(self.viewer_split,'collapsed',True)
        # This is a full-window overlay, so its breakpoint is owned by the window.
        self.breakpoint_bin.add_breakpoint(breakpoint)
        self.editor=Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_UP,valign=Gtk.Align.END)
        self.editor.set_child(self.make_editor())
        self.editor_categories.connect('notify::active-name', self.sync_editor_inset)
        self.photo_overlay.add_overlay(self.editor)
        self.keys=Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        self.keys.connect('key-pressed',self.on_key)
        self.add_controller(self.keys)
        motion=Gtk.EventControllerMotion()
        motion.connect('motion',self.pointer_motion)
        self.add_controller(motion)
        header_motion=Gtk.EventControllerMotion()
        header_motion.connect('enter',lambda *_:setattr(self,'chrome_hovered',True))
        header_motion.connect('leave',lambda *_:setattr(self,'chrome_hovered',False))
        self.header.add_controller(header_motion)
        self.update_metadata()
        background=Gtk.GestureClick(button=1)
        background.connect('released',self.background_released)
        self.add_controller(background)
        context=Gtk.GestureClick(button=3);context.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        def context_pressed(gesture,_count,x,y):
            if self.editing:return
            from copy_ui import media_menu
            media_menu(window,self,self.source.media_item,x,y);gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        context.connect('pressed',context_pressed);self.add_controller(context)
        from zoom_ui import MediaZoom
        self.zoom_controls=MediaZoom(self)

    def background_released(self,gesture,_count,x,y):
        if self.editing or self.stage.progress<1:return
        node=self.pick(x,y,Gtk.PickFlags.DEFAULT)
        while node and node!=self:
            if isinstance(node,(Gtk.Button,Gtk.ToggleButton,Gtk.MenuButton)) or node==self.details:return
            node=node.get_parent()
        ok,bounds=self.stage.picture.compute_bounds(self)
        if ok and bounds.get_x()<=x<=bounds.get_x()+bounds.get_width() and bounds.get_y()<=y<=bounds.get_y()+bounds.get_height():return
        gesture.set_state(Gtk.EventSequenceState.CLAIMED);self.close()

    def prepare_media(self):
        item=self.source.media_item
        if item and item.kind=='VIDEO':
            uri=Gio.File.new_for_path(item.path).get_uri() if item.path else self.window.get_video_proxy().register(self.window.client,item,self.window.vault)
            self.stage.set_video(uri)
        self.window.load_preview(self.stage,self.source)

    def opened(self):
        self.info.set_sensitive(True)
        if self.stage.video_player:self.stage.video_player.play()

    def dismiss_action(self):
        self.closing=True
        if self.chrome_timer:GLib.source_remove(self.chrome_timer);self.chrome_timer=0
        if self.fullscreen_tick:self.remove_tick_callback(self.fullscreen_tick);self.fullscreen_tick=0
        self.dispose_editors();self.stage.dispose()
        if self.get_parent()==self.window.root_overlay:self.window.root_overlay.remove_overlay(self)
        self.window.mosaic.hide_tile(None);self.window.split.set_can_target(True);self.window.viewer=None
        if self.immersive and not self.was_fullscreen:self.window.unfullscreen()

    def dispose_editors(self):
        if self.exit_dialog:self.exit_dialog.close();self.exit_dialog=None
        for name in ('photo_editor','video_editor'):
            editor=getattr(self,name,None)
            if editor:editor.close()

    def update_metadata(self):
        item=getattr(self.source,'media_item',None)
        if not item:return
        exif=item.metadata.get('exifInfo') or {}
        self.title.set_title(item.filename)
        self.title.set_subtitle(item.created.strftime('%d %B %Y'))
        values=[item.created.strftime('%d %B %Y, %H:%M'),item.filename,
                ', '.join(str(exif[key]) for key in ('city','state','country') if exif.get(key)) or 'No location',
                ' '.join(str(exif[key]) for key in ('make','model') if exif.get(key)) or 'No camera information']
        for widget,value in zip(self.detail_labels,values):widget.set_label(value)
        self.edit_button.set_sensitive(item.kind in ('IMAGE','VIDEO'))
        self.favorite_syncing=True;self.favorite.set_active(bool(item.metadata.get('isFavorite')));self.favorite_syncing=False
        self.favorite.set_sensitive(bool(self.window.client))

    def toggle_favorite(self,button):
        active=button.get_active();button.set_icon_name('starred-symbolic' if active else 'non-starred-symbolic')
        button.set_tooltip_text('Remove from favorites' if active else 'Add to favorites')
        if self.favorite_syncing:return
        client=self.window.client;item=self.source.media_item
        if not client:return
        button.set_sensitive(False)
        def done(_):
            item.metadata['isFavorite']=active;self.window.page_cache.clear();client.refresh_serial=getattr(client,'refresh_serial',0)+1
            if self.window.current_page=='favorites' and not active:self.window.pending_media=([value for value in self.window.media_items if value.id!=item.id],True)
            for value in self.window.media_items:
                if value.id==item.id:value.metadata['isFavorite']=active
            if self.source.media_item.id==item.id:button.set_sensitive(True)
        def failed(message):
            if self.source.media_item.id==item.id:
                self.favorite_syncing=True;button.set_active(not active);self.favorite_syncing=False;button.set_sensitive(True)
            self.window.notice(message)
        self.window.background(lambda:client.update_assets([item.id],{'isFavorite':active}),done,failed)

    def show(self):
        # Block pointer interaction without changing the grid's disabled styling.
        self.window.split.set_can_target(False)
        self.window.root_overlay.add_overlay(self)
        self.window.mosaic.hide_tile(self.source)
        self.backdrop.set_opacity(0)
        self.header.set_opacity(0)
        for arrow in self.arrows:
            arrow.set_opacity(0)
        self.close_button.grab_focus()
        self.info.set_sensitive(False)
        self.prepare_media()
        self.stage.animate(self.source,False,self.fade,self.opened)

    def toggle_details(self,widget):
        if widget.get_active():self.zoom_controls.reset()
        if widget.get_active() and self.stage.progress<1:
            widget.set_active(False);return
        self.viewer_split.set_show_sidebar(widget.get_active())

    def fade(self,progress):
        self.backdrop.set_opacity(progress)
        self.header.set_opacity(progress)
        for arrow in self.arrows:
            arrow.set_opacity(progress)

    def close(self):
        if self.closing:
            return
        if self.media_stack.get_transition_running():
            return
        if self.confirm_edit_exit(self.close):return
        self.zoom_controls.reset()
        needs_settle = self.editing or self.immersive or self.viewer_split.get_show_sidebar()
        was_immersive=self.immersive
        self.closing=True
        if self.stage.video_player:self.stage.video_player.pause()
        if self.immersive:
            self.set_immersive(False)
        self.set_editing(False)
        self.info.set_active(False)
        self.window.reveal_tile(self.source)
        def begin():
            def finish():
                self.window.mosaic.hide_tile(None)
                self.window.root_overlay.remove_overlay(self)
                self.stage.dispose()
                self.dispose_editors()
                self.window.split.set_can_target(True)
                self.window.viewer=None
                self.window.flush_pending_media()
                if self.chrome_timer:
                    GLib.source_remove(self.chrome_timer)
                    self.chrome_timer=0
                target=next((tile for tile in self.window.mosaic.tiles if tile.media_item.id==self.source.media_item.id),None)
                if target and target.get_child_visible():target.grab_focus()
            self.stage.animate(self.source,True,self.fade,finish)
            return GLib.SOURCE_REMOVE
        # Allow sidebar/editor/fullscreen geometry to settle before measuring the tile.
        GLib.timeout_add(350 if was_immersive else 220,begin) if needs_settle else GLib.idle_add(begin)

    def move(self,step):
        if self.stage.progress<1 or self.closing or self.media_stack.get_transition_running():
            return
        if self.confirm_edit_exit(lambda:self.move(step)):return
        old=self.stage
        self.dispose_editors();self.photo_editor=None;self.video_editor=None
        if old.video_player:old.video_player.pause()
        self.window.mosaic.hide_tile(None)
        visible=[i for i,tile in enumerate(self.window.mosaic.tiles) if tile in self.window.mosaic.rendered and not tile.media_item.metadata.get('placeholder')]
        self.index=visible[(visible.index(self.index)+step)%len(visible)]
        self.source=self.window.mosaic.tiles[self.index]
        self.stage=PhotoStage(self.source,self.index)
        self.zoom_controls.reset()
        self.editor.set_child(self.make_editor())
        self.editor_categories.connect('notify::active-name',self.sync_editor_inset)
        self.window.mosaic.hide_tile(self.source)
        self.stage.progress=1
        self.stage.set_opacity(1)
        self.stage.thumbnail.set_opacity(0)
        self.stage.material.set_opacity(1)
        self.stage.symbol.set_opacity(1)
        self.stage.immersive=self.immersive
        self.stage.top_inset=0 if self.immersive else 52
        self.media_stack.add_child(self.stage)
        self.media_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT if step>0 else Gtk.StackTransitionType.SLIDE_RIGHT)
        self.media_stack.set_visible_child(self.stage)
        def cleanup():
            if self.media_stack.get_transition_running():
                return GLib.SOURCE_CONTINUE
            self.media_stack.remove(old)
            old.dispose()
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(40,cleanup)
        self.title.set_title(f'Photo preview · {self.index+1}')
        self.update_metadata()
        self.prepare_media()
        stage=self.stage
        def play():
            if self.stage==stage and not self.closing and stage.video_player:stage.video_player.play()
            return False
        GLib.timeout_add(230,play)

    def set_immersive(self,active):
        self.zoom_controls.reset()
        if self.editing or self.stage.progress<1:
            return
        before=self.stage.last_rect
        self.immersive=active
        self.stage.immersive=active
        self.stage.top_inset=0 if active else 52
        self.stage.queue_allocate()
        self.info.set_active(False)
        if active:
            self.window.fullscreen()
            self.fullscreen_button.set_icon_name('view-restore-symbolic')
            self.fullscreen_button.set_tooltip_text('Exit fullscreen (Esc)')
            self.show_chrome(False)
        else:
            if not self.was_fullscreen:
                self.window.unfullscreen()
            self.fullscreen_button.set_icon_name('view-fullscreen-symbolic')
            self.fullscreen_button.set_tooltip_text('Fullscreen media')
            self.show_chrome(True)
        self.stage.animate_geometry(before,duration_ms=320,dynamic=True)
        if self.fullscreen_tick:
            self.remove_tick_callback(self.fullscreen_tick)
        start=self.fullscreen_mix
        started=None
        duration=320000 if Gtk.Settings.get_default().get_property('gtk-enable-animations') else 1
        def frame(_widget,clock):
            nonlocal started
            now=clock.get_frame_time()
            if started is None:started=now
            t=min(1,(now-started)/duration)
            p=t*t*(3-2*t)
            self.fullscreen_mix=start+((1 if active else 0)-start)*p
            self.blackout.set_opacity(self.fullscreen_mix)
            if t>=1:
                self.fullscreen_tick=0
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        self.fullscreen_tick=self.add_tick_callback(frame)

    def show_chrome(self,visible):
        self.header_revealer.set_reveal_child(visible)
        for arrow,reveal in zip(self.arrows,self.arrow_revealers):
            reveal.set_reveal_child(visible)
            arrow.set_can_target(visible)

    def pointer_motion(self,*_):
        if not self.immersive:
            return
        self.show_chrome(True)
        if self.chrome_timer:
            GLib.source_remove(self.chrome_timer)
        def hide():
            if self.chrome_hovered:
                return GLib.SOURCE_CONTINUE
            self.show_chrome(False)
            self.chrome_timer=0
            return GLib.SOURCE_REMOVE
        self.chrome_timer=GLib.timeout_add(1400,hide)

    def on_key(self,_controller,keyval,_keycode=0,state=0):
        if not self.editing and not isinstance(self.window.get_focus(),Gtk.Editable):
            if keyval in (Gdk.KEY_plus,Gdk.KEY_equal,Gdk.KEY_minus,Gdk.KEY_0):
                if keyval==Gdk.KEY_0:self.zoom_controls.reset()
                else:self.zoom_controls.set_zoom(self.stage.zoom*(1.2 if keyval!=Gdk.KEY_minus else 1/1.2))
                return True
        editor=getattr(self,'photo_editor',None) or getattr(self,'video_editor',None)
        if self.editing and editor and not isinstance(self.window.get_focus(),Gtk.Editable):
            if state & Gdk.ModifierType.CONTROL_MASK and keyval in (Gdk.KEY_z,Gdk.KEY_Z,Gdk.KEY_y,Gdk.KEY_Y):
                editor.undo_edits(keyval in (Gdk.KEY_y,Gdk.KEY_Y) or bool(state & Gdk.ModifierType.SHIFT_MASK));return True
        if self.editing and getattr(self,'photo_editor',None) and keyval==Gdk.KEY_Escape and self.photo_editor.markup.entry.get_visible():
            self.photo_editor.markup.finish_text();return True
        if keyval==Gdk.KEY_space and not self.editing and self.stage.video_player and not isinstance(self.window.get_focus(),Gtk.Editable):
            self.stage.video_player.toggle();return True
        if keyval in (Gdk.KEY_d,Gdk.KEY_D) and state & Gdk.ModifierType.SHIFT_MASK and not state & (Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.ALT_MASK|Gdk.ModifierType.SUPER_MASK) and not self.editing and not isinstance(self.window.get_focus(),Gtk.Editable) and not self.window.get_visible_dialog():
            self.window.download_items([self.source.media_item]);return True
        if keyval==Gdk.KEY_space and self.editing and getattr(self,'video_editor',None) and not isinstance(self.window.get_focus(),Gtk.Editable):
            self.video_editor.toggle_playback();return True
        if keyval==Gdk.KEY_c and state & Gdk.ModifierType.CONTROL_MASK and not self.editing and self.source.media_item.kind!='VIDEO':
            from copy_ui import copy_media
            copy_media(self.window,self.source.media_item);return True
        if keyval==Gdk.KEY_Escape:
            if self.editing:
                self.set_editing(False)
            elif self.immersive:
                self.set_immersive(False)
            else:
                self.close()
            return True
        if keyval in (Gdk.KEY_f,Gdk.KEY_F11) and not self.editing:
            self.set_immersive(not self.immersive)
            return True
        if keyval in (Gdk.KEY_Left,Gdk.KEY_Right) and not self.editing:
            self.move(-1 if keyval==Gdk.KEY_Left else 1)
            return True
        if keyval==Gdk.KEY_Tab:
            backwards=bool(state & Gdk.ModifierType.SHIFT_MASK)
            direction=Gtk.DirectionType.TAB_BACKWARD if backwards else Gtk.DirectionType.TAB_FORWARD
            if not self.child_focus(direction):
                self.close_button.grab_focus()
            return True
        return False

    def make_editor(self):
        return build_editor(self)

    def confirm_edit_exit(self,leave):
        if self.exit_dialog or self.exit_saving:return True
        editor=getattr(self,'photo_editor',None) or getattr(self,'video_editor',None)
        if not self.editing or not editor:return False
        if getattr(editor,'markup',None):editor.markup.finish_text()
        if not editor.dirty():return False
        dialog=Adw.AlertDialog(heading='Save changes?',body='Save an edited copy before leaving? Your original stays unchanged.')
        for response,label in [('cancel','Cancel'),('discard','Discard'),('save','Save')]:dialog.add_response(response,label)
        dialog.set_close_response('cancel');dialog.set_default_response('save')
        dialog.set_response_appearance('discard',Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_response_appearance('save',Adw.ResponseAppearance.SUGGESTED)
        self.exit_dialog=dialog
        def respond(_dialog,response):
            self.exit_dialog=None
            if response=='discard':
                editor.discard_changes();GLib.idle_add(lambda:(leave(),False)[1])
            elif response=='save':
                self.exit_saving=True;self.set_sensitive(False)
                def saved(success):
                    self.exit_saving=False;self.set_sensitive(True)
                    if success and self.window.viewer==self:leave()
                GLib.idle_add(lambda:(editor.save_copy(finished=saved),False)[1])
        dialog.connect('response',respond);dialog.present(self.window)
        return True

    def set_editing(self, active):
        if active==self.editing:return
        if not active and self.confirm_edit_exit(lambda:self.set_editing(False)):return
        if active:
            if hasattr(self,'zoom_controls'):self.zoom_controls.reset()
            self.stage.crop_ratio=None
        if active and self.immersive:
            self.set_immersive(False)
        self.editing = active
        if getattr(self,'photo_editor',None):self.photo_editor.queue(0)
        if getattr(self,'video_editor',None):
            self.video_editor.enter() if active else self.video_editor.leave()
        if active:
            self.info.set_active(False)
        for widget in self.viewing_controls + self.arrows:
            widget.set_visible(not active)
        self.editor.set_reveal_child(active)
        self.stage.crop_frame.set_visible(active and self.editor_categories.get_active_name() == 'Crop')
        self.sync_editor_inset()
        self.stage.queue_allocate()
        self.edit_button.set_label('Done' if active else 'Edit')
        self.title.set_title(('Edit video' if getattr(self,'video_editor',None) else 'Edit photo') if active else getattr(self.source,'filename','Photo preview'))

    def sync_editor_inset(self, *_):
        before=self.stage.last_rect
        self.stage.bottom_inset = (self.editor.get_child().measure(
            Gtk.Orientation.VERTICAL, max(300, self.photo_overlay.get_width()))[1] if self.editing else 0)
        self.stage.queue_allocate()
        self.stage.animate_geometry(before)

    def rotate(self, angle):
        if getattr(self,'photo_editor',None):self.photo_editor.rotate(angle);return
        self.stage.rotation = (self.stage.rotation + angle) % 360
        self.stage.symbol.set_from_icon_name("object-rotate-right-symbolic" if self.stage.rotation else "image-x-generic-symbolic")
        self.stage.queue_allocate()

    def flip(self):
        if getattr(self,'photo_editor',None):self.photo_editor.flip();return
        self.stage.flipped = not self.stage.flipped
        self.stage.symbol.set_from_icon_name("object-flip-horizontal-symbolic" if self.stage.flipped else "image-x-generic-symbolic")

    def change_crop(self, dropdown, *_):
        ratio=self.photo_editor.aspect() if getattr(self,'photo_editor',None) else self.stage.ratio
        self.stage.crop_frame.set_aspect([None,ratio,1,4/3,16/9][dropdown.get_selected()])
        if getattr(self,'photo_editor',None):self.photo_editor.remember()

    def reset_edits(self):
        if getattr(self,'video_editor',None):self.video_editor.reset_edits();return
        if getattr(self,'photo_editor',None):self.photo_editor.reset();return
        self.stage.rotation, self.stage.flipped, self.stage.crop_ratio = 0, False, None
        self.stage.symbol.set_from_icon_name("image-x-generic-symbolic")
        self.stage.crop_frame.reset()
        self.crop_dropdown.set_selected(1)
        for scale in self.scales:
            scale.set_value(0)
        self.stage.queue_allocate()


