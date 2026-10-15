"""Restore missing public DAT source snapshots, rejecting upstream version drift."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT/'configs/literature/dat-v1.json').read_text())
base = ROOT/'data/literature/dat-v1/sources'
base.mkdir(parents=True, exist_ok=True)
for name, spec in config['sources'].items():
    path = base/name
    if path.exists():
        content = path.read_bytes()
    else:
        with urllib.request.urlopen(spec['url'], timeout=60) as response:
            content = response.read(10_000_001)
    if len(content) > 10_000_000 or hashlib.sha256(content).hexdigest() != spec['sha256']:
        raise SystemExit(f'{name}: upstream content differs from the pinned snapshot; do not silently update the corpus.')
    if not path.exists():
        path.write_bytes(content)
    print(name, 'verified')
