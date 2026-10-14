# Milestone 4 protocol: reliability-aware experimental selection

The fixed study is `configs/reliability-v1.json`. It was written before development
runs. New target identities were fixed before development; their outcome datasets
were downloaded only after `artifacts/reliability-dev-v1/frozen_policy.json` existed.
This is a small retrospective research comparison, not laboratory validation.

## Question and boundaries

Can Aster improve on greedy Morgan/ridge selection by exploring model disagreement,
reducing within-batch redundancy, or avoiding disagreement? Independently, do model
disagreement and chemical novelty identify larger prediction errors?

All learning receives only structures and measurements already revealed by the
oracle. Audit labels and hidden candidate measurements are used only after the
entire replay. All policies have the same initial measurements, candidate pools,
audit sets and five batches of eight assays. Once selections differ, later measured
sets differ by design. The primary outcome is final strongest-decile pool discoveries;
the pool threshold is evaluator-only. pKi >=7 hits and scaffold diversity are secondary.

Development intentionally reuses three already exposed tasks: CHEMBL1862_Ki,
CHEMBL1871_Ki and CHEMBL2034_Ki. Twelve cases (three tasks, two protocols, initial 32,
seeds 0/1) times seven policies =84 replays. Two targets are related and overlap;
these development results do not establish generalization.

Fresh evaluation: CHEMBL238_Ki (dopamine transporter), CHEMBL287_Ki (sigma receptor 1),
CHEMBL4005_Ki (PI3K alpha), verified using the
[ChEMBL API](https://www.ebi.ac.uk/chembl/api/data/target.json?target_chembl_id__in=CHEMBL238,CHEMBL287,CHEMBL4005).
Twenty-four cases (three tasks, two protocols, initial 32/64, seeds 0/1) times seven
policies =168 replays. All six previously inspected tasks contribute to structure
exclusions. The pinned revision, source hashes, conversion checks, duplicate policy
and scaffold split implementation are inherited from the prior benchmark. Exact
indices, cross-target overlap, and exclusions are in the prepared plan/data audit.
Fresh to this project does not imply universally unseen chemistry or unbiased
sampling of molecular space. No CheMeleon features or weights enter this milestone.

## Models, policies and diagnostic bands

Morgan: chirality-aware radius 2, 2,048 binary bits. Standardization fits only
observed data, followed by ridge alpha 10. The full-observation ridge supplies the
point prediction; the bootstrap ensemble does not replace its mean. Sixteen ridge
models fit independent bootstrap samples of observed compounds to supply prediction
standard deviation. The forest reference uses 200 trees, leaf size 2, and tree-level
prediction standard deviation. Both are disagreement proxies, not calibrated
predictive standard deviations.

Policy formulas, in pKi score units:

| Policy | Score |
| --- | --- |
| greedy | predicted pKi |
| explore | predicted pKi + 0.5 × bootstrap disagreement |
| cautious | predicted pKi − 1.0 × bootstrap disagreement |
| diverse | predicted pKi − 0.5 × maximum Tanimoto similarity to already selected batch members |
| explore_diverse | predicted pKi + 0.5 × disagreement − 0.5 × within-batch maximum similarity |
| random | uniform sampling without replacement |
| morgan_rf | random-forest predicted pKi |

Batch construction updates the redundancy penalty after each pick; the first pick
has zero penalty. Entire batches are chosen before their outcomes are revealed.
Ties resolve by candidate index. Distance to known chemistry is 1 minus the highest
Tanimoto similarity to a currently measured compound. Similarity uses float32 dot
products, preventing uint8 intersection-count overflow. No outcome clipping occurs.
These exploration scores are heuristics, not GP posterior UCBs with guarantees.

Training-only shuffled three-fold CV gives out-of-fold absolute residuals each round.
Their 80th percentile (`higher` interpolation) defines a constant-width symmetric
band around the full-observation predictor. This is an **approximate residual band**,
not a conformal method with a coverage guarantee. It uses no audit labels and does
not influence selection. Report empirical audit coverage and width, including under
scaffold shift. Adaptive sampling and differences between fold/full training sizes
limit interpretation. Raw ensemble spread is never mislabeled as a confidence interval.

Reliability diagnostics: Spearman association with absolute audit error, and AUROC
for detecting errors >1 pKi. Undefined correlations/AUCs are stored as null. Summaries
average defined case/round metrics equally; these correlated cases are not independent
biological replications. The descriptive screen requires mean AUC >=0.60 and mean
Spearman >=0.20. Nominal band coverage is 80%, with a predeclared ±10-point diagnostic
tolerance. These screens do not authorize changing the frozen policy after evaluation.

## Freeze and promotion decision

A challenger passes development only if it improves mean final strongest-decile
discoveries by >=1 over greedy, loses no more than 1 on any target mean, has final
mean audit MAE <=1.25, and has zero [0,14] prediction-guard violations. Among passers,
choose the highest mean discovery gain, then lower MAE, then policy ID. If none pass,
freeze greedy. Apply the same gate to the primary fresh-target comparison; all other
policy comparisons remain secondary and descriptive. Do not promote a post-hoc winner.
No significance or universal-superiority claim is planned from three new targets.

## Reproduce and inspect

Use the existing `requirements-neural.lock.txt` environment for consistency with
prior experiments. This milestone uses RDKit/scikit-learn/NumPy/SciPy; it does not
train a neural network or require a GPU. Every run records dependency versions,
code hashes, a source snapshot, the study hash and exact plan. Use new output paths
if any code or settings change; do not overwrite past results.

```sh
MPLCONFIGDIR=.mplconfig .venv/bin/python -m aster.reliability develop
MPLCONFIGDIR=.mplconfig .venv/bin/python -m aster.reliability prepare
MPLCONFIGDIR=.mplconfig .venv/bin/python -m aster.reliability evaluate
MPLCONFIGDIR=.mplconfig .venv/bin/python -m aster.reliability_report
MPLCONFIGDIR=.mplconfig .venv/bin/python -m pytest -q
```

Source datasets are fetched from the pinned MoleculeACE revision by the preparer
if not already cached, with checksums validated before use. The study, source data
config and frozen-policy hash bind evaluation to the declared protocol.
`recommendation_trace.csv` explains historical recommendations; it is not a future
lab submission. `validation.json` independently checks budgets, pool/audit separation,
nearest measured references, score decomposition, hit counts, error and band coverage.

## Technical research and open source actually used

- [MoleculeACE code/data](https://github.com/molML/MoleculeACE) and van Tilborg et al.,
  [Exposing the Limitations of Molecular Machine Learning with Activity Cliffs](https://doi.org/10.1021/acs.jcim.2c01073):
  benchmark data and the existing scaffold/shift evaluation context. This is Aster's
  acquisition protocol, not a reproduction of the paper's leaderboard.
- [RDKit](https://www.rdkit.org/docs/GettingStartedInPython.html): molecular parsing,
  Morgan fingerprints, scaffold identities and structural similarity inputs.
- [scikit-learn Ridge](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html),
  random forests, KFold, and metrics: regression, resampling and evaluation.
- Efron (1979), [Bootstrap Methods: Another Look at the Jackknife](https://doi.org/10.1214/aos/1176344552):
  the bootstrap-resampling foundation. Aster's disagreement score is a practical
  heuristic, not a validated bootstrap confidence interval.
- [Cross-validated prediction documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.cross_val_predict.html):
  distinction between out-of-fold predictions and valid generalization estimates.
  Aster implements the fold loop explicitly and measures actual errors on separate audit data.

The fixed score weights and greedy within-batch similarity penalty are Aster
experimental choices; no third-party acquisition package or unpublished model is claimed.
