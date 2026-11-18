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

from . import censored, conformal
from .acquisition import nearest_measured
from .data import canonicalize, fingerprints
from .heads import StableRidge

SCHEMA = 1
RECIPE = {"model": "Morgan + ridge", "radius": 2, "bits": 2048,
          "chirality": True, "scaling": "standard", "alpha": 10,
          "policy": "greedy", "minimum_measured": 32}
DIRECTIONS = ('higher_is_better', 'lower_is_better')
# A prediction is flagged when it lies this many observed standard deviations
# beyond the measured range. It is a diagnostic, not a calibrated bound.
EXTRAPOLATION_MARGIN = 1.0


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


def measured_value(text):
    """Read one reported measurement on the declared endpoint.

    Exact numbers and bounds are both accepted: "7.4", "> 10", "< 0.5". A bound is
    stored as a bound, so nothing downstream can mistake a limit of detection for a
    result. Returns the relation and the number; see `aster/censored.py`.
    """
    return censored.parse(text)


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


def declaration(state):
    """Any endpoint, any assay, one number per compound.

    Campaigns created before endpoints were declared carry a log-potency endpoint
    where larger is better, which is what this workflow assumed at the time.
    """
    return {'endpoint': state['endpoint'], 'unit': state.get('unit', ''),
            'direction': state.get('direction', 'higher_is_better')}


def better(state):
    """+1 when larger measurements are better, -1 when smaller ones are."""
    return 1.0 if declaration(state)['direction'] == 'higher_is_better' else -1.0


def create(path, measured, candidates, *, name, assay, endpoint, unit='', direction='higher_is_better'):
    endpoint, unit = endpoint.strip(), unit.strip()
    if not endpoint or len(endpoint) > 100 or any(ord(c) < 32 for c in endpoint + unit) or len(unit) > 60:
        raise ValueError('Require a printable endpoint name of at most 100 characters')
    if direction not in DIRECTIONS:
        raise ValueError(f"Declare which direction is better: {' or '.join(sorted(DIRECTIONS))}")
    if not name.strip() or not assay.strip():
        raise ValueError('Require a campaign name and a single assay identifier')
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
            # `relation` says how to read `value`: '=' for an exact measurement, '<', '<=',
            # '>' or '>=' when the assay reported a bound instead. It is None for a
            # candidate, which has no measurement at all.
            relation, value = measured_value(row['value']) if status == 'measured' else (None, None)
            compounds[cid] = {'smiles': structure, 'identity': identity, 'status': status,
                              'value': value, 'relation': relation, 'constraint': 'available'}
    state = {'schema': SCHEMA, 'name': name.strip(), 'assay': assay.strip(), 'endpoint': endpoint,
             'unit': unit, 'direction': direction, 'created_at': stamp(), 'recipe': RECIPE, 'compounds': compounds, 'rounds': [], 'events': []}
    event(state, 'create', {'measured_sha256': mh, 'candidates_sha256': ph,
                            'initial_count': len(observations), 'candidate_count': len(pool),
                            'endpoint': endpoint, 'unit': unit, 'direction': direction,
                            'censoring': censored.summarize([compounds[r['compound_id']]
                                                             for r in observations])})
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


def greedy_propensity(ranked, locked, batch_size):
    """Probability that the greedy policy would select each eligible candidate.

    Written into the slate when the batch is decided, because it cannot be rebuilt
    later: a future analysis that asks "what would a different policy have found?"
    has to reweight each measured pick by how likely the policy in force was to pick
    it. Greedy selection with a fixed tie-break is deterministic, so every value is
    exactly 1.0 or 0.0. Locked compounds are 1.0 because the user forced them in.
    Excluded compounds never reach the slate; their propensity is 0.0 by construction.
    """
    chosen = set(locked) | set(ranked[:batch_size-len(locked)])
    return {cid: 1.0 if cid in chosen else 0.0 for cid in list(locked) + list(ranked)}


def propensity_summary(propensity, followed=True):
    """Round-level statement of what the stored propensities can and cannot support."""
    values = list(propensity.values())
    return {'of': 'the policy in force, computed when the batch was decided',
            'deterministic': all(value in (0.0, 1.0) for value in values),
            'nonzero': sum(value > 0 for value in values),
            'candidates': len(values),
            # False when a person replaced the policy's picks at commit time. The stored
            # propensities still describe the policy, but the batch was chosen by a person
            # whose probabilities nobody recorded.
            'batch_followed_policy': followed}


def shadow_seed(training_sha256, eligible_ids, round_number):
    """Seed for the shadow draw, fixed by what the round was decided from.

    It depends on the training snapshot, the eligible pool and the round number only,
    never on predictions, so the draw cannot lean toward compounds the model likes, and
    re-proposing the same round reproduces the same shadow batch.
    """
    basis = encoded({'training_sha256': training_sha256, 'eligible_ids': sorted(eligible_ids),
                     'round': round_number})
    return int(hashlib.sha256(basis.encode()).hexdigest()[:16], 16)


def shadow_batch(pool, locked, batch_size, seed):
    """A matched random batch: recorded with every committed batch, never assayed.

    Same size and same constraints as the real batch (locked compounds in, excluded
    ones out), with the free slots filled uniformly at random from the rest of the same
    eligible pool. The policy's own picks stay in the draw, so the two batches can
    overlap; leaving them out would make the shadow a sample of "what greedy rejected"
    rather than of a random policy. Every unlocked candidate has the same chance of
    being drawn, which is stored as the shadow policy's propensity.
    """
    locked_set = set(locked)
    free = sorted(cid for cid in pool if cid not in locked_set)
    slots = batch_size - len(locked)
    order = np.random.default_rng(seed).permutation(len(free))
    drawn = [free[i] for i in order[:slots]]
    return {'policy': 'random',
            'rule': 'same size and constraints as the batch; free slots drawn uniformly '
                    'at random from the same eligible pool',
            'ids': list(locked) + drawn, 'size': batch_size, 'locked': list(locked),
            'pool_size': len(pool), 'seed': seed,
            'seed_basis': 'sha256 of the training snapshot hash, the eligible ids and the round number',
            'propensity_unlocked': slots / len(free) if free else 0.0,
            'propensity_locked': 1.0,
            'assayed': False}


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
        relations = [censored.relation_of(compounds[cid]) for cid in observed]
        # Censored measurements enter the fit as bounds. With none present this is the
        # ordinary ridge fit on the measured values, so the picks of an all-exact
        # campaign are unchanged to the last digit.
        model, censoring = censored.fit(
            x, y, relations,
            lambda features, values: StableRidge('standard', 10).fit(features, values))
        # What the fit ended up treating each measurement as: the measurement itself when
        # it is exact, and the model's own prediction where a bound allows it. The
        # diagnostic range below is read off these rather than off the reported bounds.
        targets = censored.clip(model.predict(x), relations, y)
        snapshot = [{'compound_id': cid, **compounds[cid]} for cid in observed]
        training_sha256 = hashlib.sha256(encoded(snapshot).encode()).hexdigest()
        # A second model, fitted without the calibration half, supplies the interval.
        # Ranking still uses the full-data model above, so adding intervals changes no pick.
        # Censored rows are left out of calibration: the distance from a prediction to a
        # bound is not a prediction error, so it cannot calibrate an interval width.
        exact = censored.exact_rows(relations)
        calibration_model, uncertainty = conformal.calibrate(
            x[exact], y[exact], seed=conformal.seed_from(training_sha256),
            recipe={'mode': RECIPE['scaling'], 'alpha': RECIPE['alpha']})
        if censoring['censored']:
            uncertainty = {**uncertainty, 'censored_measurements_excluded': censoring['censored'],
                           'calibrated_on': 'the exact measurements only; a bound supplies no '
                                            'prediction error, so it calibrates nothing'}
        # Chunk scoring and nearest-neighbour evidence to bound similarity matrix size.
        predictions, centers, neighbours, similarities = [], [], [], []
        for start in range(0, len(pool), 256):
            chunk = pool[start:start+256]
            features = fingerprints([compounds[c]['smiles'] for c in chunk])
            predictions.extend(model.predict(features).tolist())
            if calibration_model is not None:
                centers.extend(calibration_model.predict(features).tolist())
            nearest, novelty = nearest_measured(features, x)
            neighbours.extend([observed[i] for i in nearest])
            similarities.extend((1-novelty).tolist())
        if not np.isfinite(predictions).all():
            raise ValueError('Nonfinite predictions; no batch was saved')
        by_id = {cid: i for i, cid in enumerate(pool)}
        sign = better(state)
        ranked = sorted((cid for cid in pool if cid not in locked),
                        key=lambda cid: (-sign * predictions[by_id[cid]], cid))
        margin = EXTRAPOLATION_MARGIN * float(np.std(targets)) if len(targets) > 1 else 0.0
        low, high = float(targets.min()) - margin, float(targets.max()) + margin
        selected = locked + ranked[:batch_size-len(locked)]
        propensity = greedy_propensity(ranked, locked, batch_size)
        # The full ranked slate records what was considered and rejected, not only the picks.
        # The slate keeps each candidate's interval centre, not the whole interval: the
        # half-width is one number for the round, and a person who overrides the picks at
        # commit time needs the centre of whatever they chose instead.
        slate = [{'rank': rank, 'compound_id': cid, 'prediction': predictions[by_id[cid]],
                  'selected': cid in selected, 'propensity': propensity[cid],
                  'interval_center': centers[by_id[cid]] if centers else None}
                 for rank, cid in enumerate(sorted(pool, key=lambda c: (-sign * predictions[by_id[c]], c)), 1)]
        rows = []
        for rank, cid in enumerate(selected, 1):
            i = by_id[cid]
            neighbour = neighbours[i]
            rows.append({'rank': rank, 'compound_id': cid, 'smiles': compounds[cid]['smiles'],
                         'prediction': predictions[i], 'selection_reason': 'user_locked' if cid in locked else 'best_prediction',
                         'nearest_measured_id': neighbour, 'nearest_measured_value': compounds[neighbour]['value'],
                         # How to read that neighbour's measurement: exact, or a bound.
                         'nearest_measured_relation': censored.relation_of(compounds[neighbour]),
                         'similarity': similarities[i],
                         'outside_diagnostic_range': not low <= predictions[i] <= high,
                         # None when the measured set was too small to calibrate an interval.
                         'interval': (conformal.interval(centers[i], uncertainty['half_width'])
                                      if centers else None)})
        if centers:
            # How far the interval's centre sits from the number that did the ranking.
            drift = [abs(centers[by_id[cid]] - predictions[by_id[cid]]) for cid in selected]
            uncertainty = {**uncertainty, 'centered_on': 'the calibration-split model, not the '
                                                         'full-data model used for ranking',
                           'mean_center_offset_from_ranking_prediction': float(np.mean(drift))}
        coef, intercept = model.linear_coefficients()
        number = len(state['rounds']) + 1
        shadow = shadow_batch(pool, locked, batch_size, shadow_seed(training_sha256, pool, number))
        round_record = {'round': number, 'created_at': stamp(), 'status': 'pending',
                        'training': snapshot, 'training_sha256': training_sha256,
                        'eligible_ids': pool, 'constraints': {cid: compounds[cid]['constraint'] for cid in pool},
                        'recommendations': rows, 'slate': slate, 'propensity': propensity_summary(propensity),
                        # The interval each pick carries, and what it rests on.
                        'uncertainty': uncertainty,
                        # Which measurements were bounds, and what the fit did with them.
                        'censoring': censoring,
                        # Recorded for later comparison only. Shadow compounds are never marked
                        # pending, exported or sent to the assay.
                        'shadow': shadow,
                        'results': {}, 'recipe': state['recipe'],
                        'policy': {'id': state['recipe']['policy'], 'rule': 'rank by predicted value in the declared direction',
                                   'locked': locked, 'excluded': sorted(cid for cid, c in compounds.items()
                                                                        if c['constraint'] == 'excluded')},
                        'declaration': declaration(state),
                        'diagnostic_range': {'low': low, 'high': high,
                                             'basis': 'range of what the fit treated the measurements '
                                                      'as, extended by one standard deviation'},
                        'model': {'coefficients': coef.tolist(), 'intercept': intercept},
                        'versions': {p: importlib.metadata.version(p) for p in ('rdkit', 'numpy', 'scikit-learn')},
                        'source_sha256': {p: hashlib.sha256(Path(__file__).with_name(p).read_bytes()).hexdigest()
                                          for p in ('campaign.py', 'data.py', 'heads.py', 'acquisition.py',
                                                    'conformal.py', 'censored.py')}}
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
            relation, value = measured_value(row['value']) if status == 'measured' else (None, None)
            result = {'status': status, 'value': value, 'relation': relation}
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
        event(state, 'import_results', {'round': round_number, 'sha256': sha, 'ids': sorted(new),
                                        'censoring': censored.summarize(
                                            [result for result in new.values()
                                             if result['status'] == 'measured'])})
        return {'added': len(new), 'round_status': record['status']}


def export_batch(path, round_number, destination, template=False):
    state = load(path)
    if not 1 <= round_number <= len(state['rounds']):
        raise ValueError('Unknown round')
    rows = state['rounds'][round_number-1]['recommendations']
    if template:
        rows = [{'compound_id': row['compound_id'], 'status': '', 'value': ''} for row in rows]
    else:
        rows = [{**row, **declaration(state), 'assay': state['assay']} for row in rows]
    # Machine-readable CSV preserves exact IDs for round trips.
    with Path(destination).open('x', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summary(path):
    state = load(path)
    counts = {status: sum(c['status'] == status for c in state['compounds'].values())
              for status in ('measured', 'available', 'pending', 'failed')}
    return {'name': state['name'], 'assay': state['assay'], **declaration(state),
            'counts': counts, 'rounds': [{'round': r['round'], 'status': r['status'],
                                         'training_count': len(r['training']), 'results': len(r['results'])}
                                        for r in state['rounds']],
            'constraints': {k: sum(c['constraint'] == k and c['status'] == 'available' for c in state['compounds'].values())
                            for k in ('locked', 'excluded')}, 'events': len(state['events'])}


def main():
    parser = argparse.ArgumentParser(
        description='Aster local campaign workflow: one assay, one declared endpoint, one number per compound')
    parser.add_argument('--db', required=True, type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('create')
    for key in ('name', 'assay', 'measured', 'candidates'):
        init.add_argument('--'+key, required=True)
    init.add_argument('--endpoint', required=True, help='Endpoint name, for example pKi, pIC50, percent_inhibition or clearance')
    init.add_argument('--unit', default='', help='Unit of the measured values, if the endpoint has one')
    init.add_argument('--direction', choices=list(DIRECTIONS), default='higher_is_better',
                      help='Whether larger or smaller measurements are better for this endpoint')
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
            create(args.db, args.measured, args.candidates, name=args.name, assay=args.assay,
                   endpoint=args.endpoint, unit=args.unit, direction=args.direction)
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
