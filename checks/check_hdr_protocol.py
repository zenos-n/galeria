"""Check actual Wayland output: SDR parents and HDR-tagged media children."""
import re,json,sys
from pathlib import Path


def check(path):
    creators={};descriptions={};surfaces={};roots=set();children={};states={};attached=set();formats={};buffers={}
    checks=[];root_assignments=0
    for line in Path(path).read_text().splitlines():
        m=re.search(r'wp_image_description_creator_params_v1#(\d+)\.set_(primaries|tf)_named\((\d+)\)',line)
        if m:creators.setdefault(m[1],{})[m[2]]=int(m[3])
        m=re.search(r'wp_image_description_creator_params_v1#(\d+)\.create\(new id wp_image_description_v1#(\d+)\)',line)
        if m:descriptions[m[2]]=dict(creators.get(m[1],{}))
        m=re.search(r'get_surface\(new id wp_color_management_surface_v1#(\d+), wl_surface#(\d+)\)',line)
        if m:surfaces[m[1]]=m[2]
        m=re.search(r'get_xdg_surface\(new id xdg_surface#\d+, wl_surface#(\d+)\)',line)
        if m:roots.add(m[1])
        m=re.search(r'get_subsurface\(new id wl_subsurface#\d+, wl_surface#(\d+), wl_surface#(\d+)\)',line)
        if m:children[m[1]]=m[2]
        m=re.search(r'wp_color_management_surface_v1#(\d+)\.set_image_description\(wp_image_description_v1#(\d+),',line)
        if m:
            surface=surfaces[m[1]];state=descriptions[m[2]];states[surface]=state
            if surface in roots:
                assert state=={'primaries':1,'tf':9},('UI parent is not sRGB',surface,state)
                root_assignments+=1
        m=re.search(r'wl_shm_pool#\d+\.create_buffer\(new id wl_buffer#(\d+), (?:-?\d+, ){4}(\d+)\)',line)
        if m:buffers[m[1]]=int(m[2])
        m=re.search(r'zwp_linux_buffer_params_v1#\d+\.create_immed\(new id wl_buffer#(\d+), \d+, \d+, (\d+),',line)
        if m:buffers[m[1]]=int(m[2])
        m=re.search(r'wl_surface#(\d+)\.attach\((nil|wl_buffer#\d+),',line)
        if m:
            surface,buffer=m.groups()
            if buffer=='nil':attached.discard(surface)
            else:attached.add(surface);formats[surface]=buffers.get(buffer.split('#')[1])
        m=re.search(r'wl_surface#(\d+)\.destroy\(',line)
        if m:attached.discard(m[1]);states.pop(m[1],None);children.pop(m[1],None)
        m=re.search(r'SURFACE SETTLED (\S+)',line)
        if m:
            name=m[1]
            for surface in roots & attached:
                assert formats.get(surface) in (0,1,875713089,875713112,875708993,875709016),('UI buffer is not 8-bit',surface,formats.get(surface))
            hdr=[(s,state,formats.get(s)) for s,state in states.items() if s in attached and s in children and state.get('tf')==11]
            if name.startswith(('pq.','hlg.')):
                assert hdr,('HDR media has no PQ subsurface',name)
                if name.endswith('.png'):assert any(f==1211384385 for _,_,f in hdr),('Photo is not RGBA16F',name,hdr)
            else:assert not hdr,('SDR media created an HDR subsurface',name,hdr)
            checks.append(name)
    assert root_assignments and len(checks)>=5,(root_assignments,checks)
    return {'sdr_parent_assignments':root_assignments,'media_checks':checks}


if __name__=='__main__':print(json.dumps(check(sys.argv[1])))
