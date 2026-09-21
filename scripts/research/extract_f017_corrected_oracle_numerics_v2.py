#!/usr/bin/env python3
"""Audit the historical-to-v2 pure-core extraction without rewriting authority.

The original one-shot extraction helper became stale after row arithmetic was
moved from the target matrices into the pure cores. This successor is
deliberately read-only: it proves the committed symbol mapping against exact
historical Git bytes and rejects target-capable APIs in the successor cores.
"""
from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMIT = "84f0d1dc3e60a4151329ed82773880951ee3e618"
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"


def historical(path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{COMMIT}:{path}"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout


def top_symbols(text: str) -> set[str]:
    result: set[str] = set()
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            result.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            result.update(target.id for target in targets if isinstance(target, ast.Name))
    return result


def main() -> int:
    mapping = json.loads((CONTRACTS / "f017-corrected-oracle-numerical-symbol-mapping-v1.json").read_text())
    roles = {
        "primary": (
            "scripts/research/f017_corrected_oracle_primary.py",
            "scripts/research/f017_corrected_oracle_primary_numerics_v2.py",
        ),
        "secondary": (
            "scripts/research/f017_corrected_oracle_secondary.py",
            "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py",
        ),
    }
    audited = 0
    for role, (old_path, new_path) in roles.items():
        old_symbols = top_symbols(historical(old_path))
        new_text = (ROOT / new_path).read_text()
        new_symbols = top_symbols(new_text)
        record = mapping[role]
        exact = record["exact_or_interface_only"]
        if record["historical_path"] != old_path or record["successor_path"] != new_path:
            raise ValueError(f"{role} path mapping")
        for historical_symbol, successor in exact.items():
            if historical_symbol not in old_symbols:
                raise ValueError(f"{role} historical symbol absent: {historical_symbol}")
            if successor not in new_symbols:
                raise ValueError(f"{role} pure successor absent: {successor}")
            audited += 1
        for historical_symbol in record["moved_target_arithmetic"]:
            class_name, method_name = historical_symbol.split(".", 1)
            old_class_methods = next(
                {item.name for item in node.body if isinstance(item, ast.FunctionDef)}
                for node in ast.parse(historical(old_path)).body
                if isinstance(node, ast.ClassDef) and node.name == class_name
            )
            if method_name not in old_class_methods:
                raise ValueError(f"{role} moved arithmetic source absent: {historical_symbol}")
            audited += 1
        forbidden = {"StreamingCatalogSource", "StreamingMatrix", "CatalogStore", "CatalogMatrix", "main"}
        if new_symbols & forbidden:
            raise ValueError(f"{role} target surface retained: {sorted(new_symbols & forbidden)}")
    print(json.dumps({"result": "PASS", "mode": "READ_ONLY_PROVENANCE_AUDIT", "mapped_symbols": audited}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
