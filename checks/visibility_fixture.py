"""Small read-only Immich metadata fixture for timeline visibility checks."""
from datetime import datetime
from io import BytesIO
from urllib.parse import urlsplit,parse_qs
import threading
from library import ImmichClient


class Client(ImmichClient):
    def __init__(self):
        super().__init__('https://fixture.invalid')
        self.user={'id':'viewer','name':'Fixture'};self.token='fixture'
        self.assets=[];self.calls=[];self.gate=threading.Event();self.gate.set();self.waiting=threading.Event()
        self.album_values=[{'id':'screens','albumName':'Pictures / Screenshots','assetCount':2,'updatedAt':'1'},
                           {'id':'hidden','albumName':'Downloads','assetCount':2,'updatedAt':'1'}]
        for id,name,date,albums in [('camera','camera.jpg','2026-11-20',[]),('shot','Screenshot.png','2026-11-19',['screens','hidden']),
                ('numeric','123.png','2026-10-01',['screens']),('download','saved.jpg','2026-11-18',['hidden']),
                ('ancient','Screen Shot 2000.png','2000-01-01',[])]:
            self.assets.append({'id':id,'originalFileName':name,'fileCreatedAt':date+'T12:00:00Z','localDateTime':date+'T12:00:00',
                                'type':'IMAGE','visibility':'timeline','width':150,'height':100,'albums':albums,'ownerId':'viewer'})

    def request(self,path,body=None,method=None,binary=False):
        self.calls.append((path,body,method))
        if path=='/albums':return self.album_values
        parts=urlsplit(path)
        if parts.path.startswith('/assets/'):
            id=parts.path.split('/')[2]
            return next(asset for asset in self.assets if asset['id']==id)
        if parts.path=='/timeline/buckets':
            counts={}
            for asset in self.assets:
                if asset.get('ownerId','viewer')!='viewer':continue
                key=asset['fileCreatedAt'][:7]+'-01';counts[key]=counts.get(key,0)+1
            return [{'timeBucket':key,'count':count} for key,count in sorted(counts.items(),reverse=True)]
        if parts.path=='/timeline/bucket':
            month=parse_qs(parts.query)['timeBucket'][0][:7]
            values=[asset for asset in self.assets if asset['fileCreatedAt'].startswith(month) and asset.get('ownerId','viewer')=='viewer']
            return {'id':[a['id'] for a in values],'ratio':[1.5]*len(values),'fileCreatedAt':[a['fileCreatedAt'] for a in values],
                    'isImage':[True]*len(values),'visibility':['timeline']*len(values)}
        if path=='/search/metadata':
            self.waiting.set();assert self.gate.wait(8),'Fixture metadata not released'
            filters=body.get('filter',{});values=[]
            for asset in self.assets:
                if not filters.get('albumIds') and asset.get('ownerId','viewer')!='viewer':continue
                if 'albumIds' in filters and not set(asset['albums']) & set(filters['albumIds']['any']):continue
                if 'or' in filters and asset['id'] not in {entry['id']['eq'] for entry in filters['or']}:continue
                if any(key in filters and filters[key]['like'].strip('%').casefold() not in asset.get(key,'').casefold() for key in ('originalFileName','originalPath')):continue
                if 'takenAt' in filters:
                    date=asset['fileCreatedAt'];taken=filters['takenAt']
                    if date<taken.get('gte','') or date>taken.get('lte','9999'):continue
                values.append(asset)
            start=int(body.get('cursor','0'));size=body['size'];page=values[start:start+size]
            return {'assets':{'items':page,'nextCursor':str(start+size) if start+size<len(values) else None}}
        raise AssertionError((path,body,method))

    def image_bytes(self,item,size='thumbnail'):
        from PIL import Image
        out=BytesIO();Image.new('RGB',(90,60),'purple').save(out,format='PNG');return out.getvalue()
