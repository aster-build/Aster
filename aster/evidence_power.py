"""Power accounting for the paired evidence studies.

Every evidence arm is compared to a baseline arm on the same split, seed and
budget, so the unit of analysis is a paired per-case difference. This module
reports what such a comparison can and cannot detect: the achieved power for a
declared effect, the minimum detectable effect at the cases actually run, the
cases a smaller effect would require, and the interval that a null rules out.
It computes nothing from outcomes other than the metrics file it is given, and
it is meant to be run before committing to an expensive arm.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from .data import write_json

PAIR_KEYS = ('task', 'protocol', 'support_size', 'donor_mode', 'donor_count', 'seed')
DEFAULT_EFFECTS = (1.0, 0.5, 0.25)


def pair_keys(metrics: pd.DataFrame) -> list[str]:
    """Pairing columns present in this metrics file, in declared order."""
    keys = [key for key in PAIR_KEYS if key in metrics.columns]
    if not keys:
        raise ValueError('No pairing columns found in metrics')
    return keys


def paired_differences(metrics: pd.DataFrame, arm: str, metric: str,
                       baseline: str = 'baseline',
                       keys: list[str] | None = None) -> pd.Series:
    """Per-case arm-minus-baseline differences, aligned on the pairing columns."""
    keys = keys or pair_keys(metrics)
    left = metrics[metrics.arm == baseline].set_index(keys).sort_index()
    right = metrics[metrics.arm == arm].set_index(keys).sort_index()
    if not left.index.equals(right.index):
        raise ValueError(f'Unpaired cases between {baseline} and {arm}')
    return (right[metric] - left[metric]).astype(float)


def power(effect: float, sd: float, cases: int, alpha: float = 0.05) -> float:
    """Power of a two-sided paired t-test, from the noncentral t distribution."""
    if cases < 2 or sd <= 0 or effect <= 0:
        return float('nan')
    df = cases - 1
    ncp = effect / (sd / np.sqrt(cases))
    critical = stats.t.ppf(1 - alpha / 2, df)
    exact = stats.nct.sf(critical, df, ncp) + stats.nct.cdf(-critical, df, ncp)
    if np.isfinite(exact):
        return float(exact)
    # The noncentral t integral loses precision at large noncentrality, where power is
    # effectively one; fall back to the normal approximation rather than return nothing.
    return float(stats.norm.sf(critical - ncp) + stats.norm.cdf(-critical - ncp))


def detectable_effect(sd: float, cases: int, alpha: float = 0.05,
                      target: float = 0.8) -> float:
    """Smallest effect this many cases would detect at the target power."""
    if cases < 2 or sd <= 0:
        return float('nan')
    low, high = 1e-6, 100.0 * sd
    for _ in range(200):
        mid = (low + high) / 2
        if power(mid, sd, cases, alpha) < target:
            low = mid
        else:
            high = mid
    return float((low + high) / 2)


def required_cases(effect: float, sd: float, alpha: float = 0.05,
                   target: float = 0.8, limit: int = 2_000_000) -> int | None:
    """Cases needed to reach the target power against a true effect of this size."""
    if sd <= 0 or effect <= 0:
        return None
    cases = 2
    while cases < limit:
        if power(effect, sd, cases, alpha) >= target:
            return cases
        cases = cases + 1 if cases < 64 else int(cases * 1.05) + 1
    return None


def summarize(delta: pd.Series, effects=DEFAULT_EFFECTS, alpha: float = 0.05,
              target: float = 0.8) -> dict:
    """Observed difference, what it rules out, and what the design could detect."""
    cases = int(len(delta))
    mean = float(delta.mean())
    sd = float(delta.std(ddof=1)) if cases > 1 else float('nan')
    se = sd / np.sqrt(cases) if cases > 1 else float('nan')
    half = stats.t.ppf(1 - alpha / 2, cases - 1) * se if cases > 1 else float('nan')
    report = {
        'cases': cases, 'mean_paired_difference': mean,
        'standard_deviation': sd, 'standard_error': float(se) if cases > 1 else None,
        'confidence_level': 1 - alpha,
        'confidence_interval': [float(mean - half), float(mean + half)] if cases > 1 else None,
        'largest_effect_not_ruled_out': float(mean + half) if cases > 1 else None,
        'minimum_detectable_effect': detectable_effect(sd, cases, alpha, target),
        'target_power': target,
        'power_against_declared_effects': {
            f'{effect:g}': power(effect, sd, cases, alpha) for effect in effects},
        'cases_required_for_effects': {
            f'{effect:g}': required_cases(effect, sd, alpha, target) for effect in effects},
    }
    if cases > 1:
        statistic, pvalue = stats.ttest_1samp(delta, 0.0)
        report['paired_t'] = {'statistic': float(statistic), 'p_value': float(pvalue),
                              'test': 'two-sided one-sample t on paired differences'}
    return report


def plan(sd: float, cases_available: int, effects=DEFAULT_EFFECTS, alpha: float = 0.05,
         target: float = 0.8) -> dict:
    """Prospective view: what a planned design could detect at a given spread."""
    return {'assumed_standard_deviation': sd, 'cases_available': cases_available,
            'minimum_detectable_effect': detectable_effect(sd, cases_available, alpha, target),
            'power_against_declared_effects': {
                f'{effect:g}': power(effect, sd, cases_available, alpha) for effect in effects},
            'cases_required_for_effects': {
                f'{effect:g}': required_cases(effect, sd, alpha, target) for effect in effects}}


def report(metrics: pd.DataFrame, metric: str = 'top_decile_found',
           baseline: str = 'baseline', effects=DEFAULT_EFFECTS,
           alpha: float = 0.05, target: float = 0.8,
           by: str | None = None) -> dict:
    """Power accounting for every non-baseline arm, optionally per subgroup."""
    keys = pair_keys(metrics)
    arms = [arm for arm in metrics.arm.unique() if arm != baseline]
    out = {'metric': metric, 'baseline_arm': baseline, 'pairing_keys': keys,
           'declared_effects': list(effects), 'arms': {}}
    for arm in sorted(arms):
        delta = paired_differences(metrics, arm, metric, baseline, keys)
        entry = summarize(delta, effects, alpha, target)
        if by and by in metrics.columns:
            level = keys.index(by)
            entry['by_' + by] = {
                str(value): summarize(delta.xs(value, level=level), effects, alpha, target)
                for value in sorted(delta.index.get_level_values(level).unique())}
        out['arms'][arm] = entry
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description='Paired power accounting for evidence arms')
    parser.add_argument('--metrics', type=Path, required=True,
                        help='case_metrics.csv from an evidence study')
    parser.add_argument('--metric', default='top_decile_found')
    parser.add_argument('--baseline', default='baseline')
    parser.add_argument('--effects', type=float, nargs='+', default=list(DEFAULT_EFFECTS))
    parser.add_argument('--alpha', type=float, default=0.05)
    parser.add_argument('--target-power', type=float, default=0.8)
    parser.add_argument('--by', default=None, help='pairing column to break results down by')
    parser.add_argument('--output', type=Path, default=None)
    args = parser.parse_args()
    result = report(pd.read_csv(args.metrics), args.metric, args.baseline,
                    tuple(args.effects), args.alpha, args.target_power, args.by)
    result['metrics_file'] = str(args.metrics)
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
