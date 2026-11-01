"""Editor tool layout for design review; no image-processing backend."""
from gi.repository import Adw, Gtk
from panels import text, icon_button

CATEGORIES = ['Suggestions','Crop','Adjust','Filters','Markup','Actions','Ask']
ADJUSTMENTS = ['Brightness','Contrast','White point','Highlights','Shadows','Black point',
               'Saturation','Warmth','Tint','Skin tone','Blue tone','Pop','Sharpen','Denoise','Vignette','HDR effect']
ACTIONS = ['Magic Eraser','Unblur','Portrait blur','Portrait light','Color focus','Sky','Best Take','Auto frame']


def build_editor(viewer):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
    box.add_css_class('editor-bar')
    categories = Adw.ToggleGroup(halign=Gtk.Align.CENTER)
    categories.add_css_class('round')
    for title in CATEGORIES:
        categories.add(Adw.Toggle(name=title,label=title))
    category_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
                                         vscrollbar_policy=Gtk.PolicyType.NEVER)
    category_scroll.set_child(categories)
    box.append(category_scroll)
    stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,hhomogeneous=False,vhomogeneous=False)
    stack.set_size_request(-1,125)
    viewer.editor_categories, viewer.editor_stack = categories, stack
    viewer.scales=[]

    def add_page(name,widget):
        widget.set_halign(Gtk.Align.CENTER)
        stack.add_named(widget,name)

    def chips(names,callback,previews=False):
        row=Gtk.Box(spacing=8,halign=Gtk.Align.CENTER)
        for i,name in enumerate(names):
            child=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
            if previews:
                tile=Gtk.Image(icon_name='gallery-image-symbolic',pixel_size=24,width_request=62,height_request=50)
                tile.add_css_class('filter-preview')
                tile.add_css_class(f'shade-{i%5}')
                child.append(tile)
            child.append(text(name))
            choice=Gtk.Button(child=child)
            choice.add_css_class('flat')
            choice.connect('clicked',lambda _,value=name:callback(value))
            row.append(choice)
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,vscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(row)
        return scroll

    suggestions=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
    suggestions.append(chips(['Original','Enhance','Dynamic','AI Enhance'],lambda name:viewer.tool_message.set_label(name+' selected'),True))
    add_page('Suggestions',suggestions)
    crop=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
    tools=Gtk.Box(spacing=10,halign=Gtk.Align.CENTER)
    tools.append(icon_button('gallery-rotate-acw-symbolic','Rotate left',lambda _:viewer.rotate(-90)))
    tools.append(icon_button('gallery-rotate-cw-symbolic','Rotate right',lambda _:viewer.rotate(90)))
    tools.append(icon_button('gallery-flip-h-symbolic','Mirror',lambda _:viewer.flip()))
    tools.append(text('Aspect ratio',margin_start=10))
    dropdown=Gtk.DropDown.new_from_strings(['Original','Square','4:3','16:9'])
    viewer.crop_dropdown=dropdown
    dropdown.connect('notify::selected',viewer.change_crop)
    tools.append(dropdown)
    perspective=Gtk.Button(label='Perspective')
    perspective.connect('clicked',lambda _:viewer.tool_message.set_label('Drag the corners to adjust perspective.'))
    tools.append(perspective)
    crop.append(tools)
    straighten=Gtk.Box(spacing=12,halign=Gtk.Align.CENTER)
    straighten.append(text('Straighten'))
    scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,-45,45,1)
    scale.set_size_request(270,-1)
    scale.set_value(0)
    straighten.append(scale)
    crop.append(straighten)
    add_page('Crop',crop)
    adjust=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
    adjustment=Gtk.DropDown.new_from_strings(ADJUSTMENTS)
    adjustment.set_halign(Gtk.Align.CENTER)
    adjust.append(adjustment)
    slider=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,-100,100,1)
    slider.set_size_request(370,-1)
    slider.set_value(0)
    slider.set_draw_value(True)
    slider.connect('value-changed',lambda _:viewer.adjust())
    viewer.scales.append(slider)
    adjust.append(slider)
    add_page('Adjust',adjust)
    filters=chips(['Original','Vivid','Warm','Cool','Mono','Noir'],lambda name:viewer.tool_message.set_label(name+' filter selected'),True)
    add_page('Filters',filters)
    markup=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
    markup.append(chips(['Pen','Highlight','Redact','Text'],lambda name:viewer.tool_message.set_label(name+' · draw or tap on the photo.')))
    markup_tools=Gtk.Box(spacing=12,halign=Gtk.Align.CENTER)
    for color in ['white','black','red','blue','yellow']:
        color_button=Gtk.Button(tooltip_text=color.title())
        color_button.add_css_class('circular')
        color_button.add_css_class('swatch-'+color)
        markup_tools.append(color_button)
    markup_tools.append(Gtk.Entry(placeholder_text='Add text',width_chars=14))
    markup.append(markup_tools)
    add_page('Markup',markup)
    actions=chips(ACTIONS,lambda name:viewer.tool_message.set_label(name+' · select an area or subject.'))
    add_page('Actions',actions)
    ask=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
    ask.append(text('Describe the edit you want',xalign=0))
    ask_line=Gtk.Box(spacing=8)
    ask_line.append(Gtk.Entry(placeholder_text='Remove a distraction, change the lighting…',hexpand=True,width_chars=42))
    apply=Gtk.Button(label='Apply')
    apply.add_css_class('suggested-action')
    apply.connect('clicked',lambda _:viewer.tool_message.set_label('Conversational editing is a UI preview. No service is connected.'))
    ask_line.append(apply)
    ask.append(ask_line)
    add_page('Ask',ask)
    categories.connect('notify::active-name',lambda w,_:(stack.set_visible_child_name(w.get_active_name()),
                       viewer.stage.crop_frame.set_visible(viewer.editing and w.get_active_name()=='Crop')))
    categories.set_active_name('Suggestions')
    box.append(stack)
    viewer.tool_message=text('', 'dim-label',halign=Gtk.Align.CENTER)
    box.append(viewer.tool_message)
    footer=Gtk.Box(spacing=8,halign=Gtk.Align.CENTER)
    reset=Gtk.Button(label='Reset')
    reset.connect('clicked',lambda _:viewer.reset_edits())
    compare=Gtk.ToggleButton(label='Compare',tooltip_text='Compare with original')
    compare.connect('toggled',lambda w:viewer.stage.surface.set_visible(not w.get_active()))
    copy=Gtk.Button(label='Save a copy')
    save=Gtk.Button(label='Save')
    save.add_css_class('suggested-action')
    for widget in (copy,save):
        widget.connect('clicked',lambda _:viewer.tool_message.set_label('Design preview · image files are not changed.'))
    for widget in (reset,compare,copy,save):
        footer.append(widget)
    box.append(footer)
    return box
