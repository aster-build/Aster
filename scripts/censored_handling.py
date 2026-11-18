"""What the three ways of handling a censored measurement do to the picks.

A censored measurement is one the assay could not quantify: it reports a limit instead
of a value, like "< 5" for a compound too weak to measure on the tested range. A
workflow has three options, and this script measures all three on the same data.

  discarded    The measurement is thrown away, because the store cannot represent it.
               This is what Aster did before this release: it accepted exact numbers
               only, so a bound was refused at the door.
  substituted  The bound is written down as if it were the value. This is the common
               practice, and the one that cannot be undone later: nothing downstream
               can tell a limit of detection from a result.
  bounded      The bound is kept as a bound and fitted as one: a censored row's target
               is the model's own prediction where the bound allows it, and the bound
               itself otherwise. This is what this release does.

Protocol, on the public dashboard example (MoleculeACE CHEMBL238, 160 compounds whose
pKi values are all published, so every outcome is already known):

  - Each replay draws a different starting set of 56 compounds and leaves 104 in the
    pool, then runs four rounds of eight through the ordinary campaign workflow. The
    starting set is larger than the workflow's minimum of 32 on purpose: the arm that
    discards censored measurements starts with fewer than it was given, and it has to
    clear the minimum in every replay for the three arms to stay comparable.
  - A censoring limit is applied to every measurement as it enters a campaign, in the
    starting set and in each round's results. The limit is a percentile of the dataset,
    so the censoring rate is the same in every replay. Both directions are available,
    because a real assay has both: an assay whose tested range runs out at the weak end
    reports "< limit" for everything below it, and one that saturates at the strong end
    reports "> limit" for everything above it.
  - The three arms see exactly the same assay results. They differ only in what their
    store can represent, which is the thing under test.
  - Picks are then scored against the published values, which no arm ever sees. A
    "strong" compound is one in the top decile of the whole dataset by published pKi.

pKi is a potency scale on which larger is better. One target, one dataset, one
censoring rule: these numbers describe this dataset, not drug discovery.
"""
import argparse
import csv
import json
import tempfile
from pathlib import Path

import numpy as np

from aster.campaign import create, import_results, propose

ROOT = Path(__file__).resolve().parents[1]
ARMS = ('discarded', 'substituted', 'bounded')


def write(path, header, rows):
    with path.open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def reported(value, limit, side, arm):
    """What this arm's store records for a measurement of `value`.

    Returns the text to store, or None when the arm cannot represent the measurement at
    all and has to drop it. `side` is 'low' for an assay that cannot quantify below the
    limit and 'high' for one that saturates above it.
    """
    censored = value <= limit if side == 'low' else value >= limit
    if not censored:
        return f'{value}'
    if arm == 'discarded':
        return None
    if arm == 'substituted':
        return f'{limit}'
    return f'< {limit}' if side == 'low' else f'> {limit}'


def arm_replay(everything, seed, limit, side, arm, rounds, batch, strong):
    """One arm of one replay: four rounds of eight, scored against published values."""
    order = np.random.default_rng(seed).permutation(len(everything))
    initial = [everything[i] for i in order[:56]]
    pool = [everything[i] for i in order[56:]]
    truth = {cid: value for cid, _, value in everything}
    measured_rows = [(cid, smiles, reported(value, limit, side, arm)) for cid, smiles, value in initial]
    kept = [row for row in measured_rows if row[2] is not None]
    out, best, found = [], None, 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        db = tmp/'campaign.sqlite'
        create(db, write(tmp/'measured.csv', ['compound_id', 'smiles', 'value'], kept),
               write(tmp/'candidates.csv', ['compound_id', 'smiles'], [(c, s) for c, s, _ in pool]),
               name=f'censored handling ({arm})', assay='MoleculeACE CHEMBL238 Ki task',
               endpoint='pKi')
        for number in range(1, rounds+1):
            record = propose(db, batch)
            picks = [row['compound_id'] for row in record['recommendations']]
            values = [truth[cid] for cid in picks]
            best = max([best] + values) if best is not None else max(values)
            found += sum(truth[cid] >= strong for cid in picks)
            errors = [abs(truth[cid] - row['prediction'])
                      for cid, row in zip(picks, record['recommendations'])]
            out.append({
                'replay_seed': seed, 'arm': arm, 'round': number,
                'measurements_known': len(record['training']),
                'censored_known': record['censoring']['censored'],
                'picks_strong': int(sum(truth[cid] >= strong for cid in picks)),
                'cumulative_strong': int(found),
                'best_found_so_far': float(best),
                'mean_absolute_error_on_picks': float(np.mean(errors)),
                'mean_true_value_of_picks': float(np.mean(values)),
                'interval_half_width': record['uncertainty']['half_width'],
                'target_shift_from_bound': record['censoring']['mean_target_shift_from_bound'],
            })
            results = []
            for cid in picks:
                text = reported(truth[cid], limit, side, arm)
                # An arm that cannot store the measurement has to record the assay as
                # giving nothing, which is what discarding a censored result means.
                results.append((cid, 'measured', text) if text is not None else (cid, 'failed', ''))
            import_results(db, number, write(tmp/f'results-{number}.csv',
                                             ['compound_id', 'status', 'value'], results))
    return out


def per_replay(rows, arm, field, seeds):
    """One number per replay for one arm, so the arms can be compared in pairs."""
    return [float(np.mean([row[field] for row in rows if row['arm'] == arm and row['replay_seed'] == seed]))
            for seed in seeds]


def final(rows, arm, field, seeds):
    """The end-of-replay value of a running total, one per replay."""
    return [float([row[field] for row in rows
                   if row['arm'] == arm and row['replay_seed'] == seed][-1]) for seed in seeds]


def paired(first, second):
    """A paired comparison of two arms over the same replays."""
    from scipy.stats import wilcoxon
    gaps = [a - b for a, b in zip(first, second)]
    if not any(gaps):
        return {'mean_difference': 0.0, 'sd_difference': 0.0, 'replays_better': 0,
                'replays_worse': 0, 'wilcoxon_p': None,
                'note': 'The two arms gave identical numbers in every replay.'}
    return {'mean_difference': float(np.mean(gaps)), 'sd_difference': float(np.std(gaps, ddof=1)),
            'replays_better': sum(gap > 0 for gap in gaps),
            'replays_worse': sum(gap < 0 for gap in gaps),
            'wilcoxon_p': float(wilcoxon(gaps).pvalue)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replays', type=int, default=40)
    parser.add_argument('--rounds', type=int, default=4)
    parser.add_argument('--batch', type=int, default=8)
    parser.add_argument('--censor-side', choices=('low', 'high'), default='low',
                        help="'low' for an assay that cannot quantify weak compounds, which "
                             "censors the bottom of the range; 'high' for one that saturates on "
                             "the strong ones, which censors the top")
    parser.add_argument('--censor-percentile', type=float, default=None,
                        help='The percentile of the dataset the limit sits at. Defaults to the '
                             '25th from the censored side.')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    fixture = ROOT/'examples/dashboard'
    truth = {r['compound_id']: float(r['value']) for r in csv.DictReader((fixture/'outcomes.csv').open())}
    everything = ([(r['compound_id'], r['smiles'], float(r['value']))
                   for r in csv.DictReader((fixture/'measured.csv').open())] +
                  [(r['compound_id'], r['smiles'], truth[r['compound_id']])
                   for r in csv.DictReader((fixture/'candidates.csv').open())])
    values = np.asarray([value for _, _, value in everything])
    percentile = args.censor_percentile
    if percentile is None:
        percentile = 25.0 if args.censor_side == 'low' else 75.0
    limit = float(np.round(np.percentile(values, percentile), 2))
    strong = float(np.percentile(values, 90))
    seeds = list(range(3000, 3000+args.replays))
    rows = [row for seed in seeds for arm in ARMS
            for row in arm_replay(everything, seed, limit, args.censor_side, arm,
                                  args.rounds, args.batch, strong)]
    strong_total = {arm: final(rows, arm, 'cumulative_strong', seeds) for arm in ARMS}
    best_total = {arm: final(rows, arm, 'best_found_so_far', seeds) for arm in ARMS}
    error = {arm: per_replay(rows, arm, 'mean_absolute_error_on_picks', seeds) for arm in ARMS}
    summary = {
        'dataset': 'MoleculeACE CHEMBL238 Ki task, 160 compounds with published pKi values',
        'endpoint': 'pKi, larger is better',
        'replays': args.replays, 'rounds_per_replay': args.rounds, 'batch': args.batch,
        'assays_per_replay': args.rounds * args.batch,
        'censoring_limit': limit, 'censoring_percentile': percentile,
        'censored_side': args.censor_side,
        'censored_share_of_dataset': float(np.mean(values <= limit if args.censor_side == 'low'
                                                   else values >= limit)),
        'strong_threshold': strong,
        'strong_compounds_in_dataset': int(np.sum(values >= strong)),
        'measurements_known_at_first_round': {
            arm: float(np.mean([row['measurements_known'] for row in rows
                                if row['arm'] == arm and row['round'] == 1])) for arm in ARMS},
        'mean_strong_found_per_replay': {arm: float(np.mean(totals)) for arm, totals in strong_total.items()},
        'sd_strong_found_per_replay': {arm: float(np.std(totals, ddof=1)) for arm, totals in strong_total.items()},
        'mean_best_found_per_replay': {arm: float(np.mean(totals)) for arm, totals in best_total.items()},
        'mean_absolute_error_on_picks': {arm: float(np.mean(e)) for arm, e in error.items()},
        'mean_interval_half_width': {
            arm: (lambda widths: float(np.mean(widths)) if widths else None)(
                [row['interval_half_width'] for row in rows
                 if row['arm'] == arm and row['interval_half_width'] is not None]) for arm in ARMS},
        'bounded_minus_substituted': {
            'strong_found': paired(strong_total['bounded'], strong_total['substituted']),
            'best_found': paired(best_total['bounded'], best_total['substituted']),
            # Lower error is better, so the sign here is the other way round.
            'mean_absolute_error': paired(error['bounded'], error['substituted'])},
        'bounded_minus_discarded': {
            'strong_found': paired(strong_total['bounded'], strong_total['discarded']),
            'best_found': paired(best_total['bounded'], best_total['discarded']),
            'mean_absolute_error': paired(error['bounded'], error['discarded'])},
    }
    text = json.dumps({'summary': summary, 'rounds': rows}, indent=2)
    if args.output:
        args.output.write_text(text + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
