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
        self.player.connect('notify::state',self.state_changed)
        self.player.connect('error',self.failed)
        self.player.get_queue().add_item(Clapper.MediaItem.new(uri))

    def play(self):self.player.play()

    def pause(self):self.player.pause()

    def state_changed(self,*_):
        state=self.player.get_state()
        if state in (Clapper.PlayerState.PLAYING,Clapper.PlayerState.PAUSED):self.has_played=True
        loading=(state==Clapper.PlayerState.BUFFERING or state==Clapper.PlayerState.STOPPED and not self.has_played) and not self.error_label.get_visible()
        self.spinner.set_visible(loading)
        if not loading:self.video.set_opacity(1)

    def failed(self,_player,error,*_):
        self.spinner.set_visible(False)
        self.error_label.set_label('Could not play video: '+error.message)
        self.error_label.set_visible(True)

    def stop(self):self.player.stop()
