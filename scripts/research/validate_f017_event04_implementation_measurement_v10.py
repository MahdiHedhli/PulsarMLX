#!/usr/bin/env python3
"""Validate V10 implementation bindings against exact Git object bytes."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event04-runtime-authority-manifest-v10.json"
ENTRY_PATHS = {
    "scripts/research/validate_f017_corrected_oracle_access_v10.py",
    "scripts/research/execute_f017_corrected_oracle_event_v10.py",
    "scripts/research/f017_corrected_oracle_primary_v10.py",
    "scripts/research/f017_corrected_oracle_secondary_v10.py",
}


def _runtime_closure() -> set[str]:
    research = ROOT / "scripts/research"; pending = list(ENTRY_PATHS); closure: set[str] = set()
    while pending:
        relative = pending.pop()
        if relative in closure: continue
        try: tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"), filename=relative)
        except (OSError, SyntaxError, UnicodeError) as exc: raise ValueError("runtime closure parse") from exc
        closure.add(relative)
        for node in ast.walk(tree):
            modules = ([item.name.split(".", 1)[0] for item in node.names] if isinstance(node, ast.Import)
                       else [node.module.split(".", 1)[0]] if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module
                       else [])
            for module in modules:
                dependency = research / f"{module}.py"
                if dependency.is_file(): pending.append(f"scripts/research/{module}.py")
    return closure


def validate(head: str) -> dict:
    try:
        resolved = subprocess.check_output(["git", "rev-parse", head], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        tree = subprocess.check_output(["git", "rev-parse", f"{resolved}^{{tree}}"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError) as exc: raise ValueError("measurement Git authority") from exc
    manifest = json.loads(MANIFEST.read_bytes()); checked = []
    bound_paths = {binding.get("path") for binding in manifest["implementation"].values() if type(binding) is dict}
    closure = _runtime_closure()
    if not closure.issubset(bound_paths): raise ValueError("runtime closure not fully measured")
    for name, binding in sorted(manifest["implementation"].items()):
        if type(binding) is not dict or set(binding) != {"path", "sha256"}: raise ValueError("measurement binding census")
        try: raw = subprocess.check_output(["git", "show", f"{resolved}:{binding['path']}"], cwd=ROOT)
        except subprocess.CalledProcessError as exc: raise ValueError("measured Git path absent") from exc
        if hashlib.sha256(raw).hexdigest() != binding["sha256"]: raise ValueError(f"measured Git SHA mismatch: {name}")
        if (ROOT / binding["path"]).read_bytes() != raw: raise ValueError(f"working tree differs from measured Git bytes: {name}")
        checked.append(name)
    return {"schema": "pulsarmlx.f017.event04-implementation-measurement-validation/10.0.0", "result": "PASS",
            "implementation_head": resolved, "implementation_tree": tree, "binding_count": len(checked),
            "runtime_import_closure_count": len(closure),
            "working_tree_byte_identity": True, "original_checkpoint_access": 0}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--head", required=True); args = parser.parse_args()
    print(json.dumps(validate(args.head), sort_keys=True, separators=(",", ":"))); return 0


if __name__ == "__main__": raise SystemExit(main())
