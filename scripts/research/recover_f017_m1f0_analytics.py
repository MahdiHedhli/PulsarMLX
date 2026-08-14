#!/usr/bin/env python3
"""One-shot analytical recovery for the accepted M1-F0 route.

The accepted route computation retained hashes but omitted the complete score
and ranking values.  This tool reads the already accepted twelve-payload
boundary once, executes the frozen independent NumPy oracle once, and exposes
analytical values only after every accepted identity reproduces exactly.
It never imports Rust or MLX and never accesses an expert tensor.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import platform
import shutil
import struct
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "pulsarmlx.f017.m1f0-analytical-recovery-config"
READY = "READY_TO_RECOVER_M1_F0_ANALYTICS"
U32 = 2.0**-24
ETA32 = 2.0**-149
U64 = 2.0**-53
RMS_EPS = float(np.float32(9.999999747378752e-6))


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(), object_pairs_hook=_reject_duplicates)


def _load(root: Path, relative: str, name: str):
    path = root / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _safe_file(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("path escape")
    resolved = (root / candidate).resolve(strict=True)
    canonical_root = root.resolve(strict=True)
    if canonical_root not in (resolved, *resolved.parents):
        raise ValueError("symlink escape")
    return resolved


def validate_config(repository_root: Path, config: dict[str, Any]) -> None:
    required = {
        "schema",
        "schema_version",
        "status",
        "source_identities",
        "accepted_bindings",
        "contracts",
        "input_state",
        "tensor_allowlist",
        "access_budget",
        "expected_identities",
        "scope",
    }
    if set(config) != required:
        raise ValueError("recovery config fields")
    if config["schema"] != SCHEMA or config["schema_version"] != "1.0.0":
        raise ValueError("recovery config schema")
    if config["status"] != "AUTHORIZED_FOR_EXACTLY_ONE_ANALYTICAL_RECOVERY_NOT_EXECUTED":
        raise ValueError("recovery state")
    source = config["source_identities"]
    tooling = source["tooling_commit_sha"]
    if _git(repository_root, "rev-parse", f"{tooling}^{{tree}}") != source["tooling_tree_oid"]:
        raise ValueError("tooling tree identity")
    if _git(repository_root, "merge-base", "--is-ancestor", tooling, "HEAD") != "":
        raise ValueError("tooling ancestry")
    changed = set(_git(repository_root, "diff", "--name-only", f"{tooling}..HEAD").splitlines())
    if not changed.issubset(set(source["permitted_post_tooling_paths"])):
        raise ValueError("post-tooling execution drift")
    if _git(repository_root, "status", "--porcelain"):
        raise ValueError("dirty worktree")
    if platform.python_version() != source["python"] or np.__version__ != source["numpy"]:
        raise ValueError("recovery Python/NumPy identity")
    for binding in config["accepted_bindings"].values():
        path = _safe_file(repository_root, binding["symbolic_path"])
        if file_sha256(path) != binding["sha256"]:
            raise ValueError(f"accepted binding identity: {binding['symbolic_path']}")
    for binding in config["contracts"].values():
        path = _safe_file(repository_root, binding["symbolic_path"])
        if file_sha256(path) != binding["sha256"]:
            raise ValueError(f"contract identity: {binding['symbolic_path']}")
    accepted_config = load_json(
        _safe_file(repository_root, config["accepted_bindings"]["execution_config"]["symbolic_path"])
    )
    if config["tensor_allowlist"] != accepted_config["tensor_allowlist"]:
        raise ValueError("accepted tensor allowlist identity")
    if config["input_state"] != accepted_config["input_state"]:
        raise ValueError("accepted input identity")
    budget = config["access_budget"]
    if budget != {
        "shard_opens": 1,
        "positional_reads": 12,
        "tensor_payloads": 12,
        "compressed_bytes": 139_217_920,
        "decoded_bytes": 666_430_464,
        "expert_payloads": 0,
    }:
        raise ValueError("recovery access budget")
    if len(config["tensor_allowlist"]) != 12:
        raise ValueError("recovery allowlist count")
    if any("_exps" in item["name"] or "_shexp" in item["name"] for item in config["tensor_allowlist"]):
        raise ValueError("UNAUTHORIZED_ACCESS")
    if config["scope"] != {
        "new_route": False,
        "expert_computation": False,
        "shared_expert_computation": False,
        "mlx_candidate_dispatches": 0,
        "m1_f_execution": False,
        "q6_k_qualification": False,
    }:
        raise ValueError("recovery scope")
    expected = config["expected_identities"]
    if expected["top8_ids"] != [166, 78, 26, 186, 163, 199, 233, 177]:
        raise ValueError("accepted route identity")
    if expected["ranking_sha256"] != "6a878c1db20997b16cff8efdb8659543c07974dcddd718957243c889d78a2ede":
        raise ValueError("accepted ranking identity")


def validate_authorization(
    config: dict[str, Any], config_sha256: str, authorization_path: Path, authorization_sha256: str
) -> None:
    raw = authorization_path.read_bytes()
    if sha256(raw) != authorization_sha256:
        raise ValueError("recovery authorization identity")
    authorization = json.loads(raw, object_pairs_hook=_reject_duplicates)
    if authorization != {
        "schema": "pulsarmlx.f017.m1f0-analytical-recovery-authorization",
        "schema_version": "1.0.0",
        "status": "AUTHORIZED FOR EXACTLY ONE ACCEPTED-BOUNDARY EVIDENCE RECOVERY / NOT EXECUTED",
        "execution_config_sha256": config_sha256,
        "tooling_commit_sha": config["source_identities"]["tooling_commit_sha"],
        "tooling_tree_oid": config["source_identities"]["tooling_tree_oid"],
        "accepted_route_sha256": config["accepted_bindings"]["route"]["sha256"],
        "payload_budget": config["access_budget"],
        "route_discovery_attempt_consumed": False,
        "new_route_authorized": False,
        "m1_f_authorized": False,
        "q6_k_qualification_authorized": False,
    }:
        raise ValueError("recovery authorization binding")


def preflight(
    repository_root: Path,
    config_path: Path,
    expected_sha256: str,
    authorization_path: Path,
    authorization_sha256: str,
) -> dict[str, Any]:
    raw = config_path.read_bytes()
    if sha256(raw) != expected_sha256:
        raise ValueError("recovery config identity")
    config = json.loads(raw, object_pairs_hook=_reject_duplicates)
    validate_config(repository_root, config)
    validate_authorization(config, expected_sha256, authorization_path, authorization_sha256)
    return {
        "result": READY,
        "checkpoint_payload_reads": 0,
        "attention_computation": 0,
        "router_computation": 0,
        "expert_computation": 0,
        "mlx_dispatches": 0,
        "m1_f_execution": 0,
        "recovery_consumed": False,
    }


def write_start_marker(path: Path, config_sha256: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json(
        {
            "schema": "pulsarmlx.f017.m1f0-analytical-recovery-start",
            "schema_version": "1.0.0",
            "state": "RECOVERY_STARTED",
            "execution_config_sha256": config_sha256,
            "recorded_unix_ns": time.time_ns(),
        }
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def gamma(operations: int) -> float:
    product = operations * U32
    if product >= 1.0:
        raise ValueError("gamma domain")
    return product / (1.0 - product)


def _columnwise_l1(matrix: np.ndarray, values: np.ndarray, errors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rows, columns = matrix.shape
    l1 = np.zeros(rows, dtype=np.float64)
    propagated = np.zeros(rows, dtype=np.float64)
    for start in range(0, columns, 128):
        end = min(start + 128, columns)
        block = np.abs(np.asarray(matrix[:, start:end], dtype=np.float64))
        l1 += block @ np.abs(np.asarray(values[start:end], dtype=np.float64))
        propagated += block @ np.asarray(errors[start:end], dtype=np.float64)
    return l1, propagated


def matvec_bound(matrix: np.ndarray, values: np.ndarray, input_error: np.ndarray) -> np.ndarray:
    n = values.size
    l1, propagated = _columnwise_l1(matrix, values, input_error)
    reduction = 2.0 * gamma(2 * n) * l1 + 4.0 * n * ETA32
    return np.nextafter(reduction + (1.0 + gamma(2 * n)) * propagated, math.inf)


def _strict_rms_state(values: np.ndarray) -> tuple[float, float]:
    total = np.float32(0)
    for value in values:
        total = np.add(total, np.multiply(value, value, dtype=np.float32), dtype=np.float32)
    mean = np.divide(total, np.float32(values.size), dtype=np.float32)
    q = np.add(mean, np.float32(RMS_EPS), dtype=np.float32)
    inverse = np.divide(np.float32(1), np.sqrt(q, dtype=np.float32), dtype=np.float32)
    return float(q), float(inverse)


def rms_norm_bound(values: np.ndarray, weights: np.ndarray, input_error: np.ndarray) -> np.ndarray:
    absolute = np.abs(np.asarray(values, dtype=np.float64))
    error = np.asarray(input_error, dtype=np.float64)
    upper = absolute + error
    n = values.size
    same_input = 2.0 * gamma(2 * n) * float(np.sum(upper * upper, dtype=np.float64)) + 4.0 * n * ETA32
    propagated = float(np.sum(2.0 * absolute * error + error * error, dtype=np.float64))
    sum_error = np.nextafter(same_input + (1.0 + gamma(2 * n)) * propagated, math.inf)
    q, inverse = _strict_rms_state(values)
    q_error = np.nextafter((sum_error / n) * (1.0 + U32) + 4.0 * U32 * abs(q) + 4.0 * ETA32, math.inf)
    q_lower = q - q_error
    if not math.isfinite(q_lower) or q_lower <= 0.0:
        raise ValueError("RMS norm positive interval")
    inverse_error = np.nextafter(
        0.5 * q_lower ** -1.5 * q_error + 4.0 * U32 * (abs(inverse) + q_lower ** -0.5) + 4.0 * ETA32,
        math.inf,
    )
    weight = np.abs(np.asarray(weights, dtype=np.float64))
    propagated_output = weight * (absolute * inverse_error + error * (abs(inverse) + inverse_error))
    magnitude = weight * upper * (abs(inverse) + inverse_error)
    rounding = 4.0 * U32 * magnitude + 4.0 * ETA32
    return np.nextafter(propagated_output + rounding, math.inf)


def route_score_bounds(tensors: dict[str, np.ndarray], captured: dict[str, Any], hidden: np.ndarray) -> dict[str, Any]:
    zero_hidden = np.zeros(hidden.size, dtype=np.float64)
    attention_norm_error = rms_norm_bound(
        hidden, tensors["blk.3.attn_norm.weight"], zero_hidden
    )
    kv_raw_error = matvec_bound(
        tensors["blk.3.attn_kv_a_mqa.weight"], captured["attention_normalized"], attention_norm_error
    )
    kv_normalized_error = rms_norm_bound(
        captured["kv_raw"][:512],
        tensors["blk.3.attn_kv_a_norm.weight"],
        kv_raw_error[:512],
    )
    value_errors = np.empty((64, 256), dtype=np.float64)
    for head in range(64):
        value_errors[head] = matvec_bound(
            tensors["blk.3.attn_v_b.weight"][head],
            captured["kv_normalized"],
            kv_normalized_error,
        )
    attention_output_error = matvec_bound(
        tensors["blk.3.attn_output.weight"],
        captured["value_heads"].reshape(-1),
        value_errors.reshape(-1),
    )
    residual_magnitude = np.abs(hidden.astype(np.float64)) + np.abs(captured["attention_output"].astype(np.float64))
    residual_error = np.nextafter(
        attention_output_error + 4.0 * U32 * (residual_magnitude + attention_output_error) + 4.0 * ETA32,
        math.inf,
    )
    router_normalized_error = rms_norm_bound(
        captured["attention_residual"],
        tensors["blk.3.ffn_norm.weight"],
        residual_error,
    )
    router_logit_error = matvec_bound(
        tensors["blk.3.ffn_gate_inp.weight"],
        captured["router_normalized"],
        router_normalized_error,
    )
    scores = np.asarray(captured["scores"], dtype=np.float64)
    score_error = np.nextafter(
        0.25 * router_logit_error + 2.0 * U64 * (np.abs(scores) + 0.25 * router_logit_error),
        math.inf,
    )
    return {
        "attention_residual_abs_error": residual_error,
        "router_normalized_abs_error": router_normalized_error,
        "router_logit_abs_error": router_logit_error,
        "router_score_abs_error": score_error,
    }


def _instrumented_oracle(oracle: Any, tensors: dict[str, np.ndarray], hidden: np.ndarray) -> tuple[dict[str, Any], dict[str, Any]]:
    captures: dict[str, Any] = {"rms_outputs": [], "value_heads": []}
    identities = {id(value): name for name, value in tensors.items()}
    original_matvec = oracle.strict_matvec
    original_rms = oracle.rms_norm
    original_select = oracle.select_route

    def matvec(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
        result = original_matvec(matrix, vector)
        name = identities.get(id(matrix))
        if name is not None:
            captures[name] = result.copy()
        elif np.shares_memory(matrix, tensors["blk.3.attn_v_b.weight"]):
            captures["value_heads"].append(result.copy())
        return result

    def rms(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
        result = original_rms(values, weights)
        captures["rms_outputs"].append(result.copy())
        return result

    def select(logits: np.ndarray, bias: np.ndarray):
        selected, weights, scores = original_select(logits, bias)
        captures["probabilities"] = [oracle._sigmoid(value) for value in logits]
        captures["bias"] = np.asarray(bias, dtype=np.float32).copy()
        captures["scores"] = list(scores)
        captures["ranking"] = sorted(range(256), key=lambda index: (-scores[index], index))
        return selected, weights, scores

    oracle.strict_matvec = matvec
    oracle.rms_norm = rms
    oracle.select_route = select
    try:
        result = oracle.compute_oracle(tensors, hidden)
    finally:
        oracle.strict_matvec = original_matvec
        oracle.rms_norm = original_rms
        oracle.select_route = original_select
    if len(captures["rms_outputs"]) != 4 or len(captures["value_heads"]) != 64:
        raise ValueError("oracle instrumentation completeness")
    captures["attention_normalized"] = captures["rms_outputs"][0]
    captures["kv_raw"] = captures["blk.3.attn_kv_a_mqa.weight"]
    captures["kv_normalized"] = captures["rms_outputs"][2]
    captures["value_heads"] = np.stack(captures["value_heads"])
    captures["attention_output"] = captures["blk.3.attn_output.weight"]
    captures["attention_residual"] = np.add(hidden, captures["attention_output"], dtype=np.float32)
    captures["router_normalized"] = captures["rms_outputs"][3]
    captures["router_logits"] = captures["blk.3.ffn_gate_inp.weight"]
    return result, captures


def _write_private_package(output: Path, manifest: dict[str, Any], payloads: dict[str, bytes]) -> None:
    if output.exists():
        raise ValueError("refusing to overwrite analytical recovery package")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        for name, payload in payloads.items():
            target = temporary / name
            target.write_bytes(payload)
            target.chmod(0o444)
        (temporary / "recovery-manifest.json").write_bytes(canonical_json(manifest))
        (temporary / "recovery-manifest.json").chmod(0o444)
        os.replace(temporary, output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def execute(
    repository_root: Path,
    config_path: Path,
    expected_config_sha256: str,
    authorization_path: Path,
    authorization_sha256: str,
    private_package_root: Path,
    output: Path,
    start_marker: Path,
) -> dict[str, Any]:
    readiness = preflight(
        repository_root,
        config_path,
        expected_config_sha256,
        authorization_path,
        authorization_sha256,
    )
    if readiness["result"] != READY:
        raise ValueError("recovery preflight")
    config = load_json(config_path)
    oracle = _load(
        repository_root,
        "scripts/research/prepare_f017_m1f0_real_reference.py",
        "m1f0_accepted_oracle_recovery",
    )
    manifest = load_json(_safe_file(private_package_root, "checkpoint-manifest.json"))
    accepted_config = load_json(
        _safe_file(repository_root, config["accepted_bindings"]["execution_config"]["symbolic_path"])
    )
    if manifest.get("checkpoint_set_sha256") != accepted_config["checkpoint_bindings"]["checkpoint_set_sha256"]:
        raise ValueError("checkpoint package identity")
    shard = manifest.get("shard_2", {})
    if set(shard) != {"path_kind", "path", "size_bytes", "sha256"} or shard.get("path_kind") != "package_relative":
        raise ValueError("checkpoint package shard")
    shard_path = _safe_file(private_package_root, shard["path"])
    if shard_path.stat().st_size != shard["size_bytes"]:
        raise ValueError("checkpoint shard size")
    fixture = load_json(_safe_file(repository_root, config["input_state"]["symbolic_path"]))
    hidden = np.frombuffer(bytes.fromhex(fixture["state"]["hidden"]["bytes_hex"]), dtype="<f4").copy()
    if sha256(hidden.tobytes()) != config["input_state"]["hidden_sha256"]:
        raise ValueError("accepted hidden identity")

    write_start_marker(start_marker, expected_config_sha256)
    tensors: dict[str, np.ndarray] = {}
    packed: dict[str, str] = {}
    decoded: dict[str, str] = {}
    with shard_path.open("rb", buffering=0) as source:
        for binding in config["tensor_allowlist"]:
            source.seek(binding["offset"])
            raw = source.read(binding["packed_length"])
            if len(raw) != binding["packed_length"]:
                raise ValueError("truncated recovery payload")
            name = binding["name"]
            packed[name] = sha256(raw)
            tensor = oracle.decode_tensor(raw, binding["quantization"], binding["logical_shape"])
            decoded[name] = sha256(oracle.f32_bytes(tensor))
            tensors[name] = tensor
    expected = config["expected_identities"]
    if packed != expected["tensor_payload_sha256"] or decoded != expected["decoded_tensor_sha256"]:
        raise ValueError("accepted tensor identity mismatch")

    result, captured = _instrumented_oracle(oracle, tensors, hidden)
    reproduced = {
        "router_scores_sha256": result["router_scores_sha256"],
        "ranking_sha256": result["ranking_sha256"],
        "top8_ids_sha256": result["top8_ids_sha256"],
        "routing_weights_sha256": result["routing_weights_sha256"],
        "attention_output_sha256": result["stage_hashes"]["attention_output"],
        "attention_residual_sha256": result["stage_hashes"]["attention_residual"],
        "router_normalized_input_sha256": result["stage_hashes"]["router_normalized"],
        "top8_ids": result["top8_ids"],
    }
    expected_gate = {key: expected[key] for key in reproduced}
    if reproduced != expected_gate:
        raise ValueError("BLOCKED — M1-F0 RECOVERY IDENTITY MISMATCH")

    probability_bytes = b"".join(struct.pack("<d", value) for value in captured["probabilities"])
    bias_bytes = np.asarray(captured["bias"], dtype="<f4").tobytes(order="C")
    score_bytes = b"".join(struct.pack("<d", value) for value in captured["scores"])
    ranking_bytes = b"".join(struct.pack("<H", value) for value in captured["ranking"])
    top8_bytes = struct.pack("<8H", *result["top8_ids"])
    weight_bytes = b"".join(struct.pack("<d", value) for value in result["routing_weights"])
    bounds = route_score_bounds(tensors, captured, hidden)
    bound_bytes = np.asarray(bounds["router_score_abs_error"], dtype="<f8").tobytes(order="C")
    payloads = {
        "router-probabilities.lef64": probability_bytes,
        "router-bias.lef32": bias_bytes,
        "router-scores.lef64": score_bytes,
        "ranking.leu16": ranking_bytes,
        "top8.leu16": top8_bytes,
        "routing-weights.lef64": weight_bytes,
        "router-score-bounds.lef64": bound_bytes,
    }
    analytics = {
        "probabilities": captured["probabilities"],
        "bias": [float(value) for value in captured["bias"]],
        "scores": captured["scores"],
        "ranking": captured["ranking"],
        "top8_ids": result["top8_ids"],
        "routing_weights": result["routing_weights"],
        "router_score_abs_error_bounds": bounds["router_score_abs_error"].tolist(),
    }
    private_artifacts = {
        name: {
            "path_kind": "recovery_package_relative",
            "path": name,
            "sha256": sha256(payload),
            "size_bytes": len(payload),
        }
        for name, payload in payloads.items()
    }
    recovery_manifest = {
        "schema": "pulsarmlx.f017.m1f0-analytical-recovery-private-package",
        "schema_version": "1.0.0",
        "execution_config_sha256": expected_config_sha256,
        "accepted_identities_reproduced": reproduced,
        "tensor_payload_sha256": packed,
        "decoded_tensor_sha256": decoded,
        "canonical_analytics": analytics,
        "private_artifacts": private_artifacts,
        "access": {
            "shard_opens": 1,
            "positional_reads": 12,
            "tensor_payloads": 12,
            "compressed_bytes": 139_217_920,
            "decoded_bytes": 666_430_464,
            "expert_payloads": 0,
        },
        "scope": config["scope"],
    }
    _write_private_package(output, recovery_manifest, payloads)
    return recovery_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--execution-config", type=Path, required=True)
    parser.add_argument("--execution-config-sha256", required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--authorization-sha256", required=True)
    parser.add_argument("--private-package-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--start-marker", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    root = args.repository_root.resolve(strict=True)
    if args.preflight_only:
        print(
            preflight(
                root,
                args.execution_config,
                args.execution_config_sha256,
                args.authorization,
                args.authorization_sha256,
            )["result"]
        )
        return 0
    if args.private_package_root is None or args.output is None or args.start_marker is None:
        parser.error("execution requires private package, output, and start marker")
    result = execute(
        root,
        args.execution_config,
        args.execution_config_sha256,
        args.authorization,
        args.authorization_sha256,
        args.private_package_root.resolve(strict=True),
        args.output,
        args.start_marker,
    )
    print(sha256(canonical_json(result)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
