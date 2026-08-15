#!/usr/bin/env python3
"""Checkpoint-free constructor/validator for DPREFIX-REAL-1's 40-read package.

The module has no checkpoint, shard-open, positional-read, decoder-execution,
or MLX entry point.  It converts the independently reviewed reuse blocker into
an explicit forty-fresh-read strategy while preserving that blocker as history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
from pathlib import Path
from typing import Any, Mapping

from scripts.research import f017_m1f_minus1_dense_prefix_prep as BASE


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
AUTHORIZATION_BASE_HEAD = "cefb7302bc6a7982cfa7ae670669a02cd6652304"
ATTEMPT_ID = "DPREFIX-REAL-1"

PREPARATION_V1 = CONTRACTS / "f017-m1f-minus1-preparation-v1.json"
PREPARATION_V1_SHA = "64fee7f240aac25fded225c81a9c7696d74ec47df67d86d48e3912ebc2e6ae11"
BLOCKER_EVIDENCE = EVIDENCE / "f017-dense-prefix-authorization-preparation-audit-v1.json"
BLOCKER_EVIDENCE_SHA = "63b9fa5c8d6960c787f9bebeb0c88db2e8796c944b3482cd588d2743da57137f"
LEDGER = EVIDENCE / "f017-real-payload-access-ledger-v1.json"
PROMPT = EVIDENCE / "f017-m1f-minus1-prompt-token-package-v1.json"
INVENTORY = EVIDENCE / "f017-m1f-minus1-exact-inventory-v1.json"
Q4_EVIDENCE = EVIDENCE / "f017-q4-k-real-byte-qualification-attempt-1-v1.json"
Q6_EVIDENCE = EVIDENCE / "f017-q6-k-real-byte-qualification-attempt-1-v1.json"
M1B_IDENTITY = EVIDENCE / "f017-m1-b-checkpoint-identity-v1.json"

Q4_EVIDENCE_SHA = "035ad4351406c24c65667a5322f1ffae71589f046a5ba3f591b8a4e3f6140994"
Q4_PACKED_SHA = "3e4c34141f918333883442b8ff44c78c9927295ae16378047a8a36edeb7ed5ef"
Q4_DECODED_SHA = "e2cff562131674156704ca21b2b6e850337c2e5d8948b4dcc9f14676ecf8f2c1"
Q6_EVIDENCE_SHA = "375e6b852733e8ac885d53c3814a03deb3a80e639bf61d427f1e49f1aae57086"
Q6_PACKED_SHA = "845b4fd6b5d290506e576ca5099336bae7d28f3ebfcec964ed2136c3ea4a8ede"
Q6_DECODED_SHA = "ff26151a7997379c1713b90852fdbfd8301b36d5d89a1c3bb623b9b8f273483a"

ORACLE_SHA = "0a54aa957e8b768108e4d8bc8c6e2a84cb48fbb3e0c93414c308112e88b3e816"
TIER_B_SHA = "9d1a6cc20ce8325fe8395334416f5ebcf980b72f02c6a0b44dc3240e0810024a"
NUMERICAL_SHA = "4a9f2f29689b8c20259ebadd46a0038008895ea173bf024b2ab805d35b7aa488"
DISPATCH_SHA = "d430b7dcc23d98d1b339315443f7868d6f8dd7e3e7c389ebae7d24ecae45e267"
RESIDENCY_SHA = "56ab1eae69b45f9ae97f98e1d36dfa124e080a6dc82573013cc57782bce1ac76"
HIDDEN_SCHEMA_SHA = "6610c3396fff1405131c843f8ba43bc06f5fde7f929ead7f2141e52cae07bf8f"
PROMPT_SHA = "c05ba1cba69535cd17daf9f4326e5e1db25ffafe504c53712aa548f251741dff"
INVENTORY_SHA = "eaf54506f5bd45ef41f223224096a253f6fa6c5e2ad3bf94971c18eb09f6b21b"
M1B_IDENTITY_SHA = "9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770"
ENVIRONMENT_MANIFEST_SHA = "33f57e945762e1b805ede4663e6ae19ee94240936c5e87940aba5e6e5face251"
TOKENIZER_IDENTITY = "glm52-gguf-tokenizer-v1:149e907384517d91d236a819835aa0dc97e6d4a3c512e6d5806d6b162ced1c6d"
MLX_NATIVE_SOURCE_SHA = "68cf2fddd8de5edd8ab3d926391772b2e2cedad8"
MLX_C_SOURCE_SHA = "0726ca922fc902c4c61ef9c27d94132be418e945"
MLX_NATIVE_LIBRARY_SHA = "6622caeb3e65a8310cf2290751ffbecf32135187aa75ef05f398916ac37bd9ed"
MLX_C_LIBRARY_SHA = "a060915d4b9accbf58e84d174029d5c51805891834494d50cf87a0d573222e62"

DECODER_LINEAGE = {
    "F32": {"path": "docs/architecture/reviews/evidence/f017-m1-c-real-tensor-v1.json", "sha256": "343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e", "status": "REAL_BYTE_QUALIFIED"},
    "Q8_0": {"path": "specs/017-rust-native-inference-runtime/contracts/m1d-q8-0-decoder-v1.json", "sha256": "aac49f628446cc41c295e690114632673aefc4e3f08663bd11216db9fd9cfbdd", "status": "REAL_BYTE_QUALIFIED"},
    "Q5_K": {"path": "specs/017-rust-native-inference-runtime/contracts/m1f0-q5-k-real-byte-exact-v1.json", "sha256": "06e9acf6838fbfe8bb11a653b631d126dadab37590f50cba4db9bdaf16656510", "status": "REAL_BYTE_QUALIFIED"},
    "Q4_K": {"path": "docs/architecture/reviews/evidence/f017-q4-k-real-byte-qualification-attempt-1-v1.json", "sha256": Q4_EVIDENCE_SHA, "format_contract_sha256": "bbdb296744910dbec5e95496d73df62b1e1b5cae4a9438b41de9962385399305", "status": "REAL_BYTE_QUALIFIED"},
    "Q6_K": {"path": "docs/architecture/reviews/evidence/f017-q6-k-real-byte-qualification-attempt-1-v1.json", "sha256": Q6_EVIDENCE_SHA, "format_contract_sha256": "9e5d15d87b88b9754a5f4b546a110dc1c0659e2c6f62683e12401b8bffb6ff95", "status": "REAL_BYTE_QUALIFIED"},
}

PREPARATION_V2_PATH = CONTRACTS / "f017-m1f-minus1-preparation-v2.json"
IDENTITY_PATH = CONTRACTS / "f017-dense-prefix-identity-confirmation-v1.json"
RETENTION_PATH = CONTRACTS / "f017-cross-event-retention-at-creation-v1.json"
LIFECYCLE_PATH = CONTRACTS / "f017-dense-prefix-lifecycle-v1.json"
HOST_PATH = CONTRACTS / "f017-dense-prefix-host-admission-v1.json"
EVIDENCE_SCHEMA_PATH = CONTRACTS / "f017-dense-prefix-evidence-v2.schema.json"
CROSS_ARTIFACT_PATH = CONTRACTS / "f017-dense-prefix-cross-artifact-v1.json"
ALLOWLIST_PATH = EVIDENCE / "f017-dense-prefix-40-read-allowlist-v1.json"
CONFIG_PATH = EVIDENCE / "f017-dense-prefix-execution-config-v2.json"
BINDING_PATH = EVIDENCE / "f017-dense-prefix-authorization-binding-v1.json"
ATTEMPT_PATH = EVIDENCE / "f017-dense-prefix-attempt-ledger-v1.json"
PREFLIGHT_PATH = EVIDENCE / "f017-dense-prefix-40-read-preflight-v1.json"
M1F0_HANDOFF_PATH = EVIDENCE / "f017-m1f0-representative-route-handoff-v2.json"
REVIEW_PATH = EVIDENCE / "f017-dense-prefix-40-read-internal-review-v1.json"

GENERATED_PATHS = (
    PREPARATION_V2_PATH, IDENTITY_PATH, RETENTION_PATH, LIFECYCLE_PATH,
    HOST_PATH, EVIDENCE_SCHEMA_PATH, CROSS_ARTIFACT_PATH, ALLOWLIST_PATH,
    CONFIG_PATH, BINDING_PATH, ATTEMPT_PATH, PREFLIGHT_PATH,
    M1F0_HANDOFF_PATH, REVIEW_PATH,
)

FAILURE_CLASSES = [
    "IDENTITY_BINDING", "HOST_ADMISSION", "MEMORY_ADMISSION", "ACCESS_BUDGET",
    "Q4_IDENTITY_CONFIRMATION", "Q6_IDENTITY_CONFIRMATION", "PACKED_PAYLOAD",
    "DECODER_IDENTITY", "ORACLE_CONSTRUCTION", "ORACLE_MUTATION", "NATIVE_RUNTIME",
    "FALLBACK_USED", "DISPATCH_RECONCILIATION", "NUMERICAL_QUALIFICATION",
    "REPEAT_DETERMINISM", "LIFECYCLE_RECONCILIATION", "RETENTION_FAILURE",
    "EVIDENCE_VALIDATION", "LEDGER_RECONCILIATION", "INFRASTRUCTURE",
]


class ContractError(ValueError):
    pass


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def canonical_sha(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _preparation_contract() -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.m1f-minus1-preparation-contract",
        "schema_version": "2.0.0",
        "contract_id": "f017-m1f-minus1-preparation-v2",
        "status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW",
        "predecessor": PREPARATION_V1.relative_to(ROOT).as_posix(),
        "predecessor_sha256": PREPARATION_V1_SHA,
        "preserved_blocker": {"path": BLOCKER_EVIDENCE.relative_to(ROOT).as_posix(), "sha256": BLOCKER_EVIDENCE_SHA, "result": "NOT_READY — QUALIFIED_PAYLOAD_REUSE_INVALID"},
        "strategy": "FORTY_FRESH_READS_WITH_Q4_Q6_IDENTITY_CONFIRMATION",
        "read_strategy": {"fresh_payload_reads": 40, "cross_event_decoded_reuse": 0},
        "semantic_delta": ["remove qualified-payload reuse", "promote Q4_K and Q6_K observations to hard identity-confirmation gates"],
        "unchanged": ["boundary", "prompt/input", "40-tensor inventory", "decoder lineages", "oracle", "Tier-B", "ten repeats", "dispatch", "lifecycle", "residency floor", "hidden-state retention", "routing v3", "no automatic M1-F0"],
        "boundary": "F017 M1-F(-1) REAL DENSE-PREFIX LAYER-3 ENTRY-STATE BOUNDARY",
        "ledger": {"before": 59, "after_all_40_reads": 99},
        "checkpoint_access_during_preparation": 0,
        "post_observation_retuning": "FORBIDDEN",
    }


def _allowlist() -> dict[str, Any]:
    inventory = BASE.reconstruct_inventory()
    entries = []
    for row in inventory["tensors"]:
        entry = {
            key: row[key]
            for key in (
                "ordinal", "name", "role", "layer", "shard_ordinal", "shard_basename",
                "offset", "packed_length", "packed_row_width", "quantization", "gguf_shape",
                "element_count", "decoded_f32_bytes", "catalog_entry_sha256",
                "map_contract_sha256", "metadata_identity_sha256",
            )
        }
        entry.update(
            decoded_shape=row["gguf_shape"],
            decoder_contract=DECODER_LINEAGE[row["quantization"]],
            allowed_read_count=1,
            event_observation="HARD_IDENTITY_CONFIRMATION" if row["name"] in ("token_embd.weight", "blk.0.ffn_down.weight") else "FIRST_OBSERVATION",
        )
        entries.append(entry)
    return {
        "schema": "pulsarmlx.f017.dense-prefix-40-read-allowlist",
        "schema_version": "1.0.0",
        "status": "FROZEN_NOT_EXECUTED",
        "source_inventory": {"path": INVENTORY.relative_to(ROOT).as_posix(), "sha256": INVENTORY_SHA},
        "tensor_count": len(entries),
        "packed_bytes": sum(row["packed_length"] for row in entries),
        "aggregate_decoded_f32_bytes": sum(row["decoded_f32_bytes"] for row in entries),
        "shard_opens": len({row["shard_ordinal"] for row in entries}),
        "quantization_counts": {family: sum(row["quantization"] == family for row in entries) for family in sorted(DECODER_LINEAGE)},
        "entries": entries,
        "forbidden_scope": ["wildcard", "layer-3 tensor", "router tensor", "expert tensor", "output head", "adjacent layer"],
        "checkpoint_access": 0,
    }


def _identity_confirmation() -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.dense-prefix-identity-confirmation",
        "schema_version": "1.0.0",
        "status": "FROZEN_PREOBSERVATION",
        "purpose": "confirm two earlier real observations during the authorized forty-read event; not a decoder requalification",
        "gates": [
            {"tensor_name": "token_embd.weight", "evidence_sha256": Q4_EVIDENCE_SHA, "packed_sha256": Q4_PACKED_SHA, "decoded_sha256": Q4_DECODED_SHA, "format_contract_sha256": DECODER_LINEAGE["Q4_K"]["format_contract_sha256"], "mismatch_terminal_class": "Q4_IDENTITY_CONFIRMATION", "mismatch_policy": "TERMINAL_FAIL_NO_RETRY", "new_decoder_qualification": False},
            {"tensor_name": "blk.0.ffn_down.weight", "evidence_sha256": Q6_EVIDENCE_SHA, "packed_sha256": Q6_PACKED_SHA, "decoded_sha256": Q6_DECODED_SHA, "format_contract_sha256": DECODER_LINEAGE["Q6_K"]["format_contract_sha256"], "mismatch_terminal_class": "Q6_IDENTITY_CONFIRMATION", "mismatch_policy": "TERMINAL_FAIL_NO_RETRY", "new_decoder_qualification": False},
        ],
        "required": ["exact catalog/map target", "exact packed SHA", "decode through accepted lineage", "exact decoded SHA"],
        "checkpoint_access": 0,
    }


def _retention_contract() -> dict[str, Any]:
    fields = ["private_package_identity", "manifest_sha256", "symbolic_package_relative_path", "creation_ordinal", "immutable", "read_only", "dtype", "shape", "count", "serialization", "content_sha256", "provenance", "source_event_evidence_sha256"]
    return {
        "schema": "pulsarmlx.f017.cross-event-retention-at-creation",
        "schema_version": "1.0.0",
        "status": "FROZEN_PROSPECTIVE_RULE",
        "rule": "reuse eligibility is declared and instantiated during the source event",
        "required_reusable_artifact_fields": fields,
        "missing_package_disposition": "CROSS_EVENT_REUSE_INELIGIBLE",
        "hash_only_reuse_eligibility": False,
        "creation_phases": [
            "create immutable canonical bytes and package identity during execution",
            "bank terminal evidence containing the hidden-state content identity",
            "finalize the public descriptor/manifest with committed evidence SHA and execution commit without mutating retained bytes",
        ],
        "pass_requires_final_manifest": True,
        "layer3_entry_state": {"retention_at_creation_required": True, "private_canonical_bytes_required": True, "dtype": "little_endian_f32", "shape": [6144], "count": 6144, "serialization": "canonical_little_endian_ieee754_binary32", "immutable": True, "read_only": True, "public_path_policy": "repository_relative_descriptor_only", "manifest_required": True},
        "checkpoint_access": 0,
    }


def _lifecycle_contract() -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.dense-prefix-lifecycle-contract",
        "schema_version": "1.0.0",
        "status": "FROZEN_PREOBSERVATION",
        "required_counters": ["managed_created", "managed_destroyed", "derived_created", "derived_destroyed", "callbacks", "contexts_created", "contexts_destroyed", "default_cpu_streams", "default_gpu_streams", "owned_streams_created", "owned_streams_destroyed", "registrations", "teardowns", "in_flight_work", "stale_generations", "singleton_live_state"],
        "pass_rule": "created/destroyed pairs reconcile; in_flight_work=0; stale_generations=0; singleton_live_state=0; all registrations torn down",
        "failure_cleanup_required": True,
        "retained_private_evidence_excluded_from_runtime_live_ownership": True,
        "checkpoint_access": 0,
    }


def _host_admission(allowlist: Mapping[str, Any]) -> dict[str, Any]:
    packed = allowlist["packed_bytes"]
    decoded = allowlist["aggregate_decoded_f32_bytes"]
    reserve = 4 * 1024**3
    required = math.ceil(1.25 * (packed + decoded + decoded + reserve) / 1024**3) * 1024**3
    return {
        "schema": "pulsarmlx.f017.dense-prefix-host-admission",
        "schema_version": "1.0.0",
        "status": "FROZEN_NONCONSUMING",
        "predecessor_residency_sha256": RESIDENCY_SHA,
        "reviewed_environment": {
            "identity_evidence_sha256": M1B_IDENTITY_SHA,
            "environment_manifest_sha256": ENVIRONMENT_MANIFEST_SHA,
            "architecture": "arm64",
            "macos_version": "26.0",
            "macos_build": "25A354",
            "sdk_version": "26.2",
            "xcode_version": "26.3",
            "mlx_native_source_sha": MLX_NATIVE_SOURCE_SHA,
            "mlx_c_source_sha": MLX_C_SOURCE_SHA,
            "loaded_library_sha256": {
                "libmlx.dylib": MLX_NATIVE_LIBRARY_SHA,
                "libmlxc.dylib": MLX_C_LIBRARY_SHA,
            },
        },
        "read_strategy": "40 fresh packed reads with event-local oracle decode and separately identifiable candidate import/copy",
        "liveness": {"packed_inventory_bytes": packed, "decoded_oracle_upper_bound_bytes": decoded, "decoded_equivalent_candidate_upper_bound_bytes": decoded, "fixed_runtime_reserve_bytes": reserve, "engineering_multiplier": 1.25, "required_available_memory_bytes": required, "required_available_memory_gib": required // 1024**3},
        "required": ["arm64", "reviewed macOS/SDK/runtime", "exact native MLX libraries", "clean worktree", "local/remote parity", "real-payload ledger=59", "available memory at least floor", "acceptable memory pressure", "acceptable thermal state", "no competing inference", "clean context/stream/singleton state"],
        "failure_class": "HOST_ADMISSION_OR_MEMORY_ADMISSION",
        "consumes_attempt": False,
        "checkpoint_access": 0,
    }


def _evidence_schema() -> dict[str, Any]:
    strict_object = {"type": "object", "additionalProperties": False}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/MahdiHedhli/PulsarMLX/specs/017-rust-native-inference-runtime/contracts/f017-dense-prefix-evidence-v2.schema.json",
        "title": "F017 DPREFIX-REAL-1 terminal evidence",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema", "schema_version", "identity", "access", "identity_confirmations", "oracle", "candidate", "retention", "state", "result"],
        "properties": {
            "schema": {"const": "pulsarmlx.f017.dense-prefix-real-evidence"},
            "schema_version": {"const": "2.0.0"},
            "identity": {**strict_object, "required": ["execution_head", "tooling_sha256", "runtime_sha256", "execution_config_sha256", "authorization_binding_sha256", "checkpoint_set_sha256", "catalog_sha256", "tensor_map_sha256", "prompt_package_sha256", "allowlist_sha256"], "properties": {name: {"type": "string", "minLength": 1} for name in ["execution_head", "tooling_sha256", "runtime_sha256", "execution_config_sha256", "authorization_binding_sha256", "checkpoint_set_sha256", "catalog_sha256", "tensor_map_sha256", "prompt_package_sha256", "allowlist_sha256"]}},
            "access": {**strict_object, "required": ["shard_opens", "positional_reads", "payload_count", "packed_bytes", "entries"], "properties": {"shard_opens": {"const": 1}, "positional_reads": {"type": "integer", "minimum": 0, "maximum": 40}, "payload_count": {"type": "integer", "minimum": 0, "maximum": 40}, "packed_bytes": {"type": "integer", "minimum": 0, "maximum": 1431263232}, "entries": {"type": "array", "maxItems": 40, "items": {"type": "object"}}}},
            "identity_confirmations": {"type": "array", "minItems": 2, "maxItems": 2, "items": {**strict_object, "required": ["tensor_name", "expected_packed_sha256", "actual_packed_sha256", "expected_decoded_sha256", "actual_decoded_sha256", "matched"], "properties": {"tensor_name": {"enum": ["token_embd.weight", "blk.0.ffn_down.weight"]}, "expected_packed_sha256": {"type": "string", "minLength": 64, "maxLength": 64}, "actual_packed_sha256": {"type": "string", "minLength": 64, "maxLength": 64}, "expected_decoded_sha256": {"type": "string", "minLength": 64, "maxLength": 64}, "actual_decoded_sha256": {"type": "string", "minLength": 64, "maxLength": 64}, "matched": {"type": "boolean"}}}},
            "oracle": {**strict_object, "required": ["package_sha256", "finalized_before_candidate", "stage_hashes", "post_candidate_rehash_sha256", "unchanged"], "properties": {"package_sha256": {"const": ORACLE_SHA}, "finalized_before_candidate": {"const": True}, "stage_hashes": {"type": "object"}, "post_candidate_rehash_sha256": {"type": "string", "minLength": 64, "maxLength": 64}, "unchanged": {"type": "boolean"}}},
            "candidate": {**strict_object, "required": ["repeat_count", "repeats", "numerical_surfaces", "dispatch", "lifecycle"], "properties": {"repeat_count": {"const": 10}, "repeats": {"type": "array", "minItems": 10, "maxItems": 10}, "numerical_surfaces": {"type": "array", "minItems": 5}, "dispatch": {"type": "object"}, "lifecycle": {"type": "object"}}},
            "retention": {**strict_object, "required": ["private_package_identity", "symbolic_package_relative_path", "hidden_state_sha256", "dtype", "shape", "count", "serialization", "immutable", "read_only", "canonical_bytes_created"], "properties": {"private_package_identity": {"type": "string", "minLength": 1}, "symbolic_package_relative_path": {"type": "string", "pattern": "^(?!/)(?!.*\\.\\.).+$"}, "hidden_state_sha256": {"type": "string", "minLength": 64, "maxLength": 64}, "dtype": {"const": "f32"}, "shape": {"const": [6144]}, "count": {"const": 6144}, "serialization": {"const": "canonical_little_endian_ieee754_binary32"}, "immutable": {"const": True}, "read_only": {"const": True}, "canonical_bytes_created": {"const": True}}},
            "state": {**strict_object, "required": ["attempt_id", "authorized", "consumed", "executed", "checkpoint_accessed", "payload_count", "ledger_before", "ledger_after", "automatic_retry", "automatic_m1f0_continuation"], "properties": {"attempt_id": {"const": ATTEMPT_ID}, "authorized": {"const": True}, "consumed": {"type": "boolean"}, "executed": {"type": "boolean"}, "checkpoint_accessed": {"type": "boolean"}, "payload_count": {"type": "integer", "minimum": 0, "maximum": 40}, "ledger_before": {"const": 59}, "ledger_after": {"type": "integer", "minimum": 59, "maximum": 99}, "automatic_retry": {"const": False}, "automatic_m1f0_continuation": {"const": False}}},
            "result": {**strict_object, "required": ["terminal_class", "pass", "first_failure"], "properties": {"terminal_class": {"enum": FAILURE_CLASSES + ["PASS"]}, "pass": {"type": "boolean"}, "first_failure": {"type": ["object", "null"]}}},
            "analytical_extensions": {"type": "object"},
        },
        "$comment": "PASS is derived only after 40-entry access reconciliation, both hard identity confirmations, oracle-before-candidate rehash, ten repeat/stage surfaces, lifecycle cleanup, retained bytes+manifest, and cross-artifact reconciliation.",
    }


def _cross_artifact_contract() -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.dense-prefix-cross-artifact-consistency",
        "schema_version": "1.0.0",
        "status": "FROZEN_PREOBSERVATION",
        "artifacts": ["execution-start record", "terminal evidence", "attempt ledger", "real-payload ledger", "layer-3 retention manifest"],
        "required_equal": ["attempt_id", "consumed", "executed", "checkpoint_accessed", "payload_count", "ledger_before", "ledger_after", "terminal_class", "evidence_sha256"],
        "conditional_required_equal": ["hidden_state_sha256 when state created"],
        "partial_read_ledger_policy": "ledger_after = 59 + actual_payload_reads; never assume full 40",
        "stale_attempt_ledger_disposition": "EVIDENCE_VALIDATION",
        "checkpoint_access": 0,
    }


def _m1f0_handoff(retention_sha: str) -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.m1f0-representative-route-handoff",
        "schema_version": "2.0.0",
        "status": "PREPARED_NOT_AUTHORIZED_NOT_EXECUTED",
        "source_attempt": ATTEMPT_ID,
        "required_source": {"hidden_state_sha256": None, "private_package_identity": None, "manifest_sha256": None, "dense_prefix_evidence_sha256": None, "prompt_package_sha256": PROMPT_SHA, "checkpoint_set_sha256": load_json(Q6_EVIDENCE)["identity"]["checkpoint_set_sha256"], "retention_contract_sha256": retention_sha},
        "forbidden": ["prefix recomputation", "approximate state", "alternate prompt", "alternate token", "state substitution", "automatic authorization"],
        "automatic_continuation": False,
        "checkpoint_access": 0,
    }


def _execution_config(refs: Mapping[str, str]) -> dict[str, Any]:
    q6 = load_json(Q6_EVIDENCE)
    return {
        "schema": "pulsarmlx.f017.dense-prefix-execution-config",
        "schema_version": "2.0.0",
        "status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW",
        "execution_authorized": True,
        "attempt_id": ATTEMPT_ID,
        "authorization_base_head": AUTHORIZATION_BASE_HEAD,
        "preparation_contract_v2_sha256": refs["preparation"],
        "preparation_tool_sha256": file_sha256(Path(__file__)),
        "reviewed_environment_identity_sha256": M1B_IDENTITY_SHA,
        "environment_manifest_sha256": ENVIRONMENT_MANIFEST_SHA,
        "mlx_native_source_sha": MLX_NATIVE_SOURCE_SHA,
        "mlx_c_source_sha": MLX_C_SOURCE_SHA,
        "loaded_library_sha256": {"libmlx.dylib": MLX_NATIVE_LIBRARY_SHA, "libmlxc.dylib": MLX_C_LIBRARY_SHA},
        "checkpoint_set_sha256": q6["identity"]["checkpoint_set_sha256"],
        "catalog_sha256": q6["identity"]["catalog_sha256"],
        "tensor_map_sha256": q6["identity"]["tensor_map_sha256"],
        "prompt_package_sha256": PROMPT_SHA,
        "tokenizer_identity": TOKENIZER_IDENTITY,
        "allowlist_sha256": refs["allowlist"],
        "identity_confirmation_sha256": refs["identity_confirmation"],
        "decoder_contracts": DECODER_LINEAGE,
        "oracle_sha256": ORACLE_SHA,
        "oracle_finalized_before_candidate": True,
        "post_candidate_oracle_rehash_required": True,
        "tier_b_sha256": TIER_B_SHA,
        "numerical_repeat_sha256": NUMERICAL_SHA,
        "repeat_count": 10,
        "dispatch_sha256": DISPATCH_SHA,
        "lifecycle_sha256": refs["lifecycle"],
        "retention_at_creation_sha256": refs["retention"],
        "hidden_state_retention_schema_sha256": HIDDEN_SCHEMA_SHA,
        "host_admission_sha256": refs["host"],
        "evidence_schema_sha256": refs["evidence_schema"],
        "cross_artifact_sha256": refs["cross_artifact"],
        "access_budget": {"shard_opens": 1, "positional_reads": 40, "payloads": 40, "packed_bytes": 1_431_263_232},
        "ledger_before": 59,
        "expected_ledger_after": 99,
        "consumption_boundary": "immediately before first authorized positional checkpoint read after preflight/admission",
        "automatic_retry": False,
        "automatic_m1f0_continuation": False,
        "cli_tensor_override": False,
        "environment_target_override": False,
        "failure_classes": FAILURE_CLASSES,
        "evidence_destination": "docs/architecture/reviews/evidence/f017-dense-prefix-real-attempt-1-v1.json",
        "checkpoint_access_during_preparation": 0,
    }


def _authorization_binding(config_sha: str, refs: Mapping[str, str]) -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.dense-prefix-authorization-binding",
        "schema_version": "1.0.0",
        "status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW",
        "execution_authorized": True,
        "attempt_id": ATTEMPT_ID,
        "authorization_base_head": AUTHORIZATION_BASE_HEAD,
        "preparation_contract_v2_sha256": refs["preparation"],
        "preparation_tool_sha256": file_sha256(Path(__file__)),
        "execution_config_sha256": config_sha,
        "allowlist_sha256": refs["allowlist"],
        "identity_confirmation_sha256": refs["identity_confirmation"],
        "retention_at_creation_sha256": refs["retention"],
        "host_admission_sha256": refs["host"],
        "oracle_sha256": ORACLE_SHA,
        "tier_b_sha256": TIER_B_SHA,
        "numerical_repeat_sha256": NUMERICAL_SHA,
        "ledger_before": 59,
        "expected_ledger_after": 99,
        "review_releases_execution_without_mutating_authorization": True,
        "automatic_retry": False,
        "automatic_m1f0_continuation": False,
        "checkpoint_access": 0,
    }


def _attempt_ledger(config_sha: str, binding_sha: str, allowlist_sha: str) -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.dense-prefix-attempt-ledger",
        "schema_version": "1.0.0",
        "append_only": True,
        "events": [{"attempt_id": ATTEMPT_ID, "gate": "M1-F(-1) REAL DENSE PREFIX", "authorized": True, "consumed": False, "executed": False, "checkpoint_accessed": False, "authorization_base_head": AUTHORIZATION_BASE_HEAD, "execution_config_sha256": config_sha, "authorization_binding_sha256": binding_sha, "allowlist_sha256": allowlist_sha, "ledger_before": 59, "expected_success_ledger_after": 99, "actual_payload_reads": 0, "automatic_retry": False, "automatic_m1f0_continuation": False, "status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW"}],
        "checkpoint_access": 0,
    }


def build_package() -> dict[str, Any]:
    prep = _preparation_contract()
    allowlist = _allowlist()
    identity = _identity_confirmation()
    retention = _retention_contract()
    lifecycle = _lifecycle_contract()
    host = _host_admission(allowlist)
    evidence_schema = _evidence_schema()
    cross = _cross_artifact_contract()
    refs = {"preparation": canonical_sha(prep), "allowlist": canonical_sha(allowlist), "identity_confirmation": canonical_sha(identity), "retention": canonical_sha(retention), "lifecycle": canonical_sha(lifecycle), "host": canonical_sha(host), "evidence_schema": canonical_sha(evidence_schema), "cross_artifact": canonical_sha(cross)}
    config = _execution_config(refs)
    config_sha = canonical_sha(config)
    binding = _authorization_binding(config_sha, refs)
    binding_sha = canonical_sha(binding)
    attempt = _attempt_ledger(config_sha, binding_sha, refs["allowlist"])
    handoff = _m1f0_handoff(refs["retention"])
    preflight = {"schema": "pulsarmlx.f017.dense-prefix-preflight", "schema_version": "1.0.0", "result": "READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE", "attempt_id": ATTEMPT_ID, "execution_config_sha256": config_sha, "authorization_binding_sha256": binding_sha, "attempt_ledger_sha256": canonical_sha(attempt), "checkpoint_reads": 0, "ledger": 59, "host_observation_deferred_to_execution_preflight": True}
    review = {"schema": "pulsarmlx.f017.dense-prefix-40-read-internal-review", "schema_version": "1.0.0", "verdict": "GO FOR DENSE-PREFIX 40-READ AUTHORIZATION ADVERSARIAL REVIEW", "reuse_blocker_retired_not_bypassed": True, "quantization_families_real_byte_ready": ["F32", "Q8_0", "Q5_K", "Q4_K", "Q6_K"], "inventory_exact": True, "q4_q6_hard_gates": True, "ledger_59_to_99": True, "retention_at_creation_enforced": True, "layer3_state_reusable_by_design": True, "oracle_independent": True, "candidate_oracle_isolated": True, "tier_b_unchanged": True, "memory_model_recomputed_for_40_fresh_reads": True, "memory_floor_gib": 27, "lifecycle_accounting_complete": True, "automatic_downstream_chain": False, "real_checkpoint_access": 0, "ledger": 59}
    return {"preparation_contract": prep, "identity_confirmation": identity, "retention_contract": retention, "lifecycle": lifecycle, "host_admission": host, "evidence_schema": evidence_schema, "cross_artifact_contract": cross, "allowlist": allowlist, "execution_config": config, "authorization_binding": binding, "attempt_ledger": attempt, "preflight": preflight, "m1f0_handoff": handoff, "internal_review": review}


def validate_partial_read_ledger(before: int, actual_reads: int, after: int) -> None:
    require(before == 59, "ledger before")
    require(0 <= actual_reads <= 40, "actual read range")
    require(after == before + actual_reads, "partial-read ledger arithmetic")


def validate_package(package: Mapping[str, Any]) -> None:
    expected = build_package()
    for key in expected:
        require(package.get(key) == expected[key], f"{key} drift")
    allowlist = package["allowlist"]
    require(allowlist["tensor_count"] == len(allowlist["entries"]) == 40, "40-entry allowlist")
    require(len({row["name"] for row in allowlist["entries"]}) == 40, "duplicate tensor")
    require(sum(row["packed_length"] for row in allowlist["entries"]) == 1_431_263_232, "packed arithmetic")
    require(all(row["allowed_read_count"] == 1 for row in allowlist["entries"]), "read count")
    require(not any(row["layer"] == 3 or "router" in row["role"] or "expert" in row["role"] for row in allowlist["entries"]), "scope leak")
    require(package["host_admission"]["liveness"]["required_available_memory_gib"] == 27, "memory floor")
    require(package["host_admission"]["reviewed_environment"]["loaded_library_sha256"] == {"libmlx.dylib": MLX_NATIVE_LIBRARY_SHA, "libmlxc.dylib": MLX_C_LIBRARY_SHA}, "native library identity")
    require(package["execution_config"]["tokenizer_identity"] == TOKENIZER_IDENTITY, "tokenizer identity")
    require(package["execution_config"]["repeat_count"] == 10, "ten repeats")
    require(package["execution_config"]["automatic_retry"] is False and package["execution_config"]["automatic_m1f0_continuation"] is False, "automatic continuation")
    validate_partial_read_ledger(59, 40, 99)


ARTIFACT_KEYS = {
    PREPARATION_V2_PATH: "preparation_contract", IDENTITY_PATH: "identity_confirmation",
    RETENTION_PATH: "retention_contract", LIFECYCLE_PATH: "lifecycle", HOST_PATH: "host_admission",
    EVIDENCE_SCHEMA_PATH: "evidence_schema", CROSS_ARTIFACT_PATH: "cross_artifact_contract",
    ALLOWLIST_PATH: "allowlist", CONFIG_PATH: "execution_config", BINDING_PATH: "authorization_binding",
    ATTEMPT_PATH: "attempt_ledger", PREFLIGHT_PATH: "preflight", M1F0_HANDOFF_PATH: "m1f0_handoff",
    REVIEW_PATH: "internal_review",
}


def validate_banked_artifacts(package: Mapping[str, Any] | None = None) -> None:
    package = build_package() if package is None else package
    validate_package(package)
    for path, key in ARTIFACT_KEYS.items():
        require(path.is_file() and not path.is_symlink(), f"missing banked {path.name}")
        require(path.read_bytes() == canonical_bytes(package[key]), f"banked artifact drift {path.name}")


def canonical_preflight(*, check_git: bool = True, check_host: bool = True) -> str:
    package = build_package()
    validate_banked_artifacts(package)
    require(load_json(LEDGER)["cumulative_tensor_payloads"] == 59, "real-payload ledger")
    if check_git:
        local = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        remote = subprocess.check_output(["git", "rev-parse", "origin/feat/017-real-checkpoint-runner"], cwd=ROOT, text=True).strip()
        require(local == remote, "local/remote parity")
        require(not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip(), "worktree clean")
        require(subprocess.run(["git", "merge-base", "--is-ancestor", AUTHORIZATION_BASE_HEAD, local], cwd=ROOT, check=False).returncode == 0, "authorization ancestry")
    if check_host:
        require(platform.machine() == "arm64", "host architecture")
    return "READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", choices=[path.name for path in GENERATED_PATHS])
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--skip-git", action="store_true")
    parser.add_argument("--skip-host", action="store_true")
    args = parser.parse_args()
    package = build_package()
    validate_package(package)
    if args.dump:
        path = next(path for path in GENERATED_PATHS if path.name == args.dump)
        print(canonical_bytes(package[ARTIFACT_KEYS[path]]).decode(), end="")
    elif args.preflight:
        print(canonical_preflight(check_git=not args.skip_git, check_host=not args.skip_host))
    else:
        print(json.dumps({"status": package["execution_config"]["status"], "checkpoint_reads": 0, "ledger": 59}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
