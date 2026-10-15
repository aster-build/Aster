"""Rebuild the bounded DAT evidence corpus from pinned public source snapshots.

No network access. Use scripts/fetch_literature_sources.py to restore missing sources.
The machine audit is not independent scientific review.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aster.evidence import Claim, import_corpus

BASE = ROOT/'data/literature/dat-v1'
SOURCES = BASE/'sources'
CONFIG = ROOT/'configs/literature/dat-v1.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(element):
    return ' '.join(''.join(element.itertext()).split())


def build():
    config = json.loads(CONFIG.read_text())
    for name, record in config['sources'].items():
        if sha(SOURCES/name) != record['sha256']:
            raise ValueError(f'Source checksum mismatch: {name}')
    metadata = {r.get('pmcid'): r for r in json.loads((SOURCES/'europepmc-search.json').read_text())['resultList']['result']}
    claims, rejected = [], []
    for pmcid in config['abstracts']:
        name = pmcid+'.xml'
        article = ET.parse(SOURCES/name).getroot()
        permission = ET.tostring(article.find('.//permissions'), encoding='unicode')
        if not ('Creative Commons' in permission and ('Attribution' in permission or 'CC0' in permission or 'creativecommons.org/licenses/by/4.0' in permission)):
            raise ValueError(f'Unverified reuse terms: {pmcid}')
        meta = metadata[pmcid]
        abstract = article.find('.//abstract')
        passage = normalized(abstract)
        aliases = [f"{node.attrib.get('pub-id-type')}:{node.text}" for node in article.findall('./front/article-meta/article-id')]
        claims.append(dict(id=pmcid+'-abstract', document_id=pmcid, document_aliases=aliases,
                           title=normalized(article.find('.//article-title')), authors=meta.get('authorString', ''),
                           url=f'https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/',
                           published=meta['firstPublicationDate'], retrieved=config['retrieved'],
                           license=config['abstracts'][pmcid]['license'], source_sha256=sha(SOURCES/name), source_file=name,
                           locator='front/article-meta/abstract (whitespace normalized)', passage=passage,
                           target_accession='Q01959', species='Homo sapiens', assay='Article-level target context; consult methods for species, constructs and conditions.',
                           endpoint='target_context', evidence_type=config['abstracts'][pmcid]['evidence_type'],
                           review_status='reviewed', reviewer='Codex source audit 2026-10-14', review_method='machine',
                           extraction_version='dat-v1', notices=config['abstracts'][pmcid].get('notices', []),
                           retracted=any('retract' in t.lower() for t in meta.get('pubTypeList', {}).get('pubType', []))))
    activities = json.loads((SOURCES/'chembl-activities.json').read_text())['activities']
    molecules = {r['molecule_chembl_id']: r for r in json.loads((SOURCES/'chembl-molecule.json').read_text())['molecules']}
    documents = {r['document_chembl_id']: r for r in json.loads((SOURCES/'chembl-document.json').read_text())['documents']}
    assays = {r['assay_chembl_id']: r for r in json.loads((SOURCES/'chembl-assay.json').read_text())['assays']}
    assert json.loads((SOURCES/'chembl-target.json').read_text())['target_components'][0]['accession'] == 'Q01959'
    selected = [r for r in activities if 'human' in r['assay_description'].lower() and not r['data_validity_comment'] and not r['potential_duplicate']][:100]
    for row in selected:
        assay = assays[row['assay_chembl_id']]
        if assay['confidence_score'] != 9 or assay['relationship_type'] != 'D' or assay['target_chembl_id'] != 'CHEMBL238':
            rejected.append({'activity_id': row['activity_id'], 'reason': 'Not a direct single-protein target assignment at confidence 9'})
            continue
        molecule = molecules[row['molecule_chembl_id']]
        structures = molecule.get('molecule_structures') or {}
        if not structures.get('canonical_smiles'):
            rejected.append({'activity_id': row['activity_id'], 'reason': 'Missing canonical structure'})
            continue
        doc = documents[row['document_chembl_id']]
        # Only structured database fields are reproduced. Publisher abstract is not copied.
        passage = json.dumps({k: row[k] for k in ['activity_id','molecule_chembl_id','assay_chembl_id','assay_description','standard_type','standard_relation','standard_value','standard_units']}, ensure_ascii=False, sort_keys=True)
        claims.append(dict(id='chembl-activity-'+str(row['activity_id']), document_id=doc['document_chembl_id'],
                           document_aliases=[x for x in [f"doi:{doc['doi']}" if doc['doi'] else None, f"pmid:{doc['pubmed_id']}" if doc['pubmed_id'] else None] if x],
                           title=doc['title'], authors=doc['authors'], url=f"https://www.ebi.ac.uk/chembl/explore/document/{doc['document_chembl_id']}",
                           published=f"{doc['year']}-12-31", publication_precision='year', retrieved=config['retrieved'],
                           license='ChEMBL data: CC BY-SA 3.0; structured-record extraction, not publisher full text',
                           source_sha256=sha(SOURCES/'chembl-activities.json'), source_file='chembl-activities.json',
                           locator=f"activities[activity_id={row['activity_id']}] (selected fields serialized as JSON)",
                           passage=passage, target_accession='Q01959', species='Homo sapiens',
                           compound_smiles=structures['canonical_smiles'], compound_id=row['molecule_chembl_id'],
                           assay_id=row['assay_chembl_id'], assay=assay['description'], endpoint=row['standard_type'],
                           value=float(row['standard_value']), unit=row['standard_units'], relation=row['standard_relation'],
                           evidence_type='experimental', source_kind='chembl_record', review_status='reviewed',
                           reviewer='Codex structured-record audit 2026-10-14', review_method='machine', extraction_version='dat-v1'))
    claims = [Claim.model_validate(c).model_dump(mode='json') for c in claims]
    (BASE/'corpus.json').write_text(json.dumps(claims, indent=2, ensure_ascii=False)+'\n')
    result = import_corpus(BASE/'corpus.json', ROOT/'artifacts/dashboard/evidence/index.sqlite')
    audit = result | {'screened_metadata_documents': len(json.loads((SOURCES/'europepmc-search.json').read_text())['resultList']['result']), 'fulltext_documents': len(config['abstracts']),
                      'screened_activities': len(selected), 'rejected': rejected, 'independent_review': False,
                      'source_checksums': {name: record['sha256'] for name, record in config['sources'].items()},
                      'limitations': ['Machine audit, not independent scientific review.', 'Year-only dates use December 31 as a conservative cutoff bound.', 'Article abstracts are target context; no exact chemical identity inferred from names.', 'Historical known measurements may overlap campaign labels; review-only, not a blind replay corpus.']}
    (BASE/'audit.json').write_text(json.dumps(audit, indent=2)+'\n')
    print(json.dumps({k: v for k, v in audit.items() if k not in ('source_checksums','rejected')}, indent=2))


if __name__ == '__main__':
    build()
