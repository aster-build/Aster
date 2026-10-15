"""Read-only, reviewed literature retrieval, isolated from campaign selection.

Import an explicit JSON corpus with ``python -m aster.evidence import FILE``.
Source passages are data; this module never executes or generates instructions.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
from rdkit import Chem


class SourceNotice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: str
    url: HttpUrl
    note: str


class Claim(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    id: str = Field(min_length=1, max_length=120)
    document_id: str = Field(min_length=1, max_length=250)
    title: str = Field(min_length=1, max_length=1000)
    url: HttpUrl
    published: date
    retrieved: date
    license: str = Field(min_length=1, max_length=250)
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    locator: str = Field(min_length=1, max_length=1000)
    passage: str = Field(min_length=1, max_length=20000)
    target_accession: str = Field(min_length=1, max_length=40)
    species: str = Field(min_length=1, max_length=150)
    compound_smiles: str | None = None
    assay: str = Field(min_length=1, max_length=2000)
    endpoint: str = Field(min_length=1, max_length=100)
    value: float | None = None
    unit: str | None = None
    relation: Literal['=', '<', '>', '<=', '>='] | None = None
    evidence_type: Literal['experimental', 'computational', 'context']
    review_status: Literal['reviewed', 'unreviewed']
    reviewer: str | None = None
    extraction_version: str = Field(min_length=1, max_length=100)
    retracted: bool = False
    source_kind: Literal['literature', 'chembl_record'] = 'literature'
    document_aliases: list[str] = Field(default_factory=list, max_length=10)
    authors: str = ''
    review_method: Literal['human', 'machine', 'unspecified'] = 'unspecified'
    publication_precision: Literal['day', 'year'] = 'day'
    compound_id: str | None = None
    assay_id: str | None = None
    source_file: str | None = None
    resolved_document_id: str | None = None
    notices: list[SourceNotice] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def consistent(self):
        if self.published > self.retrieved:
            raise ValueError('Publication cannot follow retrieval')
        if self.review_status == 'reviewed' and not (self.reviewer or '').strip():
            raise ValueError('Reviewed claims require a reviewer')
        measurement = (self.value is not None, bool(self.unit), self.relation is not None)
        if any(measurement) and not all(measurement):
            raise ValueError('Measurements require value, unit and relation together')
        if self.compound_smiles is not None:
            self.compound_smiles = canonical(self.compound_smiles)
        return self


def canonical(smiles):
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None or molecule.GetNumAtoms() == 0:
        raise ValueError('Invalid compound SMILES')
    return Chem.MolToSmiles(molecule, isomericSmiles=True)


def normalize_document_id(value):
    value = value.strip().lower()
    value = re.sub(r'^https?://(?:dx\.)?doi.org/', 'doi:', value)
    if value.startswith('10.'):
        value = 'doi:' + value
    if re.fullmatch(r'pmc\d+', value):
        value = 'pmcid:' + value.upper()
    if value.startswith(('pmc:', 'pmcid:')):
        suffix = value.split(':', 1)[1].upper()
        value = 'pmcid:' + (suffix if suffix.startswith('PMC') else 'PMC' + suffix)
    return value


def resolve_documents(claims):
    """Union only explicit source identifiers; never fuzzy-match titles."""
    parents = {}
    def root(key):
        parents.setdefault(key, key)
        if parents[key] != key:
            parents[key] = root(parents[key])
        return parents[key]
    for c in claims:
        identifiers = [normalize_document_id(v) for v in [c.document_id, *c.document_aliases]]
        root(identifiers[0])
        for key in identifiers[1:]:
            parents[root(key)] = root(identifiers[0])
    groups = {}
    for key in list(parents):
        groups.setdefault(root(key), []).append(key)
    for group in groups.values():
        if len([key for key in group if key.startswith('doi:')]) > 1:
            raise ValueError('Conflicting DOI aliases; review document identity before import')
    for c in claims:
        group = groups[root(normalize_document_id(c.document_id))]
        c.resolved_document_id = sorted(group, key=lambda key: (not key.startswith('doi:'), key))[0]


def import_corpus(source: Path, destination: Path):
    """Validate everything before atomically replacing the independent index."""
    raw = source.read_bytes()
    if len(raw) > 20_000_000:
        raise ValueError('Corpus exceeds the 20 MB local import limit')
    records = json.loads(raw)
    if not isinstance(records, list) or len(records) > 10000:
        raise ValueError('Corpus must be a list of at most 10,000 claims')
    claims = [Claim.model_validate(record) for record in records]
    resolve_documents(claims)
    ids, documents = set(), {}
    for claim in claims:
        if claim.id in ids:
            raise ValueError(f'Duplicate claim ID: {claim.id}')
        ids.add(claim.id)
        # Multiple claims may share a document; different versions need explicit IDs.
        identity = claim.document_id.strip().lower().removeprefix('https://doi.org/').removeprefix('doi:')
        metadata = (claim.source_sha256, claim.published, claim.title, claim.license, claim.retracted)
        if identity in documents and documents[identity] != metadata:
            raise ValueError(f'Conflicting document versions: {claim.document_id}')
        documents[identity] = metadata
    serialized = json.dumps([c.model_dump(mode='json') for c in sorted(claims, key=lambda c: c.id)], sort_keys=True)
    snapshot = hashlib.sha256(serialized.encode()).hexdigest()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, suffix='.sqlite')
    os.close(descriptor)
    try:
        with closing(sqlite3.connect(temporary)) as connection:
            connection.execute('CREATE TABLE metadata (snapshot TEXT NOT NULL)')
            connection.execute('INSERT INTO metadata VALUES (?)', (snapshot,))
            connection.execute('CREATE TABLE claims (id TEXT PRIMARY KEY, target TEXT, species TEXT, smiles TEXT, endpoint TEXT, published TEXT, eligible INTEGER, payload TEXT)')
            connection.execute('CREATE VIRTUAL TABLE passages USING fts5(id UNINDEXED, title, passage)')
            for c in claims:
                connection.execute('INSERT INTO claims VALUES (?,?,?,?,?,?,?,?)', (c.id, c.target_accession, c.species, c.compound_smiles, c.endpoint, c.published.isoformat(), int(c.review_status == 'reviewed' and not c.retracted), c.model_dump_json()))
                connection.execute('INSERT INTO passages VALUES (?,?,?)', (c.id, c.title, c.passage))
            connection.commit()
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {'snapshot_sha256': snapshot, 'claims': len(claims), 'documents': len(documents)}


def search(index: Path, query: str, target: str, species: str, *, smiles=None, endpoint=None, cutoff: date | None = None, limit=10,
           evidence_type=None, match='exact', method='lexical'):
    if not 1 <= limit <= 50 or not query.strip() or len(query) > 500:
        raise ValueError('Use a nonempty query up to 500 characters and limit 1–50')
    tokens = re.findall(r'\w+', query, flags=re.UNICODE)
    if not tokens:
        raise ValueError('Query must contain words')
    if smiles is not None:
        smiles = canonical(smiles)
    if match not in ('exact', 'analog') or method not in ('lexical', 'hybrid'):
        raise ValueError('Unsupported retrieval method or compound match')
    if match == 'analog' and not smiles:
        raise ValueError('Analog search requires a compound structure')
    if evidence_type not in (None, 'experimental', 'computational', 'context'):
        raise ValueError('Unsupported evidence type')
    result = {'status': 'no_evidence', 'snapshot_sha256': None, 'claims': [],
              'ranking_effect': 'none', 'conflicts': [], 'answer': None, 'method': method,
              'scope': 'Source passages and structured records; machine and human review are labelled. No potency inference. A date filter alone is not a leakage-safe replay.'}
    if not index.exists():
        result['status'] = 'corpus_unavailable'
        return result
    with closing(sqlite3.connect(index.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        result['snapshot_sha256'] = connection.execute('SELECT snapshot FROM metadata').fetchone()[0]
        filters = ['c.target = ?', 'c.species = ?', 'c.eligible = 1']
        parameters = [target, species]
        for column, value in [('smiles', smiles if match == 'exact' else None), ('endpoint', endpoint), ('published', cutoff.isoformat() if cutoff else None)]:
            if value is not None:
                filters.append(f'c.{column} {"<=" if column == "published" else "="} ?')
                parameters.append(value)
        query_expression = ' OR '.join('"' + token + '"' for token in tokens)
        rows = connection.execute('SELECT c.payload FROM passages JOIN claims c ON c.id = passages.id WHERE passages MATCH ? AND ' + ' AND '.join(filters) + ' ORDER BY bm25(passages), c.id', [query_expression, *parameters]).fetchall()
        candidates = [json.loads(row[0]) for row in rows]
        if method == 'hybrid':
            # Transparent local comparator: character TF-IDF, not neural semantic retrieval.
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            all_rows = connection.execute('SELECT c.payload FROM claims c WHERE ' + ' AND '.join(filters) + ' ORDER BY c.id', parameters).fetchall()
            pool = [json.loads(row[0]) for row in all_rows]
            if pool:
                vectorizer = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5), max_features=30000)
                matrix = vectorizer.fit_transform([c['title'] + ' ' + c['passage'] for c in pool])
                similarities = cosine_similarity(vectorizer.transform([query]), matrix)[0]
                lexical_ranks = {c['id']: rank for rank, c in enumerate(candidates, 1)}
                ranked = sorted(zip(pool, similarities), key=lambda item: (-item[1], item[0]['id']))
                scores = {c['id']: 1/(60+rank) for rank, c in enumerate(candidates, 1)}
                for rank, (c, similarity) in enumerate(ranked, 1):
                    if similarity >= .15:
                        scores[c['id']] = scores.get(c['id'], 0) + 1/(60+rank)
                candidates = sorted((c for c in pool if c['id'] in scores), key=lambda c: (-scores[c['id']], lexical_ranks.get(c['id'], 10001), c['id']))
        if evidence_type:
            candidates = [c for c in candidates if c['evidence_type'] == evidence_type]
        for c in candidates:
            c['match_type'] = 'exact_compound' if smiles else 'target_context'
        if match == 'analog':
            from rdkit.Chem import rdFingerprintGenerator
            from rdkit import DataStructs
            generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048, includeChirality=True)
            reference = generator.GetFingerprint(Chem.MolFromSmiles(smiles))
            analogs = []
            for c in candidates:
                if c['compound_smiles'] and c['compound_smiles'] != smiles:
                    similarity = DataStructs.TanimotoSimilarity(reference, generator.GetFingerprint(Chem.MolFromSmiles(c['compound_smiles'])))
                    if similarity >= .7:
                        c.update(match_type='analog', similarity=similarity)
                        analogs.append(c)
            candidates = analogs
        result['claims'] = candidates[:limit]
        result['total_matches'] = len(candidates)
        result['conflicts'] = measurement_conflicts(candidates)
        if result['claims']:
            result['status'] = 'evidence_found'
            result['answer'] = {'type': 'extractive', 'text': 'Relevant source records are shown below. They do not establish activity for an unmeasured candidate.',
                                'citation_ids': [c['id'] for c in result['claims']]}
    return result


def measurement_conflicts(claims):
    """Flag disagreements only within the same identified assay; never pool assays."""
    groups = {}
    for c in claims:
        if c.get('assay_id') and c.get('compound_smiles') and c.get('value') is not None:
            key = (c['compound_smiles'], c['target_accession'], c['species'], c['assay_id'], c['endpoint'], c['unit'])
            groups.setdefault(key, []).append(c)
    conflicts = []
    for group in groups.values():
        exact = [c for c in group if c['relation'] == '=']
        if len({c['value'] for c in exact}) > 1:
            conflicts.append({'type': 'measurement_disagreement', 'claim_ids': [c['id'] for c in exact],
                              'message': 'Different values in the same identified assay. Replicate variability or source error is possible; inspect the records. Values are not averaged.'})
    return conflicts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    ingest = sub.add_parser('import')
    ingest.add_argument('source', type=Path)
    ingest.add_argument('--index', type=Path, default=Path('artifacts/dashboard/evidence/index.sqlite'))
    args = parser.parse_args()
    print(json.dumps(import_corpus(args.source, args.index), indent=2))


if __name__ == '__main__':
    main()
