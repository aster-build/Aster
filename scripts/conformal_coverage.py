"""Measure what the conformal interval's coverage actually is, on picks and on the pool.

The interval each pick carries aims to contain the eventual measurement nine times in
ten. That aim rests on an assumption: that the compound being predicted is like the
compounds the interval was calibrated on. Greedy selection breaks it on purpose, because
it picks the compounds the model scored highest. This script measures the size of that
break instead of asserting it.

Protocol, on the public dashboard example (MoleculeACE CHEMBL238, 160 compounds with
published pKi values, so every outcome is already known):

  - Each replay draws a different starting set of 32 measured compounds and runs four
    rounds of eight through the ordinary campaign workflow.
  - After each round, the stored interval for every candidate in the slate is checked
    against that compound's published value. No model is refitted here; the intervals
    are the ones the round recorded.
  - Three groups are counted separately: the eight compounds the policy selected, the
    eight in the round's matched random shadow batch, and every eligible candidate.

Interval widths are also compared with the same recipe applied to a model that predicts
the average of what it was trained on, which is the cheapest thing a model can do. An
interval no narrower than that one has bought no precision.

The shadow group is the control: a random draw from the same pool, which is what the
nominal level assumes. One target and one dataset, so the numbers below describe this
dataset, not drug discovery.
"""
import argparse
import csv
import json
import tempfile
from pathlib import Path

import numpy as np

from aster.campaign import create, import_results, propose
from aster.conformal import ALPHA, covers, interval, quantile_rank, seed_from, split

ROOT = Path(__file__).resolve().parents[1]


def write(path, header, rows):
    with path.open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def mean_baseline(record):
    """The same interval recipe around a model that ignores chemistry entirely.

    It predicts the average of what it was trained on. Calibrated on the same held-out
    half, with the same quantile, so its half-width is directly comparable: if the ridge
    model's interval is no narrower than this one, the model has bought no precision.
    """
    values = np.asarray([row['value'] for row in record['training']], dtype=float)
    fit_rows, calibration_rows = split(len(values), seed_from(record['training_sha256']))
    errors = np.sort(np.abs(float(values[fit_rows].mean()) - values[calibration_rows]))
    return {'center': float(values[fit_rows].mean()),
            'half_width': float(errors[quantile_rank(len(errors), ALPHA) - 1])}


def counts(rows, half_width, truth):
    """How many of these candidates' measurements land inside their stored interval."""
    flags = [covers(interval(row['interval_center'], half_width), truth[row['compound_id']])
             for row in rows]
    widths = [2 * half_width] * len(flags)
    return {'candidates': len(flags), 'inside': sum(flags),
            'coverage': sum(flags) / len(flags) if flags else None,
            'mean_width': float(np.mean(widths)) if widths else None}


def replay(everything, seed, rounds, batch):
    order = np.random.default_rng(seed).permutation(len(everything))
    initial, pool = [everything[i] for i in order[:32]], [everything[i] for i in order[32:]]
    truth = {cid: value for cid, _, value in everything}
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        db = tmp/'campaign.sqlite'
        create(db, write(tmp/'measured.csv', ['compound_id', 'smiles', 'value'], initial),
               write(tmp/'candidates.csv', ['compound_id', 'smiles'], [(c, s) for c, s, _ in pool]),
               name='conformal coverage', assay='MoleculeACE CHEMBL238 Ki task', endpoint='pKi')
        for number in range(1, rounds+1):
            record = propose(db, batch)
            half = record['uncertainty']['half_width']
            slate = record['slate']
            shadow = set(record['shadow']['ids'])
            out.append({
                'replay_seed': seed, 'round': number, 'half_width': half,
                'calibration_size': record['uncertainty']['calibration_size'],
                'baseline_half_width': mean_baseline(record)['half_width'],
                'selected': counts([r for r in slate if r['selected']], half, truth),
                'shadow': counts([r for r in slate if r['compound_id'] in shadow], half, truth),
                'eligible': counts(slate, half, truth),
            })
            import_results(db, number, write(tmp/f'results-{number}.csv',
                                             ['compound_id', 'status', 'value'],
                                             [(r['compound_id'], 'measured', truth[r['compound_id']])
                                              for r in record['recommendations']]))
    return out


def pooled(rows, group):
    inside = sum(row[group]['inside'] for row in rows)
    total = sum(row[group]['candidates'] for row in rows)
    return {'candidates': total, 'inside': inside,
            'coverage': inside / total if total else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replays', type=int, default=20)
    parser.add_argument('--rounds', type=int, default=4)
    parser.add_argument('--batch', type=int, default=8)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    fixture = ROOT/'examples/dashboard'
    truth = {r['compound_id']: float(r['value']) for r in csv.DictReader((fixture/'outcomes.csv').open())}
    everything = ([(r['compound_id'], r['smiles'], float(r['value']))
                   for r in csv.DictReader((fixture/'measured.csv').open())] +
                  [(r['compound_id'], r['smiles'], truth[r['compound_id']])
                   for r in csv.DictReader((fixture/'candidates.csv').open())])
    seeds = range(2000, 2000+args.replays)
    rows = [row for seed in seeds for row in replay(everything, seed, args.rounds, args.batch)]
    per_replay = {group: [float(np.mean([row[group]['coverage'] for row in rows
                                         if row['replay_seed'] == seed])) for seed in seeds]
                  for group in ('selected', 'shadow', 'eligible')}
    from scipy.stats import wilcoxon
    gaps = [s - r for s, r in zip(per_replay['selected'], per_replay['shadow'])]
    width_gaps = [float(np.mean([row['half_width'] - row['baseline_half_width'] for row in rows
                                 if row['replay_seed'] == seed])) for seed in seeds]
    summary = {
        'nominal_coverage': 0.9, 'replays': args.replays, 'rounds_per_replay': args.rounds,
        'batch': args.batch, 'rounds_measured': len(rows),
        'pooled': {group: pooled(rows, group) for group in ('selected', 'shadow', 'eligible')},
        'mean_per_replay_coverage': {group: float(np.mean(values)) for group, values in per_replay.items()},
        'sd_per_replay_coverage': {group: float(np.std(values, ddof=1)) for group, values in per_replay.items()},
        'mean_selected_minus_shadow': float(np.mean(gaps)),
        'sd_selected_minus_shadow': float(np.std(gaps, ddof=1)),
        'replays_where_selected_coverage_was_lower': sum(gap < 0 for gap in gaps),
        'wilcoxon_p_selected_vs_shadow': float(wilcoxon(gaps).pvalue),
        'mean_half_width': float(np.mean([row['half_width'] for row in rows])),
        # The same interval recipe around a model that predicts the training average.
        'mean_half_width_of_mean_baseline': float(np.mean([row['baseline_half_width'] for row in rows])),
        'rounds_where_model_interval_was_narrower': sum(row['half_width'] < row['baseline_half_width']
                                                        for row in rows),
        'mean_width_difference_model_minus_baseline': float(np.mean(width_gaps)),
        'sd_width_difference_model_minus_baseline': float(np.std(width_gaps, ddof=1)),
        'wilcoxon_p_width_model_vs_baseline': float(wilcoxon(width_gaps).pvalue),
        'by_round_selected_coverage': {n: float(np.mean([row['selected']['coverage'] for row in rows
                                                         if row['round'] == n]))
                                       for n in range(1, args.rounds+1)},
    }
    text = json.dumps({'summary': summary, 'rounds': rows}, indent=2)
    if args.output:
        args.output.write_text(text + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
