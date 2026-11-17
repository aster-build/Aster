"""Show what the shadow-batch comparison reports when every outcome is already known.

A retrospective illustration on the public dashboard example (MoleculeACE CHEMBL238,
160 compounds with published values), not a new evaluation. Each of 20 replays draws a
different starting set of 32 measured compounds from those 160, runs four rounds of
eight through the ordinary campaign workflow, and then reads the decision record's
shadow comparison with the hidden values filled in for the shadow compounds only.

The 20 replays reuse the same 160 compounds and one target, so they show the mechanism
working, not how the greedy policy performs in general.
"""
import argparse
import csv
import json
import tempfile
from pathlib import Path

import numpy as np

from aster.campaign import create, import_results, load, propose
from aster.decisions import shadow

ROOT = Path(__file__).resolve().parents[1]


def write(path, header, rows):
    with path.open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


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
               name='shadow replay', assay='MoleculeACE CHEMBL238 Ki task', endpoint='pKi')
        for number in range(1, rounds+1):
            record = propose(db, batch)
            import_results(db, number, write(tmp/f'results-{number}.csv', ['compound_id', 'status', 'value'],
                                             [(r['compound_id'], 'measured', truth[r['compound_id']])
                                              for r in record['recommendations']]))
            state = load(db)
            # Hidden outcomes are filled in on this in-memory copy only; the campaign
            # file never records a shadow compound as measured.
            for cid in record['shadow']['ids']:
                if state['compounds'][cid]['status'] != 'measured':
                    state['compounds'][cid].update(status='measured', value=truth[cid])
            report = shadow(state, state['rounds'][number-1])
            out.append({'replay_seed': seed, 'round': number,
                        'shared_with_batch': report['shared_with_committed_batch'],
                        **{k: v for k, v in report['comparison'].items() if k != 'note'}})
    return out


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
    rows = [row for seed in range(1000, 1000+args.replays) for row in replay(everything, seed, args.rounds, args.batch)]
    per_replay = [float(np.mean([r['batch_mean'] - r['shadow_mean'] for r in rows if r['replay_seed'] == seed]))
                  for seed in range(1000, 1000+args.replays)]
    from scipy.stats import wilcoxon
    summary = {
        'rounds_compared': len(rows),
        'replays': args.replays,
        'mean_difference_batch_minus_shadow_mean': float(np.mean(per_replay)),
        'sd_of_per_replay_difference': float(np.std(per_replay, ddof=1)),
        'replays_where_batch_mean_beat_shadow_mean': sum(d > 0 for d in per_replay),
        'wilcoxon_p_per_replay': float(wilcoxon(per_replay).pvalue),
        'rounds_where_batch_best_beat_shadow_best': sum(r['batch_better_on_best'] for r in rows),
        'rounds_where_best_tied': sum(r['batch_best'] == r['shadow_best'] for r in rows),
        'mean_compounds_shared_per_round': float(np.mean([r['shared_with_batch'] for r in rows])),
        'by_round_mean_difference': {n: float(np.mean([r['batch_mean'] - r['shadow_mean'] for r in rows if r['round'] == n]))
                                     for n in range(1, args.rounds+1)},
    }
    text = json.dumps({'summary': summary, 'rounds': rows}, indent=2)
    if args.output:
        args.output.write_text(text + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
