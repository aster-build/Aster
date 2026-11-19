import pytest
from rdkit import rdBase

from aster import standardisation
from aster.data import canonicalize
from aster.standardisation import CONVENTION_ID, PROBES, compare, current, probe_outputs, probe_sha256


def test_current_names_the_convention_the_rdkit_version_and_a_probe_hash():
    record = current()
    assert record['convention'] == CONVENTION_ID
    assert record['rdkit_version'] == rdBase.rdkitVersion
    assert len(record['probe_sha256']) == 64
    for choice in ('tautomers', 'resonance', 'charges', 'fragments', 'stereochemistry'):
        assert record['description'][choice]


def test_probe_hash_is_stable_within_one_installation():
    assert probe_sha256() == probe_sha256() == current()['probe_sha256']


def test_the_description_matches_what_canonicalize_actually_does():
    by_input = {o['input']: o for o in probe_outputs()}
    # Tautomers are not merged.
    assert by_input['Oc1ccccn1']['identity'] != by_input['O=c1cccc[nH]1']['identity']
    # Kekule benzene is aromatised; hypervalent nitro becomes charge-separated.
    assert by_input['C1=CC=CC=C1']['identity'] == 'c1ccccc1'
    assert by_input['CN(=O)=O']['identity'] == 'C[N+](=O)[O-]'
    # Charges kept; nothing neutralised.
    assert '+' in by_input['C[NH3+]']['identity']
    assert '-' in by_input['CC(=O)[O-]']['identity']
    # Enhanced stereo stays in the structure but not in the identity key.
    enhanced = by_input['C[C@H](N)C(=O)O |&1:1|']
    assert '|' in enhanced['structure'] and '|' not in enhanced['identity']
    assert by_input['[2H]C(Cl)Cl']['identity'].startswith('[2H]')
    # Salts are refused, not stripped.
    with pytest.raises(ValueError, match='multiple_fragments'):
        canonicalize('CC(=O)[O-].[Na+]')
    assert len(by_input) == len(PROBES)


def test_a_behaviour_change_moves_the_probe_hash():
    outputs = probe_outputs()
    changed = [dict(o) for o in outputs]
    # As if a future convention merged tautomers: 2-hydroxypyridine read as 2-pyridone.
    changed[0]['identity'] = changed[1]['identity']
    assert probe_sha256(changed) != probe_sha256(outputs)


def test_compare_reports_same_different_and_unknown():
    here = current()
    assert compare(here, dict(here)) == {'verdict': 'same', 'comparable': True, 'reasons': []}

    upgraded = {**here, 'rdkit_version': '9999.01.1'}
    result = compare(here, upgraded)
    assert result['verdict'] == 'same_on_probes' and result['comparable'] is True
    assert '9999.01.1' in result['reasons'][0]

    drifted = {**here, 'probe_sha256': '0' * 64}
    result = compare(here, drifted)
    assert result['verdict'] == 'different' and result['comparable'] is False

    renamed = {**here, 'convention': 'tautomer-canonical-v1'}
    assert compare(renamed, here)['verdict'] == 'different'

    # A record that predates logging is never assumed to match.
    for first, second in ((None, here), (here, None), (None, None)):
        assert compare(first, second) == {**compare(None, None), 'verdict': 'unknown'}
        assert compare(first, second)['comparable'] is None


def test_changing_canonicalize_without_a_new_id_would_be_caught(monkeypatch):
    before = probe_sha256()
    monkeypatch.setattr(standardisation, 'canonicalize',
                        lambda smiles: ('X', 'X'))
    assert probe_sha256() != before


def test_summary_keeps_only_the_identifying_fields():
    assert standardisation.summary(current()) == {
        key: current()[key] for key in ('convention', 'rdkit_version', 'probe_sha256')}
