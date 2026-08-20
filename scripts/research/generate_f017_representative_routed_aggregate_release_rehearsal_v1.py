#!/usr/bin/env python3
"""Generate checkpoint-free rehearsal evidence for release mechanics only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

from f017_representative_routed_aggregate_release_wrapper_v1 import (
    OUTPUT_BYTES,
    ReleaseError,
    begin_attempt,
    fixed_paths,
    publish_no_replace,
)
from f017_representative_routed_aggregate_release_terminalizer_v1 import reconcile


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def roots(temporary: str) -> dict[str, Path]:
    paths = fixed_paths(Path(temporary))
    paths["release_root"].mkdir(parents=True, mode=0o700)
    paths["output_root"].mkdir(mode=0o700)
    os.chmod(paths["release_root"], 0o700)
    os.chmod(paths["output_root"], 0o700)
    return paths


def authority_files(temporary: str) -> tuple[Path, Path, Path]:
    paths = [Path(temporary) / name for name in ("release.json", "approval.json", "token.json")]
    for path in paths:
        path.write_text("{}\n")
        os.chmod(path, 0o400)
    return paths[0], paths[1], paths[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    synthetic = bytes(OUTPUT_BYTES)
    cases: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as temporary:
        paths = roots(temporary)
        identity = publish_no_replace(synthetic, paths["output_root"])
        if identity != sha(synthetic):
            raise RuntimeError("publication identity")
        cases["durable_no_replace_publication"] = "PASS"
        try:
            publish_no_replace(synthetic, paths["output_root"])
        except ReleaseError:
            cases["preexisting_output_rejected"] = "PASS"
        else:
            raise RuntimeError("overwrite accepted")
    with tempfile.TemporaryDirectory() as temporary:
        paths = roots(temporary)
        release, approval, token = authority_files(temporary)
        begin_attempt(paths, release, approval, token)
        try:
            begin_attempt(paths, release, approval, token)
        except ReleaseError:
            cases["duplicate_attempt_rejected"] = "PASS"
        else:
            raise RuntimeError("duplicate attempt accepted")
        interrupted = reconcile(paths["state_root"], paths["output"], release)
        if interrupted["disposition"] != "INTERRUPTED_NO_OUTPUT" or not interrupted["release_consumed"]:
            raise RuntimeError("interruption reconciliation")
        cases["interrupted_no_output_consumed"] = "PASS"
    with tempfile.TemporaryDirectory() as temporary:
        paths = roots(temporary)
        release, approval, token = authority_files(temporary)
        begin_attempt(paths, release, approval, token)
        identity = publish_no_replace(synthetic, paths["output_root"])
        interrupted = reconcile(paths["state_root"], paths["output"], release)
        if interrupted["disposition"] != "INTERRUPTED_OUTPUT_PUBLISHED" or interrupted["output_sha256"] != identity:
            raise RuntimeError("published interruption reconciliation")
        cases["published_output_without_terminal_recovered"] = "PASS"
    evidence = {
        "schema": "pulsarmlx.f017.representative-routed-aggregate-release-rehearsal",
        "schema_version": "1.0.0",
        "synthetic_publication_bytes": OUTPUT_BYTES,
        "synthetic_publication_sha256": sha(synthetic),
        "real_representative_output_bytes_used": False,
        "real_aggregate_computed": False,
        "cases": cases,
        "case_count": len(cases),
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
        "aggregate_executions": 0,
        "result": "PASS",
    }
    args.output.write_text(json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
