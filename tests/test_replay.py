import hashlib
import json
import math
from pathlib import Path

from fastapi.testclient import TestClient
from aster.api import create_app, ROOT
from tests.test_api import demo, preview


def test_replay_preserves_training_and_outcomes_without_mutation(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        cid = demo(client)
        assert client.get(f'/campaigns/{cid}/replay').json()['rounds'] == []
        first = preview(client, cid)
        client.post(f'/campaigns/{cid}/commit', json={'preview_id':first['id']})
        pending = client.get(f'/campaigns/{cid}/replay').json()['rounds'][0]
        assert len(pending['training']) == 32 and pending['results'] == {}
        assert len(pending['scored']) == 128
        assert pending['recommendations'] == first['recommendations']
        client.post(f'/campaigns/{cid}/rounds/1/demo-results', json={})
        second = preview(client,cid)
        client.post(f'/campaigns/{cid}/commit', json={'preview_id':second['id']})
        client.post(f'/campaigns/{cid}/rounds/2/demo-results', json={})
        before=client.get(f'/campaigns/{cid}').json()
        replay=client.get(f'/campaigns/{cid}/replay').json()
        a,b=replay['rounds']
        assert [len(r['training']) for r in [a,b]] == [32,40]
        assert a['training']==pending['training']
        assert a['scored']==pending['scored']
        assert len(a['results'])==len(b['results'])==8
        assert not {r['compound_id'] for r in a['training']} & set(a['results'])
        assert set(a['results']) <= {r['compound_id'] for r in b['training']}
        assert client.get(f'/campaigns/{cid}').json()==before
        (tmp_path/(first['id']+'.preview.json')).unlink()
        fallback=client.get(f'/campaigns/{cid}/replay').json()['rounds'][0]
        assert fallback['score_coverage']=='committed batch only'
        assert fallback['scored']==a['recommendations']
        assert client.get('/campaigns/'+'0'*32+'/replay').status_code==404


def test_structural_evidence_is_pinned_and_geometric():
    from scripts.prepare_structure import atoms_from_pinned_cif
    base=ROOT/'apps/web/public/structures/8y2g'
    manifest=json.loads((base/'manifest.json').read_text())
    for filename,digest in manifest['files'].items():
        assert hashlib.sha256((base/filename).read_bytes()).hexdigest()==digest
    atoms=atoms_from_pinned_cif((base/'complex.cif').read_text())
    assert manifest['exact_demo_matches']==[]
    ligand=[a for a in atoms if a['label_comp_id']=='A1D5U']
    for contact in manifest['contacts']:
        protein=[a for a in atoms if a['group_PDB']=='ATOM' and a['auth_asym_id']==contact['chain'] and int(a['auth_seq_id'])==contact['sequence']]
        actual=min(math.dist(p['xyz'],l['xyz']) for p in protein for l in ligand)
        assert math.isclose(actual,contact['distance']) and actual<=4
        assert any(p['label_atom_id']==contact['protein_atom'] and p['xyz']==contact['protein_xyz'] for p in protein)
        assert any(l['label_atom_id']==contact['ligand_atom'] and l['xyz']==contact['ligand_xyz'] for l in ligand)
