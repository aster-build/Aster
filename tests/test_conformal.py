import numpy as np
import pytest

from aster.conformal import (ALPHA, calibrate, coverage, covers, interval, quantile_rank,
                             seed_from, smallest_calibration_size, split)


def linear_problem(count=64, noise=0.3, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(count, 12))
    y = x @ np.arange(12, dtype=float) + rng.normal(scale=noise, size=count)
    return x, y


def test_quantile_rank_and_minimum_size_agree():
    minimum = smallest_calibration_size(ALPHA)
    assert quantile_rank(minimum, ALPHA) <= minimum
    assert quantile_rank(minimum - 1, ALPHA) > minimum - 1
    # A 90% interval needs at least nine calibration points to be defined at all.
    assert minimum == 9


def test_split_is_disjoint_covers_everything_and_is_reproducible():
    fit, calibration = split(40, 1234)
    assert sorted(fit.tolist() + calibration.tolist()) == list(range(40))
    assert not set(fit.tolist()) & set(calibration.tolist())
    assert len(calibration) == 20
    again = split(40, 1234)
    assert np.array_equal(again[0], fit) and np.array_equal(again[1], calibration)
    assert not np.array_equal(split(40, 1235)[0], fit)


def test_seed_depends_only_on_the_training_hash():
    assert seed_from('a'*64) == seed_from('a'*64) != seed_from('b'*64)


def test_calibration_reports_a_half_width_from_the_right_error_rank():
    x, y = linear_problem()
    model, record = calibrate(x, y, seed=7)
    errors = np.sort(np.abs(model.predict(x[split(len(y), 7)[1]]) - y[split(len(y), 7)[1]]))
    assert record['quantile_rank'] == quantile_rank(record['calibration_size'])
    assert record['half_width'] == pytest.approx(errors[record['quantile_rank'] - 1])
    assert record['nominal_coverage'] == 0.9
    assert record['fit_size'] + record['calibration_size'] == len(y)
    assert 'exchangeable' in record['assumption']


def test_too_few_measurements_report_no_interval_rather_than_a_number():
    x, y = linear_problem(count=12)
    model, record = calibrate(x, y, seed=3)
    assert model is None and record['half_width'] is None
    assert 'fewer than the' in record['reason']
    assert interval(5.0, record['half_width'])['low'] is None


def test_interval_and_coverage_read_the_recorded_numbers():
    entry = interval(7.0, 1.5)
    assert (entry['low'], entry['high']) == (5.5, 8.5)
    assert covers(entry, 8.4) and not covers(entry, 8.6)
    assert covers(interval(7.0, None), 7.0) is None
    assert coverage([(entry, 6.0), (entry, 9.9), (interval(1.0, None), 1.0)]) == {
        'measurements': 2, 'covered': 1, 'observed_coverage': 0.5}
    assert coverage([])['observed_coverage'] is None


def test_interval_width_grows_with_the_noise_it_calibrates_on():
    quiet = calibrate(*linear_problem(noise=0.2), seed=11)[1]['half_width']
    loud = calibrate(*linear_problem(noise=2.0), seed=11)[1]['half_width']
    assert loud > quiet


def test_nominal_coverage_is_roughly_met_on_exchangeable_data():
    # The guarantee is for exchangeable draws, so this is the one case where the
    # observed rate should sit near the nominal one. Selected batches are tested
    # separately in scripts/conformal_coverage.py, where it does not hold.
    rng = np.random.default_rng(5)
    hits = []
    for trial in range(40):
        x, y = linear_problem(count=140, noise=0.8, seed=trial)
        held = rng.permutation(len(y))[:20]
        keep = np.setdiff1d(np.arange(len(y)), held)
        model, record = calibrate(x[keep], y[keep], seed=trial)
        centers = model.predict(x[held])
        hits.extend(covers(interval(c, record['half_width']), v)
                    for c, v in zip(centers, y[held]))
    assert 0.84 <= sum(hits) / len(hits) <= 0.96
