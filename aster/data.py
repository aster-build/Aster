"""Pinned source acquisition, conservative curation, and molecular features."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd
from rdkit import Chem, rdBase
from rdkit.Chem import rdFingerprintGenerator

SOURCE = "https://zenodo.org/records/15582067/files/Potency.csv"
RECORD = "https://zenodo.org/api/records/15582067"
EXPECTED_MD5 = "197026f128c46b7c7de78f7e899723fe"
TARGET = "pIC50 (SARS-CoV-2 Mpro)"
REQUIRED = {"CXSMILES", "Molecule Name", "Set", TARGET}


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def digest(path: Path, algorithm: str = "sha256") -> str:
    return hashlib.new(algorithm, path.read_bytes()).hexdigest()


def fetch(directory: Path) -> Path:
    """Download only the small potency CSV; never silently use a different release."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "Potency.csv"
    if not path.exists():
        with urlopen(SOURCE, timeout=60) as response:
            payload = response.read()
        if hashlib.md5(payload).hexdigest() != EXPECTED_MD5:
            raise ValueError("Source checksum mismatch; review the release before using it.")
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(payload)
        temporary.replace(path)
    if digest(path, "md5") != EXPECTED_MD5:
        raise ValueError("Cached Potency.csv differs from the pinned release.")
    metadata = directory / "source-record.json"
    if not metadata.exists():
        with urlopen(RECORD, timeout=60) as response:
            metadata.write_bytes(response.read())
    record = json.loads(metadata.read_text())
    if str(record["id"]) != "15582067":
        raise ValueError("Unexpected source metadata record.")
    return path


def canonicalize(cxsmiles: str) -> tuple[str, str]:
    """Keep chemistry intact; reject mixtures rather than silently strip fragments.

    CXSMILES retains enhanced stereo annotations. The grouping key ignores CX
    annotations but retains ordinary stereochemistry, conservatively grouping
    alternative annotations of the same encoded molecular graph.
    """
    mol = Chem.MolFromSmiles(cxsmiles)
    if mol is None or mol.GetNumAtoms() == 0:
        raise ValueError("invalid_structure")
    if len(Chem.GetMolFrags(mol)) != 1:
        raise ValueError("multiple_fragments")
    return Chem.MolToCXSmiles(mol), Chem.MolToSmiles(mol, isomericSmiles=True)


def curate(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    missing = REQUIRED - set(raw.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if not raw["Set"].isin(["Train", "Test"]).all():
        raise ValueError("Unknown or missing published partition.")
    if raw["Molecule Name"].isna().any() or raw["Molecule Name"].duplicated().any():
        raise ValueError("Molecule identifiers must be present and unique.")

    records = []
    for index, row in raw.reset_index(drop=True).iterrows():
        item = {"source_row": index + 2, "compound_id": row["Molecule Name"],
                "split": row["Set"], "raw_cxsmiles": row["CXSMILES"],
                "raw_value": row[TARGET], "canonical_cxsmiles": None,
                "identity_key": None, "pic50": None, "status": "eligible"}
        try:
            item["canonical_cxsmiles"], item["identity_key"] = canonicalize(str(row["CXSMILES"]))
        except ValueError as error:
            item["status"] = str(error)
        value = pd.to_numeric(row[TARGET], errors="coerce")
        if item["status"] == "eligible":
            if pd.isna(row[TARGET]):
                item["status"] = "missing_endpoint"
            elif not np.isfinite(value):
                item["status"] = "non_numeric_or_nonfinite_endpoint"
            else:
                item["pic50"] = float(value)
        records.append(item)
    qc = pd.DataFrame(records)
    # Exclude all rows with duplicated identities, including across published sets.
    # This does not average potentially incompatible measurements or move test rows.
    duplicate = qc.identity_key.notna() & qc.identity_key.duplicated(keep=False)
    qc.loc[duplicate & qc.status.eq("eligible"), "status"] = "duplicate_identity"
    clean = qc.loc[qc.status.eq("eligible")].copy().sort_values("compound_id").reset_index(drop=True)
    if not {"Train", "Test"}.issubset(set(clean.split)):
        raise ValueError("Both published sets must have eligible measurements.")
    summary = {
        "raw_rows": len(raw), "eligible_rows": len(clean),
        "row_status_counts": {k: int(v) for k, v in qc.status.value_counts().items()},
        "eligible_by_published_split": {k: int(v) for k, v in clean.split.value_counts().items()},
        "duplicate_identity_groups": int(qc.loc[duplicate, "identity_key"].nunique()),
        "rdkit_version": rdBase.rdkitVersion,
        "endpoint": TARGET,
        "policy": "Parse/sanitize CXSMILES; preserve stereochemistry and charge; reject mixtures; exclude all duplicate identity rows; no salt stripping or tautomer merging.",
        "censoring_limitation": "Source supplies numeric pIC50, with no censoring/replicate/QC columns. Values are modeled as published; numeric values are not proof of uncensored measurements.",
    }
    return clean, qc, summary


def fingerprints(structures: list[str], radius: int = 2, bits: int = 2048) -> np.ndarray:
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=radius, fpSize=bits, includeChirality=True)
    mols = [Chem.MolFromSmiles(s) for s in structures]
    if any(m is None for m in mols):
        raise ValueError("Invalid structure passed to fingerprint generator.")
    return np.asarray([generator.GetFingerprintAsNumPy(m) for m in mols], dtype=np.uint8)


def provenance(path: Path) -> dict:
    record = json.loads((path.parent / "source-record.json").read_text())
    return {
        "source_url": SOURCE, "record_url": "https://zenodo.org/records/15582067",
        "doi": "10.5281/zenodo.15582067", "version": "v2",
        "license": record["metadata"].get("license"),
        "title": record["metadata"].get("title"),
        "creators": record["metadata"].get("creators"),
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "sha256": digest(path), "md5": digest(path, "md5"),
        "metadata_sha256": digest(path.parent / "source-record.json"),
    }
