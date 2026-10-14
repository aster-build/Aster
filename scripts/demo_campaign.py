"""Exercise the public CLI twice using existing public measurements, not new assays."""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = 'afd41130f62d97bf9c09ff9c881355cbccf6d1004ec8a1f4acb0189b7a05c7f9'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/campaign-demo-v1')
    parser.add_argument('--source', type=Path, default=ROOT/'artifacts/reliability-v1-prepared/CHEMBL238_Ki.csv')
    args = parser.parse_args()
    sha = hashlib.sha256(args.source.read_bytes()).hexdigest()
    if sha != SOURCE_SHA:
        raise ValueError('Demo source differs from the pinned curated CHEMBL238 task')
    frame = pd.read_csv(args.source)
    train = frame[frame.published_split.eq('train')].sort_values('compound_id').reset_index(drop=True)
    order = np.random.default_rng(0).permutation(len(train))
    observed = train.iloc[order[:32]]
    pool = train.iloc[order[32:160]]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    measured_path, candidate_path = out/'measured.csv', out/'candidates.csv'
    observed[['compound_id', 'smiles', 'value']].to_csv(measured_path, index=False)
    pool[['compound_id', 'smiles']].to_csv(candidate_path, index=False)
    db = out/'campaign.sqlite'
    commands = []

    def run(*arguments):
        command = [sys.executable, '-m', 'aster.campaign', '--db', str(db), *map(str, arguments)]
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
        result = json.loads(completed.stdout)
        commands.append({'arguments': list(map(str, arguments)), 'response': result})
        return result

    run('create', '--name', 'Public dopamine-transporter demo', '--assay', 'MoleculeACE CHEMBL238 Ki task',
        '--endpoint', 'pKi', '--measured', measured_path, '--candidates', candidate_path)
    locked, excluded = pool.compound_id.iloc[0], pool.compound_id.iloc[1]
    run('constrain', 'locked', locked)
    run('constrain', 'excluded', excluded)
    lookup = pool.set_index('compound_id').value.to_dict()  # Only demo driver can see these outcomes.
    batches = []
    for number in (1, 2):
        proposal = run('propose')
        batches.append(proposal)
        run('export', '--round', number, '--output', out/f'round-{number}-recommendations.csv')
        run('export', '--round', number, '--output', out/f'round-{number}-result-template.csv', '--template')
        # Reveal existing measurements only AFTER the recommendation has been committed and exported.
        rows = [{'compound_id': r['compound_id'], 'status': 'measured', 'value': lookup[r['compound_id']]}
                for r in proposal['recommendations']]
        results_path = out/f'round-{number}-results.csv'
        with results_path.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=['compound_id', 'status', 'value'])
            writer.writeheader()
            writer.writerows(rows)
        run('import-results', '--round', number, '--csv', results_path)
        retry = run('import-results', '--round', number, '--csv', results_path)
        assert retry['added'] == 0
    status = run('status')
    run('snapshot', '--output', out/'snapshot.json')
    snapshot = json.loads((out/'snapshot.json').read_text())
    all_selected = [r['compound_id'] for b in batches for r in b['recommendations']]
    assert len(set(all_selected)) == 16 and excluded not in all_selected and locked in all_selected[:8]
    assert status['counts']['measured'] == 48
    assert [r['training_count'] for r in status['rounds']] == [32, 40]
    assert all(r['status'] == 'complete' for r in status['rounds'])
    assert not set(all_selected) & set(frame.loc[frame.published_split.eq('test'), 'compound_id'])
    for record in snapshot['rounds']:
        training_ids = {r['compound_id'] for r in record['training']}
        assert all(r['nearest_measured_id'] in training_ids for r in record['recommendations'])
    manifest = {'source': str(args.source.resolve()), 'source_sha256': sha,
                'upstream': 'https://github.com/molML/MoleculeACE/tree/7e6de0bd2968c56589c580f2a397f01c531ede26',
                'seed': 0, 'initial': 32, 'candidates': 128,
                'locked': locked, 'excluded': excluded, 'status': status,
                'purpose': 'Workflow verification on previously inspected public data; not a new model evaluation or prospective experiment.'}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
    (out/'REPORT.md').write_text('''# Aster campaign workflow verification

Two complete rounds ran through the command-line interface using existing public
CHEMBL238 dopamine-transporter measurements. This is a product workflow check,
not a new scientific benchmark or laboratory experiment.

- Started with 32 measured compounds and 128 candidates, drawn only from the published Train partition.
- Committed and exported two batches of eight before revealing their existing outcomes.
- Round 1 trained on 32 measurements; round 2 trained on 40; the campaign ended with 48 measurements.
- Selected 16 unique candidates; respected a user-locked pick and an excluded compound.
- Result-import retries added zero duplicate measurements.
- Every recommendation references a neighbour that was measured at decision time.
- Saved model coefficients, training snapshots, recipe, package versions, source hashes, and event history.

See `commands.json` for the actual CLI operations, `snapshot.json` for the complete
campaign record, and `round-*-recommendations.csv` for per-compound predictions and evidence.

The predictor is Morgan fingerprints + standardized ridge (alpha 10), with greedy
ranking and explicit user constraints. Similarity is descriptive evidence, not
calibrated confidence. Candidate outcomes are absent from campaign inputs until import.
No new claim about predictive quality follows from passing this workflow check.
''')
    print(json.dumps({'report': str(out/'REPORT.md'), 'status': status}, indent=2))


if __name__ == '__main__':
    main()
