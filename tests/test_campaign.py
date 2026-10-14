import csv
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from aster.campaign import (constrain, create, export_batch, import_results, load,
                            propose, summary)
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


@pytest.mark.parametrize('problem', ['overlap', 'invalid', 'mixture', 'nonfinite', 'censored', 'label_in_pool', 'small'])
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
        measured.write_text(measured.read_text().replace('5.0', 'nan' if problem == 'nonfinite' else '>5', 1))
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
