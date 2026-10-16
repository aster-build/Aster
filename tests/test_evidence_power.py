import numpy as np
import pandas as pd
import pytest

from aster import evidence_power as power


def metrics(values_by_arm, keys=('task', 'seed')):
    rows = []
    for arm, values in values_by_arm.items():
        for i, value in enumerate(values):
            rows.append({'task': 'T', 'seed': i, 'arm': arm, 'top_decile_found': value})
    return pd.DataFrame(rows)


def test_power_rises_with_cases_and_effect():
    assert power.power(1.0, 2.0, 100) > power.power(1.0, 2.0, 20)
    assert power.power(2.0, 2.0, 40) > power.power(1.0, 2.0, 40)
    assert power.power(1.0, 2.0, 40) > power.power(1.0, 4.0, 40)


def test_detectable_effect_and_required_cases_agree():
    sd, cases = 2.0, 60
    effect = power.detectable_effect(sd, cases)
    assert power.power(effect, sd, cases) == pytest.approx(0.8, abs=0.01)
    needed = power.required_cases(effect, sd)
    assert abs(needed - cases) <= max(3, cases * 0.06)


def test_smaller_effects_need_more_cases():
    needed = [power.required_cases(effect, 2.0) for effect in (1.0, 0.5, 0.25)]
    assert needed == sorted(needed)
    assert needed[2] > 4 * needed[0]


def test_paired_differences_require_matching_cases():
    frame = metrics({'baseline': [1, 2, 3], 'arm': [2, 3, 4]})
    delta = power.paired_differences(frame, 'arm', 'top_decile_found')
    assert delta.tolist() == [1.0, 1.0, 1.0]
    unpaired = frame[~((frame.arm == 'arm') & (frame.seed == 2))]
    with pytest.raises(ValueError):
        power.paired_differences(unpaired, 'arm', 'top_decile_found')


def test_summary_reports_interval_and_ruled_out_bound():
    rng = np.random.default_rng(0)
    delta = pd.Series(rng.normal(0.2, 2.0, 200))
    summary = power.summarize(delta)
    low, high = summary['confidence_interval']
    assert low < summary['mean_paired_difference'] < high
    assert summary['largest_effect_not_ruled_out'] == high
    assert summary['minimum_detectable_effect'] < 1.0
    assert summary['paired_t']['p_value'] > 0.05


def test_report_covers_every_non_baseline_arm():
    frame = metrics({'baseline': [1, 2, 3, 4], 'a': [2, 4, 4, 6], 'b': [0, 0, 2, 2]})
    out = power.report(frame)
    assert set(out['arms']) == {'a', 'b'}
    assert out['arms']['a']['mean_paired_difference'] == 1.5
    assert out['arms']['b']['mean_paired_difference'] == -1.5
    assert out['pairing_keys'] == ['task', 'seed']


def test_degenerate_inputs_do_not_claim_power():
    assert np.isnan(power.power(1.0, 0.0, 10))
    assert np.isnan(power.power(1.0, 2.0, 1))
    assert power.required_cases(1.0, 0.0) is None
