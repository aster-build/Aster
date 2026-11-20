"""Reference interaction audit on the pinned 8Y2G complex; no network, no docking.

Runs `aster.interactions` on the deposited dopamine-transporter structure with
its own crystal ligand in place, and compares the named interactions with the
4 Angstrom proximity list the replay manifest still carries. The deposited
complex is the one case where the answer is independently checkable, so it is
the reference the pose audit is read against.

Needs the docking environment (PLIP, PDBFixer, OpenMM, RDKit):

    .venv-docking/bin/python scripts/audit_interactions.py
"""
import argparse
import json
from pathlib import Path

from aster import interactions
from prepare_structure import atoms_from_pinned_cif

ROOT = Path(__file__).resolve().parents[1]
STRUCT = ROOT / 'apps/web/public/structures/8y2g'
OUT = ROOT / 'docs/docking/interaction-audit-8y2g.json'
LIGAND = 'A1D5U'
# The deposited component id is five characters and the PDB format reserves three
# for a residue name, so the ligand is written under a legal placeholder and the
# real component id is recorded beside it.
LIGAND_AS = 'LIG'
# Ions and the glycans are kept for the audit even though Vina scoring omits them:
# the sodium sites are 4.41 and 6.58 Angstrom from the native ligand, and PLIP can
# name a metal coordination that the scoring receptor cannot represent at all.
RECEPTOR_ENTITIES = ('1', '3', '4', '5')


def pdb_line(atom, serial, residue_name=None):
    name = atom['label_atom_id'].strip('"')
    element = atom['type_symbol']
    # A one- or two-letter element starts in column 14; a four-character name fills
    # columns 13 to 16. Getting this wrong makes PDBFixer and PLIP misread atoms.
    field = name.ljust(4) if len(name) >= 4 else f' {name:<3}'
    x, y, z = atom['xyz']
    return (f"{atom['group_PDB']:<6}{serial:>5} {field}{' '}"
            f"{(residue_name or atom['label_comp_id']):>3} {atom['auth_asym_id']:>1}"
            f"{int(atom['auth_seq_id']):>4}{' ':<4}"
            f"{x:>8.3f}{y:>8.3f}{z:>8.3f}"
            f"{float(atom['occupancy']):>6.2f}{float(atom['B_iso_or_equiv']):>6.2f}"
            f"{' ':<10}{element:>2}")


def polymer_sequence(text, entity='1'):
    """The deposited polymer sequence from the mmCIF `entity_poly_seq` table.

    PDBFixer reads SEQRES records to notice that a residue is missing entirely.
    Hand-written coordinate records carry no SEQRES, so without this the repair
    report can only ever say "nothing missing", which would be misleading.
    """
    lines = [line.strip() for line in text.splitlines()]
    start = next(i for i, line in enumerate(lines) if line == '_entity_poly_seq.entity_id')
    fields = []
    while lines[start].startswith('_entity_poly_seq.'):
        fields.append(lines[start].split('.')[1]); start += 1
    residues = []
    for line in lines[start:]:
        if line.startswith('#'): break
        row = dict(zip(fields, line.split()))
        if row['entity_id'] == entity: residues.append(row['mon_id'])
    return residues


def seqres_records(residues, chain='A'):
    out = []
    for index in range(0, len(residues), 13):
        chunk = residues[index:index + 13]
        out.append(f'SEQRES {index // 13 + 1:>3} {chain:>1} {len(residues):>4}  '
                   + ' '.join(f'{name:>3}' for name in chunk))
    return out


def split_complex(text):
    """Receptor records and ligand records, written as PDB lines."""
    atoms = atoms_from_pinned_cif(text)
    polymer, heteroatoms, ligand, serial = [], [], [], 0
    for atom in atoms:
        if atom['label_comp_id'] == LIGAND:
            target = ligand
        elif atom['label_entity_id'] == '1':
            target = polymer
        elif atom['label_entity_id'] in RECEPTOR_ENTITIES:
            target = heteroatoms
        else:
            continue
        serial += 1
        target.append(pdb_line(atom, serial, LIGAND_AS if target is ligand else None))
    # The glycans and ions are written after a TER record. Without it they join the
    # protein chain, and PDBFixer then cannot align the chain to the SEQRES
    # sequence, so it reports no unmodelled residues at all.
    header = seqres_records(polymer_sequence(text))
    return ('\n'.join(header + polymer + ['TER'] + heteroatoms + ['TER', 'END', '']),
            '\n'.join(ligand + ['END', '']))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args(argv)
    receptor, ligand = split_complex((STRUCT / 'complex.cif').read_text())
    manifest = json.loads((STRUCT / 'manifest.json').read_text())
    report = interactions.audit_block(
        receptor, ligand, receptor_label='8Y2G deposited receptor, ions and glycans retained',
        ligand_residue=LIGAND_AS)
    report['reference'] = {
        'pdb_id': manifest['pdb_id'], 'ligand_component': manifest['ligand_component'],
        'ligand_residue_written': LIGAND_AS,
        'receptor_entities': list(RECEPTOR_ENTITIES),
        'ligand_source': 'deposited coordinates, not a docked pose',
        'proximity_definition': manifest['contact_definition']}
    if report['status'] == 'complete':
        report['versus_proximity'] = interactions.compare_to_proximity(
            report['interactions'], manifest['contacts'])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'interactions'}, indent=2)[:4000])
    print(f'{len(report.get("interactions", []))} named interactions written to {args.out}')
    return 0 if report['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
