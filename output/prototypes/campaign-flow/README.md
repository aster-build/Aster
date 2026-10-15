# Isolated campaign workflow prototype

Run from the repository root:

```sh
.venv/bin/python output/prototypes/campaign-flow/server.py
```

Open http://127.0.0.1:3010. Stop with Ctrl+C. Reloading resets the browser session.

## Proposed flow

1. **Set up:** target, prediction endpoint, compound-library scope, batch size.
2. **Predict:** animated explanation of encoding, fitting and scoring; a real local model fit supplies the predictions. Animation timing is illustrative.
3. **Select:** full-screen candidate map, molecular inspector, editable batch and up-to-three-compound comparison. Saved docking poses remain available in an interactive 3D view.
4. **Results:** public-data replay for use without a lab. Alternatively export a result template and import a complete CSV with compound_id,value (pKi).
5. **Learn:** refit from accumulated observations, inspect changed estimates, and select the next batch.

Only the DAT example is supported. The prototype is separate from the existing application: it does not update campaigns, start docking jobs, order compounds, or connect to a laboratory. Imported values remain in browser memory and are sent only to the local prototype server for an ephemeral fit.

## Data and interpretation

- Public MoleculeACE CHEMBL238 Ki example: 32 starting measurements and 128 candidates from examples/dashboard.
- Actual Morgan fingerprints (2048 bits) and training-scaled ridge regression, using existing aster modules.
- The map's vertical axis is fingerprint novelty, **not calibrated predictive uncertainty**. Initial measured points use observed pKi; candidate points use predictions.
- Molecular SVGs and physicochemical descriptors generated with RDKit.
- Experimental DAT backbone/reference ligand from the local 8Y2G assets. Four compounds have saved Vina poses. Pose scores are not affinity measurements.
- Replay reveals existing public values; it does not perform a new experiment. The selected-batch error is not an independent evaluation benchmark.

`build_assets.py` regenerates the immutable local assets. `server.py` serves these files and exposes read-only/ephemeral score and reveal endpoints. No existing application source was changed for this prototype.
