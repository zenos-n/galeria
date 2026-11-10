"""Native file/folder import review and real streamed Immich uploads."""
import threading,time
from pathlib import Path
from gi.repository import Adw,GLib,Gtk
from library import LibraryError,scan_folders
from upload_media import upload,upload_bytes


def import_sheet(window,files):
    if not window.client:window.notice('Connect Immich to upload files.');window.login();return
    paths=[file.get_path() for file in files]
    if not paths or not all(paths):window.notice('Drop files or folders from this device.');return
    dialog=Adw.Dialog(title='Upload to Immich',content_width=460,content_height=420)
    toolbar=Adw.ToolbarView();toolbar.add_top_bar(Adw.HeaderBar())
    page=Adw.PreferencesPage(description='Photos and videos upload to your library. Originals stay on this device; identical files are skipped.')
    group=Adw.PreferencesGroup(title=f'{len(paths)} items selected')
    for path in paths[:5]:group.add(Adw.ActionRow(title=Path(path).name,use_markup=False))
    if len(paths)>5:group.add(Adw.ActionRow(title=f'And {len(paths)-5} more'))
    page.add(group);actions=Adw.PreferencesGroup();button=Gtk.Button(label='Upload',css_classes=['suggested-action'],margin_top=12,margin_bottom=12)
    def begin(_):dialog.close();start_upload(window,paths)
    button.connect('clicked',begin);actions.add(button);page.add(actions);toolbar.set_content(page);dialog.set_child(toolbar)
    window.dialog=dialog;dialog.present(window)


def paste_image(window):
    if not window.client:window.notice('Connect Immich to upload an image.');return
    client=window.client;generation=window.data_generation
    def ready(clipboard,result):
        if window.data_stopped or window.client is not client or window.data_generation!=generation:return
        try:image=clipboard.read_texture_finish(result)
        except GLib.Error:window.notice('The clipboard does not contain an image.');return
        if image is None:window.notice('The clipboard does not contain an image.');return
        start_upload(window,image=image)
    window.get_clipboard().read_texture_async(None,ready)


def start_upload(window,paths=(),image=None,retry_entry=None):
    if getattr(window,'upload_cancel',None) and not window.upload_cancel.is_set():window.notice('Wait for the current upload to finish.');return
    from datetime import datetime
    from library import MediaItem
    from pending_uploads import manager,ui_call
    uploads=manager(window)
    if not uploads:return
    client=window.client;cancel=threading.Event();window.upload_cancel=cancel
    entries=[]
    def image_transfer(cancel,progress):
        data=image.save_to_png_bytes().get_data()
        if cancel.is_set() or window.client is not client:raise InterruptedError()
        return upload_bytes(client,data,source.filename,source.created.timestamp(),cancel,progress=progress)
    if image is not None:
        source=MediaItem('',time.strftime('pasted-image-%Y-%m-%d-%H%M%S.png'),datetime.now(),image.get_width()/max(1,image.get_height()))
        entries.append(uploads.add(source,image,image_transfer));uploads.prepare();uploads.publish()
    elif retry_entry:
        retry_entry['item'].metadata.update(upload_state='uploading',upload_progress=0.)
        entries.append(retry_entry);uploads.prepare();uploads.publish()
    def progress(name,count,total):
        def show():
            if window.client==client and not cancel.is_set():window.uploads.manual_progress(name,count,total)
            return False
        GLib.idle_add(show)
    def work():
        if cancel.is_set() or window.client is not client:raise InterruptedError()
        if not entries:
            items,errors=scan_folders(paths)
            if errors:raise LibraryError(errors[0])
            if not items:raise LibraryError('No supported photos or videos found.')
            def queue():
                for item in items:
                    transfer=lambda cancel,progress,item=item:upload(client,item.path,cancel,progress=progress)
                    entries.append(uploads.add(item,transfer=transfer))
                uploads.prepare();uploads.publish();return True
            ui_call(window,queue,cancel)
        uploaded=existing=0
        for i,entry in enumerate(entries):
            if cancel.is_set() or window.client is not client:raise InterruptedError()
            progress(entry['source'].filename,i,len(entries))
            asset,created=entry['transfer'](cancel,lambda current,total,entry=entry:uploads.progress(entry,current,total))
            ui_call(window,lambda entry=entry,asset=asset:uploads.complete(entry,asset),cancel)
            uploaded+=int(created);existing+=int(not created)
        return uploaded,existing
    def finish(result):
        cancel.set();window.uploads.manual_finished()
        window.notice(f'{result[0]} uploaded · {result[1]} already saved.');window.upload_finished(client)
    def failed(message):
        cancel.set();window.uploads.manual_finished()
        message='Upload cancelled.' if 'InterruptedError' in message else message
        for entry in entries:uploads.fail(entry,message)
        window.notice(message)
    window.background(work,finish,failed)
