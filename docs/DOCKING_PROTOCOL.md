# Docking validation protocol v1 — fixed before results

Date: 2026-10-14. Scope: exploratory rigid-receptor DAT docking, not affinity prediction.

Primary reference: pinned RCSB 8Y2G, CCD A1D5U (dexmethylphenidate), human DAT Q01959. Preserve the protein frame. Construct, source hashes and geometric contacts are documented in `apps/web/public/structures/8y2g/manifest.json`.

## Predeclared test

- Use AutoDock Vina 1.2.7, Meeko 0.8.0; record exact remaining dependency versions.
- Prepare deposited receptor coordinates, documenting missing residues, rejected templates, ions, glycans and any removals. Do not silently delete pocket residues or invent missing atoms. A preparation failure blocks the experiment until explained.
- Primary ligand: exact deposited CCD stereochemistry and neutral formal charge. Generate fresh ETKDG conformers from its isomeric SMILES; the bound coordinates are used only as the evaluation reference and to define the known pocket center.
- Known-site search: 24 × 24 × 24 Å box centered on the reference ligand heavy-atom centroid. This is not blind pocket discovery.
- Vina scoring, rigid receptor, exhaustiveness 32, up to 10 distinct poses per seed, CPU limit 2. Seeds 17, 29, 43, 71, 101. Initial ligand embedding uses the corresponding seed. No ligand-coordinate alignment during RMSD evaluation.
- Report symmetry-aware heavy-atom RMSD of top-1 and best-of-top-5, valid chemical identity/stereochemistry, and PoseBusters physical checks. Report failed checks individually, not only a combined pass.
- Primary redocking gate: top-1 RMSD <2 Å AND applicable physical/chemical checks pass in at least 4/5 seeds. A native reference failing a relevant physical check must be reported and investigated; do not silently waive the check for predictions.
- A protonated-amine sensitivity experiment, if run, is separately labeled and cannot retroactively replace this primary protocol. Additional protocol revisions must retain original results.
- Five seeds on one structure assess stability, not independent generalization. Cross-docking on additional compatible, unused DAT complexes is a later transfer gate; do not claim it passed from redocking alone.

## Product behavior

The user can request docking only for a campaign compound, against an explicitly named prepared reference. Jobs are bounded, queued, and persisted. Identity/provenance and validation status accompany every result. Docking never changes campaign ranking, measurements, constraints, or batch commitment. No docking score is labeled pKi or binding probability.

If primary validation fails, expose the validation report and a disabled candidate-docking action with a specific reason. Do not silently display unvalidated candidate poses as supported comparisons. A passing primary gate permits explicitly exploratory candidate poses; cross-docking remains unvalidated until independently tested. Imported campaigns are not automatically linked to DAT.

## Preparation decisions, before docking results

Meeko cannot template the linked NAG residues A:702/703 (minimum native-ligand distances 32.19/38.29 Å). Retaining the two sodium ions also fails PDBQT atom typing (`atom_type is None`). The executable primary baseline is therefore **protein-only**: remove the native ligand, both remote glycans, chloride A:704 and sodium A:705/706; preserve all deposited protein heavy atoms. The ions are 7.78, 4.41 and 6.58 Å from the native ligand. This is a material approximation for a sodium-dependent transporter, not evidence that these ions are irrelevant. Physical checks additionally use the deposited receptor with ions and glycans retained (only ligand removed). Both failed preparation logs are retained. No receptor coordinates are optimized or reconstructed. Cross-docking and ion-aware preparation remain unresolved limitations even if redocking passes.
