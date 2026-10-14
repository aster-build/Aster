# Local campaign workflow

This milestone turns the tested Morgan/ridge reference into a persistent two-round
workflow. It is a local research tool, not a deployed dashboard or a new model
performance result. No cloud service, GPU, or additional dependency is needed.

## Data contract

A campaign contains **one coherent assay and one endpoint**, with higher values
preferred. Specify `pKi` or `pIC50` explicitly. Supply already transformed values
(`-log10` of a molar concentration); this interface does not guess units or convert
raw nM/uM concentrations. Do not combine Ki and IC50, different assay conditions,
or unrelated targets. The assay identifier records the user's declaration; the
software cannot establish experimental compatibility from a numeric CSV.

Measured CSV: exactly `compound_id,smiles,value`, at least 32 distinct compounds.
Candidate CSV: exactly `compound_id,smiles`, with **no outcome column**. For example:

```csv
compound_id,smiles,value
measured-001,CCO,5.2
```

```csv
compound_id,smiles
candidate-001,CCN
```

The small examples show column format, not sufficient training data. IDs are strings;
leading zeroes are preserved. UTF-8 and UTF-8 with BOM are accepted. Duplicate IDs,
duplicate molecular identities across either file, invalid structures, disconnected
mixtures, missing/nonfinite measurements, and censored measurements such as `>8`
are rejected before campaign creation. Rejection is all-or-nothing: no silent row
removal or replicate averaging. RDKit retains stereochemistry and charge; no salt
stripping or tautomer merging occurs. Numeric values are not proof of assay QC.

## Run a campaign

Run commands from the repository with its existing environment:

```sh
.venv/bin/python -m aster.campaign --db artifacts/my-campaign.sqlite create \
  --name 'My campaign' --assay 'my-single-assay-id' --endpoint pKi \
  --measured measured.csv --candidates candidates.csv

# Optional constraints, applied before proposing. IDs must exist in the candidate file.
.venv/bin/python -m aster.campaign --db artifacts/my-campaign.sqlite constrain locked candidate-001
.venv/bin/python -m aster.campaign --db artifacts/my-campaign.sqlite constrain excluded candidate-002

.venv/bin/python -m aster.campaign --db artifacts/my-campaign.sqlite propose
.venv/bin/python -m aster.campaign --db artifacts/my-campaign.sqlite export \
  --round 1 --output round-1-recommendations.csv
.venv/bin/python -m aster.campaign --db artifacts/my-campaign.sqlite export \
  --round 1 --template --output round-1-results.csv
```

Default batch size is eight; `propose --batch-size N` explicitly changes the budget.
Locked compounds consume slots and are marked `user_locked`. Excluded compounds
cannot be selected. Set a candidate's constraint back to `available` to clear a lock
or exclusion before selection. An excessive number of locks or insufficient
eligible candidates produces an error without saving a partial batch.

Fill the results template with `status=measured` and an exact numeric `value`, or
`status=failed` and an empty value:

```csv
compound_id,status,value
candidate-001,measured,6.4
candidate-003,failed,
```

```sh
.venv/bin/python -m aster.campaign --db artifacts/my-campaign.sqlite import-results \
  --round 1 --csv round-1-results.csv
.venv/bin/python -m aster.campaign --db artifacts/my-campaign.sqlite status
.venv/bin/python -m aster.campaign --db artifacts/my-campaign.sqlite propose
.venv/bin/python -m aster.campaign --db artifacts/my-campaign.sqlite export \
  --round 2 --output round-2-recommendations.csv
.venv/bin/python -m aster.campaign --db artifacts/my-campaign.sqlite snapshot \
  --output campaign-snapshot.json
```

Result files may contain a subset of the batch. A new round is blocked until each
pending assay is recorded as measured or failed. Failed compounds are not fitted
or selected again. Exact repeated imports are no-ops; conflicting values and
results for compounds outside that round are rejected atomically. This version
does not correct finalized measurements, reopen failed assays, or append new
candidate libraries; preserve the original campaign and create a reviewed new
campaign when those changes are needed.

## Decisions and evidence

Each round fits standardized Morgan fingerprints (radius 2, 2,048 bits, chirality)
with ridge alpha 10 on measured compounds only. It fills remaining batch slots by
descending prediction, breaking exact ties by compound ID. The recipe is the
provisional reference from the research milestones; no neural training occurs.

The export includes prediction in the declared endpoint, selection reason,
nearest measured compound and its observed value, and Morgan Tanimoto similarity.
A prediction outside `[0,14]` is flagged as a diagnostic; it is not clipped or
silently removed. This range is a review aid, not a universal validity boundary.
Similarity is evidence of chemical proximity, **not calibrated confidence**. The
workflow does not present bootstrap spread or residual bands as confidence scores.
The nearest neighbour is drawn only from measurements available at decision time.

## Persistence and recovery

A SQLite database contains the campaign definition, canonical structures, current
compound states, numbered events, and all round snapshots. Each round records its
training data/hash, eligible candidate IDs, constraints, package/source hashes,
recipe, recommendations, results, and fitted coefficients/intercept. The saved
linear model predicts from raw Morgan bits without loading a Python pickle.
Source hashes identify code; they are not archived source files, so preserve the
corresponding repository version and dependency lock files alongside the database.

Database write transactions serialize competing proposal requests; only one can
commit while a batch is pending. Fit or validation failures roll back changes.
If a command's response is lost, use `status` and `export` to recover the saved
batch. Do not request another batch to retry an export. Identical result imports
are safe to retry even after completion. Existing database/export paths are never
overwritten. Export failure leaves the saved campaign available for another export.
CSV exports preserve exact machine-readable strings for round trips.

This is a single-user local store, without authentication, background jobs, or
production access controls. It holds full training data; snapshots contain the
same data. Large-library performance has not been established: scoring is chunked,
but ridge fitting and the campaign record still live in memory.

## Verified public-data demonstration

```sh
.venv/bin/python scripts/demo_campaign.py
# Choose a fresh destination to repeat without overwriting artifacts:
.venv/bin/python scripts/demo_campaign.py --output artifacts/campaign-demo-repeat
.venv/bin/python -m pytest -q
```

The demonstration needs the existing, SHA256-pinned curated
`artifacts/reliability-v1-prepared/CHEMBL238_Ki.csv`. It uses the same revision-pinned
[MoleculeACE data](https://github.com/molML/MoleculeACE/tree/7e6de0bd2968c56589c580f2a397f01c531ede26)
as the completed research milestone. It selects 32 initial observations and 128
candidates only from the published Train partition, excludes one candidate, and
locks another. A separate demo driver supplies outcomes from the public dataset
only after each CLI recommendation is committed and exported.

Both batches contain eight unique picks; training counts are 32 and 40, ending
with 48 measurements. The published Test partition is not used. Import retries
add zero duplicate records. This is verification on already inspected data, not
another blind evaluation or prospective experiment. The demo driver can read the
source outcomes; the separation is procedural, not an adversarial security boundary.

Artifacts: `artifacts/campaign-demo-v1/REPORT.md`, `commands.json`, `manifest.json`,
`campaign.sqlite`, `snapshot.json`, and per-round recommendation/result CSVs.
Fifteen new tests cover lifecycle, saved-model recovery, constraints, duplicate and
invalid input rejection, partial/failed assays, idempotency, conflicts, concurrency,
fit failure rollback/retry, and stable selection under reordered candidate input.

## Next integration slice

Connect these operations to a dashboard: import preview, campaign status, batch
review with neighbour evidence, result upload, and the second round. Add a job
boundary and explicit human review state before supporting a shared deployed
service. Review the workflow with a discovery scientist before broadening assay
handling or promoting another acquisition policy.
