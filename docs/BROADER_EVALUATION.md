# Broader evaluation and frozen CheMeleon comparison

This implements the decision from the “Explain baseline report” discussion:
build harder evaluation first, run the existing baseline, then compare frozen
CheMeleon. Encoder fine-tuning is a subsequent controlled experiment, not part
of the frozen-model result.

## Scope

The original SARS-CoV-2 result stays in `artifacts/baseline/` unchanged. This suite
adds three non-viral MoleculeACE target tasks, chosen as the first three
lexicographically sorted Ki dataset IDs before inspecting model performance:

| Task | Project role | Eligible structures |
| --- | --- | ---: |
| CHEMBL1862_Ki | Development | 794 |
| CHEMBL1871_Ki | Evaluation | 659 |
| CHEMBL2034_Ki | Evaluation | 750 |

The two evaluation targets share 133 molecular identities. Their outcomes are
not independent biological replications. No molecular identities overlap with
the development task; the preparation code nevertheless enforces removal of
such overlap if present. This is broader than one antiviral target, but remains
a small task suite. Future expansion should include more dissimilar targets.

Each task has two starting-data sizes (32/64), two split protocols, three paired
seeds, and four model/policy arms: **36 cases × 4 arms = 144 replays**. Each replay
acquires five batches of eight measurements and fits again after the final batch.

## Harder tests

**Published partitions:** initial support and candidate pool come from the
original training set; the original test set is audit-only. These partitions
are not asserted to be temporal.

**Scaffold transfer:** shuffle whole Bemis–Murcko scaffold groups without labels;
allocate approximately 20% of rows to a support reservoir, 60% to the candidate
pool, and 20% to an untouched audit set. Sample 32 or 64 support compounds.
Discard unused support-reservoir rows from that replay. The three roles have
disjoint scaffold groups. Whole-group allocation means actual percentages vary.
The model may learn about a new scaffold once it acquires a compound in it.
Different scaffolds are not a guarantee of low structural similarity.

**Primary measure:** recover compounds from the candidate pool's strongest 10%,
defined by its 90th-percentile potency with ties included. Compute this threshold
only in post-run evaluation; it never guides the policy or its fitted model.
Save each pool's cutoff and eligible count so ties and attainable recall are clear.
This is a relative ranking metric, not a biological definition of a drug candidate.

**Secondary measures:** absolute hits (pKi ≥ 7, equivalent to Ki ≤ 100 nM), audit
MAE/RMSE, audit error on source-defined activity-cliff compounds, and new active
scaffolds relative to the initial support. Cliff flags never enter training,
acquisition or split generation.

The first development-only experiment (`broader-v1`) showed an absolute-hit
ceiling. Protocol `broader-v2` added the top-decile ranking measure **before either
evaluation target was run**. The configuration and split plan were frozen before
v2 results. Keep v1 as exploratory history, not part of the final comparison.

## What is compared

| Arm | Features | Predictor | Selection |
| --- | --- | --- | --- |
| morgan_rf | 2,048-bit chirality-aware Morgan fingerprints | 200-tree random forest | Highest predicted pKi |
| random | Same fingerprints | Same random forest for audit | Random, independent of predictions |
| morgan_ridge | Same fingerprints | StandardScaler + Ridge(alpha=10) | Highest predicted pKi |
| chemeleon_ridge | Frozen CheMeleon 2,048-dimensional embeddings | Same StandardScaler + Ridge(alpha=10) | Highest predicted pKi |

Scaler statistics and prediction heads are refit on acquired observations only.
No audit-label tuning, early stopping, head search, or encoder fine-tuning occurs.
The ridge pair tests representation choice with the same head; the forest versus
CheMeleon-ridge comparison tests complete pipelines and cannot isolate the encoder.

The frozen encoder loads only the official message-passing weights with
`torch.load(weights_only=True)` after SHA256 verification. It uses the official
BondMessagePassing and MeanAggregation path in evaluation mode on CPU. Its output
was checked against `MPNN.fingerprint` on two molecules and matched exactly.
Features are cached by structures, checkpoint, implementation tag and package versions.

Poor results from one fixed ridge configuration would not demonstrate that
CheMeleon generally fails. Sparse support and feature scaling can make a head
unstable on unfamiliar chemistry. Diagnose using development data before spending
compute on full fine-tuning, and retain failed configurations in reports.

## Reproduce

The neural dependency set uses RDKit 2026.3.6, selected by Chemprop's dependencies;
the original baseline lock used RDKit 2026.9.1. Both representations in the new
comparison use the same new environment. The old baseline artifacts and its
original lock file remain unchanged. Avoid comparing numbers across environments
as though only the encoder changed.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-neural.lock.txt
mkdir -p data/models
curl -fL https://zenodo.org/records/15460715/files/chemeleon_mp.pt -o data/models/chemeleon_mp.pt
.venv/bin/python -m aster.benchmark prepare
MPLCONFIGDIR=.mplconfig .venv/bin/python -m aster.benchmark run --role development --arms morgan_rf random morgan_ridge chemeleon_ridge
MPLCONFIGDIR=.mplconfig .venv/bin/python -m aster.benchmark run --role evaluation --arms morgan_rf random morgan_ridge
MPLCONFIGDIR=.mplconfig .venv/bin/python -m aster.benchmark run --role evaluation --arms chemeleon_ridge
.venv/bin/python -m pytest -q
```

Preparation downloads the three small CSVs if missing and checks each against a
pinned repository revision/checksum. The checkpoint is approximately 33 MB.
The implementation verifies its expected SHA256 before loading it. All runs are
local; no cloud service is provisioned.

Preparation refuses an existing destination. Reuse an existing prepared plan or
pass a new `--prepared` path. Model runs resume completed cases only when their
code, core package versions and plan contract agree; use a new `--output` for
changed implementations. Keep the full neural environment locked, too. Do not
change neural package versions in a partly completed comparison.

Artifacts:

- `artifacts/broader-v2-prepared/plan.json`: exact split indices, task roles, configuration and input hashes.
- `artifacts/broader-v2-prepared/data_audit.json`: rejected rows, units and cross-role filtering.
- `artifacts/broader-v2/REPORT.md`, `comparison.png`: results with limitations and completion count.
- `round_metrics.csv`, `final_metrics.csv`, `summary.csv`: per-round, per-seed and grouped results.
- `paired_differences.csv`: matched CheMeleon contrasts; positive differences mean more recovered compounds, but negative MAE differences mean smaller errors.
- `coverage.json`: expected/completed runs and explicit missing cases.
- `*__*.json`: selection order, predictions before label reveal, outcomes, audit predictions and pool thresholds.
- `run_contract.json`: plan, code and core environment hashes/versions.
- `data/embeddings/*.json`: exact structures, checkpoint and neural dependency versions for feature caches.

All prepared indices refer to row order in the hash-verified task CSV next to the
plan. These are replay controller artifacts containing labels, not model inputs.

## Interpretation and next decision

Evaluate the two held-out task roles separately from development and show each
target/protocol/support-size result. Do not turn correlated seeds, related targets
and overlapping compounds into an inflated claim of statistical independence.
Three seeds are an initial compute-bounded comparison, not a definitive study.

If CheMeleon does not improve ranking, keep the simpler model as the default.
Investigate prediction ranges, scaling, regularization and alternative heads on
development data. A controlled encoder fine-tuning experiment should use fixed
training budgets and task-separated tuning. The evaluation data already inspected
here cannot later be described as fresh blind validation.

## Sources and reuse limits

- [MoleculeACE repository](https://github.com/molML/MoleculeACE), revision `7e6de0bd2968c56589c580f2a397f01c531ede26`.
- [Activity-cliff benchmark paper](https://doi.org/10.1021/acs.jcim.2c01073).
- [CheMeleon paper](https://arxiv.org/abs/2506.15792) and [official embedding implementation](https://github.com/chrissly31415/chemeleon/blob/main/chemeleon_fingerprint.py).
- [Official checkpoint](https://zenodo.org/records/15460715/files/chemeleon_mp.pt), SHA256 `c376624d3407204e780a0ed13a9ac097cc9bb1c13ef89cdbc633c1715c183651`.

MoleculeACE's code is MIT-licensed; underlying ChEMBL data carry their own
attribution/ShareAlike terms. Verify dataset and weight terms independently for
redistribution or commercial deployment. The aggregated table does not retain
all raw assay context, replicate information or censoring flags.

CheMeleon was already evaluated on MoleculeACE in prior research. Exact pretraining
overlap has not been audited. These are project-level held-out tasks, not proof of
new structures unseen by the foundation model or by historical model development.
