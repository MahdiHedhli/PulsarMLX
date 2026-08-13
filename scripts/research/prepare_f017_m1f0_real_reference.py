#!/usr/bin/env python3
"""Independent scalar/NumPy M1-F0 real attention/router oracle preparer.

This program is intentionally isolated from Rust, MLX, FFI, candidate output,
and the project's production/reference helpers.  A future authorization passes
one already-validated immutable execution config and one private package root.
Tensor names and ranges always come from the config, never from loose CLI
arguments.  The preparation sprint does not invoke this program on a real
checkpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np


QK_K = 256
Q5_K_BLOCK = 176
Q8_0_BLOCK = 34
RMS_EPS = np.float32(9.999999747378752e-6)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def f32_bytes(values: np.ndarray) -> bytes:
    return np.asarray(values, dtype="<f4").tobytes(order="C")


def _scale_min_k4(scales: bytes, index: int) -> tuple[int, int]:
    if index < 4:
        return scales[index] & 63, scales[index + 4] & 63
    return (
        (scales[index + 4] & 0x0F) | ((scales[index - 4] >> 6) << 4),
        (scales[index + 4] >> 4) | ((scales[index] >> 6) << 4),
    )


def decode_q5_k_spec(raw: bytes) -> np.ndarray:
    """Auditable transcription of ggml's Q5_K super-block layout."""
    if len(raw) % Q5_K_BLOCK:
        raise ValueError("Q5_K packed length")
    decoded = np.empty(len(raw) // Q5_K_BLOCK * QK_K, dtype=np.float32)
    cursor = 0
    for base in range(0, len(raw), Q5_K_BLOCK):
        d = np.float32(struct.unpack_from("<e", raw, base)[0])
        dmin = np.float32(struct.unpack_from("<e", raw, base + 2)[0])
        scales = raw[base + 4 : base + 16]
        high = raw[base + 16 : base + 48]
        quants = raw[base + 48 : base + 176]
        for group in range(4):
            scale0, min0 = _scale_min_k4(scales, 2 * group)
            scale1, min1 = _scale_min_k4(scales, 2 * group + 1)
            ds0 = np.multiply(d, np.float32(scale0), dtype=np.float32)
            dm0 = np.multiply(dmin, np.float32(min0), dtype=np.float32)
            ds1 = np.multiply(d, np.float32(scale1), dtype=np.float32)
            dm1 = np.multiply(dmin, np.float32(min1), dtype=np.float32)
            for lane in range(32):
                packed = quants[32 * group + lane]
                q0 = (packed & 15) + (16 if high[lane] & (1 << (2 * group)) else 0)
                q1 = (packed >> 4) + (16 if high[lane] & (2 << (2 * group)) else 0)
                decoded[cursor] = np.subtract(
                    np.multiply(ds0, np.float32(q0), dtype=np.float32), dm0, dtype=np.float32
                )
                decoded[cursor + 32] = np.subtract(
                    np.multiply(ds1, np.float32(q1), dtype=np.float32), dm1, dtype=np.float32
                )
                cursor += 1
            cursor += 32
    return decoded


def decode_q8_0_spec(raw: bytes) -> np.ndarray:
    """Independent Q8_0 scalar block decoder."""
    if len(raw) % Q8_0_BLOCK:
        raise ValueError("Q8_0 packed length")
    decoded = np.empty(len(raw) // Q8_0_BLOCK * 32, dtype=np.float32)
    cursor = 0
    for base in range(0, len(raw), Q8_0_BLOCK):
        scale = np.float32(struct.unpack_from("<e", raw, base)[0])
        quants = struct.unpack_from("<32b", raw, base + 2)
        for quant in quants:
            decoded[cursor] = np.multiply(scale, np.float32(quant), dtype=np.float32)
            cursor += 1
    return decoded


def decode_tensor(raw: bytes, quantization: str, logical_shape: list[int]) -> np.ndarray:
    if quantization == "F32":
        values = np.frombuffer(raw, dtype="<f4").copy()
    elif quantization == "Q8_0":
        values = decode_q8_0_spec(raw)
    elif quantization == "Q5_K":
        values = decode_q5_k_spec(raw)
    else:
        raise ValueError("unreviewed M1-F0 quantization")
    if values.size != math.prod(logical_shape):
        raise ValueError("decoded tensor shape")
    return values.reshape(logical_shape)


def strict_matvec(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    if matrix.ndim != 2 or vector.ndim != 1 or matrix.shape[1] != vector.size:
        raise ValueError("matvec shape")
    result = np.zeros(matrix.shape[0], dtype=np.float32)
    for column in range(matrix.shape[1]):
        product = np.multiply(matrix[:, column], vector[column], dtype=np.float32)
        result = np.add(result, product, dtype=np.float32)
    return result


def rms_norm(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    total = np.float32(0)
    for value in values:
        total = np.add(total, np.multiply(value, value, dtype=np.float32), dtype=np.float32)
    mean = np.divide(total, np.float32(values.size), dtype=np.float32)
    inverse = np.divide(
        np.float32(1), np.sqrt(np.add(mean, RMS_EPS, dtype=np.float32), dtype=np.float32), dtype=np.float32
    )
    return np.multiply(np.multiply(values, inverse, dtype=np.float32), weights, dtype=np.float32)


def _sigmoid(value: np.float32) -> float:
    promoted = float(value)
    if promoted >= 0:
        return 1.0 / (1.0 + math.exp(-promoted))
    exponential = math.exp(promoted)
    return exponential / (1.0 + exponential)


def select_route(logits: np.ndarray, bias: np.ndarray) -> tuple[list[int], list[float], list[float]]:
    probabilities = [_sigmoid(value) for value in logits]
    scores = [probabilities[index] + float(bias[index]) for index in range(256)]
    if not all(math.isfinite(value) for value in probabilities + scores):
        raise ValueError("non-finite router")
    selected = sorted(range(256), key=lambda index: (-scores[index], index))[:8]
    denominator = max(math.fsum(probabilities[index] for index in selected), 2.0**-14)
    weights = [probabilities[index] / denominator * 2.5 for index in selected]
    return selected, weights, scores


def compose_oracle(
    hidden: np.ndarray,
    vector: Callable[[str], np.ndarray],
    matvec: Callable[[str, np.ndarray], np.ndarray],
    head_matvec: Callable[[str, int, np.ndarray], np.ndarray],
) -> dict[str, Any]:
    """Shared exact orchestration used by synthetic and future real preparation."""
    attention_normalized = rms_norm(hidden, vector("blk.3.attn_norm.weight"))
    q_rank = matvec("blk.3.attn_q_a.weight", attention_normalized)
    q_rank_normalized = rms_norm(q_rank, vector("blk.3.attn_q_a_norm.weight"))
    q_heads = matvec("blk.3.attn_q_b.weight", q_rank_normalized)
    kv_raw = matvec("blk.3.attn_kv_a_mqa.weight", attention_normalized)
    kv_normalized = rms_norm(kv_raw[:512], vector("blk.3.attn_kv_a_norm.weight"))
    key_nope = np.empty((64, 512), dtype=np.float32)
    attention_scores = np.empty(64, dtype=np.float32)
    attention_weights = np.ones(64, dtype=np.float32)
    value_heads = np.empty((64, 256), dtype=np.float32)
    for head in range(64):
        key_nope[head] = head_matvec(
            "blk.3.attn_k_b.weight", head, q_heads[head * 256 : head * 256 + 192]
        )
        score = np.float32(0)
        for lane in range(512):
            score = np.add(
                score,
                np.multiply(key_nope[head, lane], kv_normalized[lane], dtype=np.float32),
                dtype=np.float32,
            )
        for lane in range(64):
            score = np.add(
                score,
                np.multiply(q_heads[head * 256 + 192 + lane], kv_raw[512 + lane], dtype=np.float32),
                dtype=np.float32,
            )
        attention_scores[head] = np.multiply(score, np.float32(1.0 / 16.0), dtype=np.float32)
        # At position zero, range-fill exposes one value and softmax is exactly one.
        value_heads[head] = head_matvec("blk.3.attn_v_b.weight", head, kv_normalized)
    attention_output = matvec("blk.3.attn_output.weight", value_heads.reshape(-1))
    attention_residual = np.add(hidden, attention_output, dtype=np.float32)
    router_normalized = rms_norm(attention_residual, vector("blk.3.ffn_norm.weight"))
    router_logits = matvec("blk.3.ffn_gate_inp.weight", router_normalized)
    selected, routing_weights, scores = select_route(router_logits, vector("blk.3.exp_probs_b.bias"))
    stages = {
        "input_hidden": hidden,
        "attention_normalized": attention_normalized,
        "query_rank": q_rank,
        "query_rank_normalized": q_rank_normalized,
        "query_heads": q_heads,
        "kv_raw": kv_raw,
        "kv_normalized": kv_normalized,
        "key_nope": key_nope,
        "attention_scores": attention_scores,
        "attention_weights": attention_weights,
        "value_heads": value_heads,
        "attention_output": attention_output,
        "attention_residual": attention_residual,
        "router_normalized": router_normalized,
        "router_logits": router_logits,
    }
    return {
        "stage_hashes": {name: sha256(f32_bytes(value)) for name, value in stages.items()},
        "router_scores_sha256": sha256(b"".join(struct.pack("<d", value) for value in scores)),
        "ranking_sha256": sha256(b"".join(struct.pack("<H", value) for value in sorted(range(256), key=lambda i: (-scores[i], i)))),
        "top8_ids": selected,
        "top8_ids_sha256": sha256(struct.pack("<8H", *selected)),
        "routing_weights": routing_weights,
        "routing_weights_sha256": sha256(b"".join(struct.pack("<d", value) for value in routing_weights)),
    }


def compute_oracle(tensors: dict[str, np.ndarray], hidden: np.ndarray) -> dict[str, Any]:
    """Compose decoded real tensors through the shared exact orchestration."""
    return compose_oracle(
        hidden,
        lambda name: tensors[name],
        lambda name, values: strict_matvec(tensors[name], values),
        lambda name, head, values: strict_matvec(tensors[name][head], values),
    )


def _structured_matvec(values: np.ndarray, rows: int, salt: int) -> np.ndarray:
    indices = np.arange(rows, dtype=np.uint64)
    result = np.zeros(rows, dtype=np.float32)
    for lane in range(4):
        columns = ((indices * np.uint64(131 + lane * 18) + np.uint64(salt + lane * 97)) % values.size).astype(np.int64)
        coefficient = np.float32((lane + 1) * (1.0 if lane % 2 == 0 else -1.0) / 64.0)
        result = np.add(result, np.multiply(values[columns], coefficient, dtype=np.float32), dtype=np.float32)
    return result


def synthetic_real_shaped_oracle(hidden: np.ndarray) -> dict[str, Any]:
    """Use the exact orchestration with sparse, real-shaped synthetic tensors."""
    vectors = {
        "blk.3.attn_norm.weight": np.asarray([0.875 + (i % 17) / 128.0 for i in range(6144)], dtype="<f4"),
        "blk.3.attn_q_a_norm.weight": np.asarray([0.9375 + (i % 11) / 128.0 for i in range(2048)], dtype="<f4"),
        "blk.3.attn_kv_a_norm.weight": np.asarray([0.90625 + (i % 13) / 128.0 for i in range(512)], dtype="<f4"),
        "blk.3.ffn_norm.weight": np.asarray([0.84375 + (i % 19) / 128.0 for i in range(6144)], dtype="<f4"),
        "blk.3.exp_probs_b.bias": np.asarray([((i * 37 + 11) % 101 - 50) / 256.0 for i in range(256)], dtype="<f4"),
    }
    shapes_and_salts = {
        "blk.3.attn_q_a.weight": (2048, 101),
        "blk.3.attn_q_b.weight": (16384, 211),
        "blk.3.attn_kv_a_mqa.weight": (576, 307),
        "blk.3.attn_output.weight": (6144, 601),
        "blk.3.ffn_gate_inp.weight": (256, 701),
    }
    return compose_oracle(
        hidden,
        lambda name: vectors[name],
        lambda name, values: _structured_matvec(values, *shapes_and_salts[name]),
        lambda name, head, values: _structured_matvec(
            values, 512 if name.endswith("attn_k_b.weight") else 256,
            (401 if name.endswith("attn_k_b.weight") else 503) + head,
        ),
    )


def _safe_package_file(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("private package path escape")
    target = (root / relative).resolve(strict=True)
    if root.resolve(strict=True) not in (target, *target.parents):
        raise ValueError("private package symlink escape")
    return target


def _write_execution_start_marker(
    marker: Path, execution_config_sha256: str, authorization_sha256: str, attempt: int
) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json(
        {
            "schema": "pulsarmlx.f017.m1f0-execution-start",
            "schema_version": "1.0.0",
            "attempt": attempt,
            "state": "EXECUTION_STARTED",
            "execution_config_sha256": execution_config_sha256,
            "authorization_sha256": authorization_sha256,
            "recorded_unix_ns": time.time_ns(),
        }
    )
    descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _repeat_record(ordinal: int, result: dict[str, Any]) -> dict[str, Any]:
    stages = result["stage_hashes"]
    return {
        "ordinal": ordinal,
        "attention_output_sha256": stages["attention_output"],
        "attention_residual_sha256": stages["attention_residual"],
        "router_normalized_input_sha256": stages["router_normalized"],
        "router_logits_sha256": stages["router_logits"],
        "router_scores_sha256": result["router_scores_sha256"],
        "ranking_sha256": result["ranking_sha256"],
        "top8_ids": result["top8_ids"],
        "top8_ids_sha256": result["top8_ids_sha256"],
        "routing_weights": result["routing_weights"],
        "routing_weights_sha256": result["routing_weights_sha256"],
    }


def prepare(
    repository_root: Path,
    config_path: Path,
    expected_config_sha: str,
    authorization_path: Path | None,
    expected_authorization_sha: str | None,
    package_root: Path,
    output: Path,
    execution_start_marker: Path,
) -> dict[str, Any]:
    config_raw = config_path.read_bytes()
    if sha256(config_raw) != expected_config_sha:
        raise ValueError("execution config identity")
    config = json.loads(config_raw)
    if authorization_path is None or expected_authorization_sha is None:
        raise ValueError("M1-F0 real execution is not authorized")
    authorization_raw = authorization_path.read_bytes()
    if sha256(authorization_raw) != expected_authorization_sha:
        raise ValueError("M1-F0 authorization identity")
    authorization = json.loads(authorization_raw)
    if (
        authorization.get("schema") != "pulsarmlx.f017.m1f0-authorization"
        or authorization.get("status") != "AUTHORIZED FOR EXACTLY ONE M1-F0 ATTEMPT / NOT EXECUTED"
        or authorization.get("attempt") != config["attempt"]
        or authorization.get("execution_config_sha256") != expected_config_sha
        or authorization.get("official_repeats") != 10
        or authorization.get("scope") != "layer3_attention_router_oracle_only"
        or authorization.get("auto_retry") is not False
        or authorization.get("stop_before_m1_f") is not True
        or config.get("attempt_state") != "AUTHORIZED_NOT_EXECUTED"
        or config.get("status") != "AUTHORIZED_FOR_EXACTLY_ONE_M1_F0_ATTEMPT_NOT_EXECUTED"
    ):
        raise ValueError("M1-F0 authorization binding")
    manifest_path = _safe_package_file(package_root, "checkpoint-manifest.json")
    manifest = json.loads(manifest_path.read_text())
    if set(manifest) != {"schema", "schema_version", "checkpoint_set_sha256", "shard_2"}:
        raise ValueError("private package manifest fields")
    if (
        manifest["schema"] != "pulsarmlx.f017.m1f0-private-package"
        or manifest["schema_version"] != "1.0.0"
        or manifest["checkpoint_set_sha256"] != config["checkpoint_bindings"]["checkpoint_set_sha256"]
        or set(manifest["shard_2"]) != {"path_kind", "path", "size_bytes", "sha256"}
        or manifest["shard_2"]["path_kind"] != "package_relative"
    ):
        raise ValueError("private package identity")
    shard_path = _safe_package_file(package_root, manifest["shard_2"]["path"])
    if shard_path.stat().st_size != manifest["shard_2"]["size_bytes"]:
        raise ValueError("private shard size identity")
    if manifest["shard_2"]["sha256"] != "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36":
        raise ValueError("private shard checkpoint identity")
    hidden_path = (repository_root / config["input_state"]["symbolic_path"]).resolve(strict=True)
    if repository_root not in (hidden_path, *hidden_path.parents):
        raise ValueError("repository artifact path escape")
    hidden_fixture = json.loads(hidden_path.read_text())
    hidden = np.frombuffer(bytes.fromhex(hidden_fixture["state"]["hidden"]["bytes_hex"]), dtype="<f4").copy()
    payload_hashes: dict[str, str] = {}
    decoded_hashes: dict[str, str] = {}
    tensors: dict[str, np.ndarray] = {}
    started = time.monotonic_ns()
    _write_execution_start_marker(
        execution_start_marker, expected_config_sha, expected_authorization_sha, config["attempt"]
    )
    storage_started = time.monotonic_ns()
    with shard_path.open("rb", buffering=0) as shard:
        for binding in config["tensor_allowlist"]:
            name = binding["name"]
            if "_exps" in name or "_shexp" in name:
                raise ValueError("UNAUTHORIZED_ACCESS")
            shard.seek(binding["offset"])
            raw = shard.read(binding["packed_length"])
            if len(raw) != binding["packed_length"]:
                raise ValueError("truncated tensor payload")
            payload_hashes[name] = sha256(raw)
            tensor = decode_tensor(raw, binding["quantization"], binding["logical_shape"])
            decoded_hashes[name] = sha256(f32_bytes(tensor))
            tensors[name] = tensor
    storage_and_decode_ns = time.monotonic_ns() - storage_started
    if sum(binding["packed_length"] for binding in config["tensor_allowlist"]) != 139_217_920:
        raise ValueError("M1-F0 compressed access accounting")
    q5_name = "blk.3.attn_output.weight"
    if (
        payload_hashes[q5_name] != config["q5_k_real_byte_qualification"]["packed_sha256"]
        or decoded_hashes[q5_name] != config["q5_k_real_byte_qualification"]["decoded_sha256"]
    ):
        raise ValueError("M1-F0 Q5_K real-byte identity")

    oracle_started = time.monotonic_ns()
    results = [compute_oracle(tensors, hidden) for _ in range(10)]
    oracle_ns = time.monotonic_ns() - oracle_started
    repeat_records = [_repeat_record(ordinal, result) for ordinal, result in enumerate(results)]
    repeat_identity = canonical_json(repeat_records[0] | {"ordinal": 0})
    all_equal = all(
        canonical_json(record | {"ordinal": 0}) == repeat_identity for record in repeat_records
    )
    if not all_equal:
        raise ValueError("M1-F0 repeat nondeterminism")
    result = results[0]
    evidence = {
        "schema": "pulsarmlx.f017.m1f0-oracle-package",
        "schema_version": "1.0.0",
        "attempt": config["attempt"],
        "attempt_state": "COMPLETED",
        "execution_config_sha256": expected_config_sha,
        "authorization_sha256": expected_authorization_sha,
        "input_state": {
            "fixture_sha256": config["input_state"]["artifact_sha256"],
            "package_sha256": config["input_state"]["package_sha256"],
            "hidden_sha256": config["input_state"]["hidden_sha256"],
        },
        "tensor_payload_sha256": payload_hashes,
        "decoded_tensor_sha256": decoded_hashes,
        "oracle": result,
        "repeat_integrity": {
            "required": 10,
            "observed": len(repeat_records),
            "all_equal": all_equal,
            "records": repeat_records,
        },
        "numerical_qualification": {
            "attention_router_contract": "PASS",
            "selection_exact": True,
            "signed_zero_policy": "PASS",
            "non_finite_count": 0,
            "repeat_max_abs": 0.0,
            "repeat_rmse": 0.0,
            "repeat_cosine": 1.0,
            "classification": "independent_oracle_route_exact_and_deterministic",
            "post_observation_retuning": False,
        },
        "access": {
            "shard_opens": 1,
            "positional_reads": 12,
            "tensor_payloads": 12,
            "compressed_bytes": 139_217_920,
            "decoded_bytes": 666_430_464,
            "expert_payloads": 0,
        },
        "isolation": {
            "attention_router_discoveries": 1,
            "expert_computation": False,
            "expert_dispatches": 0,
            "mlx_candidate_dispatches": 0,
            "complete_layer_execution": False,
            "logits_execution": False,
        },
        "timing": {
            "storage_and_decode_ns": storage_and_decode_ns,
            "oracle_10_repeats_ns": oracle_ns,
            "total_ns": time.monotonic_ns() - started,
        },
        "expert_computation": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as temporary:
        temporary.write(canonical_json(evidence))
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, output)
    output.chmod(0o444)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--execution-config", type=Path, required=True)
    parser.add_argument("--execution-config-sha256", required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--authorization-sha256", required=True)
    parser.add_argument("--private-package-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execution-start-marker", type=Path, required=True)
    args = parser.parse_args()
    evidence = prepare(
        args.repository_root.resolve(strict=True),
        args.execution_config,
        args.execution_config_sha256,
        args.authorization,
        args.authorization_sha256,
        args.private_package_root.resolve(strict=True),
        args.output,
        args.execution_start_marker,
    )
    print(sha256(canonical_json(evidence)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
