"""Train on earlier compounds, test on later ones, and price the difference.

Every evaluation Aster has published so far is a random split: the compounds it
is scored on were drawn from the same pool as the compounds it trained on. A
real campaign never gets that. It trains on what has been measured so far and
must predict what comes next, and the compounds that come next are the ones
chemists chose to make after seeing the earlier results, so they are not a
random sample of anything.

This module runs both and reports the gap. The comparison that matters is not
temporal error against zero, it is temporal error against a random split of the
same measurements at the same training and test sizes, because that holds the
amount of data fixed and changes only whether time was respected. A third arm
re-runs the temporal split at nested earlier cutoffs, so the penalty can be
shown to be a property of time ordering rather than of one chosen cutoff.

Nothing here uses a measurement date, because the release has none. The ordering
comes from the registration number documented in ``aster.expansionrx``.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold
from scipy import stats
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import evidence_power
from .acquisition import tanimoto
from .data import digest, fingerprints, write_json
from .expansionrx import BY_ID

METRICS = ("mae", "rmse", "spearman", "normalised_mae", "training_mean_mae",
           "nearest_neighbour_distance", "new_scaffold_fraction")


def scaffold(smiles: str) -> str:
    """The compound's ring skeleton, used to ask whether a test series is new."""
    return MurckoScaffold.MurckoScaffoldSmiles(mol=Chem.MolFromSmiles(smiles),
                                               includeChirality=False) or "ACYCLIC"


def features_for(frame: pd.DataFrame, settings: dict) -> tuple[np.ndarray, np.ndarray]:
    """Fingerprints and scaffolds for one endpoint's measurements, in row order."""
    model = settings["model"]
    structures = frame.smiles.tolist()
    return (fingerprints(structures, model["radius"], model["bits"]),
            np.asarray([scaffold(s) for s in structures]))


def temporal_split(frame: pd.DataFrame, cutoff: int) -> tuple[np.ndarray, np.ndarray]:
    """Rows at or below the cutoff train; rows above it are the holdout."""
    registration = frame.registration.to_numpy()
    return (np.flatnonzero(registration <= cutoff), np.flatnonzero(registration > cutoff))


def random_matched_split(frame: pd.DataFrame, train_size: int, test_size: int,
                         seed: int) -> tuple[np.ndarray, np.ndarray]:
    """The same measurements, split at the same sizes with registration ignored.

    Drawn from the pooled earlier and later measurements, so the only difference
    from the temporal split is that time is not respected.
    """
    if train_size + test_size > len(frame):
        raise ValueError("Matched split cannot exceed the available measurements.")
    rng = np.random.default_rng(np.random.SeedSequence([seed, 7]))
    order = rng.permutation(len(frame))
    return order[:train_size], order[train_size:train_size + test_size]


def rolling_cutoffs(frame: pd.DataFrame, quantiles: list[float]) -> list[int]:
    """Nested earlier cutoffs, each a registration number inside the earlier era."""
    earlier = frame.loc[frame.era.eq("earlier"), "registration"].to_numpy()
    if not len(earlier):
        return []
    values = np.quantile(earlier, quantiles, method="lower")
    return sorted({int(value) for value in values})


def neighbourhood(features: np.ndarray, scaffolds: np.ndarray,
                  train: np.ndarray, test: np.ndarray) -> dict:
    """How far the test compounds sit from the training set that must predict them.

    Distance is one minus the Tanimoto similarity to the closest training
    compound: zero means an identical fingerprint, one means nothing in common.
    The scaffold fraction is the share of test compounds whose ring skeleton does
    not appear in training at all.
    """
    similarity = tanimoto(features[test], features[train])
    closest = similarity.max(axis=1)
    known = set(scaffolds[train].tolist())
    unseen = np.asarray([s not in known for s in scaffolds[test].tolist()])
    return {"nearest_neighbour_distance": float(np.mean(1.0 - closest)),
            "nearest_neighbour_distance_median": float(np.median(1.0 - closest)),
            "new_scaffold_fraction": float(unseen.mean()),
            "test_scaffolds": int(len(set(scaffolds[test].tolist())))}


def fit_predict(features: np.ndarray, values: np.ndarray, train: np.ndarray,
                test: np.ndarray, settings: dict) -> np.ndarray:
    """Fit on the training rows only and predict the held-out rows.

    Separated from scoring so that the no-leakage property is directly testable:
    the returned predictions must not change when the held-out values change.
    """
    model = settings["model"]
    estimator = make_pipeline(StandardScaler(), Ridge(alpha=model["ridge_alpha"]))
    estimator.fit(features[train], values[train])
    predicted = estimator.predict(features[test])
    if not np.isfinite(predicted).all():
        raise ValueError("Non-finite predictions.")
    return predicted


def fit_and_score(features: np.ndarray, values: np.ndarray, train: np.ndarray,
                  test: np.ndarray, settings: dict) -> dict:
    """Fit the product default on the training rows and score the held-out rows.

    The model never sees a test value. ``training_mean_mae`` is the error of
    predicting the training mean for everything, which is the floor any usable
    model has to beat; ``normalised_mae`` divides the error by the spread of the
    test values themselves, so a value of one means the model is no better than
    knowing the answers' average and the nine endpoints can be averaged together.
    """
    y_train, y_test = values[train], values[test]
    predicted = fit_predict(features, values, train, test, settings)
    residual = predicted - y_test
    spread = float(np.std(y_test, ddof=1))
    correlation = stats.spearmanr(predicted, y_test)
    return {
        "train_size": int(len(train)), "test_size": int(len(test)),
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual ** 2))),
        "spearman": float(correlation.statistic) if np.isfinite(correlation.statistic) else float("nan"),
        "normalised_mae": float(np.mean(np.abs(residual)) / spread) if spread > 0 else float("nan"),
        "training_mean_mae": float(np.mean(np.abs(float(np.mean(y_train)) - y_test))),
        "test_value_sd": spread,
        "train_value_mean": float(np.mean(y_train)),
        "test_value_mean": float(np.mean(y_test)),
    }


def case(frame: pd.DataFrame, features: np.ndarray, scaffolds: np.ndarray,
         train: np.ndarray, test: np.ndarray, settings: dict, **labels) -> dict:
    values = frame.value.to_numpy(dtype=float)
    record = {**labels, **fit_and_score(features, values, train, test, settings),
              **neighbourhood(features, scaffolds, train, test)}
    return record


def run_endpoint(frame: pd.DataFrame, endpoint: str, settings: dict) -> list[dict]:
    """Every case for one endpoint: the temporal split, its control, the rolling ones."""
    rows = frame[frame.endpoint.eq(endpoint)].reset_index(drop=True)
    features, scaffolds = features_for(rows, settings)
    cutoff = next(s for s in settings["splits"] if s["id"] == "temporal")["cutoff"]
    train, test = temporal_split(rows, cutoff)
    minimum_train = settings["minimum_training_measurements"]
    minimum_test = settings["minimum_test_measurements"]
    if len(train) < minimum_train or len(test) < minimum_test:
        return [{"endpoint": endpoint, "split": "temporal", "seed": None, "cutoff": cutoff,
                 "skipped": f"below the declared minimum ({len(train)} train, {len(test)} test)"}]

    label = {"endpoint": endpoint, "endpoint_label": BY_ID[endpoint]["label"],
             "transform": BY_ID[endpoint]["transform"]}
    cases = [case(rows, features, scaffolds, train, test, settings,
                  split="temporal", seed=None, cutoff=cutoff, **label)]
    for seed in settings["seeds"]:
        control_train, control_test = random_matched_split(rows, len(train), len(test), seed)
        cases.append(case(rows, features, scaffolds, control_train, control_test, settings,
                          split="random_matched", seed=seed, cutoff=None, **label))
    rolling = next((s for s in settings["splits"] if s["id"] == "temporal_rolling"), None)
    if rolling:
        for nested in rolling_cutoffs(rows, rolling["quantiles"]):
            nested_train, nested_test = temporal_split(rows, nested)
            if len(nested_train) < minimum_train or len(nested_test) < minimum_test:
                continue
            cases.append(case(rows, features, scaffolds, nested_train, nested_test, settings,
                              split="temporal_rolling", seed=None, cutoff=nested, **label))
    return cases


def analyse(metrics: pd.DataFrame, metric: str = "normalised_mae") -> dict:
    """Per endpoint, then the paired view across endpoints with its power.

    The temporal split happens once per endpoint, so it has no spread of its own;
    every quoted standard deviation belongs to the random control. The paired
    analysis therefore has one pair per endpoint, not one per seed, and the power
    report says plainly what nine pairs can detect.
    """
    scored = metrics[metrics.get("skipped").isna()] if "skipped" in metrics else metrics
    per_endpoint, pairs = {}, []
    for endpoint in sorted(scored.endpoint.unique()):
        rows = scored[scored.endpoint.eq(endpoint)]
        temporal = rows[rows.split.eq("temporal")]
        control = rows[rows.split.eq("random_matched")]
        if temporal.empty or control.empty:
            continue
        observed = float(temporal[metric].iloc[0])
        control_mean = float(control[metric].mean())
        control_sd = float(control[metric].std(ddof=1))
        rolling = rows[rows.split.eq("temporal_rolling")]
        entry = {
            "endpoint_label": str(temporal.endpoint_label.iloc[0]),
            "train_size": int(temporal.train_size.iloc[0]),
            "test_size": int(temporal.test_size.iloc[0]),
            "temporal": observed,
            "random_matched_mean": control_mean,
            "random_matched_sd": control_sd,
            "gap": observed - control_mean,
            "gap_in_control_sds": (observed - control_mean) / control_sd if control_sd > 0 else None,
            "control_seeds_worse_than_temporal": int((control[metric] >= observed).sum()),
            "control_seeds": int(len(control)),
            "temporal_mae": float(temporal.mae.iloc[0]),
            "random_matched_mae_mean": float(control.mae.mean()),
            "temporal_spearman": float(temporal.spearman.iloc[0]),
            "random_matched_spearman_mean": float(control.spearman.mean()),
            # Carried so that a restricted range cannot masquerade as a worse model:
            # a narrower set of held-out values depresses rank correlation on its own.
            "temporal_test_value_sd": float(temporal.test_value_sd.iloc[0]),
            "random_matched_test_value_sd_mean": float(control.test_value_sd.mean()),
            "temporal_test_value_mean": float(temporal.test_value_mean.iloc[0]),
            "random_matched_test_value_mean": float(control.test_value_mean.mean()),
            "temporal_beats_no_model": bool(temporal.mae.iloc[0] < temporal.training_mean_mae.iloc[0]),
            "temporal_training_mean_mae": float(temporal.training_mean_mae.iloc[0]),
            "temporal_nearest_neighbour_distance": float(temporal.nearest_neighbour_distance.iloc[0]),
            "random_matched_nearest_neighbour_distance": float(control.nearest_neighbour_distance.mean()),
            "temporal_new_scaffold_fraction": float(temporal.new_scaffold_fraction.iloc[0]),
            "random_matched_new_scaffold_fraction": float(control.new_scaffold_fraction.mean()),
            "rolling_cutoff_gaps": {int(cutoff): float(value) - control_mean
                                    for cutoff, value in zip(rolling.cutoff, rolling[metric])},
        }
        per_endpoint[endpoint] = entry
        pairs.append(entry["gap"])

    gaps = pd.Series(pairs, index=list(per_endpoint), dtype=float)
    worse = int((gaps > 0).sum())
    return {
        "metric": metric,
        "per_endpoint": per_endpoint,
        "across_endpoints": {
            "endpoints": int(len(gaps)),
            "mean_gap": float(gaps.mean()) if len(gaps) else None,
            "median_gap": float(gaps.median()) if len(gaps) else None,
            "endpoints_worse_under_time": worse,
            "endpoints_better_under_time": int(len(gaps)) - worse,
            "pairing": "One pair per endpoint: the endpoint's single temporal value minus "
                       "the mean of its random control seeds.",
            "power": evidence_power.summarize(gaps, effects=(0.10, 0.05, 0.025)) if len(gaps) > 1 else None,
            "power_note": "Effects are in units of the primary metric, where 1.0 is the error "
                          "of predicting the test mean, so 0.10 means a tenth of that spread. "
                          "The pairs are endpoints from one company's campaigns and are not "
                          "independent draws from drug discovery at large.",
        },
    }


def run(frame: pd.DataFrame, settings: dict, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    versions = {n: importlib.metadata.version(n)
                for n in ["rdkit", "numpy", "pandas", "scikit-learn", "scipy"]}
    cases: list[dict] = []
    for endpoint in settings["endpoints"]:
        cases.extend(run_endpoint(frame, endpoint, settings))
        print(f"{endpoint}: {len(cases)} cases so far", flush=True)
    metrics = pd.DataFrame(cases)
    metrics.to_csv(out / "case_metrics.csv", index=False)
    result = {"config": settings, "versions": versions,
              "analysis": analyse(metrics, "normalised_mae"),
              "analysis_mae": analyse(metrics, "mae"),
              "skipped": [row for row in cases if "skipped" in row and row.get("skipped")]}
    write_json(out / "comparison.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Temporal holdout on the ExpansionRx release")
    parser.add_argument("--config", type=Path, default=Path("configs/temporal-v1.json"))
    parser.add_argument("--measurements", type=Path,
                        default=Path("output/expansionrx/measurements.csv"))
    parser.add_argument("--output", type=Path, default=Path("output/temporal"))
    args = parser.parse_args()
    settings = json.loads(args.config.read_text())
    settings["config_sha256"] = digest(args.config)
    frame = pd.read_csv(args.measurements)
    result = run(frame, settings, args.output)
    across = result["analysis"]["across_endpoints"]
    print(json.dumps({"mean_gap": across["mean_gap"],
                      "endpoints_worse_under_time": across["endpoints_worse_under_time"],
                      "endpoints": across["endpoints"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
