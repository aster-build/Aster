"""Create a source-linked, editable review pack without inventing reviewer approval."""
import csv
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
corpus=json.loads((ROOT/'data/literature/dat-v1/corpus.json').read_text())
by_id={c['id']:c for c in corpus}
questions=json.loads((ROOT/'configs/literature/questions-v1.json').read_text())['questions']
out=ROOT/'output/literature-review';out.mkdir(parents=True,exist_ok=True)
if not (out/'review.csv').exists():
    with (out/'review.csv').open('w',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=['question_id','category','question','expected_ids','decision','reviewer','reviewed_at','notes'])
        writer.writeheader()
        for q in questions:writer.writerow(dict(question_id=q['id'],category=q['category'],question=q['query'],expected_ids=';'.join(q['expected_ids']),decision='pending'))
esc=html.escape
cards=[]
for q in questions:
    evidence=[]
    for cid in q['expected_ids']:
        c=by_id[cid]
        notices = ''.join(f'<p><a href="{esc(n["url"])}">{esc(n["kind"])}</a>: {esc(n["note"])}</p>' for n in c.get('notices', []))
        evidence.append(f'<details><summary>{esc(c["title"])} — {esc(cid)}</summary><p>{esc(c["authors"])}</p><p><a href="{esc(c["url"])}">Original source</a> · {esc(c["published"])} · {esc(c["license"])}</p><p><b>Assay:</b> {esc(c["assay"])}</p><p><b>Locator:</b> {esc(c["locator"])}</p><blockquote>{esc(c["passage"])}</blockquote>{notices}<code>{esc(c["source_sha256"])}</code></details>')
    cards.append(f'<section id="{q["id"]}"><header><span>{q["id"]} · {esc(q["category"])}</span><b>Pending independent review</b></header><h2>{esc(q["query"])}</h2><pre>{esc(json.dumps(q["filters"],indent=2))}</pre>{"".join(evidence) if evidence else "<p>Expected: abstain. Check that this scope is genuinely unsupported in the bounded corpus.</p>"}</section>')
page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Aster · Literature review pack</title><style>body{font:15px/1.7 system-ui;background:#f6f5f1;color:#26352e;margin:0}main{max-width:1000px;margin:auto;padding:55px 25px}h1{font-size:38px;line-height:1.2}h2{font-size:21px}section{background:white;border:1px solid #ddd;border-radius:10px;padding:25px;margin:20px 0}header{display:flex;justify-content:space-between;gap:20px;font-size:12px;color:#6b756b}header b{color:#976a26}summary{cursor:pointer;font-weight:600}details{border-top:1px solid #ddd;padding:15px 0}blockquote{border-left:3px solid #c8d4c9;padding-left:20px;margin-left:0}pre,code{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}a{color:#386a53}.intro{padding:20px;background:#e9ede5;border-radius:8px}@media(max-width:650px){header{flex-direction:column}main{padding:25px 16px}section{padding:18px}}</style><main><p>ASTER / MILESTONE 8</p><h1>Literature evidence review</h1><div class="intro"><p>50 questions, 42 source records, 15 documents. All independent-review decisions are pending. Download the <a href="dat-sources-v1.zip">pinned source archive</a> and <a href="evaluation-v1.json">machine evaluation results</a>. These are machine-authored engineering cases, not a blind test set.</p><p>For each question, inspect the original source, expected records, chemical mapping, species/construct, assay, endpoint, number/unit and whether the wording is answerable. Mark accept, revise or reject in <a href="review.csv">review.csv</a>, with reviewer, date and notes. Do not mark approval merely because a query finds its expected record.</p><p>Additional independent questions and document/chemical-series-separated development and test sets are required before a scientific completion claim. No source records alter campaign rankings.</p></div>'''+''.join(cards)+'</main></html>'
(out/'index.html').write_text(page)
print(out/'index.html')
