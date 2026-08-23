#!/usr/bin/env python3
"""Mechanical, auditable removal of target-only AST nodes from v2 cores.

The extraction is deliberately line-preserving outside the named top-level
nodes so numerical expressions retain their historical source spelling.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    "scripts/research/f017_corrected_oracle_primary_numerics_v2.py": {
        "_RetiredStreamingCatalogSource",
        "_RetiredStreamingMatrix",
    },
    "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py": {
        "_RetiredCatalogStore",
        "_RetiredCatalogMatrix",
    },
}


def extract(path: Path, names: set[str]) -> None:
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    spans = [
        (node.lineno - 1, node.end_lineno)
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in names
    ]
    found = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in names
    }
    if found != names:
        raise ValueError(f"extraction symbol census: {path}: {found} != {names}")
    for start, stop in sorted(spans, reverse=True):
        del lines[start:stop]
    data = "".join(lines).encode()
    temporary = path.with_name(path.name + ".extracting")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    for relative, names in TARGETS.items():
        extract(ROOT / relative, names)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
