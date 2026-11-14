import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aster import temporal

SETTINGS = json.loads(Path('configs/temporal-v1.json').read_text())


RINGS = ['c1ccccc1', 'c1ccncc1', 'C1CCCCC1', 'c1ccc2ccccc2c1', 'C1CCNCC1']
LINKS = ['C', 'CC', 'CO', 'CN', 'CS', 'CCO', 'C(C)C', 'CCN']


def synthetic(count: int = 240, cutoff: int = 20100, seed: int = 0) -> pd.DataFrame:
    """Measurements whose values depend only on structure, half each side of the cutoff.

    Built from valid fragments rather than random atom strings, so every row is a
    molecule RDKit will parse; the value is a function of the structure plus a
    little noise, so a working model must beat the no-model floor.
    """
    rng = np.random.default_rng(seed)
    rows, seen = [], set()
    index = 0
    while len(rows) < count:
        index += 1
        smiles = (rng.choice(RINGS) + rng.choice(LINKS) +
                  (rng.choice(RINGS) if index % 3 else ''))
        if smiles in seen:
            continue
        seen.add(smiles)
        position = len(rows)
        registration = cutoff - count // 2 + position + (1 if position >= count // 2 else 0)
        rows.append({'compound_id': f'E-{registration:07d}', 'endpoint': 'logd',
                     'era': 'earlier' if registration <= cutoff else 'later',
                     'registration': registration, 'smiles': smiles,
                     'value': float(len(smiles)) + smiles.count('n') + rng.normal(0, 0.1)})
    return pd.DataFrame(rows)


@pytest.fixture(scope='module')
def frame():
    return synthetic()


def test_temporal_split_puts_every_later_measurement_in_the_holdout(frame):
    train, test = temporal.temporal_split(frame, 20100)
    assert frame.registration.to_numpy()[train].max() <= 20100
    assert frame.registration.to_numpy()[test].min() > 20100
    assert len(train) + len(test) == len(frame)
    assert not set(train.tolist()) & set(test.tolist())


def test_matched_control_holds_the_sizes_fixed_and_varies_with_the_seed(frame):
    train, test = temporal.temporal_split(frame, 20100)
    a_train, a_test = temporal.random_matched_split(frame, len(train), len(test), 0)
    b_train, b_test = temporal.random_matched_split(frame, len(train), len(test), 1)
    assert len(a_train) == len(train) and len(a_test) == len(test)
    assert not set(a_train.tolist()) & set(a_test.tolist())
    assert not np.array_equal(a_train, b_train)
    assert np.array_equal(a_train, temporal.random_matched_split(frame, len(train), len(test), 0)[0])
    # The control draws from both eras, which is the whole point of it.
    assert set(frame.era.to_numpy()[a_test]) == {'earlier', 'later'}


def test_matched_control_refuses_to_exceed_the_available_measurements(frame):
    with pytest.raises(ValueError, match='cannot exceed'):
        temporal.random_matched_split(frame, len(frame), 1, 0)


def test_the_split_never_looks_at_values(frame):
    """Scrambling the values must not change which rows are chosen."""
    scrambled = frame.copy()
    scrambled['value'] = np.random.default_rng(3).permutation(scrambled.value.to_numpy())
    assert np.array_equal(temporal.temporal_split(frame, 20100)[0],
                          temporal.temporal_split(scrambled, 20100)[0])
    assert np.array_equal(temporal.random_matched_split(frame, 50, 20, 4)[0],
                          temporal.random_matched_split(scrambled, 50, 20, 4)[0])


def test_rolling_cutoffs_stay_inside_the_earlier_era_and_are_ordered(frame):
    cutoffs = temporal.rolling_cutoffs(frame, [0.5, 0.75])
    earlier = frame.loc[frame.era.eq('earlier'), 'registration']
    assert cutoffs == sorted(cutoffs)
    assert all(earlier.min() <= c <= earlier.max() for c in cutoffs)


def test_scoring_beats_the_no_model_floor_on_learnable_data(frame):
    features, scaffolds = temporal.features_for(frame, SETTINGS)
    train, test = temporal.temporal_split(frame, 20100)
    scored = temporal.fit_and_score(features, frame.value.to_numpy(float), train, test, SETTINGS)
    assert scored['train_size'] == len(train) and scored['test_size'] == len(test)
    assert scored['mae'] < scored['training_mean_mae']
    assert 0 < scored['normalised_mae'] < 1
    assert scored['spearman'] > 0.5


def test_scoring_cannot_see_test_values(frame):
    """Changing only the held-out values must not change a single prediction."""
    features, _ = temporal.features_for(frame, SETTINGS)
    values = frame.value.to_numpy(float)
    train, test = temporal.temporal_split(frame, 20100)
    altered = values.copy()
    altered[test] = altered[test] + 10.0
    scrambled = values.copy()
    scrambled[test] = np.random.default_rng(11).permutation(scrambled[test])
    baseline = temporal.fit_predict(features, values, train, test, SETTINGS)
    assert np.array_equal(baseline, temporal.fit_predict(features, altered, train, test, SETTINGS))
    assert np.array_equal(baseline, temporal.fit_predict(features, scrambled, train, test, SETTINGS))
    # Ranks are unaffected by adding a constant to every held-out value.
    first = temporal.fit_and_score(features, values, train, test, SETTINGS)
    second = temporal.fit_and_score(features, altered, train, test, SETTINGS)
    assert second['spearman'] == pytest.approx(first['spearman'], abs=1e-9)
    assert second['test_value_sd'] == pytest.approx(first['test_value_sd'], abs=1e-9)


def test_neighbourhood_reports_zero_distance_when_training_contains_the_test_rows(frame):
    features, scaffolds = temporal.features_for(frame, SETTINGS)
    indices = np.arange(len(frame))
    same = temporal.neighbourhood(features, scaffolds, indices, indices[:20])
    assert same['nearest_neighbour_distance'] == pytest.approx(0.0, abs=1e-6)
    assert same['new_scaffold_fraction'] == 0.0


def test_run_endpoint_skips_rather_than_reports_a_thin_endpoint():
    thin = synthetic(count=40)
    thin['endpoint'] = 'mgmb'
    cases = temporal.run_endpoint(thin, 'mgmb', SETTINGS)
    assert len(cases) == 1 and 'skipped' in cases[0]
    assert 'below the declared minimum' in cases[0]['skipped']


def test_run_endpoint_produces_one_temporal_case_and_one_per_seed(frame):
    settings = {**SETTINGS, 'seeds': [0, 1, 2]}
    cases = temporal.run_endpoint(frame, 'logd', settings)
    splits = pd.Series([c['split'] for c in cases]).value_counts()
    assert splits['temporal'] == 1
    assert splits['random_matched'] == 3
    assert splits.get('temporal_rolling', 0) >= 1


def test_analysis_pairs_one_gap_per_endpoint_and_reports_its_power(frame):
    settings = {**SETTINGS, 'seeds': [0, 1, 2, 3, 4]}
    cases = []
    for endpoint in ['logd', 'ksol', 'hlm_clint']:
        rows = frame.copy()
        rows['endpoint'] = endpoint
        cases.extend(temporal.run_endpoint(rows, endpoint, settings))
    result = temporal.analyse(pd.DataFrame(cases), 'normalised_mae')
    assert set(result['per_endpoint']) == {'logd', 'ksol', 'hlm_clint'}
    across = result['across_endpoints']
    assert across['endpoints'] == 3
    assert across['power']['cases'] == 3
    assert across['endpoints_worse_under_time'] + across['endpoints_better_under_time'] == 3
    entry = result['per_endpoint']['logd']
    assert entry['gap'] == pytest.approx(entry['temporal'] - entry['random_matched_mean'])
    assert entry['control_seeds'] == 5
