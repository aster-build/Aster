"""Controlled head development and sealed, additional-target replay evaluation."""
from __future__ import annotations
import argparse
import importlib.metadata
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from .data import digest, fingerprints, write_json
from .experiment import Config, LabelOracle, replay
from .heads import make_head
from .representations import frozen_chemeleon


class Monitored:
    def __init__(self, model, log, guard):
        self.model, self.log, self.guard = model, log, guard

    def fit(self, x, y):
        self.model.fit(x, y)
        return self

    def predict(self, x):
        p = np.asarray(self.model.predict(x), dtype=float)
        if not np.isfinite(p).all():
            raise ValueError("Nonfinite predictions; do not silently rank them")
        self.log.append({"n": len(p), "min": float(p.min()), "max": float(p.max()),
                         "outside_guard": int(((p < self.guard[0]) | (p > self.guard[1])).sum())})
        return p


def seal(out, inputs):
    out.mkdir(parents=True, exist_ok=True)
    contract = {"inputs": inputs,
                "versions": {n: importlib.metadata.version(n) for n in ["numpy", "scikit-learn", "rdkit", "chemprop", "torch"]},
                "source_hashes": {p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))}}
    path = out / "contract.json"
    if path.exists() and json.loads(path.read_text()) != contract:
        raise ValueError("Contract changed; use a new output directory")
    write_json(path, contract)


def run_case(frame, x, case, settings, arm, factory, guard):
    working, audit = case["initial"] + case["pool"], case["audit"]
    cfg = Config(initial_size=case["support_size"], rounds=settings["rounds"],
                 batch_size=settings["batch_size"], seeds=(case["seed"],),
                 trees=settings["trees"], hit_threshold=settings["hit_threshold"])
    cfg.validate(len(working))
    logs, fitted = [], []
    def build(seed):
        model = factory(seed)
        fitted.append(model)
        return Monitored(model, logs, guard)
    start = time.monotonic()
    result = replay(x[working], x[audit], LabelOracle(frame.iloc[working].value.to_numpy()),
                    np.arange(cfg.initial_size), cfg, case["seed"],
                    "random" if arm == "random" else "greedy", build)
    # Outcome-based diagnostics begin only once the entire replay is complete.
    threshold = float(np.quantile(frame.iloc[case["pool"]].value, .9))
    actual = frame.iloc[audit].value.to_numpy()
    cliff = frame.iloc[audit].cliff.to_numpy(dtype=bool)
    for s in result["selections"]:
        row = frame.iloc[working[s["index"]]]
        s["compound_id"] = row.compound_id
        s["top_decile"] = bool(row.value >= threshold)
        s["predicted_pki"] = s.pop("predicted_pic50")
        s["observed_pki"] = s.pop("observed_pic50")
    for h, p in zip(result["history"], result["audit_predictions"]):
        error = p - actual
        h["audit_mae"] = float(np.abs(error).mean())
        h["audit_rmse"] = float(np.sqrt(np.mean(error ** 2)))
        h["audit_cliff_rmse"] = float(np.sqrt(np.mean(error[cliff] ** 2))) if cliff.any() else None
        h["top_decile_found"] = sum(s["top_decile"] for s in result["selections"] if s["round"] <= h["round"])
        h["best_observed_pki"] = h.pop("best_observed_pic50")
    return {"case_id": case["id"], "task": case["task"], "arm": arm,
            "protocol": case["protocol"], "support_size": cfg.initial_size, "seed": case["seed"],
            "seconds": time.monotonic() - start, "history": result["history"],
            "selections": result["selections"], "prediction_checks": logs,
            "audit_ids": frame.iloc[audit].compound_id.tolist(),
            "audit_predictions": [p.tolist() for p in result["audit_predictions"]],
            "training_diagnostics": [getattr(m, "diagnostics_", None) for m in fitted]}


def reference_factory(arm, settings):
    if arm == "morgan_ridge":
        return lambda seed: make_head({"mode": "standard", "alpha": settings["ridge_alpha"]})
    return lambda seed: RandomForestRegressor(n_estimators=settings["trees"], min_samples_leaf=2,
                                               max_features=1., random_state=seed, n_jobs=1)


def summarize(out):
    records = [json.loads(p.read_text()) for p in sorted(out.glob("cases/*.json"))]
    rows = []
    for r in records:
        rows.append({k: r[k] for k in ["case_id", "task", "protocol", "support_size", "seed", "arm", "seconds"]} |
                    {"top_decile_found": r["history"][-1]["top_decile_found"],
                     "additional_hits": r["history"][-1]["additional_hits"],
                     "final_mae": r["history"][-1]["audit_mae"],
                     "mean_round_mae": np.mean([h["audit_mae"] for h in r["history"]]),
                     "worst_round_mae": max(h["audit_mae"] for h in r["history"]),
                     "outside_guard": sum(p["outside_guard"] for p in r["prediction_checks"]),
                     "prediction_min": min(p["min"] for p in r["prediction_checks"]),
                     "prediction_max": max(p["max"] for p in r["prediction_checks"])})
    frame = pd.DataFrame(rows)
    frame.to_csv(out / "metrics.csv", index=False)
    return frame


def development(config_path, out):
    study = json.loads(config_path.read_text())
    prepared = Path(study["development_prepared"])
    plan = json.loads((prepared / "plan.json").read_text())
    settings = plan["config"]
    seal(out, {"study": digest(config_path), "plan": digest(prepared / "plan.json")})
    cases = [c for c in plan["cases"] if c["role"] == "development" and c["task"] == study["development_task"]]
    if not cases:
        raise ValueError("No development cases")
    path = prepared / f"{study['development_task']}.csv"
    if digest(path) != plan["prepared_hashes"][study["development_task"]]:
        raise ValueError("Prepared data changed")
    frame = pd.read_csv(path)
    fp = fingerprints(frame.smiles.tolist())
    x = frozen_chemeleon(frame.smiles.tolist(), Path("data/models/chemeleon_mp.pt"), settings["checkpoint_sha256"], Path("data/embeddings"))
    (out / "cases").mkdir(exist_ok=True)
    arms = [r["id"] for r in study["candidates"]] + ["morgan_ridge", "morgan_rf", "random"]
    for case in cases:
        for arm in arms:
            path = out / "cases" / f"{case['id']}__{arm}.json"
            if path.exists():
                continue
            recipe = next((r for r in study["candidates"] if r["id"] == arm), None)
            factory = (lambda seed, r=recipe: make_head(r)) if recipe else reference_factory(arm, settings)
            result = run_case(frame, x if recipe else fp, case, settings, arm, factory, study["gate"]["prediction_guard"])
            write_json(path, result)
            print(f"{case['id']} {arm}: top={result['history'][-1]['top_decile_found']} MAE={result['history'][-1]['audit_mae']:.3f}", flush=True)
    scores = summarize(out)
    if len(scores) != len(cases) * len(arms):
        raise ValueError("Incomplete development coverage")
    agg = scores.groupby("arm").agg(top=("top_decile_found", "mean"), mae=("mean_round_mae", "mean"),
                                    worst_mae=("worst_round_mae", "max"), outliers=("outside_guard", "sum"))
    gate = study["gate"]
    agg["passes"] = ((agg.mae <= gate["mean_round_mae_max"]) & (agg.worst_mae <= gate["worst_round_mae_max"]) &
                     (agg.outliers == 0) & (agg.top >= gate["selection_fraction_of_current_min"] * agg.loc["standard_10", "top"]) &
                     (agg.top >= gate["selection_fraction_of_random_min"] * agg.loc["random", "top"]))
    agg.to_csv(out / "head_summary.csv")
    passing = agg.loc[[r["id"] for r in study["candidates"]]].query("passes").reset_index().sort_values(["top", "mae", "arm"], ascending=[False, True, True])
    freeze = {"study_sha256": digest(config_path), "development_contract_sha256": digest(out / "contract.json"),
              "development_metrics_sha256": digest(out / "metrics.csv"), "gate": gate,
              "selected": None if passing.empty else next(r for r in study["candidates"] if r["id"] == passing.iloc[0].arm),
              "new_targets": study["additional_targets"], "fine_tuning": study["fine_tuning"],
              "status": "no_candidate_passed" if passing.empty else "frozen_before_additional_target_evaluation"}
    write_json(out / "frozen_recipe.json", freeze)
    print(agg.to_string(), flush=True)
    print(f"Frozen selection: {freeze['selected']}", flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["develop"])
    p.add_argument("--config", type=Path, default=Path("configs/stability-v1.json"))
    p.add_argument("--output", type=Path, default=Path("artifacts/stability-v1"))
    args = p.parse_args()
    development(args.config, args.output)


if __name__ == "__main__":
    main()
