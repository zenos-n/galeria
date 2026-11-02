"""Web Mercator clustering in viewport pixels; no GTK or account data."""
import math


def normalized(latitude,longitude):
    latitude=max(-85.05112878,min(85.05112878,latitude))
    return ((longitude+180)/360)%1,(1-math.asinh(math.tan(math.radians(latitude)))/math.pi)/2


def location(x,y):return math.degrees(math.atan(math.sinh(math.pi*(1-2*y)))),(x%1)*360-180


def valid_points(values):
    points=[]
    for value in values:
        try:
            latitude=float(value.get('lat',value.get('latitude')));longitude=float(value.get('lon',value.get('longitude')))
            if not math.isfinite(latitude+longitude) or not -90<=latitude<=90 or not -180<=longitude<=180:continue
            points.append((str(value['id']),latitude,longitude))
        except (ValueError,TypeError,KeyError):continue
    return points


def clusters(points,latitude,longitude,zoom,width,height,tile_size=256,rotation=0,radius=64):
    world=tile_size*2**zoom;cx,cy=normalized(latitude,longitude)
    sine,cosine=math.sin(rotation),math.cos(rotation);groups={}
    for id,lat,lon in points:
        x,y=normalized(lat,lon);dx=((x-cx+.5)%1-.5)*world;dy=(y-cy)*world
        px=width/2+dx*cosine-dy*sine;py=height/2+dx*sine+dy*cosine
        if not -radius<=px<=width+radius or not -radius<=py<=height+radius:continue
        cell=math.floor(px/radius),math.floor(py/radius)
        group=None
        for gx in range(cell[0]-1,cell[0]+2):
            for gy in range(cell[1]-1,cell[1]+2):
                for candidate in groups.get((gx,gy),[]):
                    if math.hypot(px-candidate['px'],py-candidate['py'])<radius:
                        group=candidate;break
                if group:break
            if group:break
        if group is None:
            group={'ids':[],'x':0,'y':0,'px':px,'py':py}
            groups.setdefault(cell,[]).append(group)
        group['ids'].append(id);group['x']+=cx+dx/world;group['y']+=y
    result=[]
    for cell in groups.values():
        for group in cell:
            count=len(group['ids']);lat,lon=location(group['x']/count,group['y']/count)
            result.append({'ids':group['ids'],'latitude':lat,'longitude':lon})
    return result


def fit(points,width,height,tile_size=256):
    if not points:return 20,0,2
    xy=[normalized(lat,lon) for _,lat,lon in points];xs=sorted(x for x,_ in xy)
    gaps=[((xs[i+1] if i+1<len(xs) else xs[0]+1)-x,i) for i,x in enumerate(xs)]
    gap,index=max(gaps);span=0 if len(xs)==1 else 1-gap
    start=xs[(index+1)%len(xs)];ys=[y for _,y in xy]
    latitude,longitude=location(start+span/2,(min(ys)+max(ys))/2)
    scale=min(max(128,width-160)/(tile_size*max(span,1/8192)),max(128,height-160)/(tile_size*max(max(ys)-min(ys),1/8192)))
    return latitude,longitude,max(1,min(15,math.log2(scale)))
