#!/usr/bin/env python3
"""Read-only provenance audit for the extracted v6 target adapters."""
from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMIT = "84f0d1dc3e60a4151329ed82773880951ee3e618"


def historical(path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{COMMIT}:{path}"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout


def class_methods(text: str, class_name: str) -> set[str]:
    for node in ast.parse(text).body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
    raise ValueError(f"class absent: {class_name}")


def constructor_args(text: str, class_name: str) -> list[str]:
    for node in ast.parse(text).body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            init = next(item for item in node.body if isinstance(item, ast.FunctionDef) and item.name == "__init__")
            return [arg.arg for arg in init.args.args]
    raise ValueError(f"constructor absent: {class_name}")


def main() -> int:
    cases = [
        (
            "scripts/research/f017_corrected_oracle_primary.py", "StreamingCatalogSource", "StreamingMatrix",
            "scripts/research/f017_corrected_oracle_primary_target_source_v6.py", "PrimaryTargetSourceV6", "PrimaryTargetMatrixV6",
        ),
        (
            "scripts/research/f017_corrected_oracle_secondary.py", "CatalogStore", "CatalogMatrix",
            "scripts/research/f017_corrected_oracle_secondary_target_source_v6.py", "SecondaryTargetSourceV6", "SecondaryTargetMatrixV6",
        ),
    ]
    for old_path, old_source, old_matrix, new_path, new_source, new_matrix in cases:
        old = historical(old_path)
        new = (ROOT / new_path).read_text()
        if class_methods(old, old_source) != class_methods(new, new_source):
            raise ValueError(f"source method extraction drift: {new_path}")
        if class_methods(new, new_matrix) != class_methods(old, old_matrix) - {"matvec"}:
            raise ValueError(f"matrix arithmetic was not exclusively removed: {new_path}")
        if constructor_args(new, new_source) != ["self", "auth", "catalog", "checkpoint_root", "identity_file", "event_root"]:
            raise ValueError(f"authorization-bound constructor drift: {new_path}")
        if "AUTH_SCHEMA = 'pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/6.0.0'" not in new:
            raise ValueError(f"v6 schema binding absent: {new_path}")
    print(json.dumps({"result": "PASS", "mode": "READ_ONLY_PROVENANCE_AUDIT", "target_sources": 2}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
