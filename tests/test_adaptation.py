"""Optional neural integration check, using only synthetic small molecules."""
from pathlib import Path
import json
import numpy as np
import pytest
from aster.adaptation import AdaptedCheMeleon


def test_encoder_updates_deterministically_and_uses_observed_target_scale():
    pytest.importorskip('chemprop')
    checkpoint = Path('data/models/chemeleon_mp.pt')
    if not checkpoint.exists():
        pytest.skip('Local pinned checkpoint not downloaded')
    config = json.loads(Path('configs/stability-v1.json').read_text())
    expected = json.loads(Path('configs/broader-v2.json').read_text())['checkpoint_sha256']
    settings = dict(config['fine_tuning'], epochs=1, batch_size=3)
    recipe = {'mode':'filter', 'alpha':10, 'floor':.01}
    structures = np.array(['CCO','CCC','CCN','CCCO','CCCN','CCCC'])
    y = np.array([5.,6.,7.,5.5,6.5,7.5])
    a = AdaptedCheMeleon(recipe, settings, checkpoint, expected, 3).fit(structures, y)
    b = AdaptedCheMeleon(recipe, settings, checkpoint, expected, 3).fit(structures, y)
    assert a.diagnostics_['encoder_weight_l2_change'] > 0
    assert a.diagnostics_['n_observed'] == 6
    assert a.diagnostics_['target_mean'] == y.mean()
    np.testing.assert_allclose(a.predict(structures), b.predict(structures), atol=1e-6)
    before = a.predict(structures)
    a.predict(np.array(['c1ccccc1O']))
    np.testing.assert_array_equal(a.predict(structures), before)
