import numpy as np
import pytest
from aster.acquisition import tanimoto, nearest_measured, select_batch
from aster.reliability import simulate
from aster.experiment import LabelOracle


def settings():
    return dict(rounds=1,batch_size=2,ridge_alpha=10,forest_trees=5,bootstrap_members=3,
                cv_folds=3,nominal_interval_coverage=.8,prediction_guard=[0,14])


def policy(name='greedy',u=0,d=0):
    return dict(id=name,uncertainty_weight=u,diversity_weight=d)


def test_tanimoto_counts_do_not_overflow_and_zero_vectors_match():
    x=np.ones((2,2048),dtype=np.uint8)
    x[1,:1024]=0
    np.testing.assert_allclose(tanimoto(x,x),[[1,.5],[.5,1]])
    np.testing.assert_array_equal(tanimoto(np.zeros((1,4)),np.zeros((1,4))),[[1]])


def test_greedy_stable_ties_and_diversity_penalty_are_recorded():
    ids=np.array([8,4,2])
    x=np.array([[1,0],[1,0],[0,1]])
    mean=np.array([9.,9.,8.8])
    picks,_=select_batch(ids,mean,np.zeros(3),x,2,policy(),np.random.default_rng(0))
    assert picks.tolist()==[4,8]
    picks,reasons=select_batch(ids,mean,np.zeros(3),x,2,policy('diverse',d=.5),np.random.default_rng(0))
    assert picks.tolist()==[4,2]
    assert reasons[0]['diversity_penalty']==0


def test_uncertainty_bonus_and_penalty_move_in_opposite_directions():
    args=(np.arange(3),np.array([8.,7.8,7.]),np.array([0.,1.,0.]),np.eye(3),1)
    explore,_=select_batch(*args,policy('explore',u=.5),np.random.default_rng(0))
    cautious,_=select_batch(*args,policy('cautious',u=-1),np.random.default_rng(0))
    assert explore.tolist()==[1] and cautious.tolist()==[0]


def test_novelty_uses_measured_reference_only():
    nearest,novelty=nearest_measured(np.array([[1,0],[0,1]]),np.array([[1,0]]))
    np.testing.assert_array_equal(nearest,[0,0])
    np.testing.assert_array_equal(novelty,[0,1])


def test_hidden_labels_and_audit_structures_cannot_change_first_batch():
    rng=np.random.default_rng(10)
    x=rng.integers(0,2,(30,24),dtype=np.uint8)
    y=rng.normal(7,1,30)
    changed=y.copy();changed[9:]=rng.normal(1000,50,21)
    cfg=settings()
    a=simulate(x,x[:4],LabelOracle(y),np.arange(9),cfg,0,policy('explore_diverse',u=.5,d=.5))
    b=simulate(x,1-x[:4],LabelOracle(changed),np.arange(9),cfg,0,policy('explore_diverse',u=.5,d=.5))
    assert [s['index'] for s in a['selections']]==[s['index'] for s in b['selections']]
    assert a['predictions'][0]['half_width']==b['predictions'][0]['half_width']
    np.testing.assert_allclose([s['score'] for s in a['selections']],[s['score'] for s in b['selections']])
    assert a['predictions'][-1]['training_size']==11
    assert len(set(s['index'] for s in a['selections']))==2


def test_random_batch_independent_of_predictions_and_nan_rejected():
    ids=np.arange(10);x=np.eye(10)
    a,_=select_batch(ids,np.arange(10),np.zeros(10),x,3,policy('random'),np.random.default_rng(8))
    b,_=select_batch(ids,-np.arange(10),np.ones(10),x,3,policy('random'),np.random.default_rng(8))
    np.testing.assert_array_equal(a,b)
    with pytest.raises(ValueError,match='Invalid prediction'):
        select_batch(ids,np.full(10,np.nan),np.zeros(10),x,3,policy(),np.random.default_rng(8))
