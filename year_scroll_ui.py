"""Native scrollbar with equal year segments and a hover/drag year hint."""
from gi.repository import Gdk,GLib,Gtk
from year_scroll import YearScale


class YearScrollbar(Gtk.Overlay):
    def __init__(self,window):
        super().__init__(visible=False,margin_top=8,margin_bottom=8,margin_end=3)
        self.window=window;self.model=YearScale({},0);self.years=();self.updating=False;self.pending=0
        self.hovered=False;self.held=False;self.pointer_y=0
        adjustment=Gtk.Adjustment(lower=0,upper=1,step_increment=.002,page_increment=.04,page_size=.04)
        self.bar=Gtk.Scrollbar(orientation=Gtk.Orientation.VERTICAL,adjustment=adjustment)
        self.bar.update_property([Gtk.AccessibleProperty.LABEL],['Browse by year'])
        self.set_child(self.bar)
        self.ticks=Gtk.DrawingArea(can_target=False)
        self.ticks.set_draw_func(self.draw_ticks);self.add_overlay(self.ticks)
        self.hint=Gtk.Label(margin_top=4,margin_bottom=4,margin_start=8,margin_end=8)
        self.popover=Gtk.Popover(child=self.hint,position=Gtk.PositionType.LEFT,
            autohide=False,has_arrow=False,can_target=False)
        self.popover.set_parent(self);self.popover.add_css_class('tooltip')
        adjustment.connect('value-changed',self.seek)
        motion=Gtk.EventControllerMotion()
        motion.connect('motion',self.motion)
        motion.connect('leave',self.leave);self.bar.add_controller(motion)
        events=Gtk.EventControllerLegacy(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        events.connect('event',self.pointer_event);self.bar.add_controller(events)
        scroll=window.scroller.get_vadjustment()
        scroll.connect('value-changed',self.queue_refresh);scroll.connect('changed',self.queue_refresh)

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
            if not enabled:self.popover.popdown()
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
        if not self.updating:self.window.scroller.get_vadjustment().set_value(self.model.scroll(fraction))
        if self.held:self.show_hint(fraction)

    def motion(self,_controller,_x,y):
        self.hovered=True;self.pointer_y=y
        if not self.held:self.show_hint((y/max(1,self.bar.get_height())-.02)/.96)

    def leave(self,*_):
        self.hovered=False
        if not self.held:self.popover.popdown()

    def pointer_event(self,_controller,event):
        if event.get_event_type()==Gdk.EventType.BUTTON_PRESS:
            self.held=True;self.show_hint(self.bar.get_adjustment().get_value()/.96)
        elif event.get_event_type()==Gdk.EventType.BUTTON_RELEASE:
            self.held=False
            if not self.hovered:self.popover.popdown()
        return False

    def show_hint(self,fraction):
        if not self.years:return
        fraction=max(0,min(1,fraction));index=min(len(self.years)-1,int(fraction*len(self.years)))
        self.hint.set_label(self.years[index])
        rect=Gdk.Rectangle();rect.x=0;rect.y=round((.02+.96*fraction)*max(1,self.get_height()-1));rect.width=1;rect.height=1
        self.popover.set_pointing_to(rect);self.popover.popup()

    def draw_ticks(self,widget,context,width,height):
        if not self.years:return
        color=widget.get_color();context.set_source_rgba(color.red,color.green,color.blue,.18)
        context.set_line_width(1)
        for index in range(1,len(self.years)):
            y=round((.02+.96*index/len(self.years))*height)+.5
            context.move_to(width*.25,y);context.line_to(width*.75,y)
        context.stroke()
