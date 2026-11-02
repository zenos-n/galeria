"""Restore ordinary timeline metadata and visible thumbnail pixels without HTTP."""
from imaging import decode_image
from layout import justified_rows
from timeline_index import TimelineIndex
from library import LibraryError


def restore(client,width,height,target=154):
    try:
        buckets=client.time_buckets(cached=True)
        if not buckets:return None
        index=TimelineIndex(buckets)
    except (LibraryError,ValueError,TypeError,KeyError):return None
    for key in list(index.ranges):
        try:items=client.time_bucket(key,cached=True)
        except (LibraryError,ValueError,TypeError):continue
        if items is not None:index.apply(key,items)
    if not index.loaded:return None
    pixels={};y=0;cache=client.media_cache()
    for key,(a,b) in index.ranges.items():
        y+=40
        rows=justified_rows([item.ratio for item in index.items[a:b]],max(200,width),target)
        for offset,x,dy,w,h in rows:
            item=index.items[a+offset]
            if y+dy>height*3:break
            if item.metadata.get('placeholder'):continue
            data=cache.get(client.image_key(item))
            if data:
                try:pixels[item.id]=decode_image(data)
                except (OSError,ValueError):pass
        y+=max((dy+h for _,_,dy,_,h in rows),default=0)+12
        if y>height*3:break
    return buckets,index,pixels
