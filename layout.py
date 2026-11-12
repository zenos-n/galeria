"""Justified rows shared by the native widget and its geometry checks."""
from bisect import bisect_left,bisect_right
from datetime import datetime

MIN_TILE_SIZE=64


def prepare_timeline(items,buckets,width,target=154,query='',removed=(),mode='all',expanded_month=None,expanded_year=None):
    removed=set(removed)
    items=sorted({item.id:item for item in items if item.id not in removed}.values(),key=lambda item:item.created,reverse=True)
    asset_months={};months=[];previous=None
    for i,item in enumerate(items):
        period=(item.created.year,item.created.month)
        if period==previous:
            k,title,year,a,_=months[-1]
            months[-1]=(k,title,year,a,i+1)
        else:
            key=item.created.strftime('%Y-%m')
            months.append((key,item.created.strftime('%B %Y'),item.created.strftime('%Y'),i,i+1))
            previous=period
        asset_months[item.id]=key
    counts={}
    if buckets is not None:
        groups={month[0]:month for month in months}
        for bucket in buckets:
            key=bucket['timeBucket'][:7]
            counts[key]=counts.get(key,0)+bucket['count']
            groups.setdefault(key,(key,datetime.strptime(key,'%Y-%m').strftime('%B %Y'),key[:4],0,0))
        months=[groups[key] for key in sorted(groups,reverse=True)]
    rows={}
    groups=[(range(a,b),width) for _,_,_,a,b in months] if mode=='all' else []
    if mode=='months' and expanded_month:
        groups=[(range(a,b),width-32) for key,_,_,a,b in months if key==expanded_month]
    if mode=='years' and expanded_year:
        groups=[(tuple(i for _,_,year,a,b in months if year==expanded_year for i in range(a,b)),width-32)]
    for ids,row_width in groups:
        filtered=[i for i in ids if query.casefold() in items[i].filename.casefold()] if query else ids
        rows[(ids,row_width,target,query)]=(filtered,RowLayout([items[i].ratio for i in filtered],row_width,target))
    return {'items':items,'indices':{item.id:i for i,item in enumerate(items)},'asset_months':asset_months,'months':months,'bucket_counts':counts,'rows':rows}


class RowLayout:
    """Index whole rows; create per-photo rectangles only for the requested band."""
    def __init__(self,ratios,width,target=154,gap=3):
        self.ratios=[max(.05,float(ratio)) for ratio in ratios]
        self.width=width;self.gap=gap;self.rows=[];self.ys=[];self.height=0;self.max_height=0;self.closed=[]
        if not self.ratios or width<=0:return
        self.minimum=min(MIN_TILE_SIZE,max(1,int(width)))
        capacity=max(1,int((width+gap)//(self.minimum+gap)))
        start=0;total=0.;y=0
        def row(end,closed):
            nonlocal start,total,y
            height=max(self.minimum,round(min(target,(width-gap*(end-start-1))/total)))
            self.rows.append((start,end,y,height));self.ys.append(y);self.closed.append(closed)
            self.max_height=max(self.max_height,height)
            y+=height+gap;start=end;total=0.
        for index,ratio in enumerate(self.ratios):
            total+=ratio
            count=index-start+1
            if count>=capacity or total*target+gap*(count-1)>=width:row(index+1,True)
        if start<len(self.ratios):row(len(self.ratios),False)
        self.height=y-gap

    def visible(self,low,high):
        a=bisect_left(self.ys,low-self.max_height);b=bisect_right(self.ys,high)
        for row_index in range(a,b):
            start,end,y,height=self.rows[row_index]
            if y+height<low:continue
            available=int(self.width)-self.gap*(end-start-1)
            widths=[max(self.minimum,round(height*ratio)) for ratio in self.ratios[start:end]]
            used=available if self.closed[row_index] else min(available,sum(widths))
            weights=[width-self.minimum for width in widths]
            if not any(weights):weights=[1]*len(widths)
            total=sum(weights);extra=used-self.minimum*len(widths);cumulative=previous=0
            x=0
            for index,weight in zip(range(start,end),weights):
                cumulative+=weight;allocated=round(extra*cumulative/total)
                width=self.minimum+allocated-previous;previous=allocated
                yield index,x,y,width,height
                x+=width+self.gap


def justified_rows(ratios, width, target=154, gap=3):
    rows=RowLayout(ratios,width,target,gap)
    return list(rows.visible(0,rows.height))
