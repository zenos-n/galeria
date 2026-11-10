"""Copy image pixels without file-path clipboard formats."""
import shutil
from gi.repository import Gdk,GObject,Gtk
from imaging import decode_image
from library import LibraryError


def copy_media(window,item):
    if item.kind=='VIDEO':return
    client=window.client;locked=item.metadata.get('visibility')=='locked'
    def work():
        nonlocal item,locked
        if client and item.metadata.get('timeline_stub'):
            item=client.asset(item.id);locked=item.metadata.get('visibility')=='locked'
        if item.path:return decode_image(item.path,4096)
        if locked:return decode_image(client.image_bytes(item,True,window.vault),4096)
        shutil.rmtree(client.media_cache().root/'clipboard',ignore_errors=True)
        try:
            with client.open_original(item) as source:return decode_image(source.read(),4096)
        except (OSError,ValueError,LibraryError):return decode_image(client.image_bytes(item,True,window.vault),4096)
    def ready(pixels):
        provider=Gdk.ContentProvider.new_for_value(GObject.Value(Gdk.Texture.__gtype__,window.texture_from_pixels(pixels)))
        if locked:clear_locked_clipboard(window);window.locked_clipboard=(provider,None)
        copied=window.get_clipboard().set_content(provider)
        window.notice('Image copied.' if copied else 'Could not copy this image. Try again.')
    window.background(work,ready)


def clear_locked_clipboard(window):
    value=getattr(window,'locked_clipboard',None)
    if value:
        provider,temporary=value
        if window.get_clipboard().get_content()==provider:window.get_clipboard().set_content(None)
        if temporary:temporary.cleanup()
        window.locked_clipboard=None


def media_menu(window,widget,item,x,y,device_file=False):
    popover=Gtk.Popover();popover.set_parent(widget)
    rect=Gdk.Rectangle();rect.x=round(x);rect.y=round(y);rect.width=rect.height=1;popover.set_pointing_to(rect)
    body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4,margin_top=6,margin_bottom=6,margin_start=6,margin_end=6)
    from sharing_ui import share_media
    actions=([('Copy media',lambda:copy_media(window,item))] if item.kind!='VIDEO' else [])
    actions.append(('Download…',lambda:window.download_items([item])))
    if not device_file:
        actions += [('Share…',lambda:share_media(window,[item])),('Archive or unarchive',lambda:window.selected_action('archive',[item])),('Move to locked folder',lambda:window.move_selected_to_locked([item]))]
    actions.append(('Move to trash',lambda:window.selected_action('trash',[item])))
    for title,callback in actions:
        button=Gtk.Button(label=title,css_classes=['flat']);button.connect('clicked',lambda _,callback=callback:(popover.popdown(),callback()));body.append(button)
    popover.set_child(body);popover.connect('closed',lambda *_:popover.unparent() if popover.get_parent() else None);popover.popup()
    return popover
