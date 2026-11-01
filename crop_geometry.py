"""Normalized crop bounds, independent of GTK and image data."""

def drag_crop(bounds,handle,dx,dy,min_w=.04,min_h=.04,ratio=None):
    x0,y0,x1,y1=bounds
    clamp=lambda value,lo,hi:max(lo,min(hi,value))
    if handle=='move':
        dx=clamp(dx,-x0,1-x1);dy=clamp(dy,-y0,1-y1)
        return x0+dx,y0+dy,x1+dx,y1+dy
    left,top,right,bottom=x0,y0,x1,y1
    if 'w' in handle:left=clamp(x0+dx,0,x1-min_w)
    if 'e' in handle:right=clamp(x1+dx,x0+min_w,1)
    if 'n' in handle:top=clamp(y0+dy,0,y1-min_h)
    if 's' in handle:bottom=clamp(y1+dy,y0+min_h,1)
    if ratio:
        # Corner resizing keeps the opposite corner fixed and preserves aspect.
        width=max(min_w,(bottom-top)*ratio if abs(dy)>abs(dx)/ratio else right-left)
        height=width/ratio
        if height>1:
            height=1;width=height*ratio
        if 'n' in handle:
            height=min(height,bottom)
            top=bottom-height
        else:
            height=min(height,1-top)
            bottom=top+height
        width=height*ratio
        if 'w' in handle:
            width=min(width,right);left=right-width
        else:
            width=min(width,1-left);right=left+width
        height=width/ratio
        if 'n' in handle:top=bottom-height
        else:bottom=top+height
    return left,top,right,bottom
