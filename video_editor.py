"""Video trim, crop, rotation, filter previews and save-copy controls."""
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
from gi.repository import Adw,Gio,GLib,Gtk
from imaging import decode_image
from library import LibraryError
from video_edit import Edits,FILTERS,probe,frame,export,Cancelled


def time_label(seconds):
    minutes,seconds=divmod(max(0,seconds),60);hours,minutes=divmod(int(minutes),60)
    return f'{hours}:{minutes:02}:{seconds:04.1f}' if hours else f'{minutes}:{seconds:04.1f}'


class VideoEditor(Gtk.Box):
    def __init__(self,viewer):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=10,css_classes=['editor-bar'])
        self.viewer=viewer;self.uri=None;self.original=None;self.duration=0;self.rotation=0;self.filter='Original'
        self.generation=0;self.debounce=0;self.cancel=None;self.running=False;self.syncing=False
        self.temporary=tempfile.TemporaryDirectory(prefix='galeria-video-');self.original_ratio=viewer.stage.ratio
        categories=Adw.ToggleGroup(halign=Gtk.Align.CENTER,css_classes=['round'])
        for name in ['Trim','Crop','Filters']:categories.add(Adw.Toggle(name=name,label=name))
        self.append(categories);viewer.editor_categories=categories
        stack=Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,hhomogeneous=True,vhomogeneous=True)
        viewer.editor_stack=stack;viewer.scales=[]
        self.controls=Adw.Clamp(maximum_size=700,child=stack);self.append(self.controls)
        trim=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        row=Gtk.Box(spacing=12,halign=Gtk.Align.CENTER)
        self.start=Gtk.SpinButton.new_with_range(0,1,.1);self.end=Gtk.SpinButton.new_with_range(0,1,.1)
        for title,widget in [('Start (seconds)',self.start),('End (seconds)',self.end)]:
            column=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
            column.append(Gtk.Label(label=title,xalign=0));widget.set_digits(1);widget.set_width_chars(9)
            widget.connect('value-changed',self.trim_changed);column.append(widget);row.append(column)
        trim.append(row)
        self.position=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,1,.1)
        self.position.set_size_request(420,-1);self.position.set_draw_value(False);self.position.connect('value-changed',self.queue_preview)
        trim.append(self.position);self.times=Gtk.Label(css_classes=['dim-label']);trim.append(self.times)
        stack.add_named(trim,'Trim')
        crop=Gtk.Box(spacing=10,halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER)
        for icon,title,angle in [('gallery-rotate-acw-symbolic','Rotate left',-90),('gallery-rotate-cw-symbolic','Rotate right',90)]:
            button=Gtk.Button(icon_name=icon,tooltip_text=title,css_classes=['flat']);button.connect('clicked',lambda _,angle=angle:self.rotate(angle));crop.append(button)
        crop.append(Gtk.Label(label='Aspect ratio'))
        viewer.crop_dropdown=Gtk.DropDown.new_from_strings(['Free','Original','Square','4:3','16:9'])
        viewer.crop_dropdown.connect('notify::selected',self.aspect_changed);crop.append(viewer.crop_dropdown)
        stack.add_named(crop,'Crop')
        filters=Gtk.Box(spacing=6,halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER)
        first=None;self.filter_buttons=[]
        for name in FILTERS:
            button=Gtk.ToggleButton(label=name,css_classes=['flat','editor-choice'])
            if first:button.set_group(first)
            else:first=button;button.set_active(True)
            button.connect('toggled',lambda button,name=name:self.choose_filter(name) if button.get_active() else None)
            filters.append(button);self.filter_buttons.append(button)
        stack.add_named(filters,'Filters')
        self.message=Gtk.Label(label='Preparing video…',wrap=True,justify=Gtk.Justification.CENTER,css_classes=['dim-label']);self.append(self.message)
        self.progress=Gtk.ProgressBar(visible=False);self.append(self.progress)
        footer=Gtk.Box(spacing=8,halign=Gtk.Align.CENTER)
        self.reset=Gtk.Button(label='Reset');self.reset.connect('clicked',lambda _:self.reset_edits());footer.append(self.reset)
        self.preview=Gtk.Button(label='Preview 5 seconds');self.preview.connect('clicked',lambda _:self.render(None,True));footer.append(self.preview)
        self.save=Gtk.Button(label='Save a copy…',css_classes=['suggested-action']);self.save.connect('clicked',self.save_copy);footer.append(self.save)
        self.cancel_button=Gtk.Button(label='Cancel export',visible=False);self.cancel_button.connect('clicked',lambda _:self.cancel.set() if self.cancel else None);footer.append(self.cancel_button)
        self.append(footer);self.set_ready(False)
        categories.connect('notify::active-name',lambda group,_:(stack.set_visible_child_name(group.get_active_name()),viewer.stage.crop_frame.set_visible(viewer.editing and group.get_active_name()=='Crop'),self.queue_preview()))
        categories.set_active_name('Trim')

    def set_ready(self,ready):
        for widget in [self.controls,self.reset,self.preview,self.save]:widget.set_sensitive(ready and not self.running)

    def enter(self):
        stage=self.viewer.stage
        if stage.video_player:stage.video_player.pause();stage.video_player.set_visible(False)
        if self.uri:self.queue_preview();return
        item=self.viewer.source.media_item;window=self.viewer.window
        self.original=Gio.File.new_for_path(item.path).get_uri() if item.path else window.get_video_proxy().register(window.client,item,window.vault,original=True)
        self.uri=self.original
        def ready(info):
            if self.viewer.closing:return
            self.duration=info['duration'];self.original_ratio=info['width']/info['height']
            self.syncing=True
            for widget in [self.start,self.end]:widget.set_range(0,self.duration)
            self.end.set_value(self.duration);self.position.set_range(0,self.duration)
            self.syncing=False;self.set_ready(True);self.queue_preview()
        window.background(lambda:probe(self.uri),ready,lambda message:self.message.set_label(message),images='preview')

    def edits(self):return Edits(self.start.get_value(),self.end.get_value(),self.rotation,self.filter,tuple(self.viewer.stage.crop_frame.bounds))

    def trim_changed(self,*_):
        if self.syncing or not self.duration:return
        start,end=self.start.get_value(),self.end.get_value()
        self.position.set_range(start,max(start+.01,end));self.position.set_value(start);self.queue_preview()

    def aspect_changed(self,dropdown,*_):
        ratio=self.original_ratio if self.rotation%180==0 else 1/self.original_ratio
        self.viewer.stage.crop_frame.set_aspect([None,ratio,1,4/3,16/9][dropdown.get_selected()])

    def rotate(self,angle):
        self.rotation=(self.rotation+angle)%360;self.viewer.stage.crop_frame.reset();self.queue_preview()

    def choose_filter(self,name):self.filter=name;self.queue_preview()

    def queue_preview(self,*_):
        if self.syncing or not self.duration or not self.viewer.editing:return
        if self.debounce:GLib.source_remove(self.debounce)
        self.generation+=1;generation=self.generation
        def load():
            self.debounce=0
            try:edits=self.edits();edits.validate()
            except LibraryError as error:self.message.set_label(str(error));return False
            position=min(edits.end-.01,self.position.get_value())
            self.times.set_label(f'{time_label(edits.start)} → {time_label(edits.end)} · {time_label(edits.end-edits.start)} selected')
            if self.viewer.stage.video_player:self.viewer.stage.video_player.pause();self.viewer.stage.video_player.set_visible(False)
            def work():return decode_image(frame(self.uri,edits,position),1280) if generation==self.generation else None
            def ready(pixels):
                if not pixels or generation!=self.generation or not self.viewer.editing:return
                stage=self.viewer.stage;before=stage.last_rect
                stage.ratio=pixels[0]/pixels[1];stage.set_texture(self.viewer.window.texture_from_pixels(pixels));stage.animate_geometry(before)
                self.message.set_label('Drag the corners to crop.' if self.viewer.editor_categories.get_active_name()=='Crop' else '')
            self.viewer.window.background(work,ready,lambda message:self.message.set_label(message) if generation==self.generation else None,images='preview')
            return False
        self.debounce=GLib.timeout_add(200,load)

    def reset_edits(self):
        self.syncing=True;self.rotation=0;self.filter='Original';self.start.set_value(0);self.end.set_value(self.duration)
        self.position.set_range(0,max(.01,self.duration));self.position.set_value(0)
        self.filter_buttons[0].set_active(True);self.viewer.crop_dropdown.set_selected(0);self.viewer.stage.crop_frame.reset()
        self.syncing=False;self.queue_preview()

    def save_copy(self,*_):
        try:self.edits().validate()
        except LibraryError as error:self.message.set_label(str(error));return
        dialog=Gtk.FileDialog(title='Save edited video',initial_name=Path(self.viewer.source.filename).stem+'-edited.mp4')
        filter=Gtk.FileFilter(name='MP4 video');filter.add_pattern('*.mp4')
        filters=Gio.ListStore.new(Gtk.FileFilter);filters.append(filter);dialog.set_filters(filters);dialog.set_default_filter(filter)
        def chosen(dialog,result):
            try:file=dialog.save_finish(result)
            except GLib.Error:return
            if not file.get_path():self.message.set_label('Choose a folder on this device.');return
            self.render(file.get_path(),False)
        dialog.save(self.viewer.window,None,chosen)

    def render(self,destination,preview=False):
        if self.running or not self.duration:return
        try:edits=self.edits();edits.validate()
        except LibraryError as error:self.message.set_label(str(error));return
        self.generation+=1
        if self.debounce:GLib.source_remove(self.debounce);self.debounce=0
        self.cancel=threading.Event();cancel=self.cancel;self.running=True;self.set_ready(False)
        self.progress.set_fraction(0);self.progress.set_visible(True);self.cancel_button.set_visible(True)
        self.message.set_label('Preparing preview…' if preview else 'Exporting video…')
        destination=destination or str(Path(self.temporary.name)/'preview.mp4')
        def progress(value):
            def update():
                if self.cancel is cancel:self.progress.set_fraction(value)
                return False
            GLib.idle_add(update)
        def finish(message):
            self.running=False;self.progress.set_visible(False);self.cancel_button.set_visible(False);self.set_ready(bool(self.duration));self.message.set_label(message)
        def ready(path):
            finish('Preview · first five seconds of the selection' if preview else 'Video saved. The original is unchanged.')
            if preview and self.viewer.editing and not cancel.is_set():
                stage=self.viewer.stage;bounds=edits.crop
                ratio=self.original_ratio if edits.rotation%180==0 else 1/self.original_ratio
                stage.ratio=ratio*(bounds[2]-bounds[0])/(bounds[3]-bounds[1]);stage.crop_frame.set_visible(False)
                stage.set_video(Gio.File.new_for_path(str(path)).get_uri());stage.video_player.play();stage.queue_allocate()
        self.viewer.window.background(lambda:export(self.uri,destination,edits,cancel,progress,preview,self.viewer.source.media_item.path or None),ready,finish,images='video')

    def leave(self):
        self.generation+=1
        if self.debounce:GLib.source_remove(self.debounce);self.debounce=0
        if self.cancel:self.cancel.set()
        stage=self.viewer.stage;stage.ratio=self.original_ratio;stage.crop_ratio=None
        # Restore viewing playback; editing uses original media through its own URI.
        item=self.viewer.source.media_item
        uri=Gio.File.new_for_path(item.path).get_uri() if item.path else self.viewer.window.get_video_proxy().register(self.viewer.window.client,item,self.viewer.window.vault)
        stage.set_video(uri)
        if not self.viewer.closing:stage.video_player.play()

    def close(self):
        if self.cancel:self.cancel.set()
        if self.original and self.original.startswith('http:'):self.viewer.window.get_video_proxy().unregister(self.original)
        self.temporary.cleanup()
