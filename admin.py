"""Native Immich administration, backed by the signed-in server."""
from gi.repository import Adw, Gio, GLib, Gtk


def size(value):
    return GLib.format_size(max(0,int(value or 0)))


class AdminPanel(Adw.PreferencesDialog):
    def __init__(self,window):
        super().__init__(title='Administration',content_width=720,content_height=720)
        self.window=window
        self.client=window.client
        self.sections={}
        self.rows_by_section={}
        self.closed=False
        self.connect('closed',lambda *_:setattr(self,'closed',True))
        overview=Adw.PreferencesPage(title='Overview',icon_name='preferences-system-symbolic')
        connection=Adw.PreferencesGroup(title='Library')
        if self.client:
            account=self.client.user
            row=Adw.ActionRow(title=account.get('name') or account.get('email','Immich'),subtitle=self.client.base,use_markup=False)
            row.add_prefix(Adw.Avatar(size=40,text=account.get('name','Immich'),show_initials=True))
            connection.add(row)
        else:
            row=Adw.ActionRow(title='Local library' if window.library_mode=='local' else 'No server connected',
                              subtitle=f'{len(window.local_items)} media items' if window.local_roots else 'Connect Immich to administer your server')
            connect=Gtk.Button(label='Connect Immich',valign=Gtk.Align.CENTER)
            connect.connect('clicked',lambda _:(self.close(),window.login()))
            row.add_suffix(connect)
            connection.add(row)
            for path in window.local_roots:
                connection.add(Adw.ActionRow(title=path,use_markup=False))
        refresh=Gtk.Button(icon_name='view-refresh-symbolic',tooltip_text='Refresh administration')
        refresh.add_css_class('flat')
        refresh.connect('clicked',lambda _:self.refresh())
        connection.set_header_suffix(refresh)
        overview.add(connection)
        self.add(overview)
        if not self.client or not self.client.user.get('isAdmin'):
            group=Adw.PreferencesGroup(title='Server administration')
            group.add(Adw.ActionRow(title='Administrator access required',subtitle='Sign in with an Immich administrator account to manage this server.'))
            overview.add(group)
            return
        for key,title,icon,page in [('overview','Server','drive-harddisk-symbolic',overview),
                                    ('users','Users','system-users-symbolic',None),
                                    ('queues','Job queues','system-run-symbolic',None)]:
            if page is None:
                page=Adw.PreferencesPage(title=title,icon_name=icon)
                self.add(page)
            group=Adw.PreferencesGroup(title=title)
            page.add(group)
            self.sections[key]=group
            self.rows_by_section[key]=[]
        self.refresh()

    def replace(self,key,rows):
        group=self.sections[key]
        for row in self.rows_by_section[key]:group.remove(row)
        self.rows_by_section[key]=rows
        for row in rows:group.add(row)

    def refresh(self):
        if not self.sections:
            self.window.refresh_library()
            return
        for key in self.sections:
            self.replace(key,[Adw.ActionRow(title='Loading…')])
            self.window.background(lambda key=key:self.client.admin_section(key),
                lambda value,key=key:self.loaded(key,value),
                lambda error,key=key:self.failed(key,error))

    def failed(self,key,message):
        if not self.closed:
            row=Adw.ActionRow(title='Could not load this section',subtitle=message)
            retry=Gtk.Button(label='Retry',valign=Gtk.Align.CENTER)
            retry.connect('clicked',lambda _:self.refresh())
            row.add_suffix(retry)
            self.replace(key,[row])

    def loaded(self,key,data):
        if self.closed or self.client!=self.window.client:return
        rows=[]
        if key=='overview':
            about,storage,stats=data['about'],data['storage'],data['statistics']
            version=about.get('version','Unknown')
            for title,value in [('Immich version',str(version)),('Photos',str(stats.get('photos',0))),
                                 ('Videos',str(stats.get('videos',0))),('Media storage',size(stats.get('usage'))),
                                 ('Disk used',storage.get('diskUse') or size(storage.get('diskUseRaw'))),
                                 ('Disk available',storage.get('diskAvailable') or size(storage.get('diskAvailableRaw')))]:
                rows.append(Adw.ActionRow(title=title,subtitle=value,use_markup=False))
            meter=Gtk.ProgressBar(fraction=max(0,min(1,storage.get('diskUsagePercentage',0)/100)),
                                  margin_top=12,margin_bottom=12,margin_start=12,margin_end=12)
            rows.append(meter)
        elif key=='users':
            for user in data:
                role='Administrator' if user.get('isAdmin') else 'User'
                row=Adw.ActionRow(title=user.get('name') or user.get('email','User'),use_markup=False,
                    subtitle=f"{user.get('email','')} · {role} · {user.get('status','active')}")
                row.add_prefix(Adw.Avatar(size=36,text=user.get('name','User'),show_initials=True))
                used=size(user.get('quotaUsageInBytes'))
                quota=user.get('quotaSizeInBytes')
                row.add_suffix(Gtk.Label(label=used+(f' / {size(quota)}' if quota else ''),css_classes=['dim-label']))
                rows.append(row)
        else:
            for queue in data:
                counts=queue.get('statistics',{})
                summary=' · '.join(f'{counts.get(name,0)} {name}' for name in ('active','waiting','failed'))
                paused=queue.get('isPaused',False)
                row=Adw.ActionRow(title=queue['name'].replace('-',' ').title(),use_markup=False,
                                  subtitle=('Paused · ' if paused else '')+summary)
                control=Gtk.Button(label='Resume' if paused else 'Pause',valign=Gtk.Align.CENTER,
                                   sensitive=not queue.get('legacy',False))
                control.connect('clicked',self.pause,queue['name'],not paused)
                row.add_suffix(control)
                rows.append(row)
        self.replace(key,rows or [Adw.ActionRow(title='No items')])

    def pause(self,button,name,paused):
        button.set_sensitive(False)
        def done(_):
            self.window.notice('Queue paused.' if paused else 'Queue resumed.')
            self.refresh()
        def failed(message):
            button.set_sensitive(True)
            self.window.notice(message)
        self.window.background(lambda:self.client.pause_queue(name,paused),done,failed)


def administration(window):
    panel=AdminPanel(window)
    window.dialog=panel
    panel.present(window)
