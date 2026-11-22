import numpy as np
import pytest

from aster.censored import (EXACT, best_known, bounds, clip, compare, exact_rows, fit, is_censored,
                            measurement, parse, summarize, text)
from aster.heads import StableRidge


def ridge(x, y):
    return StableRidge('standard', 10).fit(x, y)


def linear_problem(count=60, seed=0, noise=0.2):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(count, 8))
    y = x @ np.arange(8, dtype=float) + rng.normal(scale=noise, size=count)
    return x, y


@pytest.mark.parametrize('reported, expected', [
    ('7.4', (EXACT, 7.4)), ('  7.4 ', (EXACT, 7.4)), ('= 7.4', (EXACT, 7.4)),
    ('> 10', ('>', 10.0)), ('>10', ('>', 10.0)), ('>= 10', ('>=', 10.0)), ('≥ 10', ('>=', 10.0)),
    ('< 0.5', ('<', 0.5)), ('<=0.5', ('<=', 0.5)), ('≤ 0.5', ('<=', 0.5)), ('=< 0.5', ('<=', 0.5)),
])
def test_parse_reads_bounds_and_exact_numbers(reported, expected):
    assert parse(reported) == expected


@pytest.mark.parametrize('reported', ['', '   ', None, 'ten', '> ten', '>', 'nan', 'inf', '1e'])
def test_parse_refuses_what_it_cannot_read(reported):
    with pytest.raises(ValueError):
        parse(reported)


def test_measurement_keeps_relation_value_and_unit():
    assert measurement('> 10', 'uM') == {'relation': '>', 'value': 10.0, 'unit': 'uM'}
    assert not is_censored(measurement('7.4'))
    assert is_censored(measurement('< 7.4'))
    # A stored number with no relation at all predates censoring and is read as exact.
    assert not is_censored({'value': 7.4})
    assert text(10.0, '>', 'uM') == '> 10.00 uM' and text(7.4) == '7.40'


def test_bounds_leave_the_censored_side_open():
    assert bounds('>', 10) == (10.0, None)
    assert bounds('<=', 10) == (None, 10.0)
    assert bounds(EXACT, 10) == (10.0, 10.0)


@pytest.mark.parametrize('relation, value, threshold, sign, expected', [
    ('>', 10, 8, 1, True),      # above 10 certainly beats 8 when larger is better
    ('>', 10, 12, 1, None),     # above 10 may or may not beat 12
    ('>', 10, 12, -1, None),    # above 10 may be 11 (beats 12) or 13 (does not), smaller better
    ('>', 10, 10, -1, False),   # above 10 certainly does not beat 10 when smaller is better
    ('<', 0.5, 1, -1, True),
    ('<', 0.5, 0.2, -1, None),
    (EXACT, 9, 8, 1, True),
    (EXACT, 8, 8, 1, False),
])
def test_compare_says_none_when_a_bound_does_not_settle_it(relation, value, threshold, sign, expected):
    assert compare(relation, value, threshold, sign) == expected


def test_best_known_is_uncertain_when_the_best_measurement_is_an_open_bound():
    records = [{'relation': EXACT, 'value': 7.0}, {'relation': '>', 'value': 10.0}]
    best = best_known(records, 1)
    assert best['value'] == 10.0 and best['relation'] == '>' and best['certain'] is False
    # The same set read on an endpoint where smaller is better: the bound is on the worse
    # side, so the exact 7.0 is the best known value and it is certain.
    worse = best_known(records, -1)
    assert worse['value'] == 7.0 and worse['certain'] is True


def test_best_known_falls_back_to_bounds_and_reports_nothing_known():
    only_bounds = best_known([{'relation': '<', 'value': 5.0}, {'relation': '<', 'value': 4.0}], 1)
    assert only_bounds['value'] == 5.0 and only_bounds['certain'] is False
    assert best_known([], 1) == {'value': None, 'relation': None, 'certain': False,
                                'reason': 'No measurements were known when this round was proposed.'}


def test_summarize_counts_each_kind_of_bound():
    assert summarize([{'relation': EXACT, 'value': 1}, {'relation': '>', 'value': 2},
                      {'relation': '<=', 'value': 3}, {'value': 4}]) == {
        'measurements': 4, 'exact': 2, 'upper_bounded': 1, 'lower_bounded': 1, 'censored': 2}


def test_clip_pulls_predictions_into_the_region_the_bound_allows():
    targets = clip([5.0, 15.0, 5.0, 15.0, 99.0], ['>', '>', '<', '<', EXACT], [10, 10, 10, 10, 1])
    # Below a '>' bound the bound wins; above it the prediction stands. The reverse for '<'.
    np.testing.assert_allclose(targets, [10.0, 15.0, 5.0, 10.0, 1.0])


def test_fit_without_censoring_is_the_ordinary_fit():
    x, y = linear_problem()
    model, record = fit(x, y, [EXACT]*len(y), ridge)
    np.testing.assert_allclose(model.predict(x), ridge(x, y).predict(x), atol=1e-12)
    assert record['iterations'] == 1 and record['censored'] == 0 and record['converged']
    assert record['mean_target_shift_from_bound'] == 0.0


def test_fit_moves_censored_targets_off_their_bounds_and_converges():
    x, y = linear_problem()
    relations = [EXACT]*len(y)
    values = y.copy()
    # Censor the ten largest measurements at a bound well below their true values, the way
    # an assay that saturates would report them.
    for index in np.argsort(y)[-10:]:
        relations[index], values[index] = '>', float(y[index]) - 3.0
    model, record = fit(x, values, relations, ridge)
    assert record['censored'] == 10 and record['lower_bounded'] == 10 and record['converged']
    assert record['iterations'] > 1
    # Every censored target ends at or above its bound, and at least one moved off it.
    targets = clip(model.predict(x), relations, values)
    assert np.all(targets[[i for i, r in enumerate(relations) if r == '>']]
                  >= values[[i for i, r in enumerate(relations) if r == '>']] - 1e-9)
    assert record['largest_target_shift_from_bound'] > 0
    # Fitting the bounds as if they were values pulls the fit down on exactly those rows,
    # so the censoring-aware fit predicts them higher.
    substituted = ridge(x, values)
    censored_rows = [i for i, r in enumerate(relations) if r == '>']
    assert np.mean(model.predict(x)[censored_rows]) > np.mean(substituted.predict(x)[censored_rows])


def test_fit_reports_when_it_runs_out_of_iterations():
    x, y = linear_problem()
    relations = [EXACT]*len(y)
    values = y.copy()
    for index in np.argsort(y)[-20:]:
        relations[index], values[index] = '>', float(y[index]) - 5.0
    _, record = fit(x, values, relations, ridge, tolerance=0.0, max_iterations=3)
    assert record['iterations'] == 3 and record['converged'] is False


def test_fit_refuses_mismatched_relations():
    x, y = linear_problem(count=20)
    with pytest.raises(ValueError):
        fit(x, y, [EXACT]*(len(y)-1), ridge)


def test_exact_rows_selects_only_uncensored_measurements():
    assert exact_rows([EXACT, '>', EXACT, '<=']).tolist() == [0, 2]
