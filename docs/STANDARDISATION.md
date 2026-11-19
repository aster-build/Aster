# Recording how structures were read

Queue item 9. Every structure Aster accepts is turned into a canonical form by
`aster.data.canonicalize` before it becomes a compound identity or a fingerprint.
That step makes chemical choices, and until now none of them were stored with a
campaign. This release writes them down, on every campaign and every round, and
reports them in the decision record.

## Terms

- **Standardisation**: rewriting a structure into one agreed form so that two ways of
  drawing the same molecule are treated as one compound.
- **Tautomers**: forms of a molecule that differ only in where a hydrogen and a double
  bond sit, and interconvert in solution. 2-hydroxypyridine and 2-pyridone are the
  textbook pair. Whether they count as one compound is a convention, not a fact.
- **Resonance forms**: different ways of drawing the electrons of one structure, such
  as the alternating single and double bonds of a benzene ring, or a nitro group drawn
  with two double bonds or with separated charges.
- **Identity key**: the text Aster uses to decide whether two rows are the same
  compound. Here it is RDKit's canonical isomeric SMILES.

## The convention, as it actually is

`aster/standardisation.py` states it as data under the identifier
`aster-rdkit-sanitize-v1`:

| Choice | What Aster does |
|---|---|
| Tautomers | Not merged. Each tautomer as written is its own compound. |
| Resonance | Only what RDKit sanitisation does: aromatic rings are perceived, so Kekulé forms of a ring are one compound, and hypervalent nitro and N-oxide groups are rewritten in charge-separated form. Nothing else is merged. |
| Charges | Kept as written. Nothing is neutralised. |
| Salts and mixtures | Refused, not stripped to the largest fragment. |
| Stereochemistry | Kept. The stored structure keeps enhanced (CX) stereo; the identity key drops the CX annotations. |
| Isotopes | Kept. |
| Explicit hydrogens | Removed by sanitisation. |

Each row was checked against RDKit 2026.09.1 rather than written from memory; the
tests in `tests/test_standardisation.py` assert every one of them.

## The probe check

A version number alone cannot say whether two installations read structures the same
way, because RDKit's sanitisation and canonical SMILES have changed between releases.
So the record also carries a **probe hash**: thirteen fixed structures, one per choice
in the table, are canonicalised and the output is hashed. Two readings compare as:

- `same`: same convention, same probe output, same RDKit.
- `same_on_probes`: same convention and probe output, different RDKit version. The
  probes cover the main choices, not every molecule, and the record says so.
- `different`: the convention identifier or the probe output differs. Identities,
  duplicate checks and fingerprints may differ, so error figures should not be set
  side by side.
- `unknown`: one side was recorded before this release. Never assumed to match.

## Where it is stored

- `create` stores the reading once on the campaign, because identities and the
  duplicate check are computed under it, and logs a short form in the create event.
- `propose` stores the reading in use now on the round, next to the one the campaign
  was created under and the comparison between them. A disagreement is recorded, not
  refused: refusing would lock every campaign out on an RDKit upgrade. `RECIPE` is
  unchanged, so existing campaigns still propose.
- The decision record shows it under each decision's `basis.standardisation`, per round
  in `review`, and in `review.totals.standardisation`, which says whether every round
  read structures the same way.
- `python -m aster.decisions --db A.sqlite compare B.sqlite` checks two campaigns.

Campaigns and rounds created before this release carry no record, and nothing
back-fills one: the RDKit version of those rounds is in `versions.rdkit`, but which
convention the code applied then is not something the stored data can prove.

## What was not measured

The queue item cites an outside claim that the tautomer convention can move error
metrics by over 20%. This run did not test that claim on Aster's own model and data;
it is left as a follow-up. One informal observation, from a sample only: of the first
300 ExpansionRx compounds, 53 (18%) get a different identity key under RDKit's
canonical tautomer, so the convention touches a real share of a medicinal chemistry
set. No error figure was computed from that, and none should be inferred.
