"""Measurements that are a bound rather than a number: "> 10 µM", "< 0.5 nM".

An assay often cannot report an exact value. A compound that never inhibits over the
tested concentration range comes back as "greater than 10 micromolar": the true value
is somewhere above 10, and the assay cannot say where. Such a measurement is called
*censored* — right-censored when the truth lies above the reported bound, left-censored
when it lies below it.

Until now this workflow rejected those rows outright, because it accepted exact numbers
only. Rejecting them loses real information: knowing a compound is worse than 10 is not
the same as knowing nothing about it. The usual alternative is worse still: write the
bound down as if it were the measurement ("10") and let every later calculation treat a
limit of detection as a result. That silently biases the model towards the bound, and
nothing downstream can tell the difference afterwards.

This module keeps the three facts a censored measurement actually carries — the
relation, the number, and the unit — and gives the rest of the package three things:

  * `parse` and `text`, to read and write "> 10" faithfully;
  * `compare` and `best_known`, which answer "is this better than that?" with
    `None` when the bounds genuinely do not settle it, instead of guessing;
  * `fit`, which trains the ranking model on censored rows without pretending the
    bound is the value.

Nothing here is specific to potency. A bound is a bound on whatever endpoint the
campaign declared, in whichever direction that endpoint calls better.
"""
from __future__ import annotations

import math

import numpy as np

EXACT = '='
# The relations a stored measurement may carry. '<' and '<=' are kept apart because the
# assay report distinguishes them; no calculation here depends on the difference, and
# the code says so where it stops mattering.
RELATIONS = ('=', '<', '<=', '>', '>=')
# What a reader may write. Unicode forms come from assay exports and spreadsheets.
ALIASES = {'=': '=', '==': '=', '<': '<', '<=': '<=', '=<': '<=', '≤': '<=',
           '>': '>', '>=': '>=', '=>': '>=', '≥': '>='}
UPPER_BOUNDED = ('<', '<=')
LOWER_BOUNDED = ('>', '>=')
POLICY = 'censoring-aware ridge: bounds enter the fit as bounds, never as values'


def parse(reported):
    """Read a reported measurement into its relation and its number.

    Accepts a bare number ("7.4"), any of the relations in `ALIASES` with or without a
    space ("> 10", ">10", "≥ 10"), and nothing else. Raises on text that is neither,
    so a typo in a results file is refused rather than guessed at.
    """
    if reported is None:
        raise ValueError('A measurement is required')
    text_value = str(reported).strip()
    if not text_value:
        raise ValueError('A measurement is required')
    relation = EXACT
    for symbol in sorted(ALIASES, key=len, reverse=True):
        if text_value.startswith(symbol):
            relation, text_value = ALIASES[symbol], text_value[len(symbol):].strip()
            break
    try:
        value = float(text_value)
    except (TypeError, ValueError):
        raise ValueError(f'Cannot read "{reported}" as a measurement. Write an exact number, '
                         f'or a bound such as "> 10" or "< 0.5".') from None
    if not math.isfinite(value):
        raise ValueError('Measurements must be finite')
    return relation, value


def measurement(reported, unit=''):
    """One stored measurement: {relation, value, unit}.

    `value` is the number as reported. For a censored row that number is the bound, not
    an estimate of the truth, which is what `relation` is there to say.
    """
    relation, value = parse(reported)
    return {'relation': relation, 'value': value, 'unit': unit}


def relation_of(record):
    """The relation of a stored measurement, treating a missing one as exact.

    Campaigns created before censored measurements were supported hold bare numbers.
    Those were exact by construction — the workflow refused anything else — so reading
    them as '=' describes the decision as it was made rather than re-interpreting it.
    """
    if record is None:
        return EXACT
    return record.get('relation') or EXACT


def is_censored(record):
    return relation_of(record) != EXACT


def text(value, relation=EXACT, unit='', digits=2):
    """A measurement written the way a person reads it: "> 10.00 µM"."""
    prefix = '' if relation == EXACT else relation + ' '
    suffix = f' {unit}' if unit else ''
    return f'{prefix}{value:.{digits}f}{suffix}'


def bounds(relation, value):
    """The interval a measurement allows the truth to lie in, as (low, high).

    `None` marks the open side. An exact measurement allows one point.
    """
    if relation in UPPER_BOUNDED:
        return None, float(value)
    if relation in LOWER_BOUNDED:
        return float(value), None
    return float(value), float(value)


def compare(relation, value, threshold, sign):
    """Is this measurement better than `threshold`, in the declared direction?

    `sign` is +1 when larger measurements are better and -1 when smaller ones are, the
    same convention the campaign uses. Returns True, False, or `None` when the bound
    does not settle it: "> 10" is certainly better than 8 on an endpoint where larger is
    better, and certainly not better than 12 where smaller is better, but on an endpoint
    where larger is better it says nothing about 12.
    """
    low, high = bounds(relation, value)
    if sign > 0:
        if low is not None and low > threshold:
            return True
        if high is not None and high <= threshold:
            return False
        return None
    if high is not None and high < threshold:
        return True
    if low is not None and low >= threshold:
        return False
    return None


def best_known(records, sign):
    """The best measurement in a set, and whether the bounds actually pin it down.

    Used for "was this pick an improvement on what we already knew?". With censored rows
    present the answer can be genuinely unknown: if the best thing measured is "> 10" on
    an endpoint where larger is better, the best known value is somewhere above 10 and no
    later measurement of 11 can be called an improvement on it.
    """
    numbers = [(relation_of(record), float(record['value'])) for record in records
               if record.get('value') is not None]
    if not numbers:
        return {'value': None, 'relation': None, 'certain': False,
                'reason': 'No measurements were known when this round was proposed.'}
    exact = [value for relation, value in numbers if relation == EXACT]
    # A bound that runs off in the better direction cannot be beaten by a number.
    open_ended = [value for relation, value in numbers
                  if (sign > 0 and relation in LOWER_BOUNDED) or (sign < 0 and relation in UPPER_BOUNDED)]
    # A bound that runs off in the worse direction is no better than its own bound, so it
    # can stand in for a value when nothing exact beats it.
    closed = [value for relation, value in numbers
              if (sign > 0 and relation in UPPER_BOUNDED) or (sign < 0 and relation in LOWER_BOUNDED)]
    pick = max if sign > 0 else min
    if open_ended:
        edge = pick(open_ended)
        if not exact or sign * (edge - pick(exact)) >= 0:
            return {'value': edge, 'relation': '>' if sign > 0 else '<', 'certain': False,
                    'reason': 'The best measurement known was a bound, so the best known value '
                              'is only known to lie beyond it.'}
    if exact:
        return {'value': pick(exact), 'relation': EXACT, 'certain': True,
                'reason': 'The best measurement known was exact.'}
    return {'value': pick(closed), 'relation': '<' if sign > 0 else '>', 'certain': False,
            'reason': 'Every measurement known was a bound on the worse side, so the best known '
                      'value is only known to lie short of this one.'}


def summarize(records):
    """How many measurements are exact, and how many are bounds of each kind."""
    relations = [relation_of(record) for record in records]
    return {'measurements': len(relations),
            'exact': sum(relation == EXACT for relation in relations),
            'upper_bounded': sum(relation in UPPER_BOUNDED for relation in relations),
            'lower_bounded': sum(relation in LOWER_BOUNDED for relation in relations),
            'censored': sum(relation != EXACT for relation in relations)}


def clip(predictions, relations, values):
    """Pull each prediction into the region its measurement allows.

    A row reported "> 10" is consistent with any truth above 10, so the model's own
    prediction is used when it already lies above 10 and 10 is used when it does not.
    This is the expectation step of fitting a censored regression: the unobserved value
    is replaced by the best current estimate of it that respects the bound, rather than
    by the bound itself.
    """
    targets = np.asarray(predictions, dtype=float).copy()
    values = np.asarray(values, dtype=float)
    for index, relation in enumerate(relations):
        if relation in LOWER_BOUNDED:
            targets[index] = max(targets[index], values[index])
        elif relation in UPPER_BOUNDED:
            targets[index] = min(targets[index], values[index])
        else:
            targets[index] = values[index]
    return targets


def fit(x, values, relations, fit_model, *, tolerance=1e-8, max_iterations=50):
    """Fit the ranking model with censored rows treated as bounds.

    `fit_model(x, y)` must return a fitted model with a `predict` method; this module
    does not know or care which model that is. The loop starts from bound substitution —
    the common practice of writing the bound down as the value — and then repeatedly
    replaces each censored target with the model's own prediction clipped into the
    allowed region, refitting until the targets stop moving. With no censored rows it
    fits once on the measurements and returns exactly what fitting directly would, so
    adding this path changes nothing for a campaign of exact numbers.

    Returns the fitted model and a record of what the censored rows did to the targets.
    """
    x = np.asarray(x)
    values = np.asarray(values, dtype=float)
    relations = list(relations)
    if len(relations) != len(values) or len(values) != len(x):
        raise ValueError('Each measurement needs exactly one relation')
    censored = [index for index, relation in enumerate(relations) if relation != EXACT]
    targets = values.copy()
    model = fit_model(x, targets)
    record = {'policy': POLICY, **summarize([{'relation': relation, 'value': value}
                                             for relation, value in zip(relations, values)]),
              'iterations': 1, 'converged': True,
              'started_from': 'the reported bounds, which is what bound substitution would keep',
              'mean_target_shift_from_bound': 0.0, 'largest_target_shift_from_bound': 0.0}
    if not censored:
        return model, {**record, 'reason': 'No measurement was censored, so this is an ordinary '
                                           'fit on the measured values.'}
    for iteration in range(2, max_iterations + 1):
        updated = clip(model.predict(x), relations, values)
        moved = float(np.max(np.abs(updated - targets)))
        targets = updated
        model = fit_model(x, targets)
        record['iterations'] = iteration
        if moved <= tolerance:
            break
    else:
        record['converged'] = False
    shifts = np.abs(targets[censored] - values[censored])
    return model, {**record,
                   'mean_target_shift_from_bound': float(np.mean(shifts)),
                   'largest_target_shift_from_bound': float(np.max(shifts)),
                   'reason': f'{len(censored)} of {len(values)} measurements are bounds. Each one '
                             f'was fitted as a bound: its target is the model\'s own prediction '
                             f'when that respects the bound, and the bound itself otherwise.'}


def exact_rows(relations):
    """Indices of the exact measurements, for calculations a bound cannot enter.

    Calibrating a prediction interval is one: the error of a prediction against a bound
    is not an error, so censored rows are left out of calibration rather than treated as
    if the bound were the measurement.
    """
    return np.asarray([index for index, relation in enumerate(relations) if relation == EXACT],
                      dtype=int)
