#!/usr/bin/env python3
"""Validate V9 implementation bindings against exact Git object bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event04-runtime-authority-manifest-v9.json"


def validate(head: str) -> dict:
    resolved = subprocess.check_output(["git", "rev-parse", head], cwd=ROOT, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", f"{resolved}^{{tree}}"], cwd=ROOT, text=True).strip()
    manifest = json.loads(MANIFEST.read_bytes()); checked = []
    for name, binding in sorted(manifest["implementation"].items()):
        if type(binding) is not dict or set(binding) != {"path", "sha256"}: raise ValueError("measurement binding census")
        try: raw = subprocess.check_output(["git", "show", f"{resolved}:{binding['path']}"], cwd=ROOT)
        except subprocess.CalledProcessError as exc: raise ValueError("measured Git path absent") from exc
        if hashlib.sha256(raw).hexdigest() != binding["sha256"]: raise ValueError(f"measured Git SHA mismatch: {name}")
        if (ROOT / binding["path"]).read_bytes() != raw: raise ValueError(f"working tree differs from measured Git bytes: {name}")
        checked.append(name)
    return {"schema": "pulsarmlx.f017.event04-implementation-measurement-validation/9.0.0", "result": "PASS",
            "implementation_head": resolved, "implementation_tree": tree, "binding_count": len(checked),
            "working_tree_byte_identity": True, "original_checkpoint_access": 0}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--head", required=True); args = parser.parse_args()
    print(json.dumps(validate(args.head), sort_keys=True, separators=(",", ":"))); return 0


if __name__ == "__main__": raise SystemExit(main())
