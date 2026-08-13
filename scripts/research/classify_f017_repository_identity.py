#!/usr/bin/env python3
"""Create the canonical F017 repository-identity v2 drift attestation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

VERSION = "f017-trusted-repository-identity-v2"


def classify(path: str) -> tuple[str, bool]:
    if path.startswith("docs/architecture/reviews/evidence/"):
        return "evidence", True
    if path.startswith("docs/architecture/reviews/"):
        return "docs_reviews", True
    if path.startswith("docs/"):
        return "docs", True
    if path.startswith("crates/quant/"):
        return "decoder", False
    if path.startswith("crates/stream/") or path.endswith(".mm"):
        return "mlx_bridge", False
    if path.startswith("crates/f017-runner/src/artifact_paths.rs"):
        return "path_resolver", False
    if path.startswith("crates/f017-runner/src/"):
        return "execution_runner", False
    if path.startswith("crates/"):
        return "runtime_compute", False
    if path.startswith("scripts/research/tests/") or "/tests/" in path:
        return "tests", False
    if path.startswith("scripts/research/validate_"):
        return "evidence_validator", False
    if path.startswith("scripts/"):
        return "execution_tooling", False
    if path.startswith("specs/"):
        return "schema_contracts", False
    if path.startswith(".github/"):
        return "ci", False
    return "unclassified", False


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def document(root: Path, compiled: str, authorization: str) -> dict[str, object]:
    raw = git(root, "diff", "--name-status", "--no-renames", f"{compiled}..{authorization}")
    entries: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    for line in raw.splitlines():
        status, path = line.split("\t", 1)
        category, permitted = classify(path)
        counts[category] = counts.get(category, 0) + 1
        entries.append({"status": status, "category": category, "path": path, "permitted": permitted})
    return {
        "contract_version": VERSION,
        "compiled_runtime_sha": compiled,
        "authorization_head_sha": authorization,
        "entries": entries,
        "category_counts": dict(sorted(counts.items())),
        "runtime_semantics_unchanged": all(bool(entry["permitted"]) for entry in entries),
    }


def canonical(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--compiled-runtime-sha", required=True)
    parser.add_argument("--authorization-head-sha", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = document(args.repository_root, args.compiled_runtime_sha, args.authorization_head_sha)
    raw = canonical(result)
    if args.output:
        args.output.write_bytes(raw)
    print(hashlib.sha256(raw).hexdigest())
    if not result["runtime_semantics_unchanged"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
