# Prediction intervals, and how far they can be trusted

Every pick a campaign records now carries an interval as well as a number. This
document says how the interval is built, what was measured about it, and the two
things the measurement says that were not expected.

## What the interval is

**Split conformal** is the method. It needs no assumption about the shape of the
model's errors, only a held-out set of measurements to look at:

1. The measured compounds are split in half. One half fits a model, the other is
   kept back.
2. The fitted model predicts the kept-back half, and its absolute errors are
   sorted.
3. The half-width of the interval is the error at rank `ceil((n+1)(1-α))`, where
   `n` is the size of the kept-back half and `α` is the share of measurements
   allowed to fall outside. With α = 0.1 and 16 kept-back measurements the rank
   is `ceil(17 × 0.9) = 16`, which is the largest of the 16 errors. That is not a
   quirk of this implementation: at this little data a 90% interval has to be the
   worst error the model made on everything it was shown, which is the main
   reason the widths below are so large. It narrows only as the measured set
   grows.
4. Every candidate's interval is its prediction plus and minus that half-width.

The level is **90% nominal**: the interval aims to contain nine measurements in
ten. Nine calibration measurements is the fewest for which rank
`ceil((n+1)·0.9) ≤ n` holds at all; below that the honest interval is infinite,
and Aster records no interval instead of a made-up width.

The split is seeded from the round's training snapshot hash, so it is
reproducible and cannot be re-drawn until it flatters the result.

```
measured set (32)
        │
        ├── fit half (16) ──► ridge model ──┐
        │                                   ├──► |error| on each held-out compound
        └── held-out half (16) ─────────────┘            │
                                                   sort, take the 90% rank
                                                          │
                                   half-width ◄───────────┘
                                                          │
candidate ──► prediction ──► prediction ± half-width ──► recorded with the pick
```

## What changes in the record

- Each recommendation carries `interval`: `center`, `low`, `high`, `half_width`.
- The round carries `uncertainty`: the method, the nominal level, the
  calibration size, which error rank set the width, the seed, and the assumption
  the level rests on.
- Each slate row carries `interval_center`, so a compound a person picks by hand
  in the dashboard keeps an interval rather than losing one.
- The decision record reports, once a pick is measured, whether the measurement
  landed inside its interval, and the rate over the campaign.
- **Ranking is unchanged.** The picks still come from the full-data model, so
  every earlier milestone remains comparable. The interval is centred on the
  calibration-split model, and the round records how far apart the two centres
  sat.

Rounds decided before this existed report no interval. A width computed now
would use measurements the decision did not have.

## What was measured

`scripts/conformal_coverage.py`, 100 replays × 4 rounds of 8 on the public
dashboard example (MoleculeACE CHEMBL238, 160 compounds with published pKi
values, every outcome known in advance). Each round's stored intervals are
checked against the published values for three groups: the 8 compounds the
policy selected, the 8 in the round's matched random shadow batch, and all
eligible candidates.

| Group | Candidates | Inside the interval | Observed coverage |
|---|---|---|---|
| Selected by the policy | 3,200 | 2,965 | **92.7%** |
| Matched random shadow draw | 3,200 | 2,850 | **89.1%** |
| All eligible candidates | 46,400 | 41,959 | **90.4%** |

Nominal coverage is 90%. Mean half-width 1.77 pKi.

### Finding 1: the expected failure did not appear

The reason this item said "coverage assumptions can fail under adaptive
selection" is that conformal coverage assumes the compound predicted is
exchangeable with the calibration compounds, and greedy selection picks the
compounds the model scored highest, which is not a random draw.

On this dataset, selected picks were covered **more** often than nominal, not
less: 92.7% against 89.1% for a random draw from the same pool (mean per-replay
difference +3.6 points, SD 7.2, Wilcoxon p = 3 × 10⁻⁶, lower in 24 of 100
replays). The direction is the opposite of the concern.

A plausible reading, untested: the compounds the model scores highest here are
the ones most similar to what it has already measured, so they are the easy
ones, and easy predictions land inside a width calibrated on everything. That
would mean the assumption is violated in Aster's **favour** on this data, which
is luck, not safety. One target, one dataset, one policy. The published wording
stays cautious for that reason.

### Finding 2: the interval is barely narrower than ignoring the model

The same recipe applied to a model that predicts the average of what it was
trained on — no chemistry at all — gives a mean half-width of **1.81 pKi**
against the ridge model's **1.77**. The model's interval was narrower in 231 of
400 rounds (58%); mean difference −0.04 pKi, SD 0.17, Wilcoxon p = 0.006.

So the interval is honest and almost uninformative. ±1.77 pKi is a span of 3.5
log units, while the whole 160-compound set spans 4.78 to 9.10 and has a
standard deviation of 1.05. The central 90% of the values themselves lies in a
window 3.11 wide. An interval that covers nine measurements in ten on this data
is about as wide as the data.

This is the same shape as the temporal holdout result, where six of nine
endpoints failed to beat predicting the training mean. The ranking is useful;
the calibrated uncertainty around a single compound is not, at this amount of
data.

### What this does not show

- One target, one public dataset, 160 compounds. The coverage numbers describe
  this dataset.
- The 400 rounds are not independent: they reuse the same 160 compounds, and
  rounds within a replay share a campaign. The p-values describe the replay
  design, not a population of campaigns.
- Values are published literature measurements from one collection. Coverage
  against a single laboratory's repeat measurements was not tested.
- Nothing here tests coverage under a time split. The ExpansionRx temporal
  holdout is the dataset for that, and it has not been run with intervals.

## Reproducing

```bash
python scripts/conformal_coverage.py --replays 100 --output coverage.json
```

About 25 seconds. The JSON holds every round's counts as well as the summary.
