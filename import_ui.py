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


def start_upload(window,paths=(),image=None):
    if getattr(window,'upload_cancel',None) and not window.upload_cancel.is_set():window.notice('Wait for the current upload to finish.');return
    client=window.client;cancel=threading.Event();window.upload_cancel=cancel
    def progress(name,count,total):
        def show():
            if window.client==client and not cancel.is_set():window.uploads.manual_progress(name,count,total)
            return False
        GLib.idle_add(show)
    def work():
        if cancel.is_set() or window.client is not client:raise InterruptedError()
        if image is not None:
            progress('Pasted image',0,1)
            data=image.save_to_png_bytes().get_data()
            if cancel.is_set() or window.client is not client:raise InterruptedError()
            _,created=upload_bytes(client,data,time.strftime('pasted-image-%Y-%m-%d-%H%M%S.png'),time.time(),cancel)
            return int(created),int(not created)
        items,errors=scan_folders(paths);uploaded=existing=0
        if errors:raise LibraryError(errors[0])
        if not items:raise LibraryError('No supported photos or videos found.')
        for i,item in enumerate(items):
            if cancel.is_set() or window.client!=client:raise InterruptedError()
            progress(item.filename,i,len(items));_,created=upload(client,item.path,cancel)
            uploaded+=int(created);existing+=int(not created)
        return uploaded,existing
    def finish(result):
        cancel.set();window.uploads.manual_finished()
        window.notice(f'{result[0]} uploaded · {result[1]} already saved.');window.upload_finished(client)
    def failed(message):
        cancel.set();window.uploads.manual_finished();window.notice('Upload cancelled.' if 'InterruptedError' in message else message)
    window.background(work,finish,failed)
