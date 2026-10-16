# Milestone 9 — does external evidence improve selection?

Study `evidence-v1`, run 2026-10-16. Predeclared in
[configs/evidence-v1.json](../configs/evidence-v1.json) and frozen by hash before the
run; artifacts in `artifacts/evidence-v1/`.

**Result: no. The predeclared gate is not met, and the campaign-only default stands.**

## The question

The roadmap asks whether evidence that Aster can retrieve — historical measurements
from the literature, structural information, or both — makes the next batch better
than a model trained on the campaign's own measurements alone.

## What could actually be tested

Only the first of the roadmap's three hypotheses can be tested with the data in this
repository, and only on one target.

| Arm | Status | Why |
| --- | --- | --- |
| Baseline (campaign measurements only) | Run | The implemented default |
| Literature-augmented, strict replay | Run | The dopamine-transporter corpus exists |
| Irrelevant-evidence control | Run | Information-matched, to catch artifacts |
| Structure-only | **Not run** | Docking covers one pocket of one structure for verified demo compounds; no pose or contact descriptor exists for the ~1,000 compounds in the replay task, and generating them would mean ~1,000 unvalidated poses |
| Combined | **Not run** | Requires the structural arm |
| Learned retrieval (MoleculeSTM-style) | **Not run** | The roadmap places it after a demonstrated gain from frozen retrieval |

## Design

- **Task:** `CHEMBL238_Ki`, the sodium-dependent dopamine transporter, the one target
  with both a literature corpus and an evaluation-role dataset.
- **Model and budget, identical in every arm:** Morgan fingerprints (radius 2, 2,048
  bits, chirality) with ridge regression (alpha 10, standardized), greedy selection of
  8 compounds for 5 rounds, from support sizes of 32 and 64.
- **Cases:** 2 protocols (published split, scaffold transfer) × 2 support sizes × 10
  seeds = 40 paired cases per arm, 120 replays in all.
- **Primary metric:** top-decile pool compounds recovered in the 40 picks. The decile
  cutoff is computed by the evaluator after the replay has finished.
- **Evidence arm:** permitted external pKi measurements are appended as additional
  training rows to every fit in the replay.
- **Control arm:** the same structures and the same set of values, with the values
  permuted among those structures. This holds the number of training rows and the
  value distribution fixed and destroys only the structure–value link, so a gain the
  control reproduces is an artifact of extra rows rather than of evidence.

## Leakage handling

`permitted()` enforces strict replay in code, not only in prose: an external record is
used only if its canonical isomeric SMILES appears **nowhere** in the replay dataset,
and the run aborts if a permitted record ever matches a pool or audit compound.

This filter is the first substantive finding. Of the corpus's 31 usable structures:

- **19 are already in the replay dataset**, so they are withheld. The corpus was built
  from ChEMBL activities on the same target, so it largely re-supplies what the replay
  is pretending not to know.
- **12 are permitted** in every case — new compounds, not in the task at all.

Two structures carried measurements disagreeing by more than 0.5 log units and were
excluded rather than averaged. One structure had replicate measurements inside that
tolerance and was averaged. Eight corpus records are target context with no
measurement and cannot enter a model.

Three declared rules are **not** satisfied and are limitations, not controls:

1. **No temporal cutoff.** The replay dataset carries no measurement dates, so earlier
   and later measurements cannot be separated.
2. **No independent review.** All 31 structures are machine-audited; zero are
   human-reviewed. Milestone 8's review gate is still open.
3. **One target, one endpoint, one corpus of 15 documents.** Nothing here generalizes.

## Results

Means over 40 paired cases, per 40 picks:

| Arm | Top-decile found | Additional hits | Audit MAE |
| --- | --- | --- | --- |
| Baseline | 13.23 | 32.60 | 0.808 |
| Literature-augmented | 13.63 | 32.15 | 0.803 |
| Irrelevant-evidence control | 13.43 | 32.73 | 0.812 |

Paired differences against the baseline, top-decile recovery:

| Arm | Mean difference | Standard error | Better / unchanged / worse | Published | Scaffold transfer |
| --- | --- | --- | --- | --- | --- |
| Literature-augmented | **+0.40** | 0.33 | 20 / 7 / 13 | +0.25 | +0.55 |
| Irrelevant-evidence control | +0.20 | 0.30 | 14 / 12 / 14 | −0.10 | +0.50 |

Predeclared gate: a mean gain of at least 1.0 top-decile compounds **and** at least 1.0
separation from the control. Observed: a gain of 0.40 with a separation of 0.20. **The
gate fails on both conditions.**

## Reading this honestly

- The literature arm's +0.40 is close to its own standard error of 0.33, and half of it
  is reproduced by an arm whose evidence values were deliberately scrambled. On this
  evidence the effect is indistinguishable from the effect of adding twelve more
  training rows of roughly the right potency range.
- Secondary metrics do not support a benefit either: the literature arm found slightly
  **fewer** compounds above the 7.0 pKi hit threshold (−0.45), and its audit error
  improved by 0.004 log units, which is nothing.
- This is a null result on one target with twelve permitted compounds. It does not show
  that literature evidence is useless for selection. It shows that *this corpus, at this
  size, does not move this selector*, and that the honest reason is mostly supply: the
  corpus's informative records are the ones the replay already has.
- No prediction left the 0–14 diagnostic guard in any arm.

## What this implies for the roadmap

1. **Keep evidence out of the ranking.** The product behaviour the repository already
   has — evidence is attached to a decision for a human to read, and never changes a
   score — is the behaviour this study supports.
2. **An evidence corpus is worth building for auditability, not for accuracy.** The
   value demonstrated here is that a reviewer can see what was known when a pick was
   made. Twelve compounds will not improve a ranking.
3. **Before re-running this with a bigger corpus**, fix the supply problem: a corpus
   assembled from the same source as the replay data mostly duplicates it. A meaningful
   retest needs evidence from outside the replay dataset, with dates, and with human
   review.

## Reproducing

```bash
python -m aster.evidence_selection --study configs/evidence-v1.json --output artifacts/evidence-v1
```

`artifacts/evidence-v1/` holds `contract.json` (inputs, library versions, module
hashes), `evidence_audit.json` (what the corpus supplied and what was dropped),
`evidence_filters.json` (per-case leakage filtering), `case_metrics.csv` (all 120
replays) and `comparison.json` (paired differences and the gate decision).
