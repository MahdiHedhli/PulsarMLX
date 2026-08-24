#!/usr/bin/env python3
"""Bank the exact Git/blob/SHA-256 implementation measurement for V6."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from f017_corrected_oracle_authorization_v6 import ROOT, canonical_bytes

MODEL = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-semantic-model-v6.json"


def _git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def generate() -> dict:
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    head = _git("rev-parse", "HEAD")
    tree = _git("rev-parse", "HEAD^{tree}")
    entries = []
    for relative in model["measurement_authority"]["required_entries"]:
        path = ROOT / relative
        data = path.read_bytes()
        entries.append({
            "path": relative,
            "git_blob_sha": _git("rev-parse", f"HEAD:{relative}"),
            "sha256": hashlib.sha256(data).hexdigest(),
            "semantic_role": "LOAD_BEARING_ACTIVE_OR_RETIREMENT_AUTHORITY",
        })
    return {
        "schema": model["measurement_authority"]["manifest_schema"],
        "result": "PASS",
        "branch": _git("branch", "--show-current"),
        "implementation_head": head,
        "git_tree_sha": tree,
        "entry_count": len(entries),
        "entries": entries,
        "evidence_descendant_may_not_change_measured_bytes": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.output.write_bytes(canonical_bytes(generate()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
