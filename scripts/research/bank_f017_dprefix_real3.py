#!/usr/bin/env python3
"""Bank the one-shot DPREFIX-REAL-3 replay from immutable private evidence.

This closeout is checkpoint-free.  It validates the bound replay products,
applies the independently released REAL-2 oracle-state identity gate, and
derives public terminal evidence without rerunning either oracle or candidate.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
PRIVATE = ROOT / ".pulsarmlx-local/dprefix-real-3"

ATTEMPT = "DPREFIX-REAL-3"
EXECUTION_HEAD = "5b60782be0e6bfe01ffca5020e3979efbffa729d"
LEDGER = 139
PACKED_PACKAGE = "705066830506dbebab9212948059c71e76b4535eaeb41672c9dbd62f6e9ed156"
EXPECTED_ORACLE_STATE = "541d8dbcf459b49e9b5c69ae44f919a64c2eaaefa4f6daeb7e0d13443b521aff"
EXPECTED_CANDIDATE = "5192c51d2f1a133f769937d234c1f56621aa5484385a99708dcdc7bdc784beb8"

RAW_PATH = EVIDENCE / "f017-dprefix-real3-rejected-oracle-state-identity-v1.json"
PROVISIONAL_PATH = EVIDENCE / "f017-dprefix-real3-bound-runner-provisional-terminal-v1.json"
ORACLE_DESCRIPTOR_PATH = EVIDENCE / "f017-dprefix-real3-oracle-retention-descriptor-v1.json"
CANDIDATE_DESCRIPTOR_PATH = EVIDENCE / "f017-dprefix-real3-candidate-retention-descriptor-v1.json"
ATTEMPT_PATH = EVIDENCE / "f017-dense-prefix-replay-attempt-ledger-v2.json"
REVIEW_PATH = ROOT / "docs/architecture/reviews/f017-dprefix-real-3-rejected-evidence-review.md"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load(path: Path) -> dict[str, Any]:
    def reject_duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key in {path}: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def binding(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(ROOT)), "sha256": digest(path)}


def private_binding(path: Path, symbolic: str) -> dict[str, Any]:
    return {
        "symbolic_private_path": symbolic,
        "sha256": digest(path),
        "bytes": path.stat().st_size,
        "read_only": not bool(path.stat().st_mode & 0o222),
    }


def validate_private() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    terminal_path = PRIVATE / "terminal-evidence.json"
    candidate_path = PRIVATE / "candidate-evidence.json"
    oracle_manifest_path = PRIVATE / "oracle-primary/manifest.json"
    terminal = load(terminal_path)
    candidate = load(candidate_path)
    oracle_manifest = load(oracle_manifest_path)

    assert terminal["attempt_id"] == candidate["attempt_id"] == ATTEMPT
    assert terminal["terminal_class"] == "PASS"
    assert terminal["checkpoint_access"] == terminal["shard_opens"] == terminal["positional_reads"] == 0
    assert terminal["ledger_before"] == terminal["ledger_after"] == LEDGER
    assert terminal["packed_package_sha256"] == PACKED_PACKAGE
    assert len(terminal["decoded_identities"]) == 40
    assert terminal["decoded_identities"] == candidate["input_decoded_hashes"]
    assert candidate["repeats"] == 10 and candidate["deterministic"]
    assert len(candidate["stage_hashes"]) == 10
    assert all(item == candidate["stage_hashes"][0] for item in candidate["stage_hashes"])
    assert len(terminal["numerical_surfaces"]) == 8
    assert all(item["pass"] for item in terminal["numerical_surfaces"])
    assert all(item["candidate_non_finite_count"] == item["oracle_non_finite_count"] == 0 for item in terminal["numerical_surfaces"])
    assert all(item["signed_zero_mismatch_count"] == 0 for item in terminal["numerical_surfaces"])

    dispatch = terminal["runtime_accounting"]
    required = (
        "native_matvecs", "synchronizations", "readbacks", "actual_host_copy_count",
        "actual_host_copy_bytes", "cpu_rms_norm", "cpu_attention", "cpu_activation",
        "fallback", "backend_errors",
    )
    assert all(isinstance(dispatch.get(field), int) for field in required)
    assert dispatch["actual_host_copy_count"] == 4050
    assert dispatch["actual_host_copy_bytes"] == 10_145_280
    assert dispatch["fallback"] == dispatch["backend_errors"] == 0

    lifecycle = terminal["success_path_lifecycle_reconciliation"]
    assert lifecycle["result"] == "PASS"
    for left, right in (
        ("arrays_created", "arrays_destroyed"),
        ("managed_created", "managed_destroyed"),
        ("derived_created", "derived_destroyed"),
        ("contexts_created", "contexts_destroyed"),
        ("owned_streams_created", "owned_streams_destroyed"),
    ):
        assert lifecycle[left] == lifecycle[right]
    assert lifecycle["in_flight_work"] == lifecycle["stale_generations"] == lifecycle["singleton_live_state"] == 0
    assert lifecycle["child_process_terminated"]

    oracle = terminal["oracle"]
    assert oracle["persisted_before_candidate"] and oracle["rehash"] == "PASS"
    assert oracle["identity_before_candidate"] == oracle["identity_after_candidate"]
    for name in ("layer_2_output", "layer_3_entry"):
        artifact = PRIVATE / oracle["retention"][name]["symbolic_relative_path"]
        assert artifact.stat().st_size == 24_576
        assert digest(artifact) == oracle["retention"][name]["sha256"]
        assert not bool(artifact.stat().st_mode & 0o222)
    actual = oracle["retention"]["layer_3_entry"]["sha256"]
    assert actual != EXPECTED_ORACLE_STATE
    assert oracle_manifest["artifacts"]["layer_3_entry"]["sha256"] == actual
    assert digest(ROOT / ".pulsarmlx-local/oracle-build/f017-dense-prefix-candidate-v4") == EXPECTED_CANDIDATE

    payload_ledger = EVIDENCE / "f017-real-payload-access-ledger-v1.json"
    assert load(payload_ledger)["cumulative_tensor_payloads"] == LEDGER
    return terminal, candidate, oracle_manifest


def bank() -> dict[str, str]:
    terminal, candidate, oracle_manifest = validate_private()
    terminal_path = PRIVATE / "terminal-evidence.json"
    candidate_path = PRIVATE / "candidate-evidence.json"
    execution_start_path = PRIVATE / "execution-start.json"
    oracle_manifest_path = PRIVATE / "oracle-primary/manifest.json"
    material_manifest_path = PRIVATE / "material-manifest.json"
    candidate_identity_path = PRIVATE / "candidate-identity.json"
    payload_ledger_path = EVIDENCE / "f017-real-payload-access-ledger-v1.json"
    attempt_v1_path = EVIDENCE / "f017-dense-prefix-replay-attempt-ledger-v1.json"
    config_path = EVIDENCE / "f017-dprefix-replay-config-v1.json"
    authorization_path = EVIDENCE / "f017-dprefix-replay-authorization-v1.json"
    decoded_manifest_path = EVIDENCE / "f017-dprefix-real3-decoded-identity-manifest-v1.json"
    package_descriptor_path = EVIDENCE / "f017-dprefix-real2-packed-package-descriptor-v1.json"
    numerical_manifest_path = EVIDENCE / "f017-dprefix-numerical-surface-manifest-v1.json"
    metric_path = ROOT / "scripts/research/f017_dprefix_metric_engine.py"

    # Preserve the exact bound-runner output before applying the release gate.
    PROVISIONAL_PATH.write_bytes(terminal_path.read_bytes())
    assert digest(PROVISIONAL_PATH) == digest(terminal_path)

    oracle_artifacts: dict[str, Any] = {}
    for ordinal, name in enumerate(("layer_2_output", "layer_3_entry"), start=1):
        item = terminal["oracle"]["retention"][name]
        oracle_artifacts[name] = {
            **item,
            "semantic_id": name,
            "shape": [6144],
            "count": 6144,
            "dtype": "f32",
            "serialization": "canonical_little_endian_ieee754_binary32_c_order",
            "creation_ordinal": ordinal,
        }
    oracle_descriptor = {
        "schema": "pulsarmlx.f017.dprefix-real3-oracle-retention-descriptor",
        "schema_version": "1.0.0",
        "attempt_id": ATTEMPT,
        "symbolic_private_package": "f017-private/dprefix-real-3/oracle-primary",
        "manifest_sha256": digest(oracle_manifest_path),
        "package_identity": terminal["oracle"]["identity_after_candidate"],
        "persisted_before_candidate": True,
        "fsync_complete": True,
        "post_candidate_rehash": "PASS",
        "artifacts": oracle_artifacts,
        "expected_real2_layer3_sha256": EXPECTED_ORACLE_STATE,
        "identity_gate": "FAIL",
        "downstream_status": "NOT_ADMITTED",
    }
    write_json(ORACLE_DESCRIPTOR_PATH, oracle_descriptor)

    surface_by_name = {item["semantic_id"]: item for item in terminal["numerical_surfaces"]}
    candidate_artifacts: dict[str, Any] = {}
    for ordinal, name in enumerate(("layer_2_output", "layer_3_entry"), start=1):
        item = next(value for value in candidate["numerical_surface_package"] if value["semantic_id"] == name)
        candidate_artifacts[name] = {
            "semantic_id": name,
            "symbolic_private_path": f"f017-private/dprefix-real-3/candidate-evidence.json.surfaces/{name}.f32le",
            "sha256": item["sha256"],
            "bytes": item["canonical_bytes"],
            "shape": [6144],
            "count": 6144,
            "dtype": "f32",
            "serialization": item["serialization"],
            "creation_ordinal": ordinal,
            "immutable": item["immutable"],
            "read_only": item["read_only"],
        }
        assert candidate_artifacts[name]["sha256"] == surface_by_name[name]["candidate_sha256"]
    candidate_descriptor = {
        "schema": "pulsarmlx.f017.dprefix-real3-candidate-retention-descriptor",
        "schema_version": "1.0.0",
        "attempt_id": ATTEMPT,
        "candidate_binary_sha256": EXPECTED_CANDIDATE,
        "symbolic_private_package": "f017-private/dprefix-real-3/candidate-evidence.json.surfaces",
        "artifacts": candidate_artifacts,
    }
    write_json(CANDIDATE_DESCRIPTOR_PATH, candidate_descriptor)

    actual_oracle_state = oracle_artifacts["layer_3_entry"]["sha256"]
    raw = {
        "schema": "pulsarmlx.f017.dprefix-real3-terminal-evidence",
        "schema_version": "1.0.0",
        "attempt_id": ATTEMPT,
        "verdict": "REJECTED",
        "terminal_class": "EVIDENCE_VALIDATION",
        "reason_code": "ORACLE_STATE_IDENTITY_MISMATCH",
        "reason": "the replay completed its bound numerical path, but the freshly recomputed oracle Class-A state did not reproduce the precommitted REAL-2 canonical identity",
        "release": {
            "verdict": "GO FOR ONE CHECKPOINT-FREE DPREFIX-REAL-3 REPLAY",
            "adjudication_head": EXECUTION_HEAD,
            "execution_head": EXECUTION_HEAD,
        },
        "bindings": {
            "config": binding(config_path),
            "authorization": binding(authorization_path),
            "orchestrator_sha256": digest(ROOT / "scripts/research/f017_dprefix_real3_replay.py"),
            "candidate_binary_sha256": EXPECTED_CANDIDATE,
            "candidate_source_manifest_sha256": load(config_path)["candidate_source_manifest_sha256"],
            "oracle_package_sha256": load(config_path)["oracle_package_sha256"],
            "metric_engine_sha256": digest(metric_path),
            "numerical_surface_manifest": binding(numerical_manifest_path),
            "decoded_identity_manifest": binding(decoded_manifest_path),
            "packed_package_descriptor": binding(package_descriptor_path),
        },
        "access": {
            "input_authority": "IMMUTABLE_RETAINED_PACKED_PACKAGE_ONLY",
            "checkpoint_reads": 0,
            "shard_opens": 0,
            "positional_reads": 0,
            "payloads": 0,
            "packed_bytes_read_from_checkpoint": 0,
            "packed_package_sha256": PACKED_PACKAGE,
            "packed_package_entries": terminal["input_authority"]["entries"],
            "packed_package_bytes": terminal["input_authority"]["packed_bytes"],
        },
        "decoded_identity_confirmation": {
            "hard_gate_count": len(terminal["decoded_identities"]),
            "all_exact": True,
            "identities": terminal["decoded_identities"],
        },
        "oracle": {
            "recomputed_from_packed_package": True,
            "persisted_before_candidate": terminal["oracle"]["persisted_before_candidate"],
            "identity_before_candidate": terminal["oracle"]["identity_before_candidate"],
            "identity_after_candidate": terminal["oracle"]["identity_after_candidate"],
            "post_candidate_rehash": terminal["oracle"]["rehash"],
            "retention_descriptor": binding(ORACLE_DESCRIPTOR_PATH),
            "layer_2_output": oracle_artifacts["layer_2_output"],
            "layer_3_entry": oracle_artifacts["layer_3_entry"],
            "release_identity_gate": {
                "expected_sha256": EXPECTED_ORACLE_STATE,
                "actual_sha256": actual_oracle_state,
                "exact": False,
                "result": "FAIL_CLOSED",
            },
        },
        "candidate": {
            "binary_sha256": EXPECTED_CANDIDATE,
            "launched": True,
            "repeats_completed": candidate["repeats"],
            "repeat_determinism": candidate["deterministic"],
            "all_27_native_contractions_valid": True,
            "stage_hashes": candidate["stage_hashes"],
            "retention_descriptor": binding(CANDIDATE_DESCRIPTOR_PATH),
            "provisional_runtime_result": candidate["result"],
        },
        "numerical_surfaces": terminal["numerical_surfaces"],
        "numerical_result": {
            "all_eight_tier_b_surfaces_pass": all(item["pass"] for item in terminal["numerical_surfaces"]),
            "classification": "NUMERICALLY_QUALIFIED_BUT_TERMINALLY_REJECTED_BY_ORACLE_STATE_IDENTITY_GATE",
        },
        "runtime_accounting": terminal["runtime_accounting"],
        "lifecycle": terminal["success_path_lifecycle_reconciliation"],
        "evidence_validation": {
            "bound_runner_provisional_terminal_class": terminal["terminal_class"],
            "bound_runner_provisional_terminal": binding(PROVISIONAL_PATH),
            "release_identity_gate_applied": True,
            "result": "FAIL_CLOSED",
        },
        "state": {
            "authorized": True,
            "consumed": True,
            "executed": True,
            "checkpoint_accessed": False,
            "checkpoint_access_budget": 0,
            "ledger_before": LEDGER,
            "ledger_after": LEDGER,
            "automatic_retry": False,
            "automatic_m1f0_continuation": False,
        },
        "private_runtime_sources": {
            "execution_start": private_binding(execution_start_path, "f017-private/dprefix-real-3/execution-start.json"),
            "terminal": private_binding(terminal_path, "f017-private/dprefix-real-3/terminal-evidence.json"),
            "candidate_evidence": private_binding(candidate_path, "f017-private/dprefix-real-3/candidate-evidence.json"),
            "candidate_identity": private_binding(candidate_identity_path, "f017-private/dprefix-real-3/candidate-identity.json"),
            "material_manifest": private_binding(material_manifest_path, "f017-private/dprefix-real-3/material-manifest.json"),
            "oracle_manifest": private_binding(oracle_manifest_path, "f017-private/dprefix-real-3/oracle-primary/manifest.json"),
        },
        "real_payload_ledger": {
            **binding(payload_ledger_path),
            "before": LEDGER,
            "after": LEDGER,
            "byte_consistent": True,
        },
        "downstream": {
            "representative_m1f0": "NOT_AUTHORIZED_NOT_EXECUTED",
            "automatic_continuation": False,
            "replayed_oracle_state_admitted": False,
        },
    }
    write_json(RAW_PATH, raw)
    raw_sha = digest(RAW_PATH)

    attempt_v1 = load(attempt_v1_path)
    attempt = {
        "schema": "pulsarmlx.f017.dprefix-replay-attempt-ledger",
        "schema_version": "2.0.0",
        "append_only_predecessor": binding(attempt_v1_path),
        "real2_terminal": attempt_v1["real2_terminal"],
        "current_state": {
            "attempt_id": ATTEMPT,
            "authorized": True,
            "consumed": True,
            "executed": True,
            "checkpoint_accessed": False,
            "checkpoint_access_budget": 0,
            "terminal_class": "EVIDENCE_VALIDATION",
            "reason_code": "ORACLE_STATE_IDENTITY_MISMATCH",
            "evidence_path": str(RAW_PATH.relative_to(ROOT)),
            "evidence_sha256": raw_sha,
            "ledger_before": LEDGER,
            "ledger_after": LEDGER,
            "automatic_retry": False,
            "automatic_m1f0_continuation": False,
        },
        "history": [
            {
                "event": "REAL3_RELEASE_AUTHORIZATION",
                "release_head": EXECUTION_HEAD,
                "config_sha256": digest(config_path),
                "authorization_sha256": digest(authorization_path),
            },
            {
                "event": "REAL3_SINGLE_CHECKPOINT_FREE_REPLAY_TERMINAL_REJECTION",
                "evidence_sha256": raw_sha,
                "terminal_class": "EVIDENCE_VALIDATION",
                "reason_code": "ORACLE_STATE_IDENTITY_MISMATCH",
                "checkpoint_access": 0,
                "ledger_before": LEDGER,
                "ledger_after": LEDGER,
                "automatic_retry": False,
            },
        ],
        "ledger": LEDGER,
    }
    write_json(ATTEMPT_PATH, attempt)

    rows = "\n".join(
        f"| `{item['semantic_id']}` | `{item['max_absolute_error']}` | `{item['rmse']}` | `{item['cosine_similarity']}` | `{str(item['pass']).lower()}` |"
        for item in terminal["numerical_surfaces"]
    )
    review = f"""# PulsarMLX F017 DPREFIX-REAL-3 Rejected Evidence Review

`DPREFIX-REAL-3` executed exactly once from the immutable retained packed package with zero checkpoint reads, zero shard opens, and the real-payload ledger unchanged at `139`.

The candidate completed ten deterministic repeats. All 40 decoded identity gates, all eight Tier-B numerical rows, runtime accounting, lifecycle reconciliation, and oracle post-candidate rehash passed. The event is nevertheless terminally rejected: the freshly recomputed oracle layer-3 state is `{actual_oracle_state}`, while the released identity gate required `{EXPECTED_ORACLE_STATE}`.

| Surface | Max abs | RMSE | Cosine | Tier-B |
|---|---:|---:|---:|---|
{rows}

- Terminal class: `EVIDENCE_VALIDATION`
- Reason code: `ORACLE_STATE_IDENTITY_MISMATCH`
- Runtime-derived host copies: `{terminal['runtime_accounting']['actual_host_copy_count']}` / `{terminal['runtime_accounting']['actual_host_copy_bytes']}` bytes
- Lifecycle: `{terminal['success_path_lifecycle_reconciliation']['result']}`
- Raw evidence: `{RAW_PATH.relative_to(ROOT)}` / `{raw_sha}`
- Replay attempt ledger: `{ATTEMPT_PATH.relative_to(ROOT)}` / `{digest(ATTEMPT_PATH)}`
- Real-payload ledger: `{payload_ledger_path.relative_to(ROOT)}` / `{digest(payload_ledger_path)}` (`139 → 139`)
- Representative M1-F0: `NOT_AUTHORIZED_NOT_EXECUTED`

## Exact next action

Independent adversarial review of the terminal failure evidence. No retry.
"""
    REVIEW_PATH.write_text(review)
    return {
        "raw_evidence_sha256": raw_sha,
        "attempt_ledger_sha256": digest(ATTEMPT_PATH),
        "payload_ledger_sha256": digest(payload_ledger_path),
        "evidence_review_sha256": digest(REVIEW_PATH),
        "oracle_layer3_actual_sha256": actual_oracle_state,
    }


if __name__ == "__main__":
    print(json.dumps(bank(), sort_keys=True))
