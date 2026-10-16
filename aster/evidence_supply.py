"""Milestone 9 retest: does external evidence help when supply is not the limit?

Milestone 9 compared a literature-augmented selector to the campaign-only default on
one target and found no gain. That comparison could not separate two explanations: the
evidence does not help, or the corpus supplied too little of it. Only 12 of 31 usable
corpus structures were permitted, because the corpus and the replay dataset were built
from the same source.

This study removes the supply limit by holding measurements out of the replay task and
handing them back as external evidence. Donor measurements are the most favourable
evidence that could exist: the same assay, the same endpoint, exact equality relations,
no curation noise, and structures that are genuinely absent from the task. The supplied
count is swept from the milestone 9 figure upward, across every available target, under
two donor regimes:

  donor_random             donors drawn uniformly, so some sit near pool chemotypes
  donor_scaffold_disjoint  donors drawn as whole Murcko scaffold groups, so the task
                           retains no scaffold a donor belongs to

Each regime carries a value-permuted control at the same supply, which holds the number
of extra training rows fixed and destroys only the structure-value link. A gain the
control reproduces is an artifact of extra rows, not of evidence.

The result is an upper bound: if measurements this clean do not improve selection at
these supplies, a literature corpus of the same size cannot, and neither can a noisier
structural descriptor of the same size. Donor removal shrinks the task, so every arm in
a case is compared on the same shrunken task, same split, same seed and same budget.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .benchmark import load_task, split_case
from .data import digest, fingerprints, write_json
from .evidence_power import plan, report
from .evidence_selection import replay, score, seal
from .experiment import LabelOracle

DONOR_MODES = ('donor_random', 'donor_scaffold_disjoint')
MINIMUM_FILL = 0.9


def donors(frame: pd.DataFrame, mode: str, count: int, seed: int) -> np.ndarray:
    """Choose donor rows from structure metadata only; outcomes are never consulted."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, count, 9091]))
    if count <= 0:
        return np.array([], dtype=int)
    if count >= len(frame):
        raise ValueError('Donor count must leave a task behind')
    if mode == 'donor_random':
        return np.sort(rng.choice(len(frame), count, replace=False))
    if mode == 'donor_scaffold_disjoint':
        groups = list(frame.groupby('scaffold', sort=True).indices.values())
        chosen: list[int] = []
        for index in rng.permutation(len(groups)):
            group = groups[index]
            if len(chosen) + len(group) > count:
                continue
            chosen.extend(int(i) for i in group)
            if len(chosen) == count:
                break
        # Whole groups rarely sum to the requested count exactly; the shortfall is
        # recorded per case rather than filled with part of a group.
        if len(chosen) < MINIMUM_FILL * count:
            raise ValueError(f'Scaffold groups filled only {len(chosen)} of {count} donors')
        return np.sort(np.array(chosen, dtype=int))
    raise ValueError(f'Unknown donor mode {mode}')


def guard(values: np.ndarray, declared) -> list[float]:
    """Measured range widened by one standard deviation, unless the study fixes it."""
    if isinstance(declared, (list, tuple)):
        return [float(declared[0]), float(declared[1])]
    if declared != 'task_measured_range_plus_sd':
        raise ValueError(f'Unknown prediction guard {declared}')
    spread = float(np.std(values, ddof=1))
    return [float(values.min()) - spread, float(values.max()) + spread]


def case_rows(frame: pd.DataFrame, features: np.ndarray, study: dict, task: str,
              mode: str, count: int, protocol: str, size: int, seed: int) -> list[dict]:
    """One paired case: baseline, donor-augmented and permuted control on one split."""
    donor_index = donors(frame, mode, count, seed)
    kept = np.setdiff1d(np.arange(len(frame)), donor_index)
    task_frame = frame.iloc[kept].reset_index(drop=True)
    task_x = features[kept]
    donor_x = features[donor_index]
    donor_y = frame.iloc[donor_index].value.to_numpy()

    if mode == 'donor_scaffold_disjoint':
        overlap = set(frame.iloc[donor_index].scaffold) & set(task_frame.scaffold)
        if overlap:
            raise ValueError('Donor scaffolds remain in the task; aborting')
    if set(frame.iloc[donor_index].identity) & set(task_frame.identity):
        raise ValueError('Donor structure remains in the task; aborting')

    case = split_case(task_frame, protocol, seed, size)
    working = case['initial'] + case['pool']
    oracle_values = task_frame.iloc[working].value.to_numpy()
    local = dict(study)
    local['prediction_guard'] = guard(task_frame.value.to_numpy(), study['prediction_guard'])
    permuted = np.random.default_rng(
        np.random.SeedSequence([seed, count, 909])).permutation(len(donor_y))

    rows = []
    for arm in study['arms']:
        if arm['evidence'] == 'none':
            extra_x, extra_y = donor_x[:0], np.zeros(0)
        elif arm['evidence'] == 'donor_measurements':
            extra_x, extra_y = donor_x, donor_y
        elif arm['evidence'] == 'donor_measurements_shuffled':
            extra_x, extra_y = donor_x, donor_y[permuted]
        elif arm['evidence'] == 'donor_measurements_noisy':
            # Real corpora report the same quantity with disagreement between sources;
            # the declared spread is added to donor values to see whether a gain survives.
            noise = np.random.default_rng(
                np.random.SeedSequence([seed, count, 9093])).normal(
                    0.0, float(arm['value_noise_sd']), len(donor_y))
            extra_x, extra_y = donor_x, donor_y + noise
        else:
            raise ValueError(f"Unknown evidence setting {arm['evidence']}")
        result = replay(task_x[working], task_x[case['audit']], LabelOracle(oracle_values),
                        np.arange(size), local, seed, extra_x, extra_y)
        rows.append({'task': task, 'protocol': protocol, 'support_size': size,
                     'donor_mode': mode, 'donor_count': count, 'seed': seed,
                     'arm': arm['id'], 'task_rows': len(task_frame),
                     'donor_rows': int(len(donor_index)),
                     'pool_size': len(case['pool']), 'audit_size': len(case['audit']),
                     'guard_low': local['prediction_guard'][0],
                     'guard_high': local['prediction_guard'][1],
                     **score(task_frame, case, result, local)})
    return rows


def compare(metrics: pd.DataFrame, study: dict) -> dict:
    """Pre-declared gate, read off the paired differences with their power accounting."""
    powered = report(metrics, metric=study['primary_metric_column'],
                     effects=tuple(study['declared_effects']),
                     alpha=study['alpha'], target=study['target_power'])
    gate = study['promotion_gate']
    decisions = {}
    for mode in study['donor_modes']:
        subset = metrics[metrics.donor_mode == mode]
        at_gate = subset[subset.donor_count == max(study['donor_counts'])]
        powered_mode = report(at_gate, metric=study['primary_metric_column'],
                              effects=tuple(study['declared_effects']),
                              alpha=study['alpha'], target=study['target_power'])
        evidence = powered_mode['arms'][gate['evidence_arm']]
        control = powered_mode['arms'].get(gate['control_arm'])
        gain = evidence['mean_paired_difference']
        # A study may omit the permuted control, in which case the separation half of the
        # gate cannot be read and only the gain threshold applies.
        separation = None if control is None else gain - control['mean_paired_difference']
        decisions[mode] = {
            'donor_count': int(max(study['donor_counts'])),
            'cases': evidence['cases'],
            'mean_gain': gain,
            'control_arm': gate['control_arm'] if control is not None else None,
            'control_gain': None if control is None else control['mean_paired_difference'],
            'separation_from_control': separation,
            'gain_threshold': gate['mean_top_decile_gain_min'],
            'separation_threshold': gate['control_separation_min'] if control is not None else None,
            'confidence_interval': evidence['confidence_interval'],
            'largest_effect_not_ruled_out': evidence['largest_effect_not_ruled_out'],
            'minimum_detectable_effect': evidence['minimum_detectable_effect'],
            'passes': bool(gain >= gate['mean_top_decile_gain_min']
                           and (separation is None
                                or separation >= gate['control_separation_min']))}
    supply = {}
    for mode in study['donor_modes']:
        for count in study['donor_counts']:
            subset = metrics[(metrics.donor_mode == mode) & (metrics.donor_count == count)]
            curve = report(subset, metric=study['primary_metric_column'],
                           effects=tuple(study['declared_effects']),
                           alpha=study['alpha'], target=study['target_power'])
            supply[f'{mode}:{count}'] = {
                arm: {key: entry[key] for key in
                      ('cases', 'mean_paired_difference', 'standard_error',
                       'confidence_interval', 'minimum_detectable_effect')}
                for arm, entry in curve['arms'].items()}
    by_task = {}
    for task in sorted(metrics.task.unique()):
        subset = metrics[metrics.task == task]
        curve = report(subset, metric=study['primary_metric_column'],
                       effects=tuple(study['declared_effects']),
                       alpha=study['alpha'], target=study['target_power'])
        by_task[task] = {arm: {key: entry[key] for key in
                               ('cases', 'mean_paired_difference', 'confidence_interval')}
                         for arm, entry in curve['arms'].items()}
    passes = any(decision['passes'] for decision in decisions.values())
    out = {'cases_per_arm': int(len(metrics[metrics.arm == 'baseline'])),
           'power': powered, 'gate': decisions, 'supply_curve': supply, 'by_task': by_task,
           'passes': passes}
    out['conclusion'] = (
        'At least one donor regime meets the predeclared gate; evidence augmentation '
        'is worth pursuing beyond the decision record.' if passes else
        'No donor regime meets the predeclared gate at any supply tested. Since donor '
        'measurements are the cleanest evidence obtainable for these tasks, the '
        'milestone 9 null is not explained by evidence supply, and a larger or better '
        'curated corpus of the same kind is not expected to change selection.')
    return out


def run(study_path: Path, raw: Path, out: Path) -> None:
    study = json.loads(Path(study_path).read_text())
    out = Path(out)
    seal(out, {'study': digest(Path(study_path)), 'study_version': study['version'],
               'tasks': sorted(study['tasks']), 'donor_modes': study['donor_modes'],
               'donor_counts': study['donor_counts'],
               'arms': [arm['id'] for arm in study['arms']]})
    write_json(out / 'planned_power.json',
               {'assumption': study['power_assumption'],
                'plan': plan(study['power_assumption']['paired_difference_sd'],
                             study['power_assumption']['planned_cases'],
                             tuple(study['declared_effects']), study['alpha'],
                             study['target_power'])})

    rows, provenances = [], {}
    for task, sha in sorted(study['tasks'].items()):
        frame, provenance = load_task(Path(raw) / f'{task}.csv', {'id': task, 'sha256': sha})
        provenances[task] = provenance
        features = fingerprints(frame.smiles.tolist(), study['radius'], study['bits'])
        for mode in study['donor_modes']:
            for count in study['donor_counts']:
                for protocol in study['protocols']:
                    for size in study['support_sizes']:
                        for seed in study['seeds']:
                            rows.extend(case_rows(frame, features, study, task, mode,
                                                  count, protocol, size, seed))
                print(f'{task} {mode} donors={count}: '
                      f'{len(rows)} rows so far', flush=True)
    metrics = pd.DataFrame(rows)
    metrics.to_csv(out / 'case_metrics.csv', index=False)
    write_json(out / 'task_provenance.json',
               {task: {key: value for key, value in record.items() if key != 'rejected'}
                for task, record in provenances.items()})
    write_json(out / 'comparison.json', compare(metrics, study))


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Milestone 9 retest: evidence supply across targets')
    parser.add_argument('--study', type=Path, default=Path('configs/evidence-supply-v1.json'))
    parser.add_argument('--raw', type=Path, default=Path('data/moleculeace'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/evidence-supply-v1'))
    args = parser.parse_args()
    run(args.study, args.raw, args.output)


if __name__ == '__main__':
    main()
