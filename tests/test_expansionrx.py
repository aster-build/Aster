import numpy as np
import pandas as pd
import pytest

from aster import expansionrx


def frame(rows: list[dict]) -> pd.DataFrame:
    """A published-shape partition: every endpoint column present, blanks allowed."""
    base = {endpoint["column"]: np.nan for endpoint in expansionrx.ENDPOINTS}
    return pd.DataFrame([{**base, **row} for row in rows])


EARLIER = frame([
    {"Molecule Name": "E-0001000", "SMILES": "CCO", "LogD": 1.0, "KSOL": 100.0},
    {"Molecule Name": "E-0002000", "SMILES": "CCN", "LogD": 2.0, "KSOL": 10.0},
    {"Molecule Name": "E-0003000", "SMILES": "CCCl", "LogD": -0.5, "HLM CLint": 50.0},
])
LATER = frame([
    {"Molecule Name": "E-0021000", "SMILES": "CCCC", "LogD": 3.0, "KSOL": 1.0},
    {"Molecule Name": "E-0022000", "SMILES": "CCCCC", "LogD": 0.0, "HLM CLint": 10.0},
])


def test_registration_number_is_parsed_and_validated():
    assert expansionrx.registration("E-0020101") == 20101
    assert expansionrx.registration("E-0001321") == 1321
    for bad in ["E20101", "X-0020101", "E-0020101a", ""]:
        with pytest.raises(ValueError, match="Unexpected compound identifier"):
            expansionrx.registration(bad)


def test_curation_keeps_era_registration_and_transforms_values():
    clean, qc, summary = expansionrx.curate(EARLIER, LATER)
    assert set(clean.era) == {"earlier", "later"}
    first_later = clean.loc[clean.era.eq("later"), "registration"].min()
    assert clean.loc[clean.era.eq("earlier"), "registration"].max() < first_later
    assert first_later == 21000
    solubility = clean[clean.endpoint.eq("ksol")].set_index("compound_id").value
    # 100 uM becomes 2.0 on the log10 scale; LogD is left alone.
    assert solubility["E-0001000"] == pytest.approx(2.0)
    assert clean[clean.endpoint.eq("logd")].set_index("compound_id").value["E-0003000"] == -0.5
    assert summary["measurements_by_endpoint"]["logd"] == {"earlier": 3, "later": 2}
    assert summary["registration_range"]["later"] == [21000, 22000]
    assert summary["time_basis"].startswith("Ordinal registration number")


def test_log_scaled_endpoints_exclude_non_positive_values_rather_than_clip():
    earlier = frame([
        {"Molecule Name": "E-0001000", "SMILES": "CCO", "KSOL": 100.0, "HLM CLint": 0.0},
        {"Molecule Name": "E-0002000", "SMILES": "CCN", "KSOL": 10.0, "LogD": 0.0},
        {"Molecule Name": "E-0003000", "SMILES": "CCCl", "KSOL": 1.0},
    ])
    clean, qc, summary = expansionrx.curate(earlier, LATER)
    assert "E-0001000" not in set(clean.loc[clean.endpoint.eq("hlm_clint"), "compound_id"])
    assert summary["measurement_status_counts"]["non_positive_for_log"] == 1
    # A zero on an untransformed endpoint is a legitimate measurement and is kept.
    assert clean[clean.endpoint.eq("logd")].set_index("compound_id").value["E-0002000"] == 0.0


def test_duplicate_structures_are_excluded_from_every_endpoint():
    earlier = frame([
        {"Molecule Name": "E-0001000", "SMILES": "CCO", "LogD": 1.0, "KSOL": 100.0},
        {"Molecule Name": "E-0002000", "SMILES": "OCC", "LogD": 2.0, "KSOL": 10.0},
        {"Molecule Name": "E-0003000", "SMILES": "CCCl", "LogD": 0.5, "KSOL": 1.0},
    ])
    clean, qc, summary = expansionrx.curate(earlier, LATER)
    assert set(clean.loc[clean.era.eq("earlier"), "compound_id"]) == {"E-0003000"}
    assert summary["compound_status_counts"]["duplicate_identity"] == 2
    assert summary["measurement_status_counts"]["duplicate_identity"] == 4


def test_invalid_and_mixture_structures_are_rejected_not_repaired():
    earlier = frame([
        {"Molecule Name": "E-0001000", "SMILES": "CCO.[Na+]", "LogD": 1.0},
        {"Molecule Name": "E-0002000", "SMILES": "not-a-molecule", "LogD": 2.0},
        {"Molecule Name": "E-0003000", "SMILES": "CCCl", "LogD": 0.5},
    ])
    clean, qc, summary = expansionrx.curate(earlier, LATER)
    assert set(clean.loc[clean.era.eq("earlier"), "compound_id"]) == {"E-0003000"}
    assert summary["compound_status_counts"]["multiple_fragments"] == 1
    assert summary["compound_status_counts"]["invalid_structure"] == 1


def test_curation_refuses_a_partition_that_is_not_one_cut_in_registration_order():
    overlapping = frame([{"Molecule Name": "E-0025000", "SMILES": "CCCl", "LogD": 1.0}])
    with pytest.raises(ValueError, match="not a single cut"):
        expansionrx.curate(pd.concat([EARLIER, overlapping]), LATER)


def test_curation_refuses_repeated_or_missing_identifiers():
    with pytest.raises(ValueError, match="must be present and unique"):
        expansionrx.curate(pd.concat([EARLIER, EARLIER]), LATER)
    with pytest.raises(ValueError, match="appears in both published partitions"):
        expansionrx.curate(EARLIER, pd.concat([LATER, EARLIER.head(1)]))


def test_missing_endpoint_columns_are_an_error_not_a_silent_skip():
    with pytest.raises(ValueError, match="Missing required columns"):
        expansionrx.curate(EARLIER.drop(columns=["KSOL"]), LATER)


def test_censoring_audit_counts_modifiers_without_fitting_on_them():
    raw = pd.DataFrame({
        "Molecule Name": ["E-0001000", "E-0002000", "E-0003000"],
        "SMILES": ["CCO", "CCN", "CCCl"],
        **{endpoint["column"]: pd.Series([pd.NA] * 3, dtype="string")
           for endpoint in expansionrx.ENDPOINTS},
    })
    raw.loc[0, "HLM CLint"] = "<5"
    raw.loc[1, "HLM CLint"] = ">250"
    raw.loc[2, "KSOL"] = "100"
    audit = expansionrx.censoring_audit(raw)
    assert audit["modified_measurements_by_endpoint"]["hlm_clint"] == 2
    assert audit["modified_measurements_by_endpoint"]["ksol"] == 0
    assert audit["compounds_with_any_modifier"] == 2


def test_endpoint_declarations_are_complete_and_unique():
    ids = [endpoint["id"] for endpoint in expansionrx.ENDPOINTS]
    assert len(set(ids)) == len(ids) == 9
    for endpoint in expansionrx.ENDPOINTS:
        assert endpoint["transform"] in {"identity", "log10"}
        assert endpoint["description"].endswith(".")
        assert set(endpoint) == {"id", "column", "units", "transform", "label", "description"}
