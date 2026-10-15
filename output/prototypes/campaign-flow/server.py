"""Isolated prototype. Real local fitting, public outcome replay; no campaign writes."""
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import numpy as np
from aster.heads import StableRidge
from aster.data import fingerprints
from aster.acquisition import nearest_measured
DATA=json.loads((HERE/'data.json').read_text()); ROWS={r['id']:r for r in DATA['compounds']}; OUTCOMES=json.loads((HERE/'outcomes.json').read_text()); IDS=sorted(ROWS); FEATURES=fingerprints([ROWS[c]['smiles'] for c in IDS]); INDEX={c:i for i,c in enumerate(IDS)}
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory=str(HERE),**kw)
 def do_POST(self):
  try:
   origin=self.headers.get('Origin')
   if origin and origin!='http://'+self.headers.get('Host',''):raise ValueError('Same-origin requests only')
   if int(self.headers.get('Content-Length',0))>20000:raise ValueError('Request too large')
   body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
   if not isinstance(body,dict):raise ValueError('Expected an object')
   ids=body.get('ids',[])
   if not isinstance(ids,list) or len(ids)>160 or any(not isinstance(i,str) or i not in ROWS for i in ids):raise ValueError('Unknown compound')
   if self.path=='/api/reveal':result={'outcomes':{c:OUTCOMES[c] for c in ids if c in OUTCOMES}}
   elif self.path=='/api/score':
    overrides=body.get('observations',{})
    if not isinstance(overrides,dict) or any(c not in ids or not isinstance(v,(int,float)) or isinstance(v,bool) or not np.isfinite(v) for c,v in overrides.items()):raise ValueError('Invalid observed values')
    observed=sorted(set(ids)|{c for c in IDS if ROWS[c]['initial']});pool=[c for c in IDS if c not in observed]
    x=FEATURES[[INDEX[c] for c in observed]];y=np.array([ROWS[c]['value'] if ROWS[c]['initial'] else overrides.get(c,OUTCOMES[c]) for c in observed]);q=FEATURES[[INDEX[c] for c in pool]]
    if len(pool):
     model=StableRidge('standard',10).fit(x,y);pred=model.predict(q);near,novelty=nearest_measured(q,x)
     result={'training_count':len(observed),'scores':[{'id':c,'prediction':float(pred[i]),'similarity':float(1-novelty[i]),'nearest':observed[int(near[i])],'nearest_value':float(y[near[i]])} for i,c in enumerate(pool)]}
    else:result={'training_count':len(observed),'scores':[]}
   else:self.send_error(404);return
   raw=json.dumps(result,allow_nan=False).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
  except (ValueError,KeyError,TypeError) as e:
   self.send_response(422);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps({'error':str(e)}).encode())
if __name__=='__main__':
 print('Prototype: http://127.0.0.1:3010 — no campaign writes',flush=True)
 ThreadingHTTPServer(('127.0.0.1',3010),Handler).serve_forever()
