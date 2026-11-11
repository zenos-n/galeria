"""Clapper's native GTK player with loading feedback and media controls."""
import gi
gi.require_version('Clapper','0.0')
gi.require_version('ClapperGtk','0.0')
from gi.repository import Adw,Clapper,ClapperGtk,Gtk

Clapper.init(None)


class VideoPlayer(Gtk.Overlay):
    def __init__(self,uri):
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
