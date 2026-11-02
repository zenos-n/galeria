"""Data-free timeline with stable media tiles and expandable date folders."""
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk
from layout import justified_rows
from imaging import duration_label

RATIOS=[1.2,1.78,1,.72,.56,1.6,.48,.55,1.35,.8,1.7,.6,1,1.8,.65,.5,1.3,1.5,.8,1.65,.6,1,.7,1.6,.6,1.8]
MONTHS=[('2026-01','January 2026','2026',0,12),('2025-12','December 2025','2025',12,26),('2025-11','November 2025','2025',26,40)]


class Mosaic(Gtk.Widget):
    __gtype_name__='GalleryMosaic'

    def __init__(self,open_photo,items=None):
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
        self.hovered_index=None
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
        self.card_pictures={}
        self.cover_slots={}
        self.rendered={}
        self.tick=0
        self.p=1
        self.from_map={}
        self.from_height=0
        self.last_width=900
        self.last_height=0
        self._target_cache=None
        self.motion_kind='tier'
        self.folder_membership={}
        self.folder_swap=False
        self.months=MONTHS
        if items is not None:
            self.months=[]
            for i,item in enumerate(items):
                key=item.created.strftime('%Y-%m')
                if self.months and self.months[-1][0]==key:
                    k,title,year,a,_=self.months[-1]
                    self.months[-1]=(k,title,year,a,i+1)
                else:
                    self.months.append((key,item.created.strftime('%B %Y'),item.created.strftime('%Y'),i,i+1))
        self.panel_month=self.parent(Gtk.Box(css_classes=['date-panel']))
        self.panel_year=self.parent(Gtk.Box(css_classes=['date-panel']))
        self.pointer_month=self.pointer()
        self.pointer_year=self.pointer()
        ratios=[item.ratio for item in items] if items is not None else RATIOS[:12]+RATIOS[12:]+RATIOS[4:18]
        for index,ratio in enumerate(ratios):
            overlay=Gtk.Overlay()
            block=Gtk.Box(css_classes=['placeholder',f'shade-{index%5}'])
            overlay.set_child(block)
            icon=Gtk.Image(icon_name='image-x-generic-symbolic',pixel_size=23,
                           halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER,css_classes=['placeholder-icon'])
            overlay.add_overlay(icon)
            if items is not None and items[index].kind=='VIDEO' or items is None and index in (1,4,9,17,23):
                duration=Gtk.Label(label='▷ '+duration_label(items[index].metadata.get('duration') if items is not None else '0:31'),halign=Gtk.Align.END,valign=Gtk.Align.START,css_classes=['video-duration'])
                overlay.add_overlay(duration)
                self.badges.append(duration)
            tile=Gtk.Button(child=overlay,tooltip_text='Open photo preview',css_classes=['photo-tile'])
            tile.photo_ratio=ratio
            tile.filename=items[index].filename if items is not None else f'photo_{index+1:04}.jpg'
            tile.media_item=items[index] if items is not None else None
            tile.media_texture=None
            tile.media_icon=icon
            tile.photo_picture=Gtk.Picture(can_shrink=True,content_fit=Gtk.ContentFit.COVER)
            tile.photo_picture.set_can_target(False)
            overlay.set_child(tile.photo_picture)
            tile.photo_picture.add_css_class(f'shade-{index%5}')
            tile.connect('clicked',self.clicked,index)
            check=Gtk.CheckButton(visible=False,tooltip_text='Select photo',css_classes=['media-check'])
            check.connect('toggled',lambda widget,i=index:self.check_toggled(i,widget.get_active()))
            self.checks.append(check)
            click=Gtk.GestureClick(button=1)
            click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            click.connect('pressed',self.modifier_click,index)
            tile.add_controller(click)
            self.tiles.append(self.parent(tile))
            self.parent(check)
        for key,title,year,start,stop in self.months:
            heading=self.parent(Gtk.Label(label=title if items is not None else ['Today','Yesterday','Sunday, 25 January'][len(self.headings)],
                                          xalign=0,css_classes=['day-heading']))
            self.headings.append(heading)
            card=self.card(title,lambda _,key=key:self.expand_month(key))
            self.month_cards[key]=card
            self.members[card]=self.tiles[start:stop]
        for year in dict.fromkeys(month[2] for month in self.months):
            card=self.card(year,lambda _,year=year:self.expand_year(year))
            self.year_cards[year]=card
            self.members[card]=[tile for _,_,y,a,b in self.months if y==year for tile in self.tiles[a:b]]
        for key,_,year,a,b in self.months:
            for tile in self.tiles[a:b]:
                self.owners[tile]=(self.month_cards[key],self.year_cards[year])
            self.owners[self.month_cards[key]]=(self.year_cards[year],)
        for card,members in self.members.items():
            for i,picture in enumerate(self.card_pictures[card]):
                if members:
                    tile=members[min(i,len(members)-1)]
                    self.cover_slots.setdefault(tile,[]).append(picture)
        motion=Gtk.EventControllerMotion()
        motion.connect('motion',self.pointer_motion)
        motion.connect('leave',lambda *_:self.set_hover(None))
        self.add_controller(motion)
        self.update_selection()

    def pointer_motion(self,_controller,x,y):
        hit=None
        if not self.tick:
            for i,tile in enumerate(self.tiles):
                if tile in self.rendered:
                    px,py,w,h,opacity=self.rendered[tile]
                    if opacity>.5 and px<=x<=px+w and py<=y<=py+h:
                        hit=i;break
        self.set_hover(hit)

    def set_hover(self,index):
        if self.hovered_index==index:
            return
        self.hovered_index=index
        for i,check in enumerate(self.checks):
            check.set_visible(self.selection_mode or i==index)
        self.queue_allocate()

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
        cover=Gtk.Grid(row_spacing=2,column_spacing=2,row_homogeneous=True,column_homogeneous=True,hexpand=True,vexpand=True,css_classes=['date-cover'])
        pictures=[]
        for i in range(4):
            picture=Gtk.Picture(can_shrink=True,content_fit=Gtk.ContentFit.COVER,hexpand=True,vexpand=True,css_classes=[f'shade-{i}'])
            cover.attach(picture,i%2,i//2,1,1)
            pictures.append(picture)
        body.append(cover)
        body.append(Gtk.Label(label=title,xalign=0,margin_start=4,margin_bottom=6,css_classes=['heading']))
        card=Gtk.Button(child=body,css_classes=['date-card'])
        self.card_pictures[card]=pictures
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
            check.set_visible(self.selection_mode or i==self.hovered_index)
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
        self.change(lambda:setattr(self,'expanded_month',None if self.expanded_month==key else key),'folder')

    def expand_year(self,year):
        self.change(lambda:setattr(self,'expanded_year',None if self.expanded_year==year else year),'folder')

    def change(self,update,kind='tier'):
        if self.tick:
            self.remove_tick_callback(self.tick)
        self.from_map=dict(self.rendered)
        self.from_height=self.last_height
        before=(self.expanded_month,self.expanded_year)
        self.set_hover(None)
        update()
        self.motion_kind=kind
        self.folder_swap=any(a and b and a!=b for a,b in zip(before,(self.expanded_month,self.expanded_year)))
        target,_=self.target_layout(self.last_width)
        self.folder_membership={}
        if kind=='folder':
            for widget in dict.fromkeys([*self.from_map,*target]):
                for panel in (self.panel_year,self.panel_month):
                    if widget==panel:
                        continue
                    for layout in (self.from_map,target):
                        if widget in layout and panel in layout:
                            x,y,w,h,_=layout[widget];px,py,pw,ph,_=layout[panel]
                            if x>=px and y>=py and x+w<=px+pw+1 and y+h<=py+ph+1:
                                self.folder_membership.setdefault(widget,set()).add(panel)
        self.p=0
        started=None
        duration=(340000 if kind=='folder' else 300000) if Gtk.Settings.get_default().get_property('gtk-enable-animations') else 1
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
        if not keys:
            return 0
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
                    ids=[i for _,_,year,a,b in self.months if year==active for i in range(a,b)]
                else:
                    _,_,_,a,b=next(m for m in self.months if m[0]==active)
                    ids=range(a,b)
                content_h=self.photo_rows(ids,x+12,panel_y+12,width-24,result)
                content_h+=24
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
            for heading,(_,_,_,a,b) in zip(self.headings,self.months):
                result[heading]=(2,y+8,max(1,width-4),28,1)
                y+=40
                y+=self.photo_rows(range(a,b),0,y,width,result)+12
        elif self.mode=='months':
            y=12+self.folder_rows([m[0] for m in self.months],'month',4,12,width-8,result)
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
                old=self.folder_endpoint(widget,new,True) if self.motion_kind=='folder' else self.anchor(widget,self.from_map,new)
            if new is None:
                new=self.folder_endpoint(widget,old,False) if self.motion_kind=='folder' else self.anchor(widget,target,old)
            result[widget]=tuple(a+(b-a)*self.p for a,b in zip(old,new))
        return result,round(self.from_height+(height-self.from_height)*self.p)

    def folder_endpoint(self,widget,rect,opening):
        x,y,w,h,_=rect
        if widget in (self.panel_month,self.panel_year):
            return x,y,w,0,1
        if widget in (self.pointer_month,self.pointer_year):
            return x,y,w,h,0
        return x,y-22,w,h,0 if self.folder_swap else 1

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def dispose(self):
        if self.tick:
            self.remove_tick_callback(self.tick)
            self.tick=0
        for widget in self.widgets:
            if widget.get_parent()==self:widget.unparent()

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

        for i,check in enumerate(self.checks):
            tile=self.tiles[i]
            active=tile in rects and check.get_visible()
            check.set_child_visible(active)
            if active:
                x,y,_,_,_=rects[tile]
                size=max(28,check.measure(Gtk.Orientation.HORIZONTAL,-1)[0])
                size=max(size,check.measure(Gtk.Orientation.VERTICAL,size)[0])
                point=Graphene.Point();point.init(x+6,y+6)
                check.allocate(size,size,-1,Gsk.Transform.new().translate(point))

    def do_snapshot(self,snapshot):
        for widget in self.rendered:
            self.snapshot_clipped(widget,snapshot)
        for i,check in enumerate(self.checks):
            if check.get_visible() and check.get_child_visible():
                self.snapshot_clipped(check,snapshot,self.tiles[i])

    def snapshot_clipped(self,widget,snapshot,owner=None):
        count=0
        if self.motion_kind=='folder' and self.p<1:
            for panel in self.folder_membership.get(owner or widget,()):
                if panel in self.rendered:
                    x,y,w,h,_=self.rendered[panel]
                    clip=Graphene.Rect();clip.init(x,y,w,max(0,h))
                    snapshot.push_clip(clip);count+=1
        self.snapshot_child(widget,snapshot)
        for _ in range(count):
            snapshot.pop()
