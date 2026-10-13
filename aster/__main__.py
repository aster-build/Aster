from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import subprocess
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .data import curate, digest, fetch, fingerprints, provenance, write_json
from .experiment import Config, LabelOracle, replay
from .report import report


def run(raw_dir: Path, out: Path, config: Config) -> dict:
    source = fetch(raw_dir)
    clean, qc_rows, qc = curate(pd.read_csv(source))
    train = clean[clean.split.eq("Train")].reset_index(drop=True)
    audit = clean[clean.split.eq("Test")].reset_index(drop=True)
    config.validate(len(train))
    if out.exists():
        raise ValueError(f"Output already exists: {out}. Choose a new --output directory to preserve prior results.")
    out.mkdir(parents=True)
    write_json(out / "config.json", config.to_dict())
    manifest = provenance(source)
    write_json(out / "manifest.json", manifest)
    (out / "source-record.json").write_bytes((raw_dir / "source-record.json").read_bytes())
    write_json(out / "qc_summary.json", qc)
    qc_rows.to_csv(out / "qc_rows.csv", index=False)
    clean.to_csv(out / "curated.csv", index=False)
    package_dir = Path(__file__).parent
    revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    write_json(out / "environment.json", {
        "python": platform.python_version(), "platform": platform.platform(),
        "packages": {name: importlib.metadata.version(name) for name in ["rdkit", "numpy", "pandas", "scikit-learn", "matplotlib", "joblib"]},
        "git_revision": revision.stdout.strip() if revision.returncode == 0 else None,
        "source_sha256": {p.name: digest(p) for p in sorted(package_dir.glob("*.py"))},
    })
    print(f"Validated {len(train)} training-pool compounds and {len(audit)} audit compounds.", flush=True)
    features = fingerprints(train.canonical_cxsmiles.tolist(), config.radius, config.bits)
    audit_features = fingerprints(audit.canonical_cxsmiles.tolist(), config.radius, config.bits)
    history, selections, audit_rows, splits = [], [], [], []
    for seed in config.seeds:
        initial = np.sort(np.random.default_rng(seed).choice(len(train), config.initial_size, replace=False))
        pool = np.setdiff1d(np.arange(len(train)), initial)
        splits.append({"seed": seed, "initial_ids": train.iloc[initial].compound_id.tolist(),
                       "pool_ids": train.iloc[pool].compound_id.tolist(), "audit_ids": audit.compound_id.tolist()})
        for strategy in ["greedy", "random"]:
            result = replay(features, audit_features, LabelOracle(train.pic50.to_numpy()), initial, config, seed, strategy)
            # Labels from the audit set are read only here, after the policy finishes.
            actual = audit.pic50.to_numpy(dtype=float)
            for row, prediction in zip(result["history"], result["audit_predictions"]):
                row["audit_mae"] = float(np.abs(prediction - actual).mean())
                row["audit_rmse"] = float(np.sqrt(np.mean((prediction - actual) ** 2)))
                audit_rows.extend({"seed": seed, "strategy": strategy, "round": row["round"],
                                   "compound_id": cid, "predicted_pic50": float(pred), "observed_pic50": float(y)}
                                  for cid, pred, y in zip(audit.compound_id, prediction, actual))
            history.extend(result["history"])
            for selection in result["selections"]:
                selection["compound_id"] = train.iloc[selection.pop("index")].compound_id
            selections.extend(result["selections"])
            if seed == config.seeds[0]:
                joblib.dump(result["model"], out / f"seed0_{strategy}_model.joblib")
                if strategy == "greedy":
                    measured = set(train.iloc[initial].compound_id) | {r["compound_id"] for r in result["selections"]}
                    remaining = train[~train.compound_id.isin(measured)]
                    if len(remaining):
                        export = remaining[["compound_id", "canonical_cxsmiles"]].copy()
                        export["predicted_pic50"] = result["model"].predict(features[remaining.index])
                        export.sort_values("predicted_pic50", ascending=False).to_csv(out / "seed0_greedy_remaining.csv", index=False)
            print(f"Seed {seed}: {strategy} recovered {result['history'][-1]['additional_hits']} additional hits.", flush=True)
    write_json(out / "splits.json", splits)
    frame = pd.DataFrame(history)
    frame.to_csv(out / "round_metrics.csv", index=False)
    pd.DataFrame(selections).to_csv(out / "selections.csv", index=False)
    pd.DataFrame(audit_rows).to_csv(out / "audit_predictions.csv", index=False)
    summary = report(out, frame, config, qc, manifest)
    write_json(out / "artifact_checksums.json", {p.name: digest(p) for p in sorted(out.iterdir()) if p.is_file()})
    print(f"Report: {(out / 'REPORT.md').resolve()}", flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Aster retrospective potency-selection benchmark")
    parser.add_argument("command", choices=["fetch", "run"])
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/baseline"))
    parser.add_argument("--initial-size", type=int, default=100)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(10)))
    parser.add_argument("--trees", type=int, default=200)
    parser.add_argument("--hit-threshold", type=float, default=6.0)
    args = parser.parse_args()
    try:
        if args.command == "fetch":
            print(fetch(args.raw_dir))
        else:
            config = Config(initial_size=args.initial_size, rounds=args.rounds, batch_size=args.batch_size,
                            seeds=tuple(args.seeds), trees=args.trees, hit_threshold=args.hit_threshold)
            print(json.dumps(run(args.raw_dir, args.output, config), indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, f"Aster: {error}\n")


if __name__ == "__main__":
    main()
