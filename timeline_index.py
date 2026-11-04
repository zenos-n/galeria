"""A complete scroll range, filled by compact month metadata before images."""
from dataclasses import replace
from datetime import datetime
from library import MediaItem


class TimelineIndex:
    def __init__(self,buckets):
        self.items=[];self.ranges={};self.loaded=set();self.failed={};self.refresh_keys=set()
        counts={}
        for bucket in buckets:counts[bucket['timeBucket'][:7]]=counts.get(bucket['timeBucket'][:7],0)+max(0,int(bucket['count']))
        for key in sorted(counts,reverse=True):
            start=len(self.items)
            for i in range(counts[key]):
                self.items.append(MediaItem(f'pending:{key}:{i}','Loading photo…',datetime.strptime(key,'%Y-%m'),1.5,
                    metadata={'placeholder':True,'timeline_slot':True,'visibility':'timeline'}))
            self.ranges[key]=(start,len(self.items))

    def apply(self,key,items):
        if key not in self.ranges:return False
        start,end=self.ranges[key];delta=len(items)-(end-start)
        self.items[start:end]=[replace(item,metadata={**item.metadata,'timeline_slot':True}) for item in items]
        self.ranges[key]=(start,start+len(items))
        if delta:
            for other,(a,b) in list(self.ranges.items()):
                if other!=key and a>=end:self.ranges[other]=(a+delta,b+delta)
        self.loaded.add(key);self.failed.pop(key,None)
        self.refresh_keys.discard(key)
        return bool(delta)

    def without(self,ids):
        ids=set(ids);result=object.__new__(TimelineIndex)
        result.items=[];result.ranges={};result.loaded=set(self.loaded);result.failed=dict(self.failed);result.refresh_keys=set(self.refresh_keys)
        for key,(a,b) in self.ranges.items():
            values=[item for item in self.items[a:b] if item.id not in ids]
            if values:
                start=len(result.items);result.items.extend(values);result.ranges[key]=(start,len(result.items))
        return result
