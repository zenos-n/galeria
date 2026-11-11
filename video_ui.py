"""Clapper's native GTK player with loading feedback and media controls."""
import gi
gi.require_version('Clapper','0.0')
gi.require_version('ClapperGtk','0.0')
from gi.repository import Adw,Clapper,ClapperGtk,Gio,GLib,Gtk

Clapper.init(None)


class VideoPlayer(Gtk.Overlay):
    def __init__(self,uri,window=None):
        super().__init__(hexpand=True,vexpand=True,css_classes=['galeria-video'])
        self.has_played=False
        self.video=ClapperGtk.Video.new()
        self.set_child(self.video)
        self.video.set_opacity(0)
        controls=ClapperGtk.SimpleControls.new();controls.set_valign(Gtk.Align.END)
        self.video.add_fading_overlay(controls)
        self.spinner=Adw.Spinner(width_request=32,height_request=32,can_target=False,
                                 halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER)
        self.add_overlay(self.spinner)
        self.error_label=Gtk.Label(wrap=True,visible=False,halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER,
                                  css_classes=['osd'],margin_start=24,margin_end=24)
        self.add_overlay(self.error_label)
        self.player=self.video.get_player()
        self.player.set_autoplay(False)
        from session_store import preferences_read,preferences_write
        prefs=window.preferences if window and hasattr(window,'preferences') else preferences_read()
        self.loop_switch=Gtk.Switch(active=prefs.get('video_loop',False),valign=Gtk.Align.CENTER)
        row=Gtk.Box(spacing=18,margin_start=10,margin_end=10,margin_top=6,margin_bottom=6)
        row.append(Gtk.Label(label='Loop',xalign=0,hexpand=True));row.append(self.loop_switch)
        self.loop_switch.update_property([Gtk.AccessibleProperty.LABEL],['Loop video'])
        # Clapper 0.10 exposes its mutable menu through the inner GtkMenuButton.
        popover=controls.get_extra_menu_button().get_first_child().get_popover()
        section=popover.get_menu_model().get_item_link(0,Gio.MENU_LINK_SECTION)
        item=Gio.MenuItem();item.set_attribute_value('custom',GLib.Variant('s','galeria-loop'))
        section.remove(1);section.insert_item(1,item);popover.add_child(row,'galeria-loop')
        def loop_changed(*_):
            active=self.loop_switch.get_active()
            self.player.get_queue().set_progression_mode(Clapper.QueueProgressionMode.REPEAT_ITEM if active else Clapper.QueueProgressionMode.NONE)
            prefs['video_loop']=active
            if window and hasattr(window,'save_preferences'):window.save_preferences()
            else:preferences_write(prefs)
            self.state_changed()
        self.player.get_queue().set_progression_mode(Clapper.QueueProgressionMode.REPEAT_ITEM if self.loop_switch.get_active() else Clapper.QueueProgressionMode.NONE)
        self.loop_switch.connect('notify::active',loop_changed)
        self.end_replay=Gtk.Button(label='Replay',halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER,visible=False,css_classes=['osd','pill'])
        self.end_replay.connect('clicked',lambda _:self.restart());self.add_overlay(self.end_replay)
        self.player.connect('notify::state',self.state_changed)
        self.player.connect('notify::position',self.state_changed)
        self.player.connect('error',self.failed)
        self.player.get_queue().add_item(Clapper.MediaItem.new(uri))

    def restart(self):self.end_replay.set_visible(False);self.player.seek(0);self.player.play()

    def toggle(self):
        if self.player.get_state()==Clapper.PlayerState.PLAYING:self.pause()
        elif self.end_replay.get_visible() or self.player.get_state()==Clapper.PlayerState.STOPPED and self.has_played:self.restart()
        else:self.play()

    def play(self):self.player.play()

    def pause(self):self.player.pause()

    def state_changed(self,*_):
        state=self.player.get_state()
        if state in (Clapper.PlayerState.PLAYING,Clapper.PlayerState.PAUSED):self.has_played=True
        item=self.player.get_queue().get_current_item();duration=item.get_duration() if item else 0
        ended=state==Clapper.PlayerState.STOPPED or state==Clapper.PlayerState.PAUSED and duration>0 and self.player.get_position()>=duration-.05
        looping=self.player.get_queue().get_progression_mode()==Clapper.QueueProgressionMode.REPEAT_ITEM
        self.end_replay.set_visible(ended and self.has_played and not looping)
        loading=(state==Clapper.PlayerState.BUFFERING or state==Clapper.PlayerState.STOPPED and not self.has_played) and not self.error_label.get_visible()
        self.spinner.set_visible(loading)
        if not loading:self.video.set_opacity(1)

    def failed(self,_player,error,*_):
        self.spinner.set_visible(False)
        self.error_label.set_label('Could not play video: '+error.message)
        self.error_label.set_visible(True)

    def stop(self):self.player.stop()
