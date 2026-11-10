"""Transient upload tiles; server metadata adopts them without losing pixels."""
from dataclasses import replace
from datetime import datetime
import threading,time,uuid
from gi.repository import GLib
from library import MediaItem


def manager(window,create=True):
    value=getattr(window,'upload_previews',None)
    if value and not value.current():window.upload_previews=None;value=None
    if value is None and create and window.client:
        value=PendingUploads(window);window.upload_previews=value
    return value


def ui_call(window,callback,cancel):
    event=threading.Event();result=[];errors=[];generation=window.data_generation
    def run():
        try:
            if not cancel.is_set() and not window.data_stopped and window.data_generation==generation:result.append(callback())
        except Exception as error:errors.append(error)
        finally:event.set()
        return False
    GLib.idle_add(run)
    while not event.wait(.05):
        if cancel.is_set() or window.data_stopped or window.data_generation!=generation:raise InterruptedError()
    if errors:raise errors[0]
    if not result:raise InterruptedError()
    return result[0]


class PendingUploads:
    def __init__(self,window):
        self.window=window;self.client=window.client;self.generation=window.data_generation;self.entries={};self.sync_seen={}
    def current(self):return not self.window.data_stopped and self.window.client is self.client and self.window.data_generation==self.generation
    def active(self):return self.current() and any(entry['item'].metadata.get('upload_state')=='uploading' for entry in self.entries.values())
    def add(self,source,texture=None,transfer=None,key=None):
        key=key or 'upload:'+uuid.uuid4().hex
        item=replace(source,id=key,created=datetime.now(),metadata={'optimistic_upload':True,'upload_key':key,'upload_state':'uploading','upload_progress':0.,'placeholder':True,'timeline_slot':True,'visibility':source.metadata.get('visibility','timeline')})
        entry={'item':item,'source':source,'texture':texture,'transfer':transfer,'asset':None,'last_progress':0.}
        self.entries[key]=entry
        if texture:self.window.texture_cache[self.window.texture_key(item)]=texture
        return entry
    def prepare(self):
        w=self.window
        if w.viewer:
            if w.viewer.editing:return
            w.viewer.close()
        if w.searching:w.set_searching(False)
        w.bucket_scope={}
        if w.current_page!='library':
            row=w.rows['library'];w.navigate(row.get_parent(),row)
        if w.switcher.get_active_name()!='all':w.switcher.set_active_name('all')
        w.scroll_input_serial+=1;w.scroller.get_vadjustment().set_value(0)
    def publish(self):
        if not self.current():return
        w=self.window
        if w.viewer and not (w.viewer.editing or w.viewer.device_file):w.pending_media=(w.media_items,True)
        else:w.set_library_items(w.media_items,append=True,reflow=True)
    def merge(self,items):
        values={item.id:item for item in items if not item.metadata.get('optimistic_upload')}
        for key,entry in list(self.entries.items()):
            item=entry['item'];asset=entry['asset']
            if asset in values:
                texture=entry['texture'] or self.window.texture_cache.get(self.window.texture_key(item))
                if texture:self.window.texture_cache[self.window.texture_key(values[asset])]=texture
                self.window.texture_cache.pop((key,''),None);del self.entries[key];continue
            visible=self.window.current_page=='locked' if item.metadata.get('visibility')=='locked' else self.window.current_page in ('library','photos')
            if visible:values[item.id]=item
        return list(values.values())
    def progress(self,entry,current,total):
        now=time.monotonic()
        if now-entry['last_progress']<.05 and current<total:return
        entry['last_progress']=now
        def show():
            if not self.current() or self.entries.get(entry['item'].metadata['upload_key']) is not entry:return False
            entry['item'].metadata['upload_progress']=min(.98,current/max(1,total))
            for tile in self.window.mosaic.active_widgets & self.window.mosaic.tile_set:
                if tile.media_item is entry['item'] and getattr(tile,'upload_ring',None):tile.upload_ring.queue_draw()
            return False
        GLib.idle_add(show)
    def complete(self,entry,asset):
        if not self.current():return
        old=entry['item'];texture=entry['texture'] or self.window.texture_cache.get(self.window.texture_key(old))
        entry['item']=replace(old,id=asset,path='',created=entry['source'].created,metadata={**old.metadata,'placeholder':False,'timeline_stub':True,'upload_state':'complete','upload_progress':1.})
        entry['asset']=asset;entry['texture']=texture;entry['transfer']=None
        if texture:self.window.texture_cache[self.window.texture_key(entry['item'])]=texture
        self.publish()
    def fail(self,entry,message):
        if not self.current() or entry['asset']:return
        entry['item'].metadata.update(upload_state='failed',upload_error=message);self.publish()
    def retry(self,key):
        if not self.current():return
        entry=self.entries.get(key)
        if entry and entry.get('sync'):
            self.window.request_folder_sync();return
        if entry and entry['transfer']:
            from import_ui import start_upload
            start_upload(self.window,retry_entry=entry)


def sync_previews(window,status):
    client=window.client
    if not client:return
    value=status.get('accounts',{}).get(client.identity,{})
    rows=[*value.get('folders',[]),value.get('progress',{})]
    uploads=manager(window,False)
    for row in rows:
        for transfer in row.get('transfers',[]):
            key='sync:'+str(transfer.get('key',''));state=transfer.get('state')
            if not transfer.get('path') or state not in ('uploading','complete','failed'):continue
            fresh=transfer.get('started',0)>=window.upload_started
            if uploads is None:
                if state!='uploading' and not fresh:continue
                uploads=manager(window)
            entry=uploads.entries.get(key)
            if entry is None:
                if state!='uploading' and not fresh or key in uploads.sync_seen:continue
                source=MediaItem(key,transfer['filename'],datetime.fromtimestamp(transfer['created']),kind=transfer.get('kind','IMAGE'),path=transfer['path'])
                entry=uploads.add(source,key=key);entry['sync']=True;uploads.sync_seen[key]=True
                if len(uploads.sync_seen)>1024:uploads.sync_seen.pop(next(iter(uploads.sync_seen)))
                uploads.publish()
            if state=='uploading' and entry['item'].metadata.get('upload_state')=='failed':
                entry['item'].metadata.update(upload_state='uploading',upload_progress=0.);uploads.publish()
            uploads.progress(entry,transfer.get('sent',0),transfer.get('size',1))
            if state=='complete' and transfer.get('asset') and not entry['asset']:uploads.complete(entry,transfer['asset'])
            elif state=='failed' and entry['item'].metadata.get('upload_state')!='failed':
                entry['transfer']=None;uploads.fail(entry,transfer.get('error','Upload failed.'))
