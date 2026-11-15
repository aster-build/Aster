"""Does ranking still beat picking at random when the pool is genuinely later?

The error study asks how accurate the model is. This asks the question Aster's
milestones actually report: given a budget of assays, does ranking the pool by
prediction find more good compounds than picking from it at random? Every
existing answer to that was measured on a random split, so this re-measures it
with the pool held in the future.

A "hit" needs a criterion, and ADMET endpoints have no equivalent of the potency
threshold the earlier milestones used. The criteria are therefore declared in
``configs/temporal-v1.json`` before the run, they are this study's own choices
rather than published consensus, and the whole arm is re-run at a stricter and a
looser setting so that the conclusion can be checked against that choice.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import temporal
from .data import digest, write_json
from .expansionrx import BY_ID

POLICIES = ("greedy", "random")


def scale_criterion(criterion: dict, transform: str) -> dict:
    """Express a criterion given in native units on the scale values are fitted on."""
    convert = (lambda value: float(np.log10(value))) if transform == "log10" else float
    if criterion["kind"] == "window":
        return {"kind": "window", "low": convert(criterion["low"]), "high": convert(criterion["high"])}
    if criterion["kind"] in {"max", "min"}:
        return {"kind": criterion["kind"], "threshold": convert(criterion["threshold"])}
    raise ValueError(f"Unknown criterion kind {criterion['kind']}")


def adjust_criterion(criterion: dict, factor: float) -> dict:
    """The same criterion made harder (factor < 1) or easier (factor > 1).

    For a one-sided criterion the threshold moves multiplicatively in the
    direction that changes difficulty: a higher bar to clear when more is better,
    a lower ceiling when less is better. For the LogD window the bounds move in
    by 0.5 log units when stricter and out by 0.5 when looser.
    """
    if factor == 1.0:
        return dict(criterion)
    if criterion["kind"] == "window":
        shift = 0.5 if factor < 1.0 else -0.5
        return {**criterion, "low": criterion["low"] + shift, "high": criterion["high"] - shift}
    if criterion["kind"] == "max":
        return {**criterion, "threshold": criterion["threshold"] / factor}
    return {**criterion, "threshold": criterion["threshold"] * factor}


def hits(values: np.ndarray, criterion: dict) -> np.ndarray:
    """Which measurements meet the criterion, on the fitted scale."""
    if criterion["kind"] == "window":
        return (values >= criterion["low"]) & (values <= criterion["high"])
    if criterion["kind"] == "max":
        return values >= criterion["threshold"]
    return values <= criterion["threshold"]


def desirability(predicted: np.ndarray, criterion: dict) -> np.ndarray:
    """Score to rank by: higher is more desirable under this criterion."""
    if criterion["kind"] == "window":
        centre = (criterion["low"] + criterion["high"]) / 2.0
        return -np.abs(predicted - centre)
    if criterion["kind"] == "max":
        return np.asarray(predicted, dtype=float)
    return -np.asarray(predicted, dtype=float)


def pick(policy: str, scores: np.ndarray, batch_size: int, rng: np.random.Generator) -> np.ndarray:
    """Indices into the pool. Greedy ranks by score; ties break by pool position."""
    if batch_size > len(scores):
        raise ValueError("Batch exceeds the available pool.")
    if policy == "random":
        return rng.choice(len(scores), batch_size, replace=False)
    if policy == "greedy":
        order = np.arange(len(scores))
        return order[np.lexsort((order, -np.asarray(scores, dtype=float)))[:batch_size]]
    raise ValueError(f"Unknown policy {policy}")


def discovery_case(features: np.ndarray, values: np.ndarray, train: np.ndarray,
                   pool: np.ndarray, criterion: dict, settings: dict,
                   seeds: list[int], **labels) -> list[dict]:
    """One split, both policies. The model never sees a pool value before picking."""
    batch_size = settings["discovery"]["batch_size"]
    predicted = temporal.fit_predict(features, values, train, pool, settings)
    pool_values = values[pool]
    pool_hits = hits(pool_values, criterion)
    scores = desirability(predicted, criterion)
    oracle = int(np.sort(pool_hits.astype(int))[::-1][:batch_size].sum())
    shared = {**labels, "train_size": int(len(train)), "pool_size": int(len(pool)),
              "batch_size": batch_size, "pool_hit_rate": float(pool_hits.mean()),
              "pool_hits": int(pool_hits.sum()), "best_possible_hits": oracle,
              "expected_random_hits": float(batch_size * pool_hits.mean()),
              # Also carried so a hit count can never be read without its accuracy.
              "train_hit_rate": float(hits(values[train], criterion).mean())}
    rows = []
    for policy in POLICIES:
        if policy == "greedy":
            chosen = [pick("greedy", scores, batch_size, np.random.default_rng(0))]
            policy_seeds = [None]
        else:
            policy_seeds = seeds
            chosen = [pick("random", scores, batch_size,
                           np.random.default_rng(np.random.SeedSequence([seed, 23])))
                      for seed in policy_seeds]
        for seed, indices in zip(policy_seeds, chosen):
            found = int(pool_hits[indices].sum())
            rows.append({**shared, "policy": policy, "policy_seed": seed,
                         "hits": found,
                         "hits_over_expected_random": found - shared["expected_random_hits"],
                         "enrichment": (found / shared["expected_random_hits"])
                         if shared["expected_random_hits"] > 0 else None,
                         "share_of_best_possible": found / oracle if oracle > 0 else None})
    return rows


def run_endpoint(frame: pd.DataFrame, endpoint: str, settings: dict,
                 strictness: str = "declared") -> list[dict]:
    rows = frame[frame.endpoint.eq(endpoint)].reset_index(drop=True)
    features, _ = temporal.features_for(rows, settings)
    values = rows.value.to_numpy(dtype=float)
    discovery = settings["discovery"]
    factor = {"declared": 1.0, "strict": discovery["sensitivity"]["strict"],
              "loose": discovery["sensitivity"]["loose"]}[strictness]
    native = discovery["criteria"][endpoint]
    criterion = adjust_criterion(scale_criterion(native, BY_ID[endpoint]["transform"]), factor)

    cutoff = next(s for s in settings["splits"] if s["id"] == "temporal")["cutoff"]
    train, pool = temporal.temporal_split(rows, cutoff)
    batch_size = discovery["batch_size"]
    if len(train) < settings["minimum_training_measurements"] or len(pool) < batch_size:
        return [{"endpoint": endpoint, "split": "temporal", "strictness": strictness,
                 "skipped": f"below the declared minimum ({len(train)} train, {len(pool)} pool)"}]

    label = {"endpoint": endpoint, "endpoint_label": BY_ID[endpoint]["label"],
             "strictness": strictness,
             "criterion_applied": json.dumps(criterion, sort_keys=True)}
    seeds = settings["seeds"]
    cases = discovery_case(features, values, train, pool, criterion, settings, seeds,
                           split="temporal", control_seed=None, **label)
    for seed in seeds:
        control_train, control_pool = temporal.random_matched_split(rows, len(train), len(pool), seed)
        cases.extend(discovery_case(features, values, control_train, control_pool, criterion,
                                    settings, [seed], split="random_matched",
                                    control_seed=seed, **label))
    return cases


def analyse(metrics: pd.DataFrame) -> dict:
    """Per endpoint and strictness: did ranking beat random picking, and by how much?"""
    scored = metrics[metrics.get("skipped").isna()] if "skipped" in metrics else metrics
    out: dict = {"by_strictness": {}}
    for strictness in sorted(scored.strictness.unique()):
        level = scored[scored.strictness.eq(strictness)]
        per_endpoint, gaps = {}, []
        for endpoint in sorted(level.endpoint.unique()):
            rows = level[level.endpoint.eq(endpoint)]
            temporal_rows = rows[rows.split.eq("temporal")]
            control_rows = rows[rows.split.eq("random_matched")]
            greedy = temporal_rows[temporal_rows.policy.eq("greedy")]
            random_policy = temporal_rows[temporal_rows.policy.eq("random")]
            control_greedy = control_rows[control_rows.policy.eq("greedy")]
            control_random = control_rows[control_rows.policy.eq("random")]
            if greedy.empty or control_greedy.empty:
                continue
            temporal_advantage = float(greedy.hits.iloc[0] - random_policy.hits.mean())
            control_advantage = float(control_greedy.hits.mean() - control_random.hits.mean())
            entry = {
                "endpoint_label": str(greedy.endpoint_label.iloc[0]),
                "criterion": json.loads(greedy.criterion_applied.iloc[0]),
                "pool_hit_rate": float(greedy.pool_hit_rate.iloc[0]),
                "best_possible_hits": int(greedy.best_possible_hits.iloc[0]),
                "temporal_greedy_hits": int(greedy.hits.iloc[0]),
                "temporal_random_hits_mean": float(random_policy.hits.mean()),
                "temporal_random_hits_sd": float(random_policy.hits.std(ddof=1)),
                "temporal_advantage": temporal_advantage,
                "temporal_random_seeds_matching_greedy": int(
                    (random_policy.hits >= greedy.hits.iloc[0]).sum()),
                "random_split_greedy_hits_mean": float(control_greedy.hits.mean()),
                "random_split_random_hits_mean": float(control_random.hits.mean()),
                "random_split_advantage": control_advantage,
                "advantage_lost_to_time": control_advantage - temporal_advantage,
            }
            per_endpoint[endpoint] = entry
            gaps.append(entry)
        advantages = pd.Series([e["temporal_advantage"] for e in gaps], dtype=float)
        control = pd.Series([e["random_split_advantage"] for e in gaps], dtype=float)
        out["by_strictness"][strictness] = {
            "per_endpoint": per_endpoint,
            "across_endpoints": {
                "endpoints": int(len(advantages)),
                "mean_temporal_advantage": float(advantages.mean()) if len(advantages) else None,
                "mean_random_split_advantage": float(control.mean()) if len(control) else None,
                "endpoints_where_ranking_beat_random_under_time": int((advantages > 0).sum()),
                "endpoints_where_ranking_lost_to_random_under_time": int((advantages < 0).sum()),
                "units": "extra compounds meeting the criterion per 40 assays",
            },
        }
    return out


def run(frame: pd.DataFrame, settings: dict, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []
    for strictness in ("declared", "strict", "loose"):
        for endpoint in settings["endpoints"]:
            cases.extend(run_endpoint(frame, endpoint, settings, strictness))
        print(f"{strictness}: {len(cases)} cases so far", flush=True)
    metrics = pd.DataFrame(cases)
    metrics.to_csv(out / "discovery_case_metrics.csv", index=False)
    result = {"config": settings["discovery"], "analysis": analyse(metrics)}
    write_json(out / "discovery_comparison.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Discovery metric on the temporal holdout")
    parser.add_argument("--config", type=Path, default=Path("configs/temporal-v1.json"))
    parser.add_argument("--measurements", type=Path,
                        default=Path("output/expansionrx/measurements.csv"))
    parser.add_argument("--output", type=Path, default=Path("output/temporal"))
    args = parser.parse_args()
    settings = json.loads(args.config.read_text())
    settings["config_sha256"] = digest(args.config)
    result = run(pd.read_csv(args.measurements), settings, args.output)
    for strictness, block in result["analysis"]["by_strictness"].items():
        print(strictness, json.dumps(block["across_endpoints"], indent=2), flush=True)


if __name__ == "__main__":
    main()
