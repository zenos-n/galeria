"""Copy image pixels and original files using native clipboard formats."""
import hashlib,shutil,threading,tempfile
from pathlib import Path
from gi.repository import Gdk,Gio,GLib,GObject,Gtk
from downloads import filename,save_original
from imaging import decode_image


def copy_media(window,item):
    client=window.client
    locked=item.metadata.get('visibility')=='locked'
    def work():
        nonlocal item,locked
        if client and item.metadata.get('timeline_stub'):
            item=client.asset(item.id);locked=item.metadata.get('visibility')=='locked'
        temporary=None
        if locked and item.kind=='IMAGE':return None,decode_image(client.image_bytes(item,True,window.vault),4096),None
        if item.path:path=Path(item.path)
        elif locked:
            temporary=tempfile.TemporaryDirectory(prefix='galeria-clipboard-')
            path=Path(temporary.name)/filename(item.filename)
            try:save_original(client,item,path,threading.Event())
            except Exception:temporary.cleanup();raise
        else:
            root=client.media_cache().root/'clipboard';root.mkdir(mode=0o700,exist_ok=True)
            key=hashlib.sha256((item.id+str(item.metadata.get('updatedAt',''))).encode()).hexdigest()
            folder=root/key;folder.mkdir(mode=0o700,exist_ok=True);path=folder/filename(item.filename)
            if not path.exists():save_original(client,item,path,threading.Event())
            for old in root.iterdir():
                if old!=folder and old.is_dir():shutil.rmtree(old)
        try:pixels=decode_image(path,4096) if item.kind=='IMAGE' else None
        except (OSError,ValueError):
            pixels=decode_image(client.image_bytes(item,True,window.vault),4096) if client and item.kind=='IMAGE' else None
        return path,pixels,temporary
    def ready(value):
        path,pixels,temporary=value;providers=[]
        if pixels:providers.append(Gdk.ContentProvider.new_for_value(GObject.Value(Gdk.Texture.__gtype__,window.texture_from_pixels(pixels))))
        if path:providers.append(Gdk.ContentProvider.new_for_value(Gdk.FileList.new_from_list([Gio.File.new_for_path(str(path))])))
        provider=Gdk.ContentProvider.new_union(providers)
        if locked:
            clear_locked_clipboard(window);window.locked_clipboard=(provider,temporary)
        copied=window.get_clipboard().set_content(provider)
        window.notice('Media copied.' if copied else 'Could not copy this media. Try again.')
    window.background(work,ready)


def clear_locked_clipboard(window):
    value=getattr(window,'locked_clipboard',None)
    if value:
        provider,temporary=value
        if window.get_clipboard().get_content()==provider:window.get_clipboard().set_content(None)
        if temporary:temporary.cleanup()
        window.locked_clipboard=None


def media_menu(window,widget,item,x,y):
    popover=Gtk.Popover();popover.set_parent(widget)
    rect=Gdk.Rectangle();rect.x=round(x);rect.y=round(y);rect.width=rect.height=1;popover.set_pointing_to(rect)
    body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4,margin_top=6,margin_bottom=6,margin_start=6,margin_end=6)
    for title,callback in [('Copy media',lambda:copy_media(window,item)),('Download…',lambda:window.download_items([item])),('Archive or unarchive',lambda:window.selected_action('archive',[item])),('Move to trash',lambda:window.selected_action('trash',[item]))]:
        button=Gtk.Button(label=title,css_classes=['flat']);button.connect('clicked',lambda _,callback=callback:(popover.popdown(),callback()));body.append(button)
    popover.set_child(body);popover.connect('closed',lambda *_:popover.unparent() if popover.get_parent() else None);popover.popup()
    return popover
