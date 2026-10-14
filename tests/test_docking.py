import json
import time
from fastapi.testclient import TestClient
from aster.api import create_app
from aster import docking
from tests.test_api import demo

def test_validation_gate_and_target_scope(tmp_path,monkeypatch):
    monkeypatch.setattr(docking,'validation',lambda:{'passed':False,'reason':'Redocking failed'})
    with TestClient(create_app(tmp_path)) as client:
        cid=demo(client); before=client.get(f'/campaigns/{cid}').json(); compound=before['compounds'][0]['compound_id']
        response=client.post(f'/campaigns/{cid}/docking',json={'compound_id':compound})
        assert response.status_code==409 and response.json()['detail']=='Redocking failed'
        assert client.post(f'/campaigns/{cid}/docking',json={'compound_id':'../oops'}).status_code==404
        assert client.get(f'/campaigns/{cid}').json()==before
        assert client.get(f'/campaigns/{cid}/docking').json()==[]

def test_jobs_deduplicate_persist_and_never_change_campaign(tmp_path,monkeypatch):
    monkeypatch.setattr(docking,'runtime_available',lambda:True)
    monkeypatch.setattr(docking,'validation',lambda:{'passed':True,'validation_sha256':'test'})
    def worker(self,jid):
        directory=self.store/jid
        job=json.loads((directory/'job.json').read_text())
        docking.write(directory/'result.json',{'poses':[{'passed':True}]})
        job['status']='complete'; docking.write(directory/'job.json',job)
    monkeypatch.setattr(docking.DockingJobs,'run',worker)
    with TestClient(create_app(tmp_path)) as client:
        cid=demo(client); before=client.get(f'/campaigns/{cid}').json()
        # Known single-fragment, explicitly specified stereochemistry for the worker stub.
        from aster import campaign
        with campaign.transaction(tmp_path/(cid+'.sqlite'),True) as state:
            compound=next(iter(state['compounds'])); state['compounds'][compound]['smiles']='CCO'
        before=client.get(f'/campaigns/{cid}').json()
        one=client.post(f'/campaigns/{cid}/docking',json={'compound_id':compound}).json()
        two=client.post(f'/campaigns/{cid}/docking',json={'compound_id':compound}).json()
        assert one['id']==two['id']
        for _ in range(100):
            job=client.get(f"/campaigns/{cid}/docking/{one['id']}").json()
            if job['status']=='complete': break
            time.sleep(.01)
        assert job['result']['poses'][0]['passed']
        other=demo(client)
        assert client.get(f"/campaigns/{other}/docking/{one['id']}").status_code==404
        assert client.get(f'/campaigns/{cid}').json()==before
    with TestClient(create_app(tmp_path)) as client:
        assert client.get(f"/campaigns/{cid}/docking/{one['id']}").json()['status']=='complete'

def test_restart_fails_interrupted_jobs(tmp_path):
    path=tmp_path/'docking'/('1'*32); path.mkdir(parents=True)
    docking.write(path/'job.json',{'id':'1'*32,'status':'running','campaign_id':'2'*32})
    service=docking.DockingJobs(tmp_path)
    assert service.get('2'*32,'1'*32)['status']=='failed'
    service.close()

def test_changed_reference_invalidates_gate(tmp_path,monkeypatch):
    reference=tmp_path/'receptor';reference.write_text('before')
    docking.write(tmp_path/'validation.json',{'passed':True,'hashes':{str(reference):docking.sha(reference)}})
    monkeypatch.setattr(docking,'BASE',tmp_path)
    assert docking.validation()['passed']
    reference.write_text('after')
    assert docking.validation()['status']=='stale'
