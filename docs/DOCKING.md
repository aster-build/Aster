# Milestone 7B — exploratory DAT docking

Implemented locally on 2026-10-14. The dashboard inspector links to **Explore 3D docking**. In `/replay`, choose Score candidates or Select batch, choose a compound, and click **Dock selected compound**. Jobs survive page reloads; results and validation checks are saved. Green candidate poses overlay the violet experimental ligand. Select alternatives or hide the overlay to compare. Contact lists show shared/new residues within 4 Å; these are proximity measurements, not hydrogen-bond assignments or energetic explanations.

## What the validation found

Known-site, rigid-receptor AutoDock Vina 1.2.7 redocking of dexmethylphenidate into human DAT 8Y2G. Fresh RDKit ETKDGv3 conformers; Meeko 0.8.0; exhaustiveness 32, two CPUs, 24 Å cube. RMSD is symmetry-aware over heavy atoms **without aligning the ligand**, in the protein coordinate frame. PoseBusters 0.6.5 checks chemical and physical validity against the deposited receptor.

| Seed | Top-1 RMSD (Å) | Best top-5 RMSD (Å) | Gate |
|---|---:|---:|---|
| 17 | 1.145 | 1.145 | Pass |
| 29 | 0.995 | 0.995 | Pass |
| 43 | 1.090 | 1.090 | Pass |
| 71 | 3.644 | 1.008 | Fail |
| 101 | 1.105 | 1.105 | Pass |

**4/5 passed**, meeting the threshold written before results. All top-1 poses passed the chemical/physical checks, but seed 71 did not recover the reference pose. Native-reference checks also passed. This is one ligand in one known pocket, not an independent transfer benchmark. Alternative poses and the failed seed are retained in [the full report](docking/validation-v1.json).

Preparation retained all 4,302 protein heavy atoms and their coordinate set. Meeko exchanged equivalent terminal VAL620 O/OXT names. Remote glycans could not be templated; sodium could not be typed. The explicit baseline omits both glycans and all three ions from scoring. Native-ligand distances: glycans 32.19/38.29 Å; chloride 7.78 Å; sodium 4.41/6.58 Å. Physical checks retain ions and glycans. **The sodium-dependent transporter is not fully modeled by this protein-only approximation.** See [predeclared protocol and preparation decisions](DOCKING_PROTOCOL.md) and [atom audit](docking/preparation-audit.json).

## Product limits

- Only the verified public DAT demo is enabled. Imported campaigns need explicit target/receptor verification.
- One fragment, at most 80 heavy atoms, specified tetrahedral stereochemistry. Unspecified stereocenters are rejected rather than silently choosing an isomer. Ligand preparation failures remain explicit.
- Candidate docking uses seed 17 and the validated search settings. It preserves the campaign SMILES charge state; no pH-dependent protonation/tautomer enumeration is claimed.
- Each pose has chemical/physical checks; failed poses are listed but not rendered. Geometry-based contact overlap does not establish binding or potency.
- One local worker, up to four queued/running jobs, two Vina threads per job, 30-minute wall limit; timeout kills the worker process group. Duplicate requests reuse a saved job for the same validation version. Server restarts mark interrupted work failed; completed results persist.
- Inputs, executables, protocol and worker hashes invalidate old validation when changed. Docking does not write campaign measurements, selection order, constraints or committed batches. Scores in kcal/mol are not pKi or binding probabilities.
- Local prototype only. Production requires authentication, durable workers, resource accounting and shared artifact storage.

## Reproduce and inspect

The isolated environment is `.venv-docking`, with [pinned dependencies](../requirements-docking.lock.txt). Install with `python3 -m venv .venv-docking` then `.venv-docking/bin/python -m pip install -r requirements-docking.lock.txt`. The official Mac ARM Vina 1.2.7 binary is stored at `artifacts/docking/tools/vina`; its hash is in the report. Other platforms require their matching binary and a new validation record.

Preparation inputs/logs and the native SDF are in `artifacts/docking/`. The pinned source mmCIF is in `apps/web/public/structures/8y2g`. Native ligand source: RCSB ModelServer `/v1/8y2g/ligand?auth_asym_id=A&auth_seq_id=701&encoding=sdf`.

Convert the pinned mmCIF to PDB with Gemmi, then prepare with:

```sh
.venv-docking/bin/mk_prepare_receptor.py --read_pdb artifacts/docking/source.pdb \
  -o artifacts/docking/receptor -p -j --write_pdb artifacts/docking/receptor.pdb \
  --delete_residues A:701,702,703,704,705,706
.venv-docking/bin/python scripts/validate_docking.py
```

The validation script writes every seed's initial ligand, Vina log/PDBQT, exported SDF, PoseBusters CSV and aggregate `artifacts/docking/validation.json`. Candidate jobs live under `artifacts/dashboard/docking/<job-id>/`, separately from campaign SQLite files. API: `GET /docking/validation`, `GET/POST /campaigns/{id}/docking`, `GET /campaigns/{id}/docking/{job-id}`. Dashboard uses the existing same-origin proxy.

## Next scientific gate

Freeze this result. Test independent compatible DAT complexes (cross-docking), improve ion-aware receptor handling, and compare predeclared protonation/tautomer alternatives. Do not select a new protocol on the same five-seed result and call it blind validation. Only after transfer testing should structural evidence be evaluated for improving next-compound selection.

## Primary resources

- [AutoDock Vina basic docking](https://autodock-vina.readthedocs.io/en/latest/docking_basic.html) and [official 1.2.7 release](https://github.com/ccsb-scripps/AutoDock-Vina/releases/tag/v1.2.7).
- [Meeko receptor preparation](https://meeko.readthedocs.io/en/develop/cli_rec_prep.html).
- [PoseBusters paper](https://doi.org/10.1039/D3SC04185A) and [software](https://github.com/maabuu/posebusters).
- [RCSB 8Y2G](https://www.rcsb.org/structure/8Y2G), [RDKit](https://www.rdkit.org/docs/), [Mol*](https://molstar.org/).

## Implementation verification

- 60 Python tests passed, including validation gating, changed-input invalidation, job persistence/deduplication, campaign isolation, and interrupted-job recovery. One existing Starlette/httpx deprecation warning remains.
- Next.js production build and TypeScript passed.
- Actual user-triggered jobs for CHEMBL238_Ki:713 and CHEMBL238_Ki:698 completed in about 19 seconds each on this machine, with 10/10 poses passing the implemented checks for each. This is workflow verification, not experimental confirmation of these candidate poses.
- Browser verification covered saved-result restoration, candidate switching, alternative-pose selection, hiding/restoring the overlay, no viewer errors, and a 390-pixel mobile viewport without horizontal overflow. Screenshots: `artifacts/docking/verified-desktop.png` and `verified-mobile.png`.
- CHEMBL238_Ki:719 was explicitly rejected for an unspecified stereocenter; no arbitrary isomer was generated.
