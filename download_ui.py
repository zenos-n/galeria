"""Save-location pickers and cancellable original downloads."""
from pathlib import Path
import threading,time
from gi.repository import Adw,GLib,Gtk
from downloads import DownloadCancelled,filename,save_original
from library import LibraryError


def download_items(window,items):
    items=list(items)
    if not items:return
    client=window.client
    def choose(values):
        single=len(values)==1
        picker=Gtk.FileDialog(title='Save original' if single else 'Choose a download folder',
            accept_label='Save' if single else 'Download here')
        if single:picker.set_initial_name(filename(values[0].filename))
        def chosen(picker,result):
            try:file=picker.save_finish(result) if single else picker.select_folder_finish(result)
            except GLib.Error:return
            if not file.get_path():window.notice('Choose a location on this device.');return
            run_download(window,client,values,Path(file.get_path()),single)
        picker.save(window,None,chosen) if single else picker.select_folder(window,None,chosen)
    if len(items)==1 and items[0].metadata.get('timeline_stub'):
        window.background(lambda:client.asset(items[0].id),lambda item:choose([item]))
    else:choose(items)


def run_download(window,client,items,destination,single):
    dialog=Adw.Dialog(title='Downloading',content_width=400)
    body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14,margin_top=24,margin_bottom=24,margin_start=24,margin_end=24)
    label=Gtk.Label(label='Preparing download…',wrap=True,xalign=0);bar=Gtk.ProgressBar()
    cancel=threading.Event();close=Gtk.Button(label='Cancel')
    for widget in (label,bar,close):body.append(widget)
    dialog.set_child(body)
    closed={'value':False};dialog.connect('closed',lambda *_:(closed.update(value=True),cancel.set()))
    close.connect('clicked',lambda _:cancel.set());dialog.present(window)
    def report(index,name,current,total):
        if closed['value']:return False
        label.set_label(f'{index+1} / {len(items)} · {name}')
        bar.set_fraction((index+current/total)/len(items)) if total else bar.pulse()
        return False
    def work():
        saved=[];errors=[];last=0
        for index,item in enumerate(items):
            if cancel.is_set():break
            try:
                if item.metadata.get('timeline_stub'):item=client.asset(item.id)
                target=destination if single else destination/filename(item.filename)
                def progress(current,total):
                    nonlocal last
                    now=time.monotonic()
                    if now-last>.1:last=now;GLib.idle_add(report,index,item.filename,current,total)
                saved.append(save_original(client,item,target,cancel,progress,overwrite=single))
            except DownloadCancelled:break
            except LibraryError as error:errors.append(str(error))
        return saved,errors
    def done(result):
        if closed['value']:return
        saved,errors=result
        dialog.set_title('Download cancelled' if cancel.is_set() else 'Download finished')
        label.set_label(f'{len(saved)} file'+('' if len(saved)==1 else 's')+' saved'+(f' · {len(errors)} failed\n'+errors[0] if errors else ''))
        bar.set_fraction(len(saved)/len(items));close.set_label('Close')
        close.connect('clicked',lambda _:dialog.close())
    window.background(work,done,lambda message:done(([],[message])))
