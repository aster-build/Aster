import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aster import evidence_supply as supply
from aster.benchmark import load_task
from aster.data import fingerprints

STUDY = json.loads(Path('configs/evidence-supply-v1.json').read_text())
TASK = 'CHEMBL4203_Ki'


@pytest.fixture(scope='module')
def task():
    source = Path('data/moleculeace') / f'{TASK}.csv'
    if not source.exists():
        pytest.skip('Pinned MoleculeACE task not downloaded')
    frame, _ = load_task(source, {'id': TASK, 'sha256': STUDY['tasks'][TASK]})
    features = fingerprints(frame.smiles.tolist(), STUDY['radius'], STUDY['bits'])
    return frame, features


def test_donor_choice_ignores_outcomes(task):
    frame, _ = task
    scrambled = frame.copy()
    scrambled['value'] = np.random.default_rng(0).permutation(scrambled.value.to_numpy())
    for mode in STUDY['donor_modes']:
        chosen = supply.donors(frame, mode, 50, seed=3)
        assert np.array_equal(chosen, supply.donors(scrambled, mode, 50, seed=3))
        assert np.array_equal(chosen, supply.donors(frame, mode, 50, seed=3))


def test_donor_counts_differ_by_seed(task):
    frame, _ = task
    assert not np.array_equal(supply.donors(frame, 'donor_random', 50, 0),
                              supply.donors(frame, 'donor_random', 50, 1))


def test_random_donors_fill_the_requested_count(task):
    frame, _ = task
    assert len(supply.donors(frame, 'donor_random', 150, 0)) == 150


def test_scaffold_disjoint_donors_share_no_scaffold_with_the_task(task):
    frame, _ = task
    for count in STUDY['donor_counts']:
        chosen = supply.donors(frame, 'donor_scaffold_disjoint', count, seed=2)
        assert count * supply.MINIMUM_FILL <= len(chosen) <= count
        kept = frame.drop(index=chosen)
        assert not set(frame.iloc[chosen].scaffold) & set(kept.scaffold)


def test_donors_are_absent_from_the_task_that_is_replayed(task):
    frame, features = task
    rows = supply.case_rows(frame, features, STUDY, TASK, 'donor_random', 50,
                            'published', 32, seed=0)
    chosen = supply.donors(frame, 'donor_random', 50, 0)
    assert all(row['task_rows'] == len(frame) - 50 for row in rows)
    assert all(row['donor_rows'] == 50 for row in rows)
    assert not set(frame.iloc[chosen].identity) & set(frame.drop(index=chosen).identity)


def test_guard_is_the_measured_range_widened_by_one_standard_deviation():
    values = np.array([5.0, 6.0, 7.0, 8.0])
    low, high = supply.guard(values, 'task_measured_range_plus_sd')
    spread = float(np.std(values, ddof=1))
    assert (low, high) == pytest.approx((5.0 - spread, 8.0 + spread))
    assert supply.guard(values, [0.0, 14.0]) == [0.0, 14.0]
    with pytest.raises(ValueError):
        supply.guard(values, 'something_else')


def test_arms_share_one_split_and_only_the_evidence_differs(task):
    frame, features = task
    rows = supply.case_rows(frame, features, STUDY, TASK, 'donor_random', 12,
                            'published', 32, seed=1)
    assert [row['arm'] for row in rows] == ['baseline', 'donor_evidence', 'shuffled_control']
    assert len({(row['pool_size'], row['audit_size'], row['top_decile_threshold'])
                for row in rows}) == 1
    assert rows[0]['external_rows'] == 0
    assert rows[1]['external_rows'] == rows[2]['external_rows'] == 12
    repeat = supply.case_rows(frame, features, STUDY, TASK, 'donor_random', 12,
                              'published', 32, seed=1)
    assert [row['top_decile_found'] for row in rows] == \
           [row['top_decile_found'] for row in repeat]


def test_gate_is_read_at_the_highest_supply_and_needs_both_thresholds():
    rows = []
    for mode in STUDY['donor_modes']:
        for count in STUDY['donor_counts']:
            for seed in range(12):
                gain = 4 if count == max(STUDY['donor_counts']) else 0
                for arm, value in (('baseline', 10), ('donor_evidence', 10 + gain),
                                   ('shuffled_control', 10)):
                    rows.append({'task': 'T', 'protocol': 'published', 'support_size': 32,
                                 'donor_mode': mode, 'donor_count': count, 'seed': seed,
                                 'arm': arm, 'top_decile_found': value})
    verdict = supply.compare(pd.DataFrame(rows), STUDY)
    assert verdict['passes']
    for mode in STUDY['donor_modes']:
        entry = verdict['gate'][mode]
        assert entry['donor_count'] == max(STUDY['donor_counts'])
        assert entry['mean_gain'] == 4.0 and entry['separation_from_control'] == 4.0
    assert 'worth pursuing' in verdict['conclusion']

    flat = pd.DataFrame(rows)
    flat.loc[flat.arm == 'donor_evidence', 'top_decile_found'] = 10
    null = supply.compare(flat, STUDY)
    assert not null['passes']
    assert 'not explained by evidence supply' in null['conclusion']
    assert null['supply_curve'][f"donor_random:{max(STUDY['donor_counts'])}"][
        'donor_evidence']['mean_paired_difference'] == 0.0
