"""Pinned loader for the OpenADMET-ExpansionRx release, keeping its time order.

This is the first Aster source whose rows can be placed in time relative to one
another. The release carries no measurement dates, so the order comes from two
things the publishers did supply:

1. The partition they published. 5,326 compounds were given to challenge
   entrants as training data and 2,282 later compounds were held back as the
   blinded test set, described by the organisers as predicting "late-stage
   molecules based on earlier-stage data from the same campaigns".
2. The compound registration number embedded in every identifier (``E-0020101``).
   These are assigned in registration order, and the published partition falls
   exactly at one cut in them: every training compound is at or below 20100 and
   every test compound is at or above 20101. That the publishers' own split is a
   single cut in this number is the evidence that it tracks the campaign timeline.

So ``registration`` is an ordinal proxy for time, not a date, and it orders when
a compound entered the campaign rather than when it was assayed. Both are
recorded as declared limitations rather than presented as dates, and no code in
this module converts either one into a timestamp.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd
from rdkit import rdBase

from .data import canonicalize, digest, write_json

DATASET = "openadmet/openadmet-expansionrx-challenge-data"
REVISION = "6b898ccc43d10d25b230fb09e22a6e30c30022b5"
BASE = f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}"
RECORD = f"https://huggingface.co/api/datasets/{DATASET}/revision/{REVISION}"
LICENSE = "CC-BY-4.0"

# The "ML-ready" files hold only in-range measurements. The raw file additionally
# carries the out-of-range modifiers (">", "<") and a tenth endpoint that was not
# part of the challenge; it is fetched for provenance and for the censoring audit,
# and is not used for fitting until censored values are stored faithfully.
FILES = {
    "earlier": ("expansion_data_train.csv",
                "c5214ad8c8a4d7d4d09082fcce24fe16c97a980a1e0873b91b8c8e474b79f6e4"),
    "later": ("expansion_data_test.csv",
              "e21c0ef19795317216287e924e00ca3ef9388b7032a7fa4c7f27e2580372c85e"),
    "raw": ("expansion_data_raw.csv",
            "f674ec74cca1146bc386f832a32d4b8d921d3c312f92cb436cc005901c724a3c"),
}

PUBLISHED_CUTOFF = 20100
IDENTIFIER_PATTERN = r"E-\d+"

# One entry per endpoint, naming the published column, the units it arrives in,
# and the transform applied before fitting. Reasons for the transforms are in
# docs/TEMPORAL_PROTOCOL.md; in short, every endpoint except LogD is a
# concentration, a rate or a percentage bounded below by zero and spanning
# several orders of magnitude, and is fitted on a base-10 logarithm so that a
# fixed error means a fixed ratio. LogD is already a logarithm.
ENDPOINTS: tuple[dict, ...] = (
    {"id": "logd", "column": "LogD", "units": "log ratio",
     "transform": "identity", "label": "LogD",
     "description": "Lipophilicity: the log ratio of how a compound distributes between octanol and water."},
    {"id": "ksol", "column": "KSOL", "units": "uM",
     "transform": "log10", "label": "Kinetic solubility",
     "description": "How much compound stays dissolved in aqueous buffer, in micromoles per litre."},
    {"id": "hlm_clint", "column": "HLM CLint", "units": "mL/min/kg",
     "transform": "log10", "label": "Human liver microsomal clearance",
     "description": "How fast human liver enzyme preparations destroy the compound."},
    {"id": "mlm_clint", "column": "MLM CLint", "units": "mL/min/kg",
     "transform": "log10", "label": "Mouse liver microsomal clearance",
     "description": "The same measurement in mouse liver preparations."},
    {"id": "caco2_papp", "column": "Caco-2 Permeability Papp A>B", "units": "1e-6 cm/s",
     "transform": "log10", "label": "Caco-2 permeability",
     "description": "How quickly the compound crosses a layer of gut-lining cells."},
    {"id": "caco2_efflux", "column": "Caco-2 Permeability Efflux", "units": "ratio",
     "transform": "log10", "label": "Caco-2 efflux ratio",
     "description": "How strongly the gut-lining cells pump the compound back out."},
    {"id": "mppb", "column": "MPPB", "units": "% unbound",
     "transform": "log10", "label": "Mouse plasma protein binding",
     "description": "The percentage of compound left free in plasma rather than stuck to its proteins."},
    {"id": "mbpb", "column": "MBPB", "units": "% unbound",
     "transform": "log10", "label": "Mouse brain protein binding",
     "description": "The same free percentage measured in brain tissue."},
    {"id": "mgmb", "column": "MGMB", "units": "% unbound",
     "transform": "log10", "label": "Mouse muscle binding",
     "description": "The same free percentage measured in calf muscle."},
)
BY_ID = {endpoint["id"]: endpoint for endpoint in ENDPOINTS}
REQUIRED = {"Molecule Name", "SMILES"} | {endpoint["column"] for endpoint in ENDPOINTS}


def fetch(directory: Path) -> dict[str, Path]:
    """Download the pinned revision's files, refusing anything that differs."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = {}
    for role, (name, expected) in FILES.items():
        path = directory / name
        if not path.exists():
            with urlopen(f"{BASE}/{name}", timeout=120) as response:
                payload = response.read()
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(payload)
            temporary.replace(path)
        if digest(path) != expected:
            raise ValueError(f"{name} differs from the pinned revision {REVISION[:12]}.")
        paths[role] = path
    metadata = directory / "dataset-record.json"
    if not metadata.exists():
        with urlopen(RECORD, timeout=120) as response:
            metadata.write_bytes(response.read())
    record = json.loads(metadata.read_text())
    if record.get("sha") != REVISION:
        raise ValueError("Unexpected dataset metadata revision.")
    paths["record"] = metadata
    return paths


def registration(identifier: str) -> int:
    """The registration number inside a compound identifier such as E-0020101."""
    text = str(identifier)
    if not pd.Series([text]).str.fullmatch(IDENTIFIER_PATTERN).iloc[0]:
        raise ValueError(f"Unexpected compound identifier: {identifier!r}")
    return int(text.split("-", 1)[1])


def transform_value(value: float, how: str) -> float:
    if how == "identity":
        return float(value)
    if how == "log10":
        if value <= 0:
            raise ValueError("non_positive_for_log")
        return float(np.log10(value))
    raise ValueError(f"Unknown transform {how}")


def curate(earlier: pd.DataFrame, later: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """One row per measurement, carrying its era and registration number.

    Every published row becomes up to nine measurement rows, one per endpoint
    that compound has a value for. Structures are parsed and canonicalised with
    the same conservative rules as the Zenodo source: stereochemistry and charge
    preserved, mixtures rejected, duplicate structures excluded wholesale rather
    than averaged. A non-positive value on a log-scaled endpoint is excluded as
    below the assay's range rather than clipped to a floor, because the release's
    raw file shows those measurements carry "<" modifiers that the ML-ready file
    drops; recording them faithfully is separate, later queue work.
    """
    compounds, measurements = [], []
    for era, frame in (("earlier", earlier), ("later", later)):
        missing = REQUIRED - set(frame.columns)
        if missing:
            raise ValueError(f"Missing required columns in {era} partition: {sorted(missing)}")
        if frame["Molecule Name"].isna().any() or frame["Molecule Name"].duplicated().any():
            raise ValueError(f"Compound identifiers in the {era} partition must be present and unique.")
        for index, row in frame.reset_index(drop=True).iterrows():
            item = {"compound_id": row["Molecule Name"], "era": era,
                    "source_row": index + 2, "raw_smiles": row["SMILES"],
                    "registration": registration(row["Molecule Name"]),
                    "smiles": None, "identity": None, "status": "eligible"}
            try:
                item["smiles"], item["identity"] = canonicalize(str(row["SMILES"]))
            except ValueError as error:
                item["status"] = str(error)
            compounds.append(item)
            for endpoint in ENDPOINTS:
                published = row[endpoint["column"]]
                if pd.isna(published):
                    continue
                value = pd.to_numeric(published, errors="coerce")
                record = {"compound_id": item["compound_id"], "endpoint": endpoint["id"],
                          "era": era, "registration": item["registration"],
                          "raw_value": published, "value": None, "status": item["status"]}
                if record["status"] == "eligible":
                    if pd.isna(value) or not np.isfinite(value):
                        record["status"] = "non_numeric_or_nonfinite"
                    else:
                        try:
                            record["value"] = transform_value(float(value), endpoint["transform"])
                        except ValueError as error:
                            record["status"] = str(error)
                measurements.append(record)

    structures = pd.DataFrame(compounds)
    if structures.compound_id.duplicated().any():
        raise ValueError("A compound identifier appears in both published partitions.")
    if not (structures.loc[structures.era.eq("earlier"), "registration"].max() < PUBLISHED_CUTOFF + 1
            <= structures.loc[structures.era.eq("later"), "registration"].min()):
        raise ValueError("The published partition is not a single cut in registration order; "
                         "the ordering assumption documented in this module does not hold.")
    duplicate = structures.identity.notna() & structures.identity.duplicated(keep=False)
    structures.loc[duplicate & structures.status.eq("eligible"), "status"] = "duplicate_identity"
    excluded = set(structures.loc[~structures.status.eq("eligible"), "compound_id"])

    qc = pd.DataFrame(measurements)
    qc.loc[qc.compound_id.isin(excluded) & qc.status.eq("eligible"), "status"] = "duplicate_identity"
    structure_of = structures.set_index("compound_id")
    qc["smiles"] = structure_of.smiles.reindex(qc.compound_id).to_numpy()
    clean = qc.loc[qc.status.eq("eligible")].copy()
    clean = clean.sort_values(["endpoint", "registration", "compound_id"]).reset_index(drop=True)
    clean["value"] = clean.value.astype(float)

    counts = clean.groupby(["endpoint", "era"]).size().unstack(fill_value=0)
    for era in ("earlier", "later"):
        if era not in counts.columns:
            raise ValueError(f"No eligible {era} measurements survived curation.")
    summary = {
        "published_rows": {"earlier": len(earlier), "later": len(later)},
        "eligible_compounds": int(structures.status.eq("eligible").sum()),
        "compound_status_counts": {k: int(v) for k, v in structures.status.value_counts().items()},
        "eligible_measurements": len(clean),
        "measurement_status_counts": {k: int(v) for k, v in qc.status.value_counts().items()},
        "measurements_by_endpoint": {
            endpoint: {"earlier": int(counts.loc[endpoint, "earlier"]),
                       "later": int(counts.loc[endpoint, "later"])}
            for endpoint in counts.index},
        "registration_range": {
            era: [int(structures.loc[structures.era.eq(era), "registration"].min()),
                  int(structures.loc[structures.era.eq(era), "registration"].max())]
            for era in ("earlier", "later")},
        "published_cutoff": PUBLISHED_CUTOFF,
        "rdkit_version": rdBase.rdkitVersion,
        "endpoints": [{k: endpoint[k] for k in ("id", "column", "units", "transform")}
                      for endpoint in ENDPOINTS],
        "policy": "One row per measurement; parse and canonicalise SMILES preserving "
                  "stereochemistry and charge; reject mixtures; exclude duplicate structures "
                  "wholesale; exclude non-positive values on log-scaled endpoints as below "
                  "assay range; no salt stripping, tautomer merging or value imputation.",
        "time_basis": "Ordinal registration number parsed from the compound identifier, "
                      "validated to agree with the publishers' own earlier/later partition. "
                      "Not a measurement date.",
        "declared_limitations": [
            "The release carries no measurement dates, so no real cutoff date can be stated.",
            "Registration order records when a compound entered the campaign, not when it "
            "was assayed, so a late-registered compound may carry an early measurement.",
            "The ML-ready files drop out-of-range measurements, so the surviving values are "
            "a biased sample of what was measured: compounds too insoluble or too unstable "
            "to quantify are absent from the endpoint that failed.",
        ],
    }
    return clean, qc, summary


def censoring_audit(raw: pd.DataFrame) -> dict:
    """How much of the release the ML-ready files drop for carrying a modifier."""
    counts, affected = {}, set()
    for endpoint in ENDPOINTS:
        text = raw[endpoint["column"]].astype("string").fillna("")
        modified = text.str.contains(">") | text.str.contains("<")
        counts[endpoint["id"]] = int(modified.sum())
        affected.update(raw.loc[modified, "Molecule Name"])
    return {"raw_rows": len(raw), "modified_measurements_by_endpoint": counts,
            "modified_measurements": int(sum(counts.values())),
            "compounds_with_any_modifier": len(affected),
            "meaning": "A modifier marks a measurement that fell outside the assay's "
                       "quantifiable range, so its true value is bounded, not unknown. The "
                       "ML-ready files drop these rows; storing them faithfully is separate "
                       "queue work and no model here is fitted on them."}


def provenance(paths: dict[str, Path]) -> dict:
    record = json.loads(paths["record"].read_text())
    return {
        "dataset": DATASET, "revision": REVISION,
        "dataset_url": f"https://huggingface.co/datasets/{DATASET}",
        "license": LICENSE,
        "license_declared_by_publisher": record.get("cardData", {}).get("license"),
        "last_modified": record.get("lastModified"),
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": {role: {"name": paths[role].name, "sha256": digest(paths[role])}
                  for role in FILES if role in paths},
        "metadata_sha256": digest(paths["record"]),
        "attribution": "ADMET measurements released by Expansion Therapeutics through the "
                       "OpenADMET-ExpansionRx blind challenge, which closed 19 January 2026.",
    }


def load(directory: Path) -> tuple[pd.DataFrame, dict]:
    """Fetch, curate and return the measurement table with its provenance report."""
    paths = fetch(directory)
    clean, _, summary = curate(pd.read_csv(paths["earlier"]), pd.read_csv(paths["later"]))
    report = {"provenance": provenance(paths), "curation": summary,
              "censoring": censoring_audit(pd.read_csv(paths["raw"], dtype="string"))}
    return clean, report


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Fetch and curate the ExpansionRx release")
    parser.add_argument("--data", type=Path, default=Path("data/expansionrx"))
    parser.add_argument("--output", type=Path, default=Path("output/expansionrx"))
    args = parser.parse_args()
    clean, report = load(args.data)
    args.output.mkdir(parents=True, exist_ok=True)
    clean.to_csv(args.output / "measurements.csv", index=False)
    write_json(args.output / "source_report.json", report)
    print(f"{len(clean)} eligible measurements over {clean.endpoint.nunique()} endpoints", flush=True)
    print(json.dumps(report["curation"]["measurements_by_endpoint"], indent=2), flush=True)


if __name__ == "__main__":
    main()
