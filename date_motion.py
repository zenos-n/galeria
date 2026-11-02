"""Group visible source photos into their containing month or year."""
from collections import defaultdict,deque


def cover_area(rect):
    x,y,w,h,*_=rect
    return x+5,y+5,max(1,w-10),max(1,h-39),1


def cover_slot(rect,index):
    x,y,w,h,_=cover_area(rect);w=(w-2)/2;h=(h-2)/2
    return x+(index%2)*(w+2),y+(index//2)*(h+2),w,h,1


def union(rects):
    x=min(rect[0] for rect in rects);y=min(rect[1] for rect in rects)
    return x,y,max(rect[0]+rect[2] for rect in rects)-x,max(rect[1]+rect[3] for rect in rects)-y,1


def groups(sources,destinations,months,mode,cards):
    result={};available=defaultdict(deque);used=set()
    for i,(id,paintable,rect) in enumerate(sources):available[id].append((i,rect))
    def key(id):
        month=months.get(id,'')
        return month[:4] if mode=='years' else month
    for id,paintable,end in destinations:
        group=result.setdefault(key(id),[])
        if available[id]:i,start=available[id].popleft();used.add(i)
        else:
            # A revealed photo starts inside the containing date cover.
            card=cards.get(('source',id))
            start=cover_slot(card,len(group)%4) if card else end
            start=(*start[:4],0)
        group.append((id,paintable,start,end))
    for i,(id,paintable,start) in enumerate(sources):
        if i in used:continue
        group=result.setdefault(key(id),[]);card=cards.get(key(id))
        end=cover_slot(card,len(group)%4) if card else start
        group.append((id,paintable,start,(*end[:4],0)))
    return [(key,images,union([image[2] for image in images]),cover_area(cards[key]) if key in cards else union([image[3] for image in images])) for key,images in result.items() if images]
