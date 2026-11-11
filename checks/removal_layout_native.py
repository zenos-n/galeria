"""In-place removal keeps grouped layouts equivalent to a fresh grid."""
import os,sys
from datetime import datetime,timedelta
from pathlib import Path
assert os.environ.get('DISPLAY')==':91'
sys.path.insert(0,os.environ.get('GALERIA_CHECK_SOURCE_ROOT',str(Path(__file__).resolve().parents[1])))
from app import *
from library import MediaItem
from layout import prepare_timeline

def geometry(mosaic):
    names={tile:('media',tile.media_item.id) for tile in mosaic.tiles}
    names.update({widget:('month',key) for key,widget in mosaic.month_cards.items()})
    names.update({widget:('year',key) for key,widget in mosaic.year_cards.items()})
    names.update({widget:('heading',month[0]) for month,widget in zip(mosaic.months,mosaic.headings)})
    for name in ('panel_month','panel_year','pointer_month','pointer_year','loading'):
        names[getattr(mosaic,name)]=(name,)
    rects,height=mosaic.target_layout(900)
    return {names[widget]:rect for widget,rect in rects.items()},height

items=[MediaItem(str(i),'Photo '+str(i),datetime(2026,11,3)-timedelta(days=i*4),.6+(i%7)/4) for i in range(120)]
for mode in ('all','months','years'):
    for removed in ({'1','3'},{str(i) for i in range(10)}):
        current=Mosaic(lambda *_:None,items)
        current.mode=mode;current.expanded_month='2026-10' if mode=='months' else None;current.expanded_year='2026' if mode=='years' else None
        current.target_layout(900)
        retained={tile.media_item.id:tile for tile in current.tiles if tile.media_item.id not in removed}
        plan=prepare_timeline(items,None,900,removed=removed,mode=mode,expanded_month=current.expanded_month,expanded_year=current.expanded_year)
        assert current.apply_removal(plan)
        expected=Mosaic(lambda *_:None,plan['items'])
        expected.mode=mode;expected.expanded_month=current.expanded_month;expected.expanded_year=current.expanded_year
        assert geometry(current)==geometry(expected),(mode,removed)
        assert all(retained[tile.media_item.id] is tile and tile.index==i and current.checks[i].index==i for i,tile in enumerate(current.tiles))
        for tile in current.tiles:
            key=tile.media_item.created.strftime('%Y-%m')
            assert current.owners[tile]==(current.month_cards[key],current.year_cards[key[:4]])
        assert not (set(retained.values()) ^ current.tile_set)
        assert all(tile in current.tile_set for tile in current.owners if hasattr(tile,'media_item'))
        # A second compaction followed by metadata hydration must keep click/check indices aligned.
        assert current.apply_removal(prepare_timeline(current.items,None,900,removed={'11','13'},mode=mode,expanded_month=current.expanded_month,expanded_year=current.expanded_year))
        from dataclasses import replace
        key,_,_,a,b=next(month for month in current.months if month[4]>month[3])
        current.update_bucket(key,[replace(item,id='hydrated:'+item.id) for item in current.items[a:b]])
        assert all(tile.index==i and current.checks[i].index==i for i,tile in enumerate(current.tiles))
        current.dispose();expected.dispose()
print('IN-PLACE ALL/MONTH/YEAR GEOMETRY, EMPTY MONTH PRUNING, RETAINED CELLS AND CHECK INDICES PASSED',flush=True)

# Removing files above the viewport preserves the visible anchor's pixel offset.
import time
window=Gtk.Window(default_width=900,default_height=600)
scroller=Gtk.ScrolledWindow();window.set_child(scroller)
mosaic=Mosaic(lambda *_:None,items);scroller.set_child(mosaic);window.present()
context=GLib.MainContext.default()
def pump(test):
    end=time.monotonic()+5
    while not test():
        assert time.monotonic()<end
        context.iteration(False);time.sleep(.003)
pump(lambda:window.get_mapped() and bool(mosaic.rendered))
adjustment=scroller.get_vadjustment();adjustment.connect('value-changed',lambda *_:mosaic.queue_allocate());adjustment.set_value(1700)
pump(lambda:any(tile in mosaic.rendered and mosaic.rendered[tile][1]+mosaic.rendered[tile][3]>=1700 for tile in mosaic.active_widgets & mosaic.tile_set))
anchor=min((tile for tile in mosaic.active_widgets & mosaic.tile_set if tile in mosaic.rendered and mosaic.rendered[tile][1]+mosaic.rendered[tile][3]>=1700),key=lambda tile:(mosaic.rendered[tile][1],mosaic.rendered[tile][0]))
offset=adjustment.get_value()-mosaic.rendered[anchor][1]
assert mosaic.apply_removal(prepare_timeline(items,None,mosaic.last_width,removed={'0','1','2'}))
target=mosaic.target_layout(mosaic.last_width)[0]
top,page=mosaic.visible_range()
for heading in mosaic.headings:
    if heading in target and heading not in mosaic.from_map and target[heading][1]>top+page*2:
        assert heading not in mosaic.motion_widgets,'Offscreen date label animated during removal'
pump(lambda:not mosaic.tick and not mosaic.cell_build_tick)
assert abs(adjustment.get_value()-mosaic.rendered[anchor][1]-offset)<2
print('SCROLLED REMOVAL KEEPS VISIBLE ANCHOR OFFSET PASSED',flush=True)

# Existing layout work must not exhaust the budget before any controls are built.
positions=mosaic.positions
def slow_positions(width):
    time.sleep(.004)
    return positions(width)
mosaic.positions=slow_positions
for tile in mosaic.active_widgets & mosaic.tile_set:
    tile.release();mosaic.checks[tile.index].dispose()
mosaic.incremental_cells=True;mosaic.set_selection(True);mosaic.queue_allocate()
pump(lambda:not mosaic.incremental_cells and all(tile.button and mosaic.checks[tile.index].widget for tile in mosaic.active_widgets & mosaic.tile_set))
mosaic.dispose();window.destroy()
print('CONTROL BUILDING PROGRESSES AFTER EXPENSIVE EXISTING LAYOUT PASSED',flush=True)
