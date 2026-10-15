"""Synthetic records test retrieval mechanics, not scientific retrieval quality."""
from datetime import date
import json

from fastapi.testclient import TestClient
import pytest

from aster.api import create_app
from aster.evidence import import_corpus, search


def claim(**changes):
    record = dict(id='one', document_id='doi:10.example/fixture', title='Synthetic transporter fixture',
                  url='https://example.org/fixture', published='2020-01-01', retrieved='2026-01-01',
                  license='Synthetic test fixture', source_sha256='a'*64, locator='Results, paragraph 1',
                  passage='Synthetic inhibitor binding measurement.', target_accession='Q01959',
                  species='Homo sapiens', compound_smiles='OCC', assay='Synthetic assay A', endpoint='Ki',
                  value=10, unit='nM', relation='=', evidence_type='experimental', review_status='reviewed',
                  reviewer='Test fixture author', extraction_version='fixture-v1')
    return record | changes


def build(tmp_path, records):
    source = tmp_path/'corpus.json'
    source.write_text(json.dumps(records))
    index = tmp_path/'evidence'/'index.sqlite'
    return index, import_corpus(source, index)


def lookup(index, **kwargs):
    return search(index, 'binding', 'Q01959', 'Homo sapiens', **kwargs)


def test_exact_identity_filters_and_provenance(tmp_path):
    index, manifest = build(tmp_path, [claim(), claim(id='two', compound_smiles='CCN', endpoint='IC50')])
    found = lookup(index, smiles='CCO', endpoint='Ki', cutoff=date(2020, 1, 1))
    assert found['snapshot_sha256'] == manifest['snapshot_sha256']
    assert [c['id'] for c in found['claims']] == ['one']
    assert found['claims'][0]['locator'] == 'Results, paragraph 1'
    assert found['ranking_effect'] == 'none'
    assert found['claims'][0]['review_method'] == 'unspecified'
    assert lookup(index, cutoff=date(2019, 12, 31))['status'] == 'no_evidence'
    assert search(index, 'binding', 'WRONG', 'Homo sapiens')['claims'] == []
    assert search(index, 'binding', 'Q01959', 'Mus musculus')['claims'] == []
    assert lookup(index, smiles='CCC')['claims'] == []


def test_unreviewed_retracted_and_empty_are_not_evidence(tmp_path):
    index, _ = build(tmp_path, [claim(review_status='unreviewed'), claim(id='two', document_id='other', retracted=True)])
    assert lookup(index)['status'] == 'no_evidence'
    assert lookup(tmp_path/'missing.sqlite')['status'] == 'corpus_unavailable'
    assert not (tmp_path/'missing.sqlite').exists()


@pytest.mark.parametrize('changes', [dict(value=float('nan')), dict(unit=None), dict(reviewer=' '),
                                     dict(compound_smiles='bad smiles'), dict(published='2027-01-01'),
                                     dict(source_sha256='bad')])
def test_invalid_import_preserves_existing_snapshot(tmp_path, changes):
    index, _ = build(tmp_path, [claim()])
    before = index.read_bytes()
    with pytest.raises(ValueError):
        build(tmp_path, [claim(**changes)])
    assert index.read_bytes() == before


def test_duplicate_and_conflicting_versions_are_rejected(tmp_path):
    with pytest.raises(ValueError, match='Duplicate'):
        build(tmp_path, [claim(), claim()])
    with pytest.raises(ValueError, match='Conflicting'):
        build(tmp_path, [claim(), claim(id='two', document_id='https://doi.org/10.example/fixture', source_sha256='b'*64)])


def test_conflicting_measurements_preserved_and_queries_are_literal(tmp_path):
    index, _ = build(tmp_path, [claim(), claim(id='two', value=90)])
    assert {c['value'] for c in lookup(index)['claims']} == {10, 90}
    # FTS syntax and SQL-like punctuation cannot modify the index or widen entity scope.
    assert search(index, 'binding" OR * --', 'WRONG', 'Homo sapiens')['claims'] == []
    assert len(lookup(index)['claims']) == 2
    with pytest.raises(ValueError):
        search(index, '***', 'Q01959', 'Homo sapiens')


def test_api_read_only_search_and_validation(tmp_path):
    index, _ = build(tmp_path, [claim()])
    before = index.read_bytes()
    with TestClient(create_app(tmp_path)) as client:
        params = dict(q='binding', target='Q01959', species='Homo sapiens')
        assert client.get('/evidence/search', params=params).json()['status'] == 'evidence_found'
        assert client.get('/evidence/search', params=params | {'limit': 51}).status_code == 422
        assert client.get('/evidence/search', params=params | {'cutoff': 'nonsense'}).status_code == 422
        assert client.get('/evidence/search', params=params | {'smiles': 'invalid'}).status_code == 422
        assert client.get('/campaigns').json() == []
    assert index.read_bytes() == before
    assert list(tmp_path.glob('*.sqlite')) == []


def test_alias_resolution_rejects_ambiguous_documents(tmp_path):
    index, _ = build(tmp_path, [claim(document_id='PMC123', document_aliases=['doi:10.example/fixture']),
                               claim(id='two', document_id='PMID:42', document_aliases=['https://doi.org/10.example/fixture'])])
    assert {c['resolved_document_id'] for c in lookup(index)['claims']} == {'doi:10.example/fixture'}
    with pytest.raises(ValueError, match='Conflicting DOI'):
        build(tmp_path, [claim(document_aliases=['pmid:42']), claim(id='two', document_id='doi:10.other/paper', document_aliases=['pmid:42'])])


def test_disagreement_is_assay_and_endpoint_specific(tmp_path):
    index, _ = build(tmp_path, [claim(assay_id='assay-one'), claim(id='two', assay_id='assay-one', value=90),
                               claim(id='three', assay_id='different-assay', value=200), claim(id='four', assay_id='assay-one', value=300, endpoint='IC50')])
    conflicts = lookup(index)['conflicts']
    assert len(conflicts) == 1
    assert set(conflicts[0]['claim_ids']) == {'one', 'two'}
    assert len(lookup(index)['claims']) == 4


def test_hybrid_filters_and_stereochemical_identity(tmp_path):
    index, _ = build(tmp_path, [claim(compound_smiles='C[C@H](O)CC'), claim(id='two', compound_smiles='C[C@@H](O)CC'),
                               claim(id='three', compound_smiles=None, evidence_type='context')])
    result = lookup(index, smiles='CC[C@@H](O)C', method='hybrid')
    assert [c['id'] for c in result['claims']] == ['one']
    assert lookup(index, evidence_type='context')['claims'][0]['id'] == 'three'
    assert lookup(index, smiles='CCCCCCCCCCC', match='analog')['claims'] == []
    assert search(index, 'unfindableword', 'WRONG', 'Homo sapiens', method='hybrid')['claims'] == []


def test_saved_snapshot_idempotent_survives_replacement_without_mutation(tmp_path):
    from tests.test_api import demo, preview
    index, _ = build(tmp_path, [claim()])
    with TestClient(create_app(tmp_path)) as client:
        cid = demo(client)
        proposed = preview(client, cid)
        client.post(f'/campaigns/{cid}/commit', json={'preview_id': proposed['id']})
        before = client.get(f'/campaigns/{cid}').json()
        compound_id = before['compounds'][0]['compound_id']
        params = dict(q='binding', compound_id=compound_id, scope='target')
        found = client.get(f'/campaigns/{cid}/evidence', params=params).json()
        body = params | {'snapshot_sha256': found['snapshot_sha256']}
        saved = client.post(f'/campaigns/{cid}/rounds/1/evidence', json=body)
        assert saved.status_code == 201, saved.text
        again = client.post(f'/campaigns/{cid}/rounds/1/evidence', json=body)
        assert again.json()['id'] == saved.json()['id']
        assert client.get(f'/campaigns/{cid}').json() == before
        build(tmp_path, [claim(value=11)])
        assert client.post(f'/campaigns/{cid}/rounds/1/evidence', json=body).status_code == 409
        assert client.post(f'/campaigns/{cid}/rounds/99/evidence', json=body).status_code == 404
        assert client.get(f'/campaigns/{cid}/evidence', params=params | {'compound_id':'unknown'}).status_code == 404
        other = demo(client)
        other_preview = preview(client, other)
        client.post(f'/campaigns/{other}/commit', json={'preview_id':other_preview['id']})
        assert client.get(f'/campaigns/{other}/rounds/1/evidence').json() == []
    with TestClient(create_app(tmp_path)) as client:
        records = client.get(f'/campaigns/{cid}/rounds/1/evidence').json()
        assert len(records) == 1
        assert records[0]['record']['result']['claims'][0]['value'] == 10
        assert 'after commitment' in records[0]['record']['timing']


def test_unverified_campaign_cannot_inherit_dat_target(tmp_path):
    from aster.api import ROOT
    build(tmp_path, [claim()])
    with TestClient(create_app(tmp_path)) as client:
        fixture = ROOT/'examples/dashboard'
        cid = client.post('/campaigns', json=dict(name='Unverified', assay='Unknown', endpoint='pKi',
                           measured_csv=(fixture/'measured.csv').read_text(), candidates_csv=(fixture/'candidates.csv').read_text())).json()['id']
        compound = client.get('/campaigns/'+cid).json()['compounds'][0]['compound_id']
        assert client.get(f'/campaigns/{cid}/evidence', params=dict(q='binding', compound_id=compound)).status_code == 409
