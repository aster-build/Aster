# Censored measurements: keeping "> 10 µM" as a bound

A *censored* measurement is one the assay could not quantify. It reports a limit
instead of a value: "> 10 µM" for a compound that never inhibited over the tested
concentration range, "< 0.5 nM" for one that was already at the bottom of it. The true
value is on the far side of that limit, and the assay cannot say where.

Until this release the campaign workflow refused such rows. It accepted exact numbers
only, so a results file containing "> 10" failed validation and the measurement was
lost. The usual alternative loses it in a way nobody can see afterwards: write the bound
down as if it were the value, and every later calculation treats a limit of detection as
a result.

A campaign now stores the three facts a censored measurement carries — the relation, the
number, and the unit the campaign declared — and carries the relation through the fit,
the interval, and the decision record.

## What is stored

A measurement is `{relation, value, unit}`. `relation` is `=` for an exact number, or
one of `<`, `<=`, `>`, `>=` when the assay reported a bound. `value` is the number as
reported; for a censored row that number is the bound, not an estimate of the truth.

```
compound_id,smiles,value
cmp-001,CCO,7.4          # exact
cmp-002,CCN,> 10         # right-censored: the truth is above 10
cmp-003,CCCl,< 0.5       # left-censored: the truth is below 0.5
```

Both `create` and `import-results` accept either form, in the CLI and over HTTP.
`> 10`, `>10` and `≥ 10` all parse; anything that is neither a number nor a bound is
still refused rather than guessed at. A failed assay still has to carry an empty value:
a failure is not a bound. Both events record how many measurements arrived exact and how
many as bounds, so the campaign log says what kind of data it was given.

A measurement stored with no relation at all predates this change. It is read as exact,
which is what the workflow enforced when it was written, so no stored record changes
meaning and nothing is back-filled.

## How a bound reaches the ranking

`aster/censored.py` fits the ranking model with censored rows treated as bounds. The
procedure is the standard one for censored regression, and it is three lines of idea:

1. Start every censored row at its reported bound. This is exactly bound substitution,
   the practice this release exists to avoid, so the loop starts from the status quo.
2. Fit the model. Then replace each censored row's target with the model's **own
   prediction** where the bound allows it: a row reported "> 10" keeps a prediction of
   11.3, and is pulled back to 10 if the model said 9.
3. Refit, and repeat until the targets stop moving.

With no censored rows the loop fits once on the measurements and returns exactly what
fitting directly would, so a campaign of exact numbers gets bit-identical picks and the
earlier milestones stay comparable.

Three consequences, each recorded in the round:

- **The prediction interval is calibrated on the exact measurements only.** The distance
  from a prediction to a bound is not a prediction error, so censored rows calibrate
  nothing. A campaign with fewer than nine exact measurements gets no interval rather
  than a made-up one, which is the same rule [CONFORMAL.md](CONFORMAL.md) already
  applied.
- **The diagnostic range is read off what the fit treated the measurements as**, not off
  the reported bounds.
- **Each pick says how to read its nearest measured neighbour**, so a neighbour at
  "> 5.3" is not displayed as 5.3.

## What the decision record says

The record answers "were we right?" with three possible answers instead of two.

- A pick measured as a bound has no prediction error, so none is reported, the interval
  is not scored on it, and it is left out of the error figures, the within-batch rank
  agreement and the coverage rate. It still counts as a measurement, and the round
  reports `measured_exactly` and `measured_as_a_bound` separately.
- Whether a pick beat the best thing already known can be genuinely unknown. "> 9"
  against a best known of "> 6" runs off in the same direction as what it is being
  compared with, so either could be larger. That verdict is `undetermined`, counted in
  `improvement_undetermined`, and the plain-language sentence says the bounds cannot
  settle it.
- The best value known when a round was proposed carries its own relation and a flag
  saying whether the measurements pin it down.
- The matched random shadow batch ([DECISION_RECORD.md](DECISION_RECORD.md)) is compared
  only when every shadow compound has an **exact** measurement, because the comparison
  is of best and mean values and a bound has neither.

## Does it change the picks? The measurement

`scripts/censored_handling.py` runs the same campaign three ways on the public dashboard
example (MoleculeACE CHEMBL238, 160 compounds whose pKi values are all published, so
every outcome is already known). pKi is a potency scale on which larger is better.

- **discarded** — the measurement is thrown away, because the store cannot represent it.
  This is what Aster did before this release.
- **substituted** — the bound is written down as if it were the value.
- **bounded** — the bound is kept and fitted as a bound. This release.

Each replay draws a starting set of 56 compounds, leaves 104 in the pool, and runs four
rounds of eight. A censoring limit is applied to every measurement as it enters a
campaign, in the starting set and in each round's results, so the three arms see the
same assay results and differ only in what their store can represent. Both censoring
directions were run, because real assays have both: `low` is an assay whose range runs
out at the weak end (a quarter of the dataset reported as "< 5.72"), `high` one that
saturates on the strong compounds (a quarter reported as "> 7.52"). 40 replays each,
seeds 3000–3039. A "strong" compound is one in the top decile of the dataset by
published pKi, 16 of the 160; no arm ever sees the published values.

| | discarded | substituted | bounded |
|---|---|---|---|
| Measurements known at round 1, saturating assay | 41.8 | 56.0 | 56.0 |
| Strong compounds found per 32 assays, saturating | 4.33 | 4.98 | 4.98 |
| Mean absolute error on picks, saturating | 0.81 | 0.69 | 0.69 |
| Strong compounds found per 32 assays, weak-end limit | 5.18 | 5.25 | 5.25 |
| Mean absolute error on picks, weak-end limit | 0.84 | 0.71 | 0.71 |

**Finding 1: keeping censored measurements at all is what pays.** Against discarding
them, the saturating assay gives +0.65 strong compounds per 32 assays (SD 1.29, better
in 20 of 40 replays, worse in 8, Wilcoxon p = 0.0036) and prediction error on the picks
lower by 0.12 log units (better in 38 of 40, p = 1.0 × 10⁻¹⁰). At the weak end the
discovery difference is noise (+0.08, p = 0.77) but the error difference holds (−0.14
log units, better in 37 of 40, p = 6.0 × 10⁻¹¹). The mechanism is unglamorous: an arm
that cannot represent a bound starts with about 42 measurements instead of 56 and loses
roughly a quarter of every round's results.

**Finding 2, the negative one: fitting a bound as a bound did not change a single
pick.** The bounded and substituted arms selected identical batches in all 40 replays on
both censoring sides, and their prediction errors differ by 4 × 10⁻⁶ (weak end) and
4 × 10⁻⁴ (saturating) log units.

The reason is measurable rather than speculative. The censoring-aware targets only move
off their bounds when the model predicts past them, and with Morgan fingerprints plus
ridge regression at alpha 10 on about 56 measurements the predictions are shrunk hard
toward the training mean, so they rarely cross a limit set at the quartile. Mean target
movement was 0.0001 log units at the weak end and 0.0005 at the strong end, with a
largest single movement of 0.016; of 160 rounds, any movement at all occurred in 6 and
37 rounds respectively.

So on this dataset the honest statement is: the *representation* is what matters and the
*estimator* does not, yet. Two cases where that should change, neither tested here: a
dataset where censoring is heavy enough or the limit tight enough that the model wants
to predict past it, and a model that extrapolates rather than shrinking to the mean. The
bounded path is nevertheless the one to keep, because bound substitution destroys the
distinction permanently — once a limit is stored as a value, no later analysis can tell
which rows were limits — while keeping the relation leaves every option open.

**A smaller real effect: the interval.** Excluding censored rows from calibration
narrows the 90% interval against substitution on the saturating side, by 0.058 log units
(narrower in 28 of 40 replays, p = 0.018); at the weak end the difference is noise
(−0.007, p = 0.84). This is small, but it is in the right direction: those calibration
errors had been measured against bounds.

Reproduce with:

```bash
python scripts/censored_handling.py --replays 40 --censor-side high --output high.json
python scripts/censored_handling.py --replays 40 --censor-side low  --output low.json
```

One target, one dataset, one censoring rule applied synthetically to published values.
These numbers describe this dataset, not drug discovery.

## What is not done

- **The research data loaders still drop bounds.** `aster/data.py` curation marks a
  non-numeric endpoint `non_numeric_or_nonfinite_endpoint` and excludes the row, which
  is what the published benchmark splits assume. This release changes the campaign
  workflow, not the benchmark pipeline.
- **The dashboard does not show a bound.** The import dialog no longer claims censored
  values are rejected, but a batch table still prints the number; displaying the
  relation beside it belongs with the interval display work, which is also still
  pending.
- **The relation is not used in acquisition.** A compound known only as "< 5" is not
  treated as less informative to re-measure than an exact one, because the policy ranks
  candidates, and candidates have no measurement at all.
- **Nothing here converts units.** A bound is a bound on the endpoint the campaign
  declared, in the unit it declared; the workflow still does not convert µM to pKi.
