"""Rebuild derived evidence from the pinned 8Y2G mmCIF; no network or docking."""
import csv
import hashlib
import json
import math
import shlex
from pathlib import Path
from rdkit import Chem

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'apps/web/public/structures/8y2g'

def atoms_from_pinned_cif(text):
    # 8Y2G's atom_site table has one record per line. Fail on a changed format.
    lines = [line.strip() for line in text.splitlines()]
    start = next(i for i, line in enumerate(lines) if line == '_atom_site.group_PDB')
    fields = []
    while lines[start].startswith('_atom_site.'):
        fields.append(lines[start].split('.')[1]); start += 1
    atoms = []
    for line in lines[start:]:
        if line.startswith('#'): break
        values = shlex.split(line)
        if len(values) != len(fields): raise ValueError('Unexpected atom_site row format')
        row = dict(zip(fields, values))
        if row['pdbx_PDB_model_num'] != '1' or row['type_symbol'] in ('H', 'D'): continue
        row['xyz'] = [float(row['Cartn_'+a]) for a in 'xyz']
        atoms.append(row)
    return atoms

def build():
    atoms = atoms_from_pinned_cif((BASE/'complex.cif').read_text())
    ligand = [a for a in atoms if a['label_comp_id'] == 'A1D5U']
    protein = [a for a in atoms if a['label_entity_id'] == '1']
    assert len(ligand) == 17 and len(protein) > 4000
    contacts = {}
    for p in protein:
        l = min(ligand, key=lambda a: math.dist(a['xyz'],p['xyz']))
        distance = math.dist(p['xyz'],l['xyz'])
        if distance > 4.0: continue
        key = (p['auth_asym_id'],p['auth_seq_id'])
        if key in contacts and contacts[key]['distance'] < distance: continue
        contacts[key] = dict(residue=p['label_comp_id'],chain=p['auth_asym_id'],sequence=int(p['auth_seq_id']),label_sequence=int(p['label_seq_id']),distance=distance,protein_atom=p['label_atom_id'],ligand_atom=l['label_atom_id'],protein_xyz=p['xyz'],ligand_xyz=l['xyz'])
    source = json.loads((BASE/'ligand-source.json').read_text())
    smiles = source['rcsb_chem_comp_descriptor']['SMILES_stereo']
    canonical = lambda s: Chem.MolToSmiles(Chem.MolFromSmiles(s),isomericSmiles=True)
    exact = []
    for filename in ['measured.csv','candidates.csv']:
        for row in csv.DictReader((ROOT/'examples/dashboard'/filename).open()):
            if canonical(row['smiles']) == canonical(smiles): exact.append(row['compound_id'])
    manifest = dict(pdb_id='8Y2G',title='Human dopamine transporter · dexmethylphenidate',source_url='https://www.rcsb.org/structure/8Y2G',retrieved='2026-10-14',method='Cryo-EM',resolution_angstrom=2.83,uniprot='Q01959',species='Homo sapiens',protein_chain='A',ligand_component='A1D5U',ligand_name='Dexmethylphenidate',ligand_smiles=smiles,ligand_inchikey=source['rcsb_chem_comp_descriptor']['InChIKey'],ligand_label_chain=ligand[0]['label_asym_id'],ligand_auth_chain=ligand[0]['auth_asym_id'],ligand_auth_sequence=int(ligand[0]['auth_seq_id']),ligand_center=[sum(a['xyz'][i] for a in ligand)/len(ligand) for i in range(3)],contacts=sorted(contacts.values(),key=lambda c:c['distance']),exact_demo_matches=exact,contact_definition='Minimum heavy-atom distance ≤ 4 Å; geometric proximity, not a hydrogen-bond assignment or energetic explanation.',construct_note='Engineered 562-residue deposited construct; 545 modeled residues. RCSB reports one sequence conflict; inspect source metadata before mechanistic interpretation.',evidence_type='experimental reference complex',files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in BASE.glob('*') if p.suffix in ('.cif','.json') and p.name!='manifest.json'})
    (BASE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'contacts':len(contacts),'exact_demo_matches':exact,'ligand_chain':manifest['ligand_label_chain']}))

if __name__ == '__main__': build()
