#!/usr/bin/env python3
"""Independent binding and acceptance validator for the V9 runtime package."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from f017_event04_tensor_plan_v9 import validate_plan


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event04-runtime-authority-manifest-v9.json"


def _verify_binding(binding: object) -> Path:
    if type(binding) is not dict or set(binding) != {"path", "sha256"}: raise ValueError("authority binding census")
    path = ROOT / binding["path"]
    if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != binding["sha256"]: raise ValueError("authority binding mismatch")
    return path


def _load_binding(binding: object) -> dict:
    return json.loads(_verify_binding(binding).read_bytes())


def validate() -> dict:
    manifest = json.loads(MANIFEST.read_bytes())
    for key in ("active_generation", "scientific_access", "runtime_hardening", "production_tensor_plan", "inert_authorization", "operator_go_template"):
        _load_binding(manifest[key])
    for binding in manifest["implementation"].values(): _verify_binding(binding)
    scientific = _load_binding(manifest["scientific_access"]); runtime = _load_binding(manifest["runtime_hardening"])
    if scientific["runtime_hardening"] != manifest["runtime_hardening"] or scientific["implementation"] != manifest["implementation"]:
        raise ValueError("scientific access internal binding")
    if set(runtime["did_closure"]) != {f"DID-{index:02d}" for index in range(1, 13)} or any(value != "MECHANICALLY_GATED" for value in runtime["did_closure"].values()):
        raise ValueError("DID closure census")
    validate_plan(_load_binding(manifest["production_tensor_plan"]))
    for path, expected in (("scripts/research/f017_corrected_oracle_primary_numerics_v2.py", "657cdff9ee833cb2b3a0b3fa71b6cbc3dd1e0fbc71b74b9bbff9dca6b5b76767"),
                           ("scripts/research/f017_corrected_oracle_secondary_numerics_v2.py", "e3670b22ac71bad7523efe1e47b00f2345d1f103d2af8f7592e2f3f8c793a791"),
                           ("scripts/research/f017_oracle_primary_decoders.py", "60a4b4e7d973edc41383e20d6d3413d4f658bf4a34dc9132529a6c702b44e11e")):
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected: raise ValueError("numerical authority drift")
    check = subprocess.run([sys.executable, str(ROOT / "scripts/research/generate_f017_event04_runtime_hardening_v9.py"), "--check"], cwd=ROOT, capture_output=True, text=True)
    if check.returncode != 0: raise ValueError("generator drift")
    return {"schema": "pulsarmlx.f017.event04-runtime-hardening-validation/9.0.0", "result": "PASS", "did_closures": 12,
            "graph_tensors": 1410, "non_access_tensors": 399, "active_generation": "V9", "original_checkpoint_access": 0}


if __name__ == "__main__": print(json.dumps(validate(), sort_keys=True, separators=(",", ":")))
