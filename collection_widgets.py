"""Collection-specific native layouts with lazy, recycling-safe cover loading."""
from gi.repository import Adw,Gio,GObject,Gtk
from urllib.parse import quote
from imaging import decode_image
from library import media_from_asset


class Entry(GObject.Object):
    def __init__(self,value):
        super().__init__();self.value=value


class SquareCover(Gtk.Widget):
    def __init__(self,child):
        super().__init__(hexpand=True,css_classes=['collection-cover'])
        self.child=child;child.set_parent(self);self.set_overflow(Gtk.Overflow.HIDDEN)

    def do_get_request_mode(self):return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self,orientation,for_size):
        self.child.measure(orientation,for_size)
        natural=160 if orientation==Gtk.Orientation.HORIZONTAL or for_size<0 else max(160,for_size)
        return natural,natural,-1,-1

    def do_size_allocate(self,width,height,baseline):self.child.allocate(width,height,baseline,None)

    def do_snapshot(self,snapshot):self.snapshot_child(self.child,snapshot)

    def do_unroot(self):
        if self.child.get_parent()==self:self.child.unparent()
        Gtk.Widget.do_unroot(self)

    def do_root(self):
        if self.child.get_parent() is None:self.child.set_parent(self)
        Gtk.Widget.do_root(self)


def cover(window,client,asset_id,picture,alive,person=None):
    key=('person',person['id'],person.get('updatedAt','')) if person else ('asset',asset_id)
    def apply(texture):
        if isinstance(picture,Adw.Avatar):picture.set_custom_image(texture)
        else:picture.set_paintable(texture)
    if key in window.collection_textures:
        if alive():apply(window.collection_textures[key])
        return
    def load():
        if not alive():return None
        if person:
            blob=client.media_cache().fetch('person:'+person['id']+str(person.get('updatedAt','')),
                lambda:client.request('/people/'+quote(person['id'],safe='')+'/thumbnail',binary=True))
        else:
            item=client.collection_cover(asset_id)
            if item is None:return None
            blob=client.image_bytes(item)
        return decode_image(blob)
    def ready(pixels):
        if pixels and alive():
            texture=window.texture_from_pixels(pixels)
            window.collection_textures[key]=texture;window.collection_textures.move_to_end(key)
            while len(window.collection_textures)>256:window.collection_textures.popitem(last=False)
            apply(texture)
    window.background(load,ready,lambda _:None,images=True)


def picture_frame(square=True):
    image=Gtk.Picture(can_shrink=True,content_fit=Gtk.ContentFit.COVER)
    overlay=Gtk.Overlay(child=Gtk.Box())
    overlay.add_overlay(Gtk.Image(icon_name='gallery-image-symbolic',pixel_size=32,css_classes=['dim-label']))
    overlay.add_overlay(image)
    if square:frame=SquareCover(overlay)
    else:
        image.set_content_fit(Gtk.ContentFit.CONTAIN)
        overlay.set_size_request(-1,220);overlay.add_css_class('collection-cover')
        overlay.set_overflow(Gtk.Overflow.HIDDEN);frame=overlay
    return frame,image


def menu_button(window,kind,value,refresh):
    from collections_ui import edit_name
    popover=Gtk.Popover()
    actions=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4,margin_top=6,margin_bottom=6,margin_start=6,margin_end=6)
    def action(title,callback):
        item=Gtk.Button(label=title,css_classes=['flat'])
        item.connect('clicked',lambda _:(popover.popdown(),callback()));actions.append(item)
    if kind in ('albums','sharing'):
        from sharing_ui import share_album
        action('Share album…',lambda:share_album(window,value))
    action('Rename',lambda:edit_name(window,'albums' if kind=='sharing' else kind,value))
    if kind in ('tags','people'):
        title='Hide person' if kind=='people' else 'Delete tag'
        def remove():
            confirm=Adw.AlertDialog(heading=title+'?',body='Photos will remain in your library.')
            confirm.add_response('cancel','Cancel');confirm.add_response('apply',title)
            confirm.set_response_appearance('apply',Adw.ResponseAppearance.DESTRUCTIVE)
            client=window.client
            confirm.connect('response',lambda _,response:window.background(
                lambda:client.request('/people/'+quote(value['id'],safe='') if kind=='people' else '/tags/'+quote(value['id'],safe=''),
                    {'isHidden':True} if kind=='people' else None,method='PUT' if kind=='people' else 'DELETE'),
                lambda _:refresh()) if response=='apply' else None)
            confirm.present(window)
        action(title,remove)
    popover.set_child(actions)
    return Gtk.MenuButton(icon_name='view-more-symbolic',popover=popover,tooltip_text='Collection actions',
                          css_classes=['flat','circular'],valign=Gtk.Align.CENTER)


def grid_card(window,client,kind,value,alive,refresh):
    person=kind=='people'
    body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10,width_request=148 if person else 180,
                 margin_start=8,margin_end=8,margin_top=8,margin_bottom=8)
    name=value.get('name') or 'Unnamed person' if person else value.get('albumName') or 'Untitled album'
    if person:
        portrait=Adw.Avatar(size=120,text=name,show_initials=True,halign=Gtk.Align.CENTER)
        body.append(portrait)
        cover(window,client,None,portrait,alive,person=value)
    else:
        frame,image=picture_frame();body.append(frame)
        if value.get('albumThumbnailAssetId'):cover(window,client,value['albumThumbnailAssetId'],image,alive)
    info=Gtk.Box(spacing=4)
    labels=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4,hexpand=True)
    labels.append(Gtk.Label(label=name,xalign=0,ellipsize=3,tooltip_text=name,css_classes=['heading']))
    if not person:
        count=value.get('assetCount',0)
        labels.append(Gtk.Label(label=f'{count} '+('item' if count==1 else 'items'),xalign=0,css_classes=['dim-label','caption']))
    info.append(labels);info.append(menu_button(window,kind,value,refresh))
    # Keep the action menu separate from the open button for keyboard and pointer access.
    button=Gtk.Button(child=body,css_classes=['flat','collection-open'],hexpand=True)
    if person:button.connect('clicked',lambda _:window.open_collection(name,{'personIds':[value['id']]}))
    else:button.connect('clicked',lambda _:window.activate_album(value['id']))
    outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0)
    outer.append(button);info.set_margin_start(12);info.set_margin_end(8);info.set_margin_bottom(12);outer.append(info)
    return outer


def duplicate_row(window,client,value,alive,refresh):
    assets=[asset for asset in value.get('assets',[]) if asset.get('visibility') not in ('locked','hidden')]
    body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,margin_top=12,margin_bottom=12,
                 margin_start=12,margin_end=12,css_classes=['duplicate-group'])
    header=Gtk.Box(spacing=8)
    header.append(Gtk.Label(label=f'{len(assets)} similar items',xalign=0,hexpand=True,css_classes=['heading']))
    review=Gtk.Button(label='Review all',css_classes=['flat'])
    review.connect('clicked',lambda _:window.open_collection('Review duplicates',items=[media_from_asset(a) for a in assets]))
    header.append(review)
    dismiss=Gtk.Button(icon_name='window-close-symbolic',tooltip_text='Dismiss group',css_classes=['flat','circular'])
    dismiss.connect('clicked',lambda _:window.background(
        lambda:client.request('/duplicates/'+quote(value['duplicateId'],safe=''),method='DELETE'),lambda _:refresh()))
    header.append(dismiss);body.append(header)
    previews=Gtk.Box(spacing=12,homogeneous=True)
    for asset in assets[:3]:
        column=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,hexpand=True)
        frame,image=picture_frame(square=False);column.append(frame)
        cover(window,client,asset['id'],image,alive)
        column.append(Gtk.Label(label=asset.get('originalFileName',asset['id']),xalign=0,ellipsize=3,max_width_chars=16,tooltip_text=asset.get('originalFileName','')))
        exif=asset.get('exifInfo') or {}
        width=asset.get('width') or exif.get('exifImageWidth');height=asset.get('height') or exif.get('exifImageHeight')
        if width and height:column.append(Gtk.Label(label=f'{width} × {height}',xalign=0,css_classes=['dim-label','caption']))
        keep=Gtk.Button(label='Keep this',sensitive=len(assets)>1)
        def keep_one(_,asset=asset):
            others=[item['id'] for item in assets if item['id']!=asset['id']]
            confirm=Adw.AlertDialog(heading='Keep this photo?',body=f'Move the other {len(others)} '+('item' if len(others)==1 else 'items')+' to Trash. You can restore them later.')
            confirm.add_response('cancel','Cancel');confirm.add_response('keep','Keep this')
            confirm.set_response_appearance('keep',Adw.ResponseAppearance.DESTRUCTIVE)
            confirm.connect('response',lambda _,response:window.background(lambda:client.trash_assets(others),lambda _:refresh()) if response=='keep' else None)
            confirm.present(window)
        keep.connect('clicked',keep_one);column.append(keep);previews.append(column)
    body.append(previews)
    return Adw.Clamp(child=body,maximum_size=900,tightening_threshold=600)


def collection_grid(window,client,kind,data,generation,refresh):
    model=Gio.ListStore.new(Entry)
    model.splice(0,0,[Entry(value) for value in data])
    factory=Gtk.SignalListItemFactory()
    def bind(_factory,item):
        marker=object();item.binding_marker=marker
        alive=lambda:window.current_page==kind and window.search_generation==generation and getattr(item,'binding_marker',None) is marker
        value=item.get_item().value
        widget=duplicate_row(window,client,value,alive,refresh) if kind=='duplicates' else grid_card(window,client,kind,value,alive,refresh)
        item.set_child(widget)
    def unbind(_factory,item):item.binding_marker=None;item.set_child(None)
    factory.connect('bind',bind);factory.connect('unbind',unbind)
    selection=Gtk.NoSelection(model=model)
    if kind=='duplicates':view=Gtk.ListView(model=selection,factory=factory,css_classes=['collection-grid'])
    else:view=Gtk.GridView(model=selection,factory=factory,min_columns=1,max_columns=12,css_classes=['collection-grid'])
    view.set_margin_start(12);view.set_margin_end(12);view.set_margin_top(12);view.set_margin_bottom(12)
    return view


def tag_list(window,data,refresh):
    listing=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,css_classes=['boxed-list'],valign=Gtk.Align.START)
    for value in data:
        name=value.get('value') or value.get('name','Tag')
        row=Adw.ActionRow(title=name,use_markup=False,activatable=True)
        row.add_prefix(Gtk.Image(icon_name='gallery-tag-symbolic'))
        row.add_suffix(menu_button(window,'tags',value,refresh))
        row.connect('activated',lambda _,value=value,name=name:window.open_collection(name,{'tagIds':[value['id']]}))
        listing.append(row)
    return Adw.Clamp(child=listing,maximum_size=760,tightening_threshold=500,margin_start=24,margin_end=24,margin_top=12,margin_bottom=24)


def location_list(window,data):
    listing=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,css_classes=['boxed-list'],valign=Gtk.Align.START)
    for value in data:
        row=Adw.ActionRow(title=value['name'],use_markup=False,activatable=True)
        row.add_prefix(Gtk.Image(icon_name='find-location-symbolic'))
        row.connect('activated',lambda _,value=value:window.open_collection('Location',{'id':value['id']}))
        listing.append(row)
    return Adw.Clamp(child=listing,maximum_size=760,margin_start=24,margin_end=24,margin_top=12,margin_bottom=24)
