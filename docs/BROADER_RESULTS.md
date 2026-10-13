# Broader evaluation: first completed comparison

All **144/144 planned replays** completed locally. No paid GPU compute or encoder
fine-tuning was used. Fifteen tests passed; all 144 run records additionally passed
checks for acquisition/audit separation, unique selections, final training budget,
hit accounting and finite predictions. Frozen embeddings matched the official
CheMeleon fingerprint path exactly in a two-molecule implementation check.

## Main result

The frozen CheMeleon + fixed ridge head did **not demonstrate a clear overall
advantage** over the random-forest baseline in this small suite. It recovered
roughly the same number of strongest-decile compounds, with gains and losses
depending on the target and split. The matched fingerprint/ridge arm had the
highest mean strongest-decile recovery of the four arms.

The following numbers average the 24 evaluation cases equally (two targets × two
split protocols × two support sizes × three seeds). They exclude development.
These are descriptive averages, not a statistically independent 24-task study.

| Arm | Top-decile compounds found among 40 picks | Absolute pKi ≥ 7 hits | Audit MAE |
| --- | ---: | ---: | ---: |
| Random selection | 3.42 | 24.71 | 0.721 |
| Morgan + random forest | 11.29 | 35.54 | 0.784 |
| Morgan + ridge | 12.75 | 36.75 | 0.780 |
| Frozen CheMeleon + ridge | 11.38 | 32.29 | 5.596 |

CheMeleon recovered more top-decile compounds than the forest in 14 paired cases,
tied in two and recovered fewer in eight. Its average advantage was only **0.08
compounds per 40 picks** because some losses were larger than its wins. Do not
interpret a win count alone as clear superiority.

## Where the harder protocol matters

These rows average the two support sizes and three seeds separately for each target:

| Target | Split protocol | Random | Morgan RF | Morgan ridge | CheMeleon ridge |
| --- | --- | ---: | ---: | ---: | ---: |
| CHEMBL1871_Ki | Published | 3.50 | 13.67 | 12.33 | 13.17 |
| CHEMBL1871_Ki | Scaffold transfer | 3.00 | 7.17 | 7.00 | 9.50 |
| CHEMBL2034_Ki | Published | 4.17 | 14.33 | 17.50 | 13.83 |
| CHEMBL2034_Ki | Scaffold transfer | 3.00 | 10.00 | 14.17 | 9.00 |

Values are top-decile compounds recovered, not absolute hits. Different split
protocols change the pool as well as its familiarity, so these are stress-test
comparisons rather than a controlled causal estimate of scaffold novelty alone.

## The unstable-head finding

The large CheMeleon audit error is real in this fixed configuration and is retained
in the report. It is not grounds for concluding that the pretrained encoder is
generally poor. Some predictions were extreme; **this configuration should not be
promoted to the dashboard as a reliable potency predictor**.

A post-hoc diagnostic used only the development task (case
`CHEMBL1862_Ki__published__n32__s2`). At the final round:

- The maximum absolute standardized training feature was about 8.43.
- The maximum absolute standardized audit feature was about 138,914.
- One feature's nonzero training scale was only about 0.00000141.
- Predictions ranged from approximately −1,116 to 11.19 pKi.

This supports feature extrapolation after training-only standardization as a
plausible cause of the instability. It is a diagnostic hypothesis, not a completed
causal ablation. We did not clip predictions, drop failed seeds, retune the head,
or replace unfavorable results after viewing the evaluation outcomes.

## Decision and next work

Keep the fingerprint models as the practical reference. Before full encoder
fine-tuning, compare more stable frozen heads on development data: centering-only
ridge, training-fitted variance filtering, stronger regularization, or a nonlinear
head. Use matched fingerprint-head controls. Evaluate whether stability improves
without merely trading away discovery performance.

Then freeze a bounded fine-tuning recipe and broaden to additional dissimilar
targets. The two evaluation targets here share 133 structures; these results do
not establish generalization across drug discovery. Future iterations must disclose
that this suite has been inspected, and should reserve new tasks for fresh testing.

## Files

Full results: `artifacts/broader-v2/REPORT.md`, `comparison.png`,
`round_metrics.csv`, `paired_differences.csv`, `coverage.json`, `validation.json`
and `development_diagnostic.json`. Individual replay JSON files retain all choices
and outcomes. The [protocol and reproduction guide](BROADER_EVALUATION.md)
documents the dataset/checkpoint provenance and model settings.
