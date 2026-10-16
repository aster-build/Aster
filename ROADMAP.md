# Aster roadmap

Updated: 2026-10-16. Status: baseline, broader evaluation, and stable-head transfer evaluation completed; bounded encoder fine-tuning and reliability-aware selection pilots completed. A local campaign workflow is completed; the existing prototype is now integrated locally; the first 3D structural evidence, decision replay, and exploratory user-triggered docking are implemented. Independent docking transfer validation and expanded structural analysis remain proposed below. The controlled evidence-augmented selection study (milestone 9, first hypothesis) has now been run on one target and returned a null result: evidence augmentation did not meet its predeclared gate, so evidence stays out of the ranking. Milestone 8 has a working local literature workflow and machine-audited pilot corpus; independent scientific review remains unfinished.

### Direction A — the decision record (2026-10-16)

The product bet that milestone 9's null result supports: make Aster the system of record
for experimental decisions, for any endpoint and any assay, with one number per compound.

- [x] An endpoint is declared per campaign — name, unit, and whether higher or lower is
  better — instead of a hard-coded choice between two potency scales. Ranking, exports,
  stored rounds and the API follow the declaration; campaigns created before it still load.
- [x] The extrapolation diagnostic is no longer potency-specific: a prediction is flagged
  against the campaign's measured range extended by one standard deviation, and each round
  stores the range it used.
- [x] Each round stores the **full ranked slate** with every prediction and whether it was
  selected, plus the policy, locks and exclusions in force, so the record shows what was
  rejected and not only what was picked.
- [x] `aster.decisions` answers "why did we test this, and were we right?" for a compound,
  and `review` reports how the picks turned out, both over the CLI and at
  `/campaigns/{id}/decisions`. Every number is read from what was stored at decision time.
- [x] A pick with no result reads `awaiting_result` and a failed assay reads `no_result`;
  neither is silently scored. Compounds never picked are explained, not invented.
- [ ] **Censored values are still unsupported.** An assay reporting ">10 µM" cannot be
  recorded faithfully, so that is the next gap in the data model.
- [ ] Provenance class per value, and a review of the record by a discovery scientist.

See [DECISION_RECORD.md](docs/DECISION_RECORD.md). `review` reports only measured picks:
rejected candidates were never measured, so the record cannot claim a different batch
would have been worse.

### Milestone 9 — evidence-augmented selection tested; result is null (2026-10-16)

- [x] Predeclare the study, hypotheses, metrics and promotion gate in
  [configs/evidence-v1.json](configs/evidence-v1.json), frozen by hash before the run.
- [x] Enforce strict replay in code: an external record is used only if its canonical
  isomeric SMILES appears nowhere in the replay dataset, and the run aborts if a
  permitted record matches a pool or audit compound.
- [x] Run the first hypothesis on the dopamine transporter (`CHEMBL238_Ki`): baseline,
  literature-augmented and an information-matched irrelevant-evidence control, over
  2 protocols × 2 support sizes × 10 paired seeds = 120 replays.
- [x] **Result: the gate fails.** Literature augmentation gained **+0.40** top-decile
  compounds per 40 picks (standard error 0.33) against a required 1.0, and the
  scrambled-value control reproduced +0.20 of that, against a required separation of
  1.0. Secondary metrics did not support a benefit either (−0.45 hits above the 7.0 pKi
  threshold; audit MAE improved by 0.004). **Evidence stays out of the ranking.**
- [x] Record the supply limit found by the leakage filter: of 31 usable corpus
  structures, 19 are already in the replay dataset and only 12 are permitted. A corpus
  built from the same source as the replay data mostly re-supplies it.
- [ ] Structural and combined arms are **not run**: docking covers one pocket of one
  structure for verified demo compounds, so no pose or contact descriptor exists for the
  replay pool. Learned retrieval stays deferred behind a demonstrated frozen-retrieval gain.
- [ ] Three declared rules remain unmet and are limitations, not controls: no temporal
  cutoff (the replay dataset has no measurement dates), no independent review (all 31
  structures are machine-audited, zero human-reviewed), and one target with one endpoint.

See [EVIDENCE_SELECTION.md](docs/EVIDENCE_SELECTION.md) for the design, the leakage
handling and the full numbers. This is a null result on one target with twelve permitted
compounds: it does not establish that literature evidence cannot help selection, only
that this corpus at this size does not move this selector.

### Milestone 8 — local literature workflow implemented; independent review pending (2026-10-14)

- [x] Validated corpus importer, isolated SQLite FTS5 index, snapshot hashes,
  source downloads and read-only search API.
- [x] Screen 100 Europe PMC metadata records and 100 ChEMBL activities. Retain
  eight permitted article abstracts and 34 direct-target measurements across 15
  documents. All source audits are explicitly machine-labelled.
- [x] Add exact-compound, analog and target-context evidence cards; endpoint,
  evidence-type and date filters; source citations; explicit no-evidence states.
- [x] Resolve explicit DOI/PMID/PMCID aliases; flag same-assay measurement
  disagreements without pooling different assays, endpoints or units.
- [x] Save immutable evidence results to committed rounds without changing
  campaign state; clearly label attachment after selection.
- [x] Run 50 machine-authored engineering questions: lexical and character-TF-IDF
  hybrid recall@10 1.00, 8/8 abstentions, 42/42 source-fidelity checks. Keep keyword
  search as default. These are not independent or blind scientific results.
- [x] Verify 76 Python tests, production build/TypeScript, targeted frontend lint,
  desktop/mobile source cards, saved-record reload and unchanged campaign state.
- [ ] Complete independently reviewed questions and document/chemical-series-separated
  development/test evaluation. The review pack is prepared, with all decisions pending.
- [ ] Expand beyond the 15-document pilot where the review identifies coverage gaps;
  evaluate neural retrieval/PaperQA on the reviewed benchmark before promotion.

See [LITERATURE_EVIDENCE.md](docs/LITERATURE_EVIDENCE.md),
[the evaluation protocol](docs/LITERATURE_EVALUATION_PROTOCOL.md), and
[the independent review pack](output/literature-review/index.html).
**Milestone 8 is not marked complete:** the roadmap's independent review gate is
still unmet. Milestone 7B docking transfer validation remains separately unfinished.

### Milestone 7B — exploratory docking implemented locally (2026-10-14)

- [x] Predeclare and execute five-seed native-ligand redocking: **4/5 top-1 poses <2 Å with physical checks passing**. Seed 71 failed pose recovery; best top-5 was 1.01 Å. Native reference passed physical checks.
- [x] Record preparation limitations: protein-only scoring; ions/glycans excluded, retained in physical validation; all protein heavy-atom coordinates preserved.
- [x] User-triggered, bounded and persisted local docking jobs for verified DAT demo compounds; explicit errors for unspecified stereochemistry or unsupported preparation.
- [x] Candidate/reference 3D overlay, alternative poses, failed-pose rejection, shared/new geometric contacts, downloadable validation/provenance. Campaign rankings remain unchanged.
- [ ] Independent cross-docking on additional compatible DAT structures.
- [ ] Ion-aware preparation and predeclared protonation/tautomer sensitivity studies.
- [ ] Evaluate whether structural evidence improves held-out compound selection; no affinity or selection benefit established yet.

See [DOCKING.md](docs/DOCKING.md) for results, controls, architecture and reproducibility. This is an exploratory visualization milestone, not completed docking generalization validation.

### Milestone 7A — first molecular evidence replay implemented (2026-10-14)

Implemented locally at `/replay`; see [MOLECULAR_REPLAY.md](docs/MOLECULAR_REPLAY.md).
A 3D molecular workspace and synchronized campaign replay now precede RAG,
more model tuning, or molecular dynamics. Forepaw is a visual-layout reference only;
no robotics, dimOS, or robot-planning functionality is in scope.

- [x] First verify one experimental protein–ligand complex and its relationship to
  the campaign. Human dopamine-transporter entry [8Y2G](https://www.rcsb.org/structure/8Y2G)
  is the verified experimental reference. Exact isomeric-SMILES comparison found no
  matches among the 160 demo compounds; it is not a candidate bound pose.
- [x] Make a central Mol* scene with protein overview, pocket close-up, ligand and
  residue/contact highlighting. Camera tours and staged highlights explain a static
  structure; label any illustrative motion, never represent it as observed binding.
- [x] Surround the scene with resizable/collapsible panels: structure provenance and
  nearby residues on the left; input measurements, selected compound, ranking and
  measured analog evidence on the right; campaign timeline and predicted-versus-observed results below.
- [x] Implement Play / Pause / Step / Restart across saved events:
  measurements → model fit → candidate scoring → batch selection → outcome reveal
  → refit. Replay actual round artifacts; show rankings across rounds and before/after prediction changes
  where stored. Mark missing historical scores as unavailable rather than inventing them.
- [x] Label the current learner Morgan + ridge. Separate structure context from
  features actually used by the model. Show the saved fit recipe and feature count; detailed fragment attribution
  remains deferred until numerical checks and collision handling are implemented. Neural-training replay
  is later and must use real saved neural run artifacts.
- [x] Keep structure and campaign timelines distinct: an experimental complex is
  a structural snapshot, not a time-resolved binding trajectory. Missing exact poses
  show an explicit unavailable state or a clearly labelled reference analog.

Architecture: existing Next.js/React shell + client-only Mol*; Next.js serves pinned
mmCIF assets and provenance; FastAPI serves recorded campaign artifacts; SQLite/local artifacts store
replay manifests. RDKit handles molecular identity; PLIP is deferred; this first version uses explicitly labelled ≤4 Å heavy-atom
proximity with verified atom mappings. No GPU training is required for this first viewer.

Exit gate: one verified reference complex, synchronized compound/residue selection,
two replayed campaign rounds with outputs matching saved records, source/type labels,
responsive panels, and a non-WebGL fallback. Docking is now available as exploratory milestone 7B above;
actual molecular-dynamics trajectories are a separate later extension, not required
for the initial animated walkthrough. Literature RAG follows this milestone.

Validation: production build/TypeScript and 56 Python tests passed. The first
implementation uses a static experimental complex, camera animation, and recorded
round replay; milestone 7B adds docking separately. Dynamics and neural optimization playback remain unimplemented.

### Implementation update — first milestone completed

The original plan below is retained for reference. A Python baseline now runs with
`python -m aster run`; setup and results are in [README.md](README.md).
The landing-page source has been identified separately at `../aster-hero`.
Real ASAP potency curation, Morgan fingerprints, a random forest, five eight-compound
selection rounds, ten paired seeds, audit predictions and a report are implemented.
After QC, the experiment uses 712 published Train compounds and 210 published Test
compounds. Greedy selection recovered 36.0 additional hits on average versus 8.7 for
random selection; random selection had slightly better final audit MAE (0.748 versus
0.793). This is retrospective single-target evidence, not prospective validation.
Eleven tests passed at that milestone. Neural fine-tuning was subsequently completed
in the bounded pilot below; uncertainty-aware selection and dashboard integration remain planned. The report is generated at `artifacts/baseline/REPORT.md`.

### Second milestone — evaluation before added model complexity

Following the “Explain baseline report” discussion, the next implementation is a
broader evaluation followed by frozen CheMeleon comparison. See
[the detailed protocol](docs/BROADER_EVALUATION.md).

- [x] Preserve the original antiviral baseline and artifacts.
- [x] Add three revision-pinned MoleculeACE Ki tasks: CHEMBL1862 for development;
  CHEMBL1871 and CHEMBL2034 for evaluation. Do not treat these related/overlapping
  target datasets as independent evidence across all drug discovery.
- [x] Freeze starting-data sizes of 32 and 64, three paired seeds, and five batches of eight.
- [x] Add published-partition and scaffold-disjoint support/pool/audit protocols.
- [x] Add strongest-decile recovery to avoid the absolute-hit ceiling found on the
  development target. Protocol v2 was fixed before evaluation runs; retain the v1
  development experiment as exploratory history.
- [x] Implement matched Morgan/random-forest, random-selection, Morgan/ridge and
  frozen-CheMeleon/ridge arms, with training-only scaling and no audit tuning.
- [x] Add checkpoint and source checksums, cached embeddings, resumable run contracts,
  explicit coverage, paired differences, per-round records and comparison plots.
- [x] Test split isolation, endpoint conversions, hidden-label independence and
  training-only feature scaling. Verify embeddings against the official method.
- [x] Review all 144 completed replays. On the two evaluation tasks, frozen
  CheMeleon/ridge recovered 11.38 strongest-decile compounds per 40 picks versus
  11.29 for the forest and 12.75 for Morgan/ridge, averaged over matched cases.
  There is no clear overall frozen-model advantage in this small comparison.
- [x] Investigate the unstable frozen head on development data. Training-only
  standardization amplified rare feature variation into extreme audit features
  and predictions. Preserve the original result, including its failures.
- [x] Test stable frozen heads on development data before promoting a neural
  predictor or investing in encoder fine-tuning. See [results](docs/BROADER_RESULTS.md).
- [x] Run a bounded fine-tuning experiment after freezing its development-selected
  settings and defining genuinely additional evaluation tasks for further iteration.

The bounded local encoder fine-tuning pilot is now complete (third milestone below).
Broader adaptation studies, uncertainty-aware acquisition, dashboard integration
and prospective laboratory validation remain later milestones. No paid GPU was used.

### Third milestone — stability, then additional-target transfer

Protocol and reproducible commands: [STABILITY_PROTOCOL.md](docs/STABILITY_PROTOCOL.md).
Configs: `configs/stability-v1.json`, `configs/transfer-v1.json`.

- [x] Predeclare six head recipes and joint stability/discovery gates; run 108
  development replays with both Morgan references and random selection.
- [x] Freeze a training-only feature filter (standard deviation >=0.01), then
  standardization and ridge alpha 10. No prediction clipping. It eliminated
  development guard violations and found 14.83 strongest-decile compounds per
  40 picks, versus 10.33 for the unstable head and 15.17 for Morgan/ridge.
- [x] Evaluate the frozen recipe on three additional targets, two protocols,
  starting sizes 32/64 and two seeds: 96 replays. Exclude structures shared with
  all previously inspected targets, preserving exact source and split manifests.
- [x] Record the negative aggregate transfer result: frozen CheMeleon found
  15.50 strongest-decile compounds per 40 picks versus 17.33 for Morgan/RF and
  18.67 for Morgan/ridge. All predictions stayed inside the broad [0,14] guard;
  sensible-valued predictions do not guarantee useful selection.
- [x] Implement deterministic, observed-only encoder adaptation and pass a
  development runtime check. Fixed five-epoch schedule, local CPU, same final
  ridge policy, fresh foundation initialization each round.
- [x] Complete the predeclared six-case fine-tuning pilot (all three new targets,
  both protocols, 32 initial measurements, seed 0, the same 40-pick budget),
  validate its predictions and compare only matching frozen/Morgan cases.
  Fine-tuned CheMeleon found 13.67 strongest-decile compounds versus frozen 15.33,
  Morgan/RF 16.17 and Morgan/ridge 17.33. It tied frozen in four cases and lost
  in two; audit MAE was nearly unchanged (0.905 versus 0.904). Do not promote
  this adaptation recipe.
- [x] Validate all 210 main replays, pass 28 tests, preserve source snapshots and
  record paired results in [the milestone findings](docs/STABILITY_RESULTS.md).
  Full report: `artifacts/transfer-tuned-v1/REPORT.md`.
- [x] Add measured reliability beyond gross numerical guards: nearest-measured
  chemical similarity and uncertainty calibration, evaluated for actual failure
  detection under shift. A guard is not a confidence interval.
- [x] Test a decision policy that responds to unreliability or adds diversity,
  against Morgan/ridge, on newly reserved targets or prospective measurements.

Keep Morgan/ridge as the strongest provisional reference. These additional targets
are project-held-out, not guaranteed absent from foundation-model pretraining or
published model selection. Two of the new targets are kinases. Do not promote a
neural model from development performance or a single small adaptation pilot.
Do not tune further on these inspected evaluation outputs and call them blind.
The fourth milestone below completed this reliability-aware selection comparison. Its plan was:
use development data for policy design, reserve additional targets before checking
performance, and test whether uncertainty/diversity changes improve experimental
choices. Build the workflow using the reference model while that research proceeds.

### Fourth milestone — reliability-aware selection completed

Protocol: [RELIABILITY_PROTOCOL.md](docs/RELIABILITY_PROTOCOL.md).
Findings: [RELIABILITY_RESULTS.md](docs/RELIABILITY_RESULTS.md).

- [x] Predeclare seven policies, numerical/reliability checks and a practical
  discovery improvement gate. Preserve both Morgan references and random selection.
- [x] Add 16-member bootstrap disagreement, nearest-measured Tanimoto novelty,
  training-only cross-validation residual bands, and interpretable batch score traces.
- [x] Run 84 development replays. Freeze the exploration policy (mean +0.5×
  disagreement) before downloading three additional outcome datasets.
- [x] Run 168 fresh-target replays on dopamine transporter, sigma receptor 1 and
  PI3K alpha, excluding compounds shared with all six previously inspected tasks.
- [x] Validate all 252 replays; 34 software tests pass. No paid compute used.
- [x] Record the negative primary result: exploration 14.17 versus greedy 14.29
  strongest-decile discoveries per 40 picks. Keep greedy Morgan/ridge as default.
- [x] Record weak error detection: bootstrap disagreement AUC 0.477; novelty AUC
  0.610 under greedy. Approximate nominal-80% bands cover 72.5% of audit outcomes.
  Do not present ensemble spread as calibrated uncertainty.
- [x] Record the secondary diversity signal: 15.13 discoveries and 24.0 novel
  scaffolds versus greedy 14.29 and 20.7. The +0.83 discovery gain is below the
  predeclared +1 threshold; do not promote it from this secondary comparison.
- [x] Build a local campaign workflow: validated CSV import, a saved model/run,
  reproducible eight-compound proposal, exclusions/locked picks, export/import
  outcomes, and a second round.
- [x] Connect it to the local dashboard using the current reference model and honest
  reliability labels.
- [ ] Review that workflow with a discovery scientist. Reserve new targets or
  prospective measurements before testing any revised selection policy.

You are entering Phase 4 (product integration). The first policy/reliability
comparison and a local campaign workflow with locks/exclusions are complete.
Local dashboard integration and restart-aware preview jobs are complete.
Shared storage/authentication and distributed job infrastructure remain unfinished.
The [milestone poster gallery](output/posters/index.html) explains all four completed
scientific milestones, with PNG/SVG exports, sources and a current-workflow image.
These are retrospective research results, not clinical claims.

### Fifth milestone — local campaign lifecycle completed

[Workflow guide](docs/CAMPAIGN_WORKFLOW.md): `python -m aster.campaign`.

- [x] Define a single-assay campaign, molecule states, immutable round snapshots,
  fitted model records, and a transactional SQLite store with numbered events.
- [x] Validate measured/candidate CSVs; reject duplicate chemistry, invalid structures,
  nonfinite/censored values, and candidate outcome columns. Require explicit pKi or
  pIC50 values already on the molar logarithmic scale; do not guess units.
- [x] Generate batches of eight using Morgan/ridge, with locked and excluded compounds.
  Save predictions, selection reasons, and nearest observed-compound evidence.
- [x] Export batches, import partial or failed assay results, reject conflicting edits,
  support idempotent import retries, and refit the next round.
- [x] Verify two full CLI rounds on previously inspected public CHEMBL238 data:
  32 initial observations, 128 candidates, 16 unique picks, 48 final measurements.
  The published Test partition is unused; this is workflow verification, not a
  fresh scientific evaluation. See `artifacts/campaign-demo-v1/REPORT.md`.
- [x] Add 15 lifecycle/validation/concurrency/recovery tests; 49 total tests pass.
- [x] Connect the campaign operations to an import/review/results dashboard.
- [ ] Add distributed job infrastructure, authenticated shared access, and reviewed corrections
  before deployment or private lab data. Obtain domain feedback on the workflow.

No neural retraining, new acquisition-policy promotion, or paid compute was needed.
The prior four posters describe scientific results; this milestone adds workflow
infrastructure rather than another claim of discovery performance.

### Sixth milestone — connected local dashboard completed

Guide: [DASHBOARD.md](docs/DASHBOARD.md). Frontend: `apps/web/`. API: `aster/api.py`.

- [x] Import the existing landing-page design and add `/dashboard` using real campaign data.
- [x] Add FastAPI routes, persisted preview job states, one local model worker and restart recovery.
- [x] Separate preview from explicit commit; reject stale revisions and make commit retries idempotent.
- [x] Connect the candidate map, shortlist, RDKit molecule inspector, analog evidence,
  locks/exclusions, CSV campaign imports, batch exports, result imports and history.
- [x] Verify a browser replay of two eight-compound rounds: 32 → 40 → 48 measurements,
  plus reload persistence and a normal CSV campaign import. Inspect desktop/mobile layouts.
- [x] Pass 54 Python tests and the Next.js production/TypeScript build.
- [x] Review and refine the working prototype; add the first structural evidence replay.

This is a local prototype, not a public deployment or a new scientific benchmark.
The separate original `aster-hero` project and Vercel landing deployment are unchanged.

### Milestones 6–9 — integration status and proposed extensions

Scope confirmed: reuse the prototype dashboard in `../aster-hero`; a full SaaS
platform is not required for the next milestone. Inspected `ProductPreview.tsx`,
`CandidateMap.tsx`, and `src/lib/data.ts`: the original landing preview runs on illustrative values. The imported
`apps/web` project now includes a separate connected campaign route.

Detailed brainstorming, stack, architecture, data contracts, prior work, sources,
and evaluation gates: [PRODUCT_EXTENSIONS.md](docs/PRODUCT_EXTENSIONS.md).
Milestone 6 and the first 7A evidence replay are implemented locally. Later structural
expansion and milestone 9 remain planned. Milestone 8 has a local literature workflow and pilot corpus; none of these extensions has demonstrated selection improvement.

| Milestone | Scope and proposed stack | Exit gate |
| --- | --- | --- |
| 6. Connect the existing prototype — complete locally | Existing Next.js/React/TypeScript UI → FastAPI/Pydantic → campaign package, SQLite, local worker; retain the visual design | Browser import → preview → commit eight picks → export → import results → round two, with saved state and real evidence |
| 7A. First 3D evidence replay — implemented locally | Mol*; pinned RCSB 8Y2G; RDKit identity checking; verified geometric proximity; saved campaign replay. PLIP deferred | Verified ligand/target/atom mapping, source-labelled structure, contact selection and nearest-measured evidence; no invented binding pose |
| 7B. Exploratory predicted poses — implemented locally; transfer validation pending | AutoDock Vina pilot with recorded preparation, pocket and seeds | Predeclared pose-validation checks pass; predicted poses remain labelled and docking scores do not replace potency |
| 8. Literature evidence RAG — local workflow implemented; independent review pending | Europe PMC permitted content + ChEMBL records; typed claims, entity resolution, lexical/dense retrieval; SQLite FTS5/NumPy initially, Postgres/pgvector when warranted | Reviewed retrieval/extraction/citation test set, contradiction handling and abstention; literature does not silently change model scores |
| 9. Evidence-augmented selection research — first hypothesis run; result null | Baseline, literature augmentation and an information-matched irrelevant-evidence control on one target, with strict replay enforced in code; structural, combined and learned-retrieval arms not run | Gate failed: +0.40 top-decile gain against a required 1.0, and +0.20 of that reproduced by the scrambled control. Evidence remains attached to decisions and excluded from scores |

- [x] Replace synthetic counts, compound IDs, rationale text and pIC50-only labels
  with campaign data. Use eight picks by default and show the declared endpoint.
- [x] Replace illustrative confidence intervals and uncertainty-derived roles with
  supported evidence. Prefer a prediction-versus-nearest-measured-similarity plot;
  similarity/novelty must not be called calibrated confidence.
- [x] Add separate non-mutating web previews and explicit commit, with stale
  snapshot detection. The existing CLI `propose` retains its immediate-commit behavior.
- [x] Persist full scored candidate-pool outputs in web preview artifacts, alongside
  immutable committed-round predictions and model coefficients.
- [x] Select one target with verified structural coverage. Interpret interaction as
  protein–ligand binding initially; drug–drug interactions and dynamics are separate.
- [x] Keep model-selection reasons distinct from structural hypotheses. Morgan/ridge
  does not consume protein coordinates, so a displayed contact cannot explain its score.
- [x] Build a small target-specific literature corpus before broad ingestion. Preserve
  document dates, licenses, exact claim sources, compound identity, and assay context.
- [ ] Evaluate retrieval quality independently from downstream selection performance.
  No LLM fine-tuning is needed for the initial evidence retrieval milestone.
- [ ] Before research fusion, freeze a temporal/hidden-outcome exclusion protocol.
  Retrieved known measurements are initial knowledge, not newly discovered hits.
- [ ] Test assay-aware external evidence first; consider learned structure/text
  retrieval or fusion only after simpler information-matched baselines.

**Differentiation:** prediction, active learning, 3D interaction views and scientific
RAG already exist (Cerella, deepmirror, BayBE, Mol*/PLIP, PaperQA, MoleculeSTM).
Aster currently demonstrates a reproducible evaluation/workflow foundation, not
superior discovery or a novel model. The proposed contribution is an auditable
connection between each decision, its assay-compatible evidence and its measured
outcome, plus a rigorous test of when external evidence improves low-data selection.
This is a research direction to validate, not a claim that competitors lack it.

## 1. Product thesis and assumptions

**Aster helps discovery teams choose their next experimental batch by adapting molecular models to small assay datasets and balancing predicted activity, uncertainty, and chemical diversity.**

The first product answers: “We have measured some compounds, have a larger candidate library, and can test only a small batch. What should we test next, and what evidence supports that choice?”

Primary objective: recover useful active compounds under a fixed experimental budget. Improving predictive accuracy is a secondary objective. Active learning optimizes learning; Bayesian optimization seeks good outcomes. Evaluate both, but do not assume one automatically achieves the other.

Planning assumptions:

- One developer initially; public datasets; no existing wet-lab partnership or dedicated GPU assumed.
- Small molecules and one coherent assay endpoint per campaign first.
- A computational research MVP precedes a prospective experimental pilot.
- Initial candidate pools are approximately 1,000–50,000 compounds, subject to measured runtime and memory limits.
- No autonomous purchasing, synthesis, or laboratory execution. A researcher reviews and commits each batch.
- Schedule below is an estimated 10–12 focused engineering weeks; biological validation has a separate timeline.

The deployed [prototype](https://aster-ruby.vercel.app/) was inspected in the browser. It shows 134 untested candidates, 18 assayed compounds, a six-compound round-three proposal, activity/uncertainty plots, molecular descriptors, analog evidence, and budget controls. Those values are illustrative, not training data.

The scientific backend now lives in this repository, and the prototype frontend is present at `../aster-hero`. Reuse its components for the next milestone; its current synthetic data must be replaced through an explicit API adapter.

## 2. Convert the prototype into a working product

| Prototype surface | Production behavior | Required backend output |
| --- | --- | --- |
| Campaign and round header | Select an assay campaign; inspect previous rounds and dataset versions | Campaign, round, assay definition, model run and snapshot IDs |
| Predict → Prioritize → Test → Learn | Explicit, resumable workflow with running, failed, and completed states | Job status and allowed state transitions |
| Candidate map | Plot real predictions versus measured-neighbour similarity; filter measured, untested, excluded and proposed candidates | Prediction, similarity, endpoint, eligibility and selection status; uncertainty only if explicitly available |
| Compound inspector | Show actual structure, calculated descriptors, nearest measured analogs and source measurements | RDKit structure depiction/descriptors; fingerprint similarity; provenance |
| Ranked shortlist | Explain selection score and diversity contribution; allow exclusions and locked picks | Versioned acquisition configuration, scores, constraints and reason codes |
| Batch-size and priority sliders | Preview an updated proposal from cached predictions | Reproducible selection job; no retraining on every slider change |
| Experimental upload | Preview schema mapping and validation errors before committing results | Import validation report and immutable measurement snapshot |
| Evaluation view | Show learning curves, baseline comparisons, uncertainty calibration and limitations | Versioned benchmark reports |

Important UI changes:

- Label ensemble disagreement as such. “±1σ” is not automatically a calibrated confidence or prediction interval.
- Display pIC50 only for a compatible IC50 regression task. Classification tasks display activity probability; other endpoints retain their correct names and units.
- Keep the prototype’s visual layout, but default to prediction versus measured-neighbour similarity until useful uncertainty is validated. A separate chemical-space view can use a projection; clustering and diversity decisions must use original features, not 2D plot distances.
- Generate rationale text from recorded facts and reason codes. Similarity and feature attribution are supporting evidence, not a verified mechanism of action.
- Previewing a proposal does not commit a round. Store user overrides and compare the final chosen batch to the original recommendation.
- Show stale-prediction, insufficient-data, invalid-structure, and out-of-domain states explicitly.

MVP workflow: create campaign → upload measurements and candidate structures → validate → train → predict → propose → review and commit batch → export CSV → import assay outcomes → update and repeat.

## 3. Proposed stack and architecture

Keep scientific logic in a reusable Python package that runs identically from the command line, benchmarks, and workers. The web app is an interface to that package.

**Current prototype scope supersedes provisioning below:** use the existing Next.js frontend, a local FastAPI adapter, the working SQLite campaign store, and a local worker. The table below is a later shared-service option; Supabase, Modal, hosted authentication and paid infrastructure are not prerequisites. For structural/RAG additions and the scoped architecture, see [PRODUCT_EXTENSIONS.md](docs/PRODUCT_EXTENSIONS.md).

| Layer | Proposed choice | Purpose |
| --- | --- | --- |
| Web | Next.js App Router, TypeScript, React, Tailwind; Vercel hosting | Reuse the prototype’s visual language and implement campaign workflows |
| Client data | TanStack Query; generated OpenAPI types | Poll asynchronous jobs, cache predictions, keep API contracts explicit |
| Tables/charts | TanStack Table; existing SVG components initially; Canvas when measurements justify it | Inspect compounds and interact with larger candidate pools |
| API | Python 3.11-compatible environment, FastAPI, Pydantic, SQLAlchemy/Alembic | Validation, authorization, campaign mutations and job submission |
| API deployment | One Docker service on a managed container host, initially Render | Keep API requests independent from training jobs |
| Database/auth/storage | Supabase Postgres, Auth and private Storage buckets | Users, campaign metadata, immutable datasets and model artifacts |
| Scientific data | Parquet, PyArrow, NumPy, pandas; RDKit | Efficient tables and chemically meaningful preprocessing |
| Baseline ML | scikit-learn | Fingerprint random forests and simple reference models |
| Neural ML | PyTorch, Chemprop, CheMeleon checkpoint | Train and fine-tune molecular graph models |
| Advanced optimization | BoTorch and GPyTorch, after baseline selection works | Gaussian-process surrogates and probabilistic batch acquisition |
| Cloud compute | Modal CPU/GPU functions behind an adapter | Run bounded, asynchronous training and scoring jobs |
| Reproducibility | uv lockfile, pnpm lockfile, container image digest, Git SHA, JSON run manifests | Rebuild and audit every scientific run |
| Tests | pytest for scientific/API invariants; Playwright for full workflows | Verify the experiment loop and tenant boundaries |

These are proposed choices, not provisioned services. Validate compatible dependency versions in a small training smoke test before pinning them. For Next.js code, read the installed guides under `node_modules/next/dist/docs/` as required by the project instructions.

```mermaid
flowchart TD
    U[Researcher] --> W[Next.js dashboard on Vercel]
    W --> A[FastAPI: auth, validation, campaign operations]
    W --> AU[Supabase Auth]
    A --> D[(Postgres: campaigns, jobs, versions)]
    A --> S[(Private object storage)]
    A --> J[Asynchronous compute adapter]
    J --> C[CPU: curation, fingerprints, baselines]
    J --> G[GPU: neural training and batch scoring]
    C --> P[aster_ml scientific package]
    G --> P
    P --> S
    J --> D
    A --> W
    B[Offline benchmark runner] --> P
    B --> O[Isolated hidden-label oracle]
```

Job contract:

1. API validates membership and creates a job with an idempotency key and immutable input snapshot.
2. Dispatcher starts external compute and records its execution ID. A reconciliation process retries dispatch failures without duplicating logical jobs.
3. Worker loads only authorized inputs, records progress, and writes artifacts to a run-specific path.
4. Finalization atomically registers artifact hashes and marks the job complete. Retries must not overwrite another run.
5. Dashboard polls persisted status. Failed jobs expose a useful error; training has explicit timeouts, cancellation, concurrency and spending limits.

Do not run long training inside a Vercel request or rely on an in-process API background task for durable jobs. Use a simple local worker adapter before cloud deployment. Start without Redis, Kubernetes, a vector database, or an LLM dependency.

Infrastructure references: [FastAPI deployment](https://fastapi.tiangolo.com/deployment/), [Supabase Auth](https://supabase.com/docs/guides/auth), [Modal invocation methods](https://modal.com/docs/guide/function-invocation-methods), and [Modal compute configuration](https://modal.com/docs/guide/functions). Provider pricing and quotas must be checked when provisioning; this plan does not assume free production hosting.

### Repository layout

```text
apps/web/                 # landing page and campaign dashboard
services/api/             # FastAPI, authorization and persistence
packages/aster_ml/
  data/                   # structures, endpoint normalization, manifests
  features/               # fingerprints and encoder adapters
  models/                 # baselines, neural training and uncertainty
  selection/              # acquisition, diversity and constraints
  evaluation/             # replay loop and metrics
workers/                  # local and cloud execution adapters
configs/                  # immutable experiment configuration templates
benchmarks/               # split manifests and evaluation protocols
tests/                    # focused scientific and integration tests
docs/                     # schemas, model cards and experiment reports
ROADMAP.md
```

## 4. Data model and API boundaries

Core records:

- `workspace`, `membership`, `campaign`: tenant scope, target, endpoint, objective and campaign policy.
- `compound`: original structure, standardized structure, identity key and processing version. Keep supplier IDs and stereochemistry.
- `assay`: target, species, protocol/source, endpoint and available conditions.
- `measurement`: compound, assay, original value/unit/relation, normalized value, replicate, experiment, QC status and provenance.
- `dataset_version`: immutable row membership, schema, file hash, source version and preprocessing configuration.
- `model_run`: dataset version, split manifest, seed, architecture, checkpoint hash, parameters, metrics and artifacts.
- `prediction_set`: model run, candidate snapshot, mean/probability, uncertainty definition, interval method and applicability information.
- `round`, `proposal`, `selection`: batch configuration, model version, ranking, locks/exclusions, selected compounds and researcher overrides.
- `job`, `artifact`: lifecycle state, execution ID, progress and checksums.

Store large feature/prediction arrays in Parquet artifacts; keep searchable metadata in Postgres. Corrections create new dataset versions, preserving prior decisions.

Proposed endpoints: `POST /campaigns`, `POST /imports`, `POST /imports/{id}/commit`, `POST /campaigns/{id}/training-runs`, `POST /campaigns/{id}/prediction-runs`, `POST /campaigns/{id}/proposals`, `POST /proposals/{id}/commit`, `GET /jobs/{id}`, and versioned candidate/measurement/export endpoints. Use `202 Accepted` for long jobs.

The browser never receives cloud service credentials. API verifies tokens and workspace membership; every query and artifact download is tenant-scoped. Supabase RLS is defense in depth, not a substitute for API authorization when service credentials bypass RLS. Use short-lived signed downloads, private buckets, file-size limits and an audit log. Test cross-workspace access before accepting private data. Private campaigns are not pooled for model training by default.

## 5. Datasets: acquisition and intended use

| Dataset | What to use | Role | Key limitation |
| --- | --- | --- | --- |
| [FS-Mol](https://github.com/microsoft/FS-Mol) | Official task lists, task files and split definitions | Few-shot classification/adaptation benchmark | Do not relabel binary tasks as pIC50 regression; preserve its official evaluation track |
| [ASAP–Polaris–OpenADMET](https://huggingface.co/datasets/openadmet/ASAP_Polaris_OpenADMET_challenge) | One coherent potency or ADMET endpoint with published partitions | Campaign demonstration and external evaluation | Audit endpoint completeness and overlap; an unblinded challenge is retrospective when reused |
| [MoleculeACE](https://github.com/molML/MoleculeACE) | Activity-cliff datasets and official evaluation resources | Test whether aggregate accuracy hides failures on close analogs | Audit overlap with other training corpora and molecular pretraining |
| [ChEMBL](https://www.ebi.ac.uk/training/online/courses/chembl-quick-tour/accessing-chembl-data/) | Selected, compatible assay records and metadata | Later multitask pretraining/transfer corpus | Heterogeneous endpoints and protocols require curation |
| [BindingDB](https://www.bindingdb.org/rwd/bind/chemsearch/marvin/Download.jsp) | Target-specific measurements, assay descriptions and dates | Additional target tasks and temporal stress tests | Publication/curation dates are not necessarily experiment dates |
| [PubChem BioAssay](https://pubchem.ncbi.nlm.nih.gov/docs/bioassays) | Clearly documented screening assays with measured inactive outcomes | Later larger hit-discovery pools | Single-concentration screens and confirmatory potency measurements are different tasks |

Initial sequence:

1. Download FS-Mol from its official repository's data link. Freeze source/version/hash and honor task partitions.
2. Inspect the ASAP/OpenADMET schema and choose one sufficiently populated, consistently defined regression endpoint for the UI. Prefer an IC50 task if it satisfies the data audit; otherwise rename the dashboard endpoint correctly.
3. Add a small, predefined MoleculeACE evaluation suite.
4. Only then curate ChEMBL/BindingDB to investigate cross-assay transfer.

Write a manifest for every source: URL, release/revision, retrieval date, checksum, license, permitted usage notes, citation, schema and exclusions. Code, dataset and checkpoint licenses are separate. Dataset selection is not complete until actual eligible counts, missingness, classes, assay compatibility and split overlap are recorded.

### Curation rules

- Preserve raw rows; standardize structures with a versioned policy for salts, charges, tautomers and stereochemistry. Keep raw-to-standardized mappings and report failed/ambiguous cases.
- Use one compatible endpoint per initial campaign. Do not pool IC50, Ki and Kd as interchangeable labels.
- For positive, exact IC50 measurements: `pIC50 = -log10(IC50 in mol/L)`, so `pIC50 = 9 - log10(IC50 in nM)`.
- Preserve inequalities: `IC50 > 10,000 nM` implies `pIC50 < 5`. Start exact-value regression with excluded censored-row counts disclosed; add censored likelihoods later.
- Missing labels are not negative outcomes. Do not expose imputed values as experimental truth.
- Keep replicates and conflicting measurements. Aggregate only with an explicit, assay-compatible policy.
- Group duplicate compound/assay measurements before splitting. Avoid putting duplicate labels in training and evaluation under different database IDs.
- Audit cross-dataset overlap before supervised pretraining. Separately disclose structure-only pretraining overlap and supervised label leakage.

## 6. Model development and fine-tuning recipe

### Models to compare

| Model | Implementation | Why include it |
| --- | --- | --- |
| Fingerprint baseline | RDKit Morgan fingerprints, radius 2, 2,048 bits as an initial configuration; random forest | Strong inexpensive reference |
| Graph model from scratch | Chemprop D-MPNN | Separates architectural value from pretraining |
| Frozen pretrained model | CheMeleon encoder + regularized linear or small neural head | Tests representation quality with little adaptation |
| Fine-tuned graph model | CheMeleon initialized Chemprop | Primary deep-learning candidate |
| Probabilistic alternative | Frozen neural embeddings with a Gaussian process | Research track for low-data selection |
| 3D alternative | Uni-Mol | Later ablation when conformer processing and compute are justified |

Resources: [RDKit](https://github.com/rdkit/rdkit), [Chemprop](https://github.com/chemprop/chemprop), [CheMeleon](https://github.com/chrissly31415/chemeleon), [Uni-Mol](https://github.com/deepmodeling/Uni-Mol), [Molfeat](https://github.com/datamol-io/molfeat), [ADKF-IFT](https://github.com/Wenlin-Chen/ADKF-IFT).

Chemprop supplies the trainable graph model; CheMeleon supplies pretrained weights. Start with its documented `finetuning_demo.ipynb` and `--from-foundation CheMeleon` workflow, verifying the exact syntax against the pinned release. Do not assume a library install alone supplies a model adapted to the campaign.

### Fine-tuning procedure

1. Freeze task splits before fitting anything. Use development tasks for hyperparameter decisions. Only acquired labels from a campaign may enter its adaptation routine.
2. Compute and cache standardized structures, fingerprints and frozen embeddings. Fit target scaling on training data only; invert it for displayed regression predictions.
3. Train a frozen-encoder head as the first adaptation baseline. For classification use binary cross-entropy; for exact regression begin with MSE. Apply missing-label masks for multitask data.
4. Fine-tune the encoder with a lower learning rate than the new head. Initial search ranges: encoder `1e-5`–`1e-4`, head `1e-4`–`1e-3`, weight decay `1e-6`–`1e-3`, batch size 32 or 64, maximum 100 epochs and patience 10. These are proposed starting ranges, not validated optimal settings; supported parameter groups depend on the implementation.
5. Select hyperparameters using development tasks and visible training-label validation only. For very small campaigns, prefer a preselected schedule over an unstable tiny holdout. Never early-stop on hidden candidate labels or final audit labels.
6. Train three independently seeded members for development and consider five for final comparisons if compute permits. Compare ensemble mean and disagreement; measure calibration rather than declaring disagreement a posterior standard deviation.
7. Freeze all choices before final evaluation. Log checkpoint hash, data snapshot, split IDs, target transformation, seed, code revision, training history and runtime.
8. On a new assay round, start from the same foundation checkpoint with all currently acquired labels for the cleanest first benchmark. Treat warm-starting from the previous round as a separate, explicitly compared optimization.

Freeze-first versus full fine-tuning is an empirical choice. Small datasets can favor the frozen model or random forest. Keep the best supported model for the campaign instead of forcing a neural model into every task.

For a Gaussian-process model, use standardized or dimension-reduced frozen embeddings with a small-data GP first; fit any learned reduction on permitted training features. Document kernel and noise assumptions. A neural ensemble cannot be dropped into GP-specific BoTorch acquisition code without a compatible posterior adapter.

### Uncertainty and calibration

- Baseline: report ensemble disagreement, nearest-neighbor similarity and validation errors separately.
- Later: test heteroscedastic predictive heads and held-out interval calibration. Replicate data are needed to validate claims about experimental noise.
- Track interval coverage and width, classification Brier score/reliability, and errors by novelty/scaffold group.
- Standard conformal coverage assumptions can fail under adaptive selection or distribution shift. Do not promise distribution-free coverage on every future campaign. If calibration measurements consume real assay budget, count them.
- At low sample sizes, show insufficient calibration evidence rather than precise-looking unsupported intervals.

## 7. Batch selection and proposed innovation

### Implement a transparent baseline first

For regression on a common scale, begin with a heuristic upper-confidence score:

`score(x) = predicted_mean(x) + beta * ensemble_disagreement(x)`

Then select greedily with a fingerprint-similarity penalty, excluding already measured/pending compounds and honoring researcher locks. Record the formula, beta, diversity strength, tie-breaking seed and candidate snapshot. This is an ensemble-based heuristic, not a theorem-backed confidence bound.

Compare against random, diversity-only, nearest-active-analog and greedy-mean selection. For classification use activity probability and a task-appropriate exploration score. Document the priority-slider mapping; tune defaults only on development data.

Next, compare GP-based batch acquisition in [BoTorch](https://github.com/meta-pytorch/botorch), including noisy expected improvement where appropriate. Benchmark [BayBE](https://github.com/emdgroup/baybe) as an existing experimental-planning alternative. Do not simultaneously maintain two optimization engines without an experimental reason.

Begin with number of assays as the budget. Add monetary cost, availability and turnaround only when real metadata exist. A cost-aware optimizer should respect total batch cost; dividing scores by price alone does not solve every constrained batch problem.

### Prioritized research hypotheses

| Priority | Hypothesis | Proposed experiment | Evidence needed to retain it |
| --- | --- | --- | --- |
| First | Pretrained adaptation plus uncertainty/diversity selection finds useful compounds with fewer measurements | Factorial comparison of model family and acquisition strategy | Gains across held-out tasks and paired seeds, not one attractive curve |
| Second | Assay context improves transfer to a new assay | Molecular encoder plus context embedding/hierarchical assay head; missing-context mask; held-out-assay evaluation | Improvement over molecule-only and assay-specific baselines without target leakage |
| Third | Activity-cliff-aware pair modeling improves selection around close analogs | Auxiliary pairwise potency-difference loss within training partitions; acquisition ablation | Better cliff-region discovery/error without unacceptable overall regression |
| Later | Repeat/confirm decisions can outperform always testing a new compound | Optimize over compound × measurement type using replicate/noise information | Matched replicate data or explicitly labeled simulations; eventual prospective confirmation |

These are research directions, not established novel inventions. Review related work before making novelty claims. Assay-ID embeddings alone cannot represent an unseen assay usefully; require transferable metadata or adaptation from a support set. Auxiliary pairs must be generated after splitting to avoid leakage.

A practical differentiator could be transparent handling of assay mismatch, honest uncertainty, and reproducible batch decisions in a narrowly validated setting. Existing software already offers prediction and active learning: inspect [Cerella](https://optibrium.com/products/cerella/), [Deepmirror](https://www.deepmirror.ai/post/finding-new-active-molecules-6x-faster-with-deepmirror), and [Schrödinger's discovery workflows](https://www.schrodinger.com/life-science/solutions/hit-to-lead-and-lead-optimization/). Their descriptions are vendor claims, not independent performance comparisons.

## 8. Evaluation protocol and release gates

Keep two tracks: official dataset prediction benchmarks for comparability, and a separately documented Aster campaign replay protocol. Custom selection experiments must not be reported as official benchmark scores.

1. Separate development tasks from final evaluation tasks. Document scaffold-group, assay and temporal splits; run these as distinct stress tests where valid metadata exist.
2. Within each replay task, define initial observed labels, an eligible acquisition pool, and an untouched audit set. Final-task adaptation uses only permitted support/acquired labels.
3. Start with a feasible support size such as 32; expand to 64 and 128 where task size permits. Specify minimum remaining pool size, class support and exclusions before running.
4. Initially acquire batches of eight for five rounds. Count every measurement used for adaptation or calibration in the experimental budget.
5. Keep acquisition-pool labels behind a separate oracle interface that only returns requested selections. Keep audit labels inaccessible to training and selection. Ideally run the oracle in a separate process without mounting its files into workers.
6. Refit/update, score remaining candidates and repeat. Use matched initial samples and seeds for competing strategies; start with ten paired seeds for the final suite, subject to a declared compute budget.
7. Report per-task outcomes and aggregate paired differences with intervals that account for tasks and repeated seeds. Do not treat correlated rounds as independent experiments.

Primary metric: additional hits recovered at a fixed acquisition budget, using a prospectively specified task threshold. Secondary metrics: area under the hit-discovery curve, best observed potency, active scaffold coverage, classification PR-AUC or regression MAE/RMSE on the audit set, calibration, wall-clock runtime and actual compute cost.

For assays without an accepted activity threshold, declare a benchmark convention before final evaluation and avoid presenting it as a biological validation criterion. Do not choose thresholds from the final outcomes to favor the method.

Minimum evidence gates:

- Data pipeline: identity, units, censoring and duplicate handling validated; split leakage checks pass.
- Research: compare against random and a strong fingerprint baseline, not just a weak neural baseline.
- Promotion: predeclare a practically meaningful gain with a lab/domain reviewer; require consistent evidence across tasks and disclose uncertainty. An inconclusive result leads to iteration, not a performance claim.
- Product: upload → train → propose → export → import → next round works reproducibly, including job failure/retry.
- Prospective claim: requires new laboratory measurements obtained after recommendations were frozen.

Retrospective pools contain compounds someone previously chose to measure; they are selected samples of chemistry. Replay success does not establish performance over arbitrary vendor libraries or successful drug discovery.

## 9. Implementation milestones

| Phase | Estimated time | Deliverables | Exit criterion |
| --- | --- | --- | --- |
| 0. Scope and repository | Week 1 | Locate prototype source; choose first endpoint; dependency smoke test; dataset/license manifests; user workflow interviews | A reproducible small real dataset and agreed campaign definition |
| 1. Scientific foundation | Weeks 2–3 | Curation package, fingerprints, RF baseline, split manifests, isolated replay oracle | Reproducible baseline report with leakage checks |
| 2. Neural adaptation | Weeks 4–5 | Scratch Chemprop, frozen CheMeleon, fine-tuning, ensemble outputs | Fair comparison with identical data/budgets and saved artifacts |
| 3. Experimental selection | Weeks 6–7 | Random/diverse/greedy/uncertainty policies; constraints; replay metrics | Auditable selection curves and a documented default strategy |
| 4. Product integration | Weeks 8–9 | API, auth/storage, async jobs, dashboard, inspector, imports and exports | Complete two-round workflow using real public measurements |
| 5. Research and pilot readiness | Weeks 10–12 | One research ablation, final held-out evaluation, model cards, lab feedback | Honest evidence report, reliable jobs and defined pilot protocol |

The schedule assumes focused work and dataset availability. A negative model result does not block building the workflow with a baseline. A prospective lab pilot starts only after a partner, assay, budget and protocol are available.

### First ten implementation tasks

- [x] Locate the intended frontend at `../aster-hero` and inspect its prototype components.
- [ ] Read relevant installed Next.js documentation when implementing integration.
- [x] Select an assay and create a versioned dataset manifest.
- [x] Define local molecule, assay, measurement, snapshot and model-run schemas.
- [x] Implement CSV validation and structure canonicalization with explicit, already-normalized endpoint values.
- [ ] Add reviewed raw-unit conversion and richer assay/replicate handling.
- [x] Create duplicate-aware splits and hidden-label replay interfaces.
- [x] Train the fingerprint baseline and reproduce its metrics from a saved configuration.
- [x] Add frozen CheMeleon embeddings and a small prediction head.
- [x] Run one controlled fine-tuning comparison.
- [x] Implement campaign exclusions/locks and evaluate diversity separately; greedy remains the default.
- [x] Feed real saved predictions into the connected prototype map, inspector and shortlist.

## 10. Papers and open-source study plan

| Read | Why it matters | Concrete output |
| --- | --- | --- |
| [Traversing chemical space with active deep learning for low-data drug discovery](https://www.nature.com/articles/s43588-024-00697-2) | Molecular active-learning behavior | Baseline policies and low-data experiment design |
| [FS-Mol: A Few-Shot Learning Dataset of Molecules](https://openreview.net/pdf?id=701FtuyLlAd) | Task-level adaptation evaluation | Official task/split loader and comparable classification evaluation |
| [Descriptor-based Foundation Models for Molecular Property Prediction](https://arxiv.org/abs/2506.15792) | CheMeleon pretraining and transfer | Frozen versus fine-tuned adaptation experiment |
| [Chemprop: A Machine Learning Package for Chemical Property Prediction](https://pmc.ncbi.nlm.nih.gov/articles/PMC10777403/) | Molecular graph prediction implementation | A reproducible supervised graph baseline; consult current v2 docs for APIs |
| [Meta-learning Adaptive Deep Kernel Gaussian Processes for Molecular Property Prediction: paper/code](https://github.com/Wenlin-Chen/ADKF-IFT) | Low-data probabilistic modeling | Optional embedding-plus-GP ablation |
| [BoTorch: A Framework for Efficient Monte-Carlo Bayesian Optimization](https://arxiv.org/abs/1910.06403) | Probabilistic acquisition | GP acquisition comparison after simple selection works |
| [Exposing the Limitations of Molecular Machine Learning with Activity Cliffs](https://pure.tue.nl/ws/portalfiles/portal/257498223/acs.jcim.2c01073.pdf) | Failure cases on similar compounds | Cliff-specific metrics and later pairwise modeling |
| [Conformal Validity Guarantees Exist for Any Data Distribution (and How to Find Them)](https://proceedings.mlr.press/v235/prinster24a.html) | Sequential selection changes uncertainty assumptions | A calibration protocol with clearly stated assumptions |

Reuse chemistry tooling, model implementations, and optimization libraries. Build Aster's data contracts, experiment lifecycle, evaluation harness, decision provenance, and selected research extensions.

## 11. Adjacent research options

Choose at most one after the molecular MVP has a credible benchmark result or a lab partnership points to a better problem.

| Direction | Resources | Technical opportunity | Added burden |
| --- | --- | --- | --- |
| Cellular phenotype selection | [JUMP Cell Painting paper and data](https://www.nature.com/articles/s41592-024-02241-6) | Fuse molecular and image representations to choose phenotypic experiments | Batch effects, image compute and distinguishing measured candidate profiles from unavailable future measurements |
| Protein engineering | [ProteinGym](https://github.com/OATML-Markslab/ProteinGym) | Adapt protein representations and select variants for fitness measurements | Protein-specific representations and carefully grouped variant splits |
| Genetic perturbations | [GEARS](https://github.com/snap-stanford/GEARS) | Select informative perturbations and predict expression responses | Combinatorial generalization, biological confounding and demanding baselines |
| Reaction/formulation optimization | [BayBE](https://github.com/emdgroup/baybe) | Transfer learning and cost-aware decisions in mixed parameter spaces | A different dataset schema and experimental customer workflow |

For multimodal experiments, do not feed the measured outcome of an unperformed experiment into its own selection model. Use only features available at decision time, or explicitly charge for measuring them.

## 12. Compute, partnerships and remaining decisions

Start curation, fingerprints and baselines locally on CPU. Use one on-demand GPU for initial neural experiments, with a small smoke run to measure memory and throughput. A 16–24 GB GPU is a starting sizing hypothesis for the small-model track, not a requirement or guarantee. Benchmark before reserving resources; defer large 3D models and pretraining from scratch.

Budget formula: number of tasks × seeds × rounds × ensemble members × measured training time, plus inference, storage and service costs. Cache deterministic features, cap search trials, shut down idle compute, and get a spending limit before provisioned runs. No training or paid provisioning is performed by this roadmap.

Find a medicinal/computational chemist to review endpoint curation and a lab willing to share a de-identified campaign or run a small prospective batch. Interview researchers about existing selection practice, assay failure rates, data exports, budget constraints and what recommendation evidence they trust. The most valuable pilot is a repeatable comparison against their actual decision process.

Decisions to confirm before the relevant phase:

1. Is the near-term goal a research portfolio/paper, a lab pilot, or commercial SaaS? Default: research MVP that can support a lab pilot.
2. Is a particular target, assay, or collaborator available? Default: choose by public-data quality, then narrow with a partner.
3. What GPU/cloud spending cap and weekly time budget apply? Default: local baseline work first; no paid run assumed.
4. Frontend location is resolved: reuse `../aster-hero`, with a working prototype rather than a full SaaS release first.
5. Will private laboratory data enter the first release? Default: public data only until access controls and data-use agreements are ready.

First complete deliverable: a reproducible public-data campaign with real model predictions, documented fine-tuning, an auditable recommended batch, and a second round that learns from revealed measurements. Its evaluation should explain where Aster helps, where it does not, and what remains unvalidated.
