import hashlib
import json

import pytest

from aster.campaign import load
from aster.rocrate import CRATE_SPEC, write

from test_event_log import campaign, decided  # noqa: F401  (shared fixture and helper)


def graph(directory):
    meta = json.loads((directory/'ro-crate-metadata.json').read_text())
    return meta, {entity['@id']: entity for entity in meta['@graph']}


def as_list(value):
    return value if isinstance(value, list) else [value]


def test_the_crate_has_a_descriptor_a_root_and_every_file_it_lists(tmp_path, campaign):
    decided(tmp_path, campaign, ['7.5', '6'])
    out = tmp_path/'crate'
    summary = write(campaign, out)
    assert summary['invariants_hold'] is True
    meta, entities = graph(out)
    assert meta['@context'][0] == f'{CRATE_SPEC}/context'
    descriptor = entities['ro-crate-metadata.json']
    assert descriptor['conformsTo'] == {'@id': CRATE_SPEC} and descriptor['about'] == {'@id': './'}
    root = entities['./']
    assert root['@type'] == 'Dataset' and root['name'] and root['description'] and root['datePublished']
    for part in root['hasPart']:
        entity = entities[part['@id']]
        data = (out/part['@id']).read_bytes()
        assert entity['@type'] == 'File'
        assert entity['sha256'] == hashlib.sha256(data).hexdigest()
        assert entity['contentSize'] == str(len(data))
    assert json.loads((out/'campaign.json').read_text()) == load(campaign)


def test_individuals_operators_and_streams_map_to_prov(tmp_path, campaign):
    decided(tmp_path, campaign, ['7.5'])
    out = tmp_path/'crate'
    write(campaign, out)
    _, entities = graph(out)
    fit = entities['#op:fit:1']
    assert fit['@type'] == ['CreateAction', 'prov:Activity']
    assert fit['object'] == fit['prov:used'] == {'@id': '#snapshot:1'}
    assert fit['result'] == {'@id': '#model:1'}
    assert entities['#model:1']['prov:wasGeneratedBy'] == {'@id': '#op:fit:1'}
    assert 'prov:Agent' in entities[fit['prov:wasAssociatedWith']['@id']]['@type']
    # Input files were supplied, not generated, so they carry no generating activity.
    assert 'prov:wasGeneratedBy' not in entities['#file:measured']
    # Every reference in the PROV graph lands on an entity the crate describes.
    for entity in entities.values():
        for key in ('object', 'result', 'prov:used', 'prov:wasGeneratedBy', 'agent'):
            for ref in as_list(entity.get(key, [])):
                assert ref['@id'] in entities, (entity['@id'], key, ref)


def test_claim_semantics_travel_in_the_event_log_not_the_metadata(tmp_path, campaign):
    decided(tmp_path, campaign, ['7.5'])
    out = tmp_path/'crate'
    write(campaign, out)
    _, entities = graph(out)
    assert not any(i.startswith('#claim:') or i.startswith('#bind:') for i in entities)
    rows = [json.loads(line) for line in (out/'events.jsonl').read_text().splitlines()]
    assert any(r['record_type'] == 'evidence_binding' for r in rows)
    assert any(r['record_type'] == 'fitness_record' for r in rows)


def test_no_singleton_arrays_and_an_optional_licence(tmp_path, campaign):
    decided(tmp_path, campaign, ['7.5'])
    out = tmp_path/'crate'
    write(campaign, out, license='https://creativecommons.org/licenses/by/4.0/')
    meta, entities = graph(out)
    assert entities['./']['license'] == {'@id': 'https://creativecommons.org/licenses/by/4.0/'}
    for entity in meta['@graph']:
        for key, value in entity.items():
            assert not (isinstance(value, list) and len(value) == 1), (entity['@id'], key)


def test_it_will_not_write_over_an_existing_directory(tmp_path, campaign):
    out = tmp_path/'crate'
    out.mkdir()
    (out/'keep.txt').write_text('mine')
    with pytest.raises(ValueError):
        write(campaign, out)
    assert (out/'keep.txt').read_text() == 'mine'


def test_names_with_spaces_become_valid_local_identifiers(tmp_path):
    from test_event_log import csv_file
    from aster.campaign import create
    measured = csv_file(tmp_path/'measured.csv', ['compound_id', 'smiles', 'value'],
                        [{'compound_id': f'cmpd {i}', 'smiles': 'C'*(i+1), 'value': 5+i/32}
                         for i in range(32)])
    candidates = csv_file(tmp_path/'candidates.csv', ['compound_id', 'smiles'],
                          [{'compound_id': f'cand {i}', 'smiles': 'C'*(i+1)+'N'} for i in range(8)])
    path = tmp_path/'spaces.sqlite'
    create(path, measured, candidates, name='Spaces', assay='CHEMBL238 Ki', endpoint='pKi')
    out = tmp_path/'crate'
    write(path, out)
    _, entities = graph(out)
    assert not any(' ' in i for i in entities)
    assay = entities['#stream:assay:CHEMBL238%20Ki']
    assert assay['identifier'] == 'stream:assay:CHEMBL238 Ki'
    assert entities['#molecule:cmpd%200']['identifier'] == 'molecule:cmpd 0'
