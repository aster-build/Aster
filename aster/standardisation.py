"""What "the same compound" meant when a structure was read, written down.

Every structure Aster accepts goes through `aster.data.canonicalize`. That function
makes choices a chemist would want to know about: whether two tautomers count as one
compound, what happens to a salt, whether a charge is neutralised. Those choices
decide which rows count as duplicates, which compounds share an identity, and what
the fingerprint the model sees is computed from. They also depend on the RDKit
version, because RDKit's sanitisation and canonical SMILES have changed between
releases.

None of that was stored before. This module states the convention as data, and adds
a cheap behavioural check: a fixed set of probe structures, one per choice, whose
canonical output is hashed. Two campaigns whose convention and probe hash agree read
structures the same way on every case the probes cover. The probes cannot prove two
RDKit versions agree on every molecule; they catch the changes that matter most.
"""
from __future__ import annotations

import hashlib
import json

from rdkit import rdBase

from .data import canonicalize

# The convention `aster.data.canonicalize` implements. Change this identifier
# whenever canonicalize changes behaviour, so old and new records can be told apart.
CONVENTION_ID = 'aster-rdkit-sanitize-v1'

CONVENTION = {
    'id': CONVENTION_ID,
    'implemented_by': 'aster.data.canonicalize',
    'parser': 'RDKit MolFromSmiles with default sanitization',
    'tautomers': 'not canonicalised: each tautomer as written is its own compound, so '
                 '2-hydroxypyridine and 2-pyridone are two compounds',
    'resonance': 'only what RDKit sanitization does: aromatic rings are perceived, so the '
                 'Kekule forms of one ring are the same compound, and hypervalent nitro and '
                 'N-oxide groups are rewritten in charge-separated form. No other resonance '
                 'forms are merged.',
    'aromaticity_model': 'RDKit default',
    'charges': 'kept as written; nothing is neutralised',
    'fragments': 'refused: a structure with more than one fragment, such as a salt or a '
                 'mixture, is rejected rather than stripped to its largest piece',
    'stereochemistry': 'kept. The stored structure keeps enhanced (CX) stereo annotations; '
                       'the identity key keeps ordinary stereo and drops CX annotations',
    'isotopes': 'kept',
    'explicit_hydrogens': 'removed by sanitization',
    'identity_key': 'RDKit canonical isomeric SMILES',
}

# One probe per choice above. The value is what the choice is about, for the reader;
# the hash covers only the canonical output.
PROBES = (
    ('Oc1ccccn1', 'tautomer: 2-hydroxypyridine'),
    ('O=c1cccc[nH]1', 'tautomer: 2-pyridone'),
    ('C1=CC=CC=C1', 'resonance: Kekule benzene'),
    ('CN(=O)=O', 'resonance: hypervalent nitro'),
    ('CN(C)(C)=O', 'resonance: hypervalent N-oxide'),
    ('C[NH3+]', 'charge: protonated amine'),
    ('CC(=O)[O-]', 'charge: carboxylate'),
    ('C[C@H](N)O', 'stereo: tetrahedral'),
    ('C/C=C/C', 'stereo: double bond'),
    ('C[C@H](N)C(=O)O |&1:1|', 'stereo: enhanced CX group'),
    ('[2H]C(Cl)Cl', 'isotope'),
    ('[H]OC', 'explicit hydrogen'),
    ('Cc1ccc2[nH]ccc2c1', 'aromatic heterocycle'),
)


def probe_outputs():
    """Each probe's canonical structure and identity key under the running RDKit."""
    return [{'input': smiles, 'covers': covers,
             'structure': structure, 'identity': identity}
            for smiles, covers in PROBES
            for structure, identity in [canonicalize(smiles)]]


def probe_sha256(outputs=None):
    outputs = probe_outputs() if outputs is None else outputs
    payload = json.dumps([[o['input'], o['structure'], o['identity']] for o in outputs],
                         sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode()).hexdigest()


def current():
    """The convention in force right now: what it is, which RDKit applied it, and the probe hash."""
    return {'convention': CONVENTION_ID, 'description': CONVENTION,
            'rdkit_version': rdBase.rdkitVersion, 'probe_sha256': probe_sha256()}


def compare(first, second):
    """Can structures read under `first` be compared with ones read under `second`?

    Returns a verdict and the reasons. A missing record is never assumed to match:
    a campaign created before conventions were logged is reported as unknown.
    """
    if first is None or second is None:
        return {'verdict': 'unknown', 'comparable': None,
                'reasons': ['At least one side was recorded before the standardisation '
                            'convention was logged, so there is nothing to compare.']}
    reasons = []
    if first['convention'] != second['convention']:
        reasons.append(f"Different conventions: {first['convention']} and {second['convention']}. "
                       'Identities, duplicates and fingerprints may differ.')
    if first['probe_sha256'] != second['probe_sha256']:
        reasons.append('The probe structures canonicalise differently, so at least one choice '
                       '(tautomers, resonance, charge, stereo, isotopes or hydrogens) is '
                       'handled differently.')
    if reasons:
        return {'verdict': 'different', 'comparable': False, 'reasons': reasons}
    if first['rdkit_version'] != second['rdkit_version']:
        return {'verdict': 'same_on_probes', 'comparable': True,
                'reasons': [f"Same convention and identical probe output, but RDKit "
                            f"{first['rdkit_version']} and {second['rdkit_version']} differ. "
                            'The probes cover the main choices, not every molecule.']}
    return {'verdict': 'same', 'comparable': True, 'reasons': []}
