#!/usr/bin/env python3
"""Generate the public-safe Feature 017 independent parity oracle.

This module intentionally has no Rust, FFI, MLX, checkpoint, or PulsarMLX
runtime dependency. NumPy is used for typed f32 semantics; scalar Python loops
keep the reference operations direct and auditable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import struct
from importlib.metadata import version
from pathlib import Path
from typing import Any, Iterable

import numpy as np


SCHEMA = "glm52-f017-independent-oracle-v1"
GENERATOR_PATH = "scripts/research/generate_f017_independent_oracle.py"
SOURCE_COMMIT = "60145f8f18531e169e9fbfb676d1754efbfc4873"
CHECKPOINT_SET_SHA256 = "0b38dfc3b79bf6dd3eac3c80cd2b62cb6eb46b2f84e3e51c1a340ad1876c1a42"
DETERMINISTIC_SEED = 17017
EXPECTED_PYTHON = "3.13.13"
EXPECTED_NUMPY = "2.4.5"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _f32_bytes(values: Iterable[float]) -> bytes:
    return b"".join(struct.pack("<f", float(np.float32(value))) for value in values)


def _f64_bytes(values: Iterable[float]) -> bytes:
    return b"".join(struct.pack("<d", float(value)) for value in values)


def _u64_bytes(values: Iterable[int]) -> bytes:
    return b"".join(struct.pack("<Q", int(value)) for value in values)


def _hash_f32(values: Iterable[float]) -> str:
    return _sha256(_f32_bytes(values))


def _hash_f64(values: Iterable[float]) -> str:
    return _sha256(_f64_bytes(values))


def _hash_u64(values: Iterable[int]) -> str:
    return _sha256(_u64_bytes(values))


def _q8_block(scale: float, quants: Iterable[int]) -> bytes:
    values = list(quants)
    if len(values) != 32 or any(value < -128 or value > 127 for value in values):
        raise ValueError("Q8_0 block requires 32 signed bytes")
    return struct.pack("<e", scale) + b"".join(struct.pack("b", value) for value in values)


def _decode_q8_matrix(encoded: bytes, rows: int) -> list[np.float32]:
    if len(encoded) != rows * 34:
        raise ValueError("invalid Q8_0 matrix byte count")
    output: list[np.float32] = []
    for row in range(rows):
        start = row * 34
        scale = np.float32(struct.unpack("<e", encoded[start : start + 2])[0])
        for column in range(32):
            quant = struct.unpack("b", encoded[start + 2 + column : start + 3 + column])[0]
            output.append(np.float32(scale * np.float32(quant)))
    return output


def _matvec_f32(matrix: list[np.float32], vector: list[np.float32], rows: int) -> list[np.float32]:
    output: list[np.float32] = []
    for row in range(rows):
        total = np.float32(0.0)
        for column in range(32):
            product = np.float32(matrix[row * 32 + column] * vector[column])
            total = np.float32(total + product)
        output.append(total)
    return output


def _softmax_selected(scores: list[float], selected: list[int]) -> list[float]:
    selected_scores = [scores[index] for index in selected]
    maximum = max(selected_scores)
    exponentials = [math.exp(score - maximum) for score in selected_scores]
    denominator = sum(exponentials)
    return [value / denominator for value in exponentials]


def _rotate_pair(values: list[float], position: int, theta: float) -> list[float]:
    angle = theta * float(position)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return [cosine * values[0] - sine * values[1], sine * values[0] + cosine * values[1]]


def _matvec2(matrix: list[float], vector: list[float]) -> list[float]:
    return [
        matrix[0] * vector[0] + matrix[1] * vector[1],
        matrix[2] * vector[0] + matrix[3] * vector[1],
    ]


def _boundary(
    *,
    version_name: str,
    tensor_roles: list[str],
    dimensions: list[int],
    dtype: str,
    quantization: str,
    inputs: dict[str, Any],
    expected: dict[str, Any],
    tolerance: dict[str, Any],
) -> dict[str, Any]:
    return {
        "fixture_version": version_name,
        "tensor_roles": tensor_roles,
        "dimensions": dimensions,
        "dtype": dtype,
        "quantization": quantization,
        "inputs": inputs,
        "expected": expected,
        "numerical_contract": tolerance,
        "classification": "INDEPENDENT",
    }


def _projection() -> dict[str, Any]:
    rows = []
    for row in range(2):
        rows.append([-(index + 1) if row == 1 and index % 2 == 0 else index + 1 for index in range(32)])
    encoded = b"".join(_q8_block(1.0, row) for row in rows)
    activation = [np.float32(1.0 + (index % 8) * 0.125) for index in range(32)]
    decoded = _decode_q8_matrix(encoded, 2)
    output = _matvec_f32(decoded, activation, 2)
    return _boundary(
        version_name="glm52-runtime-projection-q8-0-v2",
        tensor_roles=["attention_projection"],
        dimensions=[2, 32],
        dtype="f32",
        quantization="Q8_0",
        inputs={
            "packed_hex": encoded.hex(),
            "packed_sha256": _sha256(encoded),
            "activation": [float(value) for value in activation],
            "activation_sha256": _hash_f32(activation),
        },
        expected={
            "decoded_sha256": _hash_f32(decoded),
            "output": [float(value) for value in output],
            "output_sha256": _hash_f32(output),
        },
        tolerance={"kind": "exact_f32_bits", "atol": 0.0, "rtol": 0.0},
    )


def _router() -> dict[str, Any]:
    scores = [1.0, 3.0, 3.0, -1.0, 2.0, 3.0, 1.0, 4.0]
    selected_outputs = [3.0, 2.0, 1.0, 2.0, 5.75, 3.5, -0.5, 5.5]
    selected_ids = [1, 2, 3, 1]
    weights = _softmax_selected(scores[0:4], [1, 2]) + _softmax_selected(scores[4:8], [3, 1])
    output = []
    for token in range(2):
        for column in range(2):
            total = 0.0
            for route in range(2):
                total += weights[token * 2 + route] * selected_outputs[(token * 2 + route) * 2 + column]
            output.append(total)
    return _boundary(
        version_name="glm52-runtime-router-v2",
        tensor_roles=["router_logits", "selected_expert_outputs"],
        dimensions=[2, 4],
        dtype="f64",
        quantization="F64",
        inputs={
            "scores": scores,
            "scores_sha256": _hash_f64(scores),
            "selected_outputs": selected_outputs,
            "selected_outputs_sha256": _hash_f64(selected_outputs),
        },
        expected={
            "selected_ids": selected_ids,
            "selected_ids_sha256": _hash_u64(selected_ids),
            "weights": weights,
            "weights_sha256": _hash_f64(weights),
            "output": output,
            "output_sha256": _hash_f64(output),
        },
        tolerance={"kind": "absolute", "atol": 1.0e-12, "rtol": 0.0, "tie_break": "lowest_expert_id"},
    )


def _expert_matrix(kind: int) -> bytes:
    blocks = []
    for row in range(32):
        values = []
        for column in range(32):
            if kind == 0:
                value = (row * 3 + column * 5) % 31 + 1
            elif kind == 1:
                value = (row * 7 + column * 11) % 29 + 1
            elif row == column:
                value = 2
            else:
                value = (row * 13 + column * 3) % 17 - 8
            values.append(value)
        blocks.append(_q8_block(1.0, values))
    return b"".join(blocks)


def _complete_expert() -> dict[str, Any]:
    packed = [_expert_matrix(kind) for kind in range(3)]
    decoded = [_decode_q8_matrix(value, 32) for value in packed]
    activation = [np.float32(1.0 + (index % 8) * 0.125) for index in range(32)]
    gate = _matvec_f32(decoded[0], activation, 32)
    up = _matvec_f32(decoded[1], activation, 32)
    hidden = []
    for gate_value, up_value in zip(gate, up):
        denominator = np.float32(1.0) + np.exp(np.float32(-gate_value), dtype=np.float32)
        silu = np.float32(gate_value / denominator)
        hidden.append(np.float32(silu * up_value))
    output = _matvec_f32(decoded[2], hidden, 32)
    return _boundary(
        version_name="glm52-runtime-expert-q8-0-v2",
        tensor_roles=["expert_gate", "expert_up", "expert_down"],
        dimensions=[32, 32],
        dtype="f32",
        quantization="Q8_0",
        inputs={
            "gate_packed_hex": packed[0].hex(),
            "gate_packed_sha256": _sha256(packed[0]),
            "up_packed_hex": packed[1].hex(),
            "up_packed_sha256": _sha256(packed[1]),
            "down_packed_hex": packed[2].hex(),
            "down_packed_sha256": _sha256(packed[2]),
            "activation": [float(value) for value in activation],
            "activation_sha256": _hash_f32(activation),
        },
        expected={
            "gate_output_sha256": _hash_f32(gate),
            "up_output_sha256": _hash_f32(up),
            "hidden_sha256": _hash_f32(hidden),
            "output": [float(value) for value in output],
            "output_sha256": _hash_f32(output),
        },
        tolerance={"kind": "exact_f32_bits", "atol": 0.0, "rtol": 0.0},
    )


def _top8_shared() -> dict[str, Any]:
    scores = [float(index) for index in range(8)]
    routed = [value for expert in range(8) for value in (float(expert + 1), -float(expert))]
    shared = [0.25, -0.5]
    residual = [1.0, -1.0]
    selected_ids = list(reversed(range(8)))
    weights = _softmax_selected(scores, selected_ids)
    aggregated = [
        sum(weights[expert] * routed[expert * 2 + column] for expert in range(8))
        for column in range(2)
    ]
    output = [aggregated[index] + shared[index] + residual[index] for index in range(2)]
    return _boundary(
        version_name="glm52-runtime-top8-shared-v2",
        tensor_roles=["router_logits", "routed_experts", "shared_expert", "residual"],
        dimensions=[1, 8, 2],
        dtype="f64",
        quantization="F64",
        inputs={
            "scores": scores,
            "scores_sha256": _hash_f64(scores),
            "routed_outputs": routed,
            "routed_outputs_sha256": _hash_f64(routed),
            "shared_output": shared,
            "shared_output_sha256": _hash_f64(shared),
            "residual": residual,
            "residual_sha256": _hash_f64(residual),
        },
        expected={
            "selected_ids": selected_ids,
            "weights": weights,
            "output": output,
            "output_sha256": _hash_f64(output),
        },
        tolerance={"kind": "absolute", "atol": 1.0e-12, "rtol": 0.0},
    )


def _mla_dense() -> dict[str, Any]:
    query = [1.0, 2.0]
    keys = [2.0, 1.0, 1.5, -0.5]
    values = [0.5, -1.0, 1.5, 0.25]
    projection = [1.0, -0.5, 0.25, 1.25]
    residual = [0.75, -0.25]
    rotated_query = _rotate_pair(query, 2, 0.25)
    rotated_keys = [_rotate_pair(keys[0:2], 0, 0.25), _rotate_pair(keys[2:4], 1, 0.25)]
    scores = [sum(left * right for left, right in zip(rotated_query, key)) / math.sqrt(2.0) for key in rotated_keys]
    weights = _softmax_selected(scores, [0, 1])
    attention = [weights[0] * values[index] + weights[1] * values[index + 2] for index in range(2)]
    projected = _matvec2(projection, attention)
    output = [projected[index] + residual[index] for index in range(2)]
    return _boundary(
        version_name="glm52-runtime-mla-dense-v2",
        tensor_roles=["query", "keys", "values", "output_projection", "residual"],
        dimensions=[2, 2, 2],
        dtype="f64",
        quantization="F64",
        inputs={
            "query": query,
            "query_sha256": _hash_f64(query),
            "keys": keys,
            "keys_sha256": _hash_f64(keys),
            "values": values,
            "values_sha256": _hash_f64(values),
            "output_projection": projection,
            "output_projection_sha256": _hash_f64(projection),
            "residual": residual,
            "residual_sha256": _hash_f64(residual),
            "query_position": 2,
            "key_positions": [0, 1],
            "rope_theta": 0.25,
        },
        expected={
            "scores": scores,
            "weights": weights,
            "output": output,
            "output_sha256": _hash_f64(output),
        },
        tolerance={"kind": "absolute", "atol": 1.0e-14, "rtol": 0.0},
    )


def _complete_layer() -> dict[str, Any]:
    inputs = {
        "input": [0.5, -1.0],
        "attention": [0.25, 0.75],
        "routed": [1.0, -0.5],
        "shared": [0.1, 0.2],
        "residual": [0.5, -0.25],
        "output_projection": [1.0, -0.25, 0.5, 1.0],
    }
    combined = [inputs["attention"][index] + inputs["routed"][index] + inputs["shared"][index] for index in range(2)]
    projected = _matvec2(inputs["output_projection"], combined)
    output = [projected[index] + inputs["residual"][index] for index in range(2)]
    input_record: dict[str, Any] = {}
    for name, values in inputs.items():
        input_record[name] = values
        input_record[f"{name}_sha256"] = _hash_f64(values)
    return _boundary(
        version_name="glm52-runtime-complete-layer-v2",
        tensor_roles=["layer_input", "attention", "routed_experts", "shared_expert", "residual", "output_projection"],
        dimensions=[1, 2],
        dtype="f64",
        quantization="F64",
        inputs=input_record,
        expected={"combined": combined, "output": output, "output_sha256": _hash_f64(output)},
        tolerance={"kind": "exact_f64_bits", "atol": 0.0, "rtol": 0.0},
    )


def _final_output() -> dict[str, Any]:
    hidden = [1.2, -0.8, 0.4]
    scale = [1.0, 0.5, 1.5]
    head = [1.0, -0.5, 0.25, 0.1, 1.2, -0.3, -0.7, 0.4, 1.5, 0.9, -1.0, 0.2]
    bias = [0.1, -0.2, 0.05, 0.0]
    epsilon = 1.0e-5
    mean_square = sum(value * value for value in hidden) / len(hidden)
    inverse = 1.0 / math.sqrt(mean_square + epsilon)
    normalized = [value * inverse * factor for value, factor in zip(hidden, scale)]
    logits = [bias[row] + sum(head[row * 3 + column] * normalized[column] for column in range(3)) for row in range(4)]
    topk = sorted(range(len(logits)), key=lambda index: (-logits[index], index))[:2]
    return _boundary(
        version_name="glm52-runtime-final-output-v2",
        tensor_roles=["final_hidden", "final_norm", "output_head", "logits"],
        dimensions=[4, 3],
        dtype="f64",
        quantization="F64",
        inputs={
            "hidden": hidden,
            "hidden_sha256": _hash_f64(hidden),
            "norm_scale": scale,
            "norm_scale_sha256": _hash_f64(scale),
            "output_head": head,
            "output_head_sha256": _hash_f64(head),
            "bias": bias,
            "bias_sha256": _hash_f64(bias),
            "epsilon": epsilon,
            "top_k": 2,
        },
        expected={
            "normalized": normalized,
            "normalized_sha256": _hash_f64(normalized),
            "logits": logits,
            "logits_sha256": _hash_f64(logits),
            "topk": topk,
            "topk_sha256": _hash_u64(topk),
            "argmax": topk[0],
        },
        tolerance={"kind": "absolute", "atol": 1.0e-14, "rtol": 0.0, "tie_break": "lowest_index"},
    )


def _edge_distributions() -> dict[str, Any]:
    patterns = {
        "f16_max_scale": (65504.0, [127 if index % 2 == 0 else -128 for index in range(32)]),
        "f16_min_normal_scale": (2.0 ** -14, [1 if index % 3 == 0 else -1 for index in range(32)]),
        "f16_min_subnormal_scale": (2.0 ** -24, [127 if index % 2 == 0 else -127 for index in range(32)]),
        "zero_and_near_zero": (1.0, [0 if index % 2 == 0 else (1 if index % 4 == 1 else -1) for index in range(32)]),
        "grid_sign_extremes": (0.5, [-128, -127, -64, -1, 0, 1, 63, 127] * 4),
    }
    q8_cases = []
    for name, (scale, quants) in patterns.items():
        packed = _q8_block(scale, quants)
        decoded = _decode_q8_matrix(packed, 1)
        q8_cases.append(
            {
                "name": name,
                "packed_hex": packed.hex(),
                "packed_sha256": _sha256(packed),
                "decoded": [float(value) for value in decoded],
                "decoded_sha256": _hash_f32(decoded),
                "contract": {"kind": "exact_f32_bits", "atol": 0.0, "rtol": 0.0},
            }
        )
    router_cases = [
        {"name": "exact_tie", "scores": [3.0, 3.0, 2.0, -1.0], "topk": [0, 1]},
        {"name": "near_tie", "scores": [3.0, math.nextafter(3.0, math.inf), 2.0, -1.0], "topk": [1, 0]},
    ]
    residual_cases = [
        {"name": "exact_cancellation", "terms": [1.0e16, -1.0e16, 1.0], "sequential_sum": 1.0},
        {"name": "signed_zero", "terms": [0.0, -0.0], "sequential_sum": 0.0},
    ]
    return {"q8_0": q8_cases, "router": router_cases, "residual": residual_cases}


def build_oracle(generator_commit: str) -> dict[str, Any]:
    if len(generator_commit) != 40 or any(character not in "0123456789abcdef" for character in generator_commit):
        raise ValueError("generator commit must be a 40-character lowercase Git SHA")
    python_version = platform.python_version()
    numpy_version = version("numpy")
    if python_version != EXPECTED_PYTHON or numpy_version != EXPECTED_NUMPY:
        raise RuntimeError(
            f"oracle requires Python {EXPECTED_PYTHON} and NumPy {EXPECTED_NUMPY}; "
            f"found Python {python_version} and NumPy {numpy_version}"
        )
    return {
        "schema": SCHEMA,
        "schema_version": 1,
        "feature_id": "017",
        "generator": {
            "implementation": "independent Python/NumPy scalar oracle",
            "path": GENERATOR_PATH,
            "source_commit": generator_commit,
            "python_version": python_version,
            "numpy_version": numpy_version,
            "deterministic_seed": DETERMINISTIC_SEED,
        },
        "source_identity": {
            "fixture_source_commit": SOURCE_COMMIT,
            "checkpoint_set_sha256": CHECKPOINT_SET_SHA256,
            "checkpoint_revision": "public-safe-synthetic-no-checkpoint-bytes",
        },
        "independence": {
            "classification": "INDEPENDENT",
            "uses_rust_candidate": False,
            "uses_rust_reference_functions": False,
            "uses_rust_ffi": False,
            "uses_mlx": False,
            "statement": "Expected values are generated entirely by this Python/NumPy module.",
        },
        "boundaries": {
            "projection": _projection(),
            "router": _router(),
            "complete_expert": _complete_expert(),
            "top8_shared": _top8_shared(),
            "mla_dense": _mla_dense(),
            "complete_layer": _complete_layer(),
            "final_norm_logits_topk": _final_output(),
        },
        "edge_distributions": _edge_distributions(),
        "limitations": [
            "Synthetic fixtures do not exhaust real-checkpoint value distributions.",
            "The M1 Ultra P1 remains the first real-checkpoint integration gate.",
        ],
    }


def _rust_constants(oracle: dict[str, Any]) -> str:
    boundaries = oracle["boundaries"]
    values = {
        "PROJECTION_ENCODED_SHA256": boundaries["projection"]["inputs"]["packed_sha256"],
        "PROJECTION_INPUT_SHA256": boundaries["projection"]["inputs"]["activation_sha256"],
        "PROJECTION_DECODED_SHA256": boundaries["projection"]["expected"]["decoded_sha256"],
        "PROJECTION_REFERENCE_OUTPUT_SHA256": boundaries["projection"]["expected"]["output_sha256"],
        "ROUTER_SCORES_SHA256": boundaries["router"]["inputs"]["scores_sha256"],
        "ROUTER_IDS_SHA256": boundaries["router"]["expected"]["selected_ids_sha256"],
        "ROUTER_WEIGHTS_SHA256": boundaries["router"]["expected"]["weights_sha256"],
        "ROUTER_OUTPUT_SHA256": boundaries["router"]["expected"]["output_sha256"],
        "EXPERT_GATE_SHA256": boundaries["complete_expert"]["inputs"]["gate_packed_sha256"],
        "EXPERT_UP_SHA256": boundaries["complete_expert"]["inputs"]["up_packed_sha256"],
        "EXPERT_DOWN_SHA256": boundaries["complete_expert"]["inputs"]["down_packed_sha256"],
        "EXPERT_INPUT_SHA256": boundaries["complete_expert"]["inputs"]["activation_sha256"],
        "EXPERT_REFERENCE_OUTPUT_SHA256": boundaries["complete_expert"]["expected"]["output_sha256"],
        "TOP8_SHARED_SCORES_SHA256": boundaries["top8_shared"]["inputs"]["scores_sha256"],
        "TOP8_SHARED_ROUTED_SHA256": boundaries["top8_shared"]["inputs"]["routed_outputs_sha256"],
        "TOP8_SHARED_SHARED_SHA256": boundaries["top8_shared"]["inputs"]["shared_output_sha256"],
        "TOP8_SHARED_RESIDUAL_SHA256": boundaries["top8_shared"]["inputs"]["residual_sha256"],
        "TOP8_SHARED_OUTPUT_SHA256": boundaries["top8_shared"]["expected"]["output_sha256"],
        "MLA_DENSE_QUERY_SHA256": boundaries["mla_dense"]["inputs"]["query_sha256"],
        "MLA_DENSE_KEYS_SHA256": boundaries["mla_dense"]["inputs"]["keys_sha256"],
        "MLA_DENSE_VALUES_SHA256": boundaries["mla_dense"]["inputs"]["values_sha256"],
        "MLA_DENSE_PROJECTION_SHA256": boundaries["mla_dense"]["inputs"]["output_projection_sha256"],
        "MLA_DENSE_RESIDUAL_SHA256": boundaries["mla_dense"]["inputs"]["residual_sha256"],
        "MLA_DENSE_OUTPUT_SHA256": boundaries["mla_dense"]["expected"]["output_sha256"],
        "COMPLETE_LAYER_INPUT_SHA256": boundaries["complete_layer"]["inputs"]["input_sha256"],
        "COMPLETE_LAYER_ATTENTION_SHA256": boundaries["complete_layer"]["inputs"]["attention_sha256"],
        "COMPLETE_LAYER_ROUTED_SHA256": boundaries["complete_layer"]["inputs"]["routed_sha256"],
        "COMPLETE_LAYER_SHARED_SHA256": boundaries["complete_layer"]["inputs"]["shared_sha256"],
        "COMPLETE_LAYER_RESIDUAL_SHA256": boundaries["complete_layer"]["inputs"]["residual_sha256"],
        "COMPLETE_LAYER_PROJECTION_SHA256": boundaries["complete_layer"]["inputs"]["output_projection_sha256"],
        "COMPLETE_LAYER_OUTPUT_SHA256": boundaries["complete_layer"]["expected"]["output_sha256"],
        "FINAL_OUTPUT_HIDDEN_SHA256": boundaries["final_norm_logits_topk"]["inputs"]["hidden_sha256"],
        "FINAL_OUTPUT_NORM_SCALE_SHA256": boundaries["final_norm_logits_topk"]["inputs"]["norm_scale_sha256"],
        "FINAL_OUTPUT_HEAD_SHA256": boundaries["final_norm_logits_topk"]["inputs"]["output_head_sha256"],
        "FINAL_OUTPUT_NORM_SHA256": boundaries["final_norm_logits_topk"]["expected"]["normalized_sha256"],
        "FINAL_OUTPUT_LOGITS_SHA256": boundaries["final_norm_logits_topk"]["expected"]["logits_sha256"],
        "FINAL_OUTPUT_TOPK_SHA256": boundaries["final_norm_logits_topk"]["expected"]["topk_sha256"],
    }
    lines = [
        "// @generated by scripts/research/generate_f017_independent_oracle.py",
        f'pub(crate) const F017_ORACLE_GENERATOR_COMMIT: &str = "{oracle["generator"]["source_commit"]}";',
    ]
    for name, value in values.items():
        lines.extend((f"pub(crate) const {name}: &str =", f'    "{value}";'))
    router = boundaries["router"]["expected"]
    projection = boundaries["projection"]["expected"]
    expert = boundaries["complete_expert"]["expected"]
    top8 = boundaries["top8_shared"]["expected"]
    mla = boundaries["mla_dense"]["expected"]
    layer = boundaries["complete_layer"]["expected"]
    final = boundaries["final_norm_logits_topk"]["expected"]
    def append_array(name: str, rust_type: str, length: int, value: Any) -> None:
        lines.extend(("#[rustfmt::skip]", f"pub(crate) const {name}: [{rust_type}; {length}] = {value!r};"))

    append_array("PROJECTION_EXPECTED_OUTPUT", "f32", 2, projection["output"])
    append_array("ROUTER_EXPECTED_IDS", "u64", 4, router["selected_ids"])
    append_array("ROUTER_EXPECTED_WEIGHTS", "f64", 4, router["weights"])
    append_array("ROUTER_EXPECTED_OUTPUT", "f64", 4, router["output"])
    append_array("EXPERT_EXPECTED_OUTPUT", "f32", 32, expert["output"])
    append_array("TOP8_SHARED_EXPECTED_IDS", "u64", 8, top8["selected_ids"])
    append_array("TOP8_SHARED_EXPECTED_WEIGHTS", "f64", 8, top8["weights"])
    append_array("TOP8_SHARED_EXPECTED_OUTPUT", "f64", 2, top8["output"])
    append_array("MLA_DENSE_EXPECTED_OUTPUT", "f64", 2, mla["output"])
    append_array("COMPLETE_LAYER_EXPECTED_OUTPUT", "f64", 2, layer["output"])
    append_array("FINAL_OUTPUT_EXPECTED_NORM", "f64", 3, final["normalized"])
    append_array("FINAL_OUTPUT_EXPECTED_LOGITS", "f64", 4, final["logits"])
    append_array("FINAL_OUTPUT_EXPECTED_TOPK", "u64", 2, final["topk"])
    lines.append(f'pub(crate) const FINAL_OUTPUT_EXPECTED_ARGMAX: usize = {final["argmax"]};')
    lines.append('pub(crate) const ROUTER_ABSOLUTE_TOLERANCE: f64 = 1.0e-12;')
    lines.append('pub(crate) const TOP8_SHARED_ABSOLUTE_TOLERANCE: f64 = 1.0e-12;')
    lines.append('pub(crate) const MLA_DENSE_ABSOLUTE_TOLERANCE: f64 = 1.0e-14;')
    lines.append('pub(crate) const FINAL_OUTPUT_ABSOLUTE_TOLERANCE: f64 = 1.0e-14;')
    return "\n".join(lines).replace("[", "[").replace("]", "]") + "\n"


def _render_json(oracle: dict[str, Any]) -> str:
    return json.dumps(oracle, indent=2, sort_keys=True, allow_nan=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generator-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rust-output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    oracle = build_oracle(arguments.generator_commit)
    rendered_json = _render_json(oracle)
    rendered_rust = _rust_constants(oracle)
    if arguments.check:
        if arguments.output.read_text() != rendered_json:
            raise SystemExit(f"generated oracle drift: {arguments.output}")
        if arguments.rust_output.read_text() != rendered_rust:
            raise SystemExit(f"generated Rust oracle drift: {arguments.rust_output}")
        return 0
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.rust_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(rendered_json)
    arguments.rust_output.write_text(rendered_rust)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
