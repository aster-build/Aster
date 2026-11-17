import csv

import pytest

from aster.campaign import create, import_results, load, propose
from aster.decisions import record, review, why


def csv_file(path, fields, rows):
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture
def inputs(tmp_path):
    measured = csv_file(tmp_path/'measured.csv', ['compound_id', 'smiles', 'value'],
                        [{'compound_id': f'm{i:02}', 'smiles': 'C'*(i+1), 'value': 5+i/32}
                         for i in range(32)])
    candidates = csv_file(tmp_path/'candidates.csv', ['compound_id', 'smiles'],
                          [{'compound_id': f'c{i:02}', 'smiles': 'C'*(i+1)+'N'} for i in range(24)])
    return measured, candidates


def campaign_at(tmp_path, inputs, **declared):
    path = tmp_path/f"campaign-{declared.get('direction', 'higher_is_better')}.sqlite"
    create(path, *inputs, name='Test', assay='assay-1',
           **{'endpoint': 'pKi', 'unit': '', 'direction': 'higher_is_better', **declared})
    return path


def test_any_endpoint_name_and_direction_are_declared_and_stored(tmp_path, inputs):
    path = campaign_at(tmp_path, inputs, endpoint='percent_inhibition', unit='%',
                       direction='higher_is_better')
    state = load(path)
    assert (state['endpoint'], state['unit'], state['direction']) == ('percent_inhibition', '%',
                                                                      'higher_is_better')
    for bad in [{'endpoint': ''}, {'endpoint': 'x'*101}, {'endpoint': 'ok', 'direction': 'sideways'},
                {'endpoint': 'bad\nname'}]:
        with pytest.raises(ValueError):
            create(tmp_path/f'rejected-{len(str(bad))}.sqlite', *inputs, name='Test',
                   assay='assay-1', **{'direction': 'higher_is_better', **bad})


def test_direction_decides_which_candidates_are_proposed(tmp_path, inputs):
    higher = propose(campaign_at(tmp_path, inputs, direction='higher_is_better'))
    lower = propose(campaign_at(tmp_path, inputs, endpoint='clearance', unit='mL/min/kg',
                                direction='lower_is_better'))
    # Synthetic candidates tie on many predictions, so compare the ranked slates:
    # the declared direction decides which end of the ranking the batch comes from.
    up = [row['prediction'] for row in higher['slate']]
    down = [row['prediction'] for row in lower['slate']]
    assert up == sorted(up, reverse=True) and down == sorted(down)
    assert max(r['prediction'] for r in lower['recommendations']) \
        <= min(r['prediction'] for r in higher['recommendations'])
    assert all(r['selection_reason'] == 'best_prediction' for r in lower['recommendations'])


def test_legacy_campaigns_without_a_declaration_keep_working(tmp_path, inputs):
    path = campaign_at(tmp_path, inputs)
    from aster.campaign import declaration, transaction
    with transaction(path, True) as state:
        del state['unit'], state['direction']
    assert declaration(load(path)) == {'endpoint': 'pKi', 'unit': '',
                                       'direction': 'higher_is_better'}
    assert propose(path)['declaration']['direction'] == 'higher_is_better'


def test_the_slate_records_rejected_candidates_and_the_policy(tmp_path, inputs):
    round_record = propose(campaign_at(tmp_path, inputs))
    slate = round_record['slate']
    assert len(slate) == 24 and sum(row['selected'] for row in slate) == 8
    assert [row['rank'] for row in slate] == list(range(1, 25))
    assert round_record['policy']['id'] == 'greedy'
    assert round_record['policy']['locked'] == [] and round_record['policy']['excluded'] == []


def test_decision_answers_why_and_whether_the_pick_was_right(tmp_path, inputs):
    path = campaign_at(tmp_path, inputs)
    round_record = propose(path)
    picks = round_record['recommendations']
    outcomes = csv_file(tmp_path/'results.csv', ['compound_id', 'status', 'value'],
                        [{'compound_id': picks[0]['compound_id'], 'status': 'measured', 'value': '9.5'},
                         {'compound_id': picks[1]['compound_id'], 'status': 'measured', 'value': '4.0'},
                         {'compound_id': picks[2]['compound_id'], 'status': 'failed', 'value': ''}])
    import_results(path, 1, outcomes)

    answer = why(path, picks[0]['compound_id'])
    entry = answer['decisions'][0]
    assert answer['tested'] is True
    assert entry['why']['rank_in_batch'] == 1
    assert entry['why']['candidates_considered'] == 24
    assert entry['why']['nearest_measured_id'].startswith('m')
    assert entry['basis']['training_sha256'] == round_record['training_sha256']
    assert entry['outcome']['value'] == 9.5
    # 9.5 beats every value in the measured set, which tops out just under 6.
    assert entry['outcome']['improved_on_best_known'] is True
    assert entry['verdict'] == 'improved_on_what_was_known'
    assert 'predicted pKi' in answer['explanation'] and 'measured 9.50' in answer['explanation']

    weak = why(path, picks[1]['compound_id'])['decisions'][0]
    assert weak['outcome']['improved_on_best_known'] is False
    assert weak['verdict'] == 'did_not_improve_on_what_was_known'

    failed = why(path, picks[2]['compound_id'])['decisions'][0]
    assert failed['outcome'] == {'status': 'failed', 'value': None}
    assert failed['verdict'] == 'no_result'

    waiting = why(path, picks[3]['compound_id'])['decisions'][0]
    assert waiting['verdict'] == 'awaiting_result'
    assert 'has not been imported' in why(path, picks[3]['compound_id'])['explanation']


def test_lower_is_better_outcomes_are_judged_in_the_declared_direction(tmp_path, inputs):
    path = campaign_at(tmp_path, inputs, endpoint='clearance', unit='mL/min/kg',
                       direction='lower_is_better')
    picks = propose(path)['recommendations']
    import_results(path, 1, csv_file(tmp_path/'low.csv', ['compound_id', 'status', 'value'],
                                     [{'compound_id': picks[0]['compound_id'],
                                       'status': 'measured', 'value': '1.0'}]))
    entry = why(path, picks[0]['compound_id'])['decisions'][0]
    # A low clearance is a good result when smaller is better.
    assert entry['outcome']['improved_on_best_known'] is True
    assert 'better than predicted' in why(path, picks[0]['compound_id'])['explanation']
    assert review(path)['rounds'][0]['best_measured_this_round'] == 1.0


def test_compounds_without_a_decision_are_explained_not_invented(tmp_path, inputs):
    path = campaign_at(tmp_path, inputs)
    propose(path)
    never = why(path, 'c23')
    assert never['tested'] is False and 'never selected' in never['explanation']
    initial = why(path, 'm00')
    assert initial['tested'] is False and 'initial measured set' in initial['explanation']
    with pytest.raises(ValueError, match='Unknown compound'):
        why(path, 'does-not-exist')


def test_review_counts_only_measured_picks_and_states_its_limits(tmp_path, inputs):
    path = campaign_at(tmp_path, inputs)
    picks = propose(path)['recommendations']
    import_results(path, 1, csv_file(tmp_path/'partial.csv', ['compound_id', 'status', 'value'],
                                     [{'compound_id': picks[i]['compound_id'], 'status': 'measured',
                                       'value': f'{7.0 + i}'} for i in range(3)]))
    summary = review(path)
    assert summary['endpoint'] == 'pKi' and summary['direction'] == 'higher_is_better'
    first = summary['rounds'][0]
    assert (first['picks'], first['measured'], first['awaiting_result']) == (8, 3, 5)
    assert first['improved_on_best_known'] == 3
    assert summary['totals']['decisions'] == len(record(path)) == 8
    assert any('Rejected candidates were never measured' in line for line in summary['limitations'])


def test_decision_record_reports_the_model_as_it_was_not_as_it_is(tmp_path, inputs):
    path = campaign_at(tmp_path, inputs)
    first = propose(path)
    import_results(path, 1, csv_file(tmp_path/'r1.csv', ['compound_id', 'status', 'value'],
                                     [{'compound_id': r['compound_id'], 'status': 'measured',
                                       'value': '8.0'} for r in first['recommendations']]))
    second = propose(path)
    entries = record(path)
    rounds = {entry['round']: entry for entry in entries}
    assert rounds[1]['basis']['training_sha256'] == first['training_sha256']
    assert rounds[2]['basis']['training_sha256'] == second['training_sha256']
    assert rounds[1]['basis']['training_sha256'] != rounds[2]['basis']['training_sha256']
    assert rounds[1]['why']['measurements_known_then'] == 32
    assert rounds[2]['why']['measurements_known_then'] == 40


def test_each_decision_carries_the_propensity_stored_when_it_was_made(tmp_path, inputs):
    path = campaign_at(tmp_path, inputs)
    propose(path)
    assert all(entry['why']['selection_propensity'] == 1.0 for entry in record(path))
    off = review(path)['rounds'][0]['off_policy']
    assert off['propensity_logged'] and off['deterministic'] and off['batch_followed_policy']
    assert off['candidates_with_nonzero_propensity'] == 8 and off['candidates'] == 24
    # A greedy policy logs propensities but gives passed-over candidates no chance at all.
    assert off['usable_for_off_policy_evaluation'] is False
    assert 'probability zero' in off['reason']
    assert review(path)['totals']['rounds_usable_for_off_policy_evaluation'] == 0


def test_rounds_from_before_propensity_logging_are_not_back_filled(tmp_path, inputs):
    path = campaign_at(tmp_path, inputs)
    propose(path)
    from aster.campaign import transaction
    with transaction(path, True) as state:
        del state['rounds'][0]['propensity']
        for row in state['rounds'][0]['slate']:
            del row['propensity']
    assert all(entry['why']['selection_propensity'] is None for entry in record(path))
    off = review(path)['rounds'][0]['off_policy']
    assert off['propensity_logged'] is False and off['usable_for_off_policy_evaluation'] is False
    assert 'cannot be reconstructed' in off['reason']


def test_only_a_followed_non_certain_policy_supports_off_policy_evaluation():
    from aster.decisions import off_policy
    base = {'deterministic': False, 'batch_followed_policy': True, 'nonzero': 24, 'candidates': 24}
    assert off_policy({'propensity': base})['usable_for_off_policy_evaluation'] is True
    overridden = off_policy({'propensity': {**base, 'batch_followed_policy': False}})
    assert overridden['usable_for_off_policy_evaluation'] is False
    assert 'person replaced' in overridden['reason']


def measure_batch(path, tmp_path, round_record, value='7.0'):
    import_results(path, round_record['round'],
                   csv_file(tmp_path/f"results-{round_record['round']}.csv", ['compound_id', 'status', 'value'],
                            [{'compound_id': r['compound_id'], 'status': 'measured', 'value': value}
                             for r in round_record['recommendations']]))


def test_each_pick_says_whether_the_shadow_batch_also_drew_it(tmp_path, inputs):
    path = campaign_at(tmp_path, inputs)
    first = propose(path)
    shadow_ids = set(first['shadow']['ids'])
    for entry in record(path):
        assert entry['why']['also_in_shadow_batch'] == (entry['compound_id'] in shadow_ids)


def test_an_unmeasured_shadow_batch_is_reported_but_never_compared(tmp_path, inputs):
    path = campaign_at(tmp_path, inputs)
    first = propose(path)
    measure_batch(path, tmp_path, first)
    report = review(path)
    shadow = report['rounds'][0]['shadow']
    shared = len(set(first['shadow']['ids']) & {r['compound_id'] for r in first['recommendations']})
    assert shadow['logged'] and shadow['size'] == 8 and shadow['matches_committed_batch_size']
    assert shadow['assayed'] is False and shadow['shared_with_committed_batch'] == shared
    # Overlapping compounds were measured because the policy picked them, which is not random.
    assert shadow['shadow_members_measured'] == shared and shadow['comparison'] is None
    assert 'not against a random draw' in shadow['reason']
    assert report['totals']['rounds_with_shadow_batch'] == 1
    assert report['totals']['shadow_batches_comparable'] == 0
    assert 'never assayed' in report['rounds'][0]['off_policy']['reason']


@pytest.mark.parametrize('direction', ['higher_is_better', 'lower_is_better'])
def test_a_fully_measured_shadow_batch_is_compared_in_the_declared_direction(tmp_path, inputs, direction):
    from aster.campaign import transaction
    path = campaign_at(tmp_path, inputs, direction=direction)
    first = propose(path)
    measure_batch(path, tmp_path, first, value='7.0')
    # A retrospective replay knows every outcome; stand that in for the shadow compounds.
    with transaction(path, True) as state:
        for cid in first['shadow']['ids']:
            if state['compounds'][cid]['status'] != 'measured':
                state['compounds'][cid].update(status='measured', value=6.0)
    comparison = review(path)['rounds'][0]['shadow']['comparison']
    assert comparison['batch_best'] == 7.0 and comparison['batch_mean'] == 7.0
    shared = set(first['shadow']['ids']) & {r['compound_id'] for r in first['recommendations']}
    # Shared compounds carry the batch's 7.0; the rest of the shadow measured 6.0.
    if direction == 'higher_is_better':
        assert comparison['shadow_best'] == (7.0 if shared else 6.0)
        assert comparison['batch_better_on_best'] == (not shared)
    else:
        assert comparison['shadow_best'] == 6.0 and comparison['batch_better_on_best'] is False
    assert review(path)['totals']['shadow_batches_comparable'] == 1


def test_rounds_from_before_shadow_batches_are_not_back_filled(tmp_path, inputs):
    from aster.campaign import transaction
    path = campaign_at(tmp_path, inputs)
    propose(path)
    with transaction(path, True) as state:
        del state['rounds'][0]['shadow']
    assert all(entry['why']['also_in_shadow_batch'] is None for entry in record(path))
    shadow = review(path)['rounds'][0]['shadow']
    assert shadow['logged'] is False and shadow['comparison'] is None
    assert 'before shadow batches' in shadow['reason']


def test_each_decision_carries_its_interval_and_whether_the_result_landed_in_it(tmp_path, inputs):
    path = campaign_at(tmp_path, inputs)
    first = propose(path)
    picks = first['recommendations']
    half = first['uncertainty']['half_width']
    # One pick measured inside its interval, one far outside it.
    inside = picks[0]['interval']['center']
    outside = picks[1]['interval']['center'] + 10 * half + 1
    import_results(path, 1, csv_file(tmp_path/'r1.csv', ['compound_id', 'status', 'value'],
                                     [{'compound_id': picks[0]['compound_id'], 'status': 'measured',
                                       'value': str(inside)},
                                      {'compound_id': picks[1]['compound_id'], 'status': 'measured',
                                       'value': str(outside)}]))
    entries = {entry['compound_id']: entry for entry in record(path)}
    first_entry = entries[picks[0]['compound_id']]
    assert first_entry['why']['interval']['half_width'] == half
    assert first_entry['outcome']['inside_interval'] is True
    assert entries[picks[1]['compound_id']]['outcome']['inside_interval'] is False
    assert entries[picks[2]['compound_id']]['outcome']['status'] == 'awaiting_result'
    explanation = why(path, picks[0]['compound_id'])['explanation']
    assert 'nine times in ten' in explanation

    reported = review(path)
    round_one = reported['rounds'][0]['uncertainty']
    assert round_one['interval_logged'] and round_one['nominal_coverage'] == 0.9
    assert (round_one['picks_measured'], round_one['picks_inside_interval']) == (2, 1)
    assert round_one['observed_coverage_this_round'] == 0.5
    assert 'cannot measure a coverage rate' in round_one['reason']
    assert reported['totals']['interval_coverage'] == {'measurements': 2, 'covered': 1,
                                                       'observed_coverage': 0.5}
    assert any('nominal level' in line for line in reported['limitations'])


def test_a_round_decided_before_intervals_existed_reports_none(tmp_path, inputs):
    path = campaign_at(tmp_path, inputs)
    propose(path)
    state = load(path)
    for pick in state['rounds'][0]['recommendations']:
        pick.pop('interval')
    state['rounds'][0].pop('uncertainty')
    reported = review(state)['rounds'][0]['uncertainty']
    assert reported['interval_logged'] is False and reported['nominal_coverage'] is None
    assert 'did not have' in reported['reason']
    assert record(state)[0]['why']['interval'] is None
