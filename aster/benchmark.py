"""Prepare immutable harder tasks, then run matched model comparisons.

This is an Aster replay protocol on MoleculeACE data, not its official leaderboard.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .data import canonicalize, digest, fingerprints, write_json
from .experiment import Config, LabelOracle, replay

ARMS = ["morgan_rf", "random", "morgan_ridge", "chemeleon_ridge"]


def scaffold(smiles: str) -> str:
    return MurckoScaffold.MurckoScaffoldSmiles(mol=Chem.MolFromSmiles(smiles), includeChirality=False) or "ACYCLIC"


def load_task(path: Path, task: dict) -> tuple[pd.DataFrame, dict]:
    if digest(path) != task["sha256"]:
        raise ValueError(f"Source checksum mismatch: {path}")
    raw = pd.read_csv(path)
    required = {"smiles", "y [pEC50/pKi]", "exp_mean [nM]", "split", "cliff_mol"}
    if not required.issubset(raw):
        raise ValueError(f"Unexpected dataset schema: {path}")
    if not raw.split.isin(["train", "test"]).all():
        raise ValueError("Unknown published partition.")
    rows, rejected = [], []
    for i, r in raw.iterrows():
        try:
            cx, identity = canonicalize(r.smiles)
            value = float(r["y [pEC50/pKi]"])
            concentration = float(r["exp_mean [nM]"])
            if not np.isfinite(value) or concentration <= 0 or not np.isfinite(concentration):
                raise ValueError("invalid_label")
            if not np.isclose(value, 9 - np.log10(concentration), atol=1e-5):
                raise ValueError("inconsistent_units")
            rows.append({"compound_id": f"{task['id']}:{i}", "source_row": i + 2,
                         "smiles": cx, "identity": identity, "value": value,
                         "published_split": r.split, "scaffold": scaffold(cx),
                         "cliff": int(r.cliff_mol)})
        except (ValueError, TypeError) as error:
            rejected.append({"source_row": i + 2, "reason": str(error)})
    frame = pd.DataFrame(rows)
    duplicated = frame.identity.duplicated(keep=False)
    rejected.extend({"source_row": int(i), "reason": "duplicate_identity"} for i in frame.loc[duplicated, "source_row"])
    frame = frame[~duplicated].reset_index(drop=True)
    return frame, {"raw_rows": len(raw), "eligible_rows_before_role_filter": len(frame),
                   "rejected": rejected, "endpoint": "pKi", "source_sha256": digest(path)}


def split_case(frame: pd.DataFrame, protocol: str, seed: int, size: int) -> dict:
    """Only structure/partition metadata affect the split; never outcomes/cliff flags."""
    rng = np.random.default_rng(seed)
    if protocol == "published":
        reservoir = np.flatnonzero(frame.published_split.eq("train"))
        audit = np.flatnonzero(frame.published_split.eq("test"))
        initial = rng.choice(reservoir, size, replace=False)
        pool = np.setdiff1d(reservoir, initial)
        unused = np.array([], dtype=int)
    elif protocol == "scaffold_transfer":
        groups = list(frame.groupby("scaffold", sort=True).indices.values())
        groups = [groups[i] for i in rng.permutation(len(groups))]
        buckets: list[list[int]] = [[], [], []]
        for group in groups:
            bucket = 0 if len(buckets[0]) < 0.2 * len(frame) else 1 if len(buckets[0]) + len(buckets[1]) < 0.8 * len(frame) else 2
            buckets[bucket].extend(int(i) for i in group)
        reservoir, pool, audit = [np.array(b, dtype=int) for b in buckets]
        if len(reservoir) < size:
            raise ValueError("Scaffold support reservoir too small; revise the protocol explicitly.")
        initial = rng.choice(reservoir, size, replace=False)
        unused = np.setdiff1d(reservoir, initial)
        scaffold_sets = [set(frame.iloc[b].scaffold) for b in [initial, pool, audit]]
        if any(scaffold_sets[i] & scaffold_sets[j] for i, j in [(0, 1), (0, 2), (1, 2)]):
            raise ValueError("Scaffold leakage.")
    else:
        raise ValueError(f"Unknown protocol {protocol}")
    if len(pool) < 40 or len(audit) < 20:
        raise ValueError("Insufficient acquisition/audit data for the fixed protocol.")
    sets = [set(x.tolist()) for x in [initial, pool, audit, unused]]
    if any(sets[i] & sets[j] for i in range(4) for j in range(i)):
        raise ValueError("Overlapping split roles.")
    return {"initial": initial.tolist(), "pool": pool.tolist(), "audit": audit.tolist(), "unused": unused.tolist()}


def prepare(config_path: Path, raw: Path, out: Path) -> None:
    if out.exists():
        raise ValueError("Prepared directory already exists; choose a new path.")
    config = json.loads(config_path.read_text())
    if config["scaffold_fractions"] != [0.2, 0.6, 0.2]:
        raise ValueError("This version implements 20/60/20 scaffold allocation only.")
    raw.mkdir(parents=True, exist_ok=True)
    frames, audit = {}, {}
    base = f"https://raw.githubusercontent.com/molML/MoleculeACE/{config['source_revision']}/MoleculeACE/Data/benchmark_data"
    for task in config["tasks"]:
        path = raw / f"{task['id']}.csv"
        if not path.exists():
            with urlopen(f"{base}/{path.name}", timeout=60) as response:
                payload = response.read()
            if hashlib.sha256(payload).hexdigest() != task["sha256"]:
                raise ValueError("Downloaded dataset checksum mismatch.")
            path.write_bytes(payload)
        frames[task["id"]], audit[task["id"]] = load_task(path, task)
    development_ids = set().union(*(set(frames[t["id"]].identity) for t in config["tasks"] if t["role"] == "development"))
    for task in config["tasks"]:
        frame = frames[task["id"]]
        overlap = frame.identity.isin(development_ids) if task["role"] == "evaluation" else pd.Series(False, index=frame.index)
        audit[task["id"]]["development_overlap_removed"] = frame.loc[overlap, "compound_id"].tolist()
        frames[task["id"]] = frame[~overlap].reset_index(drop=True)
    cases = []
    for task in config["tasks"]:
        frame = frames[task["id"]]
        for protocol in config["protocols"]:
            for seed in config["seeds"]:
                for size in config["support_sizes"]:
                    split = split_case(frame, protocol, seed, size)
                    cases.append({"id": f"{task['id']}__{protocol}__n{size}__s{seed}", "task": task["id"],
                                  "role": task["role"], "protocol": protocol, "seed": seed,
                                  "support_size": size, **split})
    out.mkdir(parents=True)
    hashes = {}
    for task_id, frame in frames.items():
        frame.to_csv(out / f"{task_id}.csv", index=False)
        hashes[task_id] = digest(out / f"{task_id}.csv")
        audit[task_id]["eligible_rows"] = len(frame)
    overlap_report = {}
    ids = list(frames)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            overlap_report[f"{a} / {b}"] = len(set(frames[a].identity) & set(frames[b].identity))
    write_json(out / "plan.json", {"config": config, "config_sha256": digest(config_path),
                                   "prepared_hashes": hashes, "cases": cases,
                                   "cross_task_identity_overlap": overlap_report,
                                   "selection_basis": "First three lexicographically sorted Ki task IDs; no performance-based selection.",
                                   "pretraining_overlap": "Unresolved. CheMeleon was evaluated on MoleculeACE in prior work; no claim of unseen structures or pristine model-selection holdout."})
    write_json(out / "data_audit.json", audit)
    print(f"Prepared {len(cases)} immutable cases at {out}", flush=True)


def run_suite(prepared: Path, out: Path, role: str, arms: list[str], checkpoint: Path) -> None:
    plan_path = prepared / "plan.json"
    plan = json.loads(plan_path.read_text())
    settings = plan["config"]
    out.mkdir(parents=True, exist_ok=True)
    versions = {n: importlib.metadata.version(n) for n in ["rdkit", "numpy", "pandas", "scikit-learn"]}
    contract = {"plan_sha256": digest(plan_path), "versions": versions,
                "source_hashes": {p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))}}
    contract_path = out / "run_contract.json"
    if contract_path.exists() and json.loads(contract_path.read_text()) != contract:
        raise ValueError("Code, environment or plan changed; use a new output directory.")
    write_json(contract_path, contract)
    for task in settings["tasks"]:
        if task["role"] != role:
            continue
        path = prepared / f"{task['id']}.csv"
        if digest(path) != plan["prepared_hashes"][task["id"]]:
            raise ValueError("Prepared dataset changed.")
        frame = pd.read_csv(path)
        fp = fingerprints(frame.smiles.tolist())
        embeddings = None
        if "chemeleon_ridge" in arms:
            from .representations import frozen_chemeleon
            embeddings = frozen_chemeleon(frame.smiles.tolist(), checkpoint, settings["checkpoint_sha256"], Path("data/embeddings"))
        for case in [c for c in plan["cases"] if c["task"] == task["id"]]:
            working = case["initial"] + case["pool"]
            audit_indices = case["audit"]
            cfg = Config(initial_size=case["support_size"], rounds=settings["rounds"],
                         batch_size=settings["batch_size"], seeds=(case["seed"],),
                         trees=settings["trees"], hit_threshold=settings["hit_threshold"])
            cfg.validate(len(working))
            for arm in arms:
                artifact = out / f"{case['id']}__{arm}.json"
                if artifact.exists():
                    continue
                x = embeddings if arm == "chemeleon_ridge" else fp
                factory = (lambda seed: make_pipeline(StandardScaler(), Ridge(alpha=settings["ridge_alpha"]))) if arm.endswith("ridge") else None
                result = replay(x[working], x[audit_indices], LabelOracle(frame.iloc[working].value.to_numpy()),
                                np.arange(cfg.initial_size), cfg, case["seed"],
                                "random" if arm == "random" else "greedy", model_factory=factory)
                # Everything below uses outcomes only for retrospective evaluation.
                actual = frame.iloc[audit_indices].value.to_numpy()
                cliff = frame.iloc[audit_indices].cliff.to_numpy(dtype=bool)
                pool_values = frame.iloc[case["pool"]].value.to_numpy()
                elite_threshold = float(np.quantile(pool_values, 0.9))
                elite_count = int((pool_values >= elite_threshold).sum())
                initial_scaffolds = set(frame.iloc[case["initial"]].scaffold)
                found_scaffolds: set[str] = set()
                for selection in result["selections"]:
                    row = frame.iloc[working[selection.pop("index")]]
                    selection["predicted_pki"] = selection.pop("predicted_pic50")
                    selection["observed_pki"] = selection.pop("observed_pic50")
                    selection["top_decile"] = bool(row.value >= elite_threshold)
                    selection["compound_id"] = row.compound_id
                    selection["scaffold"] = row.scaffold
                    selection["novel_to_initial_scaffolds"] = row.scaffold not in initial_scaffolds
                for h, prediction in zip(result["history"], result["audit_predictions"]):
                    h["best_observed_pki"] = h.pop("best_observed_pic50")
                    error = prediction - actual
                    h["audit_mae"] = float(np.abs(error).mean())
                    h["audit_rmse"] = float(np.sqrt(np.mean(error ** 2)))
                    h["audit_cliff_rmse"] = float(np.sqrt(np.mean(error[cliff] ** 2))) if cliff.any() else None
                    for pick in result["selections"]:
                        if pick["round"] == h["round"] and pick["hit"]:
                            found_scaffolds.add(pick["scaffold"])
                    h["active_scaffolds_found"] = len(found_scaffolds)
                    h["active_scaffolds_novel_to_initial"] = len(found_scaffolds - initial_scaffolds)
                    h["top_decile_found"] = sum(s["top_decile"] for s in result["selections"] if s["round"] <= h["round"])
                    h["top_decile_recall"] = h["top_decile_found"] / elite_count
                pool_hits = int((frame.iloc[case["pool"]].value >= cfg.hit_threshold).sum())
                payload = {"case_id": case["id"], "task": case["task"], "role": role,
                           "protocol": case["protocol"], "support_size": cfg.initial_size,
                           "seed": case["seed"], "arm": arm, "endpoint": "pKi",
                           "pool_size": len(case["pool"]), "pool_hits": pool_hits,
                           "top_decile_threshold_pki": elite_threshold, "top_decile_pool_count": elite_count,
                           "audit_size": len(audit_indices), "audit_cliff_count": int(cliff.sum()),
                           "history": result["history"], "selections": result["selections"],
                           "audit_ids": frame.iloc[audit_indices].compound_id.tolist(),
                           "audit_predictions": [p.tolist() for p in result["audit_predictions"]]}
                write_json(artifact.with_suffix(".tmp"), payload)
                artifact.with_suffix(".tmp").replace(artifact)
                print(f"{case['id']} {arm}: {result['history'][-1]['additional_hits']}/40 hits", flush=True)
    build_report(prepared, out)


def build_report(prepared: Path, out: Path) -> None:
    records = [json.loads(p.read_text()) for p in sorted(out.glob("*__*.json"))]
    if not records:
        return
    rows = []
    for record in records:
        for h in record["history"]:
            rows.append({k: record[k] for k in ["task", "role", "protocol", "support_size", "seed", "arm", "pool_size", "pool_hits"]} | h)
    frame = pd.DataFrame(rows)
    frame.to_csv(out / "round_metrics.csv", index=False)
    last = frame[frame["round"] == frame["round"].max()].copy()
    last.to_csv(out / "final_metrics.csv", index=False)
    grouped = last.groupby(["task", "role", "protocol", "support_size", "arm"], sort=True)[["additional_hits", "top_decile_found", "top_decile_recall", "audit_mae", "active_scaffolds_novel_to_initial"]].mean().reset_index()
    grouped.to_csv(out / "summary.csv", index=False)
    keys = ["task", "role", "protocol", "support_size", "seed"]
    contrasts = []
    for metric in ["additional_hits", "top_decile_found", "audit_mae"]:
        paired = last.pivot(index=keys, columns="arm", values=metric)
        for comparator in ["random", "morgan_rf", "morgan_ridge"]:
            if "chemeleon_ridge" in paired and comparator in paired:
                delta = (paired.chemeleon_ridge - paired[comparator]).dropna()
                for key, val in delta.items():
                    contrasts.append(dict(zip(keys, key)) | {"comparison": f"chemeleon_ridge - {comparator}", "metric": metric, "difference": float(val)})
    pd.DataFrame(contrasts).to_csv(out / "paired_differences.csv", index=False)
    plan = json.loads((prepared / "plan.json").read_text())
    completed = {(r["case_id"], r["arm"]) for r in records}
    expected = {(c["id"], a) for c in plan["cases"] for a in ARMS}
    write_json(out / "coverage.json", {"completed": len(completed), "expected": len(expected),
                                       "missing": [list(x) for x in sorted(expected - completed)]})
    os.environ.setdefault("MPLCONFIGDIR", str(Path(".mplconfig").resolve()))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tasks = [t for t in plan["config"]["tasks"] if t["id"] in set(last.task)]
    fig, axes = plt.subplots(len(tasks), 2, figsize=(12, 3.5 * len(tasks)), squeeze=False)
    colors = ["#6956bb", "#888888", "#4c9a8a", "#e29542"]
    for row_number, task in enumerate(tasks):
        for column, protocol in enumerate(["published", "scaffold_transfer"]):
            axis = axes[row_number, column]
            subset = last[(last.task == task["id"]) & (last.protocol == protocol)]
            for i, arm in enumerate(ARMS):
                values = subset[subset.arm == arm].groupby("support_size").top_decile_found.agg(["mean", "std"])
                if len(values):
                    axis.bar(np.arange(len(values)) + (i - 1.5) * .2, values["mean"], width=.2,
                             yerr=values["std"].fillna(0), color=colors[i], label=arm, capsize=2)
            axis.set_xticks([0, 1], ["32 initial labels", "64 initial labels"])
            axis.set_title(f"{task['id']} ({task['role']}) · {protocol}", fontsize=10)
            axis.set_ylabel("Top-decile compounds found / 40")
            axis.set_ylim(0, 40)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Aster broader evaluation · mean ± one seed SD; 3 paired seeds", fontsize=12)
    fig.tight_layout()
    fig.savefig(out / "comparison.png", dpi=160)
    plt.close(fig)
    table = ["| Task | Role | Protocol | Starting labels | Model/policy | Hits / 40 | Top-decile found / 40 | Audit MAE | New active scaffolds |",
             "| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: |"]
    for r in grouped.itertuples():
        table.append(f"| {r.task} | {r.role} | {r.protocol} | {r.support_size} | {r.arm} | {r.additional_hits:.2f} | {r.top_decile_found:.2f} | {r.audit_mae:.3f} | {r.active_scaffolds_novel_to_initial:.2f} |")
    text = """# Aster broader evaluation

This is a custom retrospective stress test, not a new blind challenge or a prospective discovery result.

## Protocol

- Three revision-pinned MoleculeACE Ki tasks: the first is development, the other two evaluation. Shared molecular identities from development are excluded from evaluation tasks.
- Start with 32 or 64 measurements; acquire five batches of eight; three paired seeds. A hit is **pKi ≥ 7 (Ki ≤ 100 nM)**, predeclared before running. This differs from the original pIC50 ≥ 6 experiment; do not compare raw hit counts between those datasets as if the tasks were identical.
- `published`: acquire only within the original train partition; original test is audit-only. These are not necessarily chronological splits.
- `scaffold_transfer`: a label-independent shuffled whole-scaffold allocation creates approximately 20% support reservoir, 60% acquisition pool, 20% audit. Sample the initial support from its reservoir. Unused reservoir compounds are excluded. Initial, acquisition and audit scaffolds are disjoint. After acquiring a scaffold, subsequent compounds in it are no longer entirely unfamiliar.
- `morgan_rf`: the original fingerprint/random-forest greedy approach, 200 trees. `random`: matched random selection using the same predictor for audit metrics. `morgan_ridge`: standardized fingerprints plus ridge regression. `chemeleon_ridge`: frozen pretrained CheMeleon embeddings plus the same standardized ridge head (alpha=10). The two ridge arms isolate representation choice; RF versus CheMeleon-ridge compares whole pipelines.
- Scaling and head fitting see only acquired labels/features. Hidden and audit outcomes never select compounds or tune settings. Seeds, threshold, models and splits were fixed before outcomes. No head search or encoder fine-tuning was performed.
- Published cliff flags are used only for post-run audit errors. They are label-derived and never enter splitting or acquisition.
- Primary ranking measure: number of acquired compounds in the acquisition pool's strongest 10%, defined by its 90th percentile with ties included. The evaluator computes this from hidden outcomes only AFTER selection; the model never receives this threshold. Pool-relative cutoffs measure ranking, not a clinical or common biological threshold. Absolute hits remain a secondary metric.
- Protocol v2 added this ranking measure after ceiling effects on the development target in v1, before running either evaluation target. The v1 development output is exploratory and not part of this final comparison.

## Results

Rows show seed means. Inspect `final_metrics.csv` for each seed and `paired_differences.csv` for matched contrasts. Partial runs contain only completed arms/cases; missing cases are not treated as zeros.

""" + f"Completed {len(completed)}/{len(expected)} planned model/case runs. See `coverage.json` for missing cases.\n\n![Model comparison](comparison.png)\n\n" + "\n".join(table) + "\n\n## Provenance and limits\n\n"
    text += f"Plan SHA256: `{digest(prepared / 'plan.json')}`. Cross-task overlap after development removal: `{plan['cross_task_identity_overlap']}`.\n\n"
    text += """Exact inputs and splits are in the prepared directory; model-run files store individual selections, pre-reveal predictions and per-round audit predictions. `run_contract.json` pins code and package versions. CheMeleon feature caches also pin checkpoint, structures and neural package versions.

These targets can share compounds and biology. Three seeds and two evaluation tasks are an initial broader comparison, not independent evidence across drug discovery. Report task-level results; do not compute a misleading across-target confidence interval from every correlated case. CheMeleon has previously been evaluated on MoleculeACE, and structure-pretraining overlap is unresolved. The held-out role here governs this project, not all historical development of the pretrained model.

MoleculeACE aggregates source ChEMBL measurements; endpoint consistency and raw censoring cannot be fully audited from this table. Removing duplicate identities does not remove all chemical similarity or tautomer equivalence. Scaffold splits are one stress test, not proof of biological novelty. pKi and pIC50 are different endpoints.

Sources: [MoleculeACE data/code](https://github.com/molML/MoleculeACE), [activity-cliff paper](https://doi.org/10.1021/acs.jcim.2c01073), [CheMeleon paper](https://arxiv.org/abs/2506.15792), [official embedding example](https://github.com/chrissly31415/chemeleon/blob/main/chemeleon_fingerprint.py). MoleculeACE repository license is MIT; its underlying ChEMBL data retain their own attribution/ShareAlike terms. Do not infer data or checkpoint terms from a code license.

Next: use the development task for a bounded fine-tuning comparison and freeze its settings before another evaluation. Once these evaluation outcomes are inspected, do not reuse them for tuning and call a subsequent run a fresh blind result.
"""
    (out / "REPORT.md").write_text(text)
    print(f"Report saved to {out / 'REPORT.md'}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "run", "report"])
    parser.add_argument("--config", type=Path, default=Path("configs/broader-v2.json"))
    parser.add_argument("--raw", type=Path, default=Path("data/moleculeace"))
    parser.add_argument("--prepared", type=Path, default=Path("artifacts/broader-v2-prepared"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/broader-v2"))
    parser.add_argument("--role", choices=["development", "evaluation"], default="development")
    parser.add_argument("--arms", nargs="+", choices=ARMS, default=ARMS[:3])
    parser.add_argument("--checkpoint", type=Path, default=Path("data/models/chemeleon_mp.pt"))
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.config, args.raw, args.prepared)
        elif args.command == "run":
            run_suite(args.prepared, args.output, args.role, args.arms, args.checkpoint)
        else:
            build_report(args.prepared, args.output)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Aster: {error}\n")


if __name__ == "__main__":
    main()
