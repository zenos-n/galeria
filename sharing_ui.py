"""Real Immich shared links and album collaborators."""
from datetime import datetime,timedelta,timezone
from gi.repository import Adw,Gdk,Gtk
from library import LibraryError


class SharingDialog(Adw.PreferencesDialog):
    def __init__(self,window,album=None,asset_ids=None):
        super().__init__(title='Share album' if album else 'Share media',content_width=480,content_height=680)
        self.window=window;self.client=window.client;self.album=album;self.asset_ids=asset_ids or []
        self.closed=False;self.owner=not album
        self.link_generation=0;self.member_generation=0
        self.connect('closed',lambda *_:setattr(self,'closed',True))
        self.page=Adw.PreferencesPage(title='Sharing')
        self.page.set_description(album.get('albumName','Album') if album else f'{len(self.asset_ids)} selected '+('item' if len(self.asset_ids)==1 else 'items'))
        self.links=Adw.PreferencesGroup(title='Shared links',description='Anyone with a link can access the shared media, subject to its password and expiration.')
        self.page.add(self.links)
        self.link_rows=[]
        self.options=Adw.PreferencesGroup(title='New link')
        self.downloads=Adw.SwitchRow(title='Allow downloads',active=True)
        self.uploads=Adw.SwitchRow(title='Allow uploads',active=False,visible=bool(album))
        self.metadata=Adw.SwitchRow(title='Show photo metadata',subtitle='Includes camera and location information',active=False)
        self.expiry=Adw.ComboRow(title='Expires',model=Gtk.StringList.new(['Never','In 1 day','In 7 days','In 30 days']),selected=2)
        self.password=Adw.PasswordEntryRow(title='Password (optional)')
        for row in (self.downloads,self.uploads,self.metadata,self.expiry,self.password):self.options.add(row)
        self.create=Gtk.Button(label='Create link',css_classes=['suggested-action'],halign=Gtk.Align.END,margin_top=12,margin_bottom=6,sensitive=not album)
        self.create.connect('clicked',self.create_link);self.options.add(self.create);self.page.add(self.options)
        self.message=Gtk.Label(wrap=True,xalign=0,css_classes=['error'])
        errors=Adw.PreferencesGroup();errors.add(self.message);self.page.add(errors)
        if album:
            self.members=Adw.PreferencesGroup(title='People with access');self.page.add(self.members);self.member_rows=[]
            self.invites=Adw.PreferencesGroup(title='Invite someone',visible=False)
            self.user_choice=Adw.ComboRow(title='Person',model=Gtk.StringList.new([]))
            self.role_choice=Adw.ComboRow(title='Access',model=Gtk.StringList.new(['Viewer','Editor']))
            self.invite=Gtk.Button(label='Add person',halign=Gtk.Align.END,margin_top=12,margin_bottom=6,sensitive=False)
            self.invite.connect('clicked',self.invite_person)
            for row in (self.user_choice,self.role_choice,self.invite):self.invites.add(row)
            self.page.add(self.invites);self.load_members()
        self.add(self.page);self.load_links()

    def failed(self,message):
        if not self.closed:self.message.set_label(message)

    def changed(self):self.client.media_cache().remove('albums')

    def load_links(self):
        if self.closed:return
        self.link_generation+=1;generation=self.link_generation
        def loaded(values):
            if self.closed or generation!=self.link_generation:return
            for row in self.link_rows:self.links.remove(row)
            self.link_rows=[]
            for value in values:
                if not self.album and set(a['id'] for a in value.get('assets',[]))!=set(self.asset_ids):continue
                try:url=self.client.share_url(value)
                except LibraryError:continue
                expiry=value.get('expiresAt')
                detail='Expires '+expiry[:10] if expiry else 'No expiration'
                if value.get('password'):detail+=' · Password protected'
                row=Adw.ActionRow(title='Public link',subtitle=detail,use_markup=False)
                copy=Gtk.Button(icon_name='edit-copy-symbolic',tooltip_text='Copy link',valign=Gtk.Align.CENTER,css_classes=['flat'])
                copy.connect('clicked',lambda _,url=url:(Gdk.Display.get_default().get_clipboard().set(url),self.window.notice('Link copied.')))
                revoke=Gtk.Button(icon_name='user-trash-symbolic',tooltip_text='Revoke link',valign=Gtk.Align.CENTER,css_classes=['flat'])
                revoke.connect('clicked',lambda _,value=value:self.revoke(value))
                row.add_suffix(copy);row.add_suffix(revoke);self.links.add(row);self.link_rows.append(row)
            self.links.set_description('Anyone with a link can access this media.' if self.link_rows else 'No links yet. Create one below to share this media.')
        self.window.background(lambda:self.client.shared_links(self.album['id'] if self.album else None),loaded,self.failed)

    def create_link(self,_button):
        days=[0,1,7,30][self.expiry.get_selected()]
        options={'allowDownload':self.downloads.get_active(),'allowUpload':bool(self.album and self.uploads.get_active()),
                 'showMetadata':self.metadata.get_active(),'expiresAt':(datetime.now(timezone.utc)+timedelta(days=days)).isoformat().replace('+00:00','Z') if days else None}
        password=self.password.get_text()
        if password:options['password']=password
        self.password.set_text('');self.create.set_sensitive(False);self.message.set_label('')
        def done(_value):
            self.changed()
            if self.closed:self.window.notice('Share link created. Reopen Share to manage it.');return
            self.create.set_sensitive(self.owner);self.load_links()
        def failed(message):
            if not self.closed:self.create.set_sensitive(self.owner)
            self.failed(message)
        self.window.background(lambda:self.client.share_album(self.album['id'],options) if self.album else self.client.share_assets(self.asset_ids,options),done,failed)

    def revoke(self,value):
        confirm=Adw.AlertDialog(heading='Revoke this link?',body='People using this link will lose access. Album members keep their access.')
        confirm.add_response('cancel','Cancel');confirm.add_response('revoke','Revoke link')
        confirm.set_response_appearance('revoke',Adw.ResponseAppearance.DESTRUCTIVE)
        confirm.connect('response',lambda _,response:self.window.background(lambda:self.client.revoke_link(value['id']),lambda _:(self.changed(),self.load_links()),self.failed) if response=='revoke' else None)
        confirm.present(self.window)

    def load_members(self):
        if self.closed:return
        self.member_generation+=1;generation=self.member_generation
        def loaded(album):
            if self.closed or generation!=self.member_generation:return
            self.owner=album.get('ownerId')==self.client.user['id']
            self.create.set_sensitive(self.owner);self.options.set_visible(self.owner);self.invites.set_visible(self.owner)
            for row in self.member_rows:self.members.remove(row)
            self.member_rows=[];members=album.get('albumUsers',[]);self.member_ids={member['user']['id'] for member in members}
            for member in members:
                user=member['user'];name=user.get('name') or user.get('email','Person')
                is_owner=user['id']==album.get('ownerId')
                if self.owner and not is_owner:
                    role=member.get('role','viewer');old=1 if role=='editor' else 0
                    row=Adw.ComboRow(title=name,subtitle=user.get('email',''),use_markup=False,model=Gtk.StringList.new(['Viewer','Editor']),selected=old)
                    def change(row,_param,user=user,old=old):
                        selected=row.get_selected()
                        if selected==old:return
                        row.set_sensitive(False)
                        self.window.background(lambda:self.client.album_member(self.album['id'],user['id'],'editor' if selected else 'viewer'),
                            lambda _:self.load_members(),lambda message:(self.failed(message),self.load_members()))
                    row.connect('notify::selected',change)
                    remove=Gtk.Button(icon_name='list-remove-symbolic',tooltip_text='Remove access',valign=Gtk.Align.CENTER,css_classes=['flat'])
                    remove.connect('clicked',lambda _,user=user:self.remove_member(user));row.add_suffix(remove)
                else:row=Adw.ActionRow(title=name,subtitle='Owner' if is_owner else member.get('role','viewer').capitalize(),use_markup=False)
                row.add_prefix(Adw.Avatar(size=32,text=name,show_initials=True));self.members.add(row);self.member_rows.append(row)
            if self.owner:self.window.background(lambda:self.client.request('/users'),self.users_loaded,self.failed)
        self.window.background(lambda:self.client.album_info(self.album['id']),loaded,self.failed)

    def users_loaded(self,values):
        if self.closed:return
        self.available_users=[user for user in values if user['id'] not in self.member_ids and user['id']!=self.client.user['id']]
        self.user_choice.set_model(Gtk.StringList.new([(user.get('name') or 'Person')+' · '+user.get('email','') for user in self.available_users]))
        self.invite.set_sensitive(bool(self.available_users))
        if not self.available_users:self.invites.set_description('Everyone on this server already has access.')

    def invite_person(self,_button):
        index=self.user_choice.get_selected()
        if index>=len(self.available_users):return
        user=self.available_users[index];role='editor' if self.role_choice.get_selected() else 'viewer'
        self.invite.set_sensitive(False)
        self.window.background(lambda:self.client.invite_album(self.album['id'],user['id'],role),
            lambda _:(self.changed(),self.load_members()),lambda message:(self.failed(message),self.invite.set_sensitive(True)))

    def remove_member(self,user):
        confirm=Adw.AlertDialog(heading='Remove access?',body=(user.get('name') or user.get('email','This person'))+' will no longer have access to this album.')
        confirm.add_response('cancel','Cancel');confirm.add_response('remove','Remove access')
        confirm.set_response_appearance('remove',Adw.ResponseAppearance.DESTRUCTIVE)
        confirm.connect('response',lambda _,response:self.window.background(lambda:self.client.album_member(self.album['id'],user['id'],remove=True),
            lambda _:(self.changed(),self.load_members()),self.failed) if response=='remove' else None)
        confirm.present(self.window)


def share_album(window,album):
    if not window.client:window.notice('Connect Immich to share albums.');return
    dialog=SharingDialog(window,album=album);window.dialog=dialog;dialog.present(window)


def share_media(window):
    if not window.client:window.notice('Connect Immich to share media.');return
    items=[window.viewer.source.media_item] if window.viewer else [window.mosaic.tiles[index].media_item for index in window.mosaic.selected]
    if not items:return
    if any(item.metadata.get('visibility') in ('locked','hidden') for item in items):window.notice('Move private items out of the locked folder before sharing.');return
    dialog=SharingDialog(window,asset_ids=[item.id for item in items]);window.dialog=dialog;dialog.present(window)
