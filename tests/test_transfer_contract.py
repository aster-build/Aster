import copy
from itertools import product
import pytest
from aster.transfer import validate_evaluation_plan


def protocol():
    study = dict(rounds=5, batch_size=8, evaluation_protocols=['published','scaffold_transfer'],
                 evaluation_support_sizes=[32,64], evaluation_seeds=[0,1])
    freeze = {'new_targets':['A','B','C']}
    cases = [dict(task=t,protocol=p,support_size=n,seed=s,role='evaluation')
             for t,p,n,s in product(freeze['new_targets'],study['evaluation_protocols'],
                                    study['evaluation_support_sizes'],study['evaluation_seeds'])]
    plan = {'config':dict(rounds=5,batch_size=8,frozen_recipe_sha256='sealed'), 'cases':cases}
    return plan,freeze,study


def test_full_grid_matches_frozen_contract():
    plan,freeze,study=protocol()
    validate_evaluation_plan(plan,freeze,study,'sealed')


@pytest.mark.parametrize('change',['recipe','budget','missing','duplicate','task'])
def test_changed_experiment_is_rejected(change):
    plan,freeze,study=protocol()
    if change=='recipe': plan['config']['frozen_recipe_sha256']='other'
    if change=='budget': plan['config']['rounds']=4
    if change=='missing': plan['cases'].pop()
    if change=='duplicate': plan['cases'].append(copy.deepcopy(plan['cases'][0]))
    if change=='task': plan['cases'][0]['task']='previously_seen'
    with pytest.raises(ValueError):
        validate_evaluation_plan(plan,freeze,study,'sealed')
