# The decision record

Six months after a batch was tested, a researcher should be able to ask *why did we
test this, and were we right?* and get an answer from the record rather than from
memory. This document describes what Aster stores to make that possible, and what it
deliberately refuses to claim.

Two changes implement it: an endpoint is now declared per campaign instead of being
one of two hard-coded potency scales, and every pick can be read back as a decision
joined to its basis and its outcome.

## Any endpoint, any assay, one number per compound

A campaign declares three things about its measurements:

| Field | Meaning |
| --- | --- |
| `endpoint` | Any name, up to 100 characters: `pKi`, `pIC50`, `percent_inhibition`, `clearance`, `solubility` |
| `unit` | The unit, if the endpoint has one, for example `mL/min/kg` or `%` |
| `direction` | `higher_is_better` or `lower_is_better` |

```bash
python -m aster.campaign --db campaign.sqlite create \
  --name "Microsomal stability" --assay "HLM clearance" \
  --endpoint clearance --unit "mL/min/kg" --direction lower_is_better \
  --measured measured.csv --candidates candidates.csv
```

The contract is unchanged otherwise: one assay, one measurement per compound, exact or
a bound such as `> 10` ([CENSORED.md](CENSORED.md)). The declaration propagates through
selection, exports, the stored rounds and the API.

Two consequences inside the workflow:

- **Ranking follows the declared direction.** With `lower_is_better`, the batch is the
  lowest predictions, not the highest.
- **The extrapolation flag is no longer potency-specific.** `outside_diagnostic_range`
  used to mean "outside 0–14", which only made sense for a log-potency scale. It now
  means the prediction fell outside the measured range of the campaign, extended by one
  standard deviation of the measurements. Each round stores the exact range it used.
  This is a diagnostic, not a calibrated bound.

Campaigns created before this change still load: a campaign with no declaration is read
as a log-potency endpoint where higher is better, which is what the workflow assumed at
the time.

## What each round now stores

Rounds already recorded their training snapshot and its hash, the fitted coefficients,
the recipe, library versions and module hashes. Two additions complete the record:

- **`slate`** — the full ranked candidate list with each prediction and whether it was
  selected, so the record shows what was *rejected*, not only what was picked.
- **`policy`** — which rule produced the batch, plus the locked and excluded compounds
  in force at the time.
- **`propensity`** on every slate row — the probability that the policy in force would
  have selected that candidate, written when the batch is decided. A round-level
  `propensity` summary says whether the values are certain (all 1 or 0), how many
  candidates had any chance, and whether the committed batch actually followed the
  policy (`batch_followed_policy` is false when a person replaced the picks in the
  dashboard). The slate's `selected` flag likewise means "the policy picked it", not
  "it was committed"; the committed batch is `recommendations`.
- **`shadow`** — a matched random batch, drawn when the batch is decided and never
  assayed. See below.
- **`interval`** on every recommendation and **`uncertainty`** on the round — a 90%
  split conformal interval around each pick, and what that interval rests on. Each slate
  row carries the `interval_center` it would have had, so a compound picked by hand in
  the dashboard keeps an interval too. [Prediction intervals](CONFORMAL.md) has the
  method and the measured coverage.

## Selection propensity, and what it cannot do yet

A later question this record should be able to answer is "what would a different
selection policy have found?". The standard way to ask it from logged data is to weight
each measured pick by one over the probability that the policy in force would have
picked it. That probability depends on the model, the pool and the code at the moment
of decision, so it has to be written down then; it cannot be reconstructed afterwards.
That is why it is stored now, and why rounds from before this change report it as
`None` instead of being back-filled.

Today the answer is still no. The greedy policy picks the top-ranked candidates with
certainty, so every passed-over candidate has probability exactly zero, and dividing by
zero has no answer: no reweighting can say how those candidates would have scored.
`review` reports this per round under `off_policy`, with
`usable_for_off_policy_evaluation: false` and the reason. Turning it into a yes needs
some randomness in what gets measured: a policy that is not fully greedy, or assaying
some of the shadow batch described next. Which of those to adopt is a product decision,
not something this record makes.

## The matched random shadow batch

Every round also records a second batch that nobody runs: the same size as the real
batch, under the same locks and exclusions, with its free slots drawn uniformly at
random from the same eligible pool. It costs nothing, because it is never sent to the
assay: shadow compounds are not marked pending, never appear in an export, and are not
in the campaign view the dashboard reads.

Three choices fix what it means:

- **The draw cannot see the model.** Its seed is a hash of the training snapshot, the
  eligible ids and the round number, so it cannot lean toward compounds the model likes,
  and re-proposing the same round reproduces the same shadow. The seed and its basis are
  stored with it.
- **The policy's own picks stay in the draw.** So the two batches can share compounds
  (about half a compound per batch of eight, on average, in the replay below). Leaving the picks out would
  make the shadow a sample of "what greedy rejected" rather than of a random policy.
  Every unlocked candidate has the same chance of being drawn, stored as
  `propensity_unlocked`.
- **A dashboard override does not redraw it.** If a person replaces the picks, the
  shadow drawn with the preview is kept as drawn, and `review` says when its size no
  longer matches the committed batch.

`review` reports the shadow per round under `shadow`, and each decision says whether
the shadow also drew that compound (`also_in_shadow_batch`). A comparison between the
two batches is reported **only when every shadow compound has a measurement**. A shadow
compound can end up measured because the policy picked it, in that round or a later
one, but that measurement exists because the policy wanted it, so comparing a partial
shadow would quietly compare the policy against itself. In a live campaign that normally
means no comparison is ever reported; in a retrospective replay with known outcomes it
means every round.

### What it reports in a replay with known outcomes

`scripts/shadow_replay.py` runs 20 replays of the public dashboard example (MoleculeACE
CHEMBL238, 160 compounds), each from a different starting set of 32, for four rounds of
eight, and reads the record's own shadow comparison with the hidden values filled in for
the shadow compounds only:

| Measure | Result |
|---|---|
| Rounds compared | 80 (20 replays × 4 rounds) |
| Batch mean minus shadow mean, averaged per replay | +0.63 pKi (SD 0.25 across replays) |
| Replays where the batch mean beat the shadow mean | 20 of 20 (Wilcoxon p = 2 × 10⁻⁶) |
| Rounds where the batch's best compound beat the shadow's best | 54 of 80, 3 tied |
| Compounds shared between the two batches, per round | 0.54 on average |

This shows the mechanism working, not how the greedy policy performs in general: all 20
replays reuse the same 160 compounds from one target, so they are not independent
samples of chemistry. The more useful reading is the gap between the two rows: the
greedy batch is reliably better *on average*, but its single best compound beats a
random batch's best only about two rounds in three.

## Asking the question

```bash
python -m aster.decisions --db campaign.sqlite why CHEMBL238_Ki:376
python -m aster.decisions --db campaign.sqlite review
python -m aster.decisions --db campaign.sqlite record
```

Over HTTP: `GET /campaigns/{id}/decisions`, `GET /campaigns/{id}/decisions/review`,
`GET /campaigns/{id}/decisions/{compound_id}`.

`why` returns the decision chain and one plain sentence, every number in which is
stored rather than recomputed:

> Round 1: picked at rank 1 of the batch because it had one of the best predictions, out
> of 128 eligible candidates, with a predicted clearance of 5.69 mL/min/kg. Its nearest
> measured analog then was CHEMBL238_Ki:372 at 5.53 mL/min/kg (Tanimoto similarity
> 0.70), and the best measurement known at the time was 4.83 mL/min/kg. It measured 4.20
> mL/min/kg, 1.49 better than predicted, which beat the best measurement known when it
> was chosen.

Each decision carries three parts:

- **`why`** — rank in the batch and in the full slate, the selection policy, the
  prediction, the nearest measured analog with its value and similarity, the
  extrapolation flag, how many candidates were eligible, how many measurements existed,
  and the best value known at that moment.
- **`basis`** — the training snapshot hash, the recipe, the model intercept, library
  versions, module hashes and the diagnostic range. This is what makes the record
  describe the decision as it was made rather than as current code would make it.
- **`outcome`** and **`verdict`** — the measured value, the signed and absolute
  prediction error, and whether the result beat the best value known when the pick was
  made, judged in the declared direction. A pick with no result yet reads
  `awaiting_result`; a failed assay reads `no_result`. Neither is silently scored.

A compound that was never picked gets a straight answer rather than an invented one:
either it was never selected, or it was part of the initial measured set and no
selection decision was made about it.

## `review`: were the picks right?

`review` aggregates per round and overall: picks, results, failures, picks still
awaiting a result, how many beat the best value known at the time, mean absolute and
signed prediction error, the within-batch rank agreement between predictions and
outcomes, and the best measurement of each round against what was known before it.

Three limitations are returned with every review, because the numbers are easy to
over-read:

1. **Only picks have outcomes.** Rejected candidates were never measured, so the record
   cannot say whether a different batch would have been better. The slate shows what was
   rejected; it cannot show what would have happened.
2. **Error is measured against the model of that round**, not the current model.
3. **"Improved" means it beat the best measurement known when the pick was made.** That
   is a campaign milestone, not a biological or clinical claim.
4. **The shadow batch is never assayed.** It is compared with the real batch only when
   every shadow compound has a measurement.
5. **The interval's level is nominal.** Coverage is reported over selected picks, which
   is exactly the case where the conformal assumption does not hold, and a single round
   has too few measurements to measure a rate at all.

## The prediction interval, and what it is worth

Each pick records an interval as well as a number: its prediction plus and minus a
half-width taken from how wrong the model was on a held-out half of the measured set
([method and numbers](CONFORMAL.md)). The level is 90% **nominal**. The record never
calls it a guarantee, because the guarantee assumes the compound predicted is
exchangeable with the compounds the interval was calibrated on, and a batch chosen
because the model scored it highly is not.

Rather than assert that caveat, Aster measured it: over 100 replays on the public
example, selected picks were covered 92.7% of the time against 89.1% for a random draw
from the same pool, so on that data the violation ran in the model's favour. The same
study found the interval barely narrower than the identical recipe around a model that
just predicts the training average, 1.77 against 1.81 pKi. Both numbers are reported in
`review`, alongside the observed coverage over the campaign's own measured picks.

Ranking is untouched by all of this: the picks still come from the full-data model, so
every earlier milestone stays comparable, and the interval is centred on the
calibration-split model with the round recording how far apart the two centres sat.

## How structures were read

Each round also records the standardisation convention its fingerprints were computed
under: tautomers are not merged, salts are refused, charges are kept, and only the
resonance forms RDKit sanitisation merges are merged. It names the RDKit version and
carries a probe hash, so two campaigns can be checked for the same reading of
structures before their error figures are compared. Rounds from before this was logged
say `unknown`. See [STANDARDISATION.md](STANDARDISATION.md).

## What this deliberately does not do

- It does not put evidence into the ranking. [Milestone 9](EVIDENCE_SELECTION.md) tested
  that and the gate failed, so evidence stays attached to a decision for a human to
  read.
- It does not express confidence as a single score. The interval is calibrated against
  held-out error and reported with its nominal level and its assumption; similarity and
  the extrapolation flag remain diagnostics, not probabilities.
- It records a censored value such as "greater than 10 µM" as a bound, and keeps it a
  bound: such a pick has no prediction error, is left out of the error and coverage
  figures, and can leave the improvement verdict `undetermined` rather than resolved by
  guess. See [CENSORED.md](CENSORED.md). What it does not do is use the relation in
  acquisition, or display it in the dashboard.
