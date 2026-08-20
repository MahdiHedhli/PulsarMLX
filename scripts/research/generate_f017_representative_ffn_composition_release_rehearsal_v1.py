#!/usr/bin/env python3
"""Generate checkpoint-free FFN release-mechanics rehearsal evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from f017_representative_ffn_composition_release_wrapper_v1 import (
    MANIFEST_BASENAME,
    OUTPUT_BASENAME,
    OUTPUT_BYTES,
    ReleaseError,
    begin_attempt,
    begin_ffn,
    fixed_paths,
    publish_output_and_manifest,
    write_receipt,
    write_terminal,
)
from f017_representative_ffn_composition_release_terminalizer_v1 import reconcile


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def roots(temporary: str) -> dict[str, Path]:
    paths = fixed_paths(Path(temporary))
    paths["release_root"].mkdir(parents=True, mode=0o700)
    paths["output_root"].mkdir(mode=0o700)
    os.chmod(paths["release_root"], 0o700)
    os.chmod(paths["output_root"], 0o700)
    return paths


def authorities(temporary: str) -> tuple[Path, Path, Path]:
    result = tuple(Path(temporary) / name for name in ("release.json", "approval.json", "token.json"))
    for path in result:
        path.write_text("{}\n", encoding="utf-8")
        os.chmod(path, 0o400)
    return result


def race_worker(home: Path, release: Path, approval: Path, token: Path) -> int:
    try:
        begin_attempt(fixed_paths(home), release, approval, token)
        return 0
    except (ReleaseError, FileExistsError):
        return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--race-worker", action="store_true")
    parser.add_argument("--home", type=Path)
    parser.add_argument("--release", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--token", type=Path)
    args = parser.parse_args()
    if args.race_worker:
        return race_worker(args.home, args.release, args.approval, args.token)
    if args.output is None:
        raise RuntimeError("output required")
    synthetic = bytes(OUTPUT_BYTES)
    cases: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as temporary:
        paths = roots(temporary)
        output_sha, manifest_sha = publish_output_and_manifest(synthetic, paths["output_root"])
        if output_sha != sha(synthetic) or len(manifest_sha) != 64:
            raise RuntimeError("publication identity")
        cases["durable_output_and_manifest_publication"] = "PASS"
        try:
            publish_output_and_manifest(synthetic, paths["output_root"])
        except ReleaseError:
            cases["preexisting_output_rejected"] = "PASS"
        else:
            raise RuntimeError("overwrite accepted")
    with tempfile.TemporaryDirectory() as temporary:
        paths = roots(temporary)
        release, approval, token = authorities(temporary)
        command = [sys.executable, __file__, "--race-worker", "--home", temporary,
                   "--release", str(release), "--approval", str(approval), "--token", str(token)]
        processes = [subprocess.Popen(command) for _ in range(2)]
        results = sorted(process.wait() for process in processes)
        if results != [0, 2]:
            raise RuntimeError(f"concurrent attempt results: {results}")
        reconciled = reconcile(paths["state_root"], paths["output"], paths["output_manifest"], release)
        if reconciled["disposition"] != "INTERRUPTED_AFTER_ATTEMPT_START_BEFORE_FFN" or not reconciled["release_consumed"]:
            raise RuntimeError("concurrent reconciliation")
        cases["two_process_concurrent_attempt_exactly_one_winner"] = "PASS"
    with tempfile.TemporaryDirectory() as temporary:
        paths = roots(temporary)
        release, approval, token = authorities(temporary)
        paths["state_root"].mkdir(mode=0o700)
        partial = reconcile(paths["state_root"], paths["output"], paths["output_manifest"], release)
        if partial["disposition"] != "PARTIAL_START_ROOT_ZERO_COMPUTE_REQUIRES_ADJUDICATION" or partial["release_consumed"]:
            raise RuntimeError("partial root")
        cases["partial_start_root_zero_compute_fail_closed"] = "PASS"
    with tempfile.TemporaryDirectory() as temporary:
        paths = roots(temporary)
        release, approval, token = authorities(temporary)
        begin_attempt(paths, release, approval, token)
        begin_ffn(paths, release)
        interrupted = reconcile(paths["state_root"], paths["output"], paths["output_manifest"], release)
        if interrupted["ffn_compositions"] != 1 or interrupted["disposition"] != "INTERRUPTED_AFTER_FFN_START_NO_OUTPUT":
            raise RuntimeError("durable FFN accounting")
        cases["durable_ffn_start_counts_one_after_interruption"] = "PASS"
        write_terminal(paths, "TERMINAL_FAILURE", None, None, None, "synthetic-before-output")
        failed = reconcile(paths["state_root"], paths["output"], paths["output_manifest"], release)
        if failed["ffn_compositions"] != 1 or failed["output_authority"]:
            raise RuntimeError("failure accounting")
        cases["post_start_failure_consumes_attempt_without_authority"] = "PASS"
    with tempfile.TemporaryDirectory() as temporary:
        paths = roots(temporary)
        release, approval, token = authorities(temporary)
        begin_attempt(paths, release, approval, token)
        begin_ffn(paths, release)
        output_sha, manifest_sha = publish_output_and_manifest(synthetic, paths["output_root"])
        published = reconcile(paths["state_root"], paths["output"], paths["output_manifest"], release)
        if published["disposition"] != "INTERRUPTED_OUTPUT_PUBLISHED_REQUIRES_ADJUDICATION" or published["output_authority"]:
            raise RuntimeError("published interruption")
        cases["published_output_without_receipt_terminal_has_no_authority"] = "PASS"
        receipt_sha = write_receipt(paths, release, output_sha, manifest_sha, {"routed": {}, "shared": {}})
        write_terminal(paths, "COMPLETE", output_sha, manifest_sha, receipt_sha, None)
        complete = reconcile(paths["state_root"], paths["output"], paths["output_manifest"], release)
        if complete["disposition"] != "COMPLETE_RECONSTRUCTED" or not complete["output_authority"]:
            raise RuntimeError("complete authority")
        cases["output_manifest_receipt_complete_terminal_authority"] = "PASS"
    evidence = {
        "schema": "pulsarmlx.f017.representative-ffn-composition-release-rehearsal",
        "schema_version": "1.0.0",
        "synthetic_publication_bytes": OUTPUT_BYTES,
        "synthetic_publication_sha256": sha(synthetic),
        "real_routed_bytes_used": False,
        "real_shared_bytes_used": False,
        "real_ffn_compositions": 0,
        "s1_materializations": 0,
        "s2_constructions": 0,
        "cases": cases,
        "case_count": len(cases),
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
        "shared_expert_executions": 0,
        "result": "PASS",
    }
    args.output.write_text(json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
