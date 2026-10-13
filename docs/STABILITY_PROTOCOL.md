# Stable heads and additional-target transfer

Protocol recorded on 2026-10-13 in `configs/stability-v1.json` before the head sweep.
This is an Aster retrospective acquisition experiment, not an official MoleculeACE
leaderboard result or a prospective laboratory validation.

## Development decision

Use only CHEMBL1862_Ki: published and scaffold-transfer partitions, 32/64 starting
measurements, seeds 0/1/2, five batches of eight. Compare six heads on identical
frozen CheMeleon embeddings and replay cases:

- Original training-only standardization, ridge alpha 10 (control).
- Centering without variance scaling, alpha 10 or 100.
- Standardization with a 0.1 floor on each training standard deviation, alpha 10.
- Remove features with training standard deviation below 0.01, then standardize
  the retained features, alpha 10.
- Original standardization, alpha 1000.

The filter/scaler is refitted using only currently revealed measurements each
round. All-constant inputs fall back to the observed mean. There is no clipping
of predictions. Both Morgan models and random selection run on the same cases.
Floating point comparison of the standardization control uses 1e-6 tolerance;
array layout can change float32 arithmetic at smaller scales.

A head must have zero prediction events outside [0,14] across audit AND remaining
candidate predictions; mean all-round audit MAE <=1.25; worst case/round MAE <=2;
and mean final strongest-decile discoveries >=90% of the original head and >=1.5
 times random. These are preregistered engineering screening thresholds, not
physical bounds or a claim of clinical usefulness. Repeated predictions of one
compound count as multiple events. Among passing heads select highest mean final
strongest-decile discoveries, then lowest mean all-round MAE, then candidate ID.
If nothing passes, stop instead of expanding the sweep using evaluation results.

These development cases have previously been inspected. They are appropriate for
repairing the head, but their scores are not fresh evidence of generalization.
The selected recipe and input/result hashes are saved in
`artifacts/stability-v1/frozen_recipe.json` before additional datasets are fetched.

## Additional targets

Predeclare CHEMBL214_Ki (serotonin 1A receptor), CHEMBL262_Ki (GSK-3β), and
CHEMBL4203_Ki (CLK4). Target identities were checked against the
[ChEMBL target API](https://www.ebi.ac.uk/chembl/api/data/target.json?target_chembl_id__in=CHEMBL214,CHEMBL262,CHEMBL4203).
The set covers a GPCR and two kinases; it does not represent three unrelated
families, and development was also on a kinase. Do not claim universal transfer.

Use the same pinned [MoleculeACE source revision](https://github.com/molML/MoleculeACE/tree/7e6de0bd2968c56589c580f2a397f01c531ede26/MoleculeACE/Data/benchmark_data),
Ki unit checks, duplicate exclusions, partition rules, and fingerprint settings as
broader-v2. The three previously inspected targets are marked exposed/development
and their molecular identities removed from new evaluation data. Metadata-only
partitioning precedes model runs. The prepared plan stores exact indices and hashes.
The generic preparer calls these overlap removals `development_overlap_removed`.
All three exposed datasets contribute to this exclusion, not only the head-development task.

New evaluation: 3 targets × 2 partition protocols × 2 starting sizes (32/64) × 2
seeds (0/1) × 4 arms = 96 replays. All arms acquire 40 compounds in batches of eight.
They share initial measurements, candidate pools, audit sets and tie-breaking.
Selection paths may diverge after the first batch; this is the behavior under test.
Report target-specific and protocol-specific results alongside aggregate means.
Audit outcomes and the pool's top-decile threshold are used only after selection.
No audit results drive optimization, early stopping, or recipe changes.

These are **new to Aster's tuning**, not known to be unseen by CheMeleon pretraining
or publication-time model selection. CheMeleon has previously been evaluated on
MoleculeACE. Retrospective scaffold transfer still differs from prospective novel
chemistry. Source assays are benchmark aggregates, not guaranteed homogeneous lab
campaigns. Two seeds measure limited initialization sensitivity, not independent
biological replication.

## Bounded fine-tuning pilot

Predeclared subset: all three additional targets, both protocols, initial size 32,
seed 0; six cases, five batches of eight. Compare only the matching frozen/Morgan/
random cases, not the entire 96-replay average. This is a local CPU feasibility and
effect-size pilot, not a broad hyperparameter search or a definitive fine-tuning verdict.

At every round reload the checksum-verified foundation encoder. Initialize a
linear auxiliary head to the frozen-recipe ridge predictor. Normalize outcomes
with the observed target mean and standard deviation only. Train encoder and
auxiliary head for exactly five epochs, batches of 16, AdamW (encoder LR 1e-5,
head LR 1e-4, weight decay 1e-4). Cap gradient norm at 1 for optimizer stability;
this does not clip predictions. Use deterministic CPU execution and two threads.
Then discard the auxiliary head and refit the **same frozen ridge recipe** on the
adapted features. Thus the final head policy is held constant; the representation
changes. Feature masks can change because they are always derived from observed
features. Restart from foundation weights each round for both independent-fit
consistency and reproducibility; no cross-target weights are carried forward.

Record observed sample counts, target scaling, per-epoch training losses, encoder
weight changes, predictions, selections, metrics, and wall time. A development
smoke run checks code/runtime; it does not choose among tuning configurations.
The adapter uses the official [Chemprop CheMeleon encoder API](https://chemprop.readthedocs.io/en/main/chemeleon_foundation_finetuning.html),
with a custom ridge-initialized adaptation loop rather than the official FFN recipe.
It is one specific adaptation method, not a comprehensive test of all fine-tuning.

## Reproduction

Install `requirements-neural.lock.txt` in the existing Python environment; obtain
and checksum the checkpoint as described in `BROADER_EVALUATION.md`. Never overwrite
completed artifact directories when code, dependencies or configuration changes.

```sh
MPLCONFIGDIR=.mplconfig .venv/bin/python -m aster.steady develop
MPLCONFIGDIR=.mplconfig .venv/bin/python -m aster.transfer --prepare
MPLCONFIGDIR=.mplconfig .venv/bin/python -m aster.transfer
MPLCONFIGDIR=.mplconfig .venv/bin/python -m aster.transfer \
  --fine-tune --output artifacts/transfer-tuned-v1
MPLCONFIGDIR=.mplconfig .venv/bin/python -m aster.stability_report
MPLCONFIGDIR=.mplconfig .venv/bin/python -m pytest -q
```

The transfer preparation wrapper binds the config template to the current frozen
recipe hash and records the correct target-selection metadata before sealing the
plan. The completed run applied the same metadata override directly before
evaluation; the wrapper makes that preparation reproducible. Additional guards
now reject changes to the recipe hash or the predeclared evaluation grid/budget.
These guards were also checked against the completed experiment manifests.
New source modules change the strict code contract, so use new output directories
when rerunning the experiment after implementation changes. Saved source snapshots
and dependency versions identify the code actually used in each completed run.
