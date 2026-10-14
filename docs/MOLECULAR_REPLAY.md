# Molecular evidence replay — Milestone 7A

Open `/replay` or choose **3D evidence** in the local dashboard. Run the same API and frontend described in [DASHBOARD.md](DASHBOARD.md).

## What is implemented

- Client-only, lazy-loaded Mol* renderer for a locally pinned experimental human DAT complex (RCSB 8Y2G), with protein, pocket, ligand, and guided camera-tour views.
- Collapsible surrounding evidence cards with native desktop height resizing. On smaller displays, cards stack below the 3D scene.
- Ten residues with minimum protein–ligand heavy-atom separation ≤4 Å. Selecting a row focuses/highlights the residue and draws its measured distance to the closest ligand atom. Clicking a listed residue in 3D selects its row.
- Read-only playback of committed campaign rounds: Measurements → Fit model → Score candidates → Select batch → Reveal results. Playback, step, restart, speed, round selection, and a scrubber use saved records. They never invoke fitting or change the campaign.
- Actual before/after fit prediction differences for candidates present in both scored pools; recorded selected-batch errors only after outcome reveal.
- Structural provenance and numerical tables remain available when WebGL fails. Missing historical full-pool scores fall back explicitly to the committed batch; uncommitted campaigns show an empty state.

## Evidence boundaries

8Y2G contains dexmethylphenidate (CCD A1D5U, InChIKey DUGOZIWVEXMGBE-CHWSQXEVSA-N), human DAT/UniProt Q01959, protein label/auth chain A, ligand label chain B/auth chain A/residue 701. It is a 2.83 Å cryo-EM structure. Assembly 1 uses the deposited identity operator. The deposited engineered construct is 562 residues, with 545 modeled; RCSB records one sequence conflict. Original entry, polymer and ligand metadata are retained.

Canonical isomeric SMILES comparison found **no exact matches** among the 160 dashboard demo molecules. Accordingly, selecting a campaign compound does not substitute it into the protein pocket. Imported campaigns are explicitly unverified against the reference target. Ligand identity/stereo, construct limitations, and all input file hashes are in `apps/web/public/structures/8y2g/manifest.json`.

Contacts are computed Euclidean distances from experimental coordinates, not PLIP interaction assignments, hydrogen-bond evidence, binding energies, or causal explanations. The scene is static; the guided tour moves the camera. There is no binding trajectory, molecular-dynamics simulation, docking, or neural-training animation. Morgan + ridge uses molecular fingerprints and assay measurements, not these protein coordinates.

Replay steps are semantic views of saved round artifacts, not recorded optimizer iterations or measured event durations. A stage with partial/failed outcomes says so. Outcome availability in this retrospective read-only API is not a blind-evaluation security boundary. Batch MAE reflects selected measured compounds only and is not independent evaluation evidence.

## Architecture and reproduction

- `MolecularScene.tsx`: Mol* PluginContext, fixed experimental structure, camera navigation and residue/distance selections.
- `EvidenceReplay.tsx`: React replay state; camera tour and decision playback are separate controls.
- `GET /campaigns/{id}/replay`: `aster/replay.py` reads saved training snapshots, model recipe/summary, predictions, recommendations, and imported results. It does not recompute scores.
- `scripts/prepare_structure.py`: rebuilds the local manifest and residue-distance list from pinned source files. Its atom-loop parser is intentionally limited to the checked 8Y2G format and fails on incompatible rows. Run `.venv/bin/python scripts/prepare_structure.py` after reviewing any source changes.
- Mol* is MIT-licensed; its version is pinned in the npm lockfile. RCSB source records and direct provenance links accompany the structural data. No PLIP dependency was introduced.

## Verification

Production build/TypeScript and all 56 Python tests passed. Structural tests verify source hashes and independently recompute minimum residue distances/atom mappings. API tests verify two rounds, immutable historical training/scores, no mutation during replay, and missing-preview fallback. Browser checks cover real WebGL rendering, contact selection, round progression/outcome visibility, mobile layout, and an explicitly WebGL-disabled browser fallback. Run `AGENT_BROWSER_BIN=/path/to/agent-browser sh scripts/verify_replay.sh` to repeat the checks.

Later work: additional reviewed complexes, exact campaign pose mapping where available, validated interaction classification, quantitatively checked fingerprint attribution, and conditional docking. None is needed to run this first evidence replay.
