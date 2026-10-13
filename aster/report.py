"""Static, exportable evaluation artifacts; never feed scores back to selection."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from .data import write_json
from .experiment import Config


def summarize(history: pd.DataFrame, config: Config) -> dict:
    final = history[history["round"].eq(config.rounds)]
    paired = final.pivot(index="seed", columns="strategy", values="additional_hits")
    differences = (paired.greedy - paired.random).to_numpy(dtype=float)
    interval = None
    if len(differences) > 1:
        rng = np.random.default_rng(20261013)
        bootstrap = rng.choice(differences, size=(10000, len(differences)), replace=True).mean(axis=1)
        interval = np.quantile(bootstrap, [0.025, 0.975]).tolist()
    return {
        "budget": config.rounds * config.batch_size, "seeds": len(paired),
        "hit_threshold_pic50": config.hit_threshold,
        "greedy_mean_hits": float(paired.greedy.mean()),
        "random_mean_hits": float(paired.random.mean()),
        "mean_paired_hit_difference": float(differences.mean()),
        "paired_bootstrap_95_interval": interval,
        "greedy_wins_ties_losses": [int((differences > 0).sum()), int((differences == 0).sum()), int((differences < 0).sum())],
        "interval_scope": "Variation across paired initializations on one fixed dataset, not uncertainty across targets or prospective laboratories.",
    }


def report(out: Path, history: pd.DataFrame, config: Config, qc: dict, manifest: dict) -> dict:
    # Keep plotting caches inside the workspace; no GUI backend needed.
    os.environ.setdefault("MPLCONFIGDIR", str(out.resolve() / ".mplconfig"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    summary = summarize(history, config)
    write_json(out / "summary.json", summary)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    for strategy, color, label in [("greedy", "#7165c7", "Highest predicted potency"),
                                   ("random", "#7b8794", "Random selection")]:
        rows = history[history.strategy.eq(strategy)]
        for axis, metric in zip(axes, ["additional_hits", "audit_mae"]):
            grouped = rows.groupby("assays_acquired")[metric].agg(["mean", "std"]).fillna(0)
            x = grouped.index.to_numpy()
            axis.plot(x, grouped["mean"], color=color, label=label, marker="o")
            axis.fill_between(x, grouped["mean"] - grouped["std"], grouped["mean"] + grouped["std"], color=color, alpha=0.15)
            axis.set_xlabel("Additional assays acquired")
            axis.grid(alpha=0.15)
    axes[0].set_ylabel(f"New hits (pIC50 ≥ {config.hit_threshold:g})")
    axes[0].set_title("Discovery in the published Train partition")
    axes[0].set_ylim(bottom=0)
    axes[0].legend(fontsize=8)
    axes[1].set_ylabel("MAE (pIC50 units)")
    axes[1].set_title("Untouched published Test partition")
    fig.suptitle(f"Aster · {len(config.seeds)} paired seeds · mean ± 1 seed SD", fontsize=12)
    fig.tight_layout()
    fig.savefig(out / "discovery_curves.png", dpi=180)
    plt.close(fig)

    interval = summary["paired_bootstrap_95_interval"]
    interval_text = "Not estimated with one seed." if interval is None else f"[{interval[0]:.2f}, {interval[1]:.2f}] additional hits"
    table = []
    for strategy in ["greedy", "random"]:
        final = history[(history.strategy == strategy) & (history["round"] == config.rounds)]
        table.append(f"| {strategy} | {final.additional_hits.mean():.2f} | {final.audit_mae.mean():.3f} | {final.audit_rmse.mean():.3f} |")
    text = f"""# Aster first-milestone results

This is a retrospective simulation on one antiviral assay, not a prospective discovery claim.

## Result

After {summary['budget']} additional assays, highest-predicted-potency selection recovered **{summary['greedy_mean_hits']:.2f} hits on average**, compared with **{summary['random_mean_hits']:.2f}** for random selection ({len(config.seeds)} paired seeds).

Mean paired difference: **{summary['mean_paired_hit_difference']:+.2f} hits**. Descriptive paired bootstrap 95% interval: {interval_text}. Wins/ties/losses: {summary['greedy_wins_ties_losses']}.

This interval reflects initialization variability on a fixed dataset. It does not measure generalization to new targets, and repeated seeds are not independent biological campaigns.

| Strategy | Mean additional hits | Final test MAE | Final test RMSE |
| --- | ---: | ---: | ---: |
{chr(10).join(table)}

![Discovery and prediction curves](discovery_curves.png)

## Protocol

- Endpoint: SARS-CoV-2 Mpro pIC50, used directly as published (no second log transform).
- Published Train partition: initial {config.initial_size} compounds sampled without consulting labels; remaining eligible Train compounds form the hidden acquisition pool.
- Published Test partition: audit only; predictions scored after each replay has completed. Its labels never enter fitting, selection or early stopping.
- {config.rounds} rounds × {config.batch_size} compounds. Count only newly acquired hits, excluding initial support hits.
- A hit is pIC50 ≥ {config.hit_threshold:g}; IC50 ≤ {10 ** (9-config.hit_threshold):g} nM. This is a predefined benchmark convention, not drug viability.
- Morgan fingerprints: radius {config.radius}, {config.bits} bits, chirality enabled. Random forest: {config.trees} trees, minimum leaf size {config.min_samples_leaf}, max_features={config.max_features}, one CPU job.
- Same initial support and model seed for both strategies. Models refit from scratch using only acquired labels, including the final round.
- All configuration was fixed before the run; no tuning on audit results.

## Data audit

Raw rows: {qc['raw_rows']}. Eligible rows: {qc['eligible_rows']}. Published partitions after QC: {qc['eligible_by_published_split']}.

Row status counts: {qc['row_status_counts']}.

Policy: {qc['policy']}

Source checksum (SHA256): `{manifest['sha256']}`.

Source: [ASAP–Polaris–OpenADMET v2, Scheen et al.](https://doi.org/10.5281/zenodo.15582067), CC BY 4.0. Full authorship and source metadata are retained in `manifest.json` and `source-record.json`.

## Artifacts

- `config.json`, `environment.json`, `manifest.json`: configuration, package/code hashes and dataset provenance.
- `qc_rows.csv`, `qc_summary.json`, `curated.csv`: source-row audit and eligible measurements (contain labels; benchmark-controller use only).
- `splits.json`: exact initial IDs, acquisition-pool IDs and audit IDs for each seed.
- `round_metrics.csv`: per-seed learning curves, audit MAE/RMSE and discovery counts.
- `selections.csv`: each chosen compound, prediction before revelation, outcome, round and rank.
- `audit_predictions.csv`: per-round predictions for the published Test partition.
- `seed0_greedy_model.joblib`, `seed0_random_model.joblib`: final fitted models for the first configured seed. Load only trusted local model files.
- `seed0_greedy_remaining.csv`: final predictions for compounds still unmeasured in the first greedy replay; includes no observed potency column.

## Limits and next experiment

- The source has numeric potency but no censoring, replicate, or detailed QC flags; values are modeled as supplied. Assay-floor measurements may therefore be censored even though encoded numerically.
- The molecular identity check is conservative but does not unify tautomers or all alternate stereo encodings. Enhanced CX stereo metadata is retained; Morgan features do not fully represent every enhanced stereo relationship.
- The acquisition pool is sampled from previously measured Train compounds, not a prospective vendor library. This is a custom replay, not an official challenge submission or a chronological simulation within Train.
- Similar chemistry can occur across published partitions; this does not establish scaffold extrapolation. Only exact graph-identity overlap is removed.
- Hidden-label access is an in-process software boundary tested for intended use, not a security sandbox.
- One target and two selection policies cannot establish general discovery superiority. No neural network was fine-tuned in this milestone.
- Next: preserve this baseline, compare frozen and fine-tuned CheMeleon under the same protocol, and use separate development tasks before any tuning. Once inspected, these test results must not be treated as a fresh blind evaluation for subsequent model selection.
"""
    (out / "REPORT.md").write_text(text)
    return summary
