"""Account-local timeline rules; server media and raw caches stay unchanged."""
from collections import Counter
import hashlib
import json
import re
from pathlib import PurePath
from library import LibraryError


def screenshot_name(name):
    return bool(re.search(r'screen[\s_-]*shot',str(name),re.I))


def under_folder(path,folder):
    return bool(path and folder and (PurePath(path)==PurePath(folder) or PurePath(folder) in PurePath(path).parents))


def rules_for(preferences,identity):
    return preferences.get('timeline_visibility',{}).get(identity,{})


class TimelineVisibility:
    def __init__(self,rules=None):
        rules=rules or {}
        self.screenshots=bool(rules.get('screenshots',False))
        self.albums=frozenset(rules.get('albums',[]))
        self.folders=tuple(rules.get('folders',[]))
        self.ids=frozenset();self.counts={}
        self.on_progress=None
        self.enabled=bool(self.screenshots or self.albums or self.folders)
        digest=hashlib.sha256(json.dumps([self.screenshots,sorted(self.albums),self.folders]).encode()).hexdigest()
        self.cache_key='timeline-visibility:v2:'+digest

    def hidden(self,item):
        if item.id in self.ids:return True
        path=item.path or item.metadata.get('originalPath','')
        return (any(under_folder(path,folder) for folder in self.folders) or
                self.screenshots and (screenshot_name(item.filename) or any(screenshot_name(part) for part in PurePath(path).parts)))

    def filter(self,items):
        return [item for item in items if not self.hidden(item)] if self.enabled else items

    def buckets(self,client,buckets,cached=False):
        if not self.enabled:return buckets
        cache=client.media_cache()
        blob=cache.get(self.cache_key,None if cached else 300)
        try:snapshot=json.loads(blob) if blob else None
        except (ValueError,TypeError):snapshot=None
        if snapshot is not None and (not isinstance(snapshot,dict) or not isinstance(snapshot.get('items'),dict)):snapshot=None
        if self.albums or self.screenshots:
            if cached:
                blob=cache.get('albums')
                if blob is None:return None
                try:albums=json.loads(blob)
                except (ValueError,TypeError):return None
            else:albums=client.albums()
        else:albums=[]
        excluded=[album for album in albums if album['id'] in self.albums or self.screenshots and screenshot_name(album.get('albumName',''))]
        signature=json.dumps([buckets,[(a['id'],a.get('assetCount'),a.get('updatedAt')) for a in excluded]],sort_keys=True)
        if cached:
            if snapshot is None or snapshot.get('signature')!=signature:return None
        else:
            if snapshot is None or snapshot.get('signature')!=signature:
                found={};unscoped=set();checked=0
                def collect(filters,predicate=lambda item:True):
                    nonlocal checked
                    cursor=1;seen=set()
                    while cursor is not None:
                        position=(type(cursor),str(cursor))
                        if position in seen:raise LibraryError('Immich repeated a timeline filter page. Try refreshing the library.')
                        seen.add(position)
                        items,cursor=client.search(filters,page=cursor,size=1000)
                        checked+=len(items)
                        if self.on_progress:self.on_progress(checked)
                        for item in items:
                            if predicate(item):
                                found[item.id]=item.created.strftime('%Y-%m')
                                if filters.get('albumIds') and item.metadata.get('ownerId')!=client.user['id']:unscoped.add(item.id)
                                else:unscoped.discard(item.id)
                if excluded:collect({'albumIds':[album['id'] for album in excluded]})
                if self.screenshots:collect({'originalFileName':'screen'},lambda item:screenshot_name(item.filename))
                for folder in self.folders:collect({'originalPath':folder},lambda item,folder=folder:under_folder(item.metadata.get('originalPath',''),folder))
                # Shared albums can contain photos outside this user's main timeline.
                uncertain=sorted(unscoped)
                for id in uncertain:found.pop(id,None)
                if client.modern_search:
                    for start in range(0,len(uncertain),1000):collect({'id':uncertain[start:start+1000]})
                snapshot={'signature':signature,'items':found}
                cache.put(self.cache_key,json.dumps(snapshot).encode())
        self.ids=frozenset(snapshot['items']);self.counts=Counter(snapshot['items'].values())
        totals=Counter()
        for bucket in buckets:totals[bucket['timeBucket'][:7]]+=int(bucket['count'])
        return [{'timeBucket':key+'-01','count':count-self.counts.get(key,0)}
                for key,count in sorted(totals.items(),reverse=True) if count>self.counts.get(key,0)]

    def search(self,client,filters,page=1,size=100):
        result=[];seen=set();cursor=page
        while cursor is not None:
            position=(type(cursor),str(cursor))
            if position in seen:raise LibraryError('Immich repeated a timeline filter page. Try refreshing the library.')
            seen.add(position)
            items,cursor=client.search(filters,page=cursor,size=size)
            result.extend(self.filter(items))
            if len(result)>=size:break
        return result,cursor
