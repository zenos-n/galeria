"""Native controls for photo editing and the separate video editor."""
from gi.repository import Adw, Gtk
from panels import text, icon_button

from photo_edit import ADJUSTMENTS
from photo_markup import PALETTE
CATEGORIES = ['Crop','Adjust','Markup']


def snap_neutral(scale,scroll,value):
    adjustment=scale.get_adjustment()
    if scroll==Gtk.ScrollType.JUMP and abs(value)<=(adjustment.get_upper()-adjustment.get_lower())*.015:
        scale.set_value(0);return True
    return False


def build_editor(viewer):
    if getattr(viewer.source,'media_item',None) and viewer.source.media_item.kind=='VIDEO':
        from video_editor import VideoEditor
        viewer.video_editor=VideoEditor(viewer)
        return viewer.video_editor
    from photo_ui import PhotoEditor
    viewer.photo_editor=photo=PhotoEditor(viewer)
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
    box.add_css_class('editor-bar')
    categories=Adw.ToggleGroup(halign=Gtk.Align.CENTER)
    categories.add_css_class('round')
    for name in CATEGORIES:
        categories.add(Adw.Toggle(name=name,label=name))
    box.append(categories)
    stack=Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                    hhomogeneous=True,vhomogeneous=True,hexpand=True)
    stack.set_size_request(-1,148)
    viewer.editor_categories,viewer.editor_stack=categories,stack
    viewer.scales=[]
    viewer.editor_choices={}
    viewer.tool_message=text('', 'dim-label',halign=Gtk.Align.CENTER,visible=False)

    def notify(message):
        viewer.tool_message.set_label(message)
        viewer.tool_message.set_visible(bool(message))

    def add_page(name,widget):
        widget.set_valign(Gtk.Align.CENTER)
        widget.set_hexpand(True)
        widget.set_halign(Gtk.Align.FILL)
        stack.add_named(widget,name)

    def choices(names,key):
        flow=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=True,
                         min_children_per_line=2,max_children_per_line=min(8,len(names)),
                         row_spacing=6,column_spacing=6,halign=Gtk.Align.CENTER)
        flow.add_css_class('editor-tools')
        first=None
        controls=[]
        for name in names:
            column=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=7)
            icons={'Pen':'gallery-pencil-symbolic','Highlight':'gallery-marker-symbolic',
                   'Redact':'gallery-redact-symbolic','Text':'gallery-text-symbolic'}
            column.append(Gtk.Image(icon_name=icons[name],pixel_size=22,margin_top=4))
            column.append(text(name,wrap=True,justify=Gtk.Justification.CENTER))
            choice=Gtk.ToggleButton(child=column)
            choice.add_css_class('flat')
            choice.add_css_class('editor-choice')
            choice.set_tooltip_text(name)
            if first:
                choice.set_group(first)
            else:
                first=choice
                choice.set_active(True)
            controls.append(choice)
            def choose_tool(widget,name=name):
                if widget.get_active():photo.markup.tool=name;photo.markup.set_cursor_from_name('text' if name=='Text' else 'crosshair')
            choice.connect('toggled',choose_tool)
            flow.insert(choice,-1)
        viewer.editor_choices[key]=controls
        container=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,hexpand=True)
        container.append(flow)
        return container

    crop=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=18)
    tools=Gtk.Box(spacing=10,halign=Gtk.Align.CENTER)
    tools.append(icon_button('gallery-rotate-acw-symbolic','Rotate left',lambda _:viewer.rotate(-90)))
    tools.append(icon_button('gallery-rotate-cw-symbolic','Rotate right',lambda _:viewer.rotate(90)))
    tools.append(icon_button('gallery-flip-h-symbolic','Mirror',lambda _:viewer.flip()))
    tools.append(text('Aspect ratio',margin_start=8))
    dropdown=Gtk.DropDown.new_from_strings(['Free','Original','Square','4:3','16:9'])
    dropdown.set_selected(1)
    viewer.crop_dropdown=dropdown
    dropdown.connect('notify::selected',viewer.change_crop)
    tools.append(dropdown)
    crop.append(tools)
    straighten=Gtk.Box(spacing=14,halign=Gtk.Align.CENTER)
    straighten.append(text('Straighten'))
    scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,-45,45,.1)
    scale.set_size_request(270,-1)
    scale.set_value(0)
    scale.add_mark(0,Gtk.PositionType.BOTTOM,None)
    scale.connect('change-value',snap_neutral)
    photo.straighten_slider=scale
    def straighten_changed(widget):photo.straighten=widget.get_value();photo.queue()
    scale.connect('value-changed',straighten_changed)
    straighten.append(scale)
    crop.append(straighten)
    add_page('Crop',crop)
    adjust=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
    groups=Adw.ToggleGroup(halign=Gtk.Align.CENTER)
    groups.add_css_class('flat')
    for title in ['Light','Color','Detail']:
        groups.add(Adw.Toggle(name=title,label=title))
    adjust.append(groups)
    adjustment_pages=Gtk.Stack(hhomogeneous=True,vhomogeneous=True,hexpand=True)
    selections={}
    for name,names in [('Light',ADJUSTMENTS[:6]),('Color',ADJUSTMENTS[6:11]),('Detail',ADJUSTMENTS[11:])]:
        row=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=False,
                        min_children_per_line=2,max_children_per_line=6,
                        row_spacing=4,column_spacing=4,halign=Gtk.Align.CENTER)
        row.add_css_class('editor-tools')
        first=None
        selections[name]=names[0]
        for title in names:
            choice=Gtk.ToggleButton(label=title)
            choice.add_css_class('flat')
            choice.add_css_class('adjustment-choice')
            if first:
                choice.set_group(first)
            else:
                first=choice
                choice.set_active(True)
            row.insert(choice,-1)
            def selected(widget,title=title,group=name):
                if widget.get_active():selections[group]=title;photo.select(title)
            choice.connect('toggled',selected)
        adjustment_pages.add_named(row,name)
    def change_group(widget,_):
        adjustment_pages.set_visible_child_name(widget.get_active_name());photo.select(selections[widget.get_active_name()])
    groups.connect('notify::active-name',change_group)
    groups.set_active_name('Light')
    adjust.append(adjustment_pages)
    slider=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,-100,100,1)
    slider.set_size_request(360,-1)
    slider.set_halign(Gtk.Align.CENTER)
    slider.set_value(0)
    slider.set_draw_value(True)
    slider.set_round_digits(0)
    photo.slider=slider;photo.select('Brightness')
    slider.connect('change-value',snap_neutral)
    slider.connect('value-changed',photo.changed)
    viewer.scales.append(slider)
    adjust.append(slider)
    add_page('Adjust',adjust)
    markup=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=18)
    markup.append(choices(['Pen','Highlight','Redact','Text'],'Markup'))
    tools=Gtk.Box(spacing=10,halign=Gtk.Align.CENTER)
    viewer.color_swatches=[]
    for color in ['white','black','red','blue','yellow']:
        swatch=Gtk.ToggleButton(tooltip_text=color.title(),width_request=28,height_request=28,valign=Gtk.Align.CENTER)
        swatch.add_css_class('color-swatch')
        swatch.add_css_class('swatch-'+color)
        if viewer.color_swatches:swatch.set_group(viewer.color_swatches[0])
        else:swatch.set_active(True)
        swatch.connect('toggled',lambda widget,color=color:setattr(photo.markup,'color',PALETTE[color]) if widget.get_active() else None)
        viewer.color_swatches.append(swatch)
        frame=Gtk.AspectFrame(child=swatch,ratio=1,obey_child=False,halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER)
        tools.append(frame)
    entry=Gtk.Entry(placeholder_text='Add text',width_chars=14,max_length=256)
    entry.connect('changed',lambda widget:setattr(photo.markup,'text',widget.get_text()));tools.append(entry)
    photo.undo=Gtk.Button(label='Undo',sensitive=False)
    photo.undo.connect('clicked',lambda _:photo.markup.undo());tools.append(photo.undo)
    markup.append(tools)
    add_page('Markup',markup)
    clamp=Adw.Clamp(maximum_size=850,tightening_threshold=650,child=stack,hexpand=True)
    box.append(clamp)
    box.append(viewer.tool_message)
    footer=Gtk.Box(spacing=8,halign=Gtk.Align.CENTER)
    reset=Gtk.Button(label='Reset')
    reset.connect('clicked',lambda _:viewer.reset_edits())
    compare=Gtk.ToggleButton(label='Compare',tooltip_text='Compare with original')
    photo.compare_button=compare
    compare.connect('toggled',lambda w:photo.compare(w.get_active()))
    for widget in [reset,compare]:
        footer.append(widget)
    photo.save_button=Gtk.Button(label='Save a copy…',sensitive=False,css_classes=['suggested-action'])
    photo.save_button.connect('clicked',lambda _:photo.save_copy());footer.append(photo.save_button)
    box.append(footer)

    def switch_category(group,_):
        stack.set_visible_child_name(group.get_active_name())
        viewer.stage.crop_frame.set_visible(viewer.editing and group.get_active_name()=='Crop')
        photo.category_changed()
        notify('')
    categories.connect('notify::active-name',switch_category)
    categories.set_active_name('Crop')
    return box
