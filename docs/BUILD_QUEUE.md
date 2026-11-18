# Build queue

This file is the backlog the nightly build run works from. It exists so that the
automation has somewhere to look instead of inventing work for itself.

## How it works

Each night one run takes the **topmost unchecked item that is not marked
blocked**, implements it on its own branch in several focused commits, and opens
a pull request. That pull request also ticks the item off in this file, so
merging it is what advances the queue. Nothing merges automatically.

The run is expected to stop and say so, rather than guess, when an item turns out
to be ambiguous, larger than one night, or dependent on a decision that has not
been made. A pull request that says "this is what I found, here is why I stopped"
is a successful run.

Edit this file freely: reorder items, add them, delete them, split one that is
too big, or add `**blocked:** <reason>` to an item to have it skipped. The run
reads the queue, it does not plan.

## Conventions every run follows

- Branch per item, never commit to `main`.
- Several focused commits, one per logical piece, not one lump.
- Tests for new behaviour, in the existing `tests/` style.
- A plain-language summary in the pull request body: what was built, what was
  verified, and what could not be verified.
- A negative result is a result. If an item's experiment says no, the pull
  request records that, with the numbers, and does not quietly reshape the item
  until it says yes.
- Nothing that changes the meaning of an already-stored decision record without
  a migration and a note.
- Build notes for Nicole, every run, including runs that stop early. A document
  that teaches what was built rather than listing it: the short version; the
  background needed to follow it, each term defined on first use; at least one
  diagram or illustration of what was made (how the parts connect, the data
  flow, a before and after, or the experiment's design); each decision with what
  was chosen, why, and the alternative passed on; how it was checked, with the
  real numbers, and a chart when there are five or more; findings, negative ones
  included, and what is left; and how to merge it, step by step. A Claude Doc
  when the run has the Claude Docs tools, otherwise a Markdown file with Mermaid
  diagrams in the project's shared folder under `aster-build-notes/`. Link it
  from the pull request. (Nicole asked for this on 2026-11-14 because she wants
  to learn what was built, not just approve it.)

## Queue

- [x] **1. Upgrade Next.js off the version with the published advisory.**
  `apps/web` pins Next.js 16.4.0, which carries a known security advisory;
  `next build` now compiles the app and then stops to say so before it will
  continue. The dashboard is local-only and unauthenticated, so the exposure is
  small, but the version is a dependency of a published repository and the fix
  is a version bump plus a build. Do this one first because it is small and it
  removes a warning that would otherwise appear on every future run.

- [x] **2. Read the OpenADMET ExpansionRx release with its measurement dates.**
  Add a loader for the challenge data (reported as 7,000+ molecules over nine
  endpoints with a genuine time split), keeping the dates as data rather than
  discarding them. Record provenance and checksums the way `aster/data.py`
  already does for the Zenodo source.

- [x] **3. Add a temporal-split replay protocol.** Train only on measurements
  taken before a cutoff date, evaluate on measurements taken after it. Aster has
  never had this, because none of its existing datasets carry dates. Keep the
  existing random-split protocol intact and comparable.

- [x] **4. Run the temporal holdout and write it up.** Report the same
  discovery metrics as the existing milestones so the numbers sit beside them,
  and state plainly how much the random-split figures were flattered.
  Done. Results in `docs/TEMPORAL_RESULTS.md`: all nine endpoints are worse
  under time ordering, six of nine fail to beat predicting the training mean,
  and the random split reports about 35% less error. The discovery arm
  (`aster/temporal_discovery.py`) shows ranking still beats random picking by
  +5.9 compounds per 40 assays, against the +13.3 a random split would claim.

- [x] **5. Log each candidate's selection propensity at decision time.** For
  every candidate in a committed round's ranked slate, store the probability that
  the policy in force would have selected it. One column, written at commit time.
  This cannot be reconstructed afterwards, which is why it is near the top:
  without it, no later analysis can ask what a different selection policy would
  have found, and every round committed meanwhile is a round that question is
  closed for.
  Nicole moved the temporal holdout (items 2 to 4) ahead of this on
  2026-11-14. The cost of the delay is small for now: every campaign so far is
  a retrospective replay that can be re-run, so no real decision is lost while
  this waits. Keep it next once the holdout is in.
  Done. Every slate row stores `propensity`, and `review` reports per round
  whether the log could support off-policy analysis. Under the greedy policy it
  cannot: every value is 1 or 0, so passed-over candidates had no chance. Item 6
  (or a decision to add randomness to selection) is what makes the log usable.

- [x] **6. Log a matched random shadow batch with every committed batch.** The
  same size, drawn from the same pool, recorded but never run. It costs nothing
  and it turns the project's strongest negative result into something the
  decision record can report later.
  Done. Every round stores `shadow`, drawn with a seed that cannot see the
  model; `review` compares it with the real batch only when every shadow
  compound is measured. In 20 replays of the public CHEMBL238 example the
  greedy batch's mean beat the shadow's by +0.63 pKi in 20 of 20, but its best
  compound beat the shadow's best in only 54 of 80 rounds. The shadow is never
  assayed, so it does not make off-policy evaluation possible on its own; see
  `docs/DECISION_RECORD.md`.

- [x] **7. Replace the bare point estimate with a split conformal interval.**
  State the coverage level, and say in the record that coverage assumptions can
  fail under adaptive selection rather than promising distribution-free coverage.
  Done. `aster/conformal.py` adds a 90% nominal split conformal interval to every
  pick and every slate row; ranking is unchanged. Rather than only warning about
  adaptive selection, `scripts/conformal_coverage.py` measured it over 100
  replays: selected picks were covered 92.7% of the time against a nominal 90%
  and 89.1% for a matched random draw, so the violation ran in the model's favour
  on that dataset. The interval is also barely narrower than the same recipe
  around a model that predicts the training average (1.77 against 1.81 pKi), so
  it is honest and close to uninformative at this amount of data. Written up in
  `docs/CONFORMAL.md`.

- [x] **8. Store censored measurements as {relation, value, unit}.** So that
  "> 10 µM" can be recorded faithfully instead of rejected, and propagates into
  the ranking rather than being silently treated as an exact number.
  Done. `aster/censored.py` keeps the relation and fits a bound as a bound;
  `docs/CENSORED.md` has the write-up. Measured three ways over 80 replays: keeping the
  measurement instead of discarding it is worth +0.65 strong compounds per 32 assays on
  a saturating assay (p = 0.004) and 0.12 to 0.14 log units of prediction error, while
  fitting the bound as a bound rather than substituting it changed no pick on this
  dataset, because ridge shrinkage keeps the predictions from crossing the limit.

- [ ] **9. Record the chemical standardisation convention in the decision
  record.** Which tautomer and resonance conventions were applied, and the
  RDKit version that applied them. Reported to move some error metrics by over
  20%, so an unrecorded convention makes two campaigns incomparable.

- [ ] **10. Replace the 4 Å proximity rule with a real interaction audit.** Use
  PDBFixer to repair the receptor and PLIP to list actual hydrogen bonds,
  hydrophobic contacts, salt bridges and ring stacking. Scope: the one target
  with a prepared receptor, the dopamine transporter on PDB 8Y2G. This closes a
  deferral `ROADMAP.md` already acknowledges.

- [ ] **11. Add TabPFN over pretrained features as a second model family.**
  Logged per batch as a deliberate two-model bracket, not as a replacement for
  Morgan plus ridge. Use `aster/evidence_power.py` for the power accounting
  rather than rolling a new one.

- [ ] **12. Align the record to published vocabulary.** Argonne's append-only
  event-log record types, the replay metrics of Mas et al. (Digital Discovery,
  2026), and RO-Crate with W3C PROV for archiving. Cite rather than reinvent.

## Not in this queue

Structure-model work (Boltz-2, co-folding, docking beyond the existing DAT
pilot) belongs in a separate repository, not here. Aster uses no structure
prediction model, and adding one would make it a different product.
