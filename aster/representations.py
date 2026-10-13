"""Frozen CheMeleon inference. No assay labels enter feature generation."""
from pathlib import Path
import hashlib
import json

import numpy as np

from .data import digest, write_json


def frozen_chemeleon(structures: list[str], checkpoint: Path, expected_hash: str,
                     cache: Path, batch_size: int = 32) -> np.ndarray:
    if digest(checkpoint) != expected_hash:
        raise ValueError("CheMeleon checkpoint checksum mismatch.")
    import importlib.metadata
    versions = {n: importlib.metadata.version(n) for n in ["chemprop", "torch", "rdkit"]}
    metadata = {"structures": structures, "checkpoint_sha256": expected_hash, "versions": versions,
                "algorithm": "BondMessagePassing/MeanAggregation; eval mode; CPU; v1"}
    key = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    artifact = cache / f"{key}.npz"
    if artifact.exists():
        x = np.load(artifact, allow_pickle=False)["features"]
        if x.shape[0] != len(structures) or not np.isfinite(x).all():
            raise ValueError("Invalid embedding cache.")
        return x

    import torch
    from chemprop import featurizers, nn
    from chemprop.data import BatchMolGraph
    from rdkit import Chem

    torch.set_num_threads(2)
    weights = torch.load(checkpoint, weights_only=True, map_location="cpu")
    encoder = nn.BondMessagePassing(**weights["hyper_parameters"])
    encoder.load_state_dict(weights["state_dict"])
    encoder.eval()
    aggregation = nn.MeanAggregation()
    featurizer = featurizers.SimpleMoleculeMolGraphFeaturizer()
    blocks = []
    with torch.inference_mode():
        for start in range(0, len(structures), batch_size):
            graph = BatchMolGraph([featurizer(Chem.MolFromSmiles(s)) for s in structures[start:start + batch_size]])
            blocks.append(aggregation(encoder(graph), graph.batch).cpu().numpy())
            if start % 320 == 0:
                print(f"CheMeleon embeddings: {start}/{len(structures)} molecules", flush=True)
    x = np.concatenate(blocks).astype(np.float32)
    if not np.isfinite(x).all():
        raise ValueError("Nonfinite CheMeleon embeddings.")
    np.savez_compressed(artifact, features=x)
    write_json(artifact.with_suffix(".json"), metadata)
    return x
