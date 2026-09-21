#!/usr/bin/env python3
"""Pure binary64 numerical core for the F017 corrected oracle.

This module contains only geometry, synthetic in-memory tensors, fixed-order
binary64 graph arithmetic, and numerical result construction.  It has no file,
checkpoint, authorization, access-event, lifecycle, or command-line surface.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

ORACLE_ID = "F017_INDEPENDENT_CPU_REFERENCE_V1"
TOP_N = 32

def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _hash_f64(values: list[float]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(struct.pack("<d", float(value)))
    return digest.hexdigest()


def _hash_json(value: object) -> str:
    return hashlib.sha256((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()


@dataclass(frozen=True)
class Geometry:
    layers: int
    hidden: int
    vocab: int
    dense_layers: int
    experts: int
    top_k: int
    dense_ffn: int
    expert_ffn: int
    heads: int
    q_rank: int
    kv_rank: int
    qk_nope: int
    qk_rope: int
    value_dim: int
    rms_epsilon: float
    rope_base: float
    route_scale: float

    @classmethod
    def from_json(cls, value: dict) -> "Geometry":
        expected = set(cls.__annotations__)
        if not expected.issubset(value):
            raise ValueError("geometry key census")
        result = cls(**{key: value[key] for key in expected})
        if result.layers < 1 or result.hidden < 1 or result.vocab < 2 or result.qk_rope % 2:
            raise ValueError("invalid geometry")
        return result


class Source(Protocol):
    def vector(self, name: str, length: int) -> list[float]: ...
    def matrix(self, name: str, rows: int, columns: int) -> list[float]: ...
    def expert(self, name: str, expert: int, rows: int, columns: int) -> list[float]: ...


class JsonSource:
    """Qualification source; structurally has no checkpoint path or file API."""
    def __init__(self, tensors: dict):
        self.tensors = tensors

    def _get(self, key: str, count: int) -> list[float]:
        value = self.tensors.get(key)
        if not isinstance(value, list) or len(value) != count:
            raise ValueError(f"synthetic tensor geometry: {key}")
        output = [float(v) for v in value]
        if not all(math.isfinite(v) for v in output):
            raise ValueError(f"nonfinite synthetic tensor: {key}")
        return output

    def vector(self, name: str, length: int) -> list[float]:
        return self._get(name, length)

    def matrix(self, name: str, rows: int, columns: int) -> list[float]:
        return self._get(name, rows * columns)

    def expert(self, name: str, expert: int, rows: int, columns: int) -> list[float]:
        return self._get(f"{name}#{expert}", rows * columns)




@runtime_checkable
class RowMatrix(Protocol):
    rows: int
    columns: int

    def row(self, index: int) -> list[float]: ...




def _matvec(matrix: list[float], rows: int, columns: int, vector: list[float]) -> list[float]:
    if isinstance(matrix, RowMatrix):
        if matrix.rows != rows or matrix.columns != columns: raise ValueError("streaming matvec shape")
        output = []
        for row in range(rows):
            weights = matrix.row(row)
            if len(weights) != columns or len(vector) != columns:
                raise ValueError("streaming matvec geometry")
            total = 0.0
            for column in range(columns):
                total += float(weights[column]) * float(vector[column])
            output.append(total)
        return output
    if len(matrix) != rows * columns or len(vector) != columns:
        raise ValueError("matvec shape")
    output = []
    for row in range(rows):
        total = 0.0
        for column in range(columns):
            total += float(matrix[row * columns + column]) * float(vector[column])
        output.append(total)
    return output


def _transpose_matvec(matrix: list[float], rows: int, columns: int,
                      vector: list[float]) -> list[float]:
    """Fixed-order matrix-transpose/vector product.

    The GLM MLA K-B tensor is stored as ``[kv_rank, qk_nope]`` for the
    production contraction.  Constructing the explicit key requires the
    transpose product; keeping this operation visible prevents a one-key
    shortcut from silently deleting K semantics.
    """
    if len(vector) != rows:
        raise ValueError("transpose matvec shape")
    if isinstance(matrix, RowMatrix):
        if matrix.rows != rows or matrix.columns != columns:
            raise ValueError("streaming transpose matvec shape")
        output = [0.0] * columns
        for row in range(rows):
            value = float(vector[row])
            for column, weight in enumerate(matrix.row(row)):
                output[column] += float(weight) * value
        return output
    if len(matrix) != rows * columns:
        raise ValueError("transpose matvec shape")
    output = [0.0] * columns
    for row in range(rows):
        for column in range(columns):
            output[column] += float(matrix[row * columns + column]) * float(vector[row])
    return output


def _rms(x: list[float], weight: list[float], epsilon: float) -> list[float]:
    inv = 1.0 / math.sqrt(sum(value * value for value in x) / len(x) + float(epsilon))
    return [value * inv * scale for value, scale in zip(x, weight, strict=True)]


def _silu(value: float) -> float:
    return value / (1.0 + math.exp(-value))


def _residual(left: list[float], right: list[float]) -> list[float]:
    return [a + b for a, b in zip(left, right, strict=True)]


def _projection(source: Source, prefix: str, suffix: str, rows: int, columns: int,
                expert: int | None = None, shared: bool = False) -> list[float]:
    if expert is not None:
        return source.expert(f"{prefix}_{suffix}_exps.weight", expert, rows, columns)
    name = f"{prefix}_{suffix}_shexp.weight" if shared else f"{prefix}_{suffix}.weight"
    return source.matrix(name, rows, columns)


def _swiglu(source: Source, prefix: str, x: list[float], inner: int, hidden: int,
            expert: int | None = None, shared: bool = False, weight: float = 1.0) -> list[float]:
    gate = _matvec(_projection(source, prefix, "gate", inner, len(x), expert, shared), inner, len(x), x)
    up = _matvec(_projection(source, prefix, "up", inner, len(x), expert, shared), inner, len(x), x)
    product = [_silu(g) * u * weight for g, u in zip(gate, up, strict=True)]
    return _matvec(_projection(source, prefix, "down", hidden, inner, expert, shared), hidden, inner, product)


def _route(logits: list[float], bias: list[float], count: int, scale: float) -> tuple[list[int], list[float]]:
    probabilities = [1.0 / (1.0 + math.exp(-value)) for value in logits]
    order = sorted(range(len(logits)), key=lambda i: (-(probabilities[i] + bias[i]), i))[:count]
    denominator = max(sum(probabilities[i] for i in order), 2.0 ** -14)
    return order, [probabilities[i] / denominator * scale for i in order]


@dataclass(frozen=True)
class PrimaryLayerCapture:
    layer: int
    layer_input_sha256: str
    post_attention_residual_sha256: str
    router_normalized_sha256: str
    selected_expert_ids: tuple[int, ...]
    attention_score_f64_bits: tuple[str, ...]
    routing_weight_f64_bits: tuple[str, ...]
    routed_aggregate_sha256: str | None
    shared_output_sha256: str | None
    layer_output_sha256: str


@dataclass(frozen=True)
class PrimaryTopRecord:
    token_id: int
    logit_f64_bits: str


@dataclass(frozen=True)
class PrimaryNumericalOutputs:
    role: str
    dtype: str
    core_execution_count: int
    final_hidden_element_count: int
    final_normalized_element_count: int
    full_logits_element_count: int
    final_hidden_payload: bytes
    final_normalized_payload: bytes
    full_logits_payload: bytes
    final_hidden_sha256: str
    final_normalized_sha256: str
    full_logits_sha256: str
    layer_captures: tuple[PrimaryLayerCapture, ...]
    selected_token: int
    top_32: tuple[PrimaryTopRecord, ...]
    top_1_margin: float
    tie_rule: str


@dataclass(frozen=True)
class _ExecutionState:
    hidden: list[float]
    final_normalized: list[float]
    logits: list[float]
    captures: list[dict]
    order: list[int]
    selected: int


def _execute_graph(source: Source, geometry: Geometry, token: int, position: int = 0) -> _ExecutionState:
    if not 0 <= token < geometry.vocab or position < 0:
        raise ValueError("token/position")
    embedding = source.matrix("token_embd.weight", geometry.vocab, geometry.hidden)
    hidden = embedding[token * geometry.hidden:(token + 1) * geometry.hidden]
    captures = []
    for layer in range(geometry.layers):
        layer_input = list(hidden)
        normalized = _rms(hidden, source.vector(f"blk.{layer}.attn_norm.weight", geometry.hidden), geometry.rms_epsilon)
        qa = _matvec(source.matrix(f"blk.{layer}.attn_q_a.weight", geometry.q_rank, geometry.hidden), geometry.q_rank, geometry.hidden, normalized)
        qan = _rms(qa, source.vector(f"blk.{layer}.attn_q_a_norm.weight", geometry.q_rank), geometry.rms_epsilon)
        qdim = geometry.qk_nope + geometry.qk_rope
        q = _matvec(source.matrix(f"blk.{layer}.attn_q_b.weight", geometry.heads * qdim, geometry.q_rank), geometry.heads * qdim, geometry.q_rank, qan)
        kv = _matvec(source.matrix(f"blk.{layer}.attn_kv_a_mqa.weight", geometry.kv_rank + geometry.qk_rope, geometry.hidden), geometry.kv_rank + geometry.qk_rope, geometry.hidden, normalized)
        kvn = _rms(kv[:geometry.kv_rank], source.vector(f"blk.{layer}.attn_kv_a_norm.weight", geometry.kv_rank), geometry.rms_epsilon)
        # The bounded event has one causal key, but it still instantiates the
        # complete Q/K/RoPE/score/softmax surface.  A one-element softmax is
        # exactly one; that fact is an outcome of the frozen context, not a
        # license to omit K or score construction.
        key_rope = list(kv[geometry.kv_rank:])
        for head in range(geometry.heads):
            for lane in range(0, geometry.qk_rope, 2):
                theta = position / geometry.rope_base ** (lane / geometry.qk_rope)
                c, s = math.cos(theta), math.sin(theta)
                base = head * qdim + geometry.qk_nope + lane
                q[base], q[base + 1] = q[base] * c - q[base + 1] * s, q[base] * s + q[base + 1] * c
        for lane in range(0, geometry.qk_rope, 2):
            theta = position / geometry.rope_base ** (lane / geometry.qk_rope)
            c, s = math.cos(theta), math.sin(theta)
            key_rope[lane], key_rope[lane + 1] = (
                key_rope[lane] * c - key_rope[lane + 1] * s,
                key_rope[lane] * s + key_rope[lane + 1] * c,
            )
        values = []
        attention_scores = []
        for head in range(geometry.heads):
            value = _matvec(source.expert(f"blk.{layer}.attn_v_b.weight", head, geometry.value_dim, geometry.kv_rank), geometry.value_dim, geometry.kv_rank, kvn)
            key_nope = _transpose_matvec(
                source.expert(f"blk.{layer}.attn_k_b.weight", head, geometry.kv_rank, geometry.qk_nope),
                geometry.kv_rank, geometry.qk_nope, kvn,
            )
            qbase = head * qdim
            q_nope = q[qbase:qbase + geometry.qk_nope]
            q_rope = q[qbase + geometry.qk_nope:qbase + qdim]
            score = (sum(a * b for a, b in zip(q_nope, key_nope, strict=True))
                     + sum(a * b for a, b in zip(q_rope, key_rope, strict=True))) / math.sqrt(qdim)
            if not math.isfinite(score):
                raise ValueError("attention score")
            attention_scores.append(struct.pack("<d", score).hex())
            softmax_weight = math.exp(score - score)
            softmax_weight /= softmax_weight
            values.extend(component * softmax_weight for component in value)
        attention = _matvec(source.matrix(f"blk.{layer}.attn_output.weight", geometry.hidden, geometry.heads * geometry.value_dim), geometry.hidden, geometry.heads * geometry.value_dim, values)
        hidden = _residual(hidden, attention)
        post_attention = list(hidden)
        router_input = _rms(hidden, source.vector(f"blk.{layer}.ffn_norm.weight", geometry.hidden), geometry.rms_epsilon)
        selected, weights, routed, shared = [], [], [], []
        if layer < geometry.dense_layers:
            ffn = _swiglu(source, f"blk.{layer}.ffn", router_input, geometry.dense_ffn, geometry.hidden)
        else:
            logits = _matvec(source.matrix(f"blk.{layer}.ffn_gate_inp.weight", geometry.experts, geometry.hidden), geometry.experts, geometry.hidden, router_input)
            selected, weights = _route(logits, source.vector(f"blk.{layer}.exp_probs_b.bias", geometry.experts), geometry.top_k, geometry.route_scale)
            routed = [0.0] * geometry.hidden
            for expert, route_weight in zip(selected, weights, strict=True):
                part = _swiglu(source, f"blk.{layer}.ffn", router_input, geometry.expert_ffn, geometry.hidden, expert=expert, weight=route_weight)
                routed = _residual(routed, part)
            shared = _swiglu(source, f"blk.{layer}.ffn", router_input, geometry.expert_ffn, geometry.hidden, shared=True)
            ffn = _residual(routed, shared)
        hidden = _residual(hidden, ffn)
        captures.append({
            "layer": layer, "layer_input_sha256": _hash_f64(layer_input),
            "post_attention_residual_sha256": _hash_f64(post_attention),
            "router_normalized_sha256": _hash_f64(router_input),
            "selected_expert_ids": selected,
            "attention_score_f64_bits": attention_scores,
            "routing_weight_f64_bits": [struct.pack("<d", w).hex() for w in weights],
            "routed_aggregate_sha256": _hash_f64(routed) if routed else None,
            "shared_output_sha256": _hash_f64(shared) if shared else None,
            "layer_output_sha256": _hash_f64(hidden),
        })
    final_norm = _rms(hidden, source.vector("output_norm.weight", geometry.hidden), geometry.rms_epsilon)
    logits = _matvec(source.matrix("output.weight", geometry.vocab, geometry.hidden), geometry.vocab, geometry.hidden, final_norm)
    order = sorted(range(len(logits)), key=lambda index: (-logits[index], index))
    selected = order[0]
    return _ExecutionState(
        hidden=hidden,
        final_normalized=final_norm,
        logits=logits,
        captures=captures,
        order=order,
        selected=selected,
    )


def _payload_f64le(values: list[float]) -> bytes:
    return b"".join(struct.pack("<d", float(value)) for value in values)


def _build_legacy_result(state: _ExecutionState, geometry: Geometry, position: int) -> dict:
    result = {
        "schema": "pulsarmlx.f017.corrected-full-checkpoint-primary-oracle-result/1.0.0",
        "oracle": ORACLE_ID, "position": position, "layer_count": geometry.layers,
        "layers": state.captures, "final_hidden_sha256": _hash_f64(state.hidden),
        "final_norm_sha256": _hash_f64(state.final_normalized), "full_logits_sha256": _hash_f64(state.logits),
        "full_logits": state.logits, "top_n": TOP_N,
        "top": [{"token_id": i, "logit_f64_bits": struct.pack("<d", state.logits[i]).hex()} for i in state.order[:TOP_N]],
        "top_1_margin": state.logits[state.order[0]] - state.logits[state.order[1]], "selected_token": state.selected,
        "tie_rule": "LOWEST_TOKEN_ID_ON_EQUAL_BINARY64_LOGIT",
    }
    result["result_sha256"] = _hash_json(result)
    return result


def _freeze_capture(value: dict) -> PrimaryLayerCapture:
    return PrimaryLayerCapture(
        layer=value["layer"],
        layer_input_sha256=value["layer_input_sha256"],
        post_attention_residual_sha256=value["post_attention_residual_sha256"],
        router_normalized_sha256=value["router_normalized_sha256"],
        selected_expert_ids=tuple(value["selected_expert_ids"]),
        attention_score_f64_bits=tuple(value["attention_score_f64_bits"]),
        routing_weight_f64_bits=tuple(value["routing_weight_f64_bits"]),
        routed_aggregate_sha256=value["routed_aggregate_sha256"],
        shared_output_sha256=value["shared_output_sha256"],
        layer_output_sha256=value["layer_output_sha256"],
    )


def execute_outputs(source: Source, geometry: Geometry, token: int, position: int = 0) -> PrimaryNumericalOutputs:
    state = _execute_graph(source, geometry, token, position)
    final_hidden_payload = _payload_f64le(state.hidden)
    final_normalized_payload = _payload_f64le(state.final_normalized)
    full_logits_payload = _payload_f64le(state.logits)
    return PrimaryNumericalOutputs(
        role="PRIMARY",
        dtype="f64le",
        core_execution_count=1,
        final_hidden_element_count=len(state.hidden),
        final_normalized_element_count=len(state.final_normalized),
        full_logits_element_count=len(state.logits),
        final_hidden_payload=final_hidden_payload,
        final_normalized_payload=final_normalized_payload,
        full_logits_payload=full_logits_payload,
        final_hidden_sha256=hashlib.sha256(final_hidden_payload).hexdigest(),
        final_normalized_sha256=hashlib.sha256(final_normalized_payload).hexdigest(),
        full_logits_sha256=hashlib.sha256(full_logits_payload).hexdigest(),
        layer_captures=tuple(_freeze_capture(value) for value in state.captures),
        selected_token=state.selected,
        top_32=tuple(PrimaryTopRecord(i, struct.pack("<d", state.logits[i]).hex()) for i in state.order[:TOP_N]),
        top_1_margin=state.logits[state.order[0]] - state.logits[state.order[1]],
        tie_rule="LOWEST_TOKEN_ID_ON_EQUAL_BINARY64_LOGIT",
    )


def execute(source: Source, geometry: Geometry, token: int, position: int = 0) -> dict:
    return _build_legacy_result(_execute_graph(source, geometry, token, position), geometry, position)
