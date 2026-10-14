"""Bounded worker invoked by the local API, using the validated 8Y2G recipe."""
import argparse
import json
from pathlib import Path
import numpy as np
from rdkit import Chem
from posebusters import PoseBusters
from validate_docking import ROOT, BASE, STRUCT, prepare_ligand, run, canonical, save, digest
from prepare_structure import atoms_from_pinned_cif

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('directory',type=Path); args=parser.parse_args()
    directory=args.directory.resolve(); request=json.loads((directory/'request.json').read_text())
    validation=json.loads((BASE/'validation.json').read_text())
    if not validation.get('passed') or digest(BASE/'validation.json')!=request['validation_sha256']:
        raise ValueError('Validation is unavailable or changed; request a fresh job')
    for path,expected in validation['hashes'].items():
        if digest(ROOT/path)!=expected: raise ValueError('Validated inputs changed')
    molecule=prepare_ligand(request['smiles'],17,directory)
    run([BASE/'tools/vina','--receptor',BASE/'receptor.pdbqt','--ligand',directory/'input.pdbqt','--config',BASE/'box.txt','--seed',17,'--cpu',2,'--exhaustiveness',32,'--num_modes',10,'--out',directory/'poses.pdbqt'],directory/'vina.log')
    run([ROOT/'.venv-docking/bin/mk_export.py',directory/'poses.pdbqt','-s',directory/'poses.sdf'],directory/'export.log')
    poses=list(Chem.SDMolSupplier(str(directory/'poses.sdf'),removeHs=True))
    if not poses or any(m is None for m in poses): raise ValueError('Unreadable poses')
    frame=PoseBusters(config='dock').bust(poses,mol_cond=BASE/'validation-receptor.pdb')
    frame.to_csv(directory/'posebusters.csv')
    scores=[float(line.split()[3]) for line in (directory/'poses.pdbqt').read_text().splitlines() if line.startswith('REMARK VINA RESULT:')]
    atoms=[a for a in atoms_from_pinned_cif((STRUCT/'complex.cif').read_text()) if a['label_entity_id']=='1']
    xyz=np.array([a['xyz'] for a in atoms]); results=[]
    for i,(pose,(_,row)) in enumerate(zip(poses,frame.iterrows())):
        checks={k:(bool(v) if isinstance(v,(bool,np.bool_)) else None) for k,v in row.items()}
        checks['chemical_identity_preserved']=canonical(pose)==canonical(molecule)
        coordinate_mol=Chem.Mol(pose); Chem.RemoveStereochemistry(coordinate_mol); Chem.AssignStereochemistryFrom3D(coordinate_mol)
        checks['coordinate_stereochemistry_preserved']=canonical(coordinate_mol)==canonical(molecule)
        coords=pose.GetConformer().GetPositions()
        distances=np.linalg.norm(xyz[:,None,:]-coords[None,:,:],axis=2)
        contacts={}
        for j,a in enumerate(atoms):
            nearest=int(distances[j].argmin()); distance=float(distances[j,nearest]); key=a['auth_seq_id']
            if distance<=4 and (key not in contacts or distance<contacts[key]['distance']):
                contacts[key]={'residue':a['label_comp_id'],'sequence':int(key),'chain':a['auth_asym_id'],'protein_atom':a['label_atom_id'],'ligand_atom_index':nearest,'distance':distance}
        failures=[k for k,v in checks.items() if v is not True]
        results.append({'rank':i+1,'score_kcal_mol':scores[i],'passed':not failures,'failed_checks':failures,'checks':checks,'contacts':sorted(contacts.values(),key=lambda c:c['distance']),'sdf':Chem.MolToMolBlock(pose)+'\n$$$$\n'})
    save(directory/'result.json',{'compound_id':request['compound_id'],'smiles':request['smiles'],'reference':'8Y2G','validation_sha256':request['validation_sha256'],'seed':17,'poses':results,'cross_docking_validated':False,'limitations':['Protein-only rigid-receptor scoring; ions omitted.','Single seed per candidate; protonation supplied by the campaign, not pH enumeration.','Docking score is not pKi, a binding probability or evidence of experimental binding.','No cross-docking or prospective validation; campaign ranking is unchanged.']})

if __name__=='__main__': main()
