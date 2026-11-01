"""Search controls for the UI preview; no server requests."""
from gi.repository import Adw, Gtk


class SearchPanel(Gtk.SearchBar):
    def __init__(self,window):
        super().__init__()
        self.window=window
        self.mode='immich'
        self.inputs={}
        body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6,hexpand=True,
                      margin_start=10,margin_end=10,margin_top=4,margin_bottom=6)
        row=Gtk.Box(spacing=6)
        self.entry=Gtk.SearchEntry(placeholder_text='Search photos, people, places…',hexpand=True)
        self.entry.connect('search-changed',self.changed)
        self.entry.connect('activate',lambda _:window.notice('Connect Immich to run this search.') if self.mode=='immich' else None)
        self.connect_entry(self.entry)
        row.append(self.entry)
        self.filter_button=Gtk.MenuButton(icon_name='gallery-filter-symbolic',tooltip_text='Search filters')
        self.filter_button.add_css_class('flat')
        self.popover=Gtk.Popover()
        self.filter_button.set_popover(self.popover)
        self.build_filters()
        row.append(self.filter_button)
        body.append(row)
        self.tokens=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,max_children_per_line=6,
                                min_children_per_line=1,column_spacing=5,row_spacing=4,visible=False)
        body.append(self.tokens)
        self.set_child(body)

    def build_filters(self):
        root=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,margin_top=14,margin_bottom=14,
                      margin_start=14,margin_end=14,width_request=520)
        root.append(Gtk.Label(label='Search filters',xalign=0,css_classes=['title-3']))
        groups=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=18)
        def group(title):
            widget=Adw.PreferencesGroup(title=title)
            groups.append(widget)
            return widget
        def entry(parent,key,title=None):
            widget=Adw.EntryRow(title=title or key)
            self.inputs[key]=widget
            parent.add(widget)
        def combo(parent,key,values):
            widget=Adw.ComboRow(title=key,model=Gtk.StringList.new(values))
            self.inputs[key]=widget
            parent.add(widget)
        def switch(parent,key):
            widget=Adw.SwitchRow(title=key)
            self.inputs[key]=widget
            parent.add(widget)
        what=group('What to search')
        combo(what,'Search in',['Smart search','Filename or extension','Path or folder','Description','Text in images (OCR)'])
        combo(what,'Media type',['All media','Photos','Videos'])
        who=group('People and collections')
        for key in ['People','Albums','Tags']:
            entry(who,key)
        where=group('Location')
        for key in ['City','State','Country']:
            entry(where,key)
        when=group('Date taken')
        entry(when,'From','From · YYYY-MM-DD')
        entry(when,'Until','Until · YYYY-MM-DD')
        camera=group('Camera')
        for key in ['Make','Model','Lens']:
            entry(camera,key)
        display=group('Display options')
        combo(display,'Rating',['Any rating','1 star or more','2 stars or more','3 stars or more','4 stars or more','5 stars'])
        combo(display,'Visibility',['Main library','Include archive','Archive only'])
        for key in ['Favorites only','Not in an album']:
            switch(display,key)
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,min_content_height=360,
                                  max_content_height=440,propagate_natural_height=True,child=groups)
        root.append(scroll)
        footer=Gtk.Box(spacing=8,halign=Gtk.Align.END)
        clear=Gtk.Button(label='Clear')
        clear.connect('clicked',lambda _:self.clear())
        apply=Gtk.Button(label='Apply filters')
        apply.add_css_class('suggested-action')
        apply.connect('clicked',lambda _:(self.update_tokens(),self.popover.popdown()))
        footer.append(clear);footer.append(apply)
        root.append(footer)
        self.popover.set_child(root)

    def clear(self):
        for widget in self.inputs.values():
            if isinstance(widget,Adw.EntryRow):
                widget.set_text('')
            elif isinstance(widget,Adw.ComboRow):
                widget.set_selected(0)
            else:
                widget.set_active(False)
        self.update_tokens()

    def update_tokens(self):
        while self.tokens.get_first_child():
            self.tokens.remove(self.tokens.get_first_child())
        count=0
        for key,widget in self.inputs.items():
            if isinstance(widget,Adw.EntryRow):
                value=widget.get_text().strip()
            elif isinstance(widget,Adw.ComboRow):
                item=widget.get_selected_item()
                value=item.get_string() if widget.get_selected() else ''
            else:
                value='Yes' if widget.get_active() else ''
            if not value:
                continue
            title=key if value=='Yes' else f'{key}: {value}'
            chip=Gtk.Button(label=title+'  ×')
            chip.add_css_class('filter-chip')
            chip.connect('clicked',self.remove_filter,key)
            self.tokens.insert(chip,-1)
            count+=1
        self.tokens.set_visible(bool(count) and self.mode=='immich')

    def remove_filter(self,_button,key):
        widget=self.inputs[key]
        if isinstance(widget,Adw.EntryRow):
            widget.set_text('')
        elif isinstance(widget,Adw.ComboRow):
            widget.set_selected(0)
        else:
            widget.set_active(False)
        self.update_tokens()

    def set_mode(self,mode):
        self.mode=mode
        self.entry.set_placeholder_text('Search filenames' if mode=='local' else 'Search photos, people, places…')
        self.filter_button.set_visible(mode=='immich')
        self.tokens.set_visible(mode=='immich' and bool(self.tokens.get_first_child()))
        self.changed()

    def changed(self,*_):
        if not hasattr(self.window,'mosaic'):
            return
        self.window.mosaic.query=self.entry.get_text() if self.mode=='local' else ''
        self.window.mosaic.queue_resize()
