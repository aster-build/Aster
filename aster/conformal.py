"""Split conformal intervals for a single-endpoint campaign.

A point prediction says "about 7.4". An interval says "7.4, and the measurement
will probably land between 6.1 and 8.7". Split conformal is the cheapest honest way
to get the second from the first: hold part of the measured set out of fitting, look
at how wrong the model was on that held-out part, and take a quantile of those errors
as the interval's half-width.

What it does not do here is promise coverage. The textbook guarantee assumes the
compound being predicted is exchangeable with the calibration compounds, which is
exactly what greedy selection breaks: the batch is chosen because the model likes it,
so it is not a random draw from the pool. Everything in this module therefore records
the nominal level and the assumptions beside the numbers, and `scripts/conformal_coverage.py`
measures what the coverage actually is on selected batches.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np

from .heads import StableRidge

# Nominal miscoverage. 0.1 means an interval that aims to contain 9 measurements in 10.
ALPHA = 0.1
# Share of the measured set held out of fitting to calibrate the interval.
CALIBRATION_FRACTION = 0.5
METHOD = 'split conformal on absolute residuals'
ASSUMPTION = ('Nominal coverage holds when the compound predicted is exchangeable with the '
              'calibration compounds. Greedily selected batches are not: they were chosen '
              'because the model scored them highly. Treat the level as nominal, not as a '
              'distribution-free guarantee, and check it against measured outcomes.')


def smallest_calibration_size(alpha=ALPHA):
    """Fewest calibration points for which the conformal quantile is defined at all.

    The half-width is the k-th smallest calibration error with k = ceil((n+1)(1-alpha)).
    When k exceeds n there is no such error, and the honest answer is an infinite
    interval, which this module reports as no interval rather than a made-up number.
    """
    size = 1
    while math.ceil((size + 1) * (1 - alpha)) > size:
        size += 1
    return size


def quantile_rank(size, alpha=ALPHA):
    """Which calibration error becomes the half-width, counting from the smallest."""
    return math.ceil((size + 1) * (1 - alpha))


def split(count, seed, fraction=CALIBRATION_FRACTION):
    """Which measured rows calibrate and which ones fit, as index arrays.

    The split is drawn from a seed fixed by the training snapshot, so the same round
    re-proposed gives the same split, and the split cannot be chosen after seeing which
    one produces a flattering interval.
    """
    order = np.random.default_rng(seed).permutation(count)
    held = int(round(count * fraction))
    return np.sort(order[held:]), np.sort(order[:held])


def seed_from(training_sha256):
    """A seed that depends only on what the round was trained on."""
    return int(hashlib.sha256(('conformal:' + training_sha256).encode()).hexdigest()[:16], 16)


def calibrate(x, y, *, seed, alpha=ALPHA, fraction=CALIBRATION_FRACTION, recipe=None):
    """Fit on one part of the measured set, measure the model's error on the other.

    Returns the fitted calibration-split model and a record of the interval it supports:
    `half_width` is None when there are too few calibration points for a quantile to
    exist, and the record says so in `reason` instead of inventing a width.
    """
    x, y = np.asarray(x), np.asarray(y, dtype=float)
    recipe = recipe or {'mode': 'standard', 'alpha': 10}
    fit_rows, calibration_rows = split(len(y), seed, fraction)
    minimum = smallest_calibration_size(alpha)
    base = {'method': METHOD, 'nominal_coverage': 1 - alpha, 'alpha': alpha,
            'calibration_fraction': fraction, 'calibration_size': int(len(calibration_rows)),
            'fit_size': int(len(fit_rows)), 'smallest_calibration_size': minimum,
            'seed': seed, 'assumption': ASSUMPTION}
    if len(fit_rows) < 2 or len(calibration_rows) < minimum:
        return None, {**base, 'half_width': None, 'quantile_rank': None,
                      'reason': f'{len(calibration_rows)} calibration measurements is fewer than the '
                                f'{minimum} needed for a {1 - alpha:.0%} interval to be defined. No '
                                f'interval is reported.'}
    model = StableRidge(recipe['mode'], recipe['alpha']).fit(x[fit_rows], y[fit_rows])
    errors = np.sort(np.abs(model.predict(x[calibration_rows]) - y[calibration_rows]))
    rank = quantile_rank(len(calibration_rows), alpha)
    return model, {**base, 'half_width': float(errors[rank - 1]), 'quantile_rank': rank,
                   'calibration_error_median': float(np.median(errors)),
                   'reason': f'Half-width is the {rank}th smallest of {len(errors)} calibration '
                             f'errors, which is the {1 - alpha:.0%} conformal quantile.'}


def interval(center, half_width):
    """One prediction as a range, or as a bare point when no half-width exists."""
    if half_width is None:
        return {'center': float(center), 'low': None, 'high': None, 'half_width': None}
    return {'center': float(center), 'low': float(center) - half_width,
            'high': float(center) + half_width, 'half_width': float(half_width)}


def covers(entry, value):
    """Did the measurement land inside the recorded interval? None when there was none."""
    if entry is None or entry.get('half_width') is None:
        return None
    return bool(entry['low'] <= value <= entry['high'])


def coverage(pairs):
    """Observed coverage over (interval, measurement) pairs, with the count it rests on."""
    flags = [covers(entry, value) for entry, value in pairs]
    flags = [flag for flag in flags if flag is not None]
    if not flags:
        return {'measurements': 0, 'covered': 0, 'observed_coverage': None}
    return {'measurements': len(flags), 'covered': sum(flags),
            'observed_coverage': sum(flags) / len(flags)}
