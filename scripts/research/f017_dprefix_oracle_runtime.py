#!/usr/bin/env python3
"""Immutable NumPy-only oracle machinery for F017 dense-prefix layers 0-2.

This module deliberately imports neither Rust/FFI nor MLX nor the native
candidate.  It consumes an event-local decoded tensor mapping, computes the
position-zero GLM-5.2 boundary, and canonicalizes every retained surface as
little-endian IEEE-754 f32 bytes.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping

import numpy as np

HIDDEN = 6144
Q_LORA = 2048
HEADS = 64
QK_NOPE = 192
QK_ROPE = 64
KV_LORA = 512
VALUE = 256
FFN = 12288
RMS_EPSILON = np.float32(9.999999747378752e-6)


def canonical_f32(values: np.ndarray) -> bytes:
    array = np.asarray(values, dtype=np.float32)
    if not np.isfinite(array).all():
        raise ValueError("oracle non-finite output")
    return array.astype("<f4", copy=False).tobytes(order="C")


def sha_f32(values: np.ndarray) -> str:
    return hashlib.sha256(canonical_f32(values)).hexdigest()


def rms_norm(values: np.ndarray, weight: np.ndarray) -> np.ndarray:
    x = np.asarray(values, dtype=np.float32)
    w = np.asarray(weight, dtype=np.float32)
    if x.ndim != 1 or x.shape != w.shape:
        raise ValueError("oracle RMSNorm shape")
    # f64 reduction is the independent reference construction; the result is
    # rounded once at the output boundary.
    mean_square = float(np.dot(x.astype(np.float64), x.astype(np.float64))) / x.size
    inverse = np.float32(1.0 / math.sqrt(mean_square + float(RMS_EPSILON)))
    return np.asarray(x * inverse * w, dtype=np.float32)


def matvec(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    weight = np.asarray(matrix, dtype=np.float32)
    x = np.asarray(vector, dtype=np.float32)
    if weight.ndim != 2 or x.ndim != 1 or weight.shape[1] != x.shape[0]:
        raise ValueError("oracle matvec shape")
    # NumPy is the independently bound compute implementation.  No candidate
    # intermediate or metric enters this path.
    return np.asarray(weight @ x, dtype=np.float32)


def swiglu(gate: np.ndarray, up: np.ndarray) -> np.ndarray:
    gate = np.asarray(gate, dtype=np.float32)
    up = np.asarray(up, dtype=np.float32)
    if gate.shape != up.shape or gate.ndim != 1:
        raise ValueError("oracle SwiGLU shape")
    return np.asarray((gate / (np.float32(1.0) + np.exp(-gate))) * up, dtype=np.float32)


def _tensor(tensors: Mapping[str, np.ndarray], name: str) -> np.ndarray:
    try:
        return np.asarray(tensors[name], dtype=np.float32)
    except KeyError as error:
        raise ValueError(f"oracle tensor absent: {name}") from error


def layer_position_zero_surfaces(
    tensors: Mapping[str, np.ndarray], layer: int, residual: np.ndarray
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    prefix = f"blk.{layer}"
    x_norm = rms_norm(residual, _tensor(tensors, f"{prefix}.attn_norm.weight"))
    q_rank = matvec(_tensor(tensors, f"{prefix}.attn_q_a.weight"), x_norm)
    q_rank_norm = rms_norm(q_rank, _tensor(tensors, f"{prefix}.attn_q_a_norm.weight"))
    query = matvec(_tensor(tensors, f"{prefix}.attn_q_b.weight"), q_rank_norm)
    if query.shape != (HEADS * (QK_NOPE + QK_ROPE),):
        raise ValueError("oracle query shape")
    # RoPE at position zero is exactly the identity.
    kv_raw = matvec(_tensor(tensors, f"{prefix}.attn_kv_a_mqa.weight"), x_norm)
    if kv_raw.shape != (KV_LORA + QK_ROPE,):
        raise ValueError("oracle KV shape")
    kv = rms_norm(kv_raw[:KV_LORA], _tensor(tensors, f"{prefix}.attn_kv_a_norm.weight"))
    keys = np.empty((HEADS, QK_NOPE), dtype=np.float32)
    values = np.empty((HEADS, VALUE), dtype=np.float32)
    key_weights = _tensor(tensors, f"{prefix}.attn_k_b.weight")
    value_weights = _tensor(tensors, f"{prefix}.attn_v_b.weight")
    if key_weights.shape != (HEADS, QK_NOPE, KV_LORA):
        raise ValueError("oracle key-head shape")
    if value_weights.shape != (HEADS, VALUE, KV_LORA):
        raise ValueError("oracle value-head shape")
    for head in range(HEADS):
        keys[head] = matvec(key_weights[head], kv)
        values[head] = matvec(value_weights[head], kv)
    # There is exactly one visible token, so softmax has weight one.  Query
    # and key paths are still computed and retained as analytical surfaces.
    attention = matvec(_tensor(tensors, f"{prefix}.attn_output.weight"), values.reshape(-1))
    attention_residual = np.asarray(residual + attention, dtype=np.float32)
    ffn_input = rms_norm(attention_residual, _tensor(tensors, f"{prefix}.ffn_norm.weight"))
    gate = matvec(_tensor(tensors, f"{prefix}.ffn_gate.weight"), ffn_input)
    up = matvec(_tensor(tensors, f"{prefix}.ffn_up.weight"), ffn_input)
    activated = swiglu(gate, up)
    down = matvec(_tensor(tensors, f"{prefix}.ffn_down.weight"), activated)
    output = np.asarray(attention_residual + down, dtype=np.float32)
    return output, {
        f"layer_{layer}_q": query.copy(),
        f"layer_{layer}_keys": keys.reshape(-1).copy(),
        f"layer_{layer}_attention": attention.copy(),
        f"layer_{layer}_attention_residual": attention_residual.copy(),
        f"layer_{layer}_ffn": down.copy(),
        f"layer_{layer}_output": output.copy(),
    }


def layer_position_zero(
    tensors: Mapping[str, np.ndarray], layer: int, residual: np.ndarray
) -> tuple[np.ndarray, dict[str, str]]:
    output, surfaces = layer_position_zero_surfaces(tensors, layer, residual)
    return output, {name: sha_f32(values) for name, values in surfaces.items()}


def dense_prefix_surfaces(
    tensors: Mapping[str, np.ndarray], token: int = 9703
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    if token != 9703:
        raise ValueError("oracle input substitution")
    embedding = _tensor(tensors, "token_embd.weight")
    if embedding.shape != (154880, HIDDEN):
        raise ValueError("oracle embedding shape")
    hidden = np.asarray(embedding[token], dtype=np.float32).copy()
    stages = {"embedding": hidden.copy()}
    for layer in range(3):
        hidden, layer_stages = layer_position_zero_surfaces(tensors, layer, hidden)
        stages.update(layer_stages)
    stages["layer_3_entry"] = hidden.copy()
    return hidden, stages


def dense_prefix(
    tensors: Mapping[str, np.ndarray], token: int = 9703
) -> tuple[np.ndarray, dict[str, str]]:
    hidden, surfaces = dense_prefix_surfaces(tensors, token)
    return hidden, {name: sha_f32(values) for name, values in surfaces.items()}


def synthetic_dimensions() -> dict[str, int]:
    """Record the production dimensions independently of synthetic fixtures."""
    return {
        "hidden": HIDDEN,
        "q_lora": Q_LORA,
        "heads": HEADS,
        "qk_nope": QK_NOPE,
        "qk_rope": QK_ROPE,
        "kv_lora": KV_LORA,
        "value": VALUE,
        "ffn": FFN,
    }


def _deterministic_matrix(rows: int, columns: int, salt: int) -> np.ndarray:
    indexes = np.arange(rows * columns, dtype=np.uint64)
    values = ((indexes * 17 + salt * 31) % 257).astype(np.float32)
    return ((values - np.float32(128.0)) / np.float32(4096.0)).reshape(rows, columns)


def synthetic_actual_binary_oracle_surfaces() -> dict[str, np.ndarray]:
    """Independent NumPy oracle for the bounded actual-binary rehearsal.

    The dimensions and deterministic matrix rule are frozen public fixture
    facts.  This function shares no candidate arithmetic implementation.
    """
    hidden, q_lora, heads = 6144, 32, 4
    qk_nope, qk_rope, kv_lora, value, ffn = 8, 8, 16, 16, 96
    residual = (np.arange(hidden, dtype=np.float32) - np.float32(3071.5)) / np.float32(4096.0)
    surfaces = {"embedding": residual.copy()}
    ones_hidden = np.ones(hidden, dtype=np.float32)
    for layer in range(3):
        x_norm = rms_norm(residual, ones_hidden)
        q_rank = matvec(_deterministic_matrix(q_lora, hidden, 100 + layer), x_norm)
        q_rank_norm = rms_norm(q_rank, np.ones(q_lora, dtype=np.float32))
        query = matvec(_deterministic_matrix(heads * (qk_nope + qk_rope), q_lora, 200 + layer), q_rank_norm)
        kv_raw = matvec(_deterministic_matrix(kv_lora + qk_rope, hidden, 300 + layer), x_norm)
        kv = rms_norm(kv_raw[:kv_lora], np.ones(kv_lora, dtype=np.float32))
        keys = []
        values = []
        for head in range(heads):
            keys.append(matvec(_deterministic_matrix(qk_nope, kv_lora, 400 + layer * 97 + head), kv))
            values.append(matvec(_deterministic_matrix(value, kv_lora, 500 + layer * 97 + head), kv))
        if query.size == 0 or sum(item.size for item in keys) == 0:
            raise ValueError("oracle analytical surfaces absent")
        attention = matvec(_deterministic_matrix(hidden, heads * value, 600 + layer), np.concatenate(values))
        surfaces[f"layer_{layer}_attention"] = attention.copy()
        attention_residual = np.asarray(residual + attention, dtype=np.float32)
        ffn_input = rms_norm(attention_residual, ones_hidden)
        gate = matvec(_deterministic_matrix(ffn, hidden, 700 + layer), ffn_input)
        up = matvec(_deterministic_matrix(ffn, hidden, 800 + layer), ffn_input)
        down = matvec(_deterministic_matrix(hidden, ffn, 900 + layer), swiglu(gate, up))
        residual = np.asarray(attention_residual + down, dtype=np.float32)
        surfaces[f"layer_{layer}_output"] = residual.copy()
    if residual.shape != (HIDDEN,):
        raise ValueError("oracle synthetic hidden width")
    surfaces["layer_3_entry"] = residual.copy()
    return surfaces


def synthetic_actual_binary_oracle() -> np.ndarray:
    return synthetic_actual_binary_oracle_surfaces()["layer_3_entry"].copy()
