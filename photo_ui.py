"""Photo edit state, coalesced previews and explicit save-copy export."""
import copy,os,tempfile
from io import BytesIO
from pathlib import Path
from PIL import Image
from gi.repository import Gio,GLib,Gtk
from library import LibraryError
from photo_edit import ADJUSTMENTS,POSITIVE,render
from photo_markup import Markup


class PhotoEditor:
    def __init__(self,viewer):
        self.viewer=viewer;self.stage=viewer.stage;self.original=None
        self.values={name:0 for name in ADJUSTMENTS};self.selected='Brightness'
        self.straighten=0;self.comparing=False;self.syncing=False
        self.generation=0;self.debounce=0;self.running=False;self.closed=False
        self.markup=Markup(self.markup_changed,self.notice);self.markup.set_can_target(False)
        self.stage.picture.add_overlay(self.markup)

    def notice(self,message):
        was_visible=self.viewer.tool_message.get_visible()
        self.viewer.tool_message.set_label(message);self.viewer.tool_message.set_visible(bool(message))
        if was_visible!=bool(message):self.viewer.sync_editor_inset()

    def set_source(self,pixels):
        if self.closed:return
        self.original=pixels;self.stage.set_texture(self.viewer.window.texture_from_pixels(pixels))
        self.stage.render_ratio=pixels[0]/pixels[1]
        self.stage.queue_allocate()
        self.save_button.set_sensitive(True)
        if self.viewer.editing or any(self.values.values()) or self.markup.strokes:self.queue(0)

    def select(self,name):
        self.selected=name
        if not hasattr(self,'slider'):return
        self.syncing=True
        self.slider.set_range(0 if name in POSITIVE else -100,100)
        self.slider.clear_marks();self.slider.add_mark(0,Gtk.PositionType.BOTTOM,None)
        self.slider.set_value(self.values[name]);self.syncing=False

    def changed(self,slider):
        if self.syncing:return
        self.values[self.selected]=slider.get_value();self.queue()

    def markup_changed(self):
        if hasattr(self,'undo'):self.undo.set_sensitive(bool(self.markup.strokes))
        if self.viewer.editor_categories.get_active_name()!='Markup':self.queue(0)

    def category_changed(self):
        self.markup.set_can_target(False);self.queue(0)

    def queue(self,delay=70):
        if self.closed:return
        self.generation+=1
        if self.debounce:GLib.source_remove(self.debounce);self.debounce=0
        if self.original and not self.running:self.debounce=GLib.timeout_add(delay,self.start)

    def start(self):
        self.debounce=0
        if self.closed or not self.original or self.running:return False
        generation=self.generation;self.running=True
        pixels=self.original;values={} if self.comparing else dict(self.values)
        drawing=self.viewer.editing and self.viewer.editor_categories.get_active_name()=='Markup' and not self.comparing
        strokes=[] if drawing or self.comparing else copy.deepcopy(self.markup.strokes)
        rotation=self.stage.rotation;flipped=self.stage.flipped;angle=self.straighten
        crop=None if self.viewer.editing else self.stage.crop_frame.bounds
        def work():
            image=render(Image.frombytes('RGBA',pixels[:2],pixels[2]),values,strokes,rotation,flipped,angle,crop,1200)
            return image.width,image.height,image.tobytes()
        def ready(value):
            self.running=False
            if self.closed or self.viewer.stage!=self.stage:return
            if generation!=self.generation:self.queue(0);return
            previous=self.stage.last_rect;ratio=value[0]/value[1];changed=ratio!=self.stage.render_ratio
            self.stage.render_ratio=ratio;self.stage.set_texture(self.viewer.window.texture_from_pixels(value))
            self.stage.surface.set_opacity(0)
            self.markup.set_visible(drawing);self.markup.set_can_target(drawing)
            self.stage.queue_allocate()
            if changed:self.stage.animate_geometry(previous)
        def failed(message):
            self.running=False
            if not self.closed:
                if generation!=self.generation:self.queue(0)
                else:self.notice(message)
        self.viewer.window.background(work,ready,failed,images='preview')
        return False

    def compare(self,active):self.comparing=active;self.queue(0)

    def aspect(self):
        ratio=self.original[0]/self.original[1] if self.original else self.stage.ratio
        return 1/ratio if self.stage.rotation%180 else ratio

    def rotate(self,angle):
        for _ in range((angle//90)%4):
            for stroke in self.markup.strokes:stroke['points']=[(1-y,x) for x,y in stroke['points']]
            a,b,c,d=self.stage.crop_frame.bounds;self.stage.crop_frame.bounds=(1-d,a,1-b,c)
        self.stage.rotation=(self.stage.rotation+angle)%360
        if self.viewer.crop_dropdown.get_selected()==1:self.stage.crop_frame.aspect=self.aspect()
        self.markup.queue_draw();self.queue(0)

    def flip(self):
        for stroke in self.markup.strokes:stroke['points']=[(1-x,y) for x,y in stroke['points']]
        a,b,c,d=self.stage.crop_frame.bounds;self.stage.crop_frame.bounds=(1-c,b,1-a,d)
        self.stage.flipped=not self.stage.flipped;self.markup.queue_draw();self.queue(0)

    def reset(self):
        self.values={name:0 for name in ADJUSTMENTS};self.straighten=0
        self.compare_button.set_active(False);self.notice('')
        self.stage.rotation=0;self.stage.flipped=False;self.stage.crop_ratio=None
        self.stage.crop_frame.reset();self.viewer.crop_dropdown.set_selected(1)
        self.straighten_slider.set_value(0);self.markup.clear();self.select(self.selected);self.queue(0)

    def save_copy(self):
        if self.original is None:self.notice('Wait for the photo to load.');return
        item=self.viewer.source.media_item;client=self.viewer.window.client
        picker=Gtk.FileDialog(title='Save edited photo',accept_label='Save copy')
        picker.set_initial_name(Path(item.filename).stem+'-edited.png')
        filter=Gtk.FileFilter(name='PNG image');filter.add_pattern('*.png')
        filters=Gio.ListStore.new(Gtk.FileFilter);filters.append(filter);picker.set_filters(filters);picker.set_default_filter(filter)
        def chosen(picker,result):
            try:file=picker.save_finish(result)
            except GLib.Error:return
            if not file.get_path():self.notice('Choose a location on this device.');return
            target=Path(file.get_path())
            if target.suffix.lower()!='.png':self.notice('Use a .png filename for the edited copy.');return
            if item.path and target.resolve()==Path(item.path).resolve():self.notice('Choose a different file to preserve the original.');return
            values=dict(self.values);strokes=copy.deepcopy(self.markup.strokes)
            rotation=self.stage.rotation;flipped=self.stage.flipped;angle=self.straighten;crop=self.stage.crop_frame.bounds
            self.save_button.set_sensitive(False);self.notice('Saving edited copy…')
            def work():
                if not item.path:client.check_original_access(item)
                preview=False
                try:
                    with open(item.path,'rb') if item.path else client.open_original(item) as source:
                        with Image.open(source) as image:output=render(image,values,strokes,rotation,flipped,angle,crop)
                except (OSError,ValueError):
                    if item.path:raise
                    with Image.open(BytesIO(client.image_bytes(item,True,self.viewer.window.vault))) as image:output=render(image,values,strokes,rotation,flipped,angle,crop)
                    preview=True
                fd,name=tempfile.mkstemp(prefix='.galeria-edit-',dir=target.parent)
                try:
                    with os.fdopen(fd,'wb') as stream:output.save(stream,format='PNG');stream.flush();os.fsync(stream.fileno())
                    if not item.path:client.check_original_access(item)
                    if item.path and target.resolve()==Path(item.path).resolve():raise LibraryError('Choose a different file to preserve the original.')
                    os.replace(name,target)
                finally:Path(name).unlink(missing_ok=True)
                return preview
            def done(preview):
                if not self.closed:self.save_button.set_sensitive(True);self.notice('Edited copy saved at server preview resolution.' if preview else 'Edited copy saved.')
            def failed(message):
                if not self.closed:self.save_button.set_sensitive(True);self.notice(message)
            self.viewer.window.background(work,done,failed,images='preview')
        picker.save(self.viewer.window,None,chosen)

    def close(self):
        self.closed=True;self.generation+=1
        if self.debounce:GLib.source_remove(self.debounce);self.debounce=0
        if self.markup.get_parent()==self.stage.picture:self.stage.picture.remove_overlay(self.markup)
        self.original=None
