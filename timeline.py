"""Data-free timeline with stable media tiles and expandable date folders."""
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk
from layout import justified_rows

RATIOS=[1.2,1.78,1,.72,.56,1.6,.48,.55,1.35,.8,1.7,.6,1,1.8,.65,.5,1.3,1.5,.8,1.65,.6,1,.7,1.6,.6,1.8]
MONTHS=[('2026-01','January 2026','2026',0,12),('2025-12','December 2025','2025',12,26),('2025-11','November 2025','2025',26,40)]


class Mosaic(Gtk.Widget):
    __gtype_name__='GalleryMosaic'

    def __init__(self,open_photo):
        super().__init__(hexpand=True,margin_start=10,margin_end=10)
        self.open_photo=open_photo
        self.target=154
        self.mode='all'
        self.show_durations=True
        self.selection_mode=False
        self.selected=set()
        self.on_selection=lambda:None
        self.anchor_index=None
        self.hidden_tile=None
        self.query=''
        self.expanded_month=None
        self.expanded_year=None
        self.tiles=[]
        self.checks=[]
        self.badges=[]
        self.widgets=[]
        self.headings=[]
        self.month_cards={}
        self.year_cards={}
        self.owners={}
        self.members={}
        self.rendered={}
        self.tick=0
        self.p=1
        self.from_map={}
        self.from_height=0
        self.last_width=900
        self.last_height=0
        self._target_cache=None
        self.panel_month=self.parent(Gtk.Box(css_classes=['date-panel']))
        self.panel_year=self.parent(Gtk.Box(css_classes=['date-panel']))
        self.pointer_month=self.pointer()
        self.pointer_year=self.pointer()
        ratios=RATIOS[:12]+RATIOS[12:]+RATIOS[4:18]
        for index,ratio in enumerate(ratios):
            overlay=Gtk.Overlay()
            block=Gtk.Box(css_classes=['placeholder',f'shade-{index%5}'])
            overlay.set_child(block)
            icon=Gtk.Image(icon_name='image-x-generic-symbolic',pixel_size=23,
                           halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER,css_classes=['placeholder-icon'])
            overlay.add_overlay(icon)
            if index in (1,4,9,17,23):
                duration=Gtk.Label(label='▷ 0:31',halign=Gtk.Align.END,valign=Gtk.Align.START,css_classes=['video-duration'])
                overlay.add_overlay(duration)
                self.badges.append(duration)
            tile=Gtk.Button(child=overlay,tooltip_text='Open photo preview',css_classes=['photo-tile'])
            tile.photo_ratio=ratio
            tile.filename=f'photo_{index+1:04}.jpg'
            tile.connect('clicked',self.clicked,index)
            check=Gtk.CheckButton(halign=Gtk.Align.START,valign=Gtk.Align.START,visible=False,
                                  margin_top=7,margin_start=7,tooltip_text='Select photo')
            check.connect('toggled',lambda widget,i=index:self.check_toggled(i,widget.get_active()))
            overlay.add_overlay(check)
            self.checks.append(check)
            hover=Gtk.EventControllerMotion()
            hover.connect('enter',lambda *args,i=index:self.checks[i].set_visible(True))
            hover.connect('leave',lambda *args,i=index:self.checks[i].set_visible(self.selection_mode))
            tile.add_controller(hover)
            click=Gtk.GestureClick(button=1)
            click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            click.connect('pressed',self.modifier_click,index)
            tile.add_controller(click)
            self.tiles.append(self.parent(tile))
        for key,title,year,start,stop in MONTHS:
            heading=self.parent(Gtk.Label(label=['Today','Yesterday','Sunday, 25 January'][len(self.headings)],
                                          xalign=0,css_classes=['day-heading']))
            self.headings.append(heading)
            card=self.card(title,lambda _,key=key:self.expand_month(key))
            self.month_cards[key]=card
            self.members[card]=self.tiles[start:stop]
        for year in ['2026','2025']:
            card=self.card(year,lambda _,year=year:self.expand_year(year))
            self.year_cards[year]=card
            self.members[card]=[tile for _,_,y,a,b in MONTHS if y==year for tile in self.tiles[a:b]]
        for key,_,year,a,b in MONTHS:
            for tile in self.tiles[a:b]:
                self.owners[tile]=(self.month_cards[key],self.year_cards[year])
            self.owners[self.month_cards[key]]=(self.year_cards[year],)
        self.update_selection()

    def parent(self,widget):
        widget.set_parent(self)
        self.widgets.append(widget)
        return widget

    def pointer(self):
        widget=Gtk.DrawingArea(css_classes=['date-pointer'])
        def draw(widget,context,width,height):
            color=widget.get_color()
            context.set_source_rgba(color.red,color.green,color.blue,color.alpha)
            context.move_to(0,height);context.line_to(width/2,0);context.line_to(width,height);context.close_path();context.fill()
        widget.set_draw_func(draw)
        return self.parent(widget)

    def card(self,title,callback):
        body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        cover=Gtk.Grid(row_spacing=2,column_spacing=2,hexpand=True,vexpand=True,css_classes=['date-cover'])
        for i in range(4):
            cover.attach(Gtk.Box(hexpand=True,vexpand=True,css_classes=[f'shade-{i}']),i%2,i//2,1,1)
        body.append(cover)
        body.append(Gtk.Label(label=title,xalign=0,margin_start=4,margin_bottom=6,css_classes=['heading']))
        card=Gtk.Button(child=body,css_classes=['date-card'])
        card.connect('clicked',callback)
        return self.parent(card)

    def clicked(self,tile,index):
        if self.tick:
            return
        if self.selection_mode:
            self.toggle(index)
        else:
            self.open_photo(index,tile)

    def modifier_click(self,gesture,_presses,_x,_y,index):
        state=gesture.get_current_event_state()
        if state & (Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.SHIFT_MASK):
            self.selection_mode=True
            if state & Gdk.ModifierType.SHIFT_MASK and self.anchor_index is not None:
                a,b=sorted((self.anchor_index,index))
                self.selected.update(i for i in range(a,b+1) if self.tiles[i] in self.rendered)
                self.update_selection()
            else:
                self.toggle(index)
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def check_toggled(self,index,active):
        if active==(index in self.selected):
            return
        self.selection_mode=True
        self.selected.add(index) if active else self.selected.discard(index)
        self.anchor_index=index
        self.update_selection()

    def toggle(self,index):
        self.selected.discard(index) if index in self.selected else self.selected.add(index)
        self.anchor_index=index
        self.update_selection()

    def update_selection(self):
        for i,(tile,check) in enumerate(zip(self.tiles,self.checks)):
            check.set_active(i in self.selected)
            check.set_visible(self.selection_mode)
            tile.add_css_class('selected') if i in self.selected else tile.remove_css_class('selected')
        self.on_selection()

    def set_selection(self,active):
        self.selection_mode=active
        if not active:
            self.selected.clear()
        self.update_selection()

    def select_all(self):
        self.selection_mode=True
        self.selected={i for i,tile in enumerate(self.tiles) if tile in self.rendered and self.rendered[tile][4]>.5}
        self.update_selection()

    def hide_tile(self,tile):
        if self.hidden_tile:
            self.hidden_tile.set_opacity(1)
        self.hidden_tile=tile
        if tile:
            tile.set_opacity(0)

    def rebuild(self):
        for badge in self.badges:
            badge.set_visible(self.show_durations)
        self.queue_resize()

    def set_mode(self,mode):
        if mode==self.mode:
            return
        self.set_selection(False)
        self.change(lambda:setattr(self,'mode',mode))

    def expand_month(self,key):
        self.change(lambda:setattr(self,'expanded_month',None if self.expanded_month==key else key))

    def expand_year(self,year):
        self.change(lambda:setattr(self,'expanded_year',None if self.expanded_year==year else year))

    def change(self,update):
        if self.tick:
            self.remove_tick_callback(self.tick)
        self.from_map=dict(self.rendered)
        self.from_height=self.last_height
        update()
        self.p=0
        started=None
        duration=300000 if Gtk.Settings.get_default().get_property('gtk-enable-animations') else 1
        def frame(_widget,clock):
            nonlocal started
            now=clock.get_frame_time()
            if started is None:
                started=now
            t=min(1,(now-started)/duration)
            self.p=t*t*(3-2*t)
            self.queue_resize()
            if t>=1:
                self.tick=0
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        self.tick=self.add_tick_callback(frame)
        self.queue_resize()

    def photo_rows(self,ids,x,y,width,result):
        ids=[i for i in ids if self.query.casefold() in self.tiles[i].filename.casefold()]
        rows=justified_rows([self.tiles[i].photo_ratio for i in ids],width,self.target)
        for n,dx,dy,w,h in rows:
            result[self.tiles[ids[n]]]=(x+dx,y+dy,w,h,1)
        return max((dy+h for _,_,dy,_,h in rows),default=0)

    def folder_rows(self,keys,kind,x,y,width,result):
        cols=max(1,int((width+14)/164))
        w=min(150,(width-14*(min(cols,len(keys))-1))/min(cols,len(keys)))
        h=w+32
        start=y
        for offset in range(0,len(keys),cols):
            row=keys[offset:offset+cols]
            for col,key in enumerate(row):
                card=self.year_cards[key] if kind=='year' else self.month_cards[key]
                result[card]=(x+col*(w+14),y,w,h,1)
            y+=h+12
            active=self.expanded_year if kind=='year' else self.expanded_month
            if active in row:
                panel=self.panel_year if kind=='year' else self.panel_month
                pointer=self.pointer_year if kind=='year' else self.pointer_month
                px=x+row.index(active)*(w+14)+w/2-10
                result[pointer]=(px,y-2,20,10,1)
                panel_y=y+8
                # Background is inserted before its contents in the snapshot order.
                result[panel]=(x,panel_y,width,1,1)
                if kind=='year':
                    months=[key for key,_,year,_,_ in MONTHS if year==active]
                    content_h=self.folder_rows(months,'month',x+14,panel_y+14,width-28,result)
                else:
                    _,_,_,a,b=next(m for m in MONTHS if m[0]==active)
                    content_h=self.photo_rows(range(a,b),x+12,panel_y+14,width-24,result)
                content_h+=28
                result[panel]=(x,panel_y,width,content_h,1)
                y=panel_y+content_h+18
        return y-start

    def target_layout(self,width):
        key=(width,self.mode,self.expanded_month,self.expanded_year,self.target,self.query)
        if self._target_cache and self._target_cache[0]==key:
            return self._target_cache[1]
        result={}
        if self.mode=='all':
            y=0
            for heading,(_,_,_,a,b) in zip(self.headings,MONTHS):
                result[heading]=(2,y+8,max(1,width-4),28,1)
                y+=40
                y+=self.photo_rows(range(a,b),0,y,width,result)+12
        elif self.mode=='months':
            y=12+self.folder_rows([m[0] for m in MONTHS],'month',4,12,width-8,result)
        else:
            y=12+self.folder_rows(list(self.year_cards),'year',4,12,width-8,result)
        value=(result,max(1,y))
        self._target_cache=(key,value)
        return value

    def anchor(self,widget,other,fallback):
        owners=self.owners.get(widget,())
        owners=sorted(owners,key=lambda node:0 if (self.mode=='years' and node in self.year_cards.values()) else 1)
        for owner in owners:
            if owner in other:
                x,y,w,h,_=other[owner]
                return x+w/2-8,y+h/2-8,16,16,0
        for member in self.members.get(widget,[]):
            if member in other:
                return (*other[member][:4],0)
        x,y,w,h,*_=fallback
        return x+w/2-1,y+h/2-1,2,2,0

    def positions(self,width):
        target,height=self.target_layout(width)
        if self.p>=1 or not self.from_map:
            return target,height
        result={}
        for widget in dict.fromkeys([*self.from_map,*target]):
            old=self.from_map.get(widget)
            new=target.get(widget)
            if old is None:
                old=self.anchor(widget,self.from_map,new)
            if new is None:
                new=self.anchor(widget,target,old)
            result[widget]=tuple(a+(b-a)*self.p for a,b in zip(old,new))
        return result,round(self.from_height+(height-self.from_height)*self.p)

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self,orientation,for_size):
        if orientation==Gtk.Orientation.HORIZONTAL:
            return 200,900,-1,-1
        _,height=self.positions(max(200,for_size))
        return height,height,-1,-1

    def do_size_allocate(self,width,height,baseline):
        self.last_width=width
        rects,self.last_height=self.positions(width)
        self.rendered=rects
        stable=self.target_layout(width)[0] if self.p<1 else rects
        for widget in self.widgets:
            widget.set_child_visible(widget in rects)
        for widget,(x,y,w,h,opacity) in rects.items():
            widget.set_opacity(0 if widget==self.hidden_tile else max(0,min(1,opacity)))
            reference=stable.get(widget,self.from_map.get(widget,(x,y,w,h,opacity)))
            min_w=widget.measure(Gtk.Orientation.HORIZONTAL,-1)[0]
            allocated_w=max(1,round(reference[2]),min_w)
            min_h=widget.measure(Gtk.Orientation.VERTICAL,allocated_w)[0]
            allocated_h=max(1,round(reference[3]),min_h)
            point=Graphene.Point();point.init(x,y)
            transform=Gsk.Transform.new().translate(point).scale(w/allocated_w,h/allocated_h)
            widget.allocate(allocated_w,allocated_h,-1,transform)

    def do_snapshot(self,snapshot):
        for widget in self.rendered:
            self.snapshot_child(widget,snapshot)
