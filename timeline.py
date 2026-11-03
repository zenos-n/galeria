"""Data-free timeline with stable media tiles and expandable date folders."""
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk
from layout import RowLayout
from imaging import duration_label
from collections import defaultdict,deque,OrderedDict
from bisect import bisect_left,bisect_right
from date_motion import groups as motion_groups,cover_slot

RATIOS=[1.2,1.78,1,.72,.56,1.6,.48,.55,1.35,.8,1.7,.6,1,1.8,.65,.5,1.3,1.5,.8,1.65,.6,1,.7,1.6,.6,1.8]
MONTHS=[('2026-01','January 2026','2026',0,12),('2025-12','December 2025','2025',12,26),('2025-11','November 2025','2025',26,40)]


class Mosaic(Gtk.Widget):
    __gtype_name__='GalleryMosaic'

    def __init__(self,open_photo,items=None,buckets=None,on_bucket=None):
        super().__init__(hexpand=True,margin_start=10,margin_end=10)
        self.open_photo=open_photo
        self.on_bucket=on_bucket
        self.cached_texture=lambda item:None
        self.on_context=lambda *args:None
        self.bucket_counts={}
        self.indexed=bool(buckets and any(item.metadata.get('timeline_slot') for item in (items or [])))
        self.items=items
        self.placeholder_paintable=Gdk.MemoryTexture.new(1,1,Gdk.MemoryFormat.R8G8B8A8,GLib.Bytes.new(bytes([58,58,61,255])),4)
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
        self._target_cache=OrderedDict();self._row_cache=OrderedDict()
        self.month_extents={}
        self.on_window=lambda:None;self.window_signature=None
        self.tier_images=[];self.tier_groups=[];self.tier_sources=None
        self.asset_months={item.id:item.created.strftime('%Y-%m') for item in (items or [])}
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
        if buckets is not None:
            from datetime import datetime
            groups={month[0]:month for month in self.months}
            for bucket in buckets:
                key=bucket['timeBucket'][:7]
                self.bucket_counts[key]=self.bucket_counts.get(key,0)+bucket['count']
                groups.setdefault(key,(key,datetime.strptime(key,'%Y-%m').strftime('%B %Y'),key[:4],0,0))
            self.months=[groups[key] for key in sorted(groups,reverse=True)]
        self.panel_month=self.parent(Gtk.Box(css_classes=['date-panel']))
        self.panel_year=self.parent(Gtk.Box(css_classes=['date-panel']))
        self.panels={self.panel_month,self.panel_year}
        self.loading=self.parent(Gtk.Spinner(spinning=True))
        self.pointer_month=self.pointer()
        self.pointer_year=self.pointer()
        ratios=[item.ratio for item in items] if items is not None else RATIOS[:12]+RATIOS[12:]+RATIOS[4:18]
        from timeline_cells import Cell,Check
        self.active_widgets=set()
        for index,ratio in enumerate(ratios):
            tile=Cell(self,index,items[index] if items is not None else None,ratio)
            self.tiles.append(tile)
            self.checks.append(Check(self,index))
        for key,title,year,start,stop in self.months:
            heading=self.parent(Gtk.Label(label=title if items is not None else ['Today','Yesterday','Sunday, 25 January'][len(self.headings)],
                                          xalign=0,css_classes=['day-heading']))
            self.headings.append(heading)
            card=self.card(title,lambda _,key=key:self.expand_month(key))
            self.month_cards[key]=card
            self.members[card]=self.tiles[start:stop]
        self.tile_set=set(self.tiles)
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
                    if tile.media_item:picture.media_id=tile.media_item.id
                    self.cover_slots.setdefault(tile,[]).append(picture)
        self.caption_widgets=set(self.card_pictures)|set(self.headings)
        motion=Gtk.EventControllerMotion()
        motion.connect('motion',self.pointer_motion)
        motion.connect('leave',lambda *_:self.set_hover(None))
        self.add_controller(motion)
        context=Gtk.GestureClick(button=3)
        def context_pressed(gesture,_count,x,y):
            for tile in self.active_widgets & self.tile_set:
                rect=self.rendered.get(tile)
                if rect and rect[0]<=x<=rect[0]+rect[2] and rect[1]<=y<=rect[1]+rect[3] and not tile.media_item.metadata.get('placeholder'):
                    self.on_context(tile.media_item,x,y);gesture.set_state(Gtk.EventSequenceState.CLAIMED);break
        context.connect('pressed',context_pressed);self.add_controller(context)
        self.update_selection()

    def pointer_motion(self,_controller,x,y):
        hit=None
        if not self.tick:
            for tile in self.active_widgets & self.tile_set:
                i=tile.index
                if tile in self.rendered:
                    px,py,w,h,opacity=self.rendered[tile]
                    if opacity>.5 and px<=x<=px+w and py<=y<=py+h:
                        hit=i;break
        self.set_hover(hit)

    def set_hover(self,index):
        if self.hovered_index==index:
            return
        self.hovered_index=index
        self.queue_allocate()

    def parent(self,widget):
        widget.set_parent(self)
        widget.set_child_visible(False)
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
        if tile.media_item and tile.media_item.metadata.get('placeholder'):return
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
                self.selected.update(i for i in range(a,b+1) if (self.mode=='all' or self.tiles[i] in self.rendered) and not self.tiles[i].media_item.metadata.get('placeholder'))
                self.update_selection()
            else:
                self.toggle(index)
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def check_toggled(self,index,active):
        if self.tiles[index].media_item and self.tiles[index].media_item.metadata.get('placeholder'):return
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
        for tile in self.active_widgets & self.tile_set:
            i=tile.index;check=self.checks[i]
            check.set_active(i in self.selected)
            tile.add_css_class('selected') if i in self.selected else tile.remove_css_class('selected')
        self.on_selection()
        self.queue_allocate()

    def set_selection(self,active):
        self.selection_mode=active
        if not active:
            self.selected.clear()
        self.update_selection()

    def selection_months(self):
        chosen={self.tiles[i].media_item.created.strftime('%Y-%m') for i in self.selected if self.tiles[i].media_item}
        if chosen:return chosen
        top,_=self.visible_range()
        current=next((key for key,(start,end) in self.month_extents.items() if end>top),self.months[0][0] if self.months else None)
        return {current} if current else set()

    def select_all(self):
        self.selection_mode=True
        months=self.selection_months()
        eligible=[i for key,_,_,a,b in self.months if key in months for i in range(a,b)] if self.mode=='all' else [i for key,_,year,a,b in self.months if key==self.expanded_month or year==self.expanded_year for i in range(a,b)]
        self.selected={i for i in eligible if self.query.casefold() in self.tiles[i].filename.casefold() and not (self.tiles[i].media_item and self.tiles[i].media_item.metadata.get('placeholder'))}
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

    def update_bucket(self,key,items):
        month=next((month for month in self.months if month[0]==key),None)
        if not month:return
        _,_,_,start,end=month
        if end-start!=len(items):return
        top,page=self.visible_range()
        anchor=next((tile for tile in self.active_widgets & self.tile_set if tile in self.rendered and self.rendered[tile][1]<=top<=self.rendered[tile][1]+self.rendered[tile][3]),None)
        offset=top-self.rendered[anchor][1] if anchor else 0
        geometry_changed=any(self.tiles[i].photo_ratio!=item.ratio or self.query and self.tiles[i].filename!=item.filename for i,item in enumerate(items,start))
        for i,item in enumerate(items,start):
            tile=self.tiles[i];tile.media_item=item;tile.photo_ratio=item.ratio;tile.filename=item.filename
            self.asset_months[item.id]=key
            if tile.button:tile.release()
            self.items[i]=item
        if geometry_changed:
            self._target_cache.clear()
            for cache_key in list(self._row_cache):
                ids=cache_key[0]
                if ids and ids[0]<end and ids[-1]>=start:del self._row_cache[cache_key]
        self.update_selection()
        if geometry_changed and anchor and start<=anchor.index and top>0 and self.mode=='all':
            rect=self.target_layout(self.last_width)[0].get(anchor)
            parent=self.get_parent()
            while parent and not isinstance(parent,Gtk.ScrolledWindow):parent=parent.get_parent()
            if rect and parent:GLib.idle_add(lambda:(parent.get_vadjustment().set_value(rect[1]+offset),False)[1])
        self.queue_resize()

    def set_mode(self,mode):
        if mode==self.mode:
            return
        self.set_selection(False)
        def update():
            self.mode=mode
            self.expanded_month=self.expanded_year=None
        self.change(update)

    def continue_from(self,old,kind=None,scroll_shift=0):
        pairs=[(old.panel_month,self.panel_month),(old.panel_year,self.panel_year),
               (old.pointer_month,self.pointer_month),(old.pointer_year,self.pointer_year),(old.loading,self.loading)]
        for previous,current in [(old.month_cards,self.month_cards),(old.year_cards,self.year_cards)]:
            pairs.extend((widget,current[key]) for key,widget in previous.items() if key in current)
        headings={month[0]:heading for month,heading in zip(self.months,self.headings)}
        pairs.extend((heading,headings[month[0]]) for month,heading in zip(old.months,old.headings) if month[0] in headings)
        tiles={tile.media_item.id:tile for tile in self.tiles if tile.media_item}
        pairs.extend((tile,tiles[tile.media_item.id]) for tile in old.tiles if tile.media_item and tile.media_item.id in tiles)
        self.rendered={new:(rect[0],rect[1]+scroll_shift,*rect[2:]) for previous,new in pairs if (rect:=old.rendered.get(previous)) is not None}
        self.last_width=old.last_width;self.last_height=old.last_height
        self.tier_sources=old.image_occurrences(old.rendered)
        self.change(lambda:None,kind or old.motion_kind)

    def expand_month(self,key):
        self.change(lambda:setattr(self,'expanded_month',None if self.expanded_month==key else key),'folder')
        if self.expanded_month and self.on_bucket:self.on_bucket('month',key)

    def expand_year(self,year):
        self.change(lambda:setattr(self,'expanded_year',None if self.expanded_year==year else year),'folder')
        if self.expanded_year and self.on_bucket:self.on_bucket('year',year)

    def change(self,update,kind='tier'):
        top,page=self.visible_range()
        visible_layout=lambda layout:{widget:rect for widget,rect in layout.items() if rect[1]+rect[3]>=top-page*2 and rect[1]<=top+page*3}
        sources=self.tier_sources if self.tier_sources is not None else [(id,paintable,tuple(a+(b-a)*self.p for a,b in zip(start,end))) for _,images,_,_ in self.tier_groups for id,paintable,start,end in images] if self.tick and self.motion_kind=='tier' and self.tier_groups else self.image_occurrences(visible_layout(self.rendered))
        self.tier_sources=None;self.tier_images=[];self.tier_groups=[]
        if self.tick:
            self.remove_tick_callback(self.tick)
        self.from_map=visible_layout(self.rendered)
        if kind=='folder':
            self.from_map.update((widget,rect) for widget,rect in self.rendered.items() if widget not in self.tile_set)
        self.from_height=self.last_height
        before=(self.expanded_month,self.expanded_year);old_mode=self.mode
        self.set_hover(None)
        update()
        self.motion_kind=kind
        self.folder_swap=any(a and b and a!=b for a,b in zip(before,(self.expanded_month,self.expanded_year)))
        target,target_height=self.target_layout(self.last_width)
        if kind=='reflow':self.from_height=max(self.from_height,target_height)
        if kind=='tier':
            top,page=self.visible_range()
            visible=[value for value in sources if value[2][1]+value[2][3]>=top and value[2][1]<=top+page]
            month=self.asset_months.get(min(visible,key=lambda value:value[2][1])[0],'') if visible else ''
            if self.mode=='all':
                anchor=next((heading for entry,heading in zip(self.months,self.headings) if entry[0]==month),None)
            else:anchor=(self.year_cards if self.mode=='years' else self.month_cards).get(month[:4] if self.mode=='years' else month)
            self.transition_scroll=max(0,min(target.get(anchor,(0,0))[1],target_height-page))
            target,target_height=self.target_layout(self.last_width,self.transition_scroll)
            shift=self.transition_scroll-top
            sources=[(id,paintable,(rect[0],rect[1]+shift,*rect[2:])) for id,paintable,rect in visible]
            destinations=self.image_occurrences({widget:rect for widget,rect in target.items() if rect[1]<=self.transition_scroll+page and rect[1]+rect[3]>=self.transition_scroll})
            cards={key:target[card] for key,card in (self.year_cards if self.mode=='years' else self.month_cards if self.mode=='months' else {}).items() if card in target}
            previous_cards=self.year_cards if old_mode=='years' else self.month_cards if old_mode=='months' else {}
            for id,_,_ in destinations:
                month=self.asset_months.get(id,'');card=previous_cards.get(month[:4] if old_mode=='years' else month)
                if card in self.from_map:
                    rect=self.from_map[card];cards[('source',id)]=(rect[0],rect[1]+shift,*rect[2:])
            self.tier_groups=motion_groups(sources,destinations,self.asset_months,self.mode,cards)
            self.tier_images=[(paintable,start,end) for _,images,_,_ in self.tier_groups for _,paintable,start,end in images]
            self.from_map={widget:(rect[0],rect[1]+shift,*rect[2:]) for widget,rect in self.from_map.items()}
        self.motion_widgets=tuple(dict.fromkeys([*self.from_map,*target]))
        self.folder_membership={}
        if kind=='folder':
            for widget in dict.fromkeys([*self.from_map,*target]):
                for panel in (self.panel_year,self.panel_month):
                    if widget==panel:
                        continue
                    for layout in (self.from_map,target):
                        if widget in layout and panel in layout:
                            if widget in self.tile_set or widget==self.loading:
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

    def image_occurrences(self,layout):
        result=[]
        for key,card in self.month_cards.items():
            for picture in self.card_pictures[card]:
                if getattr(picture,'media_id',None):self.asset_months[picture.media_id]=key
        for tile in layout.keys() & self.tile_set:
            if tile.media_item:
                texture=tile.media_texture or self.cached_texture(tile.media_item)
                if texture:
                    tile.photo_picture.set_paintable(texture);tile.media_icon.set_visible(False)
                result.append((tile.media_item.id,texture or self.placeholder_paintable,layout[tile]))
        for card,pictures in self.card_pictures.items():
            if card not in layout:continue
            for i,picture in enumerate(pictures):
                paintable=picture.get_paintable() or self.placeholder_paintable;asset=getattr(picture,'media_id',None)
                if asset is None:
                    key=next((key for key,value in self.month_cards.items() if value==card),None)
                    if key is None:key=next((key+'-01' for key,value in self.year_cards.items() if value==card),'')
                    asset=f'cover:{key}:{i}';self.asset_months[asset]=key
                rect=cover_slot(layout[card],i)
                result.append((asset,paintable,rect))
        return result

    def photo_rows(self,ids,x,y,width,result):
        key=(ids if isinstance(ids,range) else tuple(ids),width,self.target,self.query)
        cached=self._row_cache.get(key)
        if cached is None:
            query=self.query.casefold()
            filtered=[i for i in ids if query in self.tiles[i].filename.casefold()] if query else ids
            cached=(filtered,RowLayout([self.tiles[i].photo_ratio for i in filtered],width,self.target))
            self._row_cache[key]=cached
            while len(self._row_cache)>384:self._row_cache.popitem(last=False)
        self._row_cache.move_to_end(key)
        filtered,rows=cached
        low,high=self._layout_band
        for index,dx,dy,w,h in rows.visible(low-y,high-y):result[self.tiles[filtered[index]]]=(x+dx,y+dy,w,h,1)
        return rows.height

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
                if not content_h and self.on_bucket:
                    result[self.loading]=(x+width/2-16,panel_y+24,32,32,1)
                    content_h=68
                content_h+=24
                result[panel]=(x,panel_y,width,content_h,1)
                y=panel_y+content_h+18
        return y-start

    def target_layout(self,width,view_top=None):
        top,page=self.visible_range();top=top if view_top is None else view_top
        band=int(top//page);self._layout_band=((band-2)*page,(band+4)*page)
        key=(width,self.mode,self.expanded_month,self.expanded_year,self.target,self.query,band,page)
        if key in self._target_cache:
            self._target_cache.move_to_end(key)
            value,self.month_extents=self._target_cache[key]
            return value
        result={};extents={}
        if self.mode=='all':
            y=0
            for heading,(month,_,_,a,b) in zip(self.headings,self.months):
                if a==b:continue
                result[heading]=(2,y+8,max(1,width-4),28,1)
                start=y
                y+=40
                y+=self.photo_rows(range(a,b),0,y,width,result)+12
                extents[month]=(start,y)
        elif self.mode=='months':
            y=12+self.folder_rows([m[0] for m in self.months],'month',4,12,width-8,result)
        else:
            y=12+self.folder_rows(list(self.year_cards),'year',4,12,width-8,result)
        value=(result,max(1,y))
        self.month_extents=extents;self._target_cache[key]=(value,extents)
        while len(self._target_cache)>4:self._target_cache.popitem(last=False)
        return value

    def anchor(self,widget,other,fallback):
        if widget in self.caption_widgets:return (*fallback[:4],0)
        if self.motion_kind=='reflow':
            x,y,w,h,_=fallback
            return x,y-18,w,h,0
        owners=self.owners.get(widget,())
        owners=sorted(owners,key=lambda node:0 if (self.mode=='years' and node in self.year_cards.values()) else 1)
        for owner in owners:
            if owner in other:
                x,y,w,h,_=other[owner]
                return x,y,w,h,0
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
        for widget in self.motion_widgets:
            if self.motion_kind=='tier' and self.tier_groups and widget in self.tile_set:continue
            old=self.from_map.get(widget)
            new=target.get(widget)
            if old is None and new is None:continue
            if old is None:
                old=self.folder_endpoint(widget,new,True) if self.motion_kind=='folder' else self.anchor(widget,self.from_map,new)
            if new is None:
                new=self.folder_endpoint(widget,old,False) if self.motion_kind=='folder' else self.anchor(widget,target,old)
            result[widget]=tuple(a+(b-a)*self.p for a,b in zip(old,new))
        return result,round(self.from_height+(height-self.from_height)*self.p)

    def folder_endpoint(self,widget,rect,opening):
        x,y,w,h,_=rect
        if widget in (self.panel_month,self.panel_year):
            return x,y-8,w,0,1
        if widget in (self.pointer_month,self.pointer_year):
            return x,y,w,h,0
        if widget in self.caption_widgets:return x,y,w,h,0
        return x,y-22,w,h,0 if self.folder_swap else 1

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def dispose(self):
        child=self.get_first_child()
        while child:
            following=child.get_next_sibling()
            if isinstance(child,Gtk.Popover):
                child.popdown()
                if child.get_parent():child.unparent()
            child=following
        if self.tick:
            self.remove_tick_callback(self.tick)
            self.tick=0
        for check in self.checks:check.dispose()
        for tile in self.tiles:
            tile.release()
            if tile.get_parent()==self:tile.unparent()
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
        top,page=self.visible_range()
        tier=self.motion_kind=='tier' and self.p<1 and bool(self.tier_images)
        for pictures in self.card_pictures.values():
            for picture in pictures:picture.set_opacity(0 if tier else 1)
        if not hasattr(self,'_visible_index') or self._visible_index[0] is not rects:
            order={widget:i for i,widget in enumerate(rects)}
            entries=sorted((rect[1],order[widget],widget) for widget,rect in rects.items() if widget not in self.panels)
            self._visible_index=(rects,[row[0] for row in entries],entries,order,max((rects[widget][3] for _,_,widget in entries),default=1))
        _,ys,entries,order,max_h=self._visible_index
        lo=bisect_left(ys,max(0,top-page*2)-max_h);hi=bisect_right(ys,top+page*3)
        active={widget for _,_,widget in entries[lo:hi] if rects[widget][1]+rects[widget][3]>=max(0,top-page*2) and not (tier and widget in self.tile_set)}
        active.update(panel for panel in (self.panel_month,self.panel_year) if panel in rects and rects[panel][1]+rects[panel][3]>=top-page*2 and rects[panel][1]<=top+page*3)
        for widget in self.active_widgets-active:
            widget.set_child_visible(False)
            if widget in self.tile_set:
                widget.release();self.checks[widget.index].set_child_visible(False);widget.unparent()
        self.active_widgets=active
        self.snapshot_widgets=sorted(active,key=order.__getitem__)
        for widget in self.snapshot_widgets:
            if widget.get_parent() is None:widget.set_parent(self)
            widget.set_child_visible(True)
            if widget in self.tile_set:
                widget.add_css_class('selected') if widget.index in self.selected else widget.remove_css_class('selected')
            x,y,w,h,opacity=rects[widget]
            if widget in self.tile_set:widget.ensure()
            widget.set_opacity(0 if widget==self.hidden_tile else max(0,min(1,opacity)))
            reference=stable.get(widget,self.from_map.get(widget,(x,y,w,h,opacity)))
            min_w=widget.measure(Gtk.Orientation.HORIZONTAL,-1)[0]
            allocated_w=max(1,round(reference[2]),min_w)
            min_h=widget.measure(Gtk.Orientation.VERTICAL,allocated_w)[0]
            allocated_h=max(1,round(reference[3]),min_h)
            point=Graphene.Point();point.init(x,y)
            transform=Gsk.Transform.new().translate(point).scale(w/allocated_w,h/allocated_h)
            widget.allocate(allocated_w,allocated_h,-1,transform)

        for tile in active & self.tile_set:
            i=tile.index;check=self.checks[i]
            check.set_active(i in self.selected)
            active=tile in rects and tile.get_child_visible() and check.get_visible()
            check.set_child_visible(active)
            if active:
                x,y,_,_,_=rects[tile]
                size=check.measure(Gtk.Orientation.HORIZONTAL,-1)[0]
                size=max(size,check.measure(Gtk.Orientation.VERTICAL,size)[0])
                point=Graphene.Point();point.init(x+6,y+6)
                check.allocate(size,size,-1,Gsk.Transform.new().translate(point))
        signature=(width,top,page,self.mode,self.expanded_month,self.expanded_year,id(stable))
        if signature!=self.window_signature:self.window_signature=signature;self.on_window()

    def visible_range(self):
        parent=self.get_parent()
        while parent and not isinstance(parent,Gtk.ScrolledWindow):parent=parent.get_parent()
        if parent:
            adjustment=parent.get_vadjustment()
            return adjustment.get_value(),max(1,adjustment.get_page_size())
        return 0,max(1,self.last_height)

    def do_snapshot(self,snapshot):
        tier=self.motion_kind=='tier' and self.p<1 and bool(self.tier_images)
        top,page=self.visible_range()
        for widget in getattr(self,'snapshot_widgets',[]):
            _,y,_,h,_=self.rendered[widget]
            if not widget.get_child_visible() or y+h<top or y>top+page:continue
            if tier and (widget in self.tile_set or widget in self.caption_widgets):continue
            self.snapshot_clipped(widget,snapshot)
        if tier:
            for _,images,old_clip,new_clip in self.tier_groups:
                x,y,w,h,_=(a+(b-a)*self.p for a,b in zip(old_clip,new_clip))
                group_clip=Graphene.Rect();group_clip.init(x,y,w,h);snapshot.push_clip(group_clip)
                for _,paintable,start,end in images:
                    x,y,w,h,opacity=(a+(b-a)*self.p for a,b in zip(start,end))
                    if w<=0 or h<=0 or opacity<=0 or y+h<top or y>top+page:continue
                    clip=Graphene.Rect();clip.init(x,y,w,h)
                    snapshot.save();snapshot.push_clip(clip);snapshot.push_opacity(opacity)
                    iw=max(1,paintable.get_intrinsic_width());ih=max(1,paintable.get_intrinsic_height());scale=max(w/iw,h/ih)
                    point=Graphene.Point();point.init(x+(w-iw*scale)/2,y+(h-ih*scale)/2);snapshot.translate(point)
                    paintable.snapshot(snapshot,iw*scale,ih*scale)
                    snapshot.pop();snapshot.pop();snapshot.restore()
                snapshot.pop()
            for widget in self.snapshot_widgets:
                _,y,_,h,_=self.rendered[widget]
                if widget in self.caption_widgets and widget.get_child_visible() and y+h>=top and y<=top+page:
                    self.snapshot_clipped(widget,snapshot)
        for tile in self.active_widgets & self.tile_set:
            i=tile.index;check=self.checks[i]
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
        self.snapshot_child(widget if isinstance(widget,Gtk.Widget) else widget.widget,snapshot)
        for _ in range(count):
            snapshot.pop()
