"""Server configuration and external library management."""
import re
from gi.repository import Adw, Gtk


def title(key):return re.sub(r'([a-z])([A-Z])',r'\1 \2',key).replace('_',' ').title()


def configuration(panel,data):
    group=panel.sections['settings'];rows=[];inputs=[]
    def populate(parent,values,path=()):
        for key,value in values.items():
            target=path+(key,)
            if isinstance(value,dict):
                row=Adw.ExpanderRow(title=title(key));populate(row,value,target)
            elif isinstance(value,bool):
                row=Adw.SwitchRow(title=title(key),active=value);inputs.append((target,value,row))
            elif isinstance(value,(str,int,float)) or value is None:
                cls=Adw.PasswordEntryRow if any(word in key.lower() for word in ('password','secret','token','apikey')) else Adw.EntryRow
                row=cls(title=title(key),text='' if value is None else str(value));inputs.append((target,value,row))
            elif isinstance(value,list) and all(isinstance(item,str) for item in value):
                row=Adw.EntryRow(title=title(key)+' · comma-separated',text=', '.join(value));inputs.append((target,value,row))
            else:
                row=Adw.ActionRow(title=title(key),subtitle='Advanced entries: '+str(len(value) if isinstance(value,list) else value))
            if isinstance(parent,list):parent.append(row)
            else:parent.add_row(row)
    populate(rows,data)
    feedback=Gtk.Label(wrap=True,css_classes=['error'],margin_top=10,margin_bottom=10)
    rows.append(feedback)
    save=Gtk.Button(label='Save settings',css_classes=['suggested-action'],margin_top=10,margin_bottom=10)
    def submit(_):
        changes=[]
        try:
            for path,old,row in inputs:
                value=row.get_active() if isinstance(row,Adw.SwitchRow) else row.get_text()
                if isinstance(old,int) and not isinstance(old,bool):value=int(value)
                elif isinstance(old,float):value=float(value)
                elif isinstance(old,list):value=[item.strip() for item in value.split(',') if item.strip()]
                elif old is None and value=='':value=None
                if value!=old:changes.append((path,value))
        except ValueError:feedback.set_label('Enter a valid number for '+title(path[-1])+'.');return
        save.set_sensitive(False)
        def update():
            current=panel.client.request('/system-config')
            for path,value in changes:
                node=current
                for part in path[:-1]:node=node[part]
                node[path[-1]]=value
            return panel.client.request('/system-config',current,method='PUT')
        panel.window.background(update,lambda _:(panel.window.notice('Server settings saved.'),panel.refresh()),
            lambda message:(save.set_sensitive(True),feedback.set_label(message)))
    save.connect('clicked',submit);rows.append(save)
    return rows


def edit_library(panel,library=None):
    dialog=Adw.Dialog(title='Edit external library' if library else 'Create external library',content_width=520,content_height=520)
    toolbar=Adw.ToolbarView();toolbar.add_top_bar(Adw.HeaderBar())
    page=Adw.PreferencesPage();group=Adw.PreferencesGroup(description='Paths refer to folders on the Immich server.')
    name=Adw.EntryRow(title='Name',text=(library or {}).get('name',''))
    group.add(name)
    entries=[]
    for key,label in [('importPaths','Import paths · one per line'),('exclusionPatterns','Exclusions · one per line')]:
        group.add(Adw.ActionRow(title=label))
        view=Gtk.TextView(wrap_mode=3,top_margin=8,bottom_margin=8,left_margin=10,right_margin=10)
        view.get_buffer().set_text('\n'.join((library or {}).get(key,[])))
        group.add(Gtk.ScrolledWindow(child=view,min_content_height=70));entries.append((key,view))
    page.add(group)
    feedback=Gtk.Label(wrap=True,css_classes=['error'],margin_top=8,margin_bottom=8)
    actions=Adw.PreferencesGroup();actions.add(feedback)
    save=Gtk.Button(label='Save library' if library else 'Create library',css_classes=['suggested-action'],margin_top=10,margin_bottom=10)
    actions.add(save);page.add(actions)
    def submit(_):
        fields={'name':name.get_text().strip()}
        for key,view in entries:
            buffer=view.get_buffer();value=buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),False)
            fields[key]=[line.strip() for line in value.splitlines() if line.strip()]
        if not fields['name'] or not fields['importPaths']:feedback.set_label('Enter a name and at least one server path.');return
        save.set_sensitive(False)
        if not library:fields['ownerId']=panel.client.user['id']
        panel.window.background(lambda:panel.client.request('/libraries/'+library['id'],fields,method='PUT') if library else panel.client.request('/libraries',fields),
            lambda _:(dialog.close(),panel.refresh()),lambda message:(save.set_sensitive(True),feedback.set_label(message)))
    save.connect('clicked',submit);toolbar.set_content(page);dialog.set_child(toolbar);dialog.present(panel.window)
