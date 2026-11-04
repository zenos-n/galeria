"""Native scrollbar with equal year segments and a hover/drag year hint."""
from gi.repository import GLib,Graphene,Gtk
from year_scroll import YearScale


class YearScrollbar(Gtk.Overlay):
    def __init__(self,window):
        super().__init__(visible=False,halign=Gtk.Align.END,width_request=18,
            margin_top=8,margin_bottom=8,margin_end=2)
        self.window=window;self.model=YearScale({},0);self.years=();self.updating=False;self.pending=0
        self.hovered=False;self.held=False;self.pointer_y=0
        adjustment=Gtk.Adjustment(lower=0,upper=1,step_increment=.002,page_increment=.04,page_size=.04)
        self.bar=Gtk.Scrollbar(orientation=Gtk.Orientation.VERTICAL,adjustment=adjustment,
            halign=Gtk.Align.END,css_classes=['overlay-indicator','right'])
        self.bar.update_property([Gtk.AccessibleProperty.LABEL],['Browse by year'])
        self.set_child(self.bar)
        self.ticks=Gtk.DrawingArea(can_target=False,visible=False)
        self.ticks.set_draw_func(self.draw_ticks);self.add_overlay(self.ticks)
        self.hint=Gtk.Label(margin_top=5,margin_bottom=5,margin_start=9,margin_end=9,can_target=False)
        self.hint_card=Gtk.Box(visible=False,can_target=False,css_classes=['card','year-hint'])
        self.hint_card.append(self.hint)
        adjustment.connect('value-changed',self.seek)
        click=Gtk.GestureClick(button=1,propagation_phase=Gtk.PropagationPhase.CAPTURE)
        click.connect('pressed',self.pressed);click.connect('released',self.released)
        click.connect('unpaired-release',self.released)
        self.add_controller(click)
        scroll=window.scroller.get_vadjustment()
        scroll.connect('value-changed',self.queue_refresh);scroll.connect('changed',self.queue_refresh)

    def attach(self,view):
        self.hint_layer=Gtk.Fixed(can_target=False)
        self.hint_layer.put(self.hint_card,0,0);view.add_overlay(self.hint_layer)
        motion=Gtk.EventControllerMotion(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        def moved(controller,x,y):
            if not self.get_visible():return
            point=Graphene.Point();point.init(x,y)
            ok,point=view.compute_point(self,point)
            if not ok:return
            if self.held or 0<=point.x<=self.get_width() and 0<=point.y<=self.get_height():
                self.motion(controller,point.x,point.y)
            else:self.leave()
        motion.connect('motion',moved);motion.connect('leave',self.leave)
        view.add_controller(motion)

    def queue_refresh(self,*_):
        if not self.pending:self.pending=GLib.idle_add(self.refresh)

    def refresh(self,*_):
        self.pending=0
        window=self.window;mosaic=window.mosaic;scroll=window.scroller.get_vadjustment()
        maximum=max(0,scroll.get_upper()-scroll.get_page_size())
        enabled=mosaic.indexed and mosaic.mode=='all' and bool(mosaic.month_extents) and maximum>0
        if enabled!=self.get_visible():
            self.set_visible(enabled)
            window.scroller.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.EXTERNAL if enabled else Gtk.PolicyType.AUTOMATIC)
            if not enabled:
                self.hovered=self.held=False;self.engagement()
        if not enabled:return
        self.model=YearScale(mosaic.month_extents,maximum)
        self.years=tuple(year for year,_,_ in self.model.segments)
        self.updating=True
        self.bar.get_adjustment().set_value(self.model.fraction(scroll.get_value())*.96)
        self.updating=False
        self.ticks.queue_draw()
        if self.held:self.show_hint(self.bar.get_adjustment().get_value()/.96)

    def seek(self,*_):
        fraction=self.bar.get_adjustment().get_value()/.96
        if not self.updating:
            self.window.user_scrolled()
            scroll=self.window.scroller.get_vadjustment()
            self.model=YearScale(self.window.mosaic.month_extents,max(0,scroll.get_upper()-scroll.get_page_size()))
            scroll.set_value(self.model.scroll(fraction))
        if self.held:self.show_hint(fraction)

    def motion(self,_controller,_x,y):
        self.hovered=0<=_x<=self.get_width() and 0<=y<=self.get_height()
        self.pointer_y=max(0,min(self.get_height(),y));self.engagement()
        fraction=self.bar.get_adjustment().get_value()/.96 if self.held else (y/max(1,self.bar.get_height())-.02)/.96
        self.show_hint(fraction)

    def leave(self,*_):
        self.hovered=False
        self.engagement()

    def engagement(self):
        expanded=self.hovered or self.held
        self.bar.add_css_class('hovering') if expanded else self.bar.remove_css_class('hovering')
        self.bar.add_css_class('dragging') if self.held else self.bar.remove_css_class('dragging')
        self.ticks.set_visible(expanded)
        if not expanded:self.hint_card.set_visible(False)

    def pressed(self,_gesture,_count,_x,y):
        self.held=True;self.pointer_y=y;self.engagement()
        self.show_hint(self.bar.get_adjustment().get_value()/.96)

    def released(self,*_):
        self.held=False;self.engagement()

    def show_hint(self,fraction):
        if not self.years:return
        fraction=max(0,min(1,fraction));index=min(len(self.years)-1,int(fraction*len(self.years)))
        self.hint.set_label(self.years[index])
        point=Graphene.Point();point.init(0,self.pointer_y)
        ok,point=self.compute_point(self.hint_layer,point)
        if not ok:return
        self.hint_card.set_visible(True)
        width=self.hint_card.measure(Gtk.Orientation.HORIZONTAL,-1)[1]
        height=self.hint_card.measure(Gtk.Orientation.VERTICAL,width)[1]
        self.hint_layer.move(self.hint_card,max(4,point.x-width-8),
            max(4,min(self.hint_layer.get_height()-height-4,point.y-height/2)))

    def draw_ticks(self,widget,context,width,height):
        if not self.years:return
        color=widget.get_color();context.set_source_rgba(color.red,color.green,color.blue,.18)
        context.set_line_width(1)
        for index in range(1,len(self.years)):
            y=round((.02+.96*index/len(self.years))*height)+.5
            context.move_to(width*.25,y);context.line_to(width*.75,y)
        context.stroke()
