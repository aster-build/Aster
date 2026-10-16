# Milestone 9 retest: was the null a property of the evidence, or of its supply?

Milestone 9 asked whether permitted external evidence improves low-data batch selection.
It compared a literature-augmented selector against the campaign-only default on one
target over 40 paired cases, and found no gain: +0.40 top-decile compounds per 40 picks
(SE 0.33) against a predeclared gate of +1.0, with a value-scrambled control at +0.20.
Evidence was kept out of the ranking and attached to the decision record instead.

That comparison could not separate two explanations. Either external evidence does not
help this selector, or the corpus supplied too little of it: of 31 usable corpus
structures, 19 were already in the replay dataset, because corpus and dataset were built
from the same ChEMBL source. Twelve structures were permitted.

This retest separates them, on nine targets instead of one and at 864 paired cases
instead of 40. Two constraints turn out to bind, and only one of them was visible before.

**Supply binds below about 50 structures.** With 12 supplied measurements there is no
gain, on one target or on nine. With 50 there is, and with 150 more again. The effect is
not an artifact of extra training rows: the same rows with their values permuted make
selection substantially worse.

**Value precision binds at literature quality.** Donor measurements in the supply study
are exact. Perturbing them by the inter-source disagreement a real literature corpus
carries, about 0.68 log units, removes the entire gain and turns it negative. At
same-laboratory precision, about 0.29 log units, roughly two thirds of the gain survives.

So the milestone 9 decision is upheld, and its stated reason was incomplete. A bigger
literature corpus would not have rescued it. What the ranking needs, if evidence is ever
to enter it, is 50 or more measurements of pool-external structures at single-laboratory
precision; aggregated literature values at that supply are worse than nothing.

| Study | Cases per arm | Supplied structures | Value precision | Gain per 40 picks | 95% CI |
| --- | --- | --- | --- | --- | --- |
| Milestone 9, as run | 40 | 12 (literature) | literature | +0.40 | −0.27 to +1.07 |
| Milestone 9, 40 seeds | 160 | 12 (literature) | literature | +0.03 | −0.34 to +0.39 |
| Retest, random donors | 144 | 12 | exact | +0.29 | −0.50 to +1.07 |
| Retest, random donors | 144 | 50 | exact | **+2.35** | +1.43 to +3.26 |
| Retest, random donors | 144 | 150 | exact | **+2.80** | +1.88 to +3.72 |
| Retest, scaffold-disjoint | 144 | 12 | exact | +0.23 | −0.48 to +0.94 |
| Retest, scaffold-disjoint | 144 | 50 | exact | **+1.15** | +0.35 to +1.96 |
| Retest, scaffold-disjoint | 144 | 150 | exact | **+1.61** | +0.65 to +2.57 |
| Sensitivity, random donors | 144 | 150 | same-lab (0.29) | +1.83 | +0.90 to +2.77 |
| Sensitivity, random donors | 144 | 150 | cross-source (0.68) | −0.99 | −2.00 to +0.03 |
| Sensitivity, scaffold-disjoint | 144 | 150 | same-lab (0.29) | +1.04 | +0.10 to +1.97 |
| Sensitivity, scaffold-disjoint | 144 | 150 | cross-source (0.68) | **−1.88** | −2.92 to −0.83 |

Baseline recovery across the retest is 15.17 top-decile compounds per 40 picks, so +2.80
is a relative improvement of about 18% and −1.88 a loss of about 12%.

## 1. What milestone 9 could and could not detect

`aster/evidence_power.py` reports the power accounting of any paired evidence study from
its `case_metrics.csv`. Run against the milestone 9 metrics:

| Arm | Cases | Mean | 95% CI | p | Min detectable effect | Power against +1.0 |
| --- | --- | --- | --- | --- | --- | --- |
| literature_strict | 40 | +0.40 | −0.27 to +1.07 | 0.23 | 0.95 | 0.84 |
| shuffled_control | 40 | +0.20 | −0.42 to +0.82 | 0.52 | 0.87 | 0.89 |

Milestone 9 was adequately powered for the gate it declared: 84% power against +1.0, and
a minimum detectable effect of 0.95 at 80% power. Its null is therefore not a power
failure at that threshold. What it could not see was anything smaller: +0.5 would have
needed 145 cases and +0.25 would have needed 571, against the 40 it ran. The honest
reading of the original result is that it ruled out gains above about +1.07 and said
nothing about gains below it.

Artifacts: `artifacts/power-evidence-v1/milestone9-power.json`.

## 2. Same corpus, four times the cases

`configs/evidence-v1-extended.json` repeats milestone 9 unchanged except for seeds, 40
instead of 10, giving 160 paired cases on CHEMBL238_Ki.

| Arm | Cases | Mean | 95% CI | p | Min detectable effect |
| --- | --- | --- | --- | --- | --- |
| literature_strict | 160 | +0.03 | −0.34 to +0.39 | 0.89 | 0.53 |
| shuffled_control | 160 | −0.23 | −0.62 to +0.16 | 0.25 | 0.56 |

Per protocol: published −0.06, scaffold transfer +0.11.

The original +0.40 was split noise. With 160 cases the literature arm sits on zero, and
gains above +0.39 can now be ruled out for this corpus at this supply. The gate still
fails, so the milestone 9 decision stands for the corpus it was run on: twelve permitted
structures of literature-grade precision do not move this selector.

Artifacts: `artifacts/evidence-v1-extended/`.

## 3. Wider data, with supply swept

`configs/evidence-supply-v1.json`, run by `aster/evidence_supply.py`, removes the supply
limit instead of working around it. For each case a donor set is withheld from the replay
task and handed back as external evidence. Donor measurements are the most favourable
evidence that could exist for these tasks: same assay, same endpoint, exact equality
relations, no curation noise, and structures that are provably absent from the task,
because they were removed before the split. Every arm in a case sees the same shrunken
task, the same split, the same seed and the same budget.

- 9 MoleculeACE Ki targets (CHEMBL1862, 1871, 2034, 214, 238, 262, 287, 4005, 4203)
- 2 protocols: published partition and scaffold transfer
- 2 donor regimes: uniform random, and whole Murcko scaffold groups so that donor and
  task chemotypes are disjoint
- 3 supply levels: 12, 50, 150 structures
- 8 seeds, support size 32, 5 rounds of 8 picks
- 864 paired cases per arm, 144 per regime per supply level

The predeclared gate is milestone 9's, carried over unchanged for comparability: at the
highest supply, at least +1.0 top-decile gain and at least +1.0 separation from the
permuted control.

### Result: the gate passes in both donor regimes

| Regime at 150 donors | Cases | Gain | 95% CI | Control | Separation | Gate |
| --- | --- | --- | --- | --- | --- | --- |
| Random donors | 144 | +2.80 | +1.88 to +3.72 | −8.54 | +11.34 | passes |
| Scaffold-disjoint donors | 144 | +1.61 | +0.65 to +2.57 | −7.06 | +8.67 | passes |

Pooled across regimes and supplies, 864 cases: donor evidence +1.40 (CI +1.05 to +1.76,
p < 0.0001), permuted control −4.31 (CI −4.73 to −3.90). The minimum detectable effect at
864 cases is 0.50, so this design can see effects half the size of the gate.

Three things in that table matter more than the headline.

**The control is not neutral, it is harmful.** Appending 150 structures with permuted
values costs 8.5 top-decile compounds per 40 picks. Extra training rows are not free: the
ridge fit is pulled toward whatever those rows say. This is what makes the gain
interpretable, and it is the first hint of the precision result in section 4. A selector
that improved merely from having more rows would show a positive control; this control is
strongly negative, so the gain comes from the structure-value link and nothing else.

**Scaffold-disjoint donors help less, and still help.** When donors share no Murcko
scaffold with anything in the task, the gain drops from +2.80 to +1.61. Part of the
random-donor gain comes from donors that are near neighbours of pool compounds, which is
the optimistic case. The scaffold-disjoint number is the one to plan against, since real
external evidence usually sits off to the side of a campaign's chemotypes.

**Supply has a threshold, not a slope from zero.** At 12 structures both regimes sit on
zero (+0.29 and +0.23, both intervals spanning zero). Between 12 and 50 the gain appears;
between 50 and 150 it grows slowly. Milestone 9 was below the threshold, and no number of
extra seeds on a twelve-structure corpus would have revealed anything.

### Per target, at 150 donors

| Target | Cases | Gain | 95% CI |
| --- | --- | --- | --- |
| CHEMBL238_Ki (DAT) | 32 | +4.38 | +2.91 to +5.84 |
| CHEMBL4005_Ki | 32 | +4.00 | +2.09 to +5.91 |
| CHEMBL4203_Ki | 32 | +3.16 | +1.41 to +4.90 |
| CHEMBL1862_Ki | 32 | +2.56 | +0.37 to +4.76 |
| CHEMBL262_Ki | 32 | +2.53 | +0.81 to +4.25 |
| CHEMBL287_Ki | 32 | +2.22 | +0.46 to +3.98 |
| CHEMBL2034_Ki | 32 | +2.16 | +0.12 to +4.19 |
| CHEMBL1871_Ki | 32 | −0.47 | −1.88 to +0.95 |
| CHEMBL214_Ki | 32 | −0.69 | −3.92 to +2.54 |

Seven of nine targets gain; two are flat, with intervals that include zero in both
directions. The effect generalizes across targets but is not uniform, and 32 cases per
target cannot say why these two differ. CHEMBL214 is the largest task at 3,317 rows,
where 150 donors are a smaller share of the measurements available; that is a hypothesis,
not a result.

Artifacts: `artifacts/evidence-supply-v1/`.

## 4. The gain does not survive literature-grade value noise

Donor values are exact, which no real corpus is. Cross-source aggregation of the same
quantity carries about 0.68 log units of spread, against 0.17 to 0.29 within a single
laboratory (Kalliokoski et al., 2013, on ChEMBL activity data).
`configs/evidence-supply-v1-noise.json` repeats the 50- and 150-donor levels with
Gaussian noise added to donor values at both figures, 576 paired cases per arm.

This run is declared post-hoc: its noise levels and gate were fixed before running it but
after the primary result was read. It tests the robustness of an effect already observed,
not a pre-registered hypothesis. The exact-value arm was repeated inside it and reproduced
the primary numbers to the digit, which is the consistency check that the two runs share
splits and seeds.

| Regime and supply | Exact | Same-lab noise (0.29) | Cross-source noise (0.68) |
| --- | --- | --- | --- |
| Random, 50 | +2.35 | +1.62 (+0.66 to +2.57) | −0.37 (−1.39 to +0.65) |
| Random, 150 | +2.80 | +1.83 (+0.90 to +2.77) | −0.99 (−2.00 to +0.03) |
| Scaffold-disjoint, 50 | +1.15 | +0.69 (−0.14 to +1.53) | −0.67 (−1.49 to +0.15) |
| Scaffold-disjoint, 150 | +1.61 | +1.04 (+0.10 to +1.97) | −1.88 (−2.92 to −0.83) |

Pooled over 576 cases: exact +1.98, same-lab +1.30 (CI +0.84 to +1.75), cross-source
−0.98 (CI −1.46 to −0.49, p = 0.0001).

The ordering is consistent at every supply and in both regimes. Same-laboratory precision
keeps about two thirds of the gain and still clears the +1.0 gain threshold at 150 random
donors. Cross-source precision destroys it, and in the realistic regime, scaffold-disjoint
structures at the highest supply, it is significantly worse than adding nothing at all.

This is the same mechanism as the permuted control, in a weaker form. A ridge fit has no
way to discount a training row, so a measurement that is wrong by half a log unit is
taken as seriously as one that is right. Adding more of them adds more error.

Artifacts: `artifacts/evidence-supply-noise-v1/`.

## 5. What this changes

1. **Milestone 9's decision is upheld; its explanation was incomplete.** Evidence stays
   out of the ranking. Not because external measurements cannot help, but because the two
   conditions under which they help, 50 or more pool-external structures and
   single-laboratory value precision, are both missing from a literature corpus. The
   write-up at `docs/EVIDENCE_SELECTION.md` remains correct about what it measured; this
   document supersedes its reasoning about why.
2. **A bigger literature corpus is no longer the obvious next spend.** It was the natural
   reading of milestone 9 and section 3 supports it on supply grounds, but section 4
   withdraws it: literature-grade values at 150 structures are worse than nothing. Corpus
   expansion is worth doing for the decision record, where values are displayed with
   their provenance and never averaged into a prediction. It is not worth doing to improve
   the ranking.
3. **If evidence is ever to enter the ranking, the requirement is now specific.** 50 or
   more measurements of structures outside the pool, from one laboratory and one protocol,
   on the campaign's own endpoint. That is a description of a collaborator's unpublished
   assay history, not of a public corpus. It is worth asking a prospective lab partner
   whether they have it.
4. **The decision record is unaffected.** Direction A keeps evidence attached to
   decisions regardless of this result, and section 4 is an argument for exactly that
   treatment: a value too imprecise to train on is still worth recording with its source.
5. **A structural arm is not ruled out, but it is expensive to test.** Docking supplies a
   descriptor, not a measured value, so none of this bounds it. What this study does
   supply is the variance needed to size the experiment. The paired-difference standard
   deviation across the retest is 5.26 top-decile compounds, so at 80% power a structural
   arm needs 219 cases to detect +1.0 and 892 to detect +0.5. A single new pocket on a
   single structure yields one target, which at 2 protocols and 8 seeds is 16 cases,
   enough to detect only +3.94. Preparing and validating one more pocket would buy a
   comparison that cannot see the effect it is looking for. Docking several targets' pools,
   or accepting a much larger detectable effect, is the choice; there is no cheap version.
   Section 4 is also a caution for it: a docking score is noisier relative to its signal
   than a measurement at 0.68 log units, and appended training rows punish noise.
6. **The next data addition is still BindingDB with dates**, for the temporal holdout that
   `aster-research/datasets-model-rebind.md` recommends. Nothing here answers whether a
   decision would have been right at the time it was made, which is Direction A's own
   claim.

## 6. Limitations

- Donor measurements come from the same curated dataset as the task, so sections 3 and 4
  are an upper bound on what any real corpus of the same size could deliver.
- Nine Ki tasks from one benchmark collection. No ADMET endpoint, no differing unit or
  dynamic range, no measured inactives. "Any assay" remains a design property, not an
  evaluated claim.
- Gaussian noise of a fixed spread is a crude stand-in for real disagreement, which is
  skewed, assay-dependent and correlated within a source. The two levels are taken from
  one 2013 study of ChEMBL activity data; they are the right order of magnitude, not a
  measurement of this corpus. A direct test would re-measure the milestone 8 corpus
  against a reference assay, which nobody has done.
- No temporal holdout, so none of this says whether a decision would have been right at
  the time it was made.
- Donor removal shrinks each task, so absolute recovery counts here are not comparable to
  the milestone 1 to 4 numbers. Only the within-case paired differences are.
- The result bounds evidence used as appended training rows for this selector. Evidence
  used for filtering, weighting, or as a separate model is untested, and section 4 is a
  reason to look at exactly those: they can discount an imprecise value, and a ridge row
  cannot.
- Two targets show no gain even with exact values, and this study cannot explain why.
- `aster/evidence_power.py` gained a normal-approximation fallback after the primary
  supply run, because the noncentral t integral returns nothing usable at very large
  noncentrality. It changes reported power only where power is effectively 1, and no
  replay or mean in this document depends on it; the primary comparison was recomputed
  after the change and is identical. The sealed contracts record different source hashes
  for the two runs for this reason.

## 7. Reproducing

```sh
# power accounting for any paired evidence study
python -m aster.evidence_power --metrics artifacts/evidence-v1/case_metrics.csv --by protocol

# milestone 9, same corpus, 40 seeds
python -m aster.evidence_selection --study configs/evidence-v1-extended.json \
  --output artifacts/evidence-v1-extended

# the supply retest across nine targets
python -m aster.evidence_supply --study configs/evidence-supply-v1.json \
  --output artifacts/evidence-supply-v1

# the post-hoc noise sensitivity analysis
python -m aster.evidence_supply --study configs/evidence-supply-v1-noise.json \
  --output artifacts/evidence-supply-noise-v1
```

Each run seals its inputs, library versions and module hashes into `contract.json` before
it starts, and refuses to write into a directory whose contract differs.
