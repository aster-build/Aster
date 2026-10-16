import json

import numpy as np
import pandas as pd
import pytest

from aster.benchmark import scaffold
from aster.evidence_selection import (CONFLICT_TOLERANCE, compare, external_measurements,
                                      permitted, to_pki)

STUDY = {'target_accession': 'Q01959', 'endpoint': 'Ki'}
BASE = {'target_accession': 'Q01959', 'endpoint': 'Ki', 'relation': '=', 'unit': 'nM',
        'evidence_type': 'experimental', 'review_status': 'reviewed', 'review_method': 'machine',
        'document_id': 'doi:10.1/a', 'source_sha256': 'a' * 64, 'retracted': False}


def record(**overrides):
    return {**BASE, **overrides}


def write(tmp_path, records):
    path = tmp_path / 'corpus.json'
    path.write_text(json.dumps(records))
    return path


def test_pki_conversion_rejects_unsupported_units_and_nonpositive_values():
    assert to_pki(1.0, 'nM') == pytest.approx(9.0)
    assert to_pki(1000.0, 'nM') == pytest.approx(6.0)
    for value, unit in [(1.0, 'uM'), (0.0, 'nM'), (-5.0, 'nM'), (float('inf'), 'nM')]:
        with pytest.raises(ValueError):
            to_pki(value, unit)


def test_corpus_filter_drops_offtarget_censored_and_contextual_records(tmp_path):
    path = write(tmp_path, [
        record(compound_smiles='CCO', value=10.0),
        record(compound_smiles='CCN', value=10.0, target_accession='P00001'),
        record(compound_smiles='CCCl', value=10.0, endpoint='IC50'),
        record(compound_smiles='CCBr', value=10.0, relation='>'),
        record(compound_smiles='CCC', value=10.0, retracted=True),
        record(compound_smiles='CCCC', value=10.0, evidence_type='computational'),
        record(compound_smiles=None, value=None, endpoint='Ki'),
    ])
    evidence, audit = external_measurements(path, STUDY)
    assert evidence.identity.tolist() == ['CCO']
    assert audit['dropped'] == {'other_target': 1, 'other_endpoint': 1, 'censored_relation': 1,
                                'retracted': 1, 'not_experimental': 1,
                                'no_measurement_or_structure': 1, 'conflicting_values': 0}
    assert audit['human_reviewed_structures'] == 0


def test_disagreeing_measurements_are_excluded_and_close_ones_averaged(tmp_path):
    path = write(tmp_path, [
        record(compound_smiles='CCO', value=1.0),
        record(compound_smiles='CCO', value=1000.0),
        record(compound_smiles='CCN', value=100.0),
        record(compound_smiles='CCN', value=120.0),
    ])
    evidence, audit = external_measurements(path, STUDY)
    assert evidence.identity.tolist() == ['CCN']
    assert audit['dropped']['conflicting_values'] == 2
    assert audit['replicate_structures_averaged_within_tolerance'] == 1
    expected = (to_pki(100.0, 'nM') + to_pki(120.0, 'nM')) / 2
    assert evidence.value.iloc[0] == pytest.approx(expected)
    assert abs(to_pki(100.0, 'nM') - to_pki(120.0, 'nM')) < CONFLICT_TOLERANCE


def frame_of(structures):
    return pd.DataFrame({'compound_id': [f'c{i}' for i in range(len(structures))],
                         'smiles': structures, 'identity': structures,
                         'value': np.linspace(5.0, 9.0, len(structures)),
                         'scaffold': [scaffold(s) for s in structures]})


def test_strict_replay_withholds_every_structure_present_in_the_task():
    frame = frame_of(['CCO', 'CCN', 'CCCl'])
    evidence = pd.DataFrame({'identity': ['CCO', 'CCN', 'CCCCCC'], 'value': [7.0, 8.0, 6.0]})
    case = {'initial': [0], 'pool': [1], 'audit': [2]}
    keep, audit = permitted(evidence, frame, case)
    assert keep.identity.tolist() == ['CCCCCC']
    assert audit == {'permitted_structures': 1, 'withheld_because_present_in_task': 2,
                     'withheld_because_in_pool_or_audit': 1}


def test_permitted_evidence_never_overlaps_a_withheld_compound():
    frame = frame_of(['CCO', 'CCN'])
    evidence = pd.DataFrame({'identity': ['CCN'], 'value': [8.0]})
    case = {'initial': [0], 'pool': [1], 'audit': []}
    keep, _ = permitted(evidence, frame, case)
    assert keep.empty
    # The abort inside permitted() is a defensive backstop: it fires only if the
    # task-wide filter above ever stops covering the pool and audit sets.


def comparison_frame(gain, control_gain):
    rows = []
    for seed in range(4):
        for arm, delta in [('baseline', 0.0), ('literature_strict', gain),
                           ('shuffled_control', control_gain)]:
            rows.append({'protocol': 'published', 'support_size': 32, 'seed': seed, 'arm': arm,
                         'top_decile_found': 10 + delta, 'additional_hits': 20.0,
                         'audit_mae': 0.8, 'external_rows': 12})
    return pd.DataFrame(rows)


def test_gate_requires_both_a_gain_and_separation_from_the_control():
    study = {'protocols': ['published'],
             'arms': [{'id': 'baseline'}, {'id': 'literature_strict'}, {'id': 'shuffled_control'}],
             'promotion_gate': {'mean_top_decile_gain_min': 1.0, 'control_separation_min': 1.0}}
    assert compare(comparison_frame(2.0, 0.0), study)['gate']['passes']
    # A gain the scrambled control reproduces is an artifact, not evidence value.
    assert not compare(comparison_frame(2.0, 1.5), study)['gate']['passes']
    assert not compare(comparison_frame(0.4, 0.2), study)['gate']['passes']


def test_unpaired_arms_are_rejected():
    study = {'protocols': ['published'],
             'arms': [{'id': 'baseline'}, {'id': 'literature_strict'}, {'id': 'shuffled_control'}],
             'promotion_gate': {'mean_top_decile_gain_min': 1.0, 'control_separation_min': 1.0}}
    metrics = comparison_frame(1.0, 0.0)
    with pytest.raises(ValueError, match='Unpaired arms'):
        compare(metrics[~((metrics.arm == 'literature_strict') & (metrics.seed == 0))], study)
