# Temporal holdout results

**Protocol:** `docs/TEMPORAL_PROTOCOL.md`, declared before the run.
**Config:** `configs/temporal-v1.json`. **Artifacts:** `output/temporal/`.
**Source:** `openadmet/openadmet-expansionrx-challenge-data` at revision `6b898cc`.

## The short version

Aster's default model keeps most of its apparent accuracy only because every
evaluation it has run until now tested it on compounds drawn at random from the
same pool it trained on. Tested instead on the compounds that came **later**, the
same model on the same data:

- gets **1.2× to 1.8× more error** on every one of the nine endpoints, mean
  normalised error 1.018 against 0.591;
- **fails to beat "predict the average of what you have already measured" on six
  of the nine endpoints**, where under matched random splits it beats that floor
  in 170 of 180 cases;
- loses about a third of its ranking ability, mean Spearman 0.424 against 0.687.

The mean penalty is **+0.427** in units of the held-out values' own spread, 95%
confidence interval 0.238 to 0.616 across nine endpoints, and it is positive for
every endpoint and at every one of 36 nested cutoffs tested. It is not an artifact
of the publishers' chosen cutoff, and it is not an artifact of sample size,
because the control uses the same measurements at the same training and test
sizes.

**This is a negative result about Aster's existing numbers, and it is the point of
running it.** The milestone figures were not wrong arithmetic; they answered an
easier question than the one a real campaign asks.

## What was run

35,646 eligible measurements over 7,608 compounds and nine ADMET endpoints.
The temporal split trains on 24,940 measurements and tests on 10,706.

| Arm | Cases | What it is |
| --- | --- | --- |
| `temporal` | 9 | Train at or below registration 20100, test above it. One per endpoint. |
| `random_matched` | 180 | Same measurements, same sizes, split at random over 20 seeds. |
| `temporal_rolling` | 36 | Four nested earlier cutoffs per endpoint. |

No endpoint fell below the declared minimum, so nothing was skipped.

## Primary result: prediction error

Normalised mean absolute error, where **1.0 is the error of predicting the
held-out average** and lower is better. The control column is the mean over 20
seeds; its standard deviation is in `output/temporal/comparison.json`.

| Endpoint | Train | Test | Temporal | Random matched | Gap | Beats no-model floor? |
| --- | ---: | ---: | ---: | ---: | ---: | :---: |
| Mouse liver microsomal clearance | 4,375 | 1,161 | 1.524 | 0.644 | **+0.880** | no |
| Human liver microsomal clearance | 3,595 | 767 | 1.466 | 0.776 | **+0.690** | no |
| Caco-2 permeability | 2,156 | 1,615 | 1.355 | 0.789 | **+0.566** | no |
| Mouse plasma protein binding | 1,292 | 454 | 0.977 | 0.572 | +0.405 | no |
| LogD | 5,039 | 2,270 | 0.738 | 0.390 | +0.348 | yes |
| Caco-2 efflux ratio | 2,161 | 1,616 | 1.048 | 0.716 | +0.332 | no |
| Kinetic solubility | 5,128 | 2,170 | 0.915 | 0.619 | +0.296 | no |
| Mouse brain protein binding | 973 | 449 | 0.682 | 0.417 | +0.265 | yes |
| Mouse muscle binding | 221 | 204 | 0.459 | 0.393 | +0.066 | yes |

In the endpoints' own units the inflation runs from 1.22× (mouse muscle binding,
MAE 0.270 against 0.221) to 1.78× (mouse liver clearance, 0.791 against 0.444).
Put the other way round: **a random split reports about 35% less error than the
same model and data earn on a time-ordered test.**

### The floor matters more than the ratio

The row to read is the last column. Six of nine endpoints — both liver clearance
endpoints, both Caco-2 endpoints, solubility and plasma protein binding — give a
model whose predictions are **worse than a constant**. Predicting the mean of the
already-measured values for every new compound would have scored better. Under
matched random splits the same model clears that floor in 170 of 180 cases.

That is a different and more serious statement than "accuracy drops". For those
six endpoints, on this campaign, at this training size, the fitted model carried
no usable information about the compounds that came next.

Three endpoints survive: LogD (0.738), mouse brain protein binding (0.682) and
mouse muscle binding (0.459). LogD is the most physics-like of the nine and the
best covered; the two binding endpoints have the narrowest assays. Mouse muscle
binding has the smallest gap of all, and also by far the smallest sample (221
training, 204 test), so its estimate is the least stable of the nine and should
not be read as evidence that small endpoints are safer.

## Why: the later compounds are new chemistry

The protocol carried two explanatory measures on every case, and they tell a
single consistent story.

| | Temporal | Random matched |
| --- | ---: | ---: |
| Distance to the nearest training compound | 0.36 – 0.42 | 0.21 – 0.24 |
| Held-out compounds whose ring skeleton never appears in training | **72% – 82%** | 31% – 38% |

Under a random split, two thirds of the test compounds belong to a chemical
series the model has already seen examples of. Under the temporal split, roughly
three quarters belong to a series it has never seen. That is not a flaw in the
dataset; it is what lead optimisation *is*. Chemists look at this month's results
and make next month's compounds somewhere new. A random split quietly assumes
the opposite, and that assumption is where the flattering numbers come from.

A possible confound was checked and does not explain the gap: the held-out values
could simply have a narrower spread under the temporal split, which would depress
rank correlation on its own. The spreads are comparable between the two arms
(`temporal_test_value_sd` against `random_matched_test_value_sd_mean` in
`comparison.json`), sometimes wider under the temporal split, so range
restriction is not driving the result. It does contribute for human liver
clearance, where the temporal holdout's spread is 0.461 against the control's
0.618.

## It is not the publishers' cutoff

Repeating the temporal split at four nested earlier cutoffs per endpoint gives 36
further comparisons. **All 36 gaps are positive**, from +0.038 to +1.147. The
penalty is a property of testing forward in time, not of the one cutoff the
challenge organisers picked. On the three best-covered endpoints the gap tends to
*shrink* at later cutoffs — solubility goes +1.007, +0.720, +0.547, +0.313 as the
training set grows — which is the expected shape: more accumulated history makes
the next step less of a leap, without ever closing the gap.

## What this can and cannot support

Nine endpoints is a small design and the power accounting says so plainly.

- The paired comparison across endpoints has **nine pairs**, mean +0.427,
  standard deviation 0.246, 95% CI [0.238, 0.616], paired t = 5.22, p = 0.0008.
- The **minimum detectable effect at nine pairs is 0.262**. The observed +0.427
  clears it, which is why the effect is reported as real.
- The same design has only **19% power against an effect of 0.10**, and would
  need about 50 endpoints to detect that reliably. So this run can say "the
  penalty is large"; it cannot resolve small differences, and it cannot rank the
  endpoints against each other.
- The nine endpoints come from one company's campaigns in one disease area. They
  are **not independent draws** from drug discovery at large, so the p-value
  describes this dataset and is not an estimate for the field.
- The temporal arm is a single deterministic split per endpoint, so it has no
  variability of its own. Every spread quoted here belongs to the random control.

### Claims this result does not license

- Not "Aster's model is useless". It clears the floor on three endpoints and the
  comparison is against a deliberately unchanged, untuned default.
- Not "a better model would fix this". No alternative model family was run. The
  gap is a property of the evaluation, and testing whether a different model
  narrows it is separate work (queue item 11).
- Not a statement about **potency**, which is what every earlier Aster milestone
  measured. These are ADMET endpoints. The milestone numbers are not restated or
  corrected by this run; what this run establishes is that the *protocol* those
  numbers were measured under is optimistic.
- Not a measure of whether Aster **picks better compounds**, only of how well it
  predicts values. The discovery-metric arm addresses that question directly.

## Where it sits against outside work

Both 2026 papers that independently reproduced Aster's earlier negative results
use this same release, which is why it was chosen. Two points of contact worth
recording, both from the project's existing research notes:

- The challenge drew **370+ participants and over 1,000 submissions**, and the
  organisers credited extra proprietary data and feature engineering over model
  choice; four of the top five finishers used proprietary data. Winners have not
  published quantitative accuracy figures, so no direct leaderboard comparison is
  available.
- The field's own guidance converges with what is seen here: a pretrained
  backbone's head start disappeared by roughly 200 labels in OpenADMET's own
  campaign work, and uncertainty estimates correlated with error at only about
  ρ = 0.2. Neither contradicts this run; both argue the same way, that the
  binding constraint is data and evaluation rather than model capacity.

## Reproducing it

```
python -m aster.expansionrx                 # fetch, verify and curate the release
python -m aster.temporal                    # run the three arms and the analysis
```

Outputs: `output/expansionrx/source_report.json` (provenance, curation and
censoring audit), `output/temporal/case_metrics.csv` (one row per case),
`output/temporal/comparison.json` (per-endpoint and paired analysis with power).
The run takes about two minutes on one core.

## Secondary result: does ranking still beat picking at random?

Prediction error is not what Aster is for. It exists to choose which compounds
to assay next, and that is what its milestones report. So the second arm asks
the product question directly: train on the earlier measurements, rank the later
compounds, take the top 40, and count how many meet the endpoint's criterion,
against taking 40 at random.

The criteria are declared in `configs/temporal-v1.json` before the run. They are
round numbers in common medicinal-chemistry use — solubility above 100 µM, liver
clearance below 20 mL/min/kg, lipophilicity between 1 and 3, free fraction above
5% — and they are **this study's choices, not published consensus**, so the whole
arm is also run at a stricter (half) and a looser (double) setting.

### Ranking survives, at under half the advantage a random split reports

Extra compounds meeting the criterion per 40 assays, over random picking:

| Endpoint | Pool hit rate | Temporal | What a random split reports | Lost to time |
| --- | ---: | ---: | ---: | ---: |
| Mouse muscle binding | 61% | +13.1 | +16.9 | 3.8 |
| Kinetic solubility | 68% | +9.6 | +10.0 | 0.4 |
| Mouse liver microsomal clearance | 6% | +8.3 | +18.2 | 9.8 |
| Mouse brain protein binding | 47% | +6.1 | +19.5 | 13.4 |
| Human liver microsomal clearance | 45% | +5.6 | +11.9 | 6.3 |
| LogD | 69% | +3.9 | +12.1 | 8.2 |
| Caco-2 efflux ratio | 29% | +3.8 | +11.4 | 7.6 |
| Mouse plasma protein binding | 81% | +2.6 | +10.4 | 7.8 |
| Caco-2 permeability | 22% | +0.6 | +9.1 | 8.5 |

Ranking beat random picking on all nine endpoints, mean **+5.9 per 40 assays**
(95% CI 3.0 to 8.9, paired t on 9 endpoints, p = 0.0016). The same comparison on
a matched random split would have reported **+13.3**. The inflation is the firmer
of the two findings: **+7.3 per 40** (95% CI 4.5 to 10.1, p = 0.0003).

Sensitivity to the declared criteria, which matters because they are chosen:

| Setting | Mean advantage | Endpoints where ranking won | Random-split figure |
| --- | ---: | ---: | ---: |
| Stricter (half) | +2.9 | 6 of 9, one negative | +8.6 |
| **Declared** | **+5.9** | **9 of 9** | **+13.3** |
| Looser (double) | +4.1 | 8 of 9 | +7.9 |

The direction holds at all three. The magnitude plainly does not, so the
supportable claim is "ranking still helps under time ordering", not the 5.9.

### Two things worth separating

**Ranking well and predicting well are not the same thing.** Mouse liver
microsomal clearance has the *worst* prediction error of all nine (normalised MAE
1.524, far past the no-model floor) and yet ranks usefully: 11 hits against 2.6
for random picking, with none of 20 random seeds matching it. Only 6% of the
later compounds meet that criterion, so it is a needle-in-a-haystack pool, and
the model located needles while being unable to say how large any of them was.
This dissociation argues that the discovery metric is the more faithful measure
of what Aster does, and that the error result above, serious as it is, is not the
whole verdict.

**One endpoint's result is indistinguishable from chance.** Caco-2 permeability
gained +0.6 compounds and 8 of the 20 random draws did as well or better. It is
reported as a null, not averaged in quietly.

### Additional limitations of this arm

- One batch of 40 chosen in a single shot, not five sequential rounds of eight as
  the milestones run. Sequential picking inside the later era would require
  inventing an arrival order the release does not supply. This measures the first
  decision, not a whole campaign.
- A hit here means one endpoint clears one bar. Real programmes need several
  endpoints to pass at once, which is strictly harder than anything measured here.
- The later pool is the set of compounds chemists chose to make, already shaped by
  their judgement. Beating random selection *inside* that pool is not evidence of
  beating a medicinal chemist.
- At the stricter setting the observed effect (+2.9) is smaller than that design's
  own minimum detectable effect (3.4) despite p = 0.027, so that particular number
  was found with less than the intended power and is the weakest in this document.

Reproduce with `python -m aster.temporal_discovery` (about four minutes).
Outputs: `output/temporal/discovery_case_metrics.csv`,
`output/temporal/discovery_comparison.json`.
