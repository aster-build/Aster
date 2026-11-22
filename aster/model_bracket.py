"""Run a second model family beside the product default, as a logged bracket.

Aster's product default is one model family: Morgan fingerprints (a bit vector
that records which small substructures a molecule contains) fed into ridge
regression (a linear fit with a penalty that keeps the coefficients small). Every
result the project reports comes from that one family, so none of them can say
whether the family is the limit or the data is.

This module answers that by running a second family on the *same* splits and
recording both. A "bracket" here means exactly that: two families are logged per
case, neither replaces the other, and the default stays the default. The second
family is TabPFN -- a transformer that was pretrained on millions of synthetic
tables and then predicts a new table in a single forward pass, with no gradient
training on the assay data at all -- placed on top of frozen pretrained molecular
features rather than raw fingerprints, because that is the configuration queue
item 11 declares.

Three arms are declared, so that a difference can be attributed:

- ``morgan_ridge``    the product default, unchanged, via ``aster.temporal``.
- ``chemeleon_tabpfn``  the item's arm: pretrained CheMeleon embeddings, TabPFN head.
- ``morgan_tabpfn``   the same head on the default's own features, which separates
                      "the head helped" from "the representation helped".

Nothing here downloads model weights. Both pretrained checkpoints are loaded from
a local path whose SHA-256 is pinned in the config, the way
``aster.representations`` already loads CheMeleon, so a run either uses the exact
weights the record names or fails.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import evidence_power, temporal, temporal_discovery
from .data import digest, write_json
from .expansionrx import BY_ID

ARMS = ("morgan_ridge", "chemeleon_tabpfn", "morgan_tabpfn")
BASELINE_ARM = "morgan_ridge"


class WeightsUnavailable(RuntimeError):
    """Raised when an arm's pretrained weights are absent or not the pinned ones.

    Kept as its own type so a runner can record "this arm did not run, and why"
    instead of either crashing the whole study or silently dropping an arm.
    """


def feature_columns(train_features: np.ndarray, budget: int) -> np.ndarray:
    """The columns a TabPFN arm keeps, chosen from the training rows alone.

    TabPFN is built for tables of at most a few hundred columns; a 2048-bit
    fingerprint and a 2048-wide embedding are both outside that regime. The
    reduction keeps the ``budget`` columns that vary most across the training
    rows, which is a label-free choice: it reads the feature matrix of the
    training rows and never a measured value, and never a held-out row. Ties
    break by column index so the choice is reproducible.

    The alternative passed on was fitting a projection such as PCA. It would use
    the same information, but it adds a fitted transform that has to be stored
    and re-applied for a decision record to be replayable, for no expected gain
    on sparse binary features.
    """
    x = np.asarray(train_features, dtype=np.float64)
    if x.ndim != 2 or len(x) == 0:
        raise ValueError("Training features must be a non-empty 2-D matrix.")
    if budget < 1:
        raise ValueError("Feature budget must be at least one column.")
    if budget >= x.shape[1]:
        return np.arange(x.shape[1])
    variance = x.var(axis=0)
    order = np.lexsort((np.arange(x.shape[1]), -variance))
    return np.sort(order[:budget])


def checked_checkpoint(path: Path, expected_sha256: str, what: str) -> Path:
    """A local checkpoint that exists and matches the pinned checksum, or an error."""
    if not path.is_file():
        raise WeightsUnavailable(f"{what} checkpoint not present at {path}")
    if digest(path) != expected_sha256:
        raise WeightsUnavailable(f"{what} checkpoint at {path} does not match the pinned checksum")
    return path


def tabpfn_regressor(settings: dict):
    """A fitted-per-case TabPFN regressor, or an error naming what is missing.

    TabPFN's weights are not on PyPI. Recent releases of the package also require
    a one-time licence acceptance and an API token before they will fetch them.
    Both of those are the operator's decision, not this run's, so this function
    never downloads anything: it needs the checkpoint already on disk at the
    configured path.
    """
    arm = settings["arms"]["tabpfn"]
    try:
        from tabpfn import TabPFNRegressor
    except ImportError as error:  # pragma: no cover - exercised only without the extra
        raise WeightsUnavailable("the tabpfn package is not installed") from error
    checkpoint = checked_checkpoint(Path(arm["checkpoint"]), arm["checkpoint_sha256"], "TabPFN")
    return TabPFNRegressor(model_path=str(checkpoint), device=arm["device"],
                           random_state=arm["random_state"], n_estimators=arm["n_estimators"])


def chemeleon_features(structures: list[str], settings: dict) -> np.ndarray:
    """Frozen pretrained molecular embeddings, from the already-pinned loader."""
    from .representations import frozen_chemeleon
    arm = settings["arms"]["chemeleon"]
    checkpoint = checked_checkpoint(Path(arm["checkpoint"]), arm["checkpoint_sha256"], "CheMeleon")
    try:
        return frozen_chemeleon(structures, checkpoint, arm["checkpoint_sha256"],
                                Path(arm["cache"]))
    except ImportError as error:  # pragma: no cover - exercised only without the extra
        raise WeightsUnavailable("the neural extra (chemprop, torch) is not installed") from error


def arm_features(arm: str, frame: pd.DataFrame, morgan: np.ndarray, settings: dict) -> np.ndarray:
    """The feature matrix an arm reads. Row order always matches ``frame``."""
    if arm in {"morgan_ridge", "morgan_tabpfn"}:
        return morgan
    if arm == "chemeleon_tabpfn":
        return chemeleon_features(frame.smiles.tolist(), settings)
    raise ValueError(f"Unknown arm {arm}")


def predict_with(arm: str, features: np.ndarray, values: np.ndarray, train: np.ndarray,
                 test: np.ndarray, settings: dict) -> np.ndarray:
    """Fit one arm on the training rows and predict the held-out rows.

    Every arm refits from scratch per case and sees no held-out value, which is
    the property ``tests/test_model_bracket.py`` checks directly by changing the
    held-out values and asserting the predictions do not move.
    """
    if arm == BASELINE_ARM:
        return temporal.fit_predict(features, values, train, test, settings)
    columns = feature_columns(features[train], settings["arms"]["tabpfn"]["feature_budget"])
    model = tabpfn_regressor(settings)
    model.fit(np.asarray(features)[np.ix_(train, columns)], values[train])
    predicted = np.asarray(model.predict(np.asarray(features)[np.ix_(test, columns)]), dtype=float)
    if predicted.shape != (len(test),) or not np.isfinite(predicted).all():
        raise ValueError(f"Arm {arm} returned unusable predictions.")
    return predicted


def case_rows(frame: pd.DataFrame, morgan: np.ndarray, train: np.ndarray, test: np.ndarray,
              settings: dict, criterion: dict, arms: tuple[str, ...], **labels) -> list[dict]:
    """One split, every arm that can run: accuracy and the batch it would pick.

    Both metrics are recorded per arm because they answer different questions.
    ``normalised_mae`` is the error divided by the spread of the held-out values,
    so one means "no better than quoting the average". ``hits`` is the number of
    picks in a 40-compound batch that meet the endpoint's declared criterion,
    which is the number Aster's milestones actually report.
    """
    values = frame.value.to_numpy(dtype=float)
    pool_hits = temporal_discovery.hits(values[test], criterion)
    batch_size = min(settings["discovery"]["batch_size"], len(test))
    expected_random = float(batch_size * pool_hits.mean())
    rows = []
    for arm in arms:
        shared = {**labels, "arm": arm, "batch_size": batch_size,
                  "pool_hit_rate": float(pool_hits.mean()),
                  "expected_random_hits": expected_random}
        try:
            features = arm_features(arm, frame, morgan, settings)
            predicted = predict_with(arm, features, values, train, test, settings)
        except WeightsUnavailable as error:
            rows.append({**shared, "unavailable": str(error)})
            continue
        scored = temporal.fit_and_score(features, values, train, test, settings,
                                       predicted=predicted)
        picked = temporal_discovery.pick("greedy", temporal_discovery.desirability(predicted, criterion),
                                         batch_size, np.random.default_rng(0))
        rows.append({**shared, **scored, "hits": int(pool_hits[picked].sum()),
                     "hits_over_expected_random": float(pool_hits[picked].sum() - expected_random)})
    return rows


def run_endpoint(frame: pd.DataFrame, endpoint: str, settings: dict,
                 arms: tuple[str, ...] = ARMS) -> list[dict]:
    """The temporal split and its matched random controls, for one endpoint."""
    rows = frame[frame.endpoint.eq(endpoint)].reset_index(drop=True)
    morgan, _ = temporal.features_for(rows, settings)
    cutoff = next(s for s in settings["splits"] if s["id"] == "temporal")["cutoff"]
    train, test = temporal.temporal_split(rows, cutoff)
    if (len(train) < settings["minimum_training_measurements"]
            or len(test) < settings["minimum_test_measurements"]):
        return [{"endpoint": endpoint, "split": "temporal", "seed": None,
                 "skipped": f"below the declared minimum ({len(train)} train, {len(test)} test)"}]
    native = settings["discovery"]["criteria"][endpoint]
    criterion = temporal_discovery.scale_criterion(native, BY_ID[endpoint]["transform"])
    label = {"endpoint": endpoint, "endpoint_label": BY_ID[endpoint]["label"],
             "criterion_applied": json.dumps(criterion, sort_keys=True)}
    cases = case_rows(rows, morgan, train, test, settings, criterion, arms,
                      split="temporal", seed=None, **label)
    for seed in settings["bracket"]["control_seeds"]:
        control_train, control_test = temporal.random_matched_split(rows, len(train), len(test), seed)
        cases.extend(case_rows(rows, morgan, control_train, control_test, settings, criterion,
                               arms, split="random_matched", seed=seed, **label))
    return cases


def analyse(metrics: pd.DataFrame, metric: str = "normalised_mae") -> dict:
    """Paired arm-minus-default differences, with what the pairs can detect.

    The pairing is per case, so an arm is only ever compared against the default
    on the identical split, seed and endpoint. ``evidence_power`` then reports the
    achieved power and the smallest difference these pairs could have detected,
    which is what keeps a null from being read as "the two are equal".
    """
    scored = metrics
    for column in ("skipped", "unavailable"):
        if column in scored:
            scored = scored[scored[column].isna()]
    out: dict = {"metric": metric, "baseline": BASELINE_ARM, "arms": {}}
    keys = [k for k in ("endpoint", "split", "seed") if k in scored.columns]
    for arm in sorted(set(scored.arm.unique()) - {BASELINE_ARM}):
        subset = scored[scored.arm.isin([arm, BASELINE_ARM])].copy()
        if "seed" in subset:
            subset["seed"] = subset["seed"].fillna(-1)
        try:
            differences = evidence_power.paired_differences(subset, arm, metric,
                                                            baseline=BASELINE_ARM, keys=keys)
        except ValueError as error:
            out["arms"][arm] = {"unpaired": str(error)}
            continue
        out["arms"][arm] = {
            "cases": int(len(differences)),
            "mean_difference": float(differences.mean()),
            "sd_difference": float(differences.std(ddof=1)) if len(differences) > 1 else None,
            "cases_where_arm_had_lower_error": int((differences < 0).sum()),
            "power": evidence_power.summarize(differences) if len(differences) > 1 else None,
            "direction_note": (f"Negative means {arm} had lower {metric} than {BASELINE_ARM}. "
                               "A difference of zero is not evidence of equivalence; read it "
                               "against the minimum detectable effect below."),
        }
    out["arms_that_did_not_run"] = unavailable_arms(metrics)
    return without_undefined(out)


def without_undefined(value):
    """Replace a non-finite number with null, recursively.

    Some of these quantities are genuinely undefined rather than zero: the
    smallest detectable difference does not exist when every paired difference is
    identical, which happens when two arms pick the same batch in every case.
    Writing null says that; writing a number would not, and the project's JSON
    writer refuses a bare NaN.
    """
    if isinstance(value, dict):
        return {key: without_undefined(item) for key, item in value.items()}
    if isinstance(value, list):
        return [without_undefined(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def unavailable_arms(metrics: pd.DataFrame) -> dict:
    """Arms that could not run, and the reason, so a missing arm is never silent."""
    if "unavailable" not in metrics:
        return {}
    missing = metrics[metrics.unavailable.notna()]
    return {arm: sorted(set(rows.unavailable))[0]
            for arm, rows in missing.groupby("arm")}


def prospective_plan(metrics: pd.DataFrame, metric: str) -> dict:
    """What a bracket of this size could detect, before a second arm has run.

    Priced from the spread of the default arm's own metric across cases, because
    that is all a run with one arm can see. Two arms on the same split usually
    move together, so their paired differences are less spread out than the metric
    itself; this is therefore a pessimistic bound, and the real comparison should
    be able to detect something smaller than the number here.
    """
    rows = metrics
    for column in ("skipped", "unavailable"):
        if column in rows:
            rows = rows[rows[column].isna()]
    rows = rows[rows.arm.eq(BASELINE_ARM)]
    if metric not in rows or len(rows) < 2:
        return {"cases_available": int(len(rows)), "note": "too few cases to price"}
    sd = float(rows[metric].std(ddof=1))
    plan = evidence_power.plan(sd, int(len(rows)))
    return without_undefined({
        "metric": metric, **plan,
        "spread_source": f"case-to-case spread of {BASELINE_ARM}'s own {metric}",
        "interpretation": ("The smallest difference a bracket of this many cases could "
                           "detect at 80% power, assuming paired differences are as "
                           "spread out as the metric itself. Pairing normally does better "
                           "than that, so treat it as an upper bound.")})


def run(frame: pd.DataFrame, settings: dict, out: Path,
        arms: tuple[str, ...] = ARMS) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []
    for endpoint in settings["endpoints"]:
        cases.extend(run_endpoint(frame, endpoint, settings, arms))
        print(f"{endpoint}: {len(cases)} rows so far", flush=True)
    metrics = pd.DataFrame(cases)
    metrics.to_csv(out / "bracket_case_metrics.csv", index=False)
    result = {"config": settings["bracket"], "arms_declared": list(arms),
              "versions": versions(arms),
              "error_analysis": analyse(metrics, "normalised_mae"),
              "discovery_analysis": analyse(metrics, "hits"),
              "prospective_plan": {metric: prospective_plan(metrics, metric)
                                   for metric in ("normalised_mae", "hits")}}
    write_json(out / "bracket_comparison.json", result)
    return result


def versions(arms: tuple[str, ...]) -> dict:
    """Package versions behind the arms that ran, recorded with the result."""
    wanted = ["numpy", "scikit-learn", "rdkit"]
    if any("tabpfn" in arm for arm in arms):
        wanted += ["tabpfn", "torch"]
    if "chemeleon_tabpfn" in arms:
        wanted += ["chemprop"]
    found = {}
    for name in wanted:
        try:
            found[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            found[name] = "absent"
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description="Two model families on the same splits")
    parser.add_argument("--config", type=Path, default=Path("configs/bracket-v1.json"))
    parser.add_argument("--measurements", type=Path,
                        default=Path("output/expansionrx/measurements.csv"))
    parser.add_argument("--output", type=Path, default=Path("output/bracket"))
    parser.add_argument("--arms", nargs="+", default=list(ARMS),
                        help="Subset of arms to run; the default arm is always included.")
    args = parser.parse_args()
    settings = load_config(args.config)
    arms = tuple(dict.fromkeys([BASELINE_ARM, *args.arms]))
    unknown = set(arms) - set(ARMS)
    if unknown:
        raise SystemExit(f"Unknown arms: {sorted(unknown)}")
    result = run(pd.read_csv(args.measurements), settings, args.output, arms)
    print(json.dumps(result["error_analysis"], indent=2)[:4000], flush=True)


def load_config(path: Path) -> dict:
    """The bracket config merged onto the protocol config it declares as its base.

    The bracket does not restate the splits, endpoints or criteria: it inherits
    them from the temporal protocol so that its numbers sit beside the existing
    temporal results instead of beside a second, slightly different protocol.
    Both checksums are recorded.
    """
    bracket = json.loads(path.read_text())
    base_path = Path(bracket["base_config"])
    settings = json.loads(base_path.read_text())
    settings["bracket"] = bracket
    settings["arms"] = bracket["arms"]
    settings["config_sha256"] = digest(path)
    settings["base_config_sha256"] = digest(base_path)
    return settings


if __name__ == "__main__":
    main()
