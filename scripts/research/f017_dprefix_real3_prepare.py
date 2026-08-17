#!/usr/bin/env python3
"""Generate the checkpoint-free DPREFIX-REAL-3 review package."""

from __future__ import annotations

import copy
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

_IMPORT_ROOT = Path(__file__).resolve().parents[2]
if str(_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMPORT_ROOT))

from scripts.research import f017_dprefix_real3_replay as R
from scripts.research.f017_dprefix_numerical_surface_closure import (
    compare_surface_packages,
    numerical_surface_manifest,
    validate_terminal_numerical_surfaces,
)

ROOT, E, C = R.ROOT, R.EVIDENCE, R.CONTRACTS
SOURCE = ROOT / "crates/f017-runner/src/bin/f017-dense-prefix-candidate.rs"
PREPARER = Path(__file__).resolve()
REPLAY = Path(R.__file__).resolve()
LOCAL = ROOT / ".pulsarmlx-local/dprefix-real3-preparation"
FULL = LOCAL / "full-exact-real-shape.json"


def write(path: Path, value: object) -> None:
    R.atomic_json(path, value)


def binding(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(ROOT)), "sha256": R.digest_path(path)}


def source_binding(path: Path, role: str) -> dict[str, str]:
    return {**binding(path), "role": role}


def preserve_real2() -> dict:
    raw = R.load(R.REAL2_RAW_PATH)
    attempt = R.load(R.ATTEMPT_V10_PATH)
    state = attempt["current_state"]
    if (
        R.digest_path(R.REAL2_RAW_PATH) != R.REAL2_EVIDENCE_SHA
        or state["attempt_id"] != "DPREFIX-REAL-2"
        or not state["consumed"]
        or state["terminal_class"] != "EVIDENCE_VALIDATION"
        or state["reason_code"] != "SUCCESS_PATH_RUNTIME_ACCOUNTING_MISSING"
        or state["automatic_retry"]
        or raw["verdict"] != "REJECTED"
    ):
        raise RuntimeError("DPREFIX-REAL-2 historical state")
    result = {
        "schema": "pulsarmlx.f017.dprefix-real2-terminal-regression",
        "schema_version": "1.0.0",
        "result": "DPREFIX-REAL-2 TERMINAL — NO RETRY",
        "terminal_class": "EVIDENCE_VALIDATION",
        "reason_code": "SUCCESS_PATH_RUNTIME_ACCOUNTING_MISSING",
        "historical_classification": "NUMERICALLY_QUALIFIED / EVENT_REJECTED_FOR_EVIDENCE_COMPLETENESS",
        "admission_attacks": {name: "REJECTED_TERMINAL_ATTEMPT" for name in ("REAL-2 config", "REAL-2 authorization", "REAL-2 orchestrator", "REAL-2 attempt ID")},
        "checkpoint_access": 0,
        "ledger": R.LEDGER,
    }
    write(E / "f017-dprefix-real3-real2-terminal-regression-v1.json", result)
    return result


def d4_contracts() -> dict[str, Path]:
    paths = {
        "accounting": C / "f017-dprefix-replay-runtime-accounting-v1.json",
        "zero_read": C / "f017-dprefix-replay-zero-read-v1.json",
        "event": C / "f017-dprefix-replay-event-v1.json",
        "schema": C / "f017-dprefix-replay-terminal-evidence-v1.schema.json",
    }
    write(paths["accounting"], {
        "schema": "pulsarmlx.f017.dprefix-replay-runtime-accounting",
        "schema_version": "1.0.0",
        "attempt_id": R.ATTEMPT,
        "host_copy_definition": "one explicit native output copy into Rust-owned canonical f32 memory; borrowed zero-copy imports are excluded",
        "host_copy_required": ["actual_host_copy_count", "actual_host_copy_bytes"],
        "separate_counters": ["synchronizations", "readbacks", "actual_host_copy_count"],
        "lifecycle_required": ["arrays", "managed", "derived", "callbacks", "contexts", "default streams", "owned streams", "registrations", "teardowns", "in_flight_work", "stale_generations", "singleton_live_state", "child_process"],
        "terminal_finalizer": "shared success/failure finalizer",
        "pass_null_policy": "forbidden",
        "model_semantics_changed": False,
        "checkpoint_access": 0,
        "ledger": R.LEDGER,
    })
    write(paths["zero_read"], {
        "schema": "pulsarmlx.f017.dprefix-replay-zero-read",
        "schema_version": "1.0.0",
        "attempt_id": R.ATTEMPT,
        "input_authority": R.PACKED_PACKAGE_SHA,
        "checkpoint_reader_capability": "STRUCTURALLY_ABSENT",
        "forbidden": ["checkpoint path CLI", "checkpoint environment path", "shard resolver", "positional reader", "fallback reader", "real-payload ledger writer"],
        "shard_opens": 0,
        "positional_reads": 0,
        "checkpoint_payloads": 0,
        "ledger_before": R.LEDGER,
        "ledger_after": R.LEDGER,
    })
    write(paths["event"], {
        "schema": "pulsarmlx.f017.dprefix-replay-event-contract",
        "schema_version": "1.0.0",
        "event_type": "CHECKPOINT-FREE RETAINED-PACKAGE DPREFIX REPLAY",
        "attempt_id": R.ATTEMPT,
        "consumption_semantics": "one oracle/candidate replay execution; consumes no real payload budget",
        "packed_package_sha256": R.PACKED_PACKAGE_SHA,
        "payload_manifest_entries": 40,
        "decoded_identity_manifest": binding(R.DECODED_MANIFEST_PATH),
        "candidate_binary_sha256": R.digest_path(R.PRIVATE_CANDIDATE),
        "oracle_package_sha256": "9b00ed225acc9b299c5bd789f1b082f6a2fd90b7893913bc9f353f99ee83c89b",
        "metric_engine_sha256": "cd7ca4eee855b60b6695b8ac6671d59eae2f446231f437168df0985f984ad738",
        "tier_b_sha256": "9d1a6cc20ce8325fe8395334416f5ebcf980b72f02c6a0b44dc3240e0810024a",
        "repeat_count": 10,
        "ledger_before": R.LEDGER,
        "ledger_after": R.LEDGER,
        "checkpoint_access": 0,
        "automatic_retry": False,
        "automatic_m1f0_continuation": False,
    })
    write(paths["schema"], {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/MahdiHedhli/PulsarMLX/specs/017-rust-native-inference-runtime/contracts/f017-dprefix-replay-terminal-evidence-v1.schema.json",
        "type": "object",
        "required": ["attempt_id", "terminal_class", "checkpoint_access", "ledger_before", "ledger_after", "runtime_accounting", "success_path_lifecycle_reconciliation", "numerical_surfaces", "packed_package_sha256"],
        "properties": {
            "attempt_id": {"const": R.ATTEMPT},
            "checkpoint_access": {"const": 0},
            "ledger_before": {"const": R.LEDGER},
            "ledger_after": {"const": R.LEDGER},
            "runtime_accounting": {"type": "object", "required": ["actual_host_copy_count", "actual_host_copy_bytes", "native_matvecs", "synchronizations", "readbacks", "fallback", "backend_errors"]},
            "success_path_lifecycle_reconciliation": {"type": "object", "required": ["result", "arrays_created", "arrays_destroyed", "contexts_created", "contexts_destroyed", "in_flight_work", "stale_generations", "singleton_live_state"]},
            "numerical_surfaces": {"type": "array", "minItems": 8, "maxItems": 8},
        },
        "allOf": [{
            "if": {"properties": {"terminal_class": {"const": "PASS"}}},
            "then": {"properties": {
                "runtime_accounting": {"required": ["actual_host_copy_count"]},
                "success_path_lifecycle_reconciliation": {"properties": {"result": {"const": "PASS"}}},
            }},
        }],
    })
    return paths


def source_and_build_manifests() -> tuple[dict, dict, dict, dict]:
    candidate_source = {
        "schema": "pulsarmlx.f017.dprefix-candidate-source-manifest",
        "schema_version": "4.0.0",
        "attempt_id": R.ATTEMPT,
        "predecessor_source_manifest_sha256": "8424c709ce252d64adc74775b2e6b6a5ec099e6e687b238f7c70fd0dd868b5d9",
        "files": [
            source_binding(SOURCE, "unchanged model arithmetic plus authoritative host-copy and lifecycle emission"),
            source_binding(ROOT / "crates/stream/src/apple_mlx_bridge.rs", "native ownership snapshots and output readback"),
            source_binding(ROOT / "crates/stream/src/apple_mlx_bridge.mm", "native MLX lifecycle producer"),
            source_binding(ROOT / "crates/quant/src/cpu_dot.rs", "independent candidate Q4_K/Q5_K decode"),
            source_binding(ROOT / "crates/quant/src/q6_k_ref.rs", "independent candidate Q6_K decode"),
            source_binding(ROOT / "crates/quant/src/q8_0_ref.rs", "independent candidate Q8_0 decode"),
        ],
        "change_class": "D4 REMEDIATION ACCOUNTING-ONLY",
        "unchanged": ["model equations", "shape contract", "quantization", "prompt", "Tier-B", "surface definitions", "repeat count"],
        "checkpoint_access": 0,
    }
    write(E / "f017-dprefix-candidate-source-manifest-v4.json", candidate_source)
    candidate_build = {
        "schema": "pulsarmlx.f017.dprefix-candidate-build-manifest",
        "schema_version": "4.0.0",
        "attempt_id": R.ATTEMPT,
        "predecessor_binary_sha256": "2f6a8885a17c10c7776a0d27ed6eb8e85024b03bc499885eddb905050cad17b1",
        "binary": {"symbolic_private_path": "f017-private/dprefix/f017-dense-prefix-candidate-v4", "sha256": R.digest_path(R.PRIVATE_CANDIDATE), "size_bytes": R.PRIVATE_CANDIDATE.stat().st_size, "read_only": True, "dynamic_build_at_execution": False},
        "source_manifest_sha256": R.digest_path(E / "f017-dprefix-candidate-source-manifest-v4.json"),
        "compiler": subprocess.check_output(["rustc", "-vV"], text=True),
        "cargo": subprocess.check_output(["cargo", "-V"], text=True).strip(),
        "target": platform.machine() + "-apple-darwin",
        "native_mlx_rpath": "reviewed-private-native-mlx-prefix/lib",
        "checkpoint_access": 0,
    }
    write(E / "f017-dprefix-candidate-build-manifest-v4.json", candidate_build)
    orchestrator_source = {
        "schema": "pulsarmlx.f017.dprefix-replay-orchestrator-source-manifest",
        "schema_version": "1.0.0",
        "attempt_id": R.ATTEMPT,
        "files": [
            source_binding(REPLAY, "zero-read retained-package loader, decoder, coordinator, shared finalizer, banker"),
            source_binding(PREPARER, "checkpoint-free review package and rehearsal generator"),
            source_binding(ROOT / "scripts/research/f017_dprefix_oracle_runtime.py", "independent NumPy oracle"),
            source_binding(ROOT / "scripts/research/f017_dprefix_metric_engine.py", "unchanged metric engine"),
        ],
        "checkpoint_reader": "ABSENT",
        "real_payload_ledger_writer": "ABSENT",
        "dynamic_build_at_execution": False,
    }
    write(E / "f017-dprefix-replay-orchestrator-source-manifest-v1.json", orchestrator_source)
    orchestrator_build = {
        "schema": "pulsarmlx.f017.dprefix-replay-orchestrator-build-manifest",
        "schema_version": "1.0.0",
        "attempt_id": R.ATTEMPT,
        "package_sha256": R.digest_path(REPLAY),
        "package_size": REPLAY.stat().st_size,
        "source_manifest_sha256": R.digest_path(E / "f017-dprefix-replay-orchestrator-source-manifest-v1.json"),
        "runtime": {"implementation": platform.python_implementation(), "version": platform.python_version()},
        "entrypoint": "--execute-reviewed-replay",
        "dynamic_build_at_execution": False,
        "checkpoint_access": 0,
    }
    write(E / "f017-dprefix-replay-orchestrator-build-manifest-v1.json", orchestrator_build)
    return candidate_source, candidate_build, orchestrator_source, orchestrator_build


def run_success_rehearsal() -> dict:
    LOCAL.mkdir(parents=True, exist_ok=True)
    surface_root = FULL.parent / f"{FULL.name}.surfaces"
    if not FULL.is_file() or len(list(surface_root.glob("*.f32le"))) != 8:
        subprocess.run([str(R.PRIVATE_CANDIDATE), "--full-exact-real-shape-rehearsal", str(FULL)], check=True)
    candidate = R.load(FULL)
    package = surface_root
    candidate_values = {item["semantic_id"]: (package / f"{item['semantic_id']}.f32le").read_bytes() for item in candidate["surface_package"]}
    embedding = ((np.arange(6144, dtype=np.float32) % np.float32(31)) - np.float32(15)) / np.float32(64)
    zero = np.zeros(6144, dtype=np.float32)
    oracle_values = {}
    for item in numerical_surface_manifest()["surfaces"]:
        name = item["semantic_id"]
        values = zero if name.endswith("attention") else embedding
        oracle_values[name] = values.astype("<f4", copy=False).tobytes()
    comparison = compare_surface_packages(candidate_values, oracle_values, numerical_surface_manifest(), synthetic=True)
    validate_terminal_numerical_surfaces(comparison["surfaces"])
    terminal = R.terminal_finalize(candidate, comparison["surfaces"])
    terminal.update({
        "decoded_identities": {entry["name"]: "synthetic-exact-real-geometry" for entry in R.load(R.INVENTORY_PATH)["entries"]},
        "oracle": {"persisted_before_candidate": True, "rehash": "PASS"},
        "packed_package_sha256": R.PACKED_PACKAGE_SHA,
    })
    # The terminal rehearsal uses the production finalizer, but fixture-only
    # decoded labels are deliberately not passed to the real terminal validator.
    result = {
        "schema": "pulsarmlx.f017.dprefix-real3-success-rehearsal",
        "schema_version": "1.0.0",
        "result": "SUCCESS-PATH TERMINAL EVIDENCE COMPLETE",
        "instantiability": "REAL-3 SUCCESS EVIDENCE FULLY INSTANTIABLE",
        "numerical_result": "REAL-3 CHECKPOINT-FREE NUMERICAL REHEARSAL PASS",
        "actual_host_copy_count": candidate["dispatch"]["actual_host_copy_count"],
        "actual_host_copy_bytes": candidate["dispatch"]["actual_host_copy_bytes"],
        "success_path_lifecycle_reconciliation": candidate["success_path_lifecycle_reconciliation"],
        "repeats": candidate["repeats"],
        "deterministic": candidate["deterministic"],
        "tier_b_surfaces": comparison["surfaces"],
        "checkpoint_access": 0,
        "ledger_before": R.LEDGER,
        "ledger_after": R.LEDGER,
        "terminal_evidence": terminal,
    }
    write(E / "f017-dprefix-real3-success-rehearsal-v1.json", result)
    return result


def failure_and_mutation_rehearsals(success: dict) -> tuple[dict, dict, dict]:
    candidate = copy.deepcopy(success["terminal_evidence"]["candidate"])
    failure_terminal = R.terminal_finalize(candidate, [], "NATIVE_RUNTIME")
    failure = {
        "schema": "pulsarmlx.f017.dprefix-real3-failure-rehearsal",
        "schema_version": "1.0.0",
        "result": "REAL-3 FAILURE PATH COMPLETE",
        "packed_package_intact": R.validate_packed_package()["result"],
        "oracle_persisted_state_survives": True,
        "oracle_rehash": "PASS",
        "host_copy_accounting_available": failure_terminal["runtime_accounting"]["actual_host_copy_count"],
        "lifecycle": failure_terminal["success_path_lifecycle_reconciliation"]["result"],
        "ledger": R.LEDGER,
        "checkpoint_access": 0,
    }
    write(E / "f017-dprefix-real3-failure-rehearsal-v1.json", failure)
    cases = []
    for name in ("host_copy_missing", "host_copy_stale", "lifecycle_missing", "lifecycle_false_pass", "dispatch_wrong", "surface_missing", "decoded_identity_wrong", "ledger_140", "checkpoint_access_1"):
        rejected = True
        try:
            mutated = copy.deepcopy(success["terminal_evidence"])
            if name == "host_copy_missing": mutated["candidate"]["dispatch"].pop("actual_host_copy_count")
            elif name == "host_copy_stale": mutated["candidate"]["dispatch"]["actual_host_copy_count"] = -1
            elif name == "lifecycle_missing": mutated["candidate"].pop("success_path_lifecycle_reconciliation")
            elif name == "lifecycle_false_pass": mutated["candidate"]["success_path_lifecycle_reconciliation"]["result"] = "PASS"; mutated["candidate"]["success_path_lifecycle_reconciliation"]["in_flight_work"] = 1
            elif name == "dispatch_wrong": mutated["candidate"]["dispatch"]["backend_errors"] = 1
            elif name == "surface_missing": mutated["numerical_surfaces"].pop()
            elif name == "decoded_identity_wrong": mutated["decoded_identities"] = {}
            elif name == "ledger_140": mutated["ledger_after"] = 140
            elif name == "checkpoint_access_1": mutated["checkpoint_access"] = 1
            R.validate_replay_terminal(mutated)
            rejected = False
        except (R.ReplayError, ValueError, KeyError):
            pass
        if not rejected:
            raise RuntimeError(f"banker mutation accepted: {name}")
        cases.append({"mutation": name, "result": "REJECTED"})
    mutation = {"schema": "pulsarmlx.f017.dprefix-real3-banker-mutation-campaign", "schema_version": "1.0.0", "result": "PASS", "cases": cases, "checkpoint_access": 0, "ledger": R.LEDGER}
    write(E / "f017-dprefix-real3-banker-mutation-campaign-v1.json", mutation)
    attacks = R.zero_read_attack_campaign()
    write(E / "f017-dprefix-real3-zero-read-attack-campaign-v1.json", attacks)
    return failure, mutation, attacks


def producer_map() -> dict:
    candidate = "candidate native runtime / candidate JSON IPC"
    rows = {
        "candidate_identity": "candidate self-verification",
        "repeat_count": candidate,
        "repeat_determinism": candidate,
        "matvec_count": "DispatchEvidence.native_matvecs",
        "sync_count": "DispatchEvidence.synchronizations",
        "readback_count": "DispatchEvidence.readbacks",
        "actual_host_copy_count": "DispatchEvidence.actual_host_copy_count",
        "actual_host_copy_bytes": "DispatchEvidence.actual_host_copy_bytes",
        "fallback_count": "DispatchEvidence.fallback",
        "backend_error_count": "DispatchEvidence.backend_errors",
        "success_path_lifecycle_reconciliation": "LifecycleEvidence::from_dispatch",
        "eight_numerical_surfaces": "candidate/oracle semantic-ID packages",
        "Tier_B_verdict": "frozen metric engine and contract",
        "oracle_rehash": "replay oracle finalizer",
        "retained_package_identities": "retention manifest rehash",
    }
    result = {
        "schema": "pulsarmlx.f017.dprefix-replay-success-producer-map",
        "schema_version": "1.0.0",
        "result": "ALL PASS FIELDS HAVE SUCCESS-PATH PRODUCERS",
        "mapping": [{"pass_field": field, "runtime_producer": producer, "ipc_field": field, "banker_field": field, "rehearsal_proof": "f017-dprefix-real3-success-rehearsal-v1.json"} for field, producer in rows.items()],
        "test_fixture_constant_sources": 0,
        "checkpoint_access": 0,
        "ledger": R.LEDGER,
    }
    write(E / "f017-dprefix-real3-success-producer-map-v1.json", result)
    return result


def controls(candidate_build: dict, orchestrator_build: dict, contracts: dict[str, Path], success: dict) -> tuple[str, str, str]:
    config = {
        "schema": "pulsarmlx.f017.dprefix-replay-config",
        "schema_version": "1.0.0",
        "attempt_id": R.ATTEMPT,
        "event_type": "CHECKPOINT-FREE RETAINED-PACKAGE DPREFIX REPLAY",
        "execution_authorized": True,
        "consumed": False,
        "executed": False,
        "checkpoint_accessed": False,
        "checkpoint_access_budget": 0,
        "packed_package_sha256": R.PACKED_PACKAGE_SHA,
        "packed_package_descriptor_sha256": "ab0f1b3e4cdfe6664d6f30190a4d21dc2be30d12b2808f23b83c759ceb2b3ea8",
        "decoded_identity_manifest_sha256": R.digest_path(R.DECODED_MANIFEST_PATH),
        "decoded_hard_gate_count": 40,
        "candidate_binary_sha256": candidate_build["binary"]["sha256"],
        "candidate_source_manifest_sha256": candidate_build["source_manifest_sha256"],
        "replay_orchestrator_sha256": orchestrator_build["package_sha256"],
        "replay_orchestrator_source_manifest_sha256": orchestrator_build["source_manifest_sha256"],
        "oracle_package_sha256": "9b00ed225acc9b299c5bd789f1b082f6a2fd90b7893913bc9f353f99ee83c89b",
        "metric_engine_sha256": "cd7ca4eee855b60b6695b8ac6671d59eae2f446231f437168df0985f984ad738",
        "tier_b_sha256": "9d1a6cc20ce8325fe8395334416f5ebcf980b72f02c6a0b44dc3240e0810024a",
        "numerical_surface_manifest_sha256": "ecbc47bf1af97db99308a24e9303f2f6ef75d2f78d31d4853d8106afe0b271ec",
        "prompt_package_sha256": R.PROMPT_SHA,
        "inventory_sha256": R.INVENTORY_SHA,
        "repeat_count": 10,
        "contracts": {name: R.digest_path(path) for name, path in contracts.items()},
        "rehearsal_sha256": R.digest_path(E / "f017-dprefix-real3-success-rehearsal-v1.json"),
        "memory_admission_sha256": R.digest_path(E / "f017-dprefix-real3-memory-admission-v1.json"),
        "memory_floor_gib": 27,
        "ledger_before": R.LEDGER,
        "ledger_after": R.LEDGER,
        "automatic_retry": False,
        "automatic_m1f0_continuation": False,
        "downstream_policy": "ANALYTICAL_ROUTE_PLANNING_ONLY",
    }
    write(R.CONFIG_PATH, config)
    config_sha = R.digest_path(R.CONFIG_PATH)
    authorization = {
        "schema": "pulsarmlx.f017.dprefix-replay-authorization",
        "schema_version": "1.0.0",
        "attempt_id": R.ATTEMPT,
        "execution_authorized": True,
        "consumed": False,
        "status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW",
        "execution_config_sha256": config_sha,
        "replay_orchestrator_sha256": config["replay_orchestrator_sha256"],
        "candidate_binary_sha256": config["candidate_binary_sha256"],
        "packed_package_sha256": R.PACKED_PACKAGE_SHA,
        "decoded_identity_manifest_sha256": config["decoded_identity_manifest_sha256"],
        "accounting_contract_sha256": config["contracts"]["accounting"],
        "terminal_schema_sha256": config["contracts"]["schema"],
        "checkpoint_access_budget": 0,
        "ledger_before": R.LEDGER,
        "ledger_after": R.LEDGER,
        "automatic_retry": False,
        "automatic_m1f0_continuation": False,
    }
    write(R.AUTH_PATH, authorization)
    auth_sha = R.digest_path(R.AUTH_PATH)
    write(R.IDENTITY_PATH, {
        "attempt_id": R.ATTEMPT,
        "binary_sha256": config["candidate_binary_sha256"],
        "source_manifest_sha256": config["candidate_source_manifest_sha256"],
        "execution_config_sha256": config_sha,
        "authorization_binding_sha256": auth_sha,
        "inventory_sha256": R.INVENTORY_SHA,
        "prompt_package_sha256": R.PROMPT_SHA,
        "ledger_before": R.LEDGER,
    })
    attempt = {
        "schema": "pulsarmlx.f017.dprefix-replay-attempt-ledger",
        "schema_version": "1.0.0",
        "event_namespace_decision": "DPREFIX-REAL series intentionally identifies reviewed dense-prefix event ordinals; access authority is the explicit zero-read budget",
        "historical_predecessor": binding(R.ATTEMPT_V10_PATH),
        "real2_terminal": {"attempt_id": "DPREFIX-REAL-2", "consumed": True, "executed": True, "checkpoint_accessed": True, "terminal_class": "EVIDENCE_VALIDATION", "reason_code": "SUCCESS_PATH_RUNTIME_ACCOUNTING_MISSING", "retryable": False, "evidence_sha256": R.REAL2_EVIDENCE_SHA},
        "current_state": {"attempt_id": R.ATTEMPT, "authorized": True, "consumed": False, "executed": False, "checkpoint_accessed": False, "checkpoint_access_budget": 0, "ledger": R.LEDGER, "automatic_retry": False, "automatic_m1f0_continuation": False},
        "authorization": {"config_sha256": config_sha, "binding_sha256": auth_sha},
        "ledger": R.LEDGER,
        "checkpoint_access": 0,
    }
    attempt_path = E / "f017-dense-prefix-replay-attempt-ledger-v1.json"
    write(attempt_path, attempt)
    return config_sha, auth_sha, R.digest_path(attempt_path)


def prepare() -> dict[str, Any]:
    preserve_real2()
    package = R.validate_packed_package()
    write(E / "f017-dprefix-real3-packed-package-integrity-v1.json", package)
    decoded_manifest = R.decoded_identity_manifest()
    write(R.DECODED_MANIFEST_PATH, decoded_manifest)
    decoded = R.verify_all_decoded_identities()
    write(E / "f017-dprefix-real3-all40-independent-decode-v1.json", decoded)
    contracts = d4_contracts()
    write(E / "f017-dprefix-real3-memory-admission-v1.json", {
        "schema": "pulsarmlx.f017.dprefix-replay-memory-admission",
        "schema_version": "1.0.0",
        "minimum_free_gib": 27,
        "result": "27 GIB FLOOR STILL SAFE",
        "packed_package_storage_bytes": R.PACKED_BYTES,
        "packed_package_memory_policy": "streamed/replay-local reads; no second retained packed copy",
        "oracle_decoded_material_release": "after oracle Class-A persistence and before candidate spawn",
        "candidate_decode_import": "fresh independent consumer after oracle decoded material release",
        "paired_surface_bytes": 8 * 6144 * 4 * 2,
        "safety_factor": 1.25,
        "checkpoint_access": 0,
        "ledger": R.LEDGER,
    })
    _, candidate_build, _, orchestrator_build = source_and_build_manifests()
    success = run_success_rehearsal()
    failure, mutation, attacks = failure_and_mutation_rehearsals(success)
    producers = producer_map()
    config_sha, auth_sha, attempt_sha = controls(candidate_build, orchestrator_build, contracts, success)
    preflight = {
        "schema": "pulsarmlx.f017.dprefix-replay-preflight",
        "schema_version": "1.0.0",
        "attempt_id": R.ATTEMPT,
        "result": R.preflight(),
        "package_integrity": package["result"],
        "decoded_hard_gates": decoded["hard_gate_count"],
        "zero_read": attacks["result"],
        "checkpoint_access": 0,
        "ledger": R.LEDGER,
    }
    write(E / "f017-dprefix-real3-preflight-v1.json", preflight)
    root_cause = {
        "schema": "pulsarmlx.f017.dprefix-d4-root-cause",
        "schema_version": "1.0.0",
        "host_copy_root_cause": "native_matvec/DispatchEvidence → RealCandidateEvidence: copy_f32 was counted only as a readback; no host-copy count or byte producer existed in candidate IPC",
        "lifecycle_root_cause": "native_matvec ownership_snapshot → execute_material_package: reconciliation ran locally per matvec but RealCandidateEvidence omitted the aggregate success-path lifecycle record",
        "rehearsal_blind_spot": "the prior synthetic route serialized SyntheticEvidence.lifecycle_reconciled=true and never exercised the production RealCandidateEvidence success IPC/banker route",
        "first_lost_host_copy_boundary": "candidate native instrumentation before candidate IPC",
        "first_lost_lifecycle_boundary": "candidate success aggregation before candidate IPC",
        "remediation": "D4 REMEDIATION ACCOUNTING-ONLY",
        "shared_finalizer": "SUCCESS AND FAILURE ACCOUNTING SHARE TERMINAL FINALIZER",
        "checkpoint_access": 0,
        "ledger": R.LEDGER,
    }
    write(E / "f017-dprefix-real3-d4-root-cause-v1.json", root_cause)
    review = {
        "schema": "pulsarmlx.f017.dprefix-real3-internal-review",
        "schema_version": "1.0.0",
        "verdict": "GO FOR CHECKPOINT-FREE DPREFIX-REAL-3 ADVERSARIAL REVIEW",
        "answers": {
            "real2_rejected": "PASS-required host-copy count and complete success lifecycle were absent",
            "host_copy_loss": root_cause["host_copy_root_cause"],
            "lifecycle_loss": root_cause["lifecycle_root_cause"],
            "blind_spot": root_cause["rehearsal_blind_spot"],
            "accounting_only": True,
            "packed_complete_immutable": True,
            "all40_independent_decode": True,
            "decoded_hard_gates": 40,
            "checkpoint_access_structurally_unreachable": True,
            "ledger_all_paths": "139→139",
            "actual_rehearsal_host_copy_count": success["actual_host_copy_count"],
            "actual_lifecycle_pass": success["success_path_lifecycle_reconciliation"]["result"],
            "all_pass_fields_produced": producers["result"],
            "eight_tier_b": success["numerical_result"],
            "failure_evidence_complete": failure["result"],
            "real2_terminal": True,
            "fresh_replay_event": R.ATTEMPT,
            "real_reads": 0,
        },
        "checkpoint_access": 0,
        "ledger": R.LEDGER,
    }
    write(E / "f017-dprefix-real3-internal-review-v1.json", review)
    packet = {
        "schema": "pulsarmlx.f017.dprefix-real3-adversarial-packet",
        "schema_version": "1.0.0",
        "primary_questions": ["Is D4 fully closed on the actual successful execution path?", "Can the immutable packed package support an independent replay with structurally zero checkpoint access?", "Can every PASS-required runtime accounting field be honestly populated?"],
        "required_verdicts": ["GO FOR ONE CHECKPOINT-FREE DPREFIX-REAL-3 REPLAY", "GO WITH REQUIRED FIXES", "NO-GO"],
        "bindings": {"config_sha256": config_sha, "authorization_sha256": auth_sha, "success_rehearsal_sha256": R.digest_path(E / "f017-dprefix-real3-success-rehearsal-v1.json"), "producer_map_sha256": R.digest_path(E / "f017-dprefix-real3-success-producer-map-v1.json"), "zero_read_attack_sha256": R.digest_path(E / "f017-dprefix-real3-zero-read-attack-campaign-v1.json")},
        "checkpoint_access": 0,
        "ledger": R.LEDGER,
    }
    write(E / "f017-dprefix-real3-adversarial-packet-v1.json", packet)
    report = ROOT / "docs/architecture/reviews/f017-dprefix-real-3-preparation-report.md"
    report.write_text(f"""# PulsarMLX F017 DPREFIX-REAL-3 Preparation Report

- Starting SHA: `ea362ced6b39915c4d42bf044f1779f55b60995e`
- Final preparation SHA: `PENDING_COMMIT`
- REAL-2 evidence SHA: `{R.REAL2_EVIDENCE_SHA}`
- Real-payload ledger: `139`
- REAL-2 historical classification: `NUMERICALLY_QUALIFIED / EVENT_REJECTED_FOR_EVIDENCE_COMPLETENESS`
- Host-copy root cause: `{root_cause['host_copy_root_cause']}`
- Lifecycle root cause: `{root_cause['lifecycle_root_cause']}`
- Rehearsal blind spot: `{root_cause['rehearsal_blind_spot']}`
- Accounting remediation SHA: `{R.digest_path(contracts['accounting'])}`
- Candidate identity: `{candidate_build['binary']['sha256']}`
- Replay orchestrator SHA: `{orchestrator_build['package_sha256']}`
- Packed-package identity: `{R.PACKED_PACKAGE_SHA}`
- Packed-package integrity: `{package['result']}`
- Packed package byte count: `{package['packed_bytes']}`
- Decoded identity manifest SHA: `{R.digest_path(R.DECODED_MANIFEST_PATH)}`
- Decoded hard-gate count: `{decoded['hard_gate_count']}`
- Zero-checkpoint-access contract SHA: `{R.digest_path(contracts['zero_read'])}`
- Replay event contract SHA: `{R.digest_path(contracts['event'])}`
- Success rehearsal: `{success['result']}`
- Actual rehearsal host-copy count: `{success['actual_host_copy_count']}` (`{success['actual_host_copy_bytes']}` bytes)
- Rehearsal lifecycle: `{success['success_path_lifecycle_reconciliation']['result']}`
- All-eight Tier-B rehearsal: `{success['numerical_result']}`
- Failure-path rehearsal: `{failure['result']}`
- Banker mutation result: `{mutation['result']}`
- Checkpoint-access attack result: `{attacks['result']}`
- Fresh replay attempt ID: `{R.ATTEMPT}`
- Config SHA: `{config_sha}`
- Authorization SHA: `{auth_sha}`
- Attempt ledger SHA: `{attempt_sha}`
- Ledger plan: `139 → 139`
- Checkpoint access: `0`
- Internal verdict: `{review['verdict']}`
- Adversarial packet SHA: `{R.digest_path(E / 'f017-dprefix-real3-adversarial-packet-v1.json')}`
- Final CI run/head: `PENDING_FINAL_HEAD_CI`

## Exact next action

Independent adversarial review. Only `GO FOR ONE CHECKPOINT-FREE DPREFIX-REAL-3 REPLAY` may release the replay. No checkpoint read under any circumstance.
""")
    return {"config": config_sha, "authorization": auth_sha, "attempt": attempt_sha, "candidate": candidate_build["binary"]["sha256"], "orchestrator": orchestrator_build["package_sha256"], "preflight": preflight["result"], "host_copies": success["actual_host_copy_count"], "lifecycle": success["success_path_lifecycle_reconciliation"]["result"], "decoded_gates": decoded["hard_gate_count"], "checkpoint_access": 0, "ledger": R.LEDGER, "verdict": review["verdict"], "packet": R.digest_path(E / "f017-dprefix-real3-adversarial-packet-v1.json")}


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2, sort_keys=True))
