"""Photo edit state, coalesced previews and explicit save-copy export."""
import copy,threading
from io import BytesIO
from pathlib import Path
from PIL import Image
from gi.repository import Gio,GLib,Gtk
from library import LibraryError
from photo_edit import ADJUSTMENTS,POSITIVE,render
from photo_markup import Markup
from edit_history import History


class PhotoEditor:
    def __init__(self,viewer):
        self.viewer=viewer;self.stage=viewer.stage;self.original=None
        self.values={name:0 for name in ADJUSTMENTS};self.selected='Brightness'
        self.straighten=0;self.comparing=False;self.syncing=False
        self.generation=0;self.debounce=0;self.running=False;self.closed=False
        self.markup=Markup(self.markup_changed,self.notice);self.markup.set_can_target(False)
        self.stage.picture.add_overlay(self.markup)
        self.history=History(self.snapshot());self.history_timer=0;self.restoring=False;self.upload_cancel=threading.Event();self.saving=False;self.save_finished=None
        self.stage.crop_frame.changed=self.remember

    def snapshot(self):
        return (dict(self.values),copy.deepcopy([stroke for stroke in self.markup.strokes if stroke['tool']!='Text' or stroke.get('text')]),self.stage.rotation,self.stage.flipped,self.straighten,tuple(self.stage.crop_frame.bounds),self.stage.crop_frame.aspect,getattr(self.viewer,'crop_dropdown',None).get_selected() if hasattr(self.viewer,'crop_dropdown') else 1)

    def remember(self):
        if self.restoring or self.closed:return
        if self.history_timer:GLib.source_remove(self.history_timer)
        def commit():
            self.history_timer=0;self.history.record(self.snapshot());self.history_buttons();return False
        self.history_timer=GLib.timeout_add(300,commit)
        if hasattr(self,'undo'):self.undo.set_sensitive(True)

    def history_buttons(self):
        if hasattr(self,'undo'):self.undo.set_sensitive(len(self.history.past)>1)
        if hasattr(self,'redo'):self.redo.set_sensitive(bool(self.history.future))

    def undo_edits(self,redo=False):
        if self.history_timer:GLib.source_remove(self.history_timer);self.history_timer=0
        state=(self.history.redo if redo else self.history.undo)(self.snapshot())
        if state is None:return
        self.restore(state)

    def restore(self,state):
        self.restoring=True;self.markup.entry.set_visible(False);self.markup.selected=None
        self.values,self.markup.strokes,self.stage.rotation,self.stage.flipped,self.straighten,bounds,aspect,choice=copy.deepcopy(state)
        self.viewer.crop_dropdown.set_selected(choice);self.stage.crop_frame.bounds=bounds;self.stage.crop_frame.aspect=aspect
        self.straighten_slider.set_value(self.straighten);self.select(self.selected);self.markup.redraw();self.queue(0)
        self.restoring=False;self.history_buttons()

    def dirty(self):return self.history.dirty(self.snapshot())

    def discard_changes(self):
        self.restore(self.history.saved);self.history=History(self.snapshot());self.history_buttons()

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
        if self.closed:return
        if not self.restoring:
            if self.history_timer:GLib.source_remove(self.history_timer);self.history_timer=0
            self.history.record(self.snapshot());self.history_buttons()
        if self.viewer.editor_categories.get_active_name()!='Markup':self.queue(0)

    def category_changed(self):
        self.markup.finish_text()
        self.markup.set_can_target(False);self.queue(0)

    def queue(self,delay=70):
        if self.closed:return
        if self.viewer.editing:self.remember()
        self.generation+=1
        if self.debounce:GLib.source_remove(self.debounce);self.debounce=0
        if self.original and not self.running:self.debounce=GLib.timeout_add(delay,self.start)

    def start(self):
        self.debounce=0
        if self.closed or not self.original or self.running:return False
        generation=self.generation;self.running=True
        pixels=self.original;values={} if self.comparing else dict(self.values)
        drawing=self.viewer.editing and not self.comparing
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
            self.markup.set_visible(drawing);self.markup.set_can_target(drawing and self.viewer.editor_categories.get_active_name()=='Markup')
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
            for stroke in self.markup.strokes:
                stroke['points']=[(1-y,x) for x,y in stroke['points']]
                if stroke['tool']=='Text':stroke['rotation']=stroke.get('rotation',0)+90
            a,b,c,d=self.stage.crop_frame.bounds;self.stage.crop_frame.bounds=(1-d,a,1-b,c)
        self.stage.rotation=(self.stage.rotation+angle)%360
        if self.viewer.crop_dropdown.get_selected()==1:self.stage.crop_frame.aspect=self.aspect()
        self.markup.redraw();self.queue(0)

    def flip(self):
        for stroke in self.markup.strokes:stroke['points']=[(1-x,y) for x,y in stroke['points']]
        a,b,c,d=self.stage.crop_frame.bounds;self.stage.crop_frame.bounds=(1-c,b,1-a,d)
        self.stage.flipped=not self.stage.flipped;self.markup.redraw();self.queue(0)

    def reset(self):
        self.values={name:0 for name in ADJUSTMENTS};self.straighten=0
        self.compare_button.set_active(False);self.notice('')
        self.stage.rotation=0;self.stage.flipped=False;self.stage.crop_ratio=None
        self.stage.crop_frame.reset();self.viewer.crop_dropdown.set_selected(1)
        self.straighten_slider.set_value(0);self.markup.clear();self.select(self.selected);self.queue(0)

    def save_copy(self,finished=None):
        if self.saving:
            if finished:self.save_finished=finished
            return
        if finished:self.save_finished=finished
        if self.original is None:self.notice('Wait for the photo to load.');self.finish_save(False);return
        window=self.viewer.window;client=window.client;item=self.viewer.source.media_item
        if not client:self.notice('Connect Immich to save an edited copy.');self.finish_save(False);return
        self.markup.finish_text();state=self.snapshot();values,strokes,rotation,flipped,angle,crop,_,_=state
        self.saving=True;self.save_button.set_sensitive(False);self.notice('Saving a copy to Immich…')
        cancel=self.upload_cancel
        def work():
            from upload_media import upload_bytes
            if not item.path:client.check_original_access(item)
            preview=False
            try:
                with open(item.path,'rb') if item.path else client.open_original(item) as source:
                    with Image.open(source) as image:output=render(image,values,strokes,rotation,flipped,angle,crop)
            except (OSError,ValueError):
                if item.path:raise
                with Image.open(BytesIO(client.image_bytes(item,True,window.vault))) as image:output=render(image,values,strokes,rotation,flipped,angle,crop)
                preview=True
            stream=BytesIO();output.save(stream,format='PNG')
            if not item.path:client.check_original_access(item)
            if window.client!=client or cancel.is_set():raise InterruptedError()
            _,created=upload_bytes(client,stream.getvalue(),Path(item.filename).stem+'-edited.png',item.created.timestamp(),cancel,
                visibility='locked' if item.metadata.get('visibility')=='locked' else None)
            return preview,created
        def done(value):
            window.upload_finished(client)
            if not self.closed:
                self.save_button.set_sensitive(True);preview,created=value
                self.notice(('Copy saved to Immich' if created else 'This copy is already saved on Immich')+(' at server preview resolution.' if preview else '.'))
                self.history.mark_saved(state)
            self.finish_save(True)
        def failed(message):
            if not self.closed:self.save_button.set_sensitive(True);self.notice(message)
            self.finish_save(False)
        window.background(work,done,failed,images='preview')

    def finish_save(self,success):
        self.saving=False;callback=self.save_finished;self.save_finished=None
        if callback:callback(success)

    def close(self):
        self.closed=True;self.generation+=1;self.upload_cancel.set()
        if self.history_timer:GLib.source_remove(self.history_timer);self.history_timer=0
        if self.debounce:GLib.source_remove(self.debounce);self.debounce=0
        if self.markup.get_parent()==self.stage.picture:self.stage.picture.remove_overlay(self.markup)
        self.markup.entry.set_visible(False);self.markup.strokes.clear();self.markup.cache.clear();self.history.past.clear();self.history.future.clear();self.history.saved=None
        self.original=None
