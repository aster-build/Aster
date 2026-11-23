import csv

import pytest

from aster.campaign import constrain, create, import_results, load, propose
from aster.event_log import RECORD_TYPES, check, events


def csv_file(path, fields, rows):
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture
def campaign(tmp_path):
    measured = csv_file(tmp_path/'measured.csv', ['compound_id', 'smiles', 'value'],
                        [{'compound_id': f'm{i:02}', 'smiles': 'C'*(i+1), 'value': 5+i/32}
                         for i in range(32)])
    candidates = csv_file(tmp_path/'candidates.csv', ['compound_id', 'smiles'],
                          [{'compound_id': f'c{i:02}', 'smiles': 'C'*(i+1)+'N'} for i in range(24)])
    path = tmp_path/'campaign.sqlite'
    create(path, measured, candidates, name='Test', assay='assay-1', endpoint='pKi')
    return path


def decided(tmp_path, path, values):
    """Propose one round of four and report results for some of it."""
    picks = [row['compound_id'] for row in propose(path, 4)['recommendations']]
    rows = [{'compound_id': cid, 'status': 'failed' if value is None else 'measured',
             'value': '' if value is None else value}
            for cid, value in zip(picks, values)]
    import_results(path, len(load(path)['rounds']), csv_file(tmp_path/f'r{len(rows)}.csv',
                                                            ['compound_id', 'status', 'value'], rows))
    return picks


def by_id(rows):
    return {row['id']: row for row in rows}


def test_a_new_campaign_is_a_run_with_streams_imports_and_measurements(campaign):
    rows = events(campaign)
    assert {row['record_type'] for row in rows} <= set(RECORD_TYPES)
    assert [row['seq'] for row in rows] == list(range(1, len(rows) + 1))
    index = by_id(rows)
    assert index['file:measured']['external'] and index['file:candidates']['external']
    assert index['op:import']['parent_ids'] == ['file:measured', 'file:candidates']
    assert len(index['op:import']['child_ids']) == 56
    measurements = [r for r in rows if r['record_type'] == 'fitness_record']
    assert len(measurements) == 32
    assert all(r['evaluator'] == 'stream:assay:assay-1' for r in measurements)
    assert all(r['evaluator_version'].startswith('measured file sha256:') for r in measurements)
    assert sum(r['record_type'] == 'archive_event' and r['archive_id'] == 'archive:measured'
               for r in rows) == 32


def test_a_round_becomes_snapshot_fit_select_and_shadow_operators(tmp_path, campaign):
    picks = decided(tmp_path, campaign, ['7.5', None, '> 9'])
    index = by_id(events(campaign))
    state = load(campaign)
    record = state['rounds'][0]
    assert index['snapshot:1']['payload_hash'] == record['training_sha256']
    assert index['op:fit:1']['parent_ids'] == ['snapshot:1']
    select = index['op:select:1']
    assert select['parent_ids'] == ['model:1'] + [f'molecule:{c}' for c in picks]
    # The pool the policy chose from is context, not derivation.
    assert len(select['context_ids']) == len(record['eligible_ids'])
    assert index['op:shadow:1']['parent_ids'] == [f'molecule:{c}' for c in record['shadow']['ids']]
    # Every slate row is the model's judgement of one compound, versioned by its training.
    predictions = [r for r in index.values() if r['record_type'] == 'fitness_record'
                   and r['evaluator'] == 'model:1']
    assert len(predictions) == len(record['slate'])
    assert all(record['training_sha256'] in r['evaluator_version'] for r in predictions)


def test_results_become_claims_bound_to_their_evidence(tmp_path, campaign):
    measured, failed, bounded, waiting = decided(tmp_path, campaign, ['7.5', None, '> 9'])
    index = by_id(events(campaign))
    assert index[f'claim:1:{measured}']['status'] == 'supported'
    roles = {r['binding_role']: r for r in index.values()
             if r['record_type'] == 'evidence_binding' and r['claim_id'] == f'claim:1:{measured}'}
    assert set(roles) == {'outcome', 'prediction', 'baseline'}
    assert roles['outcome']['extracted_value'] == 7.5
    assert roles['prediction']['evidence_id'] == f'fit:model:1:{measured}'
    # A bound is cited as a bound, never as the number at its edge.
    bound = index[f'bind:claim:1:{bounded}:outcome']
    assert (bound['relation'], bound['extracted_value']) == ('>', 9.0)
    # A failed assay and a pick with no result are explicit, not missing.
    assert index[f'claim:1:{failed}']['status'] == 'unsupported'
    assert index[f'fit:assay:1:{failed}']['verdict'] == 'failed'
    assert index[f'claim:1:{waiting}']['status'] == 'unsupported'
    assert not any(r.get('claim_id') == f'claim:1:{waiting}' for r in index.values())


def test_constraints_are_steering_commands_linked_from_the_next_selection(tmp_path, campaign):
    constrain(campaign, ['c03'], 'locked')
    constrain(campaign, ['c05'], 'excluded')
    decided(tmp_path, campaign, ['6'])
    constrain(campaign, ['c05'], 'available')
    rows = events(campaign)
    index = by_id(rows)
    commands = [r for r in rows if r['record_type'] == 'steering_command']
    assert [c['instruction_type'] for c in commands] == ['constrain:locked', 'constrain:excluded',
                                                         'constrain:available']
    assert index['op:select:1']['steering_ids'] == [commands[0]['id'], commands[1]['id']]
    archive = [(r['archive_id'], r['action']) for r in rows if r['record_type'] == 'archive_event'
               and r['member_id'] == 'molecule:c05']
    assert archive == [('archive:excluded', 'add'), ('archive:excluded', 'remove')]


def test_a_dashboard_override_is_recorded_as_a_steering_command(tmp_path, campaign):
    propose(campaign, 4)
    state = load(campaign)
    state['rounds'][0]['propensity']['batch_followed_policy'] = False
    index = by_id(events(state))
    assert index['steer:override:1']['instruction_type'] == 'replace_picks'
    assert 'steer:override:1' in index['op:select:1']['steering_ids']
    assert index['op:select:1']['emitter_stream'] == 'stream:person'


def test_the_log_is_append_only_and_satisfies_the_invariants(tmp_path, campaign):
    constrain(campaign, ['c03'], 'locked')
    decided(tmp_path, campaign, ['7.5', None, '> 9', '4'])
    decided(tmp_path, campaign, ['6.1'])
    rows = events(campaign)
    report = check(rows)
    assert [i['holds'] for i in report['invariants']] == [True, True, True, True, None]
    assert report['claims'] == 8 and report['claims_supported'] == 4
    # Every prefix of the log is itself a valid log: nothing points forward.
    for cut in (40, 100, len(rows) // 2):
        assert all(i['holds'] is not False for i in check(rows[:cut])['invariants'])


def test_the_checker_catches_each_kind_of_violation(tmp_path, campaign):
    decided(tmp_path, campaign, ['7.5', '6'])
    rows = events(campaign)

    def holds(mutated):
        return [i['holds'] for i in check(mutated)['invariants']][:4]

    dangling = [dict(r) for r in rows]
    next(r for r in dangling if r['id'] == 'op:fit:1')['parent_ids'] = ['snapshot:99']
    assert holds(dangling)[0] is False
    cyclic = [dict(r) for r in rows] + [{'seq': 0, 'record_type': 'operator', 'id': 'op:loop',
                                          'at': '', 'op_type': 'fit', 'parent_ids': ['model:1'],
                                          'child_ids': ['snapshot:1'], 'emitter_stream': 'x',
                                          'timestamp': ''}]
    assert holds(cyclic)[1] is False
    unbound = [r for r in rows if r['record_type'] != 'evidence_binding']
    assert holds(unbound)[2] is False
    unversioned = [dict(r) for r in rows]
    next(r for r in unversioned if r['record_type'] == 'fitness_record')['evaluator_version'] = ''
    assert holds(unversioned)[3] is False


def test_a_campaign_from_before_slates_and_shadows_still_reads(tmp_path, campaign):
    propose(campaign, 4)
    state = load(campaign)
    for key in ('slate', 'shadow', 'propensity', 'source_sha256'):
        state['rounds'][0].pop(key)
    rows = events(state)
    index = by_id(rows)
    assert 'shadow:1' not in index
    assert sum(r['record_type'] == 'fitness_record' and r['evaluator'] == 'model:1' for r in rows) == 4
    assert 'not recorded' in index['fit:model:1:' + state['rounds'][0]['recommendations'][0]['compound_id']]['evaluator_version']
    assert all(i['holds'] is not False for i in check(rows)['invariants'])
