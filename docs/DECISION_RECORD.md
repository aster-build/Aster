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

The contract is unchanged otherwise: one assay, one exact number per compound, no
censored values. The declaration propagates through selection, exports, the stored
rounds and the API.

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

## What this deliberately does not do

- It does not put evidence into the ranking. [Milestone 9](EVIDENCE_SELECTION.md) tested
  that and the gate failed, so evidence stays attached to a decision for a human to
  read.
- It does not express confidence. Similarity and the extrapolation flag are shown;
  neither is a calibrated interval.
- It does not record censored values such as "greater than 10 µM". The workflow still
  requires exact numbers, so a campaign whose assay reports limits cannot be recorded
  faithfully yet. That is the next real gap in the data model.
