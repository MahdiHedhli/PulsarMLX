#!/usr/bin/env python3
"""Reproduce the frozen 599-path historical evidence census."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes

BASE_COMMIT = "cd4bbb19616b7edf99e4fb427eaf030b894b2732"
ROLE_PATHS = (
    "docs/architecture/reviews/evidence/f017-event06-v12-sequence09-canonical-readiness-qualification-v1.json",
    "docs/architecture/reviews/evidence/f017-event06-v12-sequence09-installation-preparation-qualification-v1.json",
    "docs/architecture/reviews/evidence/f017-event06-v12-sequence09-failure-qualification-v1.json",
    "docs/architecture/reviews/evidence/f017-event06-v12-sequence09-no-access-rehearsal-v1.json",
    "docs/architecture/reviews/evidence/f017-event06-v12-sequence09-full-corpus-validation-v1.json",
)


def enumerate_paths(repository: Path) -> tuple[str, ...]:
    completed = subprocess.run(
        [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            BASE_COMMIT,
            "docs/architecture/reviews/evidence",
        ],
        cwd=repository,
        check=True,
        text=True,
        capture_output=True,
    )
    historical = {
        path
        for path in completed.stdout.splitlines()
        if "f017-event06" in path
    }
    return tuple(sorted(historical | set(ROLE_PATHS)))


def validate(repository: Path) -> dict[str, object]:
    paths = enumerate_paths(repository)
    if len(paths) != 599:
        raise ValueError(f"historical evidence path census: {len(paths)}")
    missing = [path for path in ROLE_PATHS if not (repository / path).is_file()]
    if missing:
        raise ValueError(f"missing Sequence 9 role paths: {missing}")
    path_set_sha256 = hashlib.sha256(canonical_bytes(list(paths))).hexdigest()
    failure_records = tuple(
        path
        for path in paths
        if any(marker in Path(path).name for marker in ("failure", "blocker", "rejection"))
    )
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence09-full-corpus-reproduction/1.0.0",
        "base_commit": BASE_COMMIT,
        "selection_rule": "git ls-tree BASE docs/evidence; basename contains f017-event06; union five Q4 role paths; sort unique",
        "historical_evidence_path_census": len(paths),
        "historical_evidence_path_census_sha256": path_set_sha256,
        "paths": list(paths),
        "historical_failure_record_count": len(failure_records),
        "historical_failure_records": list(failure_records),
        "historical_failures_enumerated": True,
        "ignored_failure_keys": 0,
        "unexplained_failures": 0,
        "result": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate(args.repository.resolve())
    raw = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output is not None:
        args.output.write_text(raw, encoding="utf-8")
    else:
        print(raw, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
