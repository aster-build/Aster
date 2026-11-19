import csv
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from aster.campaign import (constrain, create, export_batch, greedy_propensity, import_results,
                            load, propose, shadow_batch, shadow_seed, summary)
from aster.conformal import seed_from
from aster.data import fingerprints


def csv_file(path, fields, rows):
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture
def inputs(tmp_path):
    # Distinct valid structures; synthetic outcomes test plumbing, not model quality.
    measured = csv_file(tmp_path/'measured.csv', ['compound_id', 'smiles', 'value'],
                        [{'compound_id': f'm{i:02}', 'smiles': 'C'*(i+1), 'value': 5+i/32} for i in range(32)])
    candidates = csv_file(tmp_path/'candidates.csv', ['compound_id', 'smiles'],
                          [{'compound_id': f'c{i:02}', 'smiles': 'C'*(i+1)+'N'} for i in range(24)])
    return measured, candidates


@pytest.fixture
def campaign(tmp_path, inputs):
    path = tmp_path/'campaign.sqlite'
    create(path, *inputs, name='Test', assay='assay-1', endpoint='pKi')
    return path


def results_csv(tmp_path, recommendations, name='results.csv', value='7.5'):
    return csv_file(tmp_path/name, ['compound_id', 'status', 'value'],
                    [{'compound_id': r['compound_id'], 'status': 'measured', 'value': value} for r in recommendations])


def test_two_rounds_persist_export_and_restore_model(campaign, tmp_path):
    first = propose(campaign)
    exported = tmp_path/'batch.csv'
    export_batch(campaign, 1, exported)
    assert len(list(csv.DictReader(exported.open()))) == 8
    template = tmp_path/'template.csv'
    export_batch(campaign, 1, template, template=True)
    assert all(r['value'] == '' for r in csv.DictReader(template.open()))
    import_results(campaign, 1, results_csv(tmp_path, first['recommendations']))
    second = propose(campaign)
    first_ids = {r['compound_id'] for r in first['recommendations']}
    assert not first_ids & {r['compound_id'] for r in second['recommendations']}
    assert len(second['training']) == 40
    assert first_ids <= {r['compound_id'] for r in second['training']}
    assert load(campaign)['rounds'][0]['recommendations'] == first['recommendations']
    features = fingerprints([r['smiles'] for r in first['recommendations']])
    restored = features @ np.asarray(first['model']['coefficients']) + first['model']['intercept']
    np.testing.assert_allclose(restored, [r['prediction'] for r in first['recommendations']], atol=1e-8)
    observed = {r['compound_id'] for r in first['training']}
    assert all(r['nearest_measured_id'] in observed for r in first['recommendations'])
    import_results(campaign, 2, results_csv(tmp_path, second['recommendations'], 'second.csv'))
    assert summary(campaign)['counts']['measured'] == 48


def test_constraints_are_atomic_and_respected(campaign):
    constrain(campaign, ['c00'], 'locked')
    constrain(campaign, ['c01', 'c02'], 'excluded')
    before = load(campaign)
    with pytest.raises(ValueError):
        constrain(campaign, ['c03', 'missing'], 'excluded')
    assert load(campaign) == before
    first = propose(campaign)
    assert first['recommendations'][0]['compound_id'] == 'c00'
    assert first['recommendations'][0]['selection_reason'] == 'user_locked'
    assert not {'c01', 'c02'} & {r['compound_id'] for r in first['recommendations']}
    with pytest.raises(ValueError):
        constrain(campaign, ['c00'], 'available')


def test_partial_results_retry_conflict_and_failure(campaign, tmp_path):
    first = propose(campaign)
    partial = results_csv(tmp_path, first['recommendations'][:2])
    assert import_results(campaign, 1, partial)['added'] == 2
    before = load(campaign)
    assert import_results(campaign, 1, partial)['added'] == 0
    assert load(campaign) == before
    with pytest.raises(ValueError):
        propose(campaign)
    bad = results_csv(tmp_path, first['recommendations'][:3], 'bad.csv', '8')
    with pytest.raises(ValueError):
        import_results(campaign, 1, bad)
    assert load(campaign) == before  # No partial writes on conflict.
    remaining = csv_file(tmp_path/'failed.csv', ['compound_id', 'status', 'value'],
                         [{'compound_id': r['compound_id'], 'status': 'failed', 'value': ''}
                          for r in first['recommendations'][2:]])
    assert import_results(campaign, 1, remaining)['round_status'] == 'complete'
    second = propose(campaign)
    assert len(second['training']) == 34
    assert summary(campaign)['counts']['failed'] == 6


def test_concurrent_proposals_only_one_commits(campaign):
    def attempt():
        try:
            return propose(campaign)['round']
        except ValueError:
            return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: attempt(), range(2)))
    assert sorted(outcomes, key=str) == [1, 'blocked']
    assert len(load(campaign)['rounds']) == 1


def test_no_overwrite_and_bad_budget(campaign, inputs, tmp_path):
    before = load(campaign)
    with pytest.raises(FileExistsError):
        create(campaign, *inputs, name='Overwrite', assay='other', endpoint='pKi')
    for size in (0, 25, -1):
        with pytest.raises(ValueError):
            propose(campaign, size)
    assert load(campaign) == before
    constrain(campaign, ['c00', 'c01'], 'locked')
    with pytest.raises(ValueError):
        propose(campaign, 1)
    propose(campaign)
    out = tmp_path/'batch.csv'
    export_batch(campaign, 1, out)
    original = out.read_bytes()
    with pytest.raises(FileExistsError):
        export_batch(campaign, 1, out)
    assert out.read_bytes() == original


@pytest.mark.parametrize('problem', ['overlap', 'invalid', 'mixture', 'nonfinite', 'unreadable', 'label_in_pool', 'small'])
def test_rejects_invalid_input_before_creating_database(tmp_path, inputs, problem):
    measured, candidates = inputs
    if problem == 'label_in_pool':
        candidates.write_text('compound_id,smiles,value\nx,CN,9\n')
    elif problem in ('overlap', 'invalid', 'mixture'):
        structure = {'overlap': 'C', 'invalid': 'invalid', 'mixture': 'CC.O'}[problem]
        candidates.write_text(f'compound_id,smiles\nx,{structure}\n')
    elif problem == 'small':
        measured.write_text('compound_id,smiles,value\nx,C,5\n')
    else:
        measured.write_text(measured.read_text().replace(
            '5.0', 'nan' if problem == 'nonfinite' else '~5', 1))
    db = tmp_path/'rejected.sqlite'
    with pytest.raises(ValueError):
        create(db, measured, candidates, name='Test', assay='single', endpoint='pKi')
    assert not db.exists()


def test_wrong_round_and_unselected_results_rejected(campaign, tmp_path):
    propose(campaign)
    before = load(campaign)
    bad = csv_file(tmp_path/'wrong.csv', ['compound_id', 'status', 'value'],
                   [{'compound_id': 'm00', 'status': 'measured', 'value': '8'}])
    for number in (0, 1, 2):
        with pytest.raises(ValueError):
            import_results(campaign, number, bad)
    assert load(campaign) == before


def test_candidate_order_does_not_change_selection(campaign, inputs, tmp_path):
    measured, candidates = inputs
    with candidates.open() as handle:
        rows = list(csv.DictReader(handle))
    csv_file(candidates, ['compound_id', 'smiles'], list(reversed(rows)))
    other = tmp_path/'other.sqlite'
    create(other, measured, candidates, name='Other', assay='single', endpoint='pKi')
    assert propose(campaign)['recommendations'] == propose(other)['recommendations']


def test_failed_model_fit_rolls_back_and_can_retry(campaign, monkeypatch):
    from aster.heads import StableRidge
    original = StableRidge.fit
    before = load(campaign)
    def failed_fit(*args, **kwargs):
        raise RuntimeError('Simulated worker failure')
    monkeypatch.setattr(StableRidge, 'fit', failed_fit)
    with pytest.raises(RuntimeError):
        propose(campaign)
    assert load(campaign) == before
    monkeypatch.setattr(StableRidge, 'fit', original)
    assert propose(campaign)['round'] == 1


def test_greedy_propensity_is_certain_for_picks_and_zero_for_the_rest():
    propensity = greedy_propensity(['a', 'b', 'c', 'd'], ['z'], 3)
    assert propensity == {'z': 1.0, 'a': 1.0, 'b': 1.0, 'c': 0.0, 'd': 0.0}
    assert greedy_propensity(['a', 'b'], ['y', 'z'], 2) == {'y': 1.0, 'z': 1.0, 'a': 0.0, 'b': 0.0}


def test_every_slate_row_stores_its_selection_propensity_at_decision_time(campaign):
    constrain(campaign, ['c05'], 'locked')
    constrain(campaign, ['c01'], 'excluded')
    first = propose(campaign)
    slate = first['slate']
    assert all(row['propensity'] == (1.0 if row['selected'] else 0.0) for row in slate)
    assert next(row for row in slate if row['compound_id'] == 'c05')['propensity'] == 1.0
    # Excluded compounds are never eligible, so they are absent rather than stored as zero.
    assert 'c01' not in {row['compound_id'] for row in slate}
    assert sum(row['propensity'] for row in slate) == 8
    assert first['propensity'] == {'of': 'the policy in force, computed when the batch was decided',
                                   'deterministic': True, 'nonzero': 8, 'candidates': 23,
                                   'batch_followed_policy': True}
    # Stored, not recomputed: the value read back later is the one written now.
    assert load(campaign)['rounds'][0]['slate'] == slate


def test_shadow_batch_matches_size_and_constraints_and_draws_uniformly():
    pool = [f'c{i:02}' for i in range(20)]
    shadow = shadow_batch(pool, ['c03'], 5, seed=7)
    assert len(shadow['ids']) == 5 == len(set(shadow['ids'])) == shadow['size']
    assert shadow['ids'][0] == 'c03' and set(shadow['ids']) <= set(pool)
    assert shadow['propensity_unlocked'] == 4 / 19 and shadow['propensity_locked'] == 1.0
    assert shadow['assayed'] is False and shadow['policy'] == 'random'
    assert shadow_batch(pool, ['c03'], 5, seed=7) == shadow
    # Uniform: over many seeds every unlocked candidate is drawn about equally often.
    counts = {cid: 0 for cid in pool if cid != 'c03'}
    for seed in range(4000):
        for cid in shadow_batch(pool, ['c03'], 5, seed)['ids'][1:]:
            counts[cid] += 1
    expected = 4000 * 4 / 19
    assert all(abs(count - expected) < 0.12 * expected for count in counts.values())


def test_shadow_seed_ignores_pool_order_and_changes_with_round():
    assert shadow_seed('abc', ['b', 'a'], 1) == shadow_seed('abc', ['a', 'b'], 1)
    assert shadow_seed('abc', ['a', 'b'], 1) != shadow_seed('abc', ['a', 'b'], 2)
    assert shadow_seed('abc', ['a', 'b'], 1) != shadow_seed('abd', ['a', 'b'], 1)


def test_every_round_records_a_shadow_batch_that_is_never_sent_to_the_assay(campaign, tmp_path):
    constrain(campaign, ['c05'], 'locked')
    constrain(campaign, ['c01'], 'excluded')
    first = propose(campaign)
    shadow = first['shadow']
    assert len(shadow['ids']) == len(first['recommendations']) == 8
    assert 'c05' in shadow['ids'] and 'c01' not in shadow['ids']
    assert set(shadow['ids']) <= set(first['eligible_ids'])
    assert shadow['pool_size'] == 23 and shadow['propensity_unlocked'] == 7 / 22
    assert shadow['seed'] == shadow_seed(first['training_sha256'], first['eligible_ids'], 1)
    state = load(campaign)
    picked = {r['compound_id'] for r in first['recommendations']}
    for cid in set(shadow['ids']) - picked:
        assert state['compounds'][cid]['status'] == 'available'
    exported = tmp_path/'batch.csv'
    export_batch(campaign, 1, exported)
    assert {r['compound_id'] for r in csv.DictReader(exported.open())} == picked
    assert state['rounds'][0]['shadow'] == shadow


def test_shadow_does_not_depend_on_candidate_file_order(campaign, inputs, tmp_path):
    rows = list(csv.DictReader(inputs[1].open()))[::-1]
    reordered = csv_file(tmp_path/'reordered.csv', ['compound_id', 'smiles'], rows)
    other = tmp_path/'other.sqlite'
    create(other, inputs[0], reordered, name='Test', assay='assay-1', endpoint='pKi')
    assert propose(campaign)['shadow']['ids'] == propose(other)['shadow']['ids']


def test_every_pick_carries_a_conformal_interval_that_the_round_explains(campaign):
    first = propose(campaign)
    uncertainty = first['uncertainty']
    assert uncertainty['method'] == 'split conformal on absolute residuals'
    assert uncertainty['nominal_coverage'] == 0.9
    assert uncertainty['fit_size'] + uncertainty['calibration_size'] == len(first['training']) == 32
    assert uncertainty['half_width'] > 0
    assert 'exchangeable' in uncertainty['assumption']
    assert uncertainty['seed'] == seed_from(first['training_sha256'])
    for row in first['recommendations']:
        entry = row['interval']
        assert entry['high'] - entry['low'] == pytest.approx(2 * uncertainty['half_width'])
        assert entry['low'] < entry['center'] < entry['high']
    assert load(campaign)['rounds'][0]['uncertainty'] == uncertainty


def test_intervals_do_not_change_which_compounds_are_picked(campaign, inputs, tmp_path, monkeypatch):
    with_intervals = propose(campaign)
    other = tmp_path/'nointervals.sqlite'
    create(other, *inputs, name='Test', assay='assay-1', endpoint='pKi')
    # Stand in for a measured set too small to calibrate: no interval, same decisions.
    monkeypatch.setattr('aster.conformal.calibrate', lambda *a, **k: (None, {'half_width': None}))
    without = propose(other)
    assert ([(r['compound_id'], r['prediction']) for r in without['recommendations']]
            == [(r['compound_id'], r['prediction']) for r in with_intervals['recommendations']])
    assert all(row['interval'] is None for row in without['recommendations'])
    assert without['uncertainty']['half_width'] is None


def censored_inputs(tmp_path, bound='> 5.3', count=4):
    """The same inputs as `inputs`, with the strongest measurements reported as bounds.

    An assay that saturates censors its best compounds: it can say the value is past the
    top of the tested range, not where past it. So the bound sits below where the model
    places those compounds, which is the case a fit has to handle.
    """
    measured = csv_file(tmp_path/'measured-censored.csv', ['compound_id', 'smiles', 'value'],
                        [{'compound_id': f'm{i:02}', 'smiles': 'C'*(i+1),
                          'value': bound if i >= 32-count else 5+i/32} for i in range(32)])
    candidates = csv_file(tmp_path/'candidates-censored.csv', ['compound_id', 'smiles'],
                          [{'compound_id': f'c{i:02}', 'smiles': 'C'*(i+1)+'N'} for i in range(24)])
    return measured, candidates


def test_create_stores_a_censored_measurement_as_a_bound(tmp_path):
    path = tmp_path/'censored.sqlite'
    create(path, *censored_inputs(tmp_path), name='Test', assay='assay-1', endpoint='pIC50', unit='uM')
    state = load(path)
    assert state['compounds']['m31'] == {**state['compounds']['m31'], 'value': 5.3, 'relation': '>'}
    assert state['compounds']['m00']['relation'] == '='
    # A candidate has no measurement, so it has no relation either.
    assert state['compounds']['c00']['relation'] is None
    assert state['events'][0]['details']['censoring'] == {
        'measurements': 32, 'exact': 28, 'upper_bounded': 0, 'lower_bounded': 4, 'censored': 4}


def test_results_may_be_censored_and_are_counted_as_such(tmp_path, campaign):
    first = propose(campaign)
    picks = first['recommendations']
    rows = [{'compound_id': r['compound_id'], 'status': 'measured',
             'value': '< 4.5' if index < 2 else '7.5'} for index, r in enumerate(picks)]
    import_results(campaign, 1, csv_file(tmp_path/'censored-results.csv',
                                         ['compound_id', 'status', 'value'], rows))
    state = load(campaign)
    stored = state['rounds'][0]['results'][picks[0]['compound_id']]
    assert stored == {'status': 'measured', 'value': 4.5, 'relation': '<'}
    assert state['compounds'][picks[0]['compound_id']]['relation'] == '<'
    imported = [e for e in state['events'] if e['action'] == 'import_results'][-1]
    assert imported['details']['censoring'] == {'measurements': 8, 'exact': 6, 'upper_bounded': 2,
                                                'lower_bounded': 0, 'censored': 2}


def test_a_failed_assay_still_cannot_carry_a_bound(tmp_path, campaign):
    first = propose(campaign)
    rows = [{'compound_id': r['compound_id'], 'status': 'failed', 'value': '> 10'}
            for r in first['recommendations']]
    with pytest.raises(ValueError):
        import_results(campaign, 1, csv_file(tmp_path/'bad.csv',
                                             ['compound_id', 'status', 'value'], rows))


def test_a_censored_campaign_records_the_fit_and_calibrates_on_exact_rows_only(tmp_path):
    path = tmp_path/'censored-propose.sqlite'
    create(path, *censored_inputs(tmp_path), name='Test', assay='assay-1', endpoint='pIC50')
    record = propose(path)
    assert record['censoring']['censored'] == 4 and record['censoring']['lower_bounded'] == 4
    assert record['censoring']['converged'] and record['censoring']['iterations'] > 1
    # The bounds moved off themselves, which is the whole point of fitting them as bounds.
    assert record['censoring']['largest_target_shift_from_bound'] > 0
    # 28 exact measurements, half of them held back, so the interval rests on 14 and says so.
    assert record['uncertainty']['calibration_size'] == 14
    assert record['uncertainty']['censored_measurements_excluded'] == 4
    assert record['censoring']['policy'] in record['censoring']['policy']
    assert 'censored.py' in record['source_sha256']


def test_fitting_a_bound_as_a_bound_ranks_differently_from_writing_it_down_as_a_value(tmp_path):
    bounded, candidates = censored_inputs(tmp_path)
    # The same file with the bounds replaced by the bare number: this is what bound
    # substitution does, and it is the practice this change exists to avoid.
    substituted = csv_file(tmp_path/'substituted.csv', ['compound_id', 'smiles', 'value'],
                           [{**row, 'value': row['value'].replace('> ', '')}
                            for row in csv.DictReader(bounded.open())])
    aware = propose(create(tmp_path/'aware.sqlite', bounded, candidates,
                           name='Aware', assay='a', endpoint='pIC50') and tmp_path/'aware.sqlite')
    naive = propose(create(tmp_path/'naive.sqlite', substituted, candidates,
                           name='Naive', assay='a', endpoint='pIC50') and tmp_path/'naive.sqlite')
    assert naive['censoring']['censored'] == 0
    aware_predictions = [row['prediction'] for row in aware['recommendations']]
    naive_predictions = [row['prediction'] for row in naive['recommendations']]
    assert aware_predictions != naive_predictions


def test_a_pick_carries_how_to_read_its_nearest_measured_neighbour(tmp_path):
    path = tmp_path/'neighbour.sqlite'
    create(path, *censored_inputs(tmp_path, count=32), name='Test', assay='a', endpoint='pIC50')
    record = propose(path)
    # Every measurement is a bound here, so every neighbour must be reported as one.
    assert {row['nearest_measured_relation'] for row in record['recommendations']} == {'>'}
    assert record['uncertainty']['half_width'] is None
    assert record['recommendations'][0]['interval'] is None


def test_campaign_and_round_record_how_structures_were_read(tmp_path):
    import json
    import sqlite3

    from aster import standardisation
    measured = tmp_path/'m.csv'
    measured.write_text('compound_id,smiles,value\n' + ''.join(f'm{i},{"C"*(i+1)},{5+i/32}\n' for i in range(32)))
    candidates = tmp_path/'c.csv'
    candidates.write_text('compound_id,smiles\n' + ''.join(f'c{i},{"C"*(i+1)}N\n' for i in range(12)))
    path = tmp_path/'campaign.sqlite'
    state = create(path, measured, candidates, name='Test', assay='a', endpoint='pKi')
    assert state['standardisation'] == standardisation.current()
    assert state['events'][0]['details']['standardisation'] == standardisation.summary(state['standardisation'])
    batch = propose(path)
    reading = batch['standardisation']
    assert reading['convention'] == standardisation.CONVENTION_ID
    assert reading['campaign_created_under'] == standardisation.summary(state['standardisation'])
    assert reading['matches_campaign']['verdict'] == 'same'
    assert 'standardisation.py' in batch['source_sha256']

    # A campaign created before conventions were logged still proposes, and its round
    # says the comparison is unknown rather than pretending it matched.
    connection = sqlite3.connect(path)
    with connection:
        stored = json.loads(connection.execute('SELECT payload FROM campaign').fetchone()[0])
        del stored['standardisation']
        stored['rounds'] = []
        for compound in stored['compounds'].values():
            if compound['status'] == 'pending':
                compound['status'] = 'available'
        connection.execute('UPDATE campaign SET payload=?', (json.dumps(stored),))
    connection.close()
    older = propose(path)
    assert older['standardisation']['campaign_created_under'] is None
    assert older['standardisation']['matches_campaign']['verdict'] == 'unknown'
