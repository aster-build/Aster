import numpy as np
import pandas as pd
import pytest

from aster.data import TARGET, canonicalize, curate, fingerprints
from aster.experiment import Config, LabelOracle, choose, replay


def test_curation_preserves_published_partition_and_excludes_duplicates():
    raw = pd.DataFrame({
        "Molecule Name": [f"compound-{i}" for i in range(8)],
        "CXSMILES": ["CCO", "OCC", "CCN", "CCCl", "CCC", "CCBr", "C.C", "invalid"],
        "Set": ["Train", "Test", "Train", "Test", "Train", "Train", "Test", "Train"],
        TARGET: [6.0, 7.0, 5.0, 6.5, np.nan, ">6", 5.0, 5.0],
    })
    clean, qc, summary = curate(raw)
    assert clean.compound_id.tolist() == ["compound-2", "compound-3"]
    assert clean.split.tolist() == ["Train", "Test"]
    assert summary["row_status_counts"]["duplicate_identity"] == 2
    assert qc.set_index("compound_id").loc["compound-4", "status"] == "missing_endpoint"
    assert qc.set_index("compound_id").loc["compound-5", "status"] == "non_numeric_or_nonfinite_endpoint"
    assert clean.pic50.tolist() == [5.0, 6.5]  # No accidental double log transform.


def test_stereochemistry_and_invalid_structures():
    a, _ = canonicalize("C[C@H](O)F")
    b, _ = canonicalize("C[C@@H](O)F")
    assert a != b
    features = fingerprints([a, b])
    assert features.shape == (2, 2048)
    assert not np.array_equal(features[0], features[1])
    with pytest.raises(ValueError, match="multiple_fragments"):
        canonicalize("CCO.[Na+]")


def test_oracle_rejects_repeats_duplicates_and_invalid_indices_atomically():
    oracle = LabelOracle(np.array([4., 5., 6.]))
    with pytest.raises(ValueError):
        oracle.reveal(np.array([0, 0]))
    with pytest.raises(ValueError):
        oracle.reveal(np.array([0, 4]))
    assert oracle.reveal(np.array([0])).tolist() == [4.]
    with pytest.raises(ValueError):
        oracle.reveal(np.array([0]))


def test_first_batch_does_not_depend_on_hidden_labels():
    features = np.random.default_rng(7).integers(0, 2, (30, 16), dtype=np.uint8)
    labels = np.linspace(4, 8, 30)
    changed = labels.copy()
    changed[5:] = changed[5:][::-1]
    config = Config(initial_size=5, rounds=2, batch_size=3, seeds=(0,), trees=5)
    first = replay(features, features[:2], LabelOracle(labels), np.arange(5), config, 0, "greedy")
    second = replay(features, features[:2], LabelOracle(changed), np.arange(5), config, 0, "greedy")
    a = [(r["index"], r["predicted_pic50"]) for r in first["selections"] if r["round"] == 1]
    b = [(r["index"], r["predicted_pic50"]) for r in second["selections"] if r["round"] == 1]
    assert a == b
    assert first["history"][-1]["training_size"] == 11
    indices = [r["index"] for r in first["selections"]]
    assert len(set(indices)) == 6
    assert not set(indices) & set(range(5))
    assert first["history"][-1]["additional_hits"] == sum(labels[i] >= 6 for i in indices)


def test_audit_features_do_not_change_policy_and_run_is_deterministic():
    rng = np.random.default_rng(8)
    features = rng.integers(0, 2, (25, 12), dtype=np.uint8)
    labels = rng.uniform(4, 8, 25)
    config = Config(initial_size=5, rounds=2, batch_size=3, seeds=(1,), trees=5)
    outputs = [replay(features, audit, LabelOracle(labels), np.arange(5), config, 1, "greedy")
               for audit in [features[:2], 1 - features[:2]]]
    assert outputs[0]["selections"] == outputs[1]["selections"]


def test_random_selection_independent_of_predictions_and_stable_ties():
    candidates = np.arange(10)
    a = choose("random", candidates, candidates, 3, np.random.default_rng(4))
    b = choose("random", candidates, -candidates, 3, np.random.default_rng(4))
    assert np.array_equal(a, b)
    assert choose("greedy", candidates, np.ones(10), 3, np.random.default_rng(4)).tolist() == [0, 1, 2]


@pytest.mark.parametrize("config", [Config(initial_size=1000), Config(seeds=(1, 1)), Config(batch_size=0), Config(hit_threshold=float("nan"))])
def test_invalid_experiment_configuration(config):
    with pytest.raises(ValueError):
        config.validate(200)
