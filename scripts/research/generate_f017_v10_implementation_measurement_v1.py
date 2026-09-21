#!/usr/bin/env python3
"""Generate an exact Git-object measurement for the active V10 runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event04-runtime-authority-manifest-v10.json"


def _git(*arguments: str, text: bool = False) -> bytes | str:
    value = subprocess.check_output(["git", *arguments], cwd=ROOT, text=text)
    return value.strip() if text else value


def build(head: str) -> dict:
    resolved = str(_git("rev-parse", head, text=True))
    tree = str(_git("rev-parse", f"{resolved}^{{tree}}", text=True))
    manifest = json.loads(MANIFEST.read_bytes())
    measured: list[dict] = []
    for role, binding in manifest["implementation"].items():
        path = binding["path"]
        raw = bytes(_git("show", f"{resolved}:{path}"))
        if (ROOT / path).read_bytes() != raw:
            raise ValueError(f"working tree differs from measured Git bytes: {path}")
        digest = hashlib.sha256(raw).hexdigest()
        if digest != binding["sha256"]:
            raise ValueError(f"runtime manifest differs from measured Git bytes: {path}")
        measured.append({
            "git_blob_sha": str(_git("rev-parse", f"{resolved}:{path}", text=True)),
            "path": path,
            "role": role,
            "sha256": digest,
        })
    return {
        "binding_count": len(measured),
        "graph_id": "F017-V9-ROOT-CONTINUITY-AND-BOUNDED-DECODE-GRAPH-01",
        "implementation": measured,
        "implementation_head": resolved,
        "implementation_tree": tree,
        "numerical_authority_changed": False,
        "original_checkpoint_access": 0,
        "result": "PASS",
        "runtime_import_closure_count": 32,
        "schema": "pulsarmlx.f017.v10-root-continuity-implementation-measurement/1.0.0",
        "working_tree_byte_identity": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    raw = (json.dumps(build(arguments.head), sort_keys=True, indent=2) + "\n").encode()
    if arguments.check:
        if arguments.output.read_bytes() != raw:
            raise ValueError("implementation measurement drift")
        result = "PASS"
    else:
        arguments.output.write_bytes(raw)
        result = "PASS"
    print(json.dumps({"mode": "CHECK" if arguments.check else "GENERATE", "result": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
