"""Run the predeclared 8Y2G redocking experiment in .venv-docking.
Inputs/preparation are documented in docs/DOCKING_PROTOCOL.md; no network access.
"""
import hashlib
import importlib.metadata
import json
import subprocess
from pathlib import Path
import gemmi
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolAlign
from meeko import MoleculePreparation, PDBQTWriterLegacy
from posebusters import PoseBusters

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/docking'
STRUCT=ROOT/'apps/web/public/structures/8y2g'
SEEDS=[17,29,43,71,101]

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(mol): return Chem.MolToSmiles(Chem.RemoveHs(mol),isomericSmiles=True)
def save(path, data): path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
def run(args, logfile):
    with logfile.open('w') as out:
        subprocess.run([str(a) for a in args],stdout=out,stderr=subprocess.STDOUT,check=True,timeout=1800,cwd=ROOT)
def prepare_ligand(smiles, seed, directory):
    molecule=Chem.AddHs(Chem.MolFromSmiles(smiles))
    params=AllChem.ETKDGv3(); params.randomSeed=seed
    if AllChem.EmbedMolecule(molecule,params)!=0: raise ValueError('Conformer embedding failed')
    if not AllChem.MMFFHasAllMoleculeParams(molecule): raise ValueError('Missing MMFF parameters')
    convergence=AllChem.MMFFOptimizeMolecule(molecule,maxIters=1000)
    if convergence!=0: raise ValueError('Initial ligand minimization did not converge')
    with Chem.SDWriter(str(directory/'input.sdf')) as writer: writer.write(molecule)
    setups=MoleculePreparation().prepare(molecule)
    if len(setups)!=1: raise ValueError('Expected one ligand setup')
    text,ok,error=PDBQTWriterLegacy.write_string(setups[0])
    if not ok: raise ValueError(error)
    (directory/'input.pdbqt').write_text(text)
    return molecule

def physical_checks(poses, native, receptor, csv_path):
    frame=PoseBusters(config='redock').bust(poses,mol_true=native,mol_cond=receptor)
    frame.to_csv(csv_path)
    # RMSD is evaluated independently in the fixed protein frame below.
    columns=[c for c in frame.columns if 'rmsd' not in c.lower()]
    output=[]
    for _,row in frame.iterrows():
        checks={c:(bool(row[c]) if isinstance(row[c],(bool,np.bool_)) else None) for c in columns}
        output.append({'checks':checks,'failed_checks':[c for c,v in checks.items() if v is not True], 'passed':all(v is True for v in checks.values())})
    return output

def main():
    manifest=json.loads((STRUCT/'manifest.json').read_text())
    native=next(iter(Chem.SDMolSupplier(str(BASE/'native.sdf'))))
    assert canonical(native)==canonical(Chem.MolFromSmiles(manifest['ligand_smiles']))
    # Preserve native ions and glycans for validation, removing only the answer ligand.
    structure=gemmi.read_structure(str(STRUCT/'complex.cif'))
    chain=structure[0]['A']
    for i in reversed(range(len(chain))):
        if chain[i].seqid.num==701: del chain[i]
    structure.write_pdb(str(BASE/'validation-receptor.pdb'))
    receptor=BASE/'validation-receptor.pdb'
    native_checks=physical_checks([native],native,receptor,BASE/'native-posebusters.csv')[0]
    config='\n'.join([f'center_{a} = {v}' for a,v in zip('xyz',manifest['ligand_center'])]+[f'size_{a} = 24' for a in 'xyz'])+'\n'
    (BASE/'box.txt').write_text(config)
    report={'protocol':'v1','status':'running','reference':'8Y2G / dexmethylphenidate','receptor_mode':'protein-only; ions retained in physical validation','native_checks':native_checks,'runs':[], 'cross_docking_validated':False,'versions':{p:importlib.metadata.version(p) for p in ['meeko','posebusters','gemmi','rdkit','numpy','scipy','pandas']},'vina':'1.2.7','parameters':{'seeds':SEEDS,'exhaustiveness':32,'cpu':2,'num_modes':10,'box_size_angstrom':[24,24,24],'center':manifest['ligand_center'],'ligand_charge':0},'hashes':{str(p.relative_to(ROOT)):digest(p) for p in [STRUCT/'complex.cif',BASE/'native.sdf',BASE/'receptor.pdbqt',BASE/'tools/vina',BASE/'box.txt',BASE/'validation-receptor.pdb',ROOT/'docs/DOCKING_PROTOCOL.md',ROOT/'scripts/validate_docking.py',ROOT/'scripts/dock_candidate.py']}}
    save(BASE/'validation.json',report)
    for seed in SEEDS:
        directory=BASE/f'seed-{seed}'; directory.mkdir(exist_ok=True)
        prepare_ligand(manifest['ligand_smiles'],seed,directory)
        run([BASE/'tools/vina','--receptor',BASE/'receptor.pdbqt','--ligand',directory/'input.pdbqt','--config',BASE/'box.txt','--seed',seed,'--cpu',2,'--exhaustiveness',32,'--num_modes',10,'--out',directory/'poses.pdbqt'],directory/'vina.log')
        run([ROOT/'.venv-docking/bin/mk_export.py',directory/'poses.pdbqt','-s',directory/'poses.sdf'],directory/'export.log')
        poses=list(Chem.SDMolSupplier(str(directory/'poses.sdf'),removeHs=True))
        if not poses or any(m is None for m in poses): raise ValueError('Unreadable docking poses')
        checks=physical_checks(poses,native,receptor,directory/'posebusters.csv')
        scores=[float(line.split()[3]) for line in (directory/'poses.pdbqt').read_text().splitlines() if line.startswith('REMARK VINA RESULT:')]
        rows=[]
        for i,pose in enumerate(poses):
            identity=canonical(pose)==canonical(native)
            rmsd=float(rdMolAlign.CalcRMS(Chem.RemoveHs(pose),Chem.RemoveHs(native))) if identity else None
            rows.append({'rank':i+1,'score_kcal_mol':scores[i],'rmsd_angstrom':rmsd,'identity_preserved':identity,**checks[i]})
        top=rows[0]
        result={'seed':seed,'top1_rmsd':top['rmsd_angstrom'],'best_top5_rmsd':min(r['rmsd_angstrom'] for r in rows[:5] if r['rmsd_angstrom'] is not None),'gate_pass':bool(top['identity_preserved'] and top['rmsd_angstrom']<2 and top['passed']),'poses':rows}
        report['runs'].append(result); save(BASE/'validation.json',report)
        print(json.dumps({k:v for k,v in result.items() if k!='poses'}),flush=True)
    successes=sum(r['gate_pass'] for r in report['runs'])
    passed=successes>=4 and native_checks['passed']
    report.update(status='passed' if passed else 'failed',passed=passed,successful_seeds=successes,reason=f'{successes}/5 top-ranked poses meet RMSD <2 Å and physical checks; native checks '+('pass.' if native_checks['passed'] else 'fail.'))
    save(BASE/'validation.json',report)
    print(report['reason'],flush=True)

if __name__=='__main__': main()
