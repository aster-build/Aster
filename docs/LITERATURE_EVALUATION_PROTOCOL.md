# DAT retrieval evaluation v1

Frozen before running retrieval evaluation, 2026-10-14. This is a **machine-authored
engineering evaluation**, not the independent 50–100-question scientific review
required by the product roadmap. The independent review gate remains open.

Corpus: `configs/literature/dat-v1.json` pins the raw source hashes. Eight permitted
full-text papers contribute their abstracts; 100 structured ChEMBL activity records
are screened, with direct-target confidence-9 assignments retained. The corpus is
purposively small, not a representative sample of all DAT literature.

Fifty queries cover 16 target-context questions (two per paper), 20 exact-compound
measurement lookups, eight unsupported or mismatched-context searches, and six
related-compound searches. Expected record IDs and filters are written to
`configs/literature/questions-v1.json` before evaluation. Question/source construction
is visible to the implementer; report performance as an engineering check, not a
blind or independently reviewed benchmark. Document/chemical-series-disjoint
held-out review remains required before milestone 8 is scientifically complete.

Compare literal BM25 lexical retrieval to a local hybrid comparator combining
BM25 with character 3–5-gram TF-IDF cosine similarity using reciprocal-rank fusion
(k=60, similarity floor 0.15). The latter is a transparent text-similarity baseline,
not a neural sentence encoder. Keep lexical retrieval as default regardless of
this first evaluation; any tuning needs a new development set.

Predeclared engineering checks:

- Expected-record recall@10 ≥ 0.80 across answerable queries; report by category.
- All eight unanswerable/incorrect-context queries return no evidence.
- Returned source passages and extracted numbers/units/relations match the pinned
  original XML or structured activity record in 100% of checked claims.
- Exact-compound retrieval has no analog or unspecified-identity fallback.
- Conflicting values in the same identified assay are flagged without averaging;
  different assays, units, species, or endpoints are never collapsed.
- Campaign state and rankings are byte-for-byte unchanged by search or attachment.
- Record latency, corpus snapshot, code hashes, all returned IDs, and failures.

A deterministic source-record check validates extraction fidelity, not the truth of
published claims. Source authors are not treated as independent reviewers of this
application. Missing citation support means abstain. This implementation produces
extractive evidence cards, not free-form generated scientific answers.

Remaining comparisons: neural sentence embeddings and PaperQA need a separately
frozen development/test set and reproducible local/provider configuration. They
are not silently represented by the character-based comparator.
