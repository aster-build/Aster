"""The decision record, re-expressed in a published vocabulary.

Aster stores a campaign as one JSON document plus a short list of events (`create`,
`constraints`, `propose` or `commit`, `import_results`). That shape was invented here.
This module reads it back as an append-only event log in the record types of Yin, Du,
Prince and Cherukara, "Artifact-centered Claim-aware Observability for Autonomous
Scientific Agents" (Argonne, arXiv:2608.18312, 2026), Appendix A, Table A.1:

=================  ========================================================
record type        what it is in an Aster campaign
=================  ========================================================
run_and_stream     the campaign (one run) and who emits into it: the
                   selection code, the assay, and a person
individual         a compound, an input file, a training snapshot, a fitted
                   model, a batch, a shadow batch, or a claim about a pick
operator           an event that derives individuals from earlier ones:
                   import, snapshot, fit, select, shadow draw
fitness_record     an evaluator's output on one individual: a measurement
                   from the assay, or a prediction from one round's model
archive_event      a compound entering or leaving a curated set: measured,
                   locked, excluded
steering_command   a person's intervention: a lock, an exclusion, or
                   replacing the policy's picks before commit
evidence_binding   one piece of evidence cited by one claim
=================  ========================================================

Nothing is recomputed. Every value in the log is read from what the campaign stored
when it happened, the same rule the decision record follows. `check` tests the
paper's five invariants against the log and reports each one, including the one that
does not apply.

The paper is a proposed profile, not a standard with a schema or a validator, and it
gives field names only as a minimum ("Minimum fields" in Table A.1). Field names below
follow that table; anything Aster adds beyond it is named so in `ASTER_FIELDS`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from .campaign import declaration, load
from .decisions import record as decision_record

PROFILE = {'name': 'Artifact-centered claim-aware observability, minimal event contract',
           'citation': 'Yin, Du, Prince, Cherukara. Artifact-centered Claim-aware Observability '
                       'for Autonomous Scientific Agents. arXiv:2608.18312 (2026), Appendix A, '
                       'Table A.1.',
           'url': 'https://arxiv.org/abs/2608.18312'}
RECORD_TYPES = ('run_and_stream', 'individual', 'operator', 'fitness_record',
                'archive_event', 'steering_command', 'evidence_binding')
# Fields Aster writes that are not among Table A.1's minimum fields.
ASTER_FIELDS = ('seq', 'record_type', 'at', 'external', 'context_ids', 'steering_ids',
                'relation', 'unit', 'status', 'claim_text', 'note')
# Who emits into the run. Aster does not record which person acted, so the person
# stream says so rather than naming someone.
SELECTION = 'stream:aster-selection'
PERSON = 'stream:person'
UNRECORDED = 'not recorded by Aster'


def _sha(value):
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(text.encode()).hexdigest()


class _Log:
    def __init__(self, run_id):
        self.run_id, self.rows = run_id, []

    def add(self, record_type, ident, at, **fields):
        self.rows.append({'seq': len(self.rows) + 1, 'record_type': record_type, 'id': ident,
                          'at': at, **fields})
        return ident

    def individual(self, ident, kind, at, payload_hash, **extra):
        return self.add('individual', ident, at, run_id=self.run_id, kind=kind,
                        created_at=at, payload_hash=payload_hash, **extra)


def _assay_stream(state):
    return f"stream:assay:{state['assay']}"


def _round_events(state):
    """The campaign's own events, with the round each `propose`/`commit` produced."""
    rounds = {r['round']: r for r in state['rounds']}
    for entry in state['events']:
        number = entry['details'].get('round')
        yield entry, rounds.get(number)


def events(path_or_state):
    """The campaign as an append-only event log, oldest first.

    Every reference in a row points at a row earlier in the list, or at an individual
    marked `external` (an input file Aster did not produce). That ordering is what makes
    the log append-only: replaying a prefix of it never meets a dangling reference.
    """
    state = path_or_state if isinstance(path_or_state, dict) else load(path_or_state)
    run_id = 'run:' + _sha({'name': state['name'], 'created_at': state['created_at']})[:16]
    log = _Log(run_id)
    compounds = state['compounds']
    declared = declaration(state)
    unit = declared['unit']
    assay = _assay_stream(state)
    claims = {}
    for entry, round_record in _round_events(state):
        action, details, at = entry['action'], entry['details'], entry['at']
        if action == 'create':
            log.add('run_and_stream', run_id, at, run_id=run_id, stream_id=None,
                    invoker=UNRECORDED, parent_run=None,
                    note=f"campaign {state['name']!r}, assay {state['assay']!r}, endpoint "
                         f"{declared['endpoint']} ({declared['direction']})")
            for stream, what in ((SELECTION, 'the selection policy in aster/campaign.py'),
                                 (assay, f"the assay {state['assay']!r}, reporting measurements"),
                                 (PERSON, 'a person using the CLI or dashboard; who is not recorded')):
                log.add('run_and_stream', stream, at, run_id=run_id, stream_id=stream,
                        invoker=UNRECORDED, parent_run=None, note=what)
            files = {'file:measured': details['measured_sha256'],
                     'file:candidates': details['candidates_sha256']}
            for ident, sha in files.items():
                log.individual(ident, 'input_file', at, sha, external=True,
                               note='supplied to Aster, not produced by it')
            initial = sorted(cid for cid in compounds if _initially_measured(state, cid))
            molecules = sorted(compounds)
            for cid in molecules:
                log.individual(f'molecule:{cid}', 'molecule', at, _sha(compounds[cid]['identity']))
            log.add('operator', 'op:import', at, op_type='import', parent_ids=list(files),
                    child_ids=[f'molecule:{cid}' for cid in molecules], emitter_stream=SELECTION,
                    timestamp=at)
            for cid in initial:
                _measurement(log, state, cid, _initial_value(state, cid), at, assay,
                             evaluator_version=f"measured file sha256:{details['measured_sha256']}")
        elif action == 'constraints':
            mode = details['mode']
            command = log.add('steering_command', f"steer:{entry['sequence']}", at,
                              issuer=UNRECORDED, target=SELECTION,
                              instruction_type=f'constrain:{mode}',
                              effect_reference=None, member_ids=[f'molecule:{c}' for c in details['ids']],
                              note='effect_reference stays empty: the select operator it affected '
                                   'lists it under steering_ids, later in the log')
            for cid in details['ids']:
                for archive in ('locked', 'excluded'):
                    if archive == mode or _was_member(log, archive, cid):
                        log.add('archive_event', f"archive:{archive}:{entry['sequence']}:{cid}", at,
                                archive_id=f'archive:{archive}', member_id=f'molecule:{cid}',
                                action='add' if archive == mode else 'remove',
                                rule=command, timestamp=at)
        elif action in ('propose', 'commit') and round_record is not None:
            _round(log, state, round_record, at, unit)
        elif action == 'import_results' and round_record is not None:
            number = round_record['round']
            for cid in details['ids']:
                result = round_record['results'][cid]
                if result['status'] == 'measured':
                    _measurement(log, state, cid, result, at, assay,
                                 evaluator_version=f"results file sha256:{details['sha256']}")
                else:
                    log.add('fitness_record', f'fit:assay:{number}:{cid}', at,
                            individual=f'molecule:{cid}', evaluator=assay,
                            evaluator_version=f"results file sha256:{details['sha256']}",
                            value=None, verdict='failed', timestamp=at)
            claims.setdefault(number, set()).update(details['ids'])
            _claims(log, state, round_record, details['ids'], at)
    _open_claims(log, state, claims)
    return log.rows


def _initially_measured(state, cid):
    """Was this compound in the measured file at creation, rather than picked later?"""
    picked = {pick['compound_id'] for r in state['rounds'] for pick in r['recommendations']}
    return cid not in picked and state['compounds'][cid]['status'] == 'measured'


def _initial_value(state, cid):
    compound = state['compounds'][cid]
    return {'value': compound['value'], 'relation': compound.get('relation') or '='}


def _was_member(log, archive, cid):
    member, inside = f'molecule:{cid}', False
    for row in log.rows:
        if row['record_type'] == 'archive_event' and row['archive_id'] == f'archive:{archive}' \
                and row['member_id'] == member:
            inside = row['action'] == 'add'
    return inside


def _measurement(log, state, cid, result, at, assay, evaluator_version):
    declared = declaration(state)
    ident = log.add('fitness_record', f'fit:assay:{_measurement_count(log, cid)}:{cid}', at,
                    individual=f'molecule:{cid}', evaluator=assay,
                    evaluator_version=evaluator_version, value=result['value'],
                    relation=result.get('relation') or '=', unit=declared['unit'],
                    verdict='measured', timestamp=at)
    log.add('archive_event', f'archive:measured:{ident}', at, archive_id='archive:measured',
            member_id=f'molecule:{cid}', action='add', rule=ident, timestamp=at)
    return ident


def _measurement_count(log, cid):
    return sum(1 for row in log.rows if row['record_type'] == 'fitness_record'
               and row.get('individual') == f'molecule:{cid}' and row['evaluator'].startswith('stream:assay'))


def _round(log, state, record, at, unit):
    """One decided round: snapshot, fit, predictions, selection and shadow draw."""
    n = record['round']
    training = [row['compound_id'] for row in record['training']]
    snapshot = log.individual(f'snapshot:{n}', 'training_snapshot', at, record['training_sha256'])
    log.add('operator', f'op:snapshot:{n}', at, op_type='snapshot',
            parent_ids=[f'molecule:{c}' for c in training], child_ids=[snapshot],
            emitter_stream=SELECTION, timestamp=at)
    model = log.individual(f'model:{n}', 'model', at, _sha(record['model']),
                           note=f"{record['recipe']['model']}, fitted on {len(training)} measurements")
    log.add('operator', f'op:fit:{n}', at, op_type='fit', parent_ids=[snapshot], child_ids=[model],
            emitter_stream=SELECTION, timestamp=at)
    # The model's version is what it was fitted from plus the code that fitted it.
    version = 'training sha256:{} campaign.py sha256:{}'.format(
        record['training_sha256'], record.get('source_sha256', {}).get('campaign.py', 'not recorded'))
    rows = record.get('slate') or [{'compound_id': r['compound_id'], 'prediction': r['prediction']}
                                   for r in record['recommendations']]
    for row in rows:
        log.add('fitness_record', f"fit:model:{n}:{row['compound_id']}", at,
                individual=f"molecule:{row['compound_id']}", evaluator=model,
                evaluator_version=version, value=row['prediction'], unit=unit,
                verdict='predicted', timestamp=at)
    # A steering command takes effect at the first selection after it. The link is recorded
    # on that operator, under steering_ids, rather than by editing the earlier command, so
    # no row is ever changed once written and the log stays append-only.
    applied = {s for row in log.rows if row['record_type'] == 'operator'
               for s in row.get('steering_ids', [])}
    steering = [row['id'] for row in log.rows if row['record_type'] == 'steering_command'
                and row['id'] not in applied]
    picks = [r['compound_id'] for r in record['recommendations']]
    overridden = (record.get('propensity') or {}).get('batch_followed_policy') is False
    if overridden:
        steering.append(log.add('steering_command', f'steer:override:{n}', at, issuer=UNRECORDED,
                                target=SELECTION, instruction_type='replace_picks',
                                effect_reference=None, member_ids=[f'molecule:{c}' for c in picks],
                                note='a person replaced the policy picks before commit; the slate '
                                     'still records what the policy would have chosen'))
    batch = log.individual(f'batch:{n}', 'batch', at, _sha(picks))
    log.add('operator', f'op:select:{n}', at, op_type='select',
            parent_ids=[model] + [f'molecule:{c}' for c in picks], child_ids=[batch],
            context_ids=[f'molecule:{c}' for c in record.get('eligible_ids', [])],
            steering_ids=steering, emitter_stream=PERSON if overridden else SELECTION, timestamp=at,
            note=(record.get('policy') or {}).get('rule', record['recipe']['policy']))
    if 'shadow' in record:
        ids = record['shadow']['ids']
        shadow = log.individual(f'shadow:{n}', 'shadow_batch', at, _sha(ids),
                                note='drawn at random, recorded, never assayed')
        log.add('operator', f'op:shadow:{n}', at, op_type='shadow_draw',
                parent_ids=[f'molecule:{c}' for c in ids], child_ids=[shadow],
                context_ids=[snapshot], emitter_stream=SELECTION, timestamp=at,
                note=f"seed {record['shadow']['seed']}, from {record['shadow']['seed_basis']}")


def _claim_text(entry):
    return {'improved_on_what_was_known': 'beat the best measurement known when it was picked',
            'did_not_improve_on_what_was_known': 'did not beat the best measurement known when it was picked',
            'undetermined': 'bounds do not settle whether it beat the best measurement known',
            'no_result': 'the assay failed, so nothing can be claimed',
            'awaiting_result': 'no result yet'}[entry['verdict']]


def _claims(log, state, record, ids, at):
    """A verdict about a pick is a claim, and it cites the records it rests on."""
    n = record['round']
    entries = {e['compound_id']: e for e in decision_record(state) if e['round'] == n}
    for cid in sorted(ids):
        entry = entries.get(cid)
        if entry is None:
            continue
        measured = entry['verdict'] in ('improved_on_what_was_known', 'did_not_improve_on_what_was_known')
        claim = log.individual(f'claim:{n}:{cid}', 'claim', at, _sha(entry['verdict']),
                               claim_text=f"{cid} {_claim_text(entry)}",
                               status='supported' if measured else 'unsupported')
        if not measured:
            continue
        outcome = next(row['id'] for row in reversed(log.rows)
                       if row['record_type'] == 'fitness_record' and row.get('individual') == f'molecule:{cid}'
                       and row['evaluator'].startswith('stream:assay'))
        for evidence, locator, value, role in (
                (outcome, 'value', entry['outcome']['value'], 'outcome'),
                (f'fit:model:{n}:{cid}', 'value', entry['why']['prediction'], 'prediction'),
                (f'snapshot:{n}', 'best measurement in the training snapshot',
                 entry['why']['best_value_known_then'], 'baseline')):
            # The outcome keeps its relation: "> 9" is cited as a bound, never as 9.
            extra = {'relation': entry['outcome']['relation']} if role == 'outcome' else {}
            log.add('evidence_binding', f'bind:{claim}:{role}', at, claim_id=claim,
                    evidence_id=evidence, locator=locator, extracted_value=value,
                    binding_role=role, **extra)


def _open_claims(log, state, claimed):
    """Picks with no result yet still get a claim, marked unsupported, so none is silent."""
    for record in state['rounds']:
        missing = [p['compound_id'] for p in record['recommendations']
                   if p['compound_id'] not in claimed.get(record['round'], set())]
        if missing:
            last = log.rows[-1]['at']
            for cid in missing:
                log.individual(f"claim:{record['round']}:{cid}", 'claim', last, _sha('awaiting_result'),
                               claim_text=f'{cid} has no result yet', status='unsupported')


# --- the five invariants -------------------------------------------------------------

def _references(row):
    """Every id a row points at that must already exist, by Table A.1's fields."""
    kind = row['record_type']
    if kind == 'operator':
        return list(row['parent_ids']) + list(row['child_ids']) + list(row.get('context_ids', [])) \
            + list(row.get('steering_ids', []))
    if kind == 'fitness_record':
        return [row['individual'], row['evaluator']]
    if kind == 'archive_event':
        return [row['member_id'], row['rule']]
    if kind == 'evidence_binding':
        return [row['claim_id'], row['evidence_id']]
    if kind == 'steering_command':
        return [row['target']] if row['target'].startswith('stream:') else []
    return []


def check(rows):
    """Test the profile's five invariants (Appendix A) against an event log.

    Returns one entry per invariant with `holds` true, false, or None when it does not
    apply, and the offending ids when it fails.
    """
    seen, problems = {}, {i: [] for i in range(1, 6)}
    individuals = {}
    for row in rows:
        if row['record_type'] not in RECORD_TYPES:
            problems[1].append(f"{row['id']}: unknown record type {row['record_type']}")
        for ref in _references(row):
            if ref not in seen:
                problems[1].append(f"{row['id']} -> {ref}")
        seen.setdefault(row['id'], row)
        if row['record_type'] == 'individual':
            individuals[row['id']] = row
    # 2. Derivation edges are acyclic by artifact version.
    edges = {}
    for row in rows:
        if row['record_type'] == 'operator':
            for child in row['child_ids']:
                edges.setdefault(child, set()).update(row['parent_ids'])
    state = {}

    def visit(node, path):
        if state.get(node) == 'done':
            return
        if state.get(node) == 'open':
            problems[2].append(' -> '.join(path + [node]))
            return
        state[node] = 'open'
        for parent in edges.get(node, ()):
            visit(parent, path + [node])
        state[node] = 'done'
    for node in list(edges):
        visit(node, [])
    # 3. Every claim has an evidence binding, a failed verification, or an explicit status.
    bound = {row['claim_id'] for row in rows if row['record_type'] == 'evidence_binding'}
    claims = [i for i in individuals.values() if i['kind'] == 'claim']
    for claim in claims:
        if claim['id'] not in bound and claim.get('status') != 'unsupported':
            problems[3].append(claim['id'])
    # 4. Evaluator outputs name the evaluator version and the individual they judged.
    for row in rows:
        if row['record_type'] == 'fitness_record' and not (
                row.get('evaluator_version') and row.get('individual') in individuals):
            problems[4].append(row['id'])
    statements = {
        1: 'every reference resolves to an earlier event object or is marked as an external import',
        2: 'derivation edges are acyclic by artifact version',
        3: 'every final scientific claim has an evidence binding, a failed verification record, '
           'or an explicit unsupported status',
        4: 'evaluator outputs name the evaluator version and the individual they judged',
        5: 'redaction removes payload access but not the fact that an event existed'}
    report = []
    for number, statement in statements.items():
        if number == 5:
            report.append({'invariant': number, 'statement': statement, 'holds': None,
                           'reason': 'Aster has no redaction; nothing is ever removed from a campaign, '
                                     'so there is nothing for this invariant to test'})
            continue
        report.append({'invariant': number, 'statement': statement,
                       'holds': not problems[number], 'violations': problems[number][:20],
                       'violation_count': len(problems[number])})
    externals = [i['id'] for i in individuals.values() if i.get('external')]
    return {'profile': PROFILE, 'events': len(rows),
            'by_type': {t: sum(r['record_type'] == t for r in rows) for t in RECORD_TYPES},
            'external_imports': externals, 'claims': len(claims),
            'claims_supported': sum(c['id'] in bound for c in claims),
            'invariants': report}


def main():
    parser = argparse.ArgumentParser(description='Aster campaign as an append-only event log in '
                                                 'the Argonne record types (arXiv:2608.18312)')
    parser.add_argument('--db', required=True, type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('events', help='print the event log, one JSON object per line')
    commands.add_parser('check', help='test the five invariants against the log')
    crate = commands.add_parser('crate', help='write the campaign as an RO-Crate directory')
    crate.add_argument('directory', type=Path)
    crate.add_argument('--license', help='licence URL for the crate, e.g. '
                                         'https://creativecommons.org/licenses/by/4.0/')
    args = parser.parse_args()
    try:
        if args.command == 'events':
            for row in events(args.db):
                print(json.dumps(row, allow_nan=False))
        elif args.command == 'check':
            print(json.dumps(check(events(args.db)), indent=2, allow_nan=False))
        else:
            from .rocrate import write
            print(json.dumps(write(args.db, args.directory, license=args.license), indent=2,
                             allow_nan=False))
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f'Aster event log: {error}\n')


if __name__ == '__main__':
    main()
