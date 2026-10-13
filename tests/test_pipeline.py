import hashlib
import json

import pandas as pd

from aster.__main__ import run
from aster.experiment import Config
import aster.data as data


def test_complete_offline_pipeline(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    structures = ["C" * i for i in range(1, 16)]
    raw = pd.DataFrame({"Molecule Name": [f"C{i:02}" for i in range(15)],
                        "CXSMILES": structures, "Set": ["Train"] * 12 + ["Test"] * 3,
                        data.TARGET: [4 + i / 5 for i in range(15)]})
    source = raw_dir / "Potency.csv"
    raw.to_csv(source, index=False)
    monkeypatch.setattr(data, "EXPECTED_MD5", hashlib.md5(source.read_bytes()).hexdigest())
    (raw_dir / "source-record.json").write_text(json.dumps({"id": 15582067, "metadata": {"license": {"id": "cc-by-4.0"}}}))
    config = Config(initial_size=4, batch_size=2, rounds=2, seeds=(0, 1), trees=5)
    out = tmp_path / "results"
    summary = run(raw_dir, out, config)
    assert summary["budget"] == 4
    assert (out / "REPORT.md").exists() and (out / "discovery_curves.png").exists()
    selection = pd.read_csv(out / "selections.csv")
    splits = json.loads((out / "splits.json").read_text())
    for split in splits:
        picked = selection[selection.seed == split["seed"]]
        assert not set(picked.compound_id) & set(split["audit_ids"])
        assert not set(picked.compound_id) & set(split["initial_ids"])
        assert picked.groupby("strategy").compound_id.nunique().eq(4).all()
    assert "observed_pic50" not in pd.read_csv(out / "seed0_greedy_remaining.csv")
    checksums = json.loads((out / "artifact_checksums.json").read_text())
    assert checksums["REPORT.md"] == data.digest(out / "REPORT.md")
