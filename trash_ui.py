"""Choose device, cloud or both without deleting untracked local files."""
from gi.repository import Adw,Gio,Gtk
from local_media import copies_for,trash_copies


def trash_selected(window,items,target=None):
    if not items or getattr(window,'media_action_pending',False):return
    client=window.client
    generation=window.data_generation;mosaic=window.mosaic
    def current():
        return not window.data_stopped and window.data_generation==generation and window.client is client
    def review(value):
        if not current():return
        local,cloud=value
        if not local and not cloud:window.notice('No available copies to move to Trash.');return
        choices=[('both','This device and Immich'),('local','This device only'),('cloud','Immich only')] if cloud and local else [('cloud','Immich only')] if cloud else [('local','This device only')]
        dialog=Adw.AlertDialog(heading=f'Move {len(items)} '+('item' if len(items)==1 else 'items')+' to trash?',body=f"{len(local)} known local {'file' if len(local)==1 else 'files'} · {len(cloud)} Immich {'item' if len(cloud)==1 else 'items'}. Local files go to this device’s Trash; cloud items go to Immich Trash. Changed local files are kept.")
        dialog.set_prefer_wide_layout(True)
        row=Adw.ComboRow(title='Remove from',use_subtitle=True,model=Gtk.StringList.new([title for _,title in choices]))
        group=Adw.PreferencesGroup();group.add(row);dialog.set_extra_child(group)
        dialog.add_response('cancel','Cancel');dialog.add_response('trash','Move to trash')
        dialog.set_response_appearance('trash',Adw.ResponseAppearance.DESTRUCTIVE);dialog.set_default_response('cancel');dialog.set_close_response('cancel')
        def confirm(_dialog,response):
            if response!='trash' or not current():return
            scope=choices[row.get_selected()][0]
            def perform():
                if not current():return None
                return trash_copies(client,local,cloud,scope,lambda path:Gio.File.new_for_path(path).trash(None))
            def done(result):
                if result is None or not current():return
                removed,remote,errors=result
                ids=[item.id for item in items if item.path in removed or remote and not item.path]
                if remote:
                    window.page_cache.clear();window.collection_cache.clear();window.remove_from_timeline(cloud)
                    client.refresh_serial=getattr(client,'refresh_serial',0)+1
                if ids:
                    if not window.client:window.local_items=[item for item in window.local_items if item.id not in ids]
                elif not window.viewer:window.mosaic.set_selection(False)
                message=f'{len(removed)} local files · {len(cloud) if remote else 0} Immich items moved to Trash.'
                if errors:message+=f' {len(errors)} local files kept. '+errors[0]
                window.notice(message)
                return ids
            paths={path for path,*_ in local} if scope!='cloud' else set()
            ids=[item.id for item in items if item.path in paths or scope!='local' and not item.path]
            optimistic=(lambda:window.optimistic_media_removal(ids,mosaic,'trash',target)) if ids else None
            window.mutate_media(perform,done,optimistic)
        dialog.connect('response',confirm);dialog.present(window)
    window.background(lambda:copies_for(client,items),review)
