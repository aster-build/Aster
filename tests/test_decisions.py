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
