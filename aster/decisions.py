"""The decision record: why a compound was tested, and whether the pick was right.

Everything here is derived from what a campaign already stored at the time of each
decision. Nothing is recomputed from current code or current data, so a record read
six months later describes the decision as it was made, not as it would be made now.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np

from .campaign import declaration, load

PENDING = 'awaiting_result'


def _numbers(record):
    """Measurements known to the model when this round was proposed."""
    return np.asarray([row['value'] for row in record['training']], dtype=float)


def _best_known(record, sign):
    values = _numbers(record)
    return float(values.max()) if sign > 0 else float(values.min())


def decision(state, record, pick):
    """One pick, joined to its model, its evidence basis and its outcome."""
    sign = 1.0 if declaration(state)['direction'] == 'higher_is_better' else -1.0
    result = record['results'].get(pick['compound_id'])
    known = _best_known(record, sign)
    slate = record.get('slate') or []
    entry = {
        'compound_id': pick['compound_id'],
        'round': record['round'],
        'decided_at': record['created_at'],
        'endpoint': declaration(state),
        'assay': state['assay'],
        'why': {
            'rank_in_batch': pick['rank'],
            'selection_reason': pick['selection_reason'],
            'policy': record.get('policy', {'id': record['recipe']['policy']}),
            'prediction': pick['prediction'],
            'candidates_considered': len(record.get('eligible_ids') or slate),
            'rank_in_slate': next((row['rank'] for row in slate
                                   if row['compound_id'] == pick['compound_id']), None),
            # None means the round predates propensity logging; it is never back-filled.
            'selection_propensity': next((row.get('propensity') for row in slate
                                          if row['compound_id'] == pick['compound_id']), None),
            # None means the round predates shadow batches; never back-filled.
            'also_in_shadow_batch': (pick['compound_id'] in record['shadow']['ids']
                                     if 'shadow' in record else None),
            'nearest_measured_id': pick['nearest_measured_id'],
            'nearest_measured_value': pick['nearest_measured_value'],
            'similarity_to_nearest_measured': pick['similarity'],
            'outside_diagnostic_range': pick['outside_diagnostic_range'],
            'best_value_known_then': known,
            'measurements_known_then': len(record['training']),
        },
        'basis': {
            'training_sha256': record['training_sha256'],
            'recipe': record['recipe'],
            'model_intercept': record['model']['intercept'],
            'library_versions': record.get('versions', {}),
            'module_sha256': record.get('source_sha256', {}),
            'diagnostic_range': record.get('diagnostic_range'),
        },
    }
    if result is None:
        entry['outcome'] = {'status': PENDING}
        entry['verdict'] = PENDING
        return entry
    if result['status'] == 'failed':
        entry['outcome'] = {'status': 'failed', 'value': None}
        entry['verdict'] = 'no_result'
        return entry
    observed = float(result['value'])
    entry['outcome'] = {'status': 'measured', 'value': observed,
                        'prediction_error': observed - pick['prediction'],
                        'absolute_error': abs(observed - pick['prediction']),
                        'improved_on_best_known': bool(sign * (observed - known) > 0)}
    entry['verdict'] = ('improved_on_what_was_known' if entry['outcome']['improved_on_best_known']
                        else 'did_not_improve_on_what_was_known')
    return entry


def off_policy(round_record):
    """Can this round support asking what a different selection policy would have found?

    That analysis reweights each measured pick by one over the probability that the
    policy in force would have picked it. It needs three things: the probability was
    stored at decision time, the batch actually followed the policy, and the policy gave
    passed-over candidates some chance. A greedy policy gives them none.
    """
    logged = round_record.get('propensity')
    if logged is None:
        return {'propensity_logged': False, 'deterministic': None, 'batch_followed_policy': None,
                'usable_for_off_policy_evaluation': False,
                'reason': 'This round was decided before selection propensities were recorded. '
                          'They cannot be reconstructed afterwards, so none are reported.'}
    entry = {'propensity_logged': True, 'deterministic': logged['deterministic'],
             'batch_followed_policy': logged['batch_followed_policy'],
             'candidates_with_nonzero_propensity': logged['nonzero'],
             'candidates': logged['candidates']}
    if not logged['batch_followed_policy']:
        reason = ('A person replaced the policy\'s picks when committing this batch. The stored '
                  'propensities describe the policy, not the person, so they cannot reweight '
                  'what was measured.')
    elif logged['deterministic']:
        reason = ('The policy picked with certainty: every passed-over candidate had probability '
                  'zero, so no reweighting can say how a different policy would have scored. '
                  'That needs some randomness in what gets measured. A matched random shadow '
                  'batch is recorded with rounds that have one, but it is never assayed, so it '
                  'does not change this.')
    else:
        reason = 'Propensities were logged, the batch followed the policy, and it was not certain.'
    usable = logged['batch_followed_policy'] and not logged['deterministic']
    return {**entry, 'usable_for_off_policy_evaluation': usable, 'reason': reason}


def shadow(state, round_record):
    """What the round's matched random batch can report, judged from what is known now.

    The shadow batch is never assayed. A shadow compound can still end up measured,
    because the policy picked it in this round or a later one, but those measurements
    are not a random sample: they exist because the policy wanted them. So a comparison
    with the real batch is reported only when every shadow compound has a measurement.
    """
    logged = round_record.get('shadow')
    if logged is None:
        return {'logged': False, 'comparison': None,
                'reason': 'This round was decided before shadow batches were recorded. A random '
                          'draw made now would not be the one that was available then, so none '
                          'is reported.'}
    sign = 1.0 if declaration(state)['direction'] == 'higher_is_better' else -1.0
    batch = [row['compound_id'] for row in round_record['recommendations']]
    shared = sorted(set(logged['ids']) & set(batch))
    known = {cid: state['compounds'][cid]['value'] for cid in logged['ids']
             if state['compounds'][cid]['status'] == 'measured'}
    entry = {'logged': True, 'policy': logged['policy'], 'size': len(logged['ids']),
             'matches_committed_batch_size': len(logged['ids']) == len(batch),
             'shared_with_committed_batch': len(shared),
             'shared_locked': len(set(shared) & set(logged['locked'])),
             'chance_of_each_unlocked_candidate': logged['propensity_unlocked'],
             'assayed': logged['assayed'], 'shadow_members_measured': len(known)}
    batch_values = [round_record['results'][cid]['value'] for cid in batch
                    if round_record['results'].get(cid, {}).get('status') == 'measured']
    if len(known) < len(logged['ids']) or len(batch_values) < len(batch):
        missing = len(logged['ids']) - len(known)
        return {**entry, 'comparison': None,
                'reason': f'{missing} of {len(logged["ids"])} shadow compounds have no measurement'
                          + ('' if len(batch_values) == len(batch)
                             else ', and the committed batch is not fully measured')
                          + '. Comparing a partial shadow batch would compare against the '
                            'compounds the policy chose to measure, not against a random draw.'}
    best = max if sign > 0 else min
    shadow_values = list(known.values())
    return {**entry, 'comparison': {
                'batch_best': best(batch_values), 'shadow_best': best(shadow_values),
                'batch_mean': float(np.mean(batch_values)), 'shadow_mean': float(np.mean(shadow_values)),
                'batch_better_on_best': bool(sign * (best(batch_values) - best(shadow_values)) > 0),
                'note': 'One round, one random draw. A single comparison is an anecdote; '
                        'only many rounds together say whether the policy beats random.'},
            'reason': 'Every shadow compound has a measurement, so the two batches can be compared.'}


def record(path_or_state):
    """Every decision this campaign has made, oldest first."""
    state = path_or_state if isinstance(path_or_state, dict) else load(path_or_state)
    return [decision(state, round_record, pick)
            for round_record in state['rounds']
            for pick in round_record['recommendations']]


def why(path_or_state, compound_id):
    """Answer 'why did we test this, and were we right?' for one compound."""
    state = path_or_state if isinstance(path_or_state, dict) else load(path_or_state)
    history = [entry for entry in record(state) if entry['compound_id'] == compound_id]
    if not history:
        compound = state['compounds'].get(compound_id)
        if compound is None:
            raise ValueError(f'Unknown compound: {compound_id}')
        return {'compound_id': compound_id, 'tested': False,
                'status': compound['status'], 'constraint': compound['constraint'],
                'value': compound['value'],
                'explanation': 'This compound was never selected for a batch.'
                               if compound['status'] == 'available'
                               else 'This compound was part of the initial measured set, '
                                    'so no selection decision was made about it.'}
    return {'compound_id': compound_id, 'tested': True, 'decisions': history,
            'explanation': sentence(state, history[-1])}


def sentence(state, entry):
    """One plain sentence a reader can check against the stored numbers."""
    endpoint = entry['endpoint']
    unit = f" {endpoint['unit']}" if endpoint['unit'] else ''
    reason = ('you locked it into the batch' if entry['why']['selection_reason'] == 'user_locked'
              else 'it had one of the best predictions')
    why_text = (f"Round {entry['round']}: picked at rank {entry['why']['rank_in_batch']} of the batch "
                f"because {reason}, out of "
                f"{entry['why']['candidates_considered']} eligible candidates, with a predicted "
                f"{endpoint['endpoint']} of {entry['why']['prediction']:.2f}{unit}. Its nearest measured "
                f"analog then was {entry['why']['nearest_measured_id']} at "
                f"{entry['why']['nearest_measured_value']:.2f}{unit} "
                f"(Tanimoto similarity {entry['why']['similarity_to_nearest_measured']:.2f}), and the best "
                f"measurement known at the time was {entry['why']['best_value_known_then']:.2f}{unit}.")
    outcome = entry['outcome']
    if outcome['status'] == 'measured':
        sign = 1.0 if endpoint['direction'] == 'higher_is_better' else -1.0
        direction = 'better' if sign * outcome['prediction_error'] > 0 else 'worse'
        return (why_text + f" It measured {outcome['value']:.2f}{unit}, "
                f"{abs(outcome['prediction_error']):.2f} {direction} than predicted, which "
                + ('beat' if outcome['improved_on_best_known'] else 'did not beat')
                + ' the best measurement known when it was chosen.')
    if outcome['status'] == 'failed':
        return why_text + ' The assay failed, so there is no result to judge the pick against.'
    return why_text + ' The result has not been imported yet.'


def review(path_or_state):
    """Were the picks right? Measured picks only, with no inference about rejected ones."""
    state = path_or_state if isinstance(path_or_state, dict) else load(path_or_state)
    sign = 1.0 if declaration(state)['direction'] == 'higher_is_better' else -1.0
    entries = record(state)
    rounds = []
    for round_record in state['rounds']:
        picks = [entry for entry in entries if entry['round'] == round_record['round']]
        measured = [entry for entry in picks if entry['outcome']['status'] == 'measured']
        errors = np.asarray([entry['outcome']['absolute_error'] for entry in measured])
        signed = np.asarray([entry['outcome']['prediction_error'] for entry in measured])
        improved = [entry for entry in measured if entry['outcome']['improved_on_best_known']]
        predicted = [entry['why']['prediction'] for entry in measured]
        observed = [entry['outcome']['value'] for entry in measured]
        rounds.append({
            'round': round_record['round'],
            'status': round_record['status'],
            'picks': len(picks), 'measured': len(measured),
            'failed': sum(entry['outcome']['status'] == 'failed' for entry in picks),
            'awaiting_result': sum(entry['verdict'] == PENDING for entry in picks),
            'improved_on_best_known': len(improved),
            'mean_absolute_error': float(errors.mean()) if len(errors) else None,
            'mean_signed_error': float(signed.mean()) if len(signed) else None,
            'within_batch_rank_agreement': agreement(predicted, observed),
            'best_measured_this_round': (max(observed) if sign > 0 else min(observed)) if observed else None,
            'best_value_known_before': picks[0]['why']['best_value_known_then'] if picks else None,
            'off_policy': off_policy(round_record),
            'shadow': shadow(state, round_record),
        })
    measured = [entry for entry in entries if entry['outcome']['status'] == 'measured']
    errors = np.asarray([entry['outcome']['absolute_error'] for entry in measured])
    return {
        'campaign': state['name'], 'assay': state['assay'], **declaration(state),
        'rounds': rounds,
        'totals': {'decisions': len(entries), 'measured': len(measured),
                   'improved_on_best_known': sum(entry['outcome']['improved_on_best_known']
                                                 for entry in measured),
                   'mean_absolute_error': float(errors.mean()) if len(errors) else None,
                   'awaiting_result': sum(entry['verdict'] == PENDING for entry in entries),
                   'rounds_usable_for_off_policy_evaluation': sum(
                       round_entry['off_policy']['usable_for_off_policy_evaluation']
                       for round_entry in rounds),
                   'rounds_with_shadow_batch': sum(round_entry['shadow']['logged'] for round_entry in rounds),
                   'shadow_batches_comparable': sum(round_entry['shadow']['comparison'] is not None
                                                    for round_entry in rounds)},
        'limitations': [
            'Only picks have outcomes. Rejected candidates were never measured, so this cannot '
            'say whether a different batch would have been better.',
            'Prediction error is measured against the model as it stood in that round, not '
            'against the current model.',
            'Improvement is relative to the best measurement known when the pick was made, '
            'which is a campaign milestone, not a biological claim.',
            'Selection propensities are stored per candidate, but under the greedy policy they '
            'are all 1 or 0, so they show which candidates the policy ruled out completely; '
            'they do not by themselves allow an estimate of what another policy would have found.',
            'Each round records a matched random shadow batch, but it is never assayed. It can be '
            'compared with the real batch only once every shadow compound has a measurement, '
            'which in a live campaign normally means never; in a retrospective replay with known '
            'outcomes it means every round.',
        ],
    }


def agreement(predicted, observed):
    """Spearman agreement inside one batch, reported only when it is defined."""
    if len(predicted) < 3 or len(set(predicted)) < 2 or len(set(observed)) < 2:
        return None
    from scipy.stats import spearmanr
    return float(spearmanr(predicted, observed).statistic)


def main():
    parser = argparse.ArgumentParser(description='Aster decision record: why a compound was '
                                                 'tested, and whether the pick was right')
    parser.add_argument('--db', required=True, type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    question = commands.add_parser('why', help='explain one compound')
    question.add_argument('compound_id')
    commands.add_parser('record', help='every decision this campaign has made')
    commands.add_parser('review', help='how the picks actually turned out')
    args = parser.parse_args()
    try:
        if args.command == 'why':
            output = why(args.db, args.compound_id)
        elif args.command == 'record':
            output = record(args.db)
        else:
            output = review(args.db)
        print(json.dumps(output, indent=2, allow_nan=False))
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f'Aster decisions: {error}\n')


if __name__ == '__main__':
    main()
