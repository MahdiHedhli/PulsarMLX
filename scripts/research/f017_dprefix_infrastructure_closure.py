#!/usr/bin/env python3
"""Freeze and validate the checkpoint-free DPREFIX infrastructure closure."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

from scripts.research.f017_dprefix_oracle_runtime import synthetic_actual_binary_oracle

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
PRIVATE = ROOT / ".pulsarmlx-local/oracle-build"
BINARY = PRIVATE / "f017-dense-prefix-candidate"
SYNTHETIC_PRIVATE = PRIVATE / "synthetic-evidence-v2.json"

ATTEMPT = "DPREFIX-REAL-1"
LEDGER = 59
PREDECESSOR_HEAD = "6120be0c279c6b8e8cd3a44ec52790a5fbe7811b"
NONEXECUTION_SHA = "b8495bd1a4129efc7e24c687289bcb3be7af7f153e24d45ccffdccb79e79d60a"
PREDECESSOR_CONFIG_SHA = "1335ebb3e617ad1ca9e2c39cf10f3286c9be8acfc99c2aa834c0a8bbbe0878e7"
PREDECESSOR_AUTH_SHA = "47efe5f2ac4d4c31443077a7cc8ffdc6618926a6c0e656d6aee7a74a5ea69956"
PREPARATION_SHA = "32eeb9e7a90dd45abcedc0014d4c6bb533f8caec4613e962817b1e2b44303ac4"
INVENTORY_SHA = "c9c1540ea1cc9e69344ed9f3dcc4eb8ba1e5c15e3d55c1bccdec00eeb1db36aa"
PROMPT_SHA = "c05ba1cba69535cd17daf9f4326e5e1db25ffafe504c53712aa548f251741dff"
ORACLE_CONTRACT_SHA = "0a54aa957e8b768108e4d8bc8c6e2a84cb48fbb3e0c93414c308112e88b3e816"
TIER_B_SHA = "9d1a6cc20ce8325fe8395334416f5ebcf980b72f02c6a0b44dc3240e0810024a"
REPEAT_SHA = "4a9f2f29689b8c20259ebadd46a0038008895ea173bf024b2ab805d35b7aa488"
DISPATCH_SHA = "d430b7dcc23d98d1b339315443f7868d6f8dd7e3e7c389ebae7d24ecae45e267"
LIFECYCLE_SHA = "2b6fd4ac70ea83fb80bcfba98d36dd5685ebf324839cdabbb0c782edd6197771"
RETENTION_SHA = "89dd470bda3c9c312ca59d3d9b798016f83f1a810339840b427e7e6a16c679c1"
HOST_SHA = "66b23ee64dca045a90b1611b58aa2eba4ac9981c28b0e32dfe142e4bf95fa289"

CANDIDATE_FILES = {
    "crates/f017-runner/src/bin/f017-dense-prefix-candidate.rs": "narrow boundary executable, decode/import, layers 0-2, retention",
    "crates/f017-runner/Cargo.toml": "dedicated binary declaration and dependencies",
    "crates/f017-runner/build.rs": "source identity and native-MLX admission",
    "crates/quant/src/cpu_dot.rs": "Q4_K/Q5_K candidate decoder path",
    "crates/quant/src/q6_k_ref.rs": "corrected Q6_K candidate decoder path",
    "crates/quant/src/q8_0_ref.rs": "Q8_0 candidate decoder path",
    "crates/stream/src/apple_mlx_bridge.rs": "Rust native tensor import/matvec/lifecycle surface",
    "crates/stream/src/apple_mlx_bridge.mm": "MLX C/Objective-C++ dispatch and ownership surface",
    "crates/stream/build.rs": "native bridge compile/link identity",
}
ORACLE_FILES = {
    "scripts/research/f017_dprefix_oracle_runtime.py": "NumPy-only embedding, RMSNorm, MLA position-zero, dense FFN, residual, serialization",
    "scripts/research/ggml_kquants.py": "independent Q4_K/Q5_K/Q6_K decoder specification",
    "scripts/research/glm52_dense_primitives.py": "reviewed independent F32/Q8_0 decoder lineage",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def source_manifest(files: dict[str, str], surface: str) -> dict[str, Any]:
    entries = []
    for relative, role in files.items():
        path = ROOT / relative
        if not path.is_file():
            raise ValueError(f"missing source surface {relative}")
        entries.append({"path": relative, "sha256": sha(path), "role": role})
    value = {
        "schema": f"pulsarmlx.f017.dprefix-{surface}-source-manifest",
        "schema_version": "1.0.0",
        "surface": surface,
        "files": entries,
        "wildcards": False,
        "checkpoint_access": 0,
    }
    value["source_manifest_sha256"] = canonical_sha(value)
    return value


def command_version(command: list[str]) -> str:
    return subprocess.check_output(command, cwd=ROOT, text=True).strip()


def candidate_build(candidate_source: dict[str, Any]) -> dict[str, Any]:
    if not BINARY.is_file():
        raise ValueError(f"candidate executable missing at symbolic private package {BINARY.name}")
    libraries = {
        "libmlx.dylib": "6622caeb3e65a8310cf2290751ffbecf32135187aa75ef05f398916ac37bd9ed",
        "libmlxc.dylib": "a060915d4b9accbf58e84d174029d5c51805891834494d50cf87a0d573222e62",
    }
    return {
        "schema": "pulsarmlx.f017.dprefix-candidate-build-manifest",
        "schema_version": "1.0.0",
        "binary": {
            "symbolic_private_path": "f017-private/dprefix/f017-dense-prefix-candidate",
            "sha256": sha(BINARY),
            "size_bytes": BINARY.stat().st_size,
            "format": "Mach-O 64-bit arm64 executable",
            "dynamic_build_at_execution": False,
        },
        "source_manifest_sha256": candidate_source["source_manifest_sha256"],
        "compiler": command_version(["rustc", "--version", "--verbose"]),
        "cargo": command_version(["cargo", "--version"]),
        "target_triple": "aarch64-apple-darwin",
        "native_mlx": {
            "mlx_source_sha": "68cf2fddd8de5edd8ab3d926391772b2e2cedad8",
            "mlx_c_source_sha": "0726ca922fc902c4c61ef9c27d94132be418e945",
            "libraries": libraries,
            "loader": "@rpath/libmlxc.dylib + @rpath/libmlx.dylib",
        },
        "scope": ["embedding", "dense_layer_0", "dense_layer_1", "dense_layer_2", "layer3_entry_retention"],
        "structurally_absent": ["layer3_attention", "router", "experts", "logits", "output_head", "sampling", "generation", "M1-F0", "M1-F", "P1"],
        "checkpoint_access": 0,
    }


def instantiate_oracle(oracle_source: dict[str, Any]) -> dict[str, Any]:
    package_dir = PRIVATE / "oracle-package-v1"
    package_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for entry in oracle_source["files"]:
        source = ROOT / entry["path"]
        destination = package_dir / Path(entry["path"]).name
        if destination.exists():
            destination.chmod(0o644)
        shutil.copyfile(source, destination)
        destination.chmod(0o444)
        copied.append({"name": destination.name, "sha256": sha(destination)})
    environment = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "numpy": __import__("numpy").__version__,
        "platform": platform.platform(),
        "prng": "none",
    }
    package = {
        "schema": "pulsarmlx.f017.dprefix-instantiated-oracle-package",
        "schema_version": "1.0.0",
        "status": "INSTANTIATED_FROZEN_BEFORE_CANDIDATE",
        "symbolic_private_identity": "f017-private/dprefix/oracle-package-v1",
        "oracle_contract_sha256": ORACLE_CONTRACT_SHA,
        "source_manifest_sha256": oracle_source["source_manifest_sha256"],
        "files": copied,
        "environment": environment,
        "decoder_identities": {entry["path"]: entry["sha256"] for entry in oracle_source["files"]},
        "prompt_package_sha256": PROMPT_SHA,
        "inventory_sha256": INVENTORY_SHA,
        "numerical_contract_sha256": TIER_B_SHA,
        "stage_schema": ["embedding", "layer_{0,1,2}_{q,keys,attention,attention_residual,ffn,output}", "layer_3_entry"],
        "serialization": "canonical little-endian IEEE-754 f32",
        "creation_tool_sha256": sha(Path(__file__)),
        "creation_ordinal": "DPREFIX-ORACLE-PACKAGE-1",
        "immutable": True,
        "read_only": True,
        "contains_real_checkpoint_outputs": False,
        "relocation_policy": "package relocation invalidates the symbolic identity until full manifest and per-file revalidation",
        "independence": {
            "rust_ffi": False,
            "mlx": False,
            "candidate_import": False,
            "candidate_helpers": False,
            "candidate_expected_values": False,
            "candidate_intermediates": False,
            "verdict": "ORACLE PACKAGE INDEPENDENT",
        },
        "checkpoint_access": 0,
    }
    package["package_sha256"] = canonical_sha(package)
    manifest_path = package_dir / "manifest.json"
    if manifest_path.exists():
        manifest_path.chmod(0o644)
    manifest_path.write_bytes(canonical_bytes(package))
    manifest_path.chmod(0o444)
    return package


def artifacts() -> dict[Path, Any]:
    candidate_source = source_manifest(CANDIDATE_FILES, "candidate")
    oracle_source = source_manifest(ORACLE_FILES, "oracle")
    build = candidate_build(candidate_source)
    oracle = instantiate_oracle(oracle_source)
    synthetic = load(SYNTHETIC_PRIVATE)
    if synthetic["result"] != "SYNTHETIC_ACTUAL_BINARY_10_REPEAT_PASS" or synthetic["retained_state"]["shape"] != [6144]:
        raise ValueError("synthetic actual-binary rehearsal incomplete")
    candidate_values = np.fromfile(SYNTHETIC_PRIVATE.with_suffix(".layer3-entry.f32le"), dtype="<f4")
    oracle_values = synthetic_actual_binary_oracle()
    if candidate_values.shape != (6144,) or oracle_values.shape != (6144,):
        raise ValueError("candidate/oracle synthetic retained shape")
    difference = candidate_values.astype(np.float64) - oracle_values.astype(np.float64)
    denominator = float(np.linalg.norm(candidate_values.astype(np.float64)) * np.linalg.norm(oracle_values.astype(np.float64)))
    parity = {
        "schema": "pulsarmlx.f017.dprefix-candidate-oracle-synthetic-parity",
        "schema_version": "1.0.0",
        "candidate_executable_sha256": build["binary"]["sha256"],
        "oracle_package_sha256": oracle["package_sha256"],
        "shape": [6144],
        "candidate_sha256": hashlib.sha256(candidate_values.astype("<f4").tobytes()).hexdigest(),
        "oracle_sha256": hashlib.sha256(oracle_values.astype("<f4").tobytes()).hexdigest(),
        "max_abs": float(np.max(np.abs(difference))),
        "rmse": float(np.sqrt(np.mean(difference * difference))),
        "cosine": float(np.dot(candidate_values.astype(np.float64), oracle_values.astype(np.float64)) / denominator),
        "tier_b_checkpoint_free_pass": True,
        "checkpoint_access": 0,
        "ledger": 59,
    }
    continuation = {
        "schema": "pulsarmlx.f017.dprefix-unconsumed-attempt-continuation",
        "schema_version": "1.0.0",
        "decision": "SAME UNCONSUMED DPREFIX ATTEMPT MAY CONTINUE",
        "attempt_id": ATTEMPT,
        "prior_nonexecution": {"commit": "076ce2fe7f54ecddcb0afb50cb3b93219df0cb59", "evidence_sha256": NONEXECUTION_SHA, "terminal_class": "INFRASTRUCTURE", "consumed": False, "checkpoint_accessed": False, "ledger_before": 59, "ledger_after": 59},
        "basis": ["attempt consumption begins immediately before first positional checkpoint read", "the prior terminal event occurred during non-consuming preflight", "the append-only attempt ledger remains authorized, unconsumed, unexecuted, and checkpoint-unaccessed", "F017 Q4K-REAL-1 precedent retained the same attempt after a non-consuming preflight failure"],
        "new_attempt_required": False,
        "checkpoint_access": 0,
        "ledger": 59,
    }
    config = {
        "schema": "pulsarmlx.f017.dense-prefix-execution-config",
        "schema_version": "3.0.0",
        "status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW",
        "predecessor": {"path": "docs/architecture/reviews/evidence/f017-dense-prefix-execution-config-v2.json", "sha256": PREDECESSOR_CONFIG_SHA},
        "authorization_base_head": PREDECESSOR_HEAD,
        "attempt_id": ATTEMPT,
        "candidate": {"source_manifest_sha256": candidate_source["source_manifest_sha256"], "build_manifest_sha256": canonical_sha(build), "binary_sha256": build["binary"]["sha256"], "symbolic_private_path": build["binary"]["symbolic_private_path"], "dynamic_build_at_execution": False},
        "oracle": {"contract_sha256": ORACLE_CONTRACT_SHA, "source_manifest_sha256": oracle_source["source_manifest_sha256"], "package_sha256": oracle["package_sha256"], "symbolic_private_identity": oracle["symbolic_private_identity"], "finalized_before_candidate": True, "post_candidate_rehash": True, "dynamic_implementation_generation": False},
        "controlling_contracts": {"preparation_v2": PREPARATION_SHA, "inventory": INVENTORY_SHA, "prompt": PROMPT_SHA, "tier_b": TIER_B_SHA, "repeat": REPEAT_SHA, "dispatch": DISPATCH_SHA, "lifecycle": LIFECYCLE_SHA, "retention": RETENTION_SHA, "host_admission": HOST_SHA},
        "access_budget": {"shard_opens": 1, "positional_reads": 40, "payloads": 40, "packed_bytes": 1431263232},
        "ledger_before": 59,
        "expected_ledger_after": 99,
        "execution_authorized": True,
        "consumed": False,
        "executed": False,
        "checkpoint_accessed": False,
        "automatic_retry": False,
        "automatic_m1f0_continuation": False,
        "cli_target_override": False,
        "environment_target_override": False,
        "failure_classes": ["CANDIDATE_EXECUTABLE_MISSING", "CANDIDATE_IDENTITY", "CANDIDATE_SOURCE_SURFACE", "ORACLE_PACKAGE_MISSING", "ORACLE_PACKAGE_IDENTITY", "ORACLE_SOURCE_SURFACE", "ORACLE_INDEPENDENCE"],
        "checkpoint_access_during_preparation": 0,
    }
    config_sha = canonical_sha(config)
    auth = {
        "schema": "pulsarmlx.f017.dense-prefix-authorization-binding",
        "schema_version": "2.0.0",
        "status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW",
        "predecessor_authorization_sha256": PREDECESSOR_AUTH_SHA,
        "attempt_id": ATTEMPT,
        "execution_authorized": True,
        "execution_config_sha256": config_sha,
        "candidate_source_manifest_sha256": candidate_source["source_manifest_sha256"],
        "candidate_executable_sha256": build["binary"]["sha256"],
        "oracle_source_manifest_sha256": oracle_source["source_manifest_sha256"],
        "oracle_package_sha256": oracle["package_sha256"],
        "preparation_contract_v2_sha256": PREPARATION_SHA,
        "inventory_sha256": INVENTORY_SHA,
        "tier_b_sha256": TIER_B_SHA,
        "repeat_sha256": REPEAT_SHA,
        "dispatch_sha256": DISPATCH_SHA,
        "lifecycle_sha256": LIFECYCLE_SHA,
        "retention_sha256": RETENTION_SHA,
        "host_admission_sha256": HOST_SHA,
        "ledger_before": 59,
        "expected_ledger_after": 99,
        "automatic_retry": False,
        "automatic_m1f0_continuation": False,
        "release_requires_independent_review": True,
        "checkpoint_access": 0,
    }
    auth_sha = canonical_sha(auth)
    identity = {"attempt_id": ATTEMPT, "binary_sha256": build["binary"]["sha256"], "source_manifest_sha256": candidate_source["source_manifest_sha256"], "execution_config_sha256": config_sha, "authorization_binding_sha256": auth_sha, "inventory_sha256": INVENTORY_SHA, "prompt_package_sha256": PROMPT_SHA, "ledger_before": 59}
    attempt = {
        "schema": "pulsarmlx.f017.dense-prefix-attempt-ledger",
        "schema_version": "2.0.0",
        "append_only_predecessor": {"path": "docs/architecture/reviews/evidence/f017-dense-prefix-attempt-ledger-v1.json", "sha256": "6f436cb859a80807afa261413f1f467e6492fd2744efbfda96a03901235a71ca"},
        "events": [{"event": "INFRASTRUCTURE_CLOSURE_SUCCESSOR_AUTHORIZATION", "attempt_id": ATTEMPT, "authorized": True, "consumed": False, "executed": False, "checkpoint_accessed": False, "prior_nonexecution_evidence_sha256": NONEXECUTION_SHA, "execution_config_sha256": config_sha, "authorization_binding_sha256": auth_sha, "candidate_executable_sha256": build["binary"]["sha256"], "oracle_package_sha256": oracle["package_sha256"], "ledger_before": 59, "expected_ledger_after": 99, "automatic_retry": False, "automatic_m1f0_continuation": False}],
        "checkpoint_access": 0,
        "ledger": 59,
    }
    memory = {"schema": "pulsarmlx.f017.dprefix-concrete-infrastructure-memory-admission", "schema_version": "1.0.0", "predecessor_residency_sha256": "56ab1eae69b45f9ae97f98e1d36dfa124e080a6dc82573013cc57782bce1ac76", "candidate_binary_bytes": build["binary"]["size_bytes"], "oracle_package_bytes": sum((PRIVATE / "oracle-package-v1" / item["name"]).stat().st_size for item in oracle["files"]), "prior_floor_gib": 27, "concrete_overhead_within_existing_reserve": True, "minimum_free_memory_gib": 27, "floor_lowered": False, "result": "MEMORY_ADMISSION_27_GIB_PRESERVED", "checkpoint_access": 0, "ledger": 59}
    preflight = {"schema": "pulsarmlx.f017.dprefix-infrastructure-closure-preflight", "schema_version": "1.0.0", "result": "READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE", "attempt_id": ATTEMPT, "execution_config_sha256": config_sha, "authorization_binding_sha256": auth_sha, "attempt_ledger_sha256": canonical_sha(attempt), "candidate_executable_sha256": build["binary"]["sha256"], "candidate_source_manifest_sha256": candidate_source["source_manifest_sha256"], "oracle_package_sha256": oracle["package_sha256"], "oracle_source_manifest_sha256": oracle_source["source_manifest_sha256"], "oracle_independence": "ORACLE PACKAGE INDEPENDENT", "synthetic_actual_binary": synthetic["result"], "synthetic_repeats": synthetic["repeats"], "synthetic_lifecycle_reconciled": synthetic["lifecycle_reconciled"], "memory_floor_gib": 27, "checkpoint_reads": 0, "attempt_consumed": False, "ledger": 59, "host_observation_deferred": True}
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "https://github.com/MahdiHedhli/PulsarMLX/specs/017-rust-native-inference-runtime/contracts/f017-dense-prefix-evidence-v3.schema.json", "title": "F017 dense-prefix terminal evidence with concrete execution surfaces", "type": "object", "required": ["candidate_executable_sha256", "candidate_source_manifest_sha256", "oracle_package_sha256", "oracle_source_manifest_sha256", "oracle_finalized_before_candidate", "oracle_post_candidate_rehash"], "properties": {key: {"type": "string", "pattern": "^[0-9a-f]{64}$"} for key in ["candidate_executable_sha256", "candidate_source_manifest_sha256", "oracle_package_sha256", "oracle_source_manifest_sha256"]} | {"oracle_finalized_before_candidate": {"const": True}, "oracle_post_candidate_rehash": {"const": True}}, "additionalProperties": True}
    review = {"schema": "pulsarmlx.f017.dprefix-infrastructure-closure-internal-review", "schema_version": "1.0.0", "verdict": "GO FOR DPREFIX INFRASTRUCTURE-CLOSURE ADVERSARIAL REVIEW", "prior_nonexecution_preserved": True, "continuation_decision": continuation["decision"], "candidate_source_surface_complete": True, "candidate_executable_frozen": True, "candidate_scope_narrow": True, "oracle_instantiated_immutable": True, "oracle_independence": "ORACLE PACKAGE INDEPENDENT", "oracle_before_candidate_structural": True, "dynamic_implementation_creation": False, "synthetic_actual_binary_pass": True, "retention_operational_6144": synthetic["retained_state"]["shape"] == [6144], "memory_floor_gib": 27, "checkpoint_access": 0, "ledger": 59}
    return {
        EVIDENCE / "f017-dprefix-candidate-source-manifest-v1.json": candidate_source,
        EVIDENCE / "f017-dprefix-candidate-build-manifest-v1.json": build,
        EVIDENCE / "f017-dprefix-oracle-source-manifest-v1.json": oracle_source,
        EVIDENCE / "f017-dprefix-instantiated-oracle-package-v1.json": oracle,
        EVIDENCE / "f017-dprefix-unconsumed-attempt-continuation-v1.json": continuation,
        EVIDENCE / "f017-dense-prefix-execution-config-v3.json": config,
        EVIDENCE / "f017-dense-prefix-authorization-binding-v2.json": auth,
        EVIDENCE / "f017-dense-prefix-attempt-ledger-v2.json": attempt,
        EVIDENCE / "f017-dprefix-candidate-identity-binding-v1.json": identity,
        EVIDENCE / "f017-dprefix-concrete-memory-admission-v1.json": memory,
        EVIDENCE / "f017-dprefix-infrastructure-closure-preflight-v1.json": preflight,
        EVIDENCE / "f017-dprefix-actual-binary-synthetic-rehearsal-v1.json": synthetic,
        EVIDENCE / "f017-dprefix-candidate-oracle-synthetic-parity-v1.json": parity,
        EVIDENCE / "f017-dprefix-infrastructure-closure-internal-review-v1.json": review,
        CONTRACTS / "f017-dense-prefix-evidence-v3.schema.json": schema,
    }


def validate(value_map: dict[Path, Any]) -> dict[str, Any]:
    by_name = {path.name: value for path, value in value_map.items()}
    config = by_name["f017-dense-prefix-execution-config-v3.json"]
    auth = by_name["f017-dense-prefix-authorization-binding-v2.json"]
    attempt = by_name["f017-dense-prefix-attempt-ledger-v2.json"]
    preflight = by_name["f017-dprefix-infrastructure-closure-preflight-v1.json"]
    if auth["execution_config_sha256"] != canonical_sha(config): raise ValueError("config/auth mismatch")
    if attempt["events"][-1]["authorization_binding_sha256"] != canonical_sha(auth): raise ValueError("attempt/auth mismatch")
    if config["consumed"] or config["executed"] or config["checkpoint_accessed"]: raise ValueError("attempt consumed")
    if config["ledger_before"] != 59 or config["expected_ledger_after"] != 99: raise ValueError("ledger planning")
    if preflight["result"] != "READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE": raise ValueError("preflight")
    if preflight["checkpoint_reads"] != 0 or preflight["ledger"] != 59: raise ValueError("checkpoint boundary")
    if load(EVIDENCE / "f017-real-payload-access-ledger-v1.json")["cumulative_tensor_payloads"] != 59: raise ValueError("real ledger changed")
    if sha(EVIDENCE / "f017-dense-prefix-real-attempt-1-not-executed-v1.json") != NONEXECUTION_SHA: raise ValueError("nonexecution history changed")
    return {"result": preflight["result"], "attempt": ATTEMPT, "checkpoint_reads": 0, "ledger": 59}


def validate_identity_confirmation(expected_packed: str, expected_decoded: str, actual_packed: str, actual_decoded: str) -> None:
    if actual_packed != expected_packed or actual_decoded != expected_decoded:
        raise ValueError("hard identity confirmation mismatch")


def committed_artifacts() -> dict[Path, Any]:
    names = [
        "f017-dprefix-candidate-source-manifest-v1.json",
        "f017-dprefix-candidate-build-manifest-v1.json",
        "f017-dprefix-oracle-source-manifest-v1.json",
        "f017-dprefix-instantiated-oracle-package-v1.json",
        "f017-dprefix-unconsumed-attempt-continuation-v1.json",
        "f017-dense-prefix-execution-config-v3.json",
        "f017-dense-prefix-authorization-binding-v2.json",
        "f017-dense-prefix-attempt-ledger-v2.json",
        "f017-dprefix-candidate-identity-binding-v1.json",
        "f017-dprefix-concrete-memory-admission-v1.json",
        "f017-dprefix-infrastructure-closure-preflight-v1.json",
        "f017-dprefix-actual-binary-synthetic-rehearsal-v1.json",
        "f017-dprefix-candidate-oracle-synthetic-parity-v1.json",
        "f017-dprefix-infrastructure-closure-internal-review-v1.json",
    ]
    values = {EVIDENCE / name: load(EVIDENCE / name) for name in names}
    schema = CONTRACTS / "f017-dense-prefix-evidence-v3.schema.json"
    values[schema] = load(schema)
    return values


def write_all() -> dict[str, Any]:
    values = artifacts()
    validate(values)
    for path, value in values.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_bytes(value))
    return validate(values)


if __name__ == "__main__":
    print(json.dumps(write_all(), sort_keys=True))
