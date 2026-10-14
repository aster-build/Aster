"""Observed-only models and label-free batch policies for reliability experiments."""
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import KFold
from .heads import StableRidge


def tanimoto(x, y):
    # uint8 dot products overflow above 255 shared bits: compute in float32.
    a, b = np.asarray(x, dtype=np.float32), np.asarray(y, dtype=np.float32)
    intersection = a @ b.T
    union = a.sum(axis=1)[:, None] + b.sum(axis=1)[None, :] - intersection
    return np.divide(intersection, union, out=np.ones_like(intersection), where=union > 0)


def nearest_measured(query, observed):
    similarities = tanimoto(query, observed)
    index = similarities.argmax(axis=1)
    return index, 1.0 - similarities[np.arange(len(query)), index]


def select_batch(indices, mean, uncertainty, features, batch_size, policy, rng):
    indices = np.asarray(indices)
    mean, uncertainty = np.asarray(mean), np.asarray(uncertainty)
    if batch_size < 1 or batch_size > len(indices) or len(np.unique(indices)) != len(indices):
        raise ValueError('Invalid candidate set or batch budget')
    if len(mean) != len(indices) or len(uncertainty) != len(indices) or len(features) != len(indices):
        raise ValueError('Mismatched candidate arrays')
    if not np.isfinite(mean).all() or not np.isfinite(uncertainty).all() or np.any(uncertainty < 0):
        raise ValueError('Invalid prediction or uncertainty')
    if policy['id'] == 'random':
        selected = rng.choice(len(indices), batch_size, replace=False)
        return indices[selected], [{'score':None,'uncertainty_term':0.,'diversity_penalty':0.} for _ in selected]
    base = mean + policy['uncertainty_weight'] * uncertainty
    redundancy = np.zeros(len(indices))
    available = np.ones(len(indices), dtype=bool)
    selected, reasons = [], []
    for _ in range(batch_size):
        score = base - policy['diversity_weight'] * redundancy
        candidates = np.flatnonzero(available)
        pick = candidates[np.lexsort((indices[candidates], -score[candidates]))[0]]
        selected.append(int(indices[pick]))
        reasons.append({'score':float(score[pick]),
                        'uncertainty_term':float(policy['uncertainty_weight'] * uncertainty[pick]),
                        'diversity_penalty':float(policy['diversity_weight'] * redundancy[pick])})
        available[pick] = False
        if policy['diversity_weight']:
            redundancy = np.maximum(redundancy, tanimoto(features, features[pick:pick+1]).ravel())
    return np.asarray(selected), reasons


class ReliabilityModel:
    def __init__(self, settings, seed, forest=False):
        self.settings, self.seed, self.forest = settings, seed, forest

    def _point_model(self, seed):
        if self.forest:
            return RandomForestRegressor(n_estimators=self.settings['forest_trees'], min_samples_leaf=2,
                                         max_features=1., random_state=seed, n_jobs=1)
        return StableRidge('standard', self.settings['ridge_alpha'])

    def fit(self, x, y):
        x, y = np.asarray(x), np.asarray(y)
        self.point = self._point_model(self.seed).fit(x, y)
        if self.forest:
            self.members = self.point.estimators_
        else:
            rng = np.random.default_rng(np.random.SeedSequence([self.seed, 17, len(y)]))
            self.members = []
            for _ in range(self.settings['bootstrap_members']):
                rows = rng.integers(0, len(y), len(y))
                self.members.append(self._point_model(self.seed).fit(x[rows], y[rows]))
        # Only revealed labels enter CV. This is an approximate residual band,
        # not a claimed conformal interval or an estimate of held-out performance.
        oof = np.empty(len(y))
        splits = KFold(n_splits=self.settings['cv_folds'], shuffle=True, random_state=self.seed)
        for fit, validation in splits.split(x):
            oof[validation] = self._point_model(self.seed).fit(x[fit], y[fit]).predict(x[validation])
        self.half_width = float(np.quantile(np.abs(oof-y), self.settings['nominal_interval_coverage'], method='higher'))
        self.n_observed = len(y)
        return self

    def predict(self, x):
        mean = self.point.predict(x)
        spread = np.std(np.asarray([m.predict(x) for m in self.members]), axis=0, ddof=1)
        if not np.isfinite(mean).all() or not np.isfinite(spread).all():
            raise ValueError('Nonfinite predictions')
        return mean, spread
