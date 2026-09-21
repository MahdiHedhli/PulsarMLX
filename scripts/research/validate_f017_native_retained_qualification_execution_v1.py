#!/usr/bin/env python3
"""Validate the completed F017 retained-only D3.5 execution evidence.

This validator intentionally proves execution/accounting/determinism only.  It
does not promote the event to a D0 numerical PASS; that remains a distinct
authority boundary recorded by the evidence artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    def no_duplicates(pairs: list[tuple[str, object]]) -> dict:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r} in {path}")
            result[key] = value
        return result

    value = json.loads(path.read_text(), object_pairs_hook=no_duplicates)
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a JSON object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_root(rows: list[dict]) -> str:
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path(
            "docs/architecture/reviews/evidence/"
            "f017-native-retained-qualification-execution-evidence-v1.json"
        ),
    )
    args = parser.parse_args()
    evidence = load_json(args.evidence)

    expected_keys = {
        "schema",
        "schema_version",
        "status",
        "event",
        "committed_authority",
        "machine_local_authority",
        "runtime",
        "execution_accounting",
        "determinism",
        "grading_boundary",
        "phase_invariants",
        "next_safe_action",
    }
    require(set(evidence) == expected_keys, "evidence top-level key census")
    require(
        evidence["schema"]
        == "pulsarmlx.f017.native-retained-qualification-execution-evidence",
        "evidence schema",
    )
    require(evidence["schema_version"] == "1.0.0", "evidence schema version")
    require(
        evidence["status"]
        == "EXECUTION_COMPLETE_D0_NUMERICAL_ACCEPTANCE_NOT_YET_DECLARED",
        "evidence status must not claim D3.5 acceptance",
    )

    root = Path(evidence["machine_local_authority"]["root"])
    require(root.is_absolute() and root.is_dir() and not root.is_symlink(), "root")
    attempt = root / "attempt-state"
    captures = root / "captures"
    paths = {
        "owner": attempt / "owner.json",
        "durable_attempt_start": attempt / "durable-attempt-start.json",
        "terminal": attempt / "terminal.json",
        "repeat_result": captures / "repeat-result.json",
    }
    bound = evidence["machine_local_authority"]
    for label, path in paths.items():
        require(path.is_file() and not path.is_symlink(), f"missing {label}")
        require(sha256(path) == bound[f"{label}_sha256"], f"{label} SHA")

    owner = load_json(paths["owner"])
    start = load_json(paths["durable_attempt_start"])
    terminal = load_json(paths["terminal"])
    repeat = load_json(paths["repeat_result"])
    require(owner == start, "durable start must be the immutable owned claim")
    require(owner["event_id"] == evidence["event"]["event_id"], "event ID")
    require(owner["ownership_nonce"] == terminal["ownership_nonce"], "owner nonce")
    require(owner["owner_pid"] == terminal["owner_pid"], "owner PID")
    require(terminal["state"] == "COMPLETE", "terminal state")
    require(not terminal["retry_permitted"] and not terminal["resume_permitted"], "retry")
    require(terminal["authoritative_retained_read_receipt_count"] == 800, "terminal count")
    require(terminal["expected_success_receipt_count"] == 800, "expected count")
    require(terminal["repeat_result_sha256"] == sha256(paths["repeat_result"]), "repeat bind")
    require(
        repeat["total_runs"] == 20
        and repeat["same_process_runs"] == 10
        and repeat["fresh_process_runs"] == 10
        and repeat["stages_per_run"] == 34
        and repeat["retained_reads_per_run"] == 40
        and repeat["retained_read_receipts"] == 800,
        "repeat census",
    )
    require(repeat["all_stage_bytes_exact"] and repeat["earliest_divergence"] is None, "repeat")
    require(
        repeat["original_checkpoint_reads"] == 0
        and repeat["original_checkpoint_shard_opens"] == 0
        and repeat["historical_payload_ledger_delta"] == 0,
        "checkpoint/ledger accounting",
    )

    run_dirs = sorted(path for path in captures.iterdir() if path.is_dir())
    require(len(run_dirs) == 20, "run directory census")
    require(
        [path.name for path in run_dirs]
        == [f"fresh-{index:02d}" for index in range(10)]
        + [f"same-{index:02d}" for index in range(10)],
        "run names",
    )
    reference_stages: list[dict] | None = None
    manifest_rows: list[dict] = []
    receipt_rows: list[dict] = []
    all_capture_rows: list[dict] = []
    for run_dir in run_dirs:
        manifest_path = run_dir / "capture-manifest.json"
        receipt_path = run_dir / "retained-read-receipts.json"
        manifest = load_json(manifest_path)
        receipts = load_json(receipt_path)
        stages = manifest.get("stages")
        reads = receipts.get("reads")
        require(isinstance(stages, list) and len(stages) == 34, f"{run_dir.name} stages")
        require(isinstance(reads, list) and len(reads) == 40, f"{run_dir.name} reads")
        require(receipts["actual_count"] == len(reads) == receipts["expected_count"] == 40, "COUNT")
        require(receipts["original_checkpoint_reads"] == 0, "checkpoint reads")
        require(receipts["original_checkpoint_shard_opens"] == 0, "shard opens")
        require(sorted(row["ordinal"] for row in reads) == list(range(40)), "read ordinals")
        require(len({row["role"] for row in reads}) == 40, "read roles")
        for row in reads:
            require(not row["checkpoint_read"] and not row["original_checkpoint_shard_open"], "read class")
            require(
                row["expected_sha256"]
                == row["before_sha256"]
                == row["consumed_sha256"]
                == row["after_sha256"],
                "retained identity",
            )
        compact = [
            {
                key: row[key]
                for key in ("ordinal", "stage_id", "sha256", "dtype", "shape", "byte_length")
            }
            for row in stages
        ]
        if reference_stages is None:
            reference_stages = compact
        require(compact == reference_stages, "cross-run stage identity")
        for row in stages:
            artifact = run_dir / row["path"]
            require(artifact.is_file() and not artifact.is_symlink(), "stage artifact")
            require(artifact.stat().st_size == row["byte_length"], "stage byte length")
            require(sha256(artifact) == row["sha256"], "stage SHA")
        manifest_rows.append(
            {"path": str(manifest_path.relative_to(root)), "sha256": sha256(manifest_path)}
        )
        receipt_rows.append(
            {"path": str(receipt_path.relative_to(root)), "sha256": sha256(receipt_path)}
        )
        for artifact in sorted(path for path in run_dir.iterdir() if path.is_file()):
            all_capture_rows.append(
                {
                    "path": str(artifact.relative_to(root)),
                    "sha256": sha256(artifact),
                    "byte_length": artifact.stat().st_size,
                }
            )

    require(canonical_root(manifest_rows) == bound["capture_manifest_root_sha256"], "manifest root")
    require(canonical_root(receipt_rows) == bound["read_receipt_root_sha256"], "receipt root")
    require(canonical_root(all_capture_rows) == bound["run_capture_root_sha256"], "capture root")
    require(len(all_capture_rows) == 720, "run capture file census")
    require(sum(row["byte_length"] for row in all_capture_rows) == 22_326_600, "capture bytes")
    require(
        evidence["grading_boundary"]["d0_numerical_acceptance_declared"] is False,
        "validator may not declare numerical acceptance",
    )
    require(evidence["phase_invariants"]["real_m1_ultra_p1_executions"] == 0, "P1")
    print("F017_NATIVE_RETAINED_QUALIFICATION_EXECUTION_EVIDENCE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
