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
            from map_ui import PhotoMap
            previous=window.stack.get_child_by_name('collections')
            if previous:window.stack.remove(previous)
            page=PhotoMap(window,client,data);window.stack.add_named(page,'collections')
            window.stack.set_visible_child_name('collections');return
        from collection_widgets import collection_grid,tag_list,location_list
        refresh=lambda:collection_view(window,kind)
        view=tag_list(window,data,refresh) if kind=='tags' else location_list(window,data) if kind=='map' else collection_grid(window,client,kind,data,generation,refresh)
        previous=window.stack.get_child_by_name('collections')
        if previous:window.stack.remove(previous)
        wrapper=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        if kind in ('tags','albums'):
            create=Gtk.Button(label='New tag' if kind=='tags' else 'New album',halign=Gtk.Align.END,margin_top=12,margin_end=24)
            create.connect('clicked',lambda _:edit_name(window,kind));wrapper.append(create)
        wrapper.append(Gtk.ScrolledWindow(child=view,hscrollbar_policy=Gtk.PolicyType.NEVER,vexpand=True))
        window.stack.add_named(wrapper,'collections')
        if data or kind in ('tags','albums'):window.stack.set_visible_child_name('collections')
        else:
            window.status.set_icon_name('folder-pictures-symbolic')
            window.status.set_title('No '+window.page_titles.get(kind,kind).lower()+' found')
            window.status.set_description('')
    window.background(lambda:client.collection(kind),loaded,window.library_failed)
