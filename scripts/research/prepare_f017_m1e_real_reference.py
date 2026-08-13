#!/usr/bin/env python3
"""Independent bounded M1-E oracle preparer.

This module intentionally imports only the independent NumPy decoders. It
does not import Rust, MLX, FFI, ctypes/cffi, or candidate output. The real
entrypoint is used only by a separately authorized attempt; checkpoint-free
tests exercise the same functions with synthetic packed matrices.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import time
from pathlib import Path

import numpy as np

from iq2_xxs_dequant import dequantize_matrix_iq2_xxs_numpy
from iq3_xxs_dequant import dequantize_matrix_iq3_xxs_numpy

U = 2.0 ** -24
ETA = 2.0 ** -149
SILU_DERIVATIVE_BOUND = 1.1
EXECUTION_CONFIG_SCHEMA = "pulsarmlx.f017.m1e-execution-config"
EXECUTION_CONFIG_VERSION = "3.0.0"
EXECUTION_ATTEMPT = 3
EXECUTION_READY = "READY_TO_EXECUTE_M1_E"
PREPARER_INPUT_CONTRACT = (
    "specs/017-rust-native-inference-runtime/contracts/"
    "m1e-real-reference-preparer-input-v3.json"
)
DECODER_CONTRACT_SHA256 = "9a92bacda92e999a9062c154acd1b52c86e1d644f0d4d697defb2db40a85ce84"
ACTIVATION_PAYLOAD_SHA256 = "732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149"
ACTIVATION_PATH = "specs/017-rust-native-inference-runtime/fixtures/f017-m1e-activation-v1.json"
ACTIVATION_ARTIFACT_SHA256 = "a5946ba6f07d4be7c13da28549a0585b90a4ca8fa3824f52d2afd0f0b582f5c8"
PRIOR_EVIDENCE = {
    "m1_a": "aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805",
    "m1_b": "9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770",
    "m1_c": "343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e",
    "m1_d": "dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c",
    "m1_e_attempt_1": "346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119",
    "m1_e_attempt_2": "8912e523963cfa8822fe6472ec30be31a78c4c3648fba34caf6c41055efd7e00",
}
CHECKPOINT_BINDINGS = {
    "checkpoint_set_sha256": "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
    "catalog_sha256": "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0",
    "tensor_map_sha256": "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223",
}
REPOSITORY_ARTIFACT_PATHS = {
    "attempt_3_handoff": "docs/architecture/reviews/f017-m1-e-attempt-3-handoff.md",
    "boundary_contract": "specs/017-rust-native-inference-runtime/contracts/m1e-expert-boundary-v1.json",
    "decoder_contract": "specs/017-rust-native-inference-runtime/contracts/m1e-decoder-contract-v2.json",
    "scaffold_contract": "specs/017-rust-native-inference-runtime/contracts/m1e-exact-scaffold-v1.json",
    "tier_b_contract": "specs/017-rust-native-inference-runtime/contracts/m1e-expert-tier-b-v1.json",
    "repeat_integrity_contract": "specs/017-rust-native-inference-runtime/contracts/m1e-repeat-integrity-v1.json",
    "timing_contract": "specs/017-rust-native-inference-runtime/contracts/m1e-timing-v1.json",
    "evidence_schema": "specs/017-rust-native-inference-runtime/contracts/m1e-evidence-v1.schema.json",
    "execution_config_schema": "specs/017-rust-native-inference-runtime/contracts/m1e-execution-config-v3.schema.json",
    "preparer_input_contract": PREPARER_INPUT_CONTRACT,
    "path_resolution_contract": "specs/017-rust-native-inference-runtime/contracts/m1d-artifact-path-resolution-v1.json",
    "trusted_repository_identity_contract": "specs/017-rust-native-inference-runtime/contracts/trusted-repository-identity-v2.json",
    "activation_generator": "scripts/research/generate_f017_m1e_activation.py",
    "execution_config_preparer": "scripts/research/prepare_f017_m1e_execution.py",
    "authorized_launcher": "scripts/research/run_f017_m1e_authorized.py",
    "real_reference_preparer": "scripts/research/prepare_f017_m1e_real_reference.py",
    "independent_iq2_decoder": "scripts/research/iq2_xxs_dequant.py",
    "independent_iq3_decoder": "scripts/research/iq3_xxs_dequant.py",
    "third_iq3_decoder": "scripts/research/iq3_xxs_spec_decoder.py",
    "iq3_order_regression": "specs/017-rust-native-inference-runtime/fixtures/f017-iq3-xxs-order-regression-v1.json",
}
REPOSITORY_ARTIFACT_ROLES = set(REPOSITORY_ARTIFACT_PATHS)
TOP_LEVEL_FIELDS = {
    "schema", "schema_version", "status", "attempt", "attempt_consumed",
    "compiled_runtime_sha", "tooling_sha", "authorization_head_sha",
    "trusted_repository_identity", "executable_identity", "repository_root",
    "package_root", "activation_fixture", "activation_payload_sha256",
    "repository_artifacts", "local_artifacts", "prior_evidence",
    "checkpoint_bindings", "expert", "tensors", "runner", "execution",
}


def f32_bytes(values: np.ndarray) -> bytes:
    return np.asarray(values, dtype="<f4").tobytes(order="C")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_matvec(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    rows, columns = matrix.shape
    if vector.shape != (columns,):
        raise ValueError("matvec shape mismatch")
    total = np.zeros(rows, dtype=np.float32)
    for column in range(columns):
        product = np.multiply(matrix[:, column], vector[column], dtype=np.float32)
        total = np.add(total, product, dtype=np.float32)
    return total


def strict_silu(gate: np.ndarray) -> np.ndarray:
    negative = np.negative(gate, dtype=np.float32)
    exponential = np.exp(negative, dtype=np.float32)
    denominator = np.add(np.float32(1.0), exponential, dtype=np.float32)
    return np.divide(gate, denominator, dtype=np.float32)


def strict_swiglu(gate: np.ndarray, up: np.ndarray) -> np.ndarray:
    return np.multiply(strict_silu(gate), up, dtype=np.float32)


def gamma(operations: int) -> float:
    return (operations * U) / (1.0 - operations * U)


def matvec_bounds(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    n = matrix.shape[1]
    l1 = np.sum(np.abs(matrix.astype(np.float64) * vector.astype(np.float64)), axis=1)
    return 2.0 * gamma(2 * n) * l1 + 4.0 * n * ETA


def composed_bounds(
    gate_matrix: np.ndarray,
    up_matrix: np.ndarray,
    down_matrix: np.ndarray,
    activation: np.ndarray,
    gate: np.ndarray,
    up: np.ndarray,
    hidden: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    gate_bound = matvec_bounds(gate_matrix, activation)
    up_bound = matvec_bounds(up_matrix, activation)
    silu = strict_silu(gate).astype(np.float64)
    preceding = (
        np.abs(up.astype(np.float64)) * SILU_DERIVATIVE_BOUND * gate_bound
        + np.abs(silu) * up_bound
        + SILU_DERIVATIVE_BOUND * gate_bound * up_bound
    )
    hidden_bound = preceding + 4.0 * U * (np.abs(hidden.astype(np.float64)) + preceding) + 4.0 * ETA
    down_reduction = matvec_bounds(down_matrix, hidden)
    propagation_l1 = np.sum(np.abs(down_matrix.astype(np.float64)) * hidden_bound, axis=1)
    final_bound = down_reduction + propagation_l1 * (1.0 + gamma(2 * hidden.size)) + 4.0 * hidden.size * ETA
    return gate_bound, up_bound, hidden_bound, final_bound


def prepare(gate_packed: bytes, up_packed: bytes, down_packed: bytes, activation: np.ndarray) -> dict[str, object]:
    started = time.time_ns()
    gate_decode_started = time.perf_counter_ns()
    gate_matrix = dequantize_matrix_iq2_xxs_numpy(gate_packed, 2048, 6144)
    gate_decode_seconds = (time.perf_counter_ns() - gate_decode_started) / 1e9
    up_decode_started = time.perf_counter_ns()
    up_matrix = dequantize_matrix_iq2_xxs_numpy(up_packed, 2048, 6144)
    up_decode_seconds = (time.perf_counter_ns() - up_decode_started) / 1e9
    down_decode_started = time.perf_counter_ns()
    down_matrix = dequantize_matrix_iq3_xxs_numpy(down_packed, 6144, 2048)
    down_decode_seconds = (time.perf_counter_ns() - down_decode_started) / 1e9
    gate_started = time.perf_counter_ns()
    gate = strict_matvec(gate_matrix, activation)
    gate_seconds = (time.perf_counter_ns() - gate_started) / 1e9
    up_started = time.perf_counter_ns()
    up = strict_matvec(up_matrix, activation)
    up_seconds = (time.perf_counter_ns() - up_started) / 1e9
    activation_started = time.perf_counter_ns()
    hidden = strict_swiglu(gate, up)
    activation_seconds = (time.perf_counter_ns() - activation_started) / 1e9
    down_started = time.perf_counter_ns()
    output = strict_matvec(down_matrix, hidden)
    down_seconds = (time.perf_counter_ns() - down_started) / 1e9
    bounds = composed_bounds(gate_matrix, up_matrix, down_matrix, activation, gate, up, hidden)
    completed = time.time_ns()
    stages = {"gate": gate, "up": up, "activated_hidden": hidden, "final_output": output}
    return {
        "schema": "pulsarmlx.f017.m1e-oracle-package",
        "schema_version": "1.0.0",
        "generator": {"implementation": "independent_python_numpy", "source_sha256": "TO_BE_BOUND_BY_EXECUTION_CONFIG"},
        "matrices": {
            "gate": {"packed_sha256": sha(gate_packed), "decoded_sha256": sha(f32_bytes(gate_matrix))},
            "up": {"packed_sha256": sha(up_packed), "decoded_sha256": sha(f32_bytes(up_matrix))},
            "down": {"packed_sha256": sha(down_packed), "decoded_sha256": sha(f32_bytes(down_matrix))},
        },
        "activation": {"sha256": sha(f32_bytes(activation)), "bytes_hex": f32_bytes(activation).hex(), "element_count": 6144},
        "stages": {name: {"sha256": sha(f32_bytes(value)), "bytes_hex": f32_bytes(value).hex()} for name, value in stages.items()},
        "bounds": {
            name: {"sha256": sha(np.asarray(value, dtype="<f8").tobytes()), "f64_hex": np.asarray(value, dtype="<f8").tobytes().hex()}
            for name, value in zip(("gate", "up", "activated_hidden", "final_output"), bounds)
        },
        "derived_global": {
            "max_absolute_bound": float(np.max(bounds[-1])),
            "rmse_bound": float(np.sqrt(np.mean(np.square(bounds[-1])))),
            "cosine_minimum": float(max(0.0, (np.linalg.norm(output.astype(np.float64)) - np.linalg.norm(bounds[-1])) / (np.linalg.norm(output.astype(np.float64)) + np.linalg.norm(bounds[-1])))) if np.linalg.norm(output.astype(np.float64)) > np.linalg.norm(bounds[-1]) else None,
        },
        "timings": {
            "decoder_gate_seconds": gate_decode_seconds,
            "decoder_up_seconds": up_decode_seconds,
            "decoder_down_seconds": down_decode_seconds,
            "oracle_gate_seconds": gate_seconds,
            "oracle_up_seconds": up_seconds,
            "oracle_activation_seconds": activation_seconds,
            "oracle_down_seconds": down_seconds,
        },
        "finalization": {
            "preparation_started_at": str(started),
            "oracle_completed_at": str(completed),
            "completion_marker": "m1e_oracle_finalized_sequence_0",
            "immutable_after_finalization": True,
        },
    }


def exclusive_finalize(path: Path, document: dict[str, object]) -> str:
    raw = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    path.chmod(stat.S_IRUSR)
    return sha(raw)


def exclusive_bytes(path: Path, payload: bytes) -> str:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    path.chmod(stat.S_IRUSR)
    return sha(payload)


def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _exact_fields(value: object, fields: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} field set mismatch")
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{label} is not a canonical SHA-256")
    return value


def _git_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{label} is not a canonical Git SHA")
    return value


def oracle_semantic_projection(config: dict[str, object]) -> dict[str, object]:
    """Return the only fields permitted to influence oracle numbers."""
    artifacts = config["repository_artifacts"]
    return {
        "expert": config["expert"],
        "tensors": config["tensors"],
        "activation_fixture": config["activation_fixture"],
        "activation_payload_sha256": config["activation_payload_sha256"],
        "checkpoint_bindings": config["checkpoint_bindings"],
        "boundary_contract": artifacts["boundary_contract"],
        "decoder_contract": artifacts["decoder_contract"],
        "scaffold_contract": artifacts["scaffold_contract"],
        "tier_b_contract": artifacts["tier_b_contract"],
        "independent_iq2_decoder": artifacts["independent_iq2_decoder"],
        "independent_iq3_decoder": artifacts["independent_iq3_decoder"],
        "third_iq3_decoder": artifacts["third_iq3_decoder"],
    }


def validate_execution_config_v3(config: dict[str, object], repository_root: Path | None = None) -> None:
    """Fail closed on schema/identity ambiguity before any checkpoint read."""
    _exact_fields(config, TOP_LEVEL_FIELDS, "execution config")
    if (
        config["schema"] != EXECUTION_CONFIG_SCHEMA
        or config["schema_version"] != EXECUTION_CONFIG_VERSION
        or config["status"] != EXECUTION_READY
        or config["attempt"] != EXECUTION_ATTEMPT
        or config["attempt_consumed"] is not False
    ):
        raise ValueError("M1-E execution config identity mismatch")
    for field in ("compiled_runtime_sha", "tooling_sha", "authorization_head_sha"):
        _git_sha(config[field], field)
    trusted = _exact_fields(
        config["trusted_repository_identity"],
        {"contract_version", "contract_sha256", "compiled_runtime_sha", "tooling_sha", "authorization_head_sha", "runtime_drift_classification_sha256"},
        "trusted repository identity",
    )
    if trusted["contract_version"] != "f017-trusted-repository-identity-v2":
        raise ValueError("trusted repository identity version mismatch")
    for field in ("compiled_runtime_sha", "tooling_sha", "authorization_head_sha"):
        if trusted[field] != config[field]:
            raise ValueError("trusted repository identity binding mismatch")
    _sha256(trusted["contract_sha256"], "identity contract")
    _sha256(trusted["runtime_drift_classification_sha256"], "runtime drift classification")
    executable = _exact_fields(config["executable_identity"], {"sha256", "build_profile", "architecture", "feature_flags"}, "executable identity")
    _sha256(executable["sha256"], "executable")
    if executable["build_profile"] != "release" or executable["architecture"] != "aarch64" or executable["feature_flags"] != ["pulsar_native_mlx"]:
        raise ValueError("executable identity mismatch")
    repository = _exact_fields(config["repository_root"], {"path_kind", "path", "identity"}, "repository root")
    package = _exact_fields(config["package_root"], {"path_kind", "path", "identity"}, "package root")
    if repository["path_kind"] != "absolute_private_local" or repository["identity"] != config["authorization_head_sha"]:
        raise ValueError("repository root binding mismatch")
    if package["path_kind"] != "absolute_private_local" or package["identity"] != "m1e_attempt_3_private_package_root":
        raise ValueError("package root binding mismatch")
    artifacts = config["repository_artifacts"]
    if not isinstance(artifacts, dict) or set(artifacts) != REPOSITORY_ARTIFACT_ROLES:
        raise ValueError("repository artifact role set mismatch")
    for role, artifact in artifacts.items():
        artifact = _exact_fields(artifact, {"path_kind", "symbolic_path", "content_sha256", "logical_role"}, role)
        if artifact["path_kind"] != "repository_relative" or artifact["logical_role"] != role:
            raise ValueError(f"{role} repository artifact binding mismatch")
        if artifact["symbolic_path"] != REPOSITORY_ARTIFACT_PATHS[role]:
            raise ValueError(f"{role} symbolic path mismatch")
        symbolic = Path(artifact["symbolic_path"])
        if symbolic.is_absolute() or ".." in symbolic.parts:
            raise ValueError(f"{role} symbolic path is unsafe")
        _sha256(artifact["content_sha256"], role)
    if artifacts["preparer_input_contract"]["symbolic_path"] != PREPARER_INPUT_CONTRACT:
        raise ValueError("preparer input contract path mismatch")
    activation = _exact_fields(config["activation_fixture"], {"path_kind", "symbolic_path", "content_sha256", "logical_role"}, "activation fixture")
    if activation["path_kind"] != "repository_relative" or activation["logical_role"] != "activation_fixture" or activation["symbolic_path"] != ACTIVATION_PATH or activation["content_sha256"] != ACTIVATION_ARTIFACT_SHA256:
        raise ValueError("activation fixture binding mismatch")
    _sha256(activation["content_sha256"], "activation fixture")
    if config["activation_payload_sha256"] != ACTIVATION_PAYLOAD_SHA256:
        raise ValueError("activation payload identity mismatch")
    if config["prior_evidence"] != PRIOR_EVIDENCE or config["checkpoint_bindings"] != CHECKPOINT_BINDINGS:
        raise ValueError("prior evidence/checkpoint binding mismatch")
    if config["expert"] != {"layer": 3, "expert": 15, "symbolic_id": "blk.3.expert.15"}:
        raise ValueError("expert identity mismatch")
    tensors = config["tensors"]
    if not isinstance(tensors, list) or len(tensors) != 3 or {t.get("role") for t in tensors if isinstance(t, dict)} != {"gate", "up", "down"}:
        raise ValueError("one-expert tensor set mismatch")
    expected_tensors = {
        "gate": ("blk.3.ffn_gate_exps.weight", "IQ2_XXS", [6144, 2048, 256], [2048, 6144], 3423197024, 3244032, 1584, "42e379023728565d323fff8b120f2c6dff6fa50f10d9ad1cceb3e3597af36354"),
        "up": ("blk.3.ffn_up_exps.weight", "IQ2_XXS", [6144, 2048, 256], [2048, 6144], 4268636000, 3244032, 1584, "011ccab7ca2293da5b0d1112172b2dccd4b2cdb2482672dd217f996280223119"),
        "down": ("blk.3.ffn_down_exps.weight", "IQ3_XXS", [2048, 6144, 256], [6144, 2048], 2203342688, 4816896, 784, "1c7a04eb897d242a621a09c6dfb78c3e92b407dff44ddf8cf67187dae50081e1"),
    }
    for tensor in tensors:
        _exact_fields(tensor, {"role", "name", "layer", "expert", "quantization", "gguf_shape", "logical_matrix_shape", "shard_ordinal", "offset", "packed_length", "packed_row_width", "catalog_entry_sha256", "decoder_contract_sha256", "path_kind", "allowed_read_count"}, f"{tensor.get('role')} tensor")
        expected = expected_tensors[tensor["role"]]
        observed = (tensor["name"], tensor["quantization"], tensor["gguf_shape"], tensor["logical_matrix_shape"], tensor["offset"], tensor["packed_length"], tensor["packed_row_width"], tensor["catalog_entry_sha256"])
        if observed != expected or tensor["layer"] != 3 or tensor["expert"] != 15 or tensor["shard_ordinal"] != 2 or tensor["path_kind"] != "bounded_checkpoint_range" or tensor["allowed_read_count"] != 1 or tensor["decoder_contract_sha256"] != DECODER_CONTRACT_SHA256:
            raise ValueError("tensor identity/decoder binding mismatch")
    runner = _exact_fields(config["runner"], {"mode", "memory_floor_bytes"}, "runner")
    if runner["mode"] not in {"fixture_expert", "real_expert"}:
        raise ValueError("runner mode mismatch")
    if config["execution"] != {"conceptual_expert_count": 1, "repeat_count": 10, "native_dispatch_count": 30, "maximum_payload_count": 3, "maximum_positional_reads": 3, "maximum_shard_opens": 1, "compressed_byte_budget": 11304960, "auto_retry": False, "stop_before_m1_f": True}:
        raise ValueError("execution bounds mismatch")
    local = _exact_fields(config["local_artifacts"], {"environment_manifest", "checkpoint_manifest", "runner_binary", "oracle_launcher", "target_shard", "oracle_output", "package_output", "attempt_state_output", "preflight_evidence_output", "evidence_output"}, "local artifacts")
    for role in ("environment_manifest", "checkpoint_manifest", "runner_binary", "oracle_launcher"):
        entry = _exact_fields(local[role], {"path_kind", "path", "content_sha256"}, role)
        if entry["path_kind"] != "absolute_private_local":
            raise ValueError(f"{role} path kind mismatch")
        _sha256(entry["content_sha256"], role)
    if local["runner_binary"]["content_sha256"] != executable["sha256"]:
        raise ValueError("runner/executable identity mismatch")
    target = _exact_fields(local["target_shard"], {"path_kind", "path", "ordinal", "basename", "byte_size", "content_sha256"}, "target shard")
    if target["path_kind"] != "absolute_private_local" or target["ordinal"] != 2:
        raise ValueError("target shard binding mismatch")
    _sha256(target["content_sha256"], "target shard")
    if repository_root is not None:
        root = repository_root.resolve(strict=True)
        for role, artifact in artifacts.items():
            resolved = (root / artifact["symbolic_path"]).resolve(strict=True)
            if root not in resolved.parents or resolved.is_symlink() or sha(resolved.read_bytes()) != artifact["content_sha256"]:
                raise ValueError(f"{role} repository artifact content mismatch")
        contract = json.loads((root / PREPARER_INPUT_CONTRACT).read_text(), object_pairs_hook=no_duplicates)
        if contract.get("contract_id") != "f017-m1e-real-reference-preparer-input-v3" or contract.get("supported_execution_config", {}).get("schema_version") != "3.0.0":
            raise ValueError("preparer input contract semantics mismatch")
    oracle_semantic_projection(config)


def read_exact_at(descriptor: int, offset: int, length: int) -> bytes:
    chunks: list[bytes] = []
    observed = 0
    while observed < length:
        chunk = os.pread(descriptor, length - observed, offset + observed)
        if not chunk:
            raise ValueError("short bounded checkpoint read")
        chunks.append(chunk)
        observed += len(chunk)
    return b"".join(chunks)


def prepare_from_config(config_path: Path, expected_sha256: str) -> str:
    raw = config_path.read_bytes()
    if sha(raw) != expected_sha256:
        raise ValueError("immutable M1-E execution config hash mismatch")
    config = json.loads(raw, object_pairs_hook=no_duplicates)
    validate_execution_config_v3(config)
    root = Path(config["repository_root"]["path"]).resolve(strict=True)
    validate_execution_config_v3(config, root)
    package_root = Path(config["package_root"]["path"]).resolve(strict=True)
    local = config["local_artifacts"]
    shard = Path(local["target_shard"]["path"])
    if shard.is_symlink() or not shard.is_file():
        raise ValueError("bound target shard is not a regular non-symlink file")
    source_binding = config["repository_artifacts"]["real_reference_preparer"]
    source_path = root / source_binding["symbolic_path"]
    if source_path.resolve(strict=True) != Path(__file__).resolve(strict=True) or sha(source_path.read_bytes()) != source_binding["content_sha256"]:
        raise ValueError("real-reference preparer source binding mismatch")
    activation_binding = config["activation_fixture"]
    activation_path = root / activation_binding["symbolic_path"]
    if sha(activation_path.read_bytes()) != activation_binding["content_sha256"]:
        raise ValueError("activation artifact hash mismatch")
    activation_doc = json.loads(activation_path.read_text(), object_pairs_hook=no_duplicates)
    activation = np.frombuffer(bytes.fromhex(activation_doc["activation"]["bytes_hex"]), dtype="<f4").copy()
    if sha(f32_bytes(activation)) != config["activation_payload_sha256"]:
        raise ValueError("activation payload hash mismatch")

    packed: dict[str, bytes] = {}
    descriptor = os.open(shard, os.O_RDONLY)
    try:
        for tensor in config["tensors"]:
            role = tensor["role"]
            if role in packed or role not in {"gate", "up", "down"} or tensor["allowed_read_count"] != 1:
                raise ValueError("one-expert tensor access set mismatch")
            packed[role] = read_exact_at(descriptor, tensor["offset"], tensor["packed_length"])
    finally:
        os.close(descriptor)
    if set(packed) != {"gate", "up", "down"}:
        raise ValueError("exactly three expert payloads are required")
    payload_references: dict[str, dict[str, object]] = {}
    for role in ("gate", "up", "down"):
        name = f"m1e-attempt-3-{role}-packed-v1.bin"
        digest = exclusive_bytes(package_root / name, packed[role])
        payload_references[role] = {
            "path_kind": "package_relative",
            "symbolic_path": name,
            "content_sha256": digest,
            "logical_role": f"{role}_packed_payload",
            "package_artifact_id": f"m1e-attempt-3-{role}-packed-v1",
        }

    oracle = prepare(packed["gate"], packed["up"], packed["down"], activation)
    oracle["generator"]["source_sha256"] = source_binding["content_sha256"]
    oracle_path = Path(local["oracle_output"])
    oracle_sha = exclusive_finalize(oracle_path, oracle)
    tensor_documents = []
    for tensor in config["tensors"]:
        tensor_documents.append({
            "role": tensor["role"], "name": tensor["name"], "shard_ordinal": tensor["shard_ordinal"],
            "offset": tensor["offset"], "packed_length": tensor["packed_length"],
            "quantization": tensor["quantization"], "matrix_shape": tensor["logical_matrix_shape"],
            "packed_sha256": payload_references[tensor["role"]]["content_sha256"],
            "payload": payload_references[tensor["role"]],
        })
    package = {
        "schema": "pulsarmlx.f017.m1e-package", "schema_version": "1.0.0",
        "package_kind": "production_reviewed" if config["runner"]["mode"] == "real_expert" else "checkpoint_free_fixture",
        "checkpoint_set_sha256": config["checkpoint_bindings"]["checkpoint_set_sha256"],
        "catalog_sha256": config["checkpoint_bindings"]["catalog_sha256"],
        "tensor_map_sha256": config["checkpoint_bindings"]["tensor_map_sha256"],
        "source_checkpoint_read_count": 3, "tensors": tensor_documents,
        "oracle": {"path_kind":"package_relative","symbolic_path":oracle_path.name,"content_sha256":oracle_sha,"logical_role":"independent_oracle","package_artifact_id":"m1e-attempt-3-real-oracle-v1"},
        "one_attempt": True,
    }
    return exclusive_finalize(Path(local["package_output"]), package)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", type=Path)
    parser.add_argument("--up", type=Path)
    parser.add_argument("--down", type=Path)
    parser.add_argument("--activation", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execution-config", type=Path)
    parser.add_argument("--execution-config-sha256")
    args = parser.parse_args()
    if args.execution_config is not None or args.execution_config_sha256 is not None:
        if args.execution_config is None or args.execution_config_sha256 is None or any(
            value is not None for value in (args.gate, args.up, args.down, args.activation, args.output)
        ):
            parser.error("config-only preparation requires exactly config path and hash")
        print(prepare_from_config(args.execution_config, args.execution_config_sha256))
        return 0
    if any(value is None for value in (args.gate, args.up, args.down, args.activation, args.output)):
        parser.error("legacy fixture preparation requires gate/up/down/activation/output")
    activation_doc = json.loads(args.activation.read_text())
    activation = np.frombuffer(bytes.fromhex(activation_doc["activation"]["bytes_hex"]), dtype="<f4").copy()
    digest = exclusive_finalize(args.output, prepare(args.gate.read_bytes(), args.up.read_bytes(), args.down.read_bytes(), activation))
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
