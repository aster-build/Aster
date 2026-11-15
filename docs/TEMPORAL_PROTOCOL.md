# Temporal holdout protocol

**Status:** declared before the run. Results are in `docs/TEMPORAL_RESULTS.md`.
**Config:** `configs/temporal-v1.json`. **Code:** `aster/expansionrx.py`, `aster/temporal.py`.

## The question

Every result Aster has published so far comes from a **random split**: the
compounds the model is scored on were drawn at random from the same pool as the
compounds it trained on. A real campaign never gets that. It trains on what has
been measured so far and has to predict what comes next, and what comes next is
not a random sample of anything, because chemists chose those compounds after
seeing the earlier results.

So the question this protocol answers is: **how much of Aster's measured accuracy
survives being tested on compounds that came later?** The project's own roadmap
has carried this as a known gap, because none of its earlier datasets carried
any information about when a measurement was taken.

## Terms used here

- **Endpoint.** One measurable property, measured by one assay. "Solubility in
  buffer" is an endpoint; so is "how fast mouse liver enzymes destroy the
  compound". This dataset has nine.
- **ADMET.** Absorption, distribution, metabolism, excretion, toxicity: the
  properties that decide whether a compound can work as a medicine at all, as
  opposed to whether it sticks to the intended target. All nine endpoints here
  are ADMET properties, which is new for Aster; its earlier work was potency.
- **Holdout.** Measurements deliberately kept away from the model during
  fitting, used afterwards to score it.
- **Temporal holdout.** A holdout chosen by time: everything after a cutoff.
- **Random split.** A holdout chosen at random, ignoring time.
- **Mean absolute error (MAE).** Average size of the miss, ignoring direction.
- **Spearman correlation.** Whether the model ranks compounds in the right
  order, from -1 (exactly backwards) through 0 (no relationship) to 1 (perfect
  order). Ranking is what matters for choosing which compound to make next.
- **Morgan fingerprint.** A molecule turned into a fixed list of yes/no answers
  about which small fragments it contains. Aster's default description of a
  molecule.
- **Ridge regression.** Fitting a straight-line relationship between those
  yes/no answers and the measured value, with a penalty that stops any single
  fragment dominating. Aster's default model, and about forty lines of
  scikit-learn.
- **Murcko scaffold.** A molecule's ring skeleton with its decorations stripped
  off. Compounds sharing a scaffold are usually the same chemical series.

## The data

The OpenADMET-ExpansionRx release
(`openadmet/openadmet-expansionrx-challenge-data`, revision `6b898cc`,
CC-BY-4.0). Real lead-optimisation measurements from Expansion Therapeutics'
campaigns on RNA-mediated diseases, released in full in January 2026 after a
blind challenge that drew over 370 participants.

Two reasons this dataset and not another:

1. It is the only public source available to Aster that can be ordered in time
   at all.
2. Both of the major 2026 papers that reproduced Aster's negative results use
   it, so numbers measured here can be compared with theirs rather than standing
   alone.

### There are no dates, and what is used instead

**The release contains no measurement dates.** This has to be said plainly
because it limits every claim below. What the publishers did supply is:

- **Their own partition.** 5,326 compounds were given to entrants as training
  data; 2,282 later compounds were held back, described by the organisers as
  predicting "the ADMET properties of late-stage molecules based on
  earlier-stage data from the same campaigns".
- **A registration number inside every identifier** (`E-0020101`), assigned in
  the order compounds entered the campaign.

The partition turns out to be **exactly one cut in those numbers**: every
training compound is at or below `E-0020100` and every test compound is at or
above `E-0020101`, with no interleaving at all. That agreement is the evidence
that registration order tracks the campaign timeline, and it is what licenses
using the number as an ordinal stand-in for time. The loader checks the
agreement on every run and refuses to proceed if a future revision breaks it.

Two limitations follow and are repeated wherever results are quoted:

- Registration order records **when a compound entered the campaign, not when it
  was assayed**. A late-registered compound could in principle carry an early
  measurement.
- No real cutoff *date* can be stated, so nothing here should be described as
  "trained on data before March" or similar.

### Curation

Identical in spirit to the rules already applied to Aster's Zenodo source:
structures parsed and canonicalised with stereochemistry and charge preserved,
mixtures rejected rather than stripped, duplicate structures excluded wholesale
rather than averaged, no value imputation. One published row becomes up to nine
measurement rows, one per endpoint it has a value for.

Two curation decisions specific to this source:

- **Transforms.** Eight of the nine endpoints are concentrations, rates or
  percentages that are bounded below by zero and span several orders of
  magnitude, so they are fitted on a base-10 logarithm; an error of 0.3 then
  means "out by a factor of two" wherever on the scale it falls. LogD is already
  a logarithm and is left alone.
- **Non-positive values are excluded, not clipped.** A zero on a log-scaled
  endpoint cannot be logged. These are measurements that fell below what the
  assay can quantify, and the release's raw file confirms it: those rows carry
  `<` modifiers which the ML-ready files drop. Excluding them is conservative and
  honest; clipping them to an invented floor would put a made-up number into the
  training data. 357 measurements are excluded this way. Storing bounded values
  faithfully is separate, later queue work.

### What the released files already hide

The ML-ready files keep only in-range measurements. The raw file shows the cost:
**617 measurements over 527 compounds carry a `>` or `<` modifier** and are
absent. This is not a neutral loss. A compound too insoluble to quantify is
missing from the solubility endpoint precisely because it was bad, so each
endpoint's surviving values are a biased sample of what was measured, and every
error figure here is computed on the measurable subset.

## The design

For each of the nine endpoints, three arms:

| Arm | Trains on | Tested on | Repeats |
| --- | --- | --- | --- |
| `temporal` | measurements at or below registration 20100 | everything above it | 1, deterministic |
| `random_matched` | a random subset of the **same pooled** measurements, **the same size** as the temporal training set | a random disjoint subset the **same size** as the temporal holdout | 20 seeds |
| `temporal_rolling` | nested earlier cutoffs inside the earlier era | whatever follows each cutoff | 4 cutoffs |

**The comparison that matters is `temporal` against `random_matched`.** Comparing
temporal error against zero would say nothing, and comparing it against a
random split of a *different* size would confound time with sample size. Holding
the training and test sizes exactly equal and changing only whether time is
respected is what isolates the effect. `temporal_rolling` exists so that any
penalty can be shown to belong to time ordering in general rather than to the
one cutoff the publishers happened to choose.

The model is Aster's unchanged default, refitted from scratch for every case:
Morgan fingerprints (radius 2, 2048 bits, chirality included) into ridge
regression (alpha 10) with standard scaling. No tuning was done for this study,
deliberately: the point is to re-measure the existing default under a harder
protocol, not to produce a better number.

### Metrics

- **Primary: normalised MAE.** Mean absolute error divided by the standard
  deviation of that endpoint's own held-out values. This makes nine endpoints
  measured in log units, micromoles and percentages comparable and averageable,
  and it anchors the scale: **1.0 is the error of simply predicting the average**,
  so anything at or above 1.0 has learned nothing usable.
- **Secondary:** raw MAE in fitted units, RMSE, Spearman correlation, and the
  no-model floor (the error of predicting the training mean) carried on every
  single case so that no result can be quoted without its floor beside it.
- **Explanatory:** the Tanimoto distance from each held-out compound to its
  nearest training neighbour, and the fraction of held-out compounds whose
  Murcko scaffold never appears in training. These are there so that a gap can be
  *explained* rather than merely reported.

### Analysis and its power

Per endpoint, the temporal arm produces **one** number and the control produces a
distribution over 20 seeds, so every quoted spread belongs to the control. The
temporal split has no seed-to-seed variability of its own, because it is a single
deterministic realisation; this is a real limitation of a temporal holdout and
not an oversight.

Across endpoints, the nine per-endpoint gaps are treated as paired differences
and passed through the repository's existing paired power accounting
(`aster/evidence_power.py`) rather than a new implementation. **Nine pairs is a
small design**, and the power report states the minimum detectable effect
rather than leaving it implied. The nine endpoints also come from one company's
campaigns in one disease area and are not independent draws from drug discovery
at large, so the paired statistics describe this dataset and are not an estimate
for the field.

### Declared before the run

- The expected direction is that temporal error is **worse** than matched random
  error. A result in the other direction would be reported as found.
- A null result — no detectable gap — is a real result and gets reported with its
  power, not reshaped into something that reads better.
- No endpoint is dropped for giving an inconvenient answer. The only exclusion
  rule is declared in the config in advance: fewer than 60 training or 30 test
  measurements and the endpoint is skipped as too thin, recorded as skipped.
- This protocol measures **prediction error**, not whether a selection policy
  picks better compounds. That is a different question and it gets its own arm;
  it inherits every limitation above.
