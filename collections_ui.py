"""Real collection overviews and utility results."""
from datetime import datetime
from gi.repository import Adw, Gtk, GLib
from library import MediaItem,media_from_asset
from imaging import decode_image
from urllib.parse import quote


def edit_name(window,kind,value=None):
    dialog=Adw.AlertDialog(heading=('Rename ' if value else 'Create ')+('tag' if kind=='tags' else 'person' if kind=='people' else 'album'))
    entry=Adw.EntryRow(title='Name',text=(value or {}).get('name') or (value or {}).get('albumName',''))
    group=Adw.PreferencesGroup();group.add(entry);dialog.set_extra_child(group)
    dialog.add_response('cancel','Cancel');dialog.add_response('save','Save')
    dialog.set_response_appearance('save',Adw.ResponseAppearance.SUGGESTED)
    def save(_,response):
        if response!='save':return
        name=entry.get_text().strip()
        if not name:window.notice('Enter a name.');return
        path='/tags' if kind=='tags' else '/people' if kind=='people' else '/albums'
        fields={'albumName' if kind=='albums' else 'name':name}
        if value:path+='/'+quote(value['id'],safe='')
        method='PUT' if value and kind!='albums' else 'PATCH' if value else 'POST'
        def done(_):
            window.client.media_cache().remove('albums')
            window.background(window.client.albums,window.album_tree.set_albums)
            collection_view(window,kind)
        window.background(lambda:window.client.request(path,fields,method=method),done)
    dialog.connect('response',save);dialog.present(window)


def collection_view(window,kind):
    if window.current_page!=kind:return
    window.busy_library('Loading '+window.page_titles.get(kind,kind).lower()+'…')
    generation=window.search_generation
    client=window.client
    if not client:
        window.status.set_title('Connect Immich to use this view')
        window.status.set_description('Your local folders remain available in Library.')
        return
    def loaded(data):
        if window.current_page!=kind or generation!=window.search_generation:return
        query=window.search.entry.get_text().strip().casefold()
        if query:data=[value for value in data if query in str(value.get('albumName') or value.get('value') or value.get('name') or '').casefold()]
        if kind=='map':
            data=[dict(marker,name=f"{marker.get('lat',marker.get('latitude',0)):.4f}, {marker.get('lon',marker.get('longitude',0)):.4f}") for marker in data]
        flow=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,min_children_per_line=1,max_children_per_line=20,
                          row_spacing=18,column_spacing=18,margin_start=24,margin_end=24,margin_top=24,margin_bottom=24,
                          homogeneous=True,valign=Gtk.Align.START)
        for value in data:
            body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,width_request=160)
            picture=Gtk.Picture(can_shrink=True,content_fit=Gtk.ContentFit.COVER)
            cover_box=Gtk.Overlay(child=Gtk.Box(width_request=170,height_request=130),css_classes=['collection-cover'])
            cover_box.add_overlay(Gtk.Image(icon_name='gallery-tag-symbolic' if kind=='tags' else 'gallery-image-symbolic',pixel_size=32))
            cover_box.add_overlay(picture)
            body.append(cover_box)
            if kind in ('albums','sharing','pinned'):
                name=value.get('albumName') or 'Untitled album'
                detail=f"{value.get('assetCount',0)} items"
                cover=value.get('albumThumbnailAssetId')
                action=lambda _,value=value:window.activate_album(value['id'])
            elif kind=='people':
                name=value.get('name') or 'Unnamed person';detail='View photos';cover=None
                action=lambda _,value=value:window.open_collection(name,{'personIds':[value['id']]})
            elif kind=='tags':
                name=value.get('value') or value.get('name','Tag');detail='View photos';cover=None
                action=lambda _,value=value:window.open_collection(name,{'tagIds':[value['id']]})
            elif kind=='duplicates':
                assets=[asset for asset in value.get('assets',[]) if asset.get('visibility') not in ('locked','hidden')]
                if not assets:continue
                name=f'{len(assets)} similar items';detail='Review group';cover=assets[0]['id']
                action=lambda _,assets=assets:window.open_collection('Review duplicates',items=[media_from_asset(asset) for asset in assets])
            else:
                name=value['name'];detail='View photo';cover=value.get('id')
                action=lambda _,value=value:window.open_collection('Location',{'id':value['id']})
            body.append(Gtk.Label(label=name,xalign=0,ellipsize=3,max_width_chars=24,tooltip_text=name))
            body.append(Gtk.Label(label=detail,xalign=0,css_classes=['dim-label','caption']))
            button=Gtk.Button(child=body,css_classes=['flat','collection-card'],valign=Gtk.Align.START,halign=Gtk.Align.START)
            button.connect('clicked',action)
            card_overlay=Gtk.Overlay(child=button,halign=Gtk.Align.START,valign=Gtk.Align.START)
            flow.insert(card_overlay,-1)
            if kind in ('albums','people','tags','duplicates'):
                popover=Gtk.Popover()
                actions=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4,margin_top=6,margin_bottom=6,margin_start=6,margin_end=6)
                if kind!='duplicates':
                    rename=Gtk.Button(label='Rename',css_classes=['flat'])
                    rename.connect('clicked',lambda _,value=value,popover=popover:(popover.popdown(),edit_name(window,kind,value)))
                    actions.append(rename)
                if kind in ('people','duplicates','tags'):
                    label='Hide person' if kind=='people' else 'Dismiss duplicate group' if kind=='duplicates' else 'Delete tag'
                    remove=Gtk.Button(label=label,css_classes=['flat'])
                    def remove_item(_,value=value,popover=popover):
                        popover.popdown()
                        confirm=Adw.AlertDialog(heading=label+'?')
                        confirm.add_response('cancel','Cancel');confirm.add_response('apply',label)
                        confirm.set_response_appearance('apply',Adw.ResponseAppearance.DESTRUCTIVE)
                        path='/people/'+quote(value['id'],safe='') if kind=='people' else '/duplicates/'+quote(value['duplicateId'],safe='') if kind=='duplicates' else '/tags/'+quote(value['id'],safe='')
                        confirm.connect('response',lambda _,response:window.background(
                            lambda:client.request(path,{'isHidden':True} if kind=='people' else None,method='PUT' if kind=='people' else 'DELETE'),
                            lambda _:collection_view(window,kind)) if response=='apply' else None)
                        confirm.present(window)
                    remove.connect('clicked',remove_item);actions.append(remove)
                popover.set_child(actions)
                menu=Gtk.MenuButton(icon_name='view-more-symbolic',popover=popover,tooltip_text='Collection actions',
                                    halign=Gtk.Align.END,valign=Gtk.Align.START,margin_top=6,margin_end=6,css_classes=['osd'])
                card_overlay.add_overlay(menu)
                context=Gtk.GestureClick(button=3)
                context.connect('pressed',lambda gesture,*_,menu=menu:(menu.popup(),gesture.set_state(Gtk.EventSequenceState.CLAIMED)))
                button.add_controller(context)
            if cover or kind=='people':
                def image(value=value,cover=cover):
                    if window.current_page!=kind or generation!=window.search_generation:return None
                    if kind=='people':
                        blob=client.media_cache().fetch('person:'+value['id']+str(value.get('updatedAt','')),
                            lambda:client.request('/people/'+value['id']+'/thumbnail',binary=True))
                    else:
                        item=client.collection_cover(cover)
                        if item is None:return None
                        blob=client.image_bytes(item)
                    return decode_image(blob)
                window.background(image,lambda pixels,picture=picture:picture.set_paintable(window.texture_from_pixels(pixels)) if pixels else None,lambda _:None,images=True)
        previous=window.stack.get_child_by_name('collections')
        if previous:window.stack.remove(previous)
        wrapper=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        if kind in ('tags','albums'):
            create=Gtk.Button(label='New tag' if kind=='tags' else 'New album',halign=Gtk.Align.END,margin_top=12,margin_end=24)
            create.connect('clicked',lambda _:edit_name(window,kind));wrapper.append(create)
        wrapper.append(Gtk.ScrolledWindow(child=flow,hscrollbar_policy=Gtk.PolicyType.NEVER,vexpand=True))
        window.stack.add_named(wrapper,'collections')
        if data or kind in ('tags','albums'):window.stack.set_visible_child_name('collections')
        else:
            window.status.set_icon_name('folder-pictures-symbolic')
            window.status.set_title('No '+window.page_titles.get(kind,kind).lower()+' found')
            window.status.set_description('')
    window.background(lambda:client.collection(kind),loaded,window.library_failed)
