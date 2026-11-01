"""Editor layout preview. No file reads or image processing."""
from gi.repository import Adw, Gtk
from panels import text, icon_button

CATEGORIES = ['Suggestions','Crop','Adjust','Filters','Markup','Actions']
ADJUSTMENTS = ['Brightness','Contrast','White point','Highlights','Shadows','Black point',
               'Saturation','Warmth','Tint','Skin tone','Blue tone','Pop','Sharpen','Denoise','Vignette','HDR effect']
ACTIONS = ['Magic Eraser','Unblur','Portrait blur','Portrait light','Color focus','Sky','Best Take','Auto frame']


def build_editor(viewer):
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

    def choices(names,key,previews=False,icon='gallery-magic-wand-symbolic'):
        flow=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=True,
                         min_children_per_line=2,max_children_per_line=min(8,len(names)),
                         row_spacing=6,column_spacing=6,halign=Gtk.Align.CENTER)
        first=None
        controls=[]
        for i,name in enumerate(names):
            column=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=7)
            if previews:
                image=Gtk.Image(icon_name='gallery-image-symbolic',pixel_size=24,
                                width_request=70,height_request=48)
                image.add_css_class('filter-preview')
                image.add_css_class(f'shade-{i%5}')
                column.append(image)
            elif key=='Actions':
                column.append(Gtk.Image(icon_name=icon,pixel_size=22,margin_top=4))
            column.append(text(name,wrap=True,justify=Gtk.Justification.CENTER))
            choice=Gtk.ToggleButton(child=column)
            choice.add_css_class('flat')
            choice.add_css_class('editor-choice')
            if first:
                choice.set_group(first)
            else:
                first=choice
                choice.set_active(True)
            controls.append(choice)
            flow.insert(choice,-1)
        viewer.editor_choices[key]=controls
        container=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,hexpand=True)
        container.append(flow)
        return container

    add_page('Suggestions',choices(['Original','Enhance','Dynamic','AI Enhance'],'Suggestions',True))
    crop=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=18)
    tools=Gtk.Box(spacing=10,halign=Gtk.Align.CENTER)
    tools.append(icon_button('gallery-rotate-acw-symbolic','Rotate left',lambda _:viewer.rotate(-90)))
    tools.append(icon_button('gallery-rotate-cw-symbolic','Rotate right',lambda _:viewer.rotate(90)))
    tools.append(icon_button('gallery-flip-h-symbolic','Mirror',lambda _:viewer.flip()))
    tools.append(text('Aspect ratio',margin_start=8))
    dropdown=Gtk.DropDown.new_from_strings(['Original','Square','4:3','16:9'])
    viewer.crop_dropdown=dropdown
    dropdown.connect('notify::selected',viewer.change_crop)
    tools.append(dropdown)
    tools.append(Gtk.Button(label='Perspective'))
    crop.append(tools)
    straighten=Gtk.Box(spacing=14,halign=Gtk.Align.CENTER)
    straighten.append(text('Straighten'))
    scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,-45,45,1)
    scale.set_size_request(270,-1)
    scale.set_value(0)
    straighten.append(scale)
    crop.append(straighten)
    add_page('Crop',crop)
    adjust=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
    tool_row=Gtk.Box(spacing=4,halign=Gtk.Align.CENTER)
    groups=Adw.ToggleGroup(halign=Gtk.Align.CENTER)
    groups.add_css_class('flat')
    for title in ['Light','Color','Detail']:
        groups.add(Adw.Toggle(name=title,label=title))
    adjust.append(groups)
    adjustment_pages=Gtk.Stack(hhomogeneous=True,vhomogeneous=True,hexpand=True)
    for name,names in [('Light',ADJUSTMENTS[:6]),('Color',ADJUSTMENTS[6:11]),('Detail',ADJUSTMENTS[11:])]:
        row=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=False,
                        min_children_per_line=2,max_children_per_line=6,
                        row_spacing=4,column_spacing=4,halign=Gtk.Align.CENTER)
        first=None
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
        adjustment_pages.add_named(row,name)
    groups.connect('notify::active-name',lambda w,_:adjustment_pages.set_visible_child_name(w.get_active_name()))
    groups.set_active_name('Light')
    adjust.append(adjustment_pages)
    slider=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,-100,100,1)
    slider.set_size_request(360,-1)
    slider.set_halign(Gtk.Align.CENTER)
    slider.set_value(0)
    slider.set_draw_value(True)
    slider.connect('value-changed',lambda _:viewer.adjust())
    viewer.scales.append(slider)
    adjust.append(slider)
    add_page('Adjust',adjust)
    add_page('Filters',choices(['Original','Vivid','Warm','Cool','Mono','Noir'],'Filters',True))
    markup=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=18)
    markup.append(choices(['Pen','Highlight','Redact','Text'],'Markup'))
    tools=Gtk.Box(spacing=10,halign=Gtk.Align.CENTER)
    viewer.color_swatches=[]
    for color in ['white','black','red','blue','yellow']:
        swatch=Gtk.ToggleButton(tooltip_text=color.title(),width_request=28,height_request=28,valign=Gtk.Align.CENTER)
        swatch.add_css_class('color-swatch')
        swatch.add_css_class('swatch-'+color)
        viewer.color_swatches.append(swatch)
        frame=Gtk.AspectFrame(child=swatch,ratio=1,obey_child=False,halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER)
        tools.append(frame)
    tools.append(Gtk.Entry(placeholder_text='Add text',width_chars=14))
    markup.append(tools)
    add_page('Markup',markup)
    add_page('Actions',choices(ACTIONS,'Actions'))
    clamp=Adw.Clamp(maximum_size=850,tightening_threshold=650,child=stack,hexpand=True)
    box.append(clamp)
    box.append(viewer.tool_message)
    footer=Gtk.Box(spacing=8,halign=Gtk.Align.CENTER)
    reset=Gtk.Button(label='Reset')
    reset.connect('clicked',lambda _:viewer.reset_edits())
    compare=Gtk.ToggleButton(label='Compare',tooltip_text='Compare with original')
    compare.connect('toggled',lambda w:viewer.stage.surface.set_visible(not w.get_active()))
    for widget in [reset,compare]:
        footer.append(widget)
    for title in ['Save a copy','Save']:
        save=Gtk.Button(label=title)
        if title=='Save':
            save.add_css_class('suggested-action')
        save.connect('clicked',lambda _:notify('Design preview · image files are not changed.'))
        footer.append(save)
    box.append(footer)

    def switch_category(group,_):
        stack.set_visible_child_name(group.get_active_name())
        viewer.stage.crop_frame.set_visible(viewer.editing and group.get_active_name()=='Crop')
        notify('')
    categories.connect('notify::active-name',switch_category)
    categories.set_active_name('Suggestions')
    return box
