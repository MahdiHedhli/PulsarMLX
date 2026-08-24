#!/usr/bin/env python3
"""Generate the Event-04 reconciliation implementation measurement from Git."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from f017_corrected_oracle_authorization_v6 import ROOT, canonical_bytes


PARENT = ROOT / "docs/architecture/reviews/evidence/f017-corrected-oracle-lifecycle-v6-implementation-measurement-v3.json"
ADDITIONAL_PATHS = {
    "scripts/research/validate_f017_event04_authority_reconciliation_v1.py",
    "scripts/research/rehearse_f017_event04_authority_reconciliation_v1.py",
    "scripts/research/generate_f017_event04_reconciliation_measurement_v4.py",
}


def git_bytes(*arguments: str) -> bytes:
    return subprocess.check_output(["git", *arguments], cwd=ROOT)


def generate(head: str) -> dict:
    head = git_bytes("rev-parse", head).decode().strip()
    tree = git_bytes("rev-parse", f"{head}^{{tree}}").decode().strip()
    parent = json.loads(PARENT.read_text())
    paths = sorted({entry["path"] for entry in parent["entries"]} | ADDITIONAL_PATHS)
    entries = []
    for path in paths:
        data = git_bytes("show", f"{head}:{path}")
        blob = git_bytes("rev-parse", f"{head}:{path}").decode().strip()
        entries.append({
            "git_blob_sha": blob,
            "path": path,
            "semantic_role": "LOAD_BEARING_ACTIVE_OR_RETIREMENT_AUTHORITY",
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    return {
        "branch": "feat/017-rust-native-inference-runtime",
        "entries": entries,
        "entry_count": len(entries),
        "evidence_descendant_may_not_change_measured_bytes": True,
        "git_tree_sha": tree,
        "implementation_head": head,
        "parent_measurement_manifest_path": str(PARENT.relative_to(ROOT)),
        "parent_measurement_manifest_sha256": hashlib.sha256(PARENT.read_bytes()).hexdigest(),
        "result": "PASS",
        "schema": "pulsarmlx.f017.corrected-oracle-implementation-measurement/4.0.0",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.output.write_bytes(canonical_bytes(generate(arguments.head)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
