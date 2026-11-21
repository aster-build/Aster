import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aster import model_bracket, temporal
from tests.test_temporal import synthetic

SETTINGS = model_bracket.load_config(Path('configs/bracket-v1.json'))


def stub_arm(monkeypatch, offset=0.5):
    """Replace the TabPFN arm with an arithmetic stand-in.

    The weights are licensed and not fetched by this repository, so the runner's
    plumbing is tested against a stand-in that honours the same interface: fit on
    the training rows, predict the held-out rows. It predicts the training mean
    shifted by a constant, which is deliberately worse than ridge, so a test can
    tell the arms apart in the output.
    """
    class Stub:
        def fit(self, x, y):
            self.offset_ = float(np.mean(y)) + offset
            self.columns_ = x.shape[1]
            return self

        def predict(self, x):
            return self.offset_ + 0.01 * np.asarray(x, dtype=float)[:, 0]

    monkeypatch.setattr(model_bracket, 'tabpfn_regressor', lambda settings: Stub())
    monkeypatch.setattr(model_bracket, 'chemeleon_features',
                        lambda structures, settings: np.asarray(
                            [[len(s), s.count('c'), s.count('C')] for s in structures], dtype=float))


def test_feature_columns_reads_no_label_and_no_held_out_row():
    rng = np.random.default_rng(0)
    features = rng.normal(size=(40, 30))
    train = np.arange(20)
    chosen = model_bracket.feature_columns(features[train], 5)
    moved = features.copy()
    moved[20:] = rng.normal(size=(20, 30)) * 50
    assert np.array_equal(chosen, model_bracket.feature_columns(moved[train], 5))
    assert len(chosen) == 5 and len(set(chosen.tolist())) == 5


def test_feature_columns_keeps_the_most_varying_columns_and_breaks_ties_by_index():
    features = np.zeros((6, 4))
    features[:, 1] = [0, 1, 0, 1, 0, 1]
    features[:, 3] = [0, 1, 0, 1, 0, 1]
    features[:, 2] = [0, 0, 0, 0, 0, 1]
    assert np.array_equal(model_bracket.feature_columns(features, 2), np.array([1, 3]))
    assert np.array_equal(model_bracket.feature_columns(features, 99), np.arange(4))
    with pytest.raises(ValueError):
        model_bracket.feature_columns(features, 0)


def test_an_arm_never_sees_a_held_out_value(monkeypatch):
    stub_arm(monkeypatch)
    frame = synthetic(160)
    features, _ = temporal.features_for(frame, SETTINGS)
    values = frame.value.to_numpy(dtype=float)
    train, test = np.arange(100), np.arange(100, 160)
    before = model_bracket.predict_with('morgan_tabpfn', features, values, train, test, SETTINGS)
    tampered = values.copy()
    tampered[test] += 7.0
    after = model_bracket.predict_with('morgan_tabpfn', features, tampered, train, test, SETTINGS)
    assert np.allclose(before, after)


def test_the_default_arm_is_the_product_default_itself(monkeypatch):
    stub_arm(monkeypatch)
    frame = synthetic(160)
    features, _ = temporal.features_for(frame, SETTINGS)
    values = frame.value.to_numpy(dtype=float)
    train, test = np.arange(100), np.arange(100, 160)
    assert np.allclose(
        model_bracket.predict_with('morgan_ridge', features, values, train, test, SETTINGS),
        temporal.fit_predict(features, values, train, test, SETTINGS))


def test_both_arms_are_logged_for_every_case_on_identical_splits(monkeypatch):
    stub_arm(monkeypatch)
    frame = synthetic(200)
    frame['endpoint'] = 'logd'
    settings = dict(SETTINGS)
    settings['bracket'] = {**SETTINGS['bracket'], 'control_seeds': [0, 1]}
    rows = pd.DataFrame(model_bracket.run_endpoint(frame, 'logd', settings,
                                                   ('morgan_ridge', 'morgan_tabpfn')))
    assert 'skipped' not in rows
    per_case = rows.groupby(['split', rows.seed.fillna(-1)]).arm.apply(set)
    assert all(arms == {'morgan_ridge', 'morgan_tabpfn'} for arms in per_case)
    for split, seed in per_case.index:
        case = rows[rows.split.eq(split) & rows.seed.fillna(-1).eq(seed)]
        assert case.train_size.nunique() == 1 and case.test_size.nunique() == 1
        assert case.pool_hit_rate.nunique() == 1
    assert (rows.hits <= rows.batch_size).all()


def test_an_arm_without_weights_is_recorded_as_not_run_rather_than_dropped(monkeypatch):
    monkeypatch.setattr(model_bracket, 'tabpfn_regressor',
                        lambda settings: (_ for _ in ()).throw(
                            model_bracket.WeightsUnavailable('TabPFN checkpoint not present')))
    frame = synthetic(200)
    frame['endpoint'] = 'logd'
    settings = dict(SETTINGS)
    settings['bracket'] = {**SETTINGS['bracket'], 'control_seeds': [0]}
    rows = pd.DataFrame(model_bracket.run_endpoint(frame, 'logd', settings,
                                                   ('morgan_ridge', 'morgan_tabpfn')))
    missing = rows[rows.arm.eq('morgan_tabpfn')]
    assert len(missing) == 2 and missing.unavailable.notna().all()
    assert 'normalised_mae' not in missing.dropna(axis=1).columns
    analysis = model_bracket.analyse(rows)
    assert analysis['arms_that_did_not_run'] == {
        'morgan_tabpfn': 'TabPFN checkpoint not present'}
    assert 'morgan_tabpfn' not in analysis['arms']


def test_a_placeholder_checksum_stops_the_run_instead_of_using_unpinned_weights(tmp_path):
    checkpoint = tmp_path / 'weights.ckpt'
    checkpoint.write_bytes(b'not the pinned file')
    with pytest.raises(model_bracket.WeightsUnavailable, match='pinned checksum'):
        model_bracket.checked_checkpoint(checkpoint, 'UNVERIFIED-SET-BEFORE-FIRST-RUN', 'TabPFN')
    with pytest.raises(model_bracket.WeightsUnavailable, match='not present'):
        model_bracket.checked_checkpoint(tmp_path / 'absent.ckpt', 'anything', 'TabPFN')


def test_the_configured_tabpfn_checksum_is_still_a_placeholder():
    """Guards the claim in the write-up: no run in this repository has used weights.

    Delete this test in the same commit that pins a real checksum.
    """
    settings = json.loads(Path('configs/bracket-v1.json').read_text())
    assert settings['arms']['tabpfn']['checkpoint_sha256'] == 'UNVERIFIED-SET-BEFORE-FIRST-RUN'


def test_analysis_pairs_per_case_and_reports_what_the_pairs_could_detect(monkeypatch):
    stub_arm(monkeypatch)
    frame = synthetic(200)
    frame['endpoint'] = 'logd'
    settings = dict(SETTINGS)
    settings['bracket'] = {**SETTINGS['bracket'], 'control_seeds': [0, 1, 2]}
    rows = pd.DataFrame(model_bracket.run_endpoint(frame, 'logd', settings,
                                                   ('morgan_ridge', 'morgan_tabpfn')))
    analysis = model_bracket.analyse(rows, 'normalised_mae')
    entry = analysis['arms']['morgan_tabpfn']
    assert entry['cases'] == 4
    # The stand-in predicts a constant, so it must be the worse arm here.
    assert entry['mean_difference'] > 0 and entry['cases_where_arm_had_lower_error'] == 0
    assert np.isfinite(entry['power']['minimum_detectable_effect'])
    assert entry['power']['cases'] == 4


def test_unpaired_metrics_are_refused_rather_than_compared(monkeypatch):
    stub_arm(monkeypatch)
    frame = synthetic(200)
    frame['endpoint'] = 'logd'
    settings = dict(SETTINGS)
    settings['bracket'] = {**SETTINGS['bracket'], 'control_seeds': [0, 1]}
    rows = pd.DataFrame(model_bracket.run_endpoint(frame, 'logd', settings,
                                                   ('morgan_ridge', 'morgan_tabpfn')))
    dropped = rows.drop(rows[rows.arm.eq('morgan_tabpfn')].index[:1])
    assert 'unpaired' in model_bracket.analyse(dropped)['arms']['morgan_tabpfn']


def test_run_writes_both_files_and_records_the_versions(monkeypatch, tmp_path):
    stub_arm(monkeypatch)
    frame = synthetic(200)
    frame['endpoint'] = 'logd'
    settings = dict(SETTINGS)
    settings['endpoints'] = ['logd']
    settings['bracket'] = {**SETTINGS['bracket'], 'control_seeds': [0]}
    result = model_bracket.run(frame, settings, tmp_path, ('morgan_ridge', 'morgan_tabpfn'))
    assert (tmp_path / 'bracket_case_metrics.csv').is_file()
    saved = json.loads((tmp_path / 'bracket_comparison.json').read_text())
    assert saved['arms_declared'] == ['morgan_ridge', 'morgan_tabpfn']
    assert set(saved['versions']) >= {'numpy', 'rdkit', 'tabpfn', 'torch'}
    assert saved['error_analysis']['metric'] == 'normalised_mae'
    assert saved['discovery_analysis']['metric'] == 'hits'
    assert result['error_analysis']['baseline'] == 'morgan_ridge'


def test_config_inherits_the_temporal_protocol_and_pins_both_files():
    assert SETTINGS['endpoints'] == json.loads(
        Path('configs/temporal-v1.json').read_text())['endpoints']
    assert len(SETTINGS['config_sha256']) == 64 and len(SETTINGS['base_config_sha256']) == 64
    assert SETTINGS['config_sha256'] != SETTINGS['base_config_sha256']


def test_a_thin_endpoint_is_skipped_rather_than_reported():
    frame = synthetic(80)
    frame['endpoint'] = 'logd'
    cases = model_bracket.run_endpoint(frame, 'logd', SETTINGS, ('morgan_ridge',))
    assert len(cases) == 1 and 'below the declared minimum' in cases[0]['skipped']


def test_an_undefined_power_quantity_is_recorded_as_null_not_as_a_number():
    """Two arms that pick identically leave no spread, so no detectable effect exists."""
    rows = pd.DataFrame([
        {'endpoint': 'logd', 'split': 'temporal', 'seed': -1, 'arm': arm, 'hits': 7}
        for arm in ('morgan_ridge', 'morgan_tabpfn')
    ] + [
        {'endpoint': 'logd', 'split': 'random_matched', 'seed': 0, 'arm': arm, 'hits': 7}
        for arm in ('morgan_ridge', 'morgan_tabpfn')
    ])
    entry = model_bracket.analyse(rows, 'hits')['arms']['morgan_tabpfn']
    assert entry['mean_difference'] == 0.0
    assert entry['power']['minimum_detectable_effect'] is None
    assert json.dumps(entry)


def test_a_single_arm_run_still_prices_what_the_bracket_could_detect(monkeypatch, tmp_path):
    frame = synthetic(200)
    frame['endpoint'] = 'logd'
    settings = dict(SETTINGS)
    settings['endpoints'] = ['logd']
    settings['bracket'] = {**SETTINGS['bracket'], 'control_seeds': [0, 1, 2]}
    result = model_bracket.run(frame, settings, tmp_path, ('morgan_ridge',))
    plan = result['prospective_plan']['normalised_mae']
    assert plan['cases_available'] == 4
    assert plan['minimum_detectable_effect'] > 0
    assert result['error_analysis']['arms'] == {}
