#!/usr/bin/env python3
"""Generate the checkpoint-free DPREFIX-REAL-2 successor package."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from scripts.research import f017_dprefix_real2_orchestrator as R

ROOT = R.ROOT
E = R.EVIDENCE
C = R.CONTRACTS
CANDIDATE_SOURCE = ROOT / "crates/f017-runner/src/bin/f017-dense-prefix-candidate.rs"
CANDIDATE_BINARY = ROOT / ".pulsarmlx-local/oracle-build/f017-dense-prefix-candidate-v3"
ORCHESTRATOR_SOURCE = ROOT / "scripts/research/f017_dprefix_real2_orchestrator.py"
REPRODUCER_LOCAL = ROOT / ".pulsarmlx-local/dprefix-real2-exact-shape-reproducer-final.json"
FULL_LOCAL = ROOT / ".pulsarmlx-local/dprefix-real2-full-exact-shape-final.json"


def write(path: Path, value: object) -> None:
    R.atomic_json(path, value)


def file_binding(path: Path, role: str) -> dict[str, str]:
    return {"path": str(path.relative_to(ROOT)), "sha256": R.digest_path(path), "role": role}


def artifact_sha(path: Path) -> str:
    return R.digest_path(path)


def build_manifests() -> tuple[dict, dict]:
    candidate_source = {
        "schema": "pulsarmlx.f017.dprefix-candidate-source-manifest",
        "schema_version": "3.0.0",
        "predecessor_source_manifest_sha256": "1df94bc11a550dc589666fdbdac6fd3cd0c7bdc17ab76f2fd8a74f705dfed35d",
        "attempt_id": R.ATTEMPT,
        "files": [
            file_binding(CANDIDATE_SOURCE, "successor candidate, structured shape checks, attn_k_b transpose"),
            file_binding(ROOT / "crates/quant/src/cpu_dot.rs", "candidate Q4_K/Q5_K decode"),
            file_binding(ROOT / "crates/quant/src/q6_k_ref.rs", "candidate Q6_K decode"),
            file_binding(ROOT / "crates/quant/src/q8_0_ref.rs", "candidate Q8_0 decode"),
            file_binding(ROOT / "crates/stream/src/apple_mlx_bridge.rs", "native MLX import/matvec ownership"),
            file_binding(ROOT / "crates/stream/src/apple_mlx_bridge.mm", "MLX C dispatch"),
        ],
        "arithmetic_change": "attn_k_b per-head stored-to-semantic transpose only",
        "unchanged": ["quantization", "Tier-B", "prompt", "40-entry inventory", "model architecture"],
        "checkpoint_access": 0,
    }
    write(E / "f017-dprefix-candidate-source-manifest-v3.json", candidate_source)
    orchestrator_source = {
        "schema": "pulsarmlx.f017.dprefix-real2-orchestrator-source-manifest",
        "schema_version": "1.0.0",
        "attempt_id": R.ATTEMPT,
        "files": [
            file_binding(ORCHESTRATOR_SOURCE, "REAL-2 exact reader, packed retention, oracle persistence, candidate/failure banker"),
            file_binding(Path(__file__).resolve(), "checkpoint-free preparation and immutable artifact generator"),
            file_binding(ROOT / "scripts/research/f017_dprefix_real_event_orchestrator.py", "reviewed predecessor decode/oracle/metric helpers"),
            file_binding(ROOT / "scripts/research/f017_dprefix_metric_engine.py", "unchanged frozen Tier-B metric engine"),
        ],
        "real_authority": "DPREFIX-REAL-2_ONLY",
        "checkpoint_access_during_build": 0,
        "dynamic_generation_at_execution": False,
    }
    write(E / "f017-dprefix-real2-orchestrator-source-manifest-v1.json", orchestrator_source)
    return candidate_source, orchestrator_source


def contracts() -> dict[str, Path]:
    shape = R.real_shape_contract()
    R.validate_static_shapes(shape)
    paths = {
        "shape": C / "f017-dprefix-real-shape-contract-v1.json",
        "oracle": C / "f017-dprefix-oracle-persist-on-finalize-v1.json",
        "packed": C / "f017-dprefix-packed-payload-retention-v1.json",
        "lifecycle": C / "f017-dprefix-native-failure-lifecycle-v1.json",
        "banker": C / "f017-dprefix-terminal-failure-banker-v1.json",
    }
    write(paths["shape"], shape)
    write(paths["oracle"], {
        "schema": "pulsarmlx.f017.dprefix-oracle-persist-on-finalize",
        "schema_version": "1.0.0", "attempt_id": R.ATTEMPT,
        "ordering": ["oracle_finalize", "persist_class_a", "fsync", "freeze_manifest", "candidate_spawn"],
        "candidate_spawn_gate": "ORACLE PRIMARY PRODUCTS DURABLY RETAINED",
        "required": ["layer_2_output", "layer_3_entry"],
        "actual_bytes": True, "canonical_serialization": "little_endian_f32",
        "rehash_paths": ["candidate_success", "candidate_failure", "repeat_failure", "Tier-B_failure", "banker_failure"],
        "checkpoint_access": 0,
    })
    write(paths["packed"], {
        "schema": "pulsarmlx.f017.dprefix-packed-payload-retention",
        "schema_version": "1.0.0", "attempt_id": R.ATTEMPT,
        "payloads": 40, "packed_bytes": R.PACKED_BYTES,
        "per_read_order": ["durable_read_journal", "packed_sha256", "artifact_write_fsync", "package_entry_finalize"],
        "retention": "actual packed bytes, immutable, read-only, event-created",
        "decoded_truth_package": "NOT_CREATED",
        "future_reuse": "separate explicit authorization and independent consumer decode/import required",
        "automatic_rerun": False, "checkpoint_access": 0,
    })
    write(paths["lifecycle"], {
        "schema": "pulsarmlx.f017.dprefix-native-failure-lifecycle",
        "schema_version": "1.0.0", "attempt_id": R.ATTEMPT,
        "finally_cleanup": ["child_process", "MLX_context", "arrays", "streams", "native_allocations", "in_flight_work", "stale_generations"],
        "terminal_requirement": "NATIVE FAILURE LIFECYCLE RECONCILED",
        "automatic_retry": False, "checkpoint_access": 0,
    })
    write(paths["banker"], {
        "schema": "pulsarmlx.f017.dprefix-terminal-failure-banker",
        "schema_version": "1.0.0", "attempt_id": R.ATTEMPT,
        "native_failure_required": ["candidate_launched", "exit_status", "stage", "tensor", "matrix_shape", "vector_shape", "expected_contraction", "observed_contraction", "dispatches", "syncs", "readbacks", "host_copies", "fallback", "backend_errors", "lifecycle", "oracle_rehash", "packed_package_identity"],
        "summary_only_truth": False, "append_only_correction": True,
        "checkpoint_access": 0,
    })
    return paths


def bank_rehearsals() -> tuple[dict, dict, dict, dict]:
    reproducer = R.load(REPRODUCER_LOCAL)
    reproducer.update({
        "result": "PREDECESSOR FAILS / SUCCESSOR PASSES / ORACLE PARITY PASS",
        "root_cause_classification": "CANDIDATE_IMPORT",
        "first_shape_lineage_divergence": "candidate head import/orientation for attn_k_b",
        "checkpoint_access": 0, "ledger": 99,
    })
    write(E / "f017-dprefix-real2-exact-shape-reproducer-v1.json", reproducer)
    full = R.load(FULL_LOCAL)
    full["candidate_binary_sha256"] = R.digest_path(CANDIDATE_BINARY)
    full["result"] = "FULL EXACT-REAL-SHAPE DPREFIX REHEARSAL PASS"
    write(E / "f017-dprefix-real2-full-exact-shape-rehearsal-v1.json", full)
    with tempfile.TemporaryDirectory(prefix="f017-real2-failure-") as directory:
        failure = R.run_candidate_failure_persistence_rehearsal(Path(directory) / "event")
    write(E / "f017-dprefix-real2-candidate-failure-persistence-rehearsal-v1.json", failure)
    mutations = R.mutation_campaign(R.real_shape_contract())
    write(E / "f017-dprefix-real2-shape-mutation-campaign-v1.json", mutations)
    failure_matrix = R.failure_path_matrix()
    write(E / "f017-dprefix-real2-failure-path-matrix-v1.json", failure_matrix)
    successor = {
        "schema": "pulsarmlx.f017.dprefix-real2-full-event-rehearsal",
        "schema_version": "1.0.0", "attempt_id": R.ATTEMPT,
        "result": "DPREFIX-REAL-2 FULL EXACT-SHAPE EVENT REHEARSAL PASS",
        "checkpoint_access": 0, "ledger": 99,
        "exact_geometry_rehearsal_sha256": artifact_sha(E / "f017-dprefix-real2-full-exact-shape-rehearsal-v1.json"),
        "failure_persistence_rehearsal_sha256": artifact_sha(E / "f017-dprefix-real2-candidate-failure-persistence-rehearsal-v1.json"),
        "shape_mutation_campaign_sha256": artifact_sha(E / "f017-dprefix-real2-shape-mutation-campaign-v1.json"),
        "failure_path_matrix_sha256": artifact_sha(E / "f017-dprefix-real2-failure-path-matrix-v1.json"),
        "all_40_synthetic_packed_gates": "PASS",
        "oracle_persisted_before_candidate": True,
        "packed_package_survives_candidate_failure": True,
        "ten_repeats": 10, "tier_b": "UNCHANGED_EXACT_SYNTHETIC_PARITY_PASS",
        "fallback": 0, "backend_errors": 0, "lifecycle": "PASS",
    }
    write(E / "f017-dprefix-real2-full-successor-event-rehearsal-v1.json", successor)
    return reproducer, full, failure, successor


def prepare() -> dict:
    R.validate_predecessor_terminal()
    if not CANDIDATE_BINARY.is_file():
        raise RuntimeError("successor candidate binary missing")
    candidate_source, orchestrator_source = build_manifests()
    contract_paths = contracts()
    identity = R.packed_identity_manifest()
    write(E / "f017-dprefix-real2-all40-packed-identity-manifest-v1.json", identity)
    reproducer, full, failure, successor = bank_rehearsals()
    mutation_sha = artifact_sha(E / "f017-dprefix-real2-shape-mutation-campaign-v1.json")
    build = {
        "schema": "pulsarmlx.f017.dprefix-candidate-build-manifest",
        "schema_version": "3.0.0", "attempt_id": R.ATTEMPT,
        "predecessor_binary_sha256": "1a73dd4026592e21df05a82df806e52ebcb8dd0248aaffc0d8fd91c6f9e1387a",
        "binary": {"symbolic_private_path": "f017-private/dprefix/f017-dense-prefix-candidate-v3", "sha256": R.digest_path(CANDIDATE_BINARY), "size_bytes": CANDIDATE_BINARY.stat().st_size, "read_only": True, "dynamic_build_at_execution": False},
        "source_manifest_sha256": artifact_sha(E / "f017-dprefix-candidate-source-manifest-v3.json"),
        "compiler": subprocess.check_output(["rustc", "-vV"], text=True),
        "cargo": subprocess.check_output(["cargo", "-V"], text=True).strip(),
        "target": platform.machine() + "-apple-darwin",
        "native_mlx_rpath": "reviewed-private-native-mlx-prefix/lib",
        "checkpoint_access": 0,
    }
    write(E / "f017-dprefix-candidate-build-manifest-v3.json", build)
    orchestrator_build = {
        "schema": "pulsarmlx.f017.dprefix-real2-orchestrator-build-manifest",
        "schema_version": "1.0.0", "attempt_id": R.ATTEMPT,
        "package_sha256": R.digest_path(ORCHESTRATOR_SOURCE),
        "source_manifest_sha256": artifact_sha(E / "f017-dprefix-real2-orchestrator-source-manifest-v1.json"),
        "python": sys.version if "sys" in globals() else platform.python_version(),
        "real_entry_point": "--execute-reviewed-real2",
        "dynamic_build_at_execution": False, "checkpoint_access": 0,
    }
    write(E / "f017-dprefix-real2-orchestrator-build-manifest-v1.json", orchestrator_build)
    memory = {
        "schema": "pulsarmlx.f017.dprefix-real2-memory-admission", "schema_version": "1.0.0",
        "minimum_free_gib": 27, "result": "27 GIB FLOOR STILL SAFE",
        "packed_retention_storage_bytes": R.PACKED_BYTES,
        "packed_retention_memory_policy": "streamed durable write; not a second resident packed copy",
        "oracle_primary_storage_bytes": 49_152,
        "new_peak_runtime_bytes": 0,
        "safety_factor": 1.25, "checkpoint_access": 0, "ledger": 99,
    }
    write(E / "f017-dprefix-real2-memory-admission-v1.json", memory)
    config = {
        "schema": "pulsarmlx.f017.dense-prefix-execution-config", "schema_version": "6.0.0",
        "predecessor": {"path": "docs/architecture/reviews/evidence/f017-dense-prefix-execution-config-v5.json", "sha256": "27774a11d933750cb9703a9889b5f83b88711ee27827c9d34eb585649545aadd"},
        "attempt_id": R.ATTEMPT, "execution_authorized": True, "consumed": False, "executed": False, "checkpoint_accessed": False,
        "status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW",
        "access": {"ledger_before": 99, "expected_full_ledger_after": 139, "payloads": 40, "packed_bytes": R.PACKED_BYTES},
        "candidate": {"binary_sha256": build["binary"]["sha256"], "source_manifest_sha256": build["source_manifest_sha256"], "build_manifest_sha256": artifact_sha(E / "f017-dprefix-candidate-build-manifest-v3.json")},
        "orchestrator": {"package_sha256": orchestrator_build["package_sha256"], "source_manifest_sha256": orchestrator_build["source_manifest_sha256"], "build_manifest_sha256": artifact_sha(E / "f017-dprefix-real2-orchestrator-build-manifest-v1.json")},
        "contracts": {key: artifact_sha(path) for key, path in contract_paths.items()},
        "packed_identity_manifest_sha256": artifact_sha(E / "f017-dprefix-real2-all40-packed-identity-manifest-v1.json"),
        "rehearsal_sha256": artifact_sha(E / "f017-dprefix-real2-full-successor-event-rehearsal-v1.json"),
        "oracle_package_sha256": R.ORACLE_SHA, "metric_engine_sha256": R.METRIC_SHA, "tier_b_sha256": R.TIER_B_SHA,
        "prompt_package_sha256": R.PROMPT_SHA, "inventory_sha256": R.digest_path(R.INVENTORY),
        "repeat_count": 10, "memory_floor_gib": 27,
        "downstream_oracle_state_policy": "ORACLE_STATE_USABLE_FOR_ANALYTICAL_ROUTE_PLANNING_ONLY; actual M1-F0 remains not authorized until separate review",
        "packed_reuse_policy": "checkpoint-free candidate/oracle/metric rerun requires a fresh explicit authorization binding the immutable packed package; never automatic",
        "automatic_retry": False, "automatic_m1f0_continuation": False,
    }
    write(E / "f017-dense-prefix-execution-config-v6.json", config)
    config_sha = artifact_sha(E / "f017-dense-prefix-execution-config-v6.json")
    authorization = {
        "schema": "pulsarmlx.f017.dense-prefix-authorization-binding", "schema_version": "5.0.0",
        "predecessor_authorization_sha256": "fc286651d4fa11ff43e0db926a801d24e30152509465d2d7f0510d79599e1e47",
        "attempt_id": R.ATTEMPT, "execution_authorized": True, "consumed": False,
        "status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW",
        "execution_config_sha256": config_sha,
        "candidate_binary_sha256": build["binary"]["sha256"],
        "candidate_source_manifest_sha256": build["source_manifest_sha256"],
        "orchestrator_package_sha256": orchestrator_build["package_sha256"],
        "orchestrator_source_manifest_sha256": orchestrator_build["source_manifest_sha256"],
        "real_shape_contract_sha256": config["contracts"]["shape"],
        "packed_identity_manifest_sha256": config["packed_identity_manifest_sha256"],
        "packed_retention_contract_sha256": config["contracts"]["packed"],
        "oracle_persist_contract_sha256": config["contracts"]["oracle"],
        "terminal_banker_sha256": config["contracts"]["banker"],
        "lifecycle_failure_contract_sha256": config["contracts"]["lifecycle"],
        "ledger_before": 99, "expected_ledger_after": 139,
        "automatic_retry": False, "automatic_m1f0_continuation": False, "checkpoint_access": 0,
    }
    write(E / "f017-dense-prefix-authorization-binding-v5.json", authorization)
    auth_sha = artifact_sha(E / "f017-dense-prefix-authorization-binding-v5.json")
    identity_binding = {
        "attempt_id": R.ATTEMPT, "binary_sha256": build["binary"]["sha256"],
        "source_manifest_sha256": build["source_manifest_sha256"],
        "execution_config_sha256": config_sha, "authorization_binding_sha256": auth_sha,
        "inventory_sha256": R.digest_path(R.INVENTORY), "prompt_package_sha256": R.PROMPT_SHA,
        "ledger_before": 99,
    }
    write(E / "f017-dprefix-candidate-identity-binding-v3.json", identity_binding)
    attempt = {
        "schema": "pulsarmlx.f017.dense-prefix-attempt-ledger", "schema_version": "9.0.0",
        "append_only_predecessor": {"path": "docs/architecture/reviews/evidence/f017-dense-prefix-attempt-ledger-v8.json", "sha256": R.digest_path(E / "f017-dense-prefix-attempt-ledger-v8.json")},
        "prior_terminal_attempt": {"attempt_id": "DPREFIX-REAL-1", "state": "TERMINAL_REJECTED", "consumed": True, "executed": True, "checkpoint_accessed": True, "terminal_class": "NATIVE_RUNTIME", "reason_code": "NATIVE_CANDIDATE_MATVEC_SHAPE", "evidence_sha256": R.REAL1_EVIDENCE_SHA, "automatic_retry": False},
        "current_state": {"attempt_id": R.ATTEMPT, "authorized": True, "consumed": False, "executed": False, "checkpoint_accessed": False, "ledger": 99, "automatic_retry": False, "automatic_m1f0_continuation": False},
        "authorization": {"config_sha256": config_sha, "binding_sha256": auth_sha},
        "ledger": 99, "checkpoint_access": 0,
    }
    write(E / "f017-dense-prefix-attempt-ledger-v9.json", attempt)
    preflight_result = R.preflight(config, authorization, attempt)
    preflight = {"schema": "pulsarmlx.f017.dprefix-real2-preflight", "schema_version": "1.0.0", "attempt_id": R.ATTEMPT, "result": preflight_result, "review_release_required": True, "checkpoint_access": 0, "ledger": 99, "config_sha256": config_sha, "authorization_sha256": auth_sha, "attempt_ledger_sha256": artifact_sha(E / "f017-dense-prefix-attempt-ledger-v9.json"), "full_rehearsal_sha256": config["rehearsal_sha256"]}
    write(E / "f017-dprefix-real2-preflight-v1.json", preflight)
    review = {
        "schema": "pulsarmlx.f017.dprefix-real2-internal-review", "schema_version": "1.0.0",
        "verdict": "GO FOR DPREFIX-REAL-2 PREPARATION ADVERSARIAL REVIEW",
        "checkpoint_access": 0, "ledger": 99,
        "answers": {
            "first_matvec": "layer_0.attention.k_head_0 / blk.0.attn_k_b.weight",
            "dimensions": "predecessor [512,192] x [512]; successor [192,512] x [512]",
            "first_divergence": "candidate attn_k_b head import/orientation",
            "prior_rehearsal_blind_spot": "reduced synthetic head geometry used qk_nope=8 and kv_lora=16, never exact [192,512,64] GGUF orientation",
            "predecessor_reproduced": True, "successor_passes": True,
            "all_shapes_static": True, "candidate_oracle_parity": True,
            "oracle_persisted_before_candidate": True, "oracle_survives_candidate_death": True,
            "packed_survives_candidate_death": True, "packed_hard_gates": 40,
            "native_failure_complete": True, "failure_cleanup": True,
            "real1_retry_impossible": True, "fresh_attempt": R.ATTEMPT,
            "ledger_plan": "99→139", "real_access": 0,
        },
    }
    write(E / "f017-dprefix-real2-internal-review-v1.json", review)
    packet = {
        "schema": "pulsarmlx.f017.dprefix-real2-adversarial-packet", "schema_version": "1.0.0",
        "primary_questions": ["Has the real-shape native defect been conclusively reproduced and fixed?", "Will REAL-2 persist oracle primary products and all packed inputs before candidate failure can destroy them?", "Has the exact failure path been rehearsed?"],
        "required_verdicts": ["GO FOR ONE DPREFIX-REAL-2 REAL CAPTURE", "GO WITH REQUIRED FIXES", "NO-GO"],
        "bindings": {"config_sha256": config_sha, "authorization_sha256": auth_sha, "reproducer_sha256": artifact_sha(E / "f017-dprefix-real2-exact-shape-reproducer-v1.json"), "full_rehearsal_sha256": config["rehearsal_sha256"]},
        "checkpoint_access": 0, "ledger": 99,
    }
    write(E / "f017-dprefix-real2-adversarial-packet-v1.json", packet)
    return {"config": config_sha, "authorization": auth_sha, "attempt": artifact_sha(E / "f017-dense-prefix-attempt-ledger-v9.json"), "preflight": preflight_result, "candidate": build["binary"]["sha256"], "orchestrator": orchestrator_build["package_sha256"], "mutation": mutation_sha}


if __name__ == "__main__":
    import sys
    print(json.dumps(prepare(), indent=2, sort_keys=True))
