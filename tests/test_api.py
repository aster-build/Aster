import csv
import io
import time

import pytest
from fastapi.testclient import TestClient

from aster.api import ROOT, create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        yield client


def demo(client):
    response = client.post('/demo', json={})
    assert response.status_code == 201, response.text
    return response.json()['id']


def preview(client, cid, size=8):
    response = client.post(f'/campaigns/{cid}/previews', json={'batch_size': size})
    assert response.status_code == 202, response.text
    jid = response.json()['job_id']
    for _ in range(100):
        job = client.get('/jobs/'+jid).json()
        if job['status'] == 'complete':
            return client.get(f'/campaigns/{cid}/previews/{jid}').json()
        assert job['status'] != 'failed', job
        time.sleep(.03)
    raise AssertionError('Preview did not finish')


def test_full_two_round_api_loop_and_saved_evidence(client):
    cid = demo(client)
    before = client.get('/campaigns/'+cid).json()
    proposal = preview(client, cid)
    after = client.get('/campaigns/'+cid).json()
    assert before == after  # A preview never commits or changes measurements.
    assert len(proposal['scored']) == 128 and len(proposal['recommendations']) == 8
    assert not any('value' in r for r in proposal['scored'])
    observed = {r['compound_id'] for r in before['compounds'] if r['status'] == 'measured'}
    assert all(r['nearest_measured_id'] in observed for r in proposal['scored'])
    committed = client.post(f'/campaigns/{cid}/commit', json={'preview_id': proposal['id']})
    assert committed.status_code == 200
    retry = client.post(f'/campaigns/{cid}/commit', json={'preview_id': proposal['id']})
    assert retry.json()['already_committed']
    assert len(client.get('/campaigns/'+cid).json()['rounds']) == 1
    export = client.get(f'/campaigns/{cid}/rounds/1/export')
    assert len(list(csv.DictReader(io.StringIO(export.text)))) == 8
    molecule = client.get(f'/campaigns/{cid}/molecule', params={'compound_id': proposal['recommendations'][0]['compound_id']})
    assert molecule.status_code == 200 and '<svg' in molecule.text
    assert client.post(f'/campaigns/{cid}/previews', json={}).status_code == 409
    assert client.post(f'/campaigns/{cid}/rounds/1/demo-results', json={}).json()['added'] == 8
    second = preview(client, cid)
    assert second['training_count'] == 40
    assert not {r['compound_id'] for r in second['recommendations']} & {r['compound_id'] for r in proposal['recommendations']}
    client.post(f'/campaigns/{cid}/commit', json={'preview_id': second['id']})
    client.post(f'/campaigns/{cid}/rounds/2/demo-results', json={})
    status = client.get('/campaigns/'+cid).json()
    assert sum(r['status'] == 'measured' for r in status['compounds']) == 48
    assert all(r['status'] == 'complete' for r in status['rounds'])


def test_stale_preview_and_cross_campaign_commit_rejected(client):
    cid = demo(client)
    proposed = preview(client, cid)
    body = client.get('/campaigns/'+cid).json()
    selected = proposed['recommendations'][0]['compound_id']
    changed = client.post(f'/campaigns/{cid}/constraints', json={'ids':[selected], 'mode':'excluded', 'revision':body['revision']})
    assert changed.status_code == 200
    assert client.post(f'/campaigns/{cid}/commit', json={'preview_id':proposed['id']}).status_code == 409
    assert client.post(f'/campaigns/{cid}/constraints', json={'ids':[selected], 'mode':'locked', 'revision':body['revision']}).status_code == 409
    other = demo(client)
    assert client.post(f'/campaigns/{other}/commit', json={'preview_id':proposed['id']}).status_code == 404
    assert client.get(f'/campaigns/{other}/previews/{proposed["id"]}').status_code == 404
    fresh = preview(client, cid)
    assert selected not in {r['compound_id'] for r in fresh['recommendations']}


def test_real_csv_import_results_and_demo_isolation(client):
    fixture = ROOT/'examples/dashboard'
    response = client.post('/campaigns', json={'name':'User import','assay':'Single assay','endpoint':'pKi',
                          'measured_csv':(fixture/'measured.csv').read_text(), 'candidates_csv':(fixture/'candidates.csv').read_text()})
    cid=response.json()['id']
    proposal=preview(client,cid)
    client.post(f'/campaigns/{cid}/commit',json={'preview_id':proposal['id']})
    assert client.post(f'/campaigns/{cid}/rounds/1/demo-results',json={}).status_code == 404
    rows=proposal['recommendations']
    text='compound_id,status,value\n'+rows[0]['compound_id']+',measured,7.2\n'
    assert client.post(f'/campaigns/{cid}/rounds/1/results',json={'csv':text}).json()['added']==1
    assert client.post(f'/campaigns/{cid}/rounds/1/results',json={'csv':text}).json()['added']==0
    assert client.post(f'/campaigns/{cid}/rounds/1/results',json={'csv':text.replace('7.2','8.2')}).status_code==422
    remaining='compound_id,status,value\n'+''.join(r['compound_id']+',failed,\n' for r in rows[1:])
    assert client.post(f'/campaigns/{cid}/rounds/1/results',json={'csv':remaining}).json()['round_status']=='complete'
    assert preview(client,cid)['training_count']==33


def test_invalid_inputs_and_hostile_origin(client):
    assert client.get('/campaigns/not-a-valid-id').status_code == 404
    assert client.post('/demo',json={},headers={'Origin':'https://unrelated.example'}).status_code == 403
    cid=demo(client)
    assert client.post(f'/campaigns/{cid}/previews',json={'batch_size':0}).status_code==422
    fixture=ROOT/'examples/dashboard'
    inputs={'name':'bad','assay':'one','measured_csv':(fixture/'measured.csv').read_text(),'candidates_csv':(fixture/'candidates.csv').read_text()}
    # Any endpoint name is allowed, but it must be present and its direction known.
    assert client.post('/campaigns',json={**inputs,'endpoint':''}).status_code==422
    assert client.post('/campaigns',json={**inputs,'endpoint':'clearance','direction':'sideways'}).status_code==422
    assert len(client.get('/campaigns').json())==1


def test_restart_keeps_campaign_and_marks_interrupted_job_failed(tmp_path):
    import json
    with TestClient(create_app(tmp_path)) as client:
        cid=demo(client)
    jid='a'*32
    (tmp_path/'jobs'/f'{jid}.json').write_text(json.dumps({'id':jid,'campaign_id':cid,'status':'running'}))
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/campaigns/'+cid).status_code==200
        job=client.get('/jobs/'+jid).json()
        assert job['status']=='failed' and 'restarted' in job['error']
        assert preview(client,cid)['training_count']==32


def test_manual_selection_is_committed_exactly_and_replayed(client):
    cid = demo(client)
    proposal = preview(client, cid, 3)
    original = {r['compound_id'] for r in proposal['recommendations']}
    alternate = next(r['compound_id'] for r in proposal['scored'] if r['compound_id'] not in original and r['constraint'] != 'excluded')
    selected = [proposal['recommendations'][0]['compound_id'], alternate]
    body = {'preview_id': proposal['id'], 'selected_ids': selected}
    assert client.post(f'/campaigns/{cid}/commit', json=body).status_code == 200
    state = client.get(f'/campaigns/{cid}').json()
    record = state['rounds'][0]
    assert [r['compound_id'] for r in record['recommendations']] == selected
    assert all(r['selection_reason'] == 'user_selected' for r in record['recommendations'])
    assert {c['compound_id'] for c in state['compounds'] if c['status'] == 'pending'} == set(selected)
    assert client.post(f'/campaigns/{cid}/commit', json=body).json()['already_committed']
    assert client.post(f'/campaigns/{cid}/commit', json={**body, 'selected_ids':selected[::-1]}).status_code == 409
    assert client.post(f'/campaigns/{cid}/rounds/1/demo-results', json={}).json()['added'] == 2
    assert preview(client, cid, 3)['training_count'] == 34


def test_manual_selection_rejects_ineligible_duplicate_oversize_and_missing_lock(client):
    cid = demo(client)
    state = client.get(f'/campaigns/{cid}').json()
    available = [c['compound_id'] for c in state['compounds'] if c['status'] == 'available']
    locked, excluded = available[:2]
    assert client.post(f'/campaigns/{cid}/constraints', json={'ids':[locked], 'mode':'locked','revision':state['revision']}).status_code == 200
    state = client.get(f'/campaigns/{cid}').json()
    assert client.post(f'/campaigns/{cid}/constraints', json={'ids':[excluded], 'mode':'excluded','revision':state['revision']}).status_code == 200
    proposal = preview(client,cid,2)
    eligible = [r['compound_id'] for r in proposal['scored'] if r['constraint']=='available']
    for selected in ([locked,locked], [locked,excluded], [eligible[0]], [locked,*eligible[:2]], ['unknown'], []):
        response = client.post(f'/campaigns/{cid}/commit',json={'preview_id':proposal['id'],'selected_ids':selected})
        assert response.status_code == 422, response.text
    assert client.get(f'/campaigns/{cid}').json()['rounds'] == []


def test_decision_record_endpoints_answer_the_six_month_question(client):
    cid = demo(client)
    proposal = preview(client, cid)
    client.post(f'/campaigns/{cid}/commit', json={'preview_id': proposal['id']})
    client.post(f'/campaigns/{cid}/rounds/1/demo-results', json={})

    decisions = client.get(f'/campaigns/{cid}/decisions').json()
    assert len(decisions) == 8
    assert {d['compound_id'] for d in decisions} == {r['compound_id'] for r in proposal['recommendations']}
    first = client.get(f'/campaigns/{cid}/decisions/{decisions[0]["compound_id"]}').json()
    assert first['tested'] is True and first['decisions'][0]['round'] == 1
    assert first['decisions'][0]['outcome']['status'] == 'measured'
    assert first['decisions'][0]['endpoint'] == {'endpoint': 'pKi', 'unit': 'log10 1/M',
                                                 'direction': 'higher_is_better'}

    review = client.get(f'/campaigns/{cid}/decisions/review').json()
    assert review['rounds'][0]['picks'] == 8 and review['rounds'][0]['measured'] == 8
    assert review['totals']['decisions'] == 8
    assert client.get(f'/campaigns/{cid}/decisions/no-such-compound').status_code == 404
