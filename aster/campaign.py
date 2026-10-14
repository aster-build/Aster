"""Local, transactional campaign workflow. No hidden outcome data are accepted."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import io
import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .acquisition import nearest_measured
from .data import canonicalize, fingerprints
from .heads import StableRidge

SCHEMA = 1
RECIPE = {"model": "Morgan + ridge", "radius": 2, "bits": 2048,
          "chirality": True, "scaling": "standard", "alpha": 10,
          "policy": "greedy", "minimum_measured": 32}


def encoded(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read_csv(path, columns):
    payload = Path(path).read_bytes()
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)) or set(reader.fieldnames) != set(columns):
        raise ValueError(f"{path}: expected exactly these columns: {', '.join(columns)}")
    rows = []
    for number, row in enumerate(reader, 2):
        if None in row or any(v is None for v in row.values()):
            raise ValueError(f"{path}: malformed row {number}")
        row = {k: v.strip() for k, v in row.items()}
        if not row['compound_id'] or any(ord(c) < 32 for c in row['compound_id']):
            raise ValueError(f"{path}: invalid compound_id on row {number}")
        rows.append(row)
    if not rows or len({r['compound_id'] for r in rows}) != len(rows):
        raise ValueError(f"{path}: require nonempty CSV and unique compound IDs")
    return rows, hashlib.sha256(payload).hexdigest()


def value_number(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        raise ValueError("Measurements must be exact numeric pKi or pIC50; censored values are unsupported") from None
    if not math.isfinite(value):
        raise ValueError("Measurements must be finite")
    return value


def event(state, action, details):
    state['events'].append({'sequence': len(state['events']) + 1, 'at': stamp(),
                            'action': action, 'details': details})


@contextmanager
def transaction(path, write=False):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f"Campaign does not exist: {path}")
    connection = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=30)
    try:
        connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        row = connection.execute('SELECT payload FROM campaign WHERE id=1').fetchone()
        if row is None:
            raise ValueError('Campaign is uninitialized')
        state = json.loads(row[0])
        if state['schema'] != SCHEMA:
            raise ValueError('Unsupported campaign schema')
        yield state
        if write:
            connection.execute('UPDATE campaign SET payload=? WHERE id=1', (encoded(state),))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def load(path):
    with transaction(path) as state:
        return state


def create(path, measured, candidates, *, name, assay, endpoint):
    if endpoint not in ('pKi', 'pIC50') or not name.strip() or not assay.strip():
        raise ValueError('Require a campaign name, single assay identifier, and pKi or pIC50 endpoint')
    observations, mh = read_csv(measured, ['compound_id', 'smiles', 'value'])
    pool, ph = read_csv(candidates, ['compound_id', 'smiles'])
    if len(observations) < RECIPE['minimum_measured']:
        raise ValueError('At least 32 measured compounds are required for this workflow')
    compounds, identities = {}, set()
    for rows, status in ((observations, 'measured'), (pool, 'available')):
        for row in rows:
            cid = row['compound_id']
            structure, identity = canonicalize(row['smiles'])
            if cid in compounds or identity in identities:
                raise ValueError(f'Duplicate compound ID or molecular identity: {cid}')
            identities.add(identity)
            compounds[cid] = {'smiles': structure, 'identity': identity, 'status': status,
                              'value': value_number(row['value']) if status == 'measured' else None,
                              'constraint': 'available'}
    state = {'schema': SCHEMA, 'name': name.strip(), 'assay': assay.strip(), 'endpoint': endpoint,
             'created_at': stamp(), 'recipe': RECIPE, 'compounds': compounds, 'rounds': [], 'events': []}
    event(state, 'create', {'measured_sha256': mh, 'candidates_sha256': ph,
                            'initial_count': len(observations), 'candidate_count': len(pool)})
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents overwriting an existing campaign.
    with path.open('xb'):
        pass
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute('CREATE TABLE campaign(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
            connection.execute('INSERT INTO campaign VALUES(1, ?)', (encoded(state),))
    finally:
        connection.close()
    return state


def constrain(path, ids, mode):
    if mode not in ('available', 'locked', 'excluded') or not ids or len(set(ids)) != len(ids):
        raise ValueError('Require unique compound IDs and an available, locked, or excluded constraint')
    with transaction(path, True) as state:
        for cid in ids:
            if cid not in state['compounds'] or state['compounds'][cid]['status'] != 'available':
                raise ValueError(f'Constraint changes require an available candidate: {cid}')
        for cid in ids:
            state['compounds'][cid]['constraint'] = mode
        event(state, 'constraints', {'ids': ids, 'mode': mode})


def propose(path, batch_size=8):
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
        raise ValueError('Batch size must be a positive integer')
    with transaction(path, True) as state:
        if any(r['status'] == 'pending' for r in state['rounds']):
            raise ValueError('Finish importing the pending batch before proposing another round')
        if state['recipe'] != RECIPE:
            raise ValueError('Campaign recipe differs from this implementation; use its recorded version')
        compounds = state['compounds']
        observed = sorted(cid for cid, c in compounds.items() if c['status'] == 'measured')
        pool = sorted(cid for cid, c in compounds.items() if c['status'] == 'available' and c['constraint'] != 'excluded')
        locked = [cid for cid in pool if compounds[cid]['constraint'] == 'locked']
        if len(pool) < batch_size or len(locked) > batch_size:
            raise ValueError('Insufficient eligible candidates or more locked candidates than batch slots')
        x = fingerprints([compounds[c]['smiles'] for c in observed])
        y = np.asarray([compounds[c]['value'] for c in observed])
        model = StableRidge('standard', 10).fit(x, y)
        # Chunk scoring and nearest-neighbour evidence to bound similarity matrix size.
        predictions, neighbours, similarities = [], [], []
        for start in range(0, len(pool), 256):
            chunk = pool[start:start+256]
            features = fingerprints([compounds[c]['smiles'] for c in chunk])
            predictions.extend(model.predict(features).tolist())
            nearest, novelty = nearest_measured(features, x)
            neighbours.extend([observed[i] for i in nearest])
            similarities.extend((1-novelty).tolist())
        if not np.isfinite(predictions).all():
            raise ValueError('Nonfinite predictions; no batch was saved')
        by_id = {cid: i for i, cid in enumerate(pool)}
        ranked = sorted((cid for cid in pool if cid not in locked), key=lambda cid: (-predictions[by_id[cid]], cid))
        selected = locked + ranked[:batch_size-len(locked)]
        rows = []
        for rank, cid in enumerate(selected, 1):
            i = by_id[cid]
            neighbour = neighbours[i]
            rows.append({'rank': rank, 'compound_id': cid, 'smiles': compounds[cid]['smiles'],
                         'prediction': predictions[i], 'selection_reason': 'user_locked' if cid in locked else 'highest_prediction',
                         'nearest_measured_id': neighbour, 'nearest_measured_value': compounds[neighbour]['value'],
                         'similarity': similarities[i], 'outside_diagnostic_range': not 0 <= predictions[i] <= 14})
        coef, intercept = model.linear_coefficients()
        snapshot = [{'compound_id': cid, **compounds[cid]} for cid in observed]
        round_record = {'round': len(state['rounds']) + 1, 'created_at': stamp(), 'status': 'pending',
                        'training': snapshot, 'training_sha256': hashlib.sha256(encoded(snapshot).encode()).hexdigest(),
                        'eligible_ids': pool, 'constraints': {cid: compounds[cid]['constraint'] for cid in pool},
                        'recommendations': rows, 'results': {}, 'recipe': state['recipe'],
                        'model': {'coefficients': coef.tolist(), 'intercept': intercept},
                        'versions': {p: importlib.metadata.version(p) for p in ('rdkit', 'numpy', 'scikit-learn')},
                        'source_sha256': {p: hashlib.sha256(Path(__file__).with_name(p).read_bytes()).hexdigest()
                                          for p in ('campaign.py', 'data.py', 'heads.py', 'acquisition.py')}}
        for cid in selected:
            compounds[cid]['status'] = 'pending'
        state['rounds'].append(round_record)
        event(state, 'propose', {'round': round_record['round'], 'ids': selected,
                                'training_sha256': round_record['training_sha256']})
        return round_record


def import_results(path, round_number, source):
    rows, sha = read_csv(source, ['compound_id', 'status', 'value'])
    with transaction(path, True) as state:
        if not 1 <= round_number <= len(state['rounds']):
            raise ValueError('Unknown round')
        record = state['rounds'][round_number-1]
        expected = {r['compound_id'] for r in record['recommendations']}
        parsed = {}
        for row in rows:
            cid, status = row['compound_id'], row['status']
            if cid not in expected or status not in ('measured', 'failed'):
                raise ValueError(f'Result must belong to this round and be measured or failed: {cid}')
            if status == 'failed' and row['value']:
                raise ValueError('Failed assays must have an empty value')
            result = {'status': status, 'value': value_number(row['value']) if status == 'measured' else None}
            if cid in record['results'] and record['results'][cid] != result:
                raise ValueError(f'Cannot overwrite a recorded result: {cid}')
            parsed[cid] = result
        new = {cid: result for cid, result in parsed.items() if cid not in record['results']}
        if not new:
            return {'added': 0, 'round_status': record['status']}
        for cid, result in new.items():
            state['compounds'][cid].update(result)
            record['results'][cid] = result
        if set(record['results']) == expected:
            record['status'] = 'complete'
        event(state, 'import_results', {'round': round_number, 'sha256': sha, 'ids': sorted(new)})
        return {'added': len(new), 'round_status': record['status']}


def export_batch(path, round_number, destination, template=False):
    state = load(path)
    if not 1 <= round_number <= len(state['rounds']):
        raise ValueError('Unknown round')
    rows = state['rounds'][round_number-1]['recommendations']
    if template:
        rows = [{'compound_id': row['compound_id'], 'status': '', 'value': ''} for row in rows]
    else:
        rows = [{**row, 'endpoint': state['endpoint'], 'assay': state['assay']} for row in rows]
    # Machine-readable CSV preserves exact IDs for round trips.
    with Path(destination).open('x', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summary(path):
    state = load(path)
    counts = {status: sum(c['status'] == status for c in state['compounds'].values())
              for status in ('measured', 'available', 'pending', 'failed')}
    return {'name': state['name'], 'assay': state['assay'], 'endpoint': state['endpoint'],
            'counts': counts, 'rounds': [{'round': r['round'], 'status': r['status'],
                                         'training_count': len(r['training']), 'results': len(r['results'])}
                                        for r in state['rounds']],
            'constraints': {k: sum(c['constraint'] == k and c['status'] == 'available' for c in state['compounds'].values())
                            for k in ('locked', 'excluded')}, 'events': len(state['events'])}


def main():
    parser = argparse.ArgumentParser(description='Aster local campaign workflow (one assay, higher pKi/pIC50 is better)')
    parser.add_argument('--db', required=True, type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('create')
    for key in ('name', 'assay', 'measured', 'candidates'):
        init.add_argument('--'+key, required=True)
    init.add_argument('--endpoint', choices=['pKi', 'pIC50'], required=True)
    constraints = commands.add_parser('constrain')
    constraints.add_argument('mode', choices=['available', 'locked', 'excluded'])
    constraints.add_argument('ids', nargs='+')
    proposal = commands.add_parser('propose')
    proposal.add_argument('--batch-size', type=int, default=8)
    export = commands.add_parser('export')
    export.add_argument('--round', type=int, required=True)
    export.add_argument('--output', required=True)
    export.add_argument('--template', action='store_true')
    results = commands.add_parser('import-results')
    results.add_argument('--round', type=int, required=True)
    results.add_argument('--csv', required=True)
    commands.add_parser('status')
    snapshot = commands.add_parser('snapshot')
    snapshot.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'create':
            create(args.db, args.measured, args.candidates, name=args.name, assay=args.assay, endpoint=args.endpoint)
            output = summary(args.db)
        elif args.command == 'constrain':
            constrain(args.db, args.ids, args.mode)
            output = summary(args.db)
        elif args.command == 'propose':
            record = propose(args.db, args.batch_size)
            output = {k: record[k] for k in ('round', 'status', 'recommendations')}
        elif args.command == 'export':
            export_batch(args.db, args.round, args.output, args.template)
            output = {'exported': args.output}
        elif args.command == 'import-results':
            output = import_results(args.db, args.round, args.csv)
        elif args.command == 'snapshot':
            with Path(args.output).open('x') as handle:
                handle.write(encoded(load(args.db)) + '\n')
            output = {'snapshot': args.output}
        else:
            output = summary(args.db)
        print(json.dumps(output, indent=2, allow_nan=False))
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f'Aster campaign: {error}\n')


if __name__ == '__main__':
    main()
