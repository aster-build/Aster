# Reliability and smarter batch selection: completed findings

**Keep greedy Morgan + ridge as the provisional default.** The exploration policy
that passed development did not improve discovery on three fresh targets.

| Policy | Strongest-decile compounds / 40 picks | Final audit MAE |
| --- | ---: | ---: |
| Greedy Morgan + ridge | 14.29 | 0.838 |
| Frozen exploration policy | 14.17 | 0.838 |
| Diversity penalty (secondary) | 15.13 | 0.825 |
| Exploration + diversity (secondary) | 14.92 | 0.825 |
| Cautious selection (secondary) | 14.21 | 0.833 |
| Morgan + random forest | 14.04 | 0.815 |
| Random selection | 3.42 | 0.777 |

Development selected prediction +0.5×bootstrap disagreement: 14.00 discoveries
versus greedy 12.33. The fixed recipe was then evaluated without retuning, and the
fresh-target gain was -0.125. Diversity improved the secondary average by +0.833,
below the predeclared +1 threshold; do not promote a post-hoc winner.

## Reliability findings

Under the greedy reference, bootstrap disagreement had mean large-error AUROC
**0.477** (chance ranking is 0.5) and error correlation **-0.034**. It is not a useful
large-error detector here. More disagreement did not reliably mean more error.
Chemical novelty performed modestly better: AUROC **0.610**, correlation **0.204**.
Those are weak descriptive associations, not a validated probability of failure.

The approximate nominal-80% cross-validation residual bands covered **72.5%** of
audit outcomes overall. On the sigma-receptor scaffold-transfer cases, coverage
was only **63.4%**. Do not label these bands or raw model disagreement as calibrated
confidence. The bands were diagnostic only; they did not choose compounds.

Diversity did change the batches: mean within-batch Tanimoto distance increased
from **0.656 to 0.737**, and novel selected scaffold count from **20.7 to 24.0**.
These scaffold counts include inactive compounds. A more diverse batch is not
necessarily a more productive batch.

## What was built and tested

- Seven fixed selection policies, 16 bootstrap ridge models, nearest-measured
  similarity, training-only CV residual bands, and per-compound score explanations.
- 84 development and 168 fresh-target replays: all 252 passed artifact validation.
  34 software tests passed, including hidden-label independence, batch accounting,
  diversity/uncertainty score behavior and similarity-overflow protection.
- Fresh tasks: dopamine transporter, sigma receptor 1, PI3K alpha. All compounds
  shared with the six previously inspected targets were excluded. Cases vary
  initial measurements (32/64), partition protocol and seed, with 40 new picks each.
- Frozen study/config hashes, source snapshots, exact partitions, per-round
  predictions, reliability metrics, and interpretable historical recommendations.
- No neural fine-tuning in this milestone. No paid compute or new lab measurements.

There are only three fresh targets and two seeds. Repeated cases are correlated;
these results do not prove universal model or policy superiority. These targets
are now inspected and cannot be called blind tests of subsequent changes.

## Roadmap position and next step

The first **Phase 3 experimental-selection comparison is complete**. A thin Phase 4
integration slice is next: import measurements/candidates, create a campaign, fit
Morgan/ridge, review eight proposed compounds with nearest-neighbor evidence,
lock/exclude compounds, export a batch, import outcomes, and repeat. Display novelty
as a diagnostic and retain uncertainty methods as experimental until validated.
Full production infrastructure and prospective lab validation remain ahead.

[Protocol and technical sources](RELIABILITY_PROTOCOL.md) ·
[Roadmap](../ROADMAP.md) · Full local report: `artifacts/reliability-v1/REPORT.md`.
