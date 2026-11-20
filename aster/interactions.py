"""Named protein-ligand interactions, in place of a bare distance cutoff.

The docking worker used to report every protein residue with a heavy atom within
4 Angstrom of the pose. That is proximity, not interaction: it cannot say whether
a residue donates a hydrogen bond, stacks a ring, or simply sits nearby. This
module repairs the receptor with PDBFixer and asks PLIP to name the interactions,
and records which tool, which version and which distance and angle thresholds
produced each one.

Nothing here changes campaign ranking, measurements or committed batches, and a
named interaction is still geometry: it is evidence about a pose, not about
experimental binding.

PLIP, PDBFixer and OpenMM live only in the docking environment, so every import
of them is deferred. On a machine without them `tooling()` reports what is
missing and `audit` returns status 'unavailable' rather than quietly falling back
to the old distance rule.
"""
import json
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version

METHOD = 'plip-pdbfixer-v1'

# PLIP groups its findings on the binding-site object under these attributes. The
# second element is the interaction name Aster stores, the third says which side
# of the interaction the listed residue is on where PLIP splits it that way.
PLIP_SOURCES = (
    ('hydrophobic_contacts', 'hydrophobic', None),
    ('hbonds_pdon', 'hydrogen_bond', 'protein_donor'),
    ('hbonds_ldon', 'hydrogen_bond', 'ligand_donor'),
    ('water_bridges', 'water_bridge', None),
    ('saltbridge_lneg', 'salt_bridge', 'ligand_negative'),
    ('saltbridge_pneg', 'salt_bridge', 'protein_negative'),
    ('pistacking', 'pi_stacking', None),
    ('pication_laro', 'pi_cation', 'ligand_aromatic'),
    ('pication_paro', 'pi_cation', 'protein_aromatic'),
    ('halogen_bonds', 'halogen_bond', None),
    ('metal_complexes', 'metal_complex', None),
)

# Fields copied from a PLIP interaction when it has them. PLIP's records differ by
# interaction type, so each is optional and a missing one is left out rather than
# guessed.
PLIP_FIELDS = (
    ('restype', 'residue'), ('resnr', 'sequence'), ('reschain', 'chain'),
    ('distance', 'distance_angstrom'), ('distance_ah', 'donor_hydrogen_acceptor_angstrom'),
    ('distance_ad', 'donor_acceptor_angstrom'), ('distance_aw', 'acceptor_water_angstrom'),
    ('distance_dw', 'donor_water_angstrom'), ('angle', 'angle_degrees'),
    ('don_angle', 'donor_angle_degrees'), ('water_angle', 'water_angle_degrees'),
    ('offset', 'ring_offset_angstrom'), ('type', 'subtype'), ('sidechain', 'sidechain'),
    ('protisdon', 'protein_is_donor'), ('protispos', 'protein_is_positive'),
    ('target', 'metal_target'), ('location', 'metal_location'),
    ('coordination', 'metal_coordination'), ('num', 'metal_coordination_number'),
)

PACKAGES = ('plip', 'pdbfixer', 'openmm', 'openbabel-wheel')


def tooling():
    """Which audit tools are installed, and their versions.

    'available' is False when PLIP or PDBFixer cannot be imported. Versions are
    recorded even when one is missing, so a stored audit says what produced it.
    """
    versions, missing = {}, []
    for name in PACKAGES:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = None
    for module in ('plip.structure.preparation', 'pdbfixer'):
        try:
            import_module(module)
        except Exception as error:               # pragma: no cover - environment dependent
            missing.append(f'{module} ({type(error).__name__})')
    return {'method': METHOD, 'available': not missing, 'versions': versions, 'missing': missing}


def thresholds():
    """The distance and angle cutoffs PLIP will actually use, as data.

    The point of the audit is that there is no single magic number any more, so
    the numbers that remain are written down beside the findings.
    """
    config = import_module('plip.basic.config')
    names = (
        'BS_DIST', 'HYDROPH_DIST_MAX', 'HBOND_DIST_MAX', 'HBOND_DON_ANGLE_MIN',
        'PISTACK_DIST_MAX', 'PISTACK_ANG_DEV', 'PISTACK_OFFSET_MAX',
        'PICATION_DIST_MAX', 'SALTBRIDGE_DIST_MAX', 'HALOGEN_DIST_MAX',
        'HALOGEN_ACC_ANGLE', 'HALOGEN_DON_ANGLE', 'HALOGEN_ANGLE_DEV',
        'WATER_BRIDGE_MINDIST', 'WATER_BRIDGE_MAXDIST', 'METAL_DIST_MAX',
    )
    return {name: getattr(config, name) for name in names if hasattr(config, name)}


def _value(raw):
    if isinstance(raw, bool) or raw is None or isinstance(raw, (int, str)):
        return raw
    if isinstance(raw, float):
        return round(raw, 3)
    return str(raw)


def normalise(site, ligand_residue='LIG'):
    """Turn one PLIP binding site into plain records, one per named interaction.

    Kept separate from running PLIP so it can be tested without the docking
    environment installed: anything with the documented attributes will do.
    """
    found = []
    for attribute, kind, role in PLIP_SOURCES:
        for item in getattr(site, attribute, None) or []:
            record = {'interaction': kind}
            if role:
                record['role'] = role
            for source, name in PLIP_FIELDS:
                if hasattr(item, source):
                    value = _value(getattr(item, source))
                    if value is not None:
                        record[name] = value
            record['ligand_residue'] = ligand_residue
            found.append(record)
    found.sort(key=lambda r: (r.get('chain') or '', r.get('sequence') or 0,
                              r['interaction'], r.get('distance_angstrom') or 0.0))
    return found


def residues(interactions):
    """The residues that have at least one named interaction, with their kinds."""
    grouped = {}
    for record in interactions:
        key = (record.get('chain'), record.get('sequence'), record.get('residue'))
        grouped.setdefault(key, set()).add(record['interaction'])
    return [{'chain': chain, 'sequence': sequence, 'residue': residue,
             'interactions': sorted(kinds)}
            for (chain, sequence, residue), kinds in sorted(
                grouped.items(), key=lambda pair: (pair[0][0] or '', pair[0][1] or 0))]


def compare_to_proximity(interactions, contacts):
    """How the named interactions differ from a plain distance cutoff.

    `contacts` is the old proximity list: dicts with 'chain', 'sequence' and
    'distance'. Returns which residues the cutoff listed without any named
    interaction, which named interactions the cutoff missed, and which agree.
    """
    named = {(record.get('chain'), record.get('sequence')) for record in interactions}
    near = {(contact.get('chain'), int(contact['sequence'])) for contact in contacts}
    def label(keys):
        return [{'chain': chain, 'sequence': sequence} for chain, sequence in sorted(
            keys, key=lambda pair: (pair[0] or '', pair[1] or 0))]
    return {'named_interaction_count': len(interactions),
            'residues_with_named_interaction': len(named),
            'residues_within_cutoff': len(near),
            'proximity_only': label(near - named),
            'named_beyond_cutoff': label(named - near),
            'agreed': label(named & near)}


def repair_receptor(pdb_text, add_missing_residues=False):
    """Repair a receptor with PDBFixer, and report every change it made.

    Missing heavy atoms inside residues that are present are added, because a
    truncated side chain in the pocket would silently remove a real interaction.
    Whole missing residues are reported but NOT built by default: their
    coordinates would be invented, and invented loop geometry could invent
    interactions. Hydrogens are left to PLIP, which protonates with Open Babel,
    so that only one tool decides protonation.
    """
    from io import StringIO
    pdbfixer = import_module('pdbfixer')
    app = import_module('openmm.app')
    fixer = pdbfixer.PDBFixer(pdbfile=StringIO(pdb_text))
    fixer.findMissingResidues()
    missing_residues = [{'chain_index': key[0], 'after_residue_index': key[1],
                         'residues': list(value)}
                        for key, value in sorted(fixer.missingResidues.items())]
    if not add_missing_residues:
        fixer.missingResidues = {}
    fixer.findNonstandardResidues()
    nonstandard = [{'residue': residue.name, 'chain': residue.chain.id,
                    'sequence': residue.id, 'standard_form': standard}
                   for residue, standard in fixer.nonstandardResidues]
    fixer.findMissingAtoms()
    added_atoms = [{'residue': residue.name, 'chain': residue.chain.id,
                    'sequence': residue.id, 'atoms': [atom.name for atom in atoms]}
                   for residue, atoms in fixer.missingAtoms.items()]
    added_terminals = [{'residue': residue.name, 'chain': residue.chain.id,
                        'sequence': residue.id, 'atoms': [atom.name for atom in atoms]}
                       for residue, atoms in fixer.missingTerminals.items()]
    fixer.addMissingAtoms()
    out = StringIO()
    app.PDBFile.writeFile(fixer.topology, fixer.positions, out, keepIds=True)
    report = {'tool': 'pdbfixer', 'version': tooling()['versions']['pdbfixer'],
              'missing_residues_reported': missing_residues,
              'missing_residues_built': bool(add_missing_residues) and bool(missing_residues),
              'nonstandard_residues_reported': nonstandard,
              'heavy_atoms_added': added_atoms,
              'terminal_atoms_added': added_terminals,
              'hydrogens_added': False}
    return out.getvalue(), report


def ligand_pdb_block(molecule, residue_name='LIG', chain='Z', sequence=900):
    """Write a pose as HETATM records so PLIP treats it as the ligand."""
    Chem = import_module('rdkit.Chem')
    tagged = Chem.Mol(molecule)
    for index, atom in enumerate(tagged.GetAtoms()):
        info = Chem.AtomPDBResidueInfo()
        info.SetResidueName(residue_name.ljust(3)[:3])
        info.SetResidueNumber(int(sequence))
        info.SetChainId(chain)
        info.SetIsHeteroAtom(True)
        info.SetOccupancy(1.0)
        info.SetTempFactor(0.0)
        info.SetName(f'{atom.GetSymbol():>2}{index + 1:<2}'[:4])
        atom.SetMonomerInfo(info)
    return Chem.MolToPDBBlock(tagged, flavor=4)


def build_complex(receptor_pdb, ligand_block):
    """One PDB file holding the receptor and the pose, which is what PLIP reads."""
    keep = [line for line in receptor_pdb.splitlines()
            if line.startswith(('ATOM', 'HETATM', 'TER'))]
    ligand = [line for line in ligand_block.splitlines() if line.startswith('HETATM')]
    if not ligand:
        raise ValueError('The pose produced no HETATM records to audit')
    return '\n'.join(keep + ligand + ['END', ''])


def audit(receptor_pdb, molecule, receptor_label=None, repair=True,
          ligand_residue='LIG'):
    """Name the interactions between one docked pose and one receptor."""
    return audit_block(receptor_pdb, ligand_pdb_block(molecule, ligand_residue),
                       receptor_label=receptor_label, repair=repair,
                       ligand_residue=ligand_residue)


def audit_block(receptor_pdb, ligand_block, receptor_label=None, repair=True,
                ligand_residue='LIG'):
    """Name the interactions for a ligand already written as PDB HETATM records.

    Used both for a docked pose and for a deposited ligand taken straight out of
    a crystal structure, so the same code path produces the reference audit.

    Returns a record with status 'complete' and the named interactions, or
    status 'unavailable' with the missing tools when the docking environment does
    not have PLIP and PDBFixer. It never falls back to a distance cutoff and
    calls the result an interaction.
    """
    state = tooling()
    base = {'method': METHOD, 'receptor': receptor_label, 'versions': state['versions']}
    if not state['available']:
        return {**base, 'status': 'unavailable', 'missing': state['missing'],
                'reason': 'PLIP and PDBFixer are installed only in the docking environment.'}
    try:
        prepared, repair_report = (repair_receptor(receptor_pdb) if repair
                                   else (receptor_pdb, {'tool': None, 'skipped': True}))
        complex_pdb = build_complex(prepared, ligand_block)
        preparation = import_module('plip.structure.preparation')
        structure = preparation.PDBComplex()
        structure.load_pdb(complex_pdb, as_string=True)
        structure.analyze()
        sites = [site for key, site in structure.interaction_sets.items()
                 if key.startswith(f'{ligand_residue}:')]
        if len(sites) != 1:
            return {**base, 'status': 'failed',
                    'reason': f'PLIP found {len(sites)} binding sites for {ligand_residue}, expected one.'}
        interactions = normalise(sites[0], ligand_residue)
        return {**base, 'status': 'complete', 'repair': repair_report,
                'thresholds': thresholds(), 'interactions': interactions,
                'residues': residues(interactions),
                'limitations': [
                    'Named interactions are geometry and protonation assignments, not measured binding.',
                    'Receptor hydrogens are placed by PLIP via Open Babel, not by pH enumeration.',
                    'Whole missing residues are reported, not built, so a gap near the pocket can hide an interaction.',
                ]}
    except Exception as error:                   # pragma: no cover - environment dependent
        return {**base, 'status': 'failed',
                'reason': f'{type(error).__name__}: {error}'}


def main(argv=None):                             # pragma: no cover - thin CLI
    """Audit one receptor and one ligand file: python -m aster.interactions ..."""
    import argparse
    from pathlib import Path
    Chem = import_module('rdkit.Chem')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--receptor', type=Path, required=True, help='receptor PDB file')
    parser.add_argument('--ligand', type=Path, required=True, help='pose as SDF or MOL file')
    parser.add_argument('--out', type=Path, help='write the audit here instead of stdout')
    parser.add_argument('--no-repair', action='store_true', help='skip the PDBFixer repair')
    args = parser.parse_args(argv)
    molecule = next(iter(Chem.SDMolSupplier(str(args.ligand), removeHs=True)), None)
    if molecule is None:
        raise SystemExit(f'Could not read a molecule from {args.ligand}')
    report = audit(args.receptor.read_text(), molecule,
                   receptor_label=str(args.receptor), repair=not args.no_repair)
    text = json.dumps(report, indent=2)
    if args.out:
        args.out.write_text(text + '\n')
    else:
        print(text)
    return 0 if report['status'] == 'complete' else 1


if __name__ == '__main__':                       # pragma: no cover
    raise SystemExit(main())
