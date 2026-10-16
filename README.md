# Aster

A reproducible scientific backend for choosing which compounds to test next.
The research milestones compare molecular predictors and batch-selection policies.
A local campaign workflow now supports CSV imports, saved Morgan/ridge proposals,
constraints, result imports, and subsequent rounds.
The workspace app in `apps/web/` connects to the Python campaign backend at
`/dashboard`; `/` redirects there. The landing page belongs exclusively to the
separate `../aster-hero` repository and site.

<img width="2659" height="1674" alt="aster-3d-docking" src="https://github.com/user-attachments/assets/636a7ff1-9cd9-4f7a-a13e-c4e5fe115730" />


## Open the connected dashboard

```sh
.venv/bin/python -m pip install -e '.[web]'
npm --prefix apps/web ci
.venv/bin/python scripts/dev_dashboard.py
```

Open **http://127.0.0.1:3000/dashboard**. Start a public-data replay or import
measurement/candidate CSVs, preview and commit a batch, then import its outcomes.
See [setup, architecture, and verification](docs/DASHBOARD.md).

**Folder distinction:** the repository is named `aster`; its inner `aster/` directory
is the Python backend package. `apps/web/` is the Next.js frontend.

## Use the campaign workflow

A persistent local campaign, using greedy Morgan + ridge as the provisional default.
See [the workflow guide](docs/CAMPAIGN_WORKFLOW.md) for CSV schemas, commands,
constraints, and recovery behavior.

A campaign declares its own endpoint: any endpoint name, its unit, and whether larger
or smaller measurements are better. One exact number per compound, one assay per
campaign. Ranking, exports and the stored rounds follow that declaration.

```sh
.venv/bin/python -m aster.campaign --db campaign.sqlite create \
  --name "Microsomal stability" --assay "HLM clearance" \
  --endpoint clearance --unit "mL/min/kg" --direction lower_is_better \
  --measured measured.csv --candidates candidates.csv
```

## Ask why a compound was tested

Every pick is readable afterwards as a decision joined to its basis and its outcome:
the rank it held in the full ranked slate, the policy that produced the batch, the
prediction, the nearest measured analog at the time, the training snapshot hash and
model version behind it, the measured result, and whether it beat the best value known
when the pick was made.

```sh
.venv/bin/python -m aster.decisions --db campaign.sqlite why COMPOUND_ID
.venv/bin/python -m aster.decisions --db campaign.sqlite review
```

See [the decision record](docs/DECISION_RECORD.md) for the fields, the HTTP endpoints
and the limits of what `review` can claim.

```sh
.venv/bin/python -m aster.campaign --help
.venv/bin/python scripts/demo_campaign.py
```

The demo uses the already prepared public dataset and writes a fresh directory at
`artifacts/campaign-demo-v1`. It verifies two batches of eight, with 32 → 40 → 48
measurements, without treating the workflow check as a new model-quality result.
The connected dashboard is now implemented in `apps/web/`; see the guide below.

## Run it

Tested with Python 3.12.5 on macOS arm64. Use Python 3.12 for the captured dependency set.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python -m aster run
```

The command downloads only the 123 KB potency file and source metadata if missing,
verifies the pinned file checksum, curates measurements, and runs the full experiment.
Internet is needed for installation and the first fetch; reruns use the verified local cache.
No cloud account or GPU is required. The supplied lock file captures the environment
used for the reported run; different operating systems may need compatible wheel versions.

Defaults: 100 initially observed compounds, five rounds of eight selections,
ten paired seeds (0–9), a 200-tree random forest, and pIC50 ≥ 6 as the hit threshold.
That threshold means IC50 ≤ 1 µM; it is a benchmark convention, not drug viability.

Outputs appear in `artifacts/baseline/`, including:

- `REPORT.md` and `discovery_curves.png`: results and limitations.
- `selections.csv`: all recommendations with predictions made before outcomes were revealed.
- `round_metrics.csv` and `audit_predictions.csv`: discovery and prediction performance.
- `splits.json`, `config.json`, `environment.json`, `manifest.json`: reproducibility records.
- `qc_rows.csv`, `qc_summary.json`, `curated.csv`: source-row curation and exclusions.
- `seed0_greedy_model.joblib`, `seed0_random_model.joblib`: final models for the first configured seed.
- `seed0_greedy_remaining.csv`: predictions for that greedy run's still-unmeasured candidates.
- `artifact_checksums.json`: output integrity checks.

Existing output directories are never overwritten. For another run:

```sh
.venv/bin/python -m aster run --output artifacts/reproduction
```

For a quick smoke run (not comparable to the full ten-seed result):

```sh
.venv/bin/python -m aster run --seeds 0 --trees 20 --output artifacts/smoke
```

Use `--help` for options. Changing initial size, budget, threshold or model settings
creates a different experiment; do not choose them after inspecting test outcomes
and describe the result as a blind evaluation.

## What is implemented

1. **Data acquisition:** pinned Zenodo v2 source and MD5 verification; source metadata and SHA256 recorded.
2. **Curation:** RDKit CXSMILES validation, structure canonicalization, missing-label exclusion,
   mixture rejection and conservative removal of all duplicate identity rows.
3. **Features/model:** chirality-aware Morgan fingerprints (radius 2, 2,048 bits) and a random forest.
4. **Replay:** select the highest predicted potency or a random batch, reveal only its measurements,
   refit on accumulated observations, and repeat.
5. **Audit:** predict the untouched published Test partition and score it after the replay completes.
6. **Reporting:** per-seed records, paired comparison, fitted models and static plots.

The experiment uses the published **Train** partition for initial support and hidden
acquisition candidates. The published **Test** partition is never acquired or used for
fitting, tuning, selection, or stopping. The two policies start from identical initial
measurements for each seed. Initial support hits do not count toward newly discovered hits.

“Hidden labels” is an evaluation technique, not content withheld from the user. All
public measurements remain inspectable in local source/audit files. The oracle is an
in-process API boundary, not a security sandbox against arbitrary code.

## First completed run

The pinned source contains 1,328 rows. This target has 223 missing measurements.
Conservative duplicate removal excludes another 183 measured rows, leaving **712 Train
and 210 Test compounds**. Duplicate groups are excluded wholesale rather than averaging
potentially conflicting records or moving compounds across the published split.

| After 40 additional assays, averaged over 10 seeds | Highest predicted potency | Random selection |
| --- | ---: | ---: |
| Additional hits (pIC50 ≥ 6) | 36.0 | 8.7 |
| Final audit MAE, pIC50 units | 0.793 | 0.748 |
| Final audit RMSE, pIC50 units | 0.970 | 0.912 |

Mean paired discovery gain: **27.3 hits**; descriptive bootstrap interval across seeds:
**25.3–29.1**. Greedy selection recovered more hits in all ten paired runs. This interval
captures initialization variability on this dataset, not evidence across independent targets.

Random selection gave slightly better average audit prediction error. Finding active
compounds and improving global prediction accuracy are distinct objectives.

This is a **single-target retrospective case study**, not evidence of discovering drugs
or generalizing to arbitrary chemistry. Existing measured pools have selection bias;
published splits can share chemical series. No uncertainty calibration, deep learning,
or prospective laboratory experiment is included yet. Source numeric values lack explicit
censoring and replicate flags; assay floors may therefore affect regression.

## Validate

```sh
.venv/bin/python -m pytest -q
```

The initial suite has 11 tests covering duplicate/split leakage, stereo-sensitive features,
missing and non-numeric outcomes, oracle access, policy independence from hidden labels,
budget accounting, reproducibility of selection, and a complete offline synthetic-fixture run.
Synthetic fixtures test code behavior; the reported results above use the real downloaded data.

## Broader evaluation completed

The broader evaluation and frozen-model comparison are now implemented. See
[the broader evaluation guide](docs/BROADER_EVALUATION.md) for the fixed protocols,
neural environment, exact commands and interpretation. The new report is generated
at `artifacts/broader-v2/REPORT.md`; the original result above is preserved.

All 144 replays completed. In the two evaluation tasks, mean strongest-decile recovery
was 11.29/40 for the random forest, 12.75 for Morgan/ridge, and 11.38 for frozen
CheMeleon/ridge. The frozen head also had unstable prediction errors. See
[the result interpretation](docs/BROADER_RESULTS.md); these are descriptive results
on a small, partially overlapping target suite, not proof of general superiority.

## Stable heads and new-target transfer

The next milestone is implemented in `aster.steady`, `aster.transfer`, and
`aster.adaptation`. See [the protocol](docs/STABILITY_PROTOCOL.md).
A six-head development comparison selected training-only removal of near-constant
features followed by standardized ridge. No predictions are clipped.

Across 96 new-target replays the repaired frozen model stayed inside the numerical
guard but recovered 15.50 strongest-decile compounds per 40 picks, versus 17.33
for Morgan/random forest and 18.67 for Morgan/ridge. The latter remains a
provisional reference, not a universal winner. The matched six-case local CPU
fine-tuning pilot also completed: 13.67 discoveries versus 15.33 for frozen
CheMeleon and 17.33 for Morgan/ridge on those same cases. This adaptation recipe
showed no advantage. See [the findings](docs/STABILITY_RESULTS.md) and the full
`artifacts/transfer-tuned-v1/REPORT.md`.

Use `requirements-neural.lock.txt` for these experiments. The 28-test suite also
checks stable-head behavior and deterministic encoder updates (the neural test
skips if the optional package or local checkpoint is unavailable). The original
baseline and broader-v2 artifacts remain unchanged. Inspected evaluation results
are no longer fresh blind benchmarks for future recipe selection.

See [ROADMAP.md](ROADMAP.md) for the architecture, fine-tuning plan and later product integration.

## Reliability-aware selection and milestone posters

The first policy/reliability comparison is complete: 252 validated replays and
34 passing tests. The frozen exploration policy found 14.17 top-decile compounds
per 40 picks versus greedy Morgan/ridge 14.29 on three fresh targets. Bootstrap
disagreement did not reliably identify larger errors; chemical novelty had only
modest diagnostic value. Keep greedy as the provisional default.

See [findings](docs/RELIABILITY_RESULTS.md), [protocol and commands](docs/RELIABILITY_PROTOCOL.md),
and `artifacts/reliability-v1/REPORT.md`. Historical selection explanations are in
`artifacts/reliability-v1/recommendation_trace.csv`.

Four milestone posters (high-resolution PNG and scalable SVG), a current-workflow
illustration, source references, and generation prompts are in
[the poster gallery](output/posters/index.html). Rebuild the data-driven posters with:

```sh
MPLCONFIGDIR=.mplconfig .venv/bin/python scripts/build_milestone_posters.py
```

The latest approach is reliability-aware experiment selection; neural fine-tuning
was the preceding milestone. A thin campaign/dashboard workflow is next.

## Does external evidence improve selection?

Not the evidence we can get. Milestone 9 compared campaign-only selection against
literature-augmented selection and an information-matched control whose evidence values
were scrambled, over 120 paired replays on the dopamine transporter. The predeclared gate
failed: a gain of 0.40 top-decile compounds per 40 picks against a required 1.0, and 0.20
of that reproduced by the scrambled control. Repeated with four times the seeds, that gain
falls to 0.03.

A retest on nine targets then swept the one thing milestone 9 could not control, how much
evidence there was, by withholding measurements from the replay task and handing them back
as evidence. Over 864 paired cases, 12 supplied structures change nothing, 50 are worth
+1.2 to +2.3 top-decile compounds per 40 picks and 150 are worth +1.6 to +2.8. So supply
was the limit, not the idea. But a sensitivity run settles it the other way: perturbing
those values by the disagreement a literature corpus carries between sources, about 0.68
log units, removes the gain and makes it negative, while single-laboratory precision
(0.29) keeps about two thirds of it.

Evidence therefore stays attached to decisions for a human to read, and out of the
ranking. Ranking-grade evidence would mean 50 or more measurements of pool-external
structures at one laboratory's precision, which is a collaborator's assay history rather
than a public corpus. Design, leakage rules and full numbers:
[EVIDENCE_RETEST.md](docs/EVIDENCE_RETEST.md), with the original study at
[EVIDENCE_SELECTION.md](docs/EVIDENCE_SELECTION.md).

## Source and attribution

Scheen, J., MacDermott-Opeskin, H., Chodera, J., et al. (2025).
*ASAP-Polaris-OpenADMET blind challenge data*, version 2.
[DOI: 10.5281/zenodo.15582067](https://doi.org/10.5281/zenodo.15582067).
Dataset license: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Full creator metadata is saved alongside results. The curated output is a filtered,
canonicalized derivative of the published potency table; modifications are recorded in QC artifacts.

Scientific software: [RDKit](https://github.com/rdkit/rdkit) and
[scikit-learn](https://scikit-learn.org/stable/). Neural comparison:
[Chemprop](https://github.com/chemprop/chemprop) and [CheMeleon](https://github.com/chrissly31415/chemeleon).

## Planned prototype extensions

The existing prototype is now connected locally to this backend.
The [extension plan](docs/PRODUCT_EXTENSIONS.md) scopes later 3D protein–ligand
evidence, compound-aware literature retrieval, and a controlled experiment to test
whether external evidence improves selection. Structural replay and exploratory docking
are now implemented locally as described below; literature retrieval and the
controlled selection study remain proposed.

### Molecular evidence replay

Open [the local replay](http://127.0.0.1:3000/replay) after starting the dashboard services. Explore the experimental DAT reference structure and replay saved campaign decisions. See [scope, provenance, and verification](docs/MOLECULAR_REPLAY.md).

### Exploratory docking

The dashboard inspector links to user-triggered DAT docking and 3D candidate/reference comparison. Five-seed redocking passed 4/5; cross-docking is untested and protein-only scoring omits ions. See [docking results and setup](docs/DOCKING.md).

### Literature evidence retrieval — local workflow implemented

Select a compound in the DAT demo to search exact-compound, analog, or general
target evidence. The bounded corpus has 42 machine-audited source records from 15
documents. Inspect citations and save evidence to a committed round without changing
its predictions. Independent scientific review is still pending; milestone 8 is
not yet complete.

```sh
.venv/bin/python scripts/fetch_literature_sources.py
.venv/bin/python scripts/build_literature_corpus.py
.venv/bin/python scripts/evaluate_literature.py
.venv/bin/python scripts/build_literature_review.py
```

See [setup, API, results and limits](docs/LITERATURE_EVIDENCE.md) and the
[independent review pack](output/literature-review/index.html).
