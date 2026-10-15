"""Read public inputs and saved poses; write only this standalone prototype's assets."""
import csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from rdkit import Chem
from rdkit.Chem import Draw,Descriptors,Crippen,rdMolDescriptors
from aster.data import fingerprints
from aster.heads import StableRidge
from aster.acquisition import nearest_measured
import numpy as np
measured=list(csv.DictReader((ROOT/'examples/dashboard/measured.csv').open()))
candidates=list(csv.DictReader((ROOT/'examples/dashboard/candidates.csv').open()))
measured.sort(key=lambda r:r['compound_id']);candidates.sort(key=lambda r:r['compound_id'])
outcomes={r['compound_id']:float(r['value']) for r in csv.DictReader((ROOT/'examples/dashboard/outcomes.csv').open())}
x=fingerprints([r['smiles'] for r in measured]);y=np.array([float(r['value']) for r in measured]);q=fingerprints([r['smiles'] for r in candidates]);model=StableRidge('standard',10).fit(x,y);pred=model.predict(q);neighbors,novelty=nearest_measured(q,x)
rows=[]
for i,r in enumerate(candidates+measured):
 mol=Chem.MolFromSmiles(r['smiles']);d=Draw.MolDraw2DSVG(520,260);d.drawOptions().clearBackground=False;d.drawOptions().bondLineWidth=2;Draw.rdMolDraw2D.PrepareAndDrawMolecule(d,mol);d.FinishDrawing();(OUT/f'assets/mol-{i}.svg').write_text(d.GetDrawingText())
 item={'id':r['compound_id'],'short':r['compound_id'].replace('CHEMBL238_Ki:','DAT-').replace('DAT-','DAT-'),'smiles':r['smiles'],'image':f'assets/mol-{i}.svg','mw':round(Descriptors.MolWt(mol),1),'logp':round(Crippen.MolLogP(mol),2),'tpsa':round(rdMolDescriptors.CalcTPSA(mol),1),'initial':i>=len(candidates)}
 if i<len(candidates): item.update(prediction=float(pred[i]),similarity=float(1-novelty[i]),nearest=measured[int(neighbors[i])]['compound_id'],nearest_value=float(y[neighbors[i]]))
 else:item.update(value=float(r['value']))
 rows.append(item)
def molecule3d(mol):
 conf=mol.GetConformer();atoms=[];mapping={}
 for a in mol.GetAtoms():
  if a.GetAtomicNum()==1:continue
  mapping[a.GetIdx()]=len(atoms);p=conf.GetAtomPosition(a.GetIdx());atoms.append([round(p.x,3),round(p.y,3),round(p.z,3),a.GetSymbol()])
 bonds=[[mapping[b.GetBeginAtomIdx()],mapping[b.GetEndAtomIdx()]] for b in mol.GetBonds() if b.GetBeginAtomIdx() in mapping and b.GetEndAtomIdx() in mapping]
 return {'atoms':atoms,'bonds':bonds}
reference=molecule3d(next(m for m in Chem.SDMolSupplier(str(ROOT/'artifacts/docking/native.sdf'),removeHs=False) if m is not None))
center=np.mean([a[:3] for a in reference['atoms']],axis=0)
ca=[];pocket=[]
for line in (ROOT/'artifacts/docking/receptor.pdb').read_text().splitlines():
 if not line.startswith('ATOM'):continue
 xyz=[float(line[30:38]),float(line[38:46]),float(line[46:54])]
 if line[12:16].strip()=='CA':ca.append(xyz)
 if np.linalg.norm(np.array(xyz)-center)<10:pocket.append(xyz+[line[76:78].strip() or 'C'])
poses={}
for path in (ROOT/'artifacts/dashboard/docking').glob('*/result.json'):
 result=json.loads(path.read_text());approved=[p for p in result['poses'] if p['passed']]
 if approved:
  poses[result['compound_id']]=[molecule3d(Chem.MolFromMolBlock(p['sdf'],removeHs=False))|{'rank':p['rank'],'score':p['score_kcal_mol']} for p in approved[:3]]
(OUT/'data.json').write_text(json.dumps({'compounds':rows,'poses':poses,'structure':{'ca':ca,'pocket':pocket,'reference':reference,'center':center.tolist()},'source':'Public MoleculeACE CHEMBL238 Ki demo; actual Morgan/ridge scores. 8Y2G experimental reference; saved Vina poses.'}))
(OUT/'outcomes.json').write_text(json.dumps(outcomes))
print(len(rows),'compounds;',len(poses),'saved docking compounds')
