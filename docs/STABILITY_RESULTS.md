# Stable CheMeleon heads and additional-target results

Completed 2026-10-13. **The numerical repair worked, but these learned features
and this fine-tuning recipe did not outperform Morgan + ridge overall.**

## What changed

A predeclared six-head sweep used only the existing development target. The
selected head removes features whose standard deviation across currently measured
compounds is below 0.01, standardizes the retained features, and fits ridge with
alpha 10. It recomputes the mask/scaler only from revealed measurements each round.
Predictions are never clipped. Both feature filtering and a variance floor passed
the joint stability/discovery gate; filtering won by the predeclared discovery rule.
Centering lost discovery performance; stronger regularization alone retained outliers.

Development: 108 replays. The repaired head found 14.83 strongest-decile compounds
per 40 picks versus 10.33 for the unstable control and 15.17 for Morgan/ridge.
Mean all-round audit MAE fell from 4.764 to 0.890. Prediction events outside the
broad engineering guard [0,14] fell from 1,110 to zero. This is development evidence.

## Frozen recipe, new targets

96 replays: three additional targets, two protocols, 32/64 initial measurements,
two seeds, and four arms. Each replay chooses five batches of eight compounds.

| Model/policy | Strongest-decile discoveries / 40 | Final audit MAE |
| --- | ---: | ---: |
| Random selection | 4.92 | 0.750 |
| Morgan + random forest | 17.33 | 0.790 |
| Morgan + ridge | **18.67** | 0.815 |
| Stable frozen CheMeleon + ridge | 15.50 | 0.903 |

Bold identifies the strongest provisional **discovery** reference, not the lowest
prediction error. The stable frozen model produced zero guard violations; its
worst case/round audit MAE was 1.099. Nevertheless it lost to Morgan/ridge in 15
of 24 matched cases, tied three, and won six. Stability is necessary but insufficient.

Target/protocol detail matters. On published GSK-3β splits, frozen CheMeleon found
14.75 strongest-decile compounds versus Morgan/ridge 13.50; on serotonin 1A
scaffold-transfer splits, it found 9.00 versus 18.50. These averages combine the
same starting sizes and seeds within each group. Full tables are in the artifact report.

## Matched encoder-adaptation pilot

Six cases: all three targets, both protocols, 32 starting measurements and seed 0.
The same initial data, pools, audit sets, selection rule and 40-measurement budgets
apply to every comparator. Five fixed CPU epochs per round update the pretrained
encoder and an auxiliary linear head using only observed normalized outcomes.
The final predictor refits the same selected ridge recipe on the adapted features.

| Model/policy — same six cases only | Strongest-decile discoveries / 40 | Final audit MAE |
| --- | ---: | ---: |
| Random selection | 5.50 | 0.767 |
| Morgan + random forest | 16.17 | 0.810 |
| Morgan + ridge | **17.33** | 0.811 |
| Stable frozen CheMeleon | 15.33 | 0.904 |
| Adapted CheMeleon | 13.67 | 0.905 |

Adaptation tied frozen CheMeleon in four cases and lost in two; it never improved
discovery in this pilot. Encoder weights did change, and all predictions remained
within the engineering guard. This negative result applies to this specific
ridge-initialized, five-epoch adaptation recipe and limited seed coverage. It does
not rule out better adaptation methods or other targets.

## Decision and evidence

Keep Morgan + ridge as the provisional discovery reference. Prioritize detecting
unreliable predictions and testing uncertainty/diversity-aware selection on a
newly reserved evaluation set, rather than promoting neural complexity on this
negative result. Do not retune on these results and describe them as blind tests.

The targets are serotonin 1A, GSK-3β and CLK4; two are kinases. Molecular identities
shared with any previously inspected target were excluded (1, 123 and 148 compounds
respectively). These tasks are held out from Aster's recipe choice, not guaranteed
absent from CheMeleon pretraining or its publication-time model selection. There
is no prospective lab evidence or broad target-level statistical superiority claim.
Numerical guards are not calibrated uncertainty estimates.

All **210 main replays passed artifact validation; 28 tests passed**. Preparation
reproduced exact curated hashes and partitions. Fine-tuning source snapshots,
training losses, sample counts, target normalization, encoder changes, per-round
predictions and selected compound IDs are retained. No paid compute was used.

- [Fixed protocol, settings, sources and reproduction](STABILITY_PROTOCOL.md)
- [Study configuration](../configs/stability-v1.json)
- [Additional-target configuration](../configs/transfer-v1.json)
- Full local report: `artifacts/transfer-tuned-v1/REPORT.md`
- Development table: `artifacts/stability-v1/head_summary.csv`
- Frozen and matched pilot tables: `artifacts/transfer-v1/metrics.csv` and
  `artifacts/transfer-tuned-v1/matched_metrics.csv`
- Paired results: `artifacts/transfer-tuned-v1/paired_comparisons.csv`
