# Public campaign fixture

A small retrospective workflow demonstration from the already inspected
MoleculeACE CHEMBL238 Ki (dopamine transporter) task. `manifest.json` identifies
the pinned upstream revision and exact curated-source checksum.

- `measured.csv`: 32 initial measurements from the published Train partition.
- `candidates.csv`: 128 structures/IDs, with no outcomes.
- `outcomes.csv`: existing public measurements for the demo replay driver only.

The API creates the campaign from the first two files. The explicit **Replay public
outcomes** operation imports only a committed batch. This is procedural isolation,
not a security boundary: these are public data, and the demo driver can access them.
Regular CSV-imported campaigns cannot call the replay-outcome endpoint.

Source: https://github.com/molML/MoleculeACE/tree/7e6de0bd2968c56589c580f2a397f01c531ede26
Retain the upstream data provenance and applicable source terms when redistributing.
This fixture is not new evaluation evidence or a set of prospective experiments.
