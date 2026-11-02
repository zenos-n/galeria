"""Folder upload rules, recursion depth, status and background service controls."""
from pathlib import Path
import time
import uuid
from gi.repository import Adw,Gio,GLib,Gtk
from library import LibraryError
from session_store import secret_put,secret_get
from sync_service import read_config,save_config,read_status,install_service,stop_service,wake_service


def folder_sync(window,identity=None):
    config=read_config();accounts=config.setdefault('accounts',{})
    if window.client:
        client=window.client
        accounts.setdefault(client.identity,{'server':client.base,'user_id':client.user['id'],
                           'label':client.user.get('name') or client.user.get('email','Immich'),'enabled':False,'folders':[]})
        identity=identity or client.identity
    else:identity=identity or next(iter(accounts),None)
    dialog=Adw.PreferencesDialog(title='Folder sync',content_width=600,content_height=680)
    if identity is None:
        page=Adw.PreferencesPage();group=Adw.PreferencesGroup(title='Connect Immich to sync folders')
        connect=Gtk.Button(label='Connect Immich',css_classes=['suggested-action'],margin_top=16,margin_bottom=16)
        connect.connect('clicked',lambda _:(dialog.close(),window.login()))
        group.add(connect);page.add(group);dialog.add(page);dialog.present(window);return
    account=accounts[identity]
    page=Adw.PreferencesPage(description='Upload new and changed media. Originals stay on this device; deletions are never mirrored.')
    connection=Adw.PreferencesGroup(title='Account')
    keys=list(accounts)
    choose=Adw.ComboRow(title='Sync account',model=Gtk.StringList.new([accounts[key].get('label',accounts[key]['server']) for key in keys]))
    choose.set_selected(keys.index(identity))
    choose.connect('notify::selected',lambda row,_:(dialog.close(),folder_sync(window,keys[row.get_selected()])))
    connection.add(choose)
    enabled=Adw.SwitchRow(title='Background uploads',subtitle='Continue while Galeria is closed',active=account.get('enabled',False))
    connection.add(enabled);page.add(connection)
    state=Adw.PreferencesGroup(title='Status')
    state_row=Adw.ActionRow(title='Ready' if account.get('enabled') else 'Paused',subtitle=account['server'],use_markup=False)
    now=Gtk.Button(label='Sync now',valign=Gtk.Align.CENTER,sensitive=account.get('enabled',False))
    now.connect('clicked',lambda _:window.background(wake_service,lambda _:window.notice('Sync requested.')))
    state_row.add_suffix(now);state.add(state_row);page.add(state)
    folders=Adw.PreferencesGroup(title='Folders')
    add=Gtk.Button(icon_name='list-add-symbolic',tooltip_text='Add folder');folders.set_header_suffix(add)
    page.add(folders)
    changing={'value':False}
    def persist():
        save_config(config)
        if account.get('enabled'):window.background(wake_service,lambda _:None,lambda _:None)
    def rows():
        for row in getattr(folders,'rules',[]):folders.remove(row)
        folders.rules=[]
        for rule in account['folders']:
            label='No subfolders' if not rule.get('recursive',True) else 'All subfolders' if not rule.get('max_depth') else f"Subfolders · depth {rule['max_depth']}"
            row=Adw.ActionRow(title=Path(rule['path']).name or rule['path'],subtitle=rule['path']+'\n'+label,use_markup=False)
            edit=Gtk.Button(icon_name='document-edit-symbolic',tooltip_text='Edit folder rule',valign=Gtk.Align.CENTER)
            edit.connect('clicked',lambda _,rule=rule:edit_rule(rule))
            remove=Gtk.Button(icon_name='list-remove-symbolic',tooltip_text='Remove sync rule (keeps all files)',valign=Gtk.Align.CENTER)
            remove.connect('clicked',lambda _,rule=rule:(account['folders'].remove(rule),persist(),rows()))
            row.add_suffix(edit);row.add_suffix(remove);folders.add(row);folders.rules.append(row)
    def edit_rule(rule):
        editor=Adw.Dialog(title='Folder rule',content_width=500,content_height=520)
        toolbar=Adw.ToolbarView();toolbar.add_top_bar(Adw.HeaderBar())
        body=Adw.PreferencesPage();group=Adw.PreferencesGroup(description=rule['path'])
        recursive=Adw.SwitchRow(title='Include subfolders',active=rule.get('recursive',True))
        depth=Adw.SpinRow.new_with_range(0,100,1);depth.set_title('Maximum depth · 0 means unlimited')
        depth.set_value(rule.get('max_depth',0));depth.set_sensitive(recursive.get_active())
        recursive.connect('notify::active',lambda row,_:depth.set_sensitive(row.get_active()))
        group.add(recursive);group.add(depth)
        choices=[('', 'Library only'),('__new__','Create or use a named album')]
        choices.extend((album['id'],album.get('albumName','Untitled album')) for album in getattr(window.album_tree,'albums',[]) if window.client and window.client.identity==identity)
        if rule.get('album_id') and rule['album_id'] not in [key for key,_ in choices]:choices.append((rule['album_id'],'Current album'))
        destination=Adw.ComboRow(title='Destination',model=Gtk.StringList.new([name for _,name in choices]))
        selected='__new__' if rule.get('album_name') else rule.get('album_id','')
        destination.set_selected(next((i for i,(key,_) in enumerate(choices) if key==selected),0))
        name=Adw.EntryRow(title='Album name',text=rule.get('album_name') or Path(rule['path']).name)
        name.set_sensitive(selected=='__new__')
        destination.connect('notify::selected',lambda row,_:name.set_sensitive(choices[row.get_selected()][0]=='__new__'))
        group.add(destination);group.add(name);body.add(group)
        actions=Adw.PreferencesGroup();save=Gtk.Button(label='Save folder rule',css_classes=['suggested-action'],margin_top=12,margin_bottom=12)
        def submit(_):
            target=choices[destination.get_selected()][0]
            if target=='__new__' and not name.get_text().strip():window.notice('Enter an album name.');return
            rule.update(recursive=recursive.get_active(),max_depth=int(depth.get_value()),
                        album_id=target if target!='__new__' else '',album_name=name.get_text().strip() if target=='__new__' else '')
            if rule not in account['folders']:account['folders'].append(rule)
            persist();rows();editor.close()
        save.connect('clicked',submit);actions.add(save);body.add(actions);toolbar.set_content(body);editor.set_child(toolbar)
        dialog.rule_dialog=editor;editor.present(window)
    def add_folder(_):
        picker=Gtk.FileDialog(title='Choose a folder to upload',accept_label='Choose folder')
        def chosen(picker,result):
            try:path=picker.select_folder_finish(result).get_path()
            except GLib.Error:return
            if path:edit_rule({'id':str(uuid.uuid4()),'path':str(Path(path).resolve()),'recursive':True,'max_depth':0,'enabled':True})
        picker.select_folder(window,None,chosen)
    add.connect('clicked',add_folder)
    def toggle(row,_param):
        if changing['value']:return
        active=row.get_active()
        if active and not account['folders']:
            changing['value']=True;row.set_active(False);changing['value']=False
            window.notice('Add a folder before starting background uploads.');return
        account['enabled']=active;save_config(config);row.set_sensitive(False)
        def work():
            if active:
                if window.client and window.client.identity==identity:
                    if not secret_put(identity,'session',window.client.token):raise LibraryError('The system keyring could not save the sync session.')
                elif not secret_get(identity,'session'):raise LibraryError('Sign in to this account before starting sync.')
                install_service()
            elif not any(item.get('enabled') for item in accounts.values()):stop_service()
            else:wake_service()
        def done(_):row.set_sensitive(True);now.set_sensitive(active);state_row.set_title('Running' if active else 'Paused')
        def failed(message):
            account['enabled']=False;save_config(config);changing['value']=True
            row.set_active(False);row.set_sensitive(True);changing['value']=False
            now.set_sensitive(False);state_row.set_title('Could not start sync');state_row.set_subtitle(message)
        window.background(work,done,failed)
    enabled.connect('notify::active',toggle)
    closed={'value':False};dialog.connect('closed',lambda *_:closed.update(value=True))
    def status():
        if closed['value']:return False
        value=read_status().get('accounts',{}).get(identity,{})
        if value.get('error'):state_row.set_title('Sync needs attention');state_row.set_subtitle(value['error'])
        elif value.get('folders'):
            uploaded=sum(folder.get('uploaded',0) for folder in value['folders'])
            errors=[error for folder in value['folders'] for error in folder.get('errors',[])]
            state_row.set_title(f'{uploaded} uploaded in the last pass' if account.get('enabled') else 'Paused')
            state_row.set_subtitle(errors[0] if errors else 'Originals are unchanged. Deletions are never mirrored.')
        return True
    rows();dialog.add(page);window.dialog=dialog;dialog.present(window);GLib.timeout_add_seconds(2,status)
