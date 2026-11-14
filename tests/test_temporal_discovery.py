import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aster import temporal
from aster import temporal_discovery as discovery
from tests.test_temporal import synthetic

SETTINGS = json.loads(Path('configs/temporal-v1.json').read_text())


def test_native_thresholds_are_converted_to_the_fitted_scale():
    # 100 uM on a log10-fitted endpoint is a threshold of 2.0.
    scaled = discovery.scale_criterion({'kind': 'max', 'threshold': 100.0}, 'log10')
    assert scaled == {'kind': 'max', 'threshold': pytest.approx(2.0)}
    # An untransformed endpoint keeps its own units.
    assert discovery.scale_criterion({'kind': 'window', 'low': 1.0, 'high': 3.0},
                                     'identity') == {'kind': 'window', 'low': 1.0, 'high': 3.0}
    with pytest.raises(ValueError, match='Unknown criterion kind'):
        discovery.scale_criterion({'kind': 'nonsense'}, 'identity')


def test_sensitivity_moves_each_criterion_in_the_harder_direction():
    more_is_better = {'kind': 'max', 'threshold': 100.0}
    less_is_better = {'kind': 'min', 'threshold': 20.0}
    window = {'kind': 'window', 'low': 1.0, 'high': 3.0}
    assert discovery.adjust_criterion(more_is_better, 0.5)['threshold'] == 200.0
    assert discovery.adjust_criterion(more_is_better, 2.0)['threshold'] == 50.0
    assert discovery.adjust_criterion(less_is_better, 0.5)['threshold'] == 10.0
    assert discovery.adjust_criterion(less_is_better, 2.0)['threshold'] == 40.0
    strict = discovery.adjust_criterion(window, 0.5)
    assert (strict['low'], strict['high']) == (1.5, 2.5)
    loose = discovery.adjust_criterion(window, 2.0)
    assert (loose['low'], loose['high']) == (0.5, 3.5)
    assert discovery.adjust_criterion(window, 1.0) == window


def test_hits_and_desirability_agree_about_which_direction_is_good():
    values = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    more = {'kind': 'max', 'threshold': 2.0}
    assert discovery.hits(values, more).tolist() == [False, False, True, True, True]
    assert np.argmax(discovery.desirability(values, more)) == 4
    less = {'kind': 'min', 'threshold': 2.0}
    assert discovery.hits(values, less).tolist() == [True, True, True, False, False]
    assert np.argmax(discovery.desirability(values, less)) == 0
    window = {'kind': 'window', 'low': 1.0, 'high': 3.0}
    assert discovery.hits(values, window).tolist() == [False, True, True, True, False]
    # The most desirable prediction under a window is its centre, not an extreme.
    assert np.argmax(discovery.desirability(values, window)) == 2


def test_greedy_takes_the_top_scores_and_random_varies_by_seed():
    scores = np.array([0.0, 5.0, 1.0, 4.0, 2.0])
    taken = discovery.pick('greedy', scores, 2, np.random.default_rng(0))
    assert sorted(taken.tolist()) == [1, 3]
    a = discovery.pick('random', scores, 3, np.random.default_rng(1))
    assert len(set(a.tolist())) == 3
    with pytest.raises(ValueError, match='Batch exceeds'):
        discovery.pick('greedy', scores, 9, np.random.default_rng(0))
    with pytest.raises(ValueError, match='Unknown policy'):
        discovery.pick('coin-flip', scores, 2, np.random.default_rng(0))


def test_greedy_ties_break_on_pool_position_not_on_values():
    scores = np.zeros(6)
    assert discovery.pick('greedy', scores, 3, np.random.default_rng(0)).tolist() == [0, 1, 2]


def test_discovery_case_reports_both_policies_and_never_exceeds_the_best_possible():
    frame = synthetic(count=240)
    features, _ = temporal.features_for(frame, SETTINGS)
    values = frame.value.to_numpy(float)
    train, pool = temporal.temporal_split(frame, 20100)
    criterion = {'kind': 'max', 'threshold': float(np.median(values))}
    settings = {**SETTINGS, 'discovery': {**SETTINGS['discovery'], 'batch_size': 20}}
    rows = discovery.discovery_case(features, values, train, pool, criterion, settings,
                                    [0, 1, 2], split='temporal', control_seed=None,
                                    endpoint='logd', endpoint_label='LogD',
                                    strictness='declared',
                                    criterion_applied=json.dumps(criterion))
    policies = pd.Series([r['policy'] for r in rows]).value_counts()
    assert policies['greedy'] == 1 and policies['random'] == 3
    for row in rows:
        assert 0 <= row['hits'] <= row['best_possible_hits'] <= row['batch_size']
        assert row['pool_hits'] >= row['hits']


def test_picking_cannot_see_the_pool_values():
    """Scrambling the pool's values must not change which compounds greedy picks."""
    frame = synthetic(count=240)
    features, _ = temporal.features_for(frame, SETTINGS)
    values = frame.value.to_numpy(float)
    train, pool = temporal.temporal_split(frame, 20100)
    criterion = {'kind': 'max', 'threshold': float(np.median(values))}
    scrambled = values.copy()
    scrambled[pool] = np.random.default_rng(5).permutation(scrambled[pool])
    first = temporal.fit_predict(features, values, train, pool, SETTINGS)
    second = temporal.fit_predict(features, scrambled, train, pool, SETTINGS)
    assert np.array_equal(first, second)
    assert np.array_equal(discovery.pick('greedy', discovery.desirability(first, criterion), 20,
                                         np.random.default_rng(0)),
                          discovery.pick('greedy', discovery.desirability(second, criterion), 20,
                                         np.random.default_rng(0)))


def test_run_endpoint_skips_a_pool_smaller_than_the_batch():
    thin = synthetic(count=80)
    thin['endpoint'] = 'mgmb'
    settings = {**SETTINGS, 'discovery': {**SETTINGS['discovery'], 'batch_size': 100}}
    cases = discovery.run_endpoint(thin, 'mgmb', settings, 'declared')
    assert len(cases) == 1 and 'below the declared minimum' in cases[0]['skipped']


def test_analysis_separates_the_two_advantages_per_strictness():
    frame = synthetic(count=240)
    settings = {**SETTINGS, 'seeds': [0, 1, 2],
                'discovery': {**SETTINGS['discovery'], 'batch_size': 20}}
    cases = []
    for strictness in ('declared', 'strict'):
        cases.extend(discovery.run_endpoint(frame, 'logd', settings, strictness))
    result = discovery.analyse(pd.DataFrame(cases))
    assert set(result['by_strictness']) == {'declared', 'strict'}
    entry = result['by_strictness']['declared']['per_endpoint']['logd']
    assert entry['temporal_advantage'] == pytest.approx(
        entry['temporal_greedy_hits'] - entry['temporal_random_hits_mean'])
    assert entry['advantage_lost_to_time'] == pytest.approx(
        entry['random_split_advantage'] - entry['temporal_advantage'])
    across = result['by_strictness']['declared']['across_endpoints']
    assert across['endpoints'] == 1
    assert across['units'].startswith('extra compounds')


def test_every_endpoint_has_a_declared_criterion_with_a_reason():
    criteria = SETTINGS['discovery']['criteria']
    assert set(criteria) == set(SETTINGS['endpoints'])
    for endpoint, criterion in criteria.items():
        assert criterion['kind'] in {'max', 'min', 'window'}
        assert criterion['reason'].endswith('.')
        assert criterion['units']
        if criterion['kind'] == 'window':
            assert criterion['low'] < criterion['high']
        else:
            assert criterion['threshold'] > 0
