"""Evaluate the frozen engineering question set; never claim independent review."""
from datetime import date
import hashlib
import json
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aster.evidence import search


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    config = ROOT/'configs/literature/questions-v1.json'
    questions = json.loads(config.read_text())['questions']
    base = ROOT/'data/literature/dat-v1'
    claims = json.loads((base/'corpus.json').read_text())
    source_checks = []
    activities = {r['activity_id']:r for r in json.loads((base/'sources/chembl-activities.json').read_text())['activities']}
    for c in claims:
        source = base/'sources'/c['source_file']
        valid = sha(source) == c['source_sha256']
        if c['source_kind'] == 'literature':
            abstract = ET.parse(source).getroot().find('.//abstract')
            valid &= c['passage'] == ' '.join(''.join(abstract.itertext()).split())
        else:
            row = activities[int(c['id'].split('-')[-1])]
            extracted = json.loads(c['passage'])
            valid &= all(row[k] == v for k,v in extracted.items())
            valid &= (float(row['standard_value']),row['standard_units'],row['standard_relation']) == (c['value'],c['unit'],c['relation'])
        source_checks.append({'id':c['id'],'passed':bool(valid)})
    results = []
    for method in ['lexical','hybrid']:
        for question in questions:
            filters = dict(question['filters'])
            target = filters.pop('target','Q01959'); species = filters.pop('species','Homo sapiens')
            if 'cutoff' in filters:filters['cutoff']=date.fromisoformat(filters['cutoff'])
            start=time.perf_counter()
            result=search(ROOT/'artifacts/dashboard/evidence/index.sqlite',question['query'],target,species,method=method,**filters)
            elapsed=(time.perf_counter()-start)*1000
            ids=[c['id'] for c in result['claims']]; expected=set(question['expected_ids'])
            recall=len(expected & set(ids))/len(expected) if expected else None
            results.append({'id':question['id'],'method':method,'category':question['category'],'recall_at_10':recall,
                            'abstention_correct':not ids if not expected else None,'returned_ids':ids,'latency_ms':round(elapsed,3),
                            'snapshot_sha256':result['snapshot_sha256']})
    summary={}
    for method in ['lexical','hybrid']:
        rows=[r for r in results if r['method']==method]; answered=[r for r in rows if r['recall_at_10'] is not None]; empty=[r for r in rows if r['abstention_correct'] is not None]
        recall=sum(r['recall_at_10'] for r in answered)/len(answered)
        abstained=sum(r['abstention_correct'] for r in empty)
        categories={category:sum(r['recall_at_10'] for r in answered if r['category']==category)/sum(r['category']==category for r in answered) for category in sorted({r['category'] for r in answered})}
        summary[method]={'mean_recall_at_10':recall,'category_recall':categories,'correct_abstentions':abstained,'unanswerable_queries':len(empty),'max_latency_ms':max(r['latency_ms'] for r in rows),'engineering_gate_passed':recall>=.8 and abstained==len(empty) and all(c['passed'] for c in source_checks)}
    report={'independent_review':False,'milestone_complete':False,'summary':summary,'source_checks':source_checks,'queries':results,
            'question_sha256':sha(config),'protocol_sha256':sha(ROOT/'docs/LITERATURE_EVALUATION_PROTOCOL.md'),
            'implementation_sha256':sha(ROOT/'aster/evidence.py'),'evaluator_sha256':sha(Path(__file__))}
    output=ROOT/'artifacts/literature';output.mkdir(parents=True,exist_ok=True)
    (output/'evaluation-v1.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
