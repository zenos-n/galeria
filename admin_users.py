"""Native account editor and account actions."""
from gi.repository import Adw, Gtk


def edit_user(panel,user=None):
    window=panel.window;client=panel.client
    dialog=Adw.Dialog(title='Edit user' if user else 'Create user',content_width=500,content_height=650)
    toolbar=Adw.ToolbarView();toolbar.add_top_bar(Adw.HeaderBar())
    page=Adw.PreferencesPage()
    group=Adw.PreferencesGroup(title='Account')
    name=Adw.EntryRow(title='Name',text=(user or {}).get('name',''))
    email=Adw.EntryRow(title='Email',text=(user or {}).get('email',''))
    password=Adw.PasswordEntryRow(title='New password' if user else 'Password')
    quota=Adw.EntryRow(title='Storage quota · GB (blank for unlimited)')
    if user and user.get('quotaSizeInBytes') is not None:quota.set_text(str(user['quotaSizeInBytes']/1024**3))
    role=Adw.SwitchRow(title='Administrator',active=bool((user or {}).get('isAdmin')))
    change=Adw.SwitchRow(title='Require password change',active=(user or {}).get('shouldChangePassword',True))
    for row in (name,email,password,quota,role,change):group.add(row)
    page.add(group)
    feedback=Gtk.Label(wrap=True,css_classes=['error'],margin_top=12,margin_bottom=12)
    buttons=Adw.PreferencesGroup();buttons.add(feedback)
    save=Gtk.Button(label='Save changes' if user else 'Create user',css_classes=['suggested-action'],margin_top=8,margin_bottom=8)
    buttons.add(save);page.add(buttons)
    if user:
        info=Adw.PreferencesGroup(title='Activity and storage')
        info_row=Adw.ActionRow(title='Loading account information…')
        info.add(info_row);page.add(info)
        def loaded(value):
            stats,sessions=value
            info_row.set_title(f"{stats.get('photos',0)} photos · {stats.get('videos',0)} videos")
            info_row.set_subtitle(f'{len(sessions)} sessions')
            for session in sessions:
                info.add(Adw.ActionRow(title=session.get('deviceType') or 'Session',subtitle=session.get('deviceOS') or session.get('updatedAt',''),use_markup=False))
        window.background(lambda:(client.request('/admin/users/'+user['id']+'/statistics'),client.request('/admin/users/'+user['id']+'/sessions')),loaded,
                          lambda message:(info_row.set_title('Account details unavailable'),info_row.set_subtitle(message)))
        danger=Adw.PreferencesGroup(title='Account status')
        deleted=bool(user.get('deletedAt')) or user.get('status')=='deleted'
        action=Gtk.Button(label='Restore user' if deleted else 'Delete user',css_classes=[] if deleted else ['destructive-action'],margin_top=8,margin_bottom=8)
        def perform(_):
            confirm=Adw.AlertDialog(heading='Restore this user?' if deleted else 'Delete this user?',body=user.get('email',''))
            confirm.add_response('cancel','Cancel');confirm.add_response('apply','Restore' if deleted else 'Delete user')
            confirm.set_response_appearance('apply',Adw.ResponseAppearance.SUGGESTED if deleted else Adw.ResponseAppearance.DESTRUCTIVE)
            def response(_dialog,value):
                if value!='apply':return
                action.set_sensitive(False)
                window.background(lambda:client.user_restore(user['id']) if deleted else client.users_delete(user['id']),
                    lambda _:(dialog.close(),panel.refresh()),lambda message:(action.set_sensitive(True),feedback.set_label(message)))
            confirm.connect('response',response);confirm.present(window)
        action.connect('clicked',perform);danger.add(action);page.add(danger)
    def submit(_):
        fields={'name':name.get_text().strip(),'email':email.get_text().strip(),
                'isAdmin':role.get_active(),'shouldChangePassword':change.get_active()}
        if not user:fields['notify']=False
        if not fields['name'] or '@' not in fields['email']:
            feedback.set_label('Enter a name and valid email address.');return
        if not user and not password.get_text():feedback.set_label('Enter an initial password.');return
        if password.get_text():fields['password']=password.get_text()
        try:
            value=quota.get_text().strip();amount=float(value) if value else None
            if amount is not None and (amount<0 or amount!=amount):raise ValueError()
            fields['quotaSizeInBytes']=int(amount*1024**3) if amount is not None else None
        except (ValueError,OverflowError):feedback.set_label('Enter a non-negative storage quota.');return
        password.set_text('');save.set_sensitive(False);feedback.set_label('Saving…')
        window.background(lambda:client.users_update(user['id'],fields) if user else client.users_create(fields),
            lambda _:(dialog.close(),panel.refresh(),window.notice('User updated.' if user else 'User created.')),
            lambda message:(save.set_sensitive(True),feedback.set_label(message)))
    save.connect('clicked',submit)
    toolbar.set_content(page);dialog.set_child(toolbar);panel.user_dialog=dialog;dialog.present(window)
