import hashlib

import numpy as np
import pandas as pd
import pytest

from aster.benchmark import load_task, split_case
from aster.experiment import Config, LabelOracle, replay
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def fixture_frame():
    return pd.DataFrame({"compound_id": [f"c{i}" for i in range(400)],
                         "scaffold": [f"family{i // 4}" for i in range(400)],
                         "published_split": ["train"] * 300 + ["test"] * 100,
                         "value": np.linspace(4, 9, 400), "cliff": [0, 1] * 200})


def test_scaffold_roles_disjoint_and_outcome_independent():
    frame = fixture_frame()
    split = split_case(frame, "scaffold_transfer", 3, 32)
    changed = frame.copy()
    changed["value"] = changed.value.to_numpy()[::-1]
    changed["cliff"] = 1 - changed.cliff
    assert split == split_case(changed, "scaffold_transfer", 3, 32)
    groups = [set(frame.iloc[split[role]].scaffold) for role in ["initial", "pool", "audit"]]
    assert not groups[0] & groups[1]
    assert not groups[0] & groups[2]
    assert not groups[1] & groups[2]
    assert sum(len(split[r]) for r in split) == len(frame)


def test_published_partition_is_preserved():
    frame = fixture_frame()
    split = split_case(frame, "published", 0, 64)
    assert frame.iloc[split["initial"] + split["pool"]].published_split.eq("train").all()
    assert frame.iloc[split["audit"]].published_split.eq("test").all()


def test_ki_conversion_and_checksum(tmp_path):
    raw = pd.DataFrame({"smiles": ["CCO", "CCN", "CCC"], "exp_mean [nM]": [100, 1000, 10],
                        "y [pEC50/pKi]": [7, 6, 9], "split": ["train", "test", "train"], "cliff_mol": [0, 1, 0]})
    path = tmp_path / "task.csv"
    raw.to_csv(path, index=False)
    task = {"id": "test", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    frame, audit = load_task(path, task)
    assert frame.value.tolist() == [7, 6]
    assert audit["rejected"] == [{"source_row": 4, "reason": "inconsistent_units"}]
    path.write_text("changed")
    with pytest.raises(ValueError, match="checksum"):
        load_task(path, task)


def test_ridge_pipeline_scaling_only_sees_observed_rows():
    x = np.arange(100, dtype=float).reshape(25, 4)
    y = np.linspace(4, 8, 25)
    seen = []
    def factory(seed):
        model = make_pipeline(StandardScaler(), Ridge(alpha=10))
        seen.append(model)
        return model
    result = replay(x, x[:2] * 1000, LabelOracle(y), np.arange(5),
                    Config(initial_size=5, rounds=1, batch_size=2, trees=2), 0, "greedy", factory)
    np.testing.assert_allclose(seen[0]["standardscaler"].mean_, x[:5].mean(axis=0))
    picked = [s["index"] for s in result["selections"]]
    np.testing.assert_allclose(seen[1]["standardscaler"].mean_, x[list(range(5)) + picked].mean(axis=0))
