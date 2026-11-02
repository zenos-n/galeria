import json
from threading import Event
import unittest
from unittest.mock import patch
from sync_service import run_cycle


class SyncStatusTests(unittest.TestCase):
    def test_status_is_published_before_and_during_uploads(self):
        snapshots=[]
        class Client:
            identity='account'
            def __init__(self,*_):pass
            def request(self,path):return {'id':'user'}
            def detect_version(self):pass
        class Engine:
            def __init__(self,*args,progress=None,**kwargs):self.progress=progress
            def run_folder(self,rule):
                self.progress({'uploaded':1,'errors':[]})
                return {'uploaded':2,'errors':[]}
        config={'accounts':{'account':{'server':'https://example.invalid/api','enabled':True,'folders':[{'path':'/fixture','enabled':True}]}}}
        with patch('sync_service.SyncEngine',Engine),patch('sync_service.atomic_write',lambda path,body:snapshots.append(json.loads(body))):
            result=run_cycle(config,None,Event(),client_factory=Client,token_lookup=lambda *_:'fixture')
        self.assertTrue(snapshots[0]['active']);self.assertTrue(snapshots[0]['accounts']['account']['busy'])
        self.assertTrue(any(value['accounts']['account'].get('progress',{}).get('uploaded')==1 for value in snapshots))
        self.assertFalse(result['active']);self.assertFalse(result['accounts']['account']['busy'])
        self.assertEqual(result['accounts']['account']['folders'][0]['uploaded'],2)
