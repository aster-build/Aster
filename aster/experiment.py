"""Selection strategies receive features and observed labels, never hidden labels."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from sklearn.ensemble import RandomForestRegressor


@dataclass(frozen=True)
class Config:
    initial_size: int = 100
    rounds: int = 5
    batch_size: int = 8
    seeds: tuple[int, ...] = tuple(range(10))
    hit_threshold: float = 6.0
    trees: int = 200
    min_samples_leaf: int = 2
    max_features: float = 1.0
    radius: int = 2
    bits: int = 2048

    def validate(self, pool_size: int) -> None:
        for name in ("initial_size", "rounds", "batch_size", "trees", "min_samples_leaf", "bits"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive.")
        if self.initial_size + self.rounds * self.batch_size > pool_size:
            raise ValueError("Not enough eligible training compounds for this budget.")
        if not self.seeds or len(set(self.seeds)) != len(self.seeds) or min(self.seeds) < 0 or max(self.seeds) >= 2**32:
            raise ValueError("Seeds must be nonempty, unique unsigned 32-bit integers.")
        if not np.isfinite(self.hit_threshold) or not 0 < self.max_features <= 1 or self.radius < 0:
            raise ValueError("Invalid threshold or fingerprint/model configuration.")

    def to_dict(self) -> dict:
        return asdict(self)


class LabelOracle:
    """In-process API boundary, NOT a security sandbox against malicious code."""
    def __init__(self, labels: np.ndarray):
        self.__labels = np.asarray(labels, dtype=float).copy()
        if not np.isfinite(self.__labels).all():
            raise ValueError("Oracle labels must be finite.")
        self.__revealed: set[int] = set()

    def reveal(self, indices: np.ndarray) -> np.ndarray:
        indices = np.asarray(indices)
        if indices.ndim != 1 or not np.issubdtype(indices.dtype, np.integer):
            raise ValueError("Indices must be a one-dimensional integer array.")
        requested = set(indices.tolist())
        if len(requested) != len(indices) or requested & self.__revealed:
            raise ValueError("A measurement cannot be acquired twice.")
        if any(i < 0 or i >= len(self.__labels) for i in requested):
            raise ValueError("Requested index is outside the acquisition pool.")
        self.__revealed.update(requested)
        return self.__labels[indices].copy()


def choose(strategy: str, candidate_indices: np.ndarray, predictions: np.ndarray,
           batch_size: int, rng: np.random.Generator) -> np.ndarray:
    if batch_size > len(candidate_indices):
        raise ValueError("Batch exceeds remaining pool.")
    if strategy == "random":
        return rng.choice(candidate_indices, batch_size, replace=False)
    if strategy == "greedy":
        # Stable, label-independent tie breaking by sorted compound index.
        return candidate_indices[np.lexsort((candidate_indices, -predictions))[:batch_size]]
    raise ValueError(f"Unknown strategy: {strategy}")


def replay(features: np.ndarray, audit_features: np.ndarray, oracle: LabelOracle,
           initial: np.ndarray, config: Config, seed: int, strategy: str,
           model_factory=None) -> dict:
    """Refit from scratch each round. Audit predictions are scored only afterward."""
    observed = np.asarray(initial, dtype=int).copy()
    values = oracle.reveal(observed)
    remaining = np.setdiff1d(np.arange(len(features)), observed)
    rng = np.random.default_rng(np.random.SeedSequence([seed, 1]))
    history, selections, audit_predictions = [], [], []
    initial_hits = int(np.sum(values >= config.hit_threshold))
    for round_number in range(config.rounds + 1):
        model = model_factory(seed) if model_factory is not None else RandomForestRegressor(
            n_estimators=config.trees, min_samples_leaf=config.min_samples_leaf,
            max_features=config.max_features, random_state=seed, n_jobs=1,
        )
        model.fit(features[observed], values)
        audit_predictions.append(model.predict(audit_features))
        history.append({"seed": seed, "strategy": strategy, "round": round_number,
                        "assays_acquired": round_number * config.batch_size,
                        "training_size": len(observed), "initial_hits": initial_hits,
                        "additional_hits": int(np.sum(values >= config.hit_threshold)) - initial_hits,
                        "best_observed_pic50": float(values.max())})
        if round_number == config.rounds:
            break
        predictions = model.predict(features[remaining])
        selected = choose(strategy, remaining, predictions, config.batch_size, rng)
        # Prediction/selection completes BEFORE the oracle returns outcomes.
        lookup = dict(zip(remaining.tolist(), predictions.tolist()))
        measured = oracle.reveal(selected)
        for rank, (index, actual) in enumerate(zip(selected, measured), start=1):
            selections.append({"seed": seed, "strategy": strategy, "round": round_number + 1,
                               "rank": rank, "index": int(index),
                               "predicted_pic50": lookup[int(index)],
                               "observed_pic50": float(actual),
                               "hit": bool(actual >= config.hit_threshold)})
        observed = np.concatenate([observed, selected])
        values = np.concatenate([values, measured])
        remaining = np.setdiff1d(remaining, selected)
    return {"history": history, "selections": selections,
            "audit_predictions": audit_predictions, "model": model}
