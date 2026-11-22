# Interaction audit — named interactions in place of a 4 Å cutoff

Added 2026-11-20 for queue item 10. Scope: the one target with a prepared
receptor, human dopamine transporter on PDB 8Y2G. This closes the PLIP deferral
`ROADMAP.md` records for milestone 7A.

## What changed

Every docked pose used to be described by a list of protein residues with a
heavy atom within 4 Å of it. That list is **proximity**: a residue appears
because it is close, whether it donates a hydrogen bond, stacks a ring,
coordinates an ion, or merely sits nearby. It also cannot show an interaction
that reaches past 4 Å, and a salt bridge or a π-stack routinely does.

`aster/interactions.py` now repairs the receptor with PDBFixer and asks PLIP
(Protein-Ligand Interaction Profiler) to **name** each interaction, recording
with every finding the tool versions and the distance and angle thresholds that
produced it. PLIP's thresholds are stored as data in each result, so there is no
longer one unexplained number in the code.

Interactions recorded: hydrophobic contact, hydrogen bond (with donor side,
donor-acceptor and donor-hydrogen-acceptor distance, and donor angle), water
bridge, salt bridge, π-stacking (with ring offset and type), π-cation, halogen
bond, metal complex.

## Decisions

- **Missing heavy atoms inside a residue are added; whole missing residues are
  not.** A truncated side chain in the pocket would silently remove a real
  interaction, so PDBFixer rebuilds it. A whole absent residue has no
  coordinates to rebuild from, and invented loop geometry could invent an
  interaction, so each unmodelled stretch is reported together with how close
  its flanking residues come to the ligand.
- **Protonation is PLIP's, through Open Babel, and nothing else adds hydrogens.**
  Two tools assigning hydrogens would make the hydrogen-bond list depend on
  which ran last. The ligand keeps the campaign's charge state, as the docking
  protocol already requires; no pH enumeration is claimed.
- **The audit uses the receptor that keeps the ions and glycans**, the same one
  the physical checks use, while Vina still scores against the protein-only
  receptor. The scoring approximation is unchanged; the audit is simply allowed
  to see atoms the scoring receptor cannot represent, which is what makes a
  sodium coordination reportable at all.
- **No fallback.** On a machine without PLIP and PDBFixer the audit returns
  status `unavailable` and names what is missing. It never relabels the
  proximity list as an interaction.
- **The proximity list stays, under the name `proximity_contacts`**, because it
  drives residue highlighting in the 3D viewer and because results saved before
  this change contain it. It is no longer the pose's account of how it binds.

## Reference result: the deposited 8Y2G complex

The deposited structure with its own crystal ligand (dexmethylphenidate,
component A1D5U) is the one case checkable against something other than Aster,
so it is the reference. Rebuild it with:

```sh
.venv-docking/bin/python scripts/audit_interactions.py
```

Full record: [`docking/interaction-audit-8y2g.json`](docking/interaction-audit-8y2g.json).

| Named interaction | Residue | Geometry |
|---|---|---|
| Hydrogen bond (ligand donor, side chain, strong) | ASP A:79 | 3.54 Å donor-acceptor, 2.54 Å donor-H-acceptor, 164° |
| π-stacking (T-shaped) | TYR A:156 | 5.13 Å, 72°, 1.24 Å ring offset |
| Hydrophobic contact | PHE A:76 | 3.63 Å |
| Hydrophobic contact | VAL A:152 | 3.62 Å |
| Hydrophobic contact | PHE A:326 | 3.72 Å |

Against the 4 Å proximity list in the replay manifest:

- 10 residues are within 4 Å; **5 of them carry a named interaction**.
- 5 are proximity only: A:77, A:320, A:321, A:322, A:422. SER A:422 is the
  closest contact in the whole proximity list at 2.83 Å, and it is a protein
  backbone oxygen against a ligand **carbon**, which is not a hydrogen bond.
  Read as binding evidence, the old list put its strongest-looking number on a
  contact that names nothing.
- 0 named interactions fall outside the cutoff on this structure. The audit
  can report them, and on a docked pose it may; here it does not.
- The repair changed nothing: no nonstandard residue, no missing heavy atom, no
  missing terminal atom. One unmodelled stretch of 17 residues (between ASP
  A:191 and GLY A:209) is reported and not built; its flanking residues are
  30.4 Å from the ligand, so it cannot hide a pocket interaction.
- No sodium coordination was named, although both ions are retained and sit
  4.41 and 6.58 Å from the ligand: PLIP's metal distance limit is 3.0 Å. The
  ions are kept in the audited receptor so that a pose reaching one would be
  reported, not because this reference reports one.

## Limits

- One structure, one deposited ligand. This checks that the audit names
  chemically sensible interactions on a known complex; it is not a benchmark of
  interaction prediction, and it says nothing about poses Vina produces.
- A named interaction is geometry plus assigned protonation. It is not measured
  binding, not a bond strength, and not evidence that the compound binds.
- Open Babel protonating the ligand neutral rather than cationic is why ASP:79
  is named a hydrogen bond here and not a salt bridge. The distinction is a
  protonation assumption, recorded, not a measurement.
- Campaign ranking, measurements, constraints and committed batches are
  untouched, as with every part of the docking pilot.
- The pose path in `scripts/dock_candidate.py` is wired and unit-tested, but it
  has not been run end to end: that needs the Vina binary and the validated
  receptor in `artifacts/docking/`, which exist on Nicole's machine and not in
  the build container.
