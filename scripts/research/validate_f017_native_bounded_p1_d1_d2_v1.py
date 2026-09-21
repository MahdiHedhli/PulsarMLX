#!/usr/bin/env python3
"""Validate frozen F017 D1 counter semantics and D2 accounting/residency."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


D1 = Path("specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-counter-semantics-v1.json")
D2 = Path("specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-accounting-residency-v1.json")
EXPECTED_COUNTERS = {
    "callback_count", "managed_created", "managed_destroyed", "derived_created",
    "derived_destroyed", "default_cpu_stream_created", "default_cpu_stream_freed",
    "default_gpu_stream_created", "default_gpu_stream_freed", "owned_stream_created",
    "owned_stream_freed", "native_default_cpu_stream_freed",
    "native_default_gpu_stream_freed", "native_owned_stream_freed",
    "native_live_stream_handles", "native_duplicate_free_attempts",
    "native_origin_mismatches", "context_active", "registrations", "teardowns",
    "in_flight_work", "stale_native_ready_generations",
}
COUNTER_KEYS = {
    "name", "type", "owner", "producer", "current_surface", "scope",
    "pre_invariant", "post_invariant", "allowed_variance", "zero_valid",
    "monotonic", "failure_meaning",
}


class ValidationError(RuntimeError):
    pass


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValidationError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(), object_pairs_hook=reject_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot parse {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"root must be object: {path}")
    return value


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_bytes(root: Path, commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=root, capture_output=True, check=True
    )
    return result.stdout


def validate_d1(root: Path, doc: dict[str, Any]) -> None:
    if doc.get("schema") != "pulsarmlx.f017.native-bounded-p1-counter-semantics" or doc.get("schema_version") != "1.0.0":
        raise ValidationError("D1 schema mismatch")
    if doc.get("status") != "FROZEN_BEFORE_NATIVE_EXECUTOR_IMPLEMENTATION" or doc.get("counter_count") != 22:
        raise ValidationError("D1 status/count mismatch")
    snapshot = doc.get("snapshot_contract", {})
    if snapshot != {
        "target_type": "P1AccountingSnapshot",
        "target_api": "stream::P1AccountingSnapshot::capture",
        "single_typed_source_of_truth": True,
        "caller_supplied_values": False,
        "cached_snapshot_permitted": False,
        "strict_non_boolean_u64": True,
        "coherence_boundary": "NATIVE_RUNTIME_QUIESCENCE_LOCK_PLUS_SEQUENTIAL_ATOMIC_ACQUIRE_LOADS",
        "pre_capture_point": "AFTER_DURABLE_ATTEMPT_START_BEFORE_P1_TENSOR_MATH",
        "post_capture_point": "AFTER_SYNCHRONIZE_AND_RESOURCE_TEARDOWN_BEFORE_RECEIPT_BANKING",
    }:
        raise ValidationError("D1 snapshot contract weakened")
    rows = doc.get("counters")
    if not isinstance(rows, list) or len(rows) != 22:
        raise ValidationError("D1 counter rows must be exactly 22")
    names = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != COUNTER_KEYS:
            raise ValidationError("D1 counter row key census mismatch")
        if row["type"] != "u64" or row["scope"] not in {"attempt", "process"}:
            raise ValidationError(f"D1 counter type/scope mismatch: {row['name']}")
        if not all(isinstance(row[key], str) and row[key] for key in ("owner", "producer", "current_surface", "pre_invariant", "post_invariant", "allowed_variance", "failure_meaning")):
            raise ValidationError(f"D1 counter semantic field empty: {row['name']}")
        if not isinstance(row["zero_valid"], bool) or not isinstance(row["monotonic"], bool):
            raise ValidationError(f"D1 boolean semantics malformed: {row['name']}")
        names.append(row["name"])
    if set(names) != EXPECTED_COUNTERS or len(names) != len(set(names)):
        raise ValidationError("D1 exact counter census mismatch")
    sources = doc.get("source_authorities", [])
    if len(sources) != 5:
        raise ValidationError("D1 source authority census mismatch")
    for binding in sources:
        if binding.get("branch") != "feat/017-rust-native-inference-runtime" or binding.get("commit") != "d85e7f88c4939f1af3c4d816323897bfc40c4f2f":
            raise ValidationError("D1 predecessor source authority mismatch")
        raw = git_bytes(root, binding["commit"], binding["path"])
        if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
            raise ValidationError(f"D1 source hash mismatch: {binding['path']}")
    rule = doc.get("implementation_rule", {})
    if rule != {
        "d3_must_export_all_fields_from_live_native_state": True,
        "hardcoded_zero_forbidden": True,
        "validator_or_fixture_as_counter_source_forbidden": True,
        "receipt_must_bind_this_contract_sha256": True,
        "missing_producer_is_acceptance_blocking": True,
    }:
        raise ValidationError("D1 producer rule weakened")
    if doc.get("phase_accounting") != {"real_m1_ultra_p1_executions": 0, "checkpoint_reads": 0, "live_p1_authorizations": 0}:
        raise ValidationError("D1 phase accounting changed")


def validate_d2(root: Path, doc: dict[str, Any]) -> None:
    if doc.get("schema") != "pulsarmlx.f017.native-bounded-p1-accounting-residency" or doc.get("schema_version") != "1.0.0":
        raise ValidationError("D2 schema mismatch")
    if doc.get("status") != "FROZEN_BEFORE_REAL_CHECKPOINT_INTEGRATION":
        raise ValidationError("D2 status mismatch")
    master = doc.get("historical_master", {})
    expected_identity = {
        "branch": "feat/017-real-checkpoint-runner",
        "commit": "f2a7aa38c96b85cf7939c8ed653076732f066222",
        "path": "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v2.json",
        "sha256": "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e",
        "schema": "pulsarmlx.f017.real-payload-access-ledger",
        "schema_version": "2.0.0",
        "semantic_role": "AUTHORITATIVE_HISTORICAL_MASTER_REAL_PAYLOAD_LEDGER",
    }
    for key, expected in expected_identity.items():
        if master.get(key) != expected:
            raise ValidationError(f"D2 master identity mismatch: {key}")
    raw = git_bytes(root, master["commit"], master["path"])
    if hashlib.sha256(raw).hexdigest() != master["sha256"]:
        raise ValidationError("D2 historical master hash mismatch")
    parsed = json.loads(raw, object_pairs_hook=reject_duplicates)
    if parsed.get("schema") != master["schema"] or parsed.get("schema_version") != master["schema_version"]:
        raise ValidationError("D2 historical master schema mismatch")
    if master.get("terminal_count") != 175 or master.get("unit") != "BOUNDED_EXPLICIT_TENSOR_PAYLOAD_READ":
        raise ValidationError("D2 historical master terminal/unit mismatch")
    event = doc.get("native_event_model", {})
    required_event = {
        "event_class": "NATIVE_P1_EXECUTION_EVENT",
        "native_event_ledger": "APPEND_ONLY_SEPARATE_EVENT_CENSUS",
        "native_event_delta_on_durable_start": 1,
        "historical_master_before": 175,
        "historical_master_after": 175,
        "historical_master_delta": 0,
        "does_not_mean_no_checkpoint_access": True,
        "does_not_create_competing_master": True,
        "result_receipt_terminal_and_native_event_banked_atomically": True,
        "historical_master_update_same_commit_if_future_receipt_advances_it": True,
        "counts_derived_from_receipts_not_hand_entered": True,
    }
    for key, expected in required_event.items():
        if event.get(key) != expected:
            raise ValidationError(f"D2 native event invariant mismatch: {key}")
    access = doc.get("checkpoint_access_contract", {})
    if access.get("shard_count") != 6 or access.get("expected_file_opens") != 6 or access.get("fallback") != "PROHIBITED" or access.get("page_faults_as_historical_payload_units") is not False:
        raise ValidationError("D2 checkpoint access model weakened")
    rn1 = doc.get("rn1_attempt_lifecycle", {})
    if rn1.get("sequence") != ["PREFLIGHT", "EXCLUSIVE_OWNED_CLAIM", "DURABLE_ATTEMPT_START", "PRE_SNAPSHOT", "BOUNDED_EXECUTION", "POST_SNAPSHOT", "RECEIPT", "TERMINALIZE", "MANDATORY_STOP"]:
        raise ValidationError("D2 RN1 sequence changed")
    for key in ("claim_before_execution_authority", "durably_records_owner_pid_and_attempt_identity", "exception_may_terminalize_only_attempt_started_and_owned_by_this_process", "terminal_consumed_counts_derived_from_receipts", "terminal_receipt_count_cross_check"):
        if rn1.get(key) is not True:
            raise ValidationError(f"D2 RN1 guard disabled: {key}")
    if rn1.get("shared_terminal_state_is_not_ownership_authority") is not True or rn1.get("terminal_json_sole_accounting_authority") is not False:
        raise ValidationError("D2 RN1 ownership/accounting authority weakened")
    if doc.get("memory_admission") != {
        "minimum_free_bytes": 17179869184,
        "source": "mach_vm_statistics64",
        "maximum_sample_age_seconds": 5,
        "role": "PRE_EXECUTION_SAFETY_MARGIN_NOT_PROOF_MODEL_FITS_IN_RAM",
        "caller_supplied_value_authoritative": False,
    }:
        raise ValidationError("D2 memory admission changed")
    if doc.get("phase_accounting") != {"historical_master_before":175,"historical_master_after":175,"checkpoint_reads":0,"shard_opens":0,"real_m1_ultra_p1_executions":0,"live_p1_authorizations":0}:
        raise ValidationError("D2 phase accounting changed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    d1 = load(root / D1)
    d2 = load(root / D2)
    validate_d1(root, d1)
    validate_d2(root, d2)
    print(json.dumps({
        "result": "PASS", "counter_count": 22,
        "historical_master_terminal": 175, "native_event_class": "NATIVE_P1_EXECUTION_EVENT",
        "historical_master_delta": 0, "checkpoint_reads_this_phase": 0,
        "d1_sha256": sha(root / D1), "d2_sha256": sha(root / D2),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
