# Milestone 8 — local literature evidence workflow

Implemented 2026-10-14. **Independent scientific review remains pending; milestone
8 is not complete.** The original plan proposed 100–300 relevant documents and an
independently reviewed 50–100-question evaluation. This implementation supplies a
smaller 15-document pilot and a machine-authored engineering check. Neither is
silently substituted for the original scientific gate.

## Current behavior

Select a compound in the public DAT dashboard. The Literature evidence panel offers
exact compound, related compound (chirality-aware Morgan Tanimoto ≥0.70), or target
context search. Names are never converted into assumed chemical identities.
Unverified imported campaigns do not inherit the DAT target mapping.

Cards show original passages or explicitly serialized ChEMBL structured records,
source links, author attribution, publication dates, source locators, reuse terms,
checksums, assay context, and human/machine review labels. The pilot is entirely
machine-audited; no independent approval is claimed. Abstracts are article-level
context, not exact-compound evidence. No free-form scientific answer or inferred
potency is generated. No evidence does not imply inactivity.

The API filters target accession, species, compound identity, endpoint, evidence
type, publication date and review/retraction status. Different values in the same
identified assay are flagged for inspection; they may represent replicate variation
or source error. Different assays/endpoints/units are not pooled, and no unit
conversion or automatic scientific contradiction adjudication is claimed.

Users can attach results to a committed round. The immutable JSON includes the query,
corpus hash, source records and training snapshot. It explicitly says the evidence
was attached **after commitment** and was not used for selection. Retries are
idempotent, corpus changes reject stale saves, and results survive corpus replacement
and service restart. No campaign measurement, model, rank, or batch is changed.

## Corpus and provenance

`configs/literature/dat-v1.json` pins raw source URLs and SHA256 checksums. Sources
are cached under `data/literature/dat-v1/sources`.

- 100 Europe PMC metadata results were screened with a publication cutoff of
  2024-12-31. Eight relevant CC BY/CC0 full-text XML documents were downloaded;
  the initial index uses their abstracts. It does not index all full text or supplements.
- 100 ChEMBL records with explicit human assay wording were screened from a bounded
  1,000-record activity page. Only 34 direct single-protein confidence-9 assignments
  were retained. The other 66 have homologous-target assignments and are excluded.
- Molecule, assay, document, and target snapshots verify canonical structures,
  target Q01959, assay descriptions, and document identifiers. Numeric records preserve
  Ki, nM and relation `=` without converting to campaign pKi.
- The 42 records span 15 documents. Known DOI/PMID/PMCID aliases are joined only
  through explicit source links; conflicting DOI aliases are rejected.
- ChEMBL year-only dates use December 31 as a conservative upper bound for date
  filtering and are displayed as years. Publication year is not an exact release date.

ChEMBL structured data are [CC BY-SA 3.0](https://chembl.gitbook.io/chembl-interface-documentation/about).
The source papers retain their own reuse terms. No publisher abstract is copied from
ChEMBL; only structured measurement fields are indexed. Original Europe PMC XML
includes document permissions. The zinc-binding paper carries a linked grant-attribution correction, surfaced on its card. Correction/retraction status is a pinned snapshot,
not a live alert service. Curators must refresh and review it before broader use.

## Reproduce locally

Use the existing environment with `.[web]` installed:

```sh
.venv/bin/python scripts/fetch_literature_sources.py
.venv/bin/python scripts/build_literature_corpus.py
.venv/bin/python scripts/evaluate_literature.py
.venv/bin/python scripts/build_literature_review.py
```

The fetcher verifies cached bytes and rejects upstream drift rather than silently
replacing a pinned source. The builder runs offline, verifies every source hash,
produces `data/literature/dat-v1/corpus.json` and `audit.json`, and atomically installs
`artifacts/dashboard/evidence/index.sqlite`. Preserve raw source snapshots: live
APIs may change and cannot guarantee regeneration of old response bytes.

For an independently prepared corpus:

```sh
.venv/bin/python -m aster.evidence import /absolute/path/corpus.json
```

A JSON array must match `Claim` in `aster/evidence.py`. Required fields cover a
unique claim ID, document identity/title/URL, publication/retrieval dates, license,
source hash and locator, passage, target/species, assay/endpoint, evidence type,
extraction version, and review status. Reviewed claims require a reviewer. Set
`review_method` honestly (`human` or `machine`); omission is labelled unspecified. Measurements require finite value,
unit and relation together. Optional source structures are canonicalized with
stereochemistry retained. The generic importer validates the supplied contract;
it does not independently verify reviewer identity or passage fidelity. The pinned
DAT builder/evaluator adds source checks.

Use `--index /absolute/path/storage/evidence/index.sqlite` for custom API storage.
Invalid imports preserve the existing corpus. Missing corpora return an explicit
unavailable state, while the rest of the campaign remains usable.

## API

- `GET /evidence/status`: record/document counts, review counts and snapshot hash.
- `GET /evidence/search`: required `q`, `target`, `species`; optional `smiles`,
  `endpoint`, `evidence_type`, `cutoff`, `limit` (1–50), `match` (`exact`/`analog`),
  `method` (`lexical`/`hybrid`).
- `GET /evidence/sources/{name}`: download an allowlisted pinned source after
  checksum verification. No arbitrary filesystem path access.
- `GET /campaigns/{id}/evidence`: target-verified search using the saved compound
  structure and `scope=exact|analog|target`.
- `GET/POST /campaigns/{id}/rounds/{number}/evidence`: list or attach immutable
  results. POST requires the last-seen corpus hash.

Keyword search uses literal OR terms and BM25. The experimental hybrid combines
BM25 and character TF-IDF cosine similarity using reciprocal-rank fusion. It is
**not neural semantic retrieval**. Both methods apply the same entity/date/review
filters. Keyword search remains the default.

## Verification and limits

[Protocol](LITERATURE_EVALUATION_PROTOCOL.md); machine results:
`artifacts/literature/evaluation-v1.json`. Both methods recovered all expected
records at k=10 for 42 answerable questions and abstained on all eight unsupported
queries. All 42 passages/numeric records matched pinned sources. The small corpus
and implementer-visible question construction make this an engineering check,
not independent evidence of general retrieval quality or selection improvement.

76 Python tests pass, including source identity handling, numeric validation,
chemical stereochemistry, assay-specific disagreements, filtered hybrid retrieval,
unverified-target rejection, stale save prevention, retry/restart persistence,
and unchanged campaign state. Production build, TypeScript and targeted frontend
lint pass. Browser verification covered real citations, desktop/mobile layout,
empty results, saving, reloading and no campaign-state mutation.

The [review pack](../output/literature-review/index.html) contains 50 source-linked
questions and an editable decision CSV. All independent decisions are pending.
An independent reviewer must check expected answers, chemical and assay mappings,
then author/document a separate held-out set split by document and chemical series.
Expand corpus coverage based on that review. Neural retrieval and PaperQA comparison
remain deferred until that benchmark is frozen; no paid model/provider is configured.

Historical published measurements can overlap campaign labels. A date filter alone
does not remove hidden candidate outcomes. This corpus is for review; it is not a
leakage-safe selection benchmark. Milestone 9 requires separately frozen temporal
and outcome-exclusion rules and fresh evaluation targets.
