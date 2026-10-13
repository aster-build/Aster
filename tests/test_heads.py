import numpy as np
import pytest
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from aster.heads import StableRidge


def test_standard_control_matches_original_pipeline():
    rng = np.random.default_rng(7)
    x = rng.normal(size=(20, 40)).astype(np.float32)
    y = rng.normal(size=20)
    q = rng.normal(size=(8, 40)).astype(np.float32)
    original = make_pipeline(StandardScaler(), Ridge(alpha=10)).fit(x, y)
    np.testing.assert_allclose(StableRidge('standard', 10).fit(x, y).predict(q), original.predict(q), rtol=1e-6, atol=1e-6)


@pytest.mark.parametrize('mode', ['center', 'floor', 'filter', 'standard'])
def test_linear_initialization_matches_head_and_never_refits_at_prediction(mode):
    rng = np.random.default_rng(12)
    x = rng.normal(size=(32, 10)).astype(np.float32)
    x[:, 0] *= 1e-6
    y = rng.normal(size=32)
    model = StableRidge(mode, 10, .01).fit(x, y)
    q = x[:3].copy()
    q[:, 0] = 100
    coef, bias = model.linear_coefficients()
    before = model.scaler_.mean_.copy()
    np.testing.assert_allclose(model.predict(q), q @ coef + bias, rtol=2e-5, atol=2e-5)
    np.testing.assert_array_equal(before, model.scaler_.mean_)
    if mode == 'filter':
        assert not model.mask_[0]
        np.testing.assert_allclose(model.predict(q), model.predict(x[:3]))


def test_all_filtered_falls_back_to_observed_mean():
    model = StableRidge('filter', 10, .01).fit(np.zeros((5, 3)), np.arange(5))
    np.testing.assert_array_equal(model.predict(np.ones((3, 3))*1e9), [2, 2, 2])
