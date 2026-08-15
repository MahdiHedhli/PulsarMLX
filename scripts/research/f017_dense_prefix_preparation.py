"""Checkpoint-free preparation for a future real dense-prefix layer-3 state.

The synthetic integration uses real GLM-5.2 logical dimensions but structured,
matrix-free operators.  It never opens a checkpoint, catalog shard, or MLX
context.  The module also supplies strict config/evidence/route-binding and
dispatch validators for future separately reviewed gates.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


HIDDEN = 6144
Q_LORA = 2048
Q_OUT = 16384
KV_LORA = 512
KV_ROPE = 64
K_OUT = 12288
V_OUT = 16384
FFN = 12288
LAYERS = 3
REPEATS = 10
V3_SHA256 = "c5662a611abc000703606d799a7214ee27e39c556bc6595f217c86498e944a85"
V3_PREDECESSOR_SHA256 = "befbf30f85e12b779e7d5c778f337a5f7d6019a15805e04805a24e4903ea3969"
LEDGER = 57


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def f32_bytes(value: np.ndarray) -> bytes:
    return np.asarray(value, dtype="<f4").tobytes(order="C")


def rms_norm(value: np.ndarray, *, eps: float, dtype: np.dtype) -> np.ndarray:
    x = np.asarray(value, dtype=dtype)
    mean_square = np.mean(x * x, dtype=dtype)
    scale = np.asarray(1.0 / np.sqrt(mean_square + np.asarray(eps, dtype=dtype)), dtype=dtype)
    return np.asarray(x * scale, dtype=dtype)


def structured_project(value: np.ndarray, out_dim: int, seed: int, *, dtype: np.dtype) -> np.ndarray:
    """Deterministic real-shaped matrix-free linear-like projection.

    Every output samples four input positions with fixed signed coefficients.
    It is deliberately independent from real tensor bytes and exercises f32
    materialization/reduction behavior without allocating a real weight matrix.
    """
    x = np.asarray(value, dtype=dtype)
    if x.ndim != 1 or x.size == 0 or out_dim <= 0:
        raise ValueError("structured projection shape")
    i = np.arange(out_dim, dtype=np.int64)
    n = x.size
    a = x[(i * 17 + seed * 13) % n]
    b = x[(i * 29 + seed * 7 + 3) % n]
    c = x[(i * 43 + seed * 11 + 5) % n]
    d = x[(i * 61 + seed * 5 + 9) % n]
    coefficients = tuple(np.asarray(v, dtype=dtype) for v in (0.375, -0.25, 0.1875, 0.125))
    result = ((a * coefficients[0] + b * coefficients[1]) + c * coefficients[2]) + d * coefficients[3]
    return np.asarray(result, dtype=dtype)


def synthetic_embedding(token: int, *, dtype: np.dtype) -> np.ndarray:
    if token != 9703:
        raise ValueError("dense-prefix synthetic qualification is frozen to P-MIN token 9703")
    index = np.arange(HIDDEN, dtype=np.float64)
    value = np.sin((index + 1.0) * 0.0009765625 + token * 1e-5)
    value += 0.5 * np.cos((index + 3.0) * 0.001953125 - token * 2e-5)
    value[:8] = np.array([0.0, -0.0, np.finfo(np.float32).tiny, -np.finfo(np.float32).tiny, 1e-4, -1e-4, 1.0, -1.0])
    return np.asarray(value, dtype=dtype)


def dense_layer(value: np.ndarray, layer: int, *, dtype: np.dtype) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    if layer not in range(LAYERS) or value.shape != (HIDDEN,):
        raise ValueError("dense layer boundary")
    attn_norm = rms_norm(value, eps=1e-6, dtype=dtype)
    q_a = structured_project(attn_norm, Q_LORA, 100 + layer, dtype=dtype)
    q_b = structured_project(rms_norm(q_a, eps=1e-6, dtype=dtype), Q_OUT, 110 + layer, dtype=dtype)
    kv = structured_project(attn_norm, KV_LORA + KV_ROPE, 120 + layer, dtype=dtype)
    kv_latent = rms_norm(kv[:KV_LORA], eps=1e-6, dtype=dtype)
    k = structured_project(kv_latent, K_OUT, 130 + layer, dtype=dtype)
    v = structured_project(kv_latent, V_OUT, 140 + layer, dtype=dtype)
    # Position zero is range_fill([0]); self-attention has one permitted key.
    q_scalar = np.asarray(np.mean(q_b, dtype=dtype), dtype=dtype)
    k_scalar = np.asarray(np.mean(k, dtype=dtype), dtype=dtype)
    attention_probability = np.asarray(1.0, dtype=dtype)
    attention_heads = np.asarray(v * attention_probability, dtype=dtype)
    attention_output = structured_project(attention_heads, HIDDEN, 150 + layer, dtype=dtype)
    attention_residual = np.asarray(value + attention_output, dtype=dtype)
    ffn_input = rms_norm(attention_residual, eps=1e-6, dtype=dtype)
    gate = structured_project(ffn_input, FFN, 160 + layer, dtype=dtype)
    up = structured_project(ffn_input, FFN, 170 + layer, dtype=dtype)
    silu_gate = np.asarray(gate / (1.0 + np.exp(-gate)), dtype=dtype)
    hidden = np.asarray(silu_gate * up, dtype=dtype)
    down = structured_project(hidden, HIDDEN, 180 + layer, dtype=dtype)
    output = np.asarray(attention_residual + down, dtype=dtype)
    stages = {
        "attn_normalized": attn_norm,
        "q_a": q_a,
        "q_b": q_b,
        "kv_a_mqa": kv,
        "k_b": k,
        "v_b": v,
        "attention_output": attention_output,
        "attention_residual": attention_residual,
        "ffn_normalized": ffn_input,
        "ffn_gate": gate,
        "ffn_up": up,
        "ffn_down": down,
        "output": output,
        "attention_score_scalar": np.asarray([q_scalar * k_scalar], dtype=dtype),
    }
    return output, stages


def run_synthetic_dense_prefix(*, dtype: np.dtype) -> dict[str, Any]:
    state = synthetic_embedding(9703, dtype=dtype)
    layer_records = []
    for layer in range(LAYERS):
        state, stages = dense_layer(state, layer, dtype=dtype)
        layer_records.append(
            {
                "layer": layer,
                "stage_shapes": {name: list(array.shape) for name, array in stages.items()},
                "stage_hashes": {name: sha256(f32_bytes(array)) for name, array in stages.items()},
            }
        )
    return {
        "token": 9703,
        "position": 0,
        "dsa": "range_fill([0])",
        "embedding_sha256": sha256(f32_bytes(synthetic_embedding(9703, dtype=dtype))),
        "layers": layer_records,
        "layer3_entry_sha256": sha256(f32_bytes(state)),
        "layer3_entry": np.asarray(state, dtype=np.float64),
    }


def oracle_structured_project(value: np.ndarray, out_dim: int, seed: int) -> np.ndarray:
    """Independent binary64 transcription of the structured projection.

    This path deliberately does not call ``structured_project``: it gathers
    all four terms into a 2-D array and performs one explicit binary64 axis
    reduction, while the candidate uses staged binary32 arithmetic.
    """
    x = np.asarray(value, dtype=np.float64)
    i = np.arange(out_dim, dtype=np.int64)
    n = x.size
    terms = np.vstack((
        x[(i * 17 + seed * 13) % n] * 0.375,
        x[(i * 29 + seed * 7 + 3) % n] * -0.25,
        x[(i * 43 + seed * 11 + 5) % n] * 0.1875,
        x[(i * 61 + seed * 5 + 9) % n] * 0.125,
    ))
    return np.add.reduce(terms, axis=0, dtype=np.float64)


def oracle_rms_norm(value: np.ndarray) -> np.ndarray:
    x = np.asarray(value, dtype=np.float64)
    denominator = math.sqrt(math.fsum(float(v * v) for v in x) / x.size + 1e-6)
    return x / denominator


def oracle_dense_layer(value: np.ndarray, layer: int) -> np.ndarray:
    """Independent scalar-denominator/binary64 dense-layer oracle path."""
    attn_norm = oracle_rms_norm(value)
    q_a = oracle_structured_project(attn_norm, Q_LORA, 100 + layer)
    q_b = oracle_structured_project(oracle_rms_norm(q_a), Q_OUT, 110 + layer)
    kv = oracle_structured_project(attn_norm, KV_LORA + KV_ROPE, 120 + layer)
    kv_latent = oracle_rms_norm(kv[:KV_LORA])
    # Q/K means intentionally exercise the attention scaffold even though the
    # position-zero causal softmax is exactly one.
    _ = math.fsum(oracle_structured_project(kv_latent, K_OUT, 130 + layer)) / K_OUT
    v = oracle_structured_project(kv_latent, V_OUT, 140 + layer)
    attention_output = oracle_structured_project(v, HIDDEN, 150 + layer)
    attention_residual = value + attention_output
    ffn_input = oracle_rms_norm(attention_residual)
    gate = oracle_structured_project(ffn_input, FFN, 160 + layer)
    up = oracle_structured_project(ffn_input, FFN, 170 + layer)
    hidden = (gate / (1.0 + np.exp(-gate))) * up
    return attention_residual + oracle_structured_project(hidden, HIDDEN, 180 + layer)


def run_independent_oracle_dense_prefix() -> np.ndarray:
    state = synthetic_embedding(9703, dtype=np.float64)
    for layer in range(LAYERS):
        state = oracle_dense_layer(state, layer)
    return state


NUMERICAL_THRESHOLDS = {
    "max_abs_error": 2.0 ** -10,
    "rmse": 2.0 ** -12,
    "cosine_min": 1.0 - 2.0 ** -18,
}


def numerical_metrics(oracle: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    o = np.asarray(oracle, dtype=np.float64)
    c = np.asarray(candidate, dtype=np.float64)
    if o.shape != c.shape or not np.isfinite(o).all() or not np.isfinite(c).all():
        raise ValueError("dense-prefix numerical input")
    delta = c - o
    norm = float(np.linalg.norm(o) * np.linalg.norm(c))
    cosine = float(np.dot(o, c) / norm) if norm else 1.0
    return {
        "max_abs_error": float(np.max(np.abs(delta))),
        "rmse": float(np.sqrt(np.mean(delta * delta))),
        "cosine": cosine,
    }


def qualify_numerical(metrics: Mapping[str, float]) -> None:
    if metrics["max_abs_error"] > NUMERICAL_THRESHOLDS["max_abs_error"]:
        raise ValueError("dense-prefix max-absolute numerical failure")
    if metrics["rmse"] > NUMERICAL_THRESHOLDS["rmse"]:
        raise ValueError("dense-prefix RMSE numerical failure")
    if metrics["cosine"] < NUMERICAL_THRESHOLDS["cosine_min"]:
        raise ValueError("dense-prefix cosine numerical failure")


def synthetic_qualification(repeats: int = REPEATS) -> dict[str, Any]:
    if repeats != REPEATS:
        raise ValueError("dense-prefix qualification requires exactly ten repeats")
    oracle_state = run_independent_oracle_dense_prefix()
    runs = [run_synthetic_dense_prefix(dtype=np.float32) for _ in range(repeats)]
    hashes = [run["layer3_entry_sha256"] for run in runs]
    if len(set(hashes)) != 1:
        raise ValueError("dense-prefix repeat nondeterminism")
    metrics = numerical_metrics(oracle_state, runs[0]["layer3_entry"])
    qualify_numerical(metrics)
    return {
        "schema": "pulsarmlx.f017.dense-prefix-synthetic-qualification",
        "schema_version": "1.0.0",
        "checkpoint_access": 0,
        "logical_dimensions": {
            "hidden": HIDDEN, "q_lora": Q_LORA, "q_output": Q_OUT,
            "kv_lora": KV_LORA, "kv_rope": KV_ROPE, "k_output": K_OUT,
            "v_output": V_OUT, "ffn": FFN, "dense_layers": LAYERS,
        },
        "operator_kind": "deterministic_structured_matrix_free_checkpoint_independent",
        "oracle": "independent_binary64_scalar_denominator_and_axis_reduction",
        "candidate": "binary32_numpy",
        "thresholds_frozen_pre_execution": dict(NUMERICAL_THRESHOLDS),
        "metrics": metrics,
        "repeat_count": repeats,
        "repeat_hashes": hashes,
        "deterministic": True,
        "layer3_entry_sha256": hashes[0],
        "real_candidate_execution": False,
    }


@dataclass(frozen=True)
class DispatchEvent:
    repeat: int
    layer: int | None
    stage: str
    backend: str
    native_dispatches: int


PROJECTION_STAGES = (
    "embedding", "attn_q_a", "attn_q_b", "attn_kv_a_mqa", "attn_k_b",
    "attn_v_b", "attn_output", "ffn_gate", "ffn_up", "ffn_down",
)


def expected_dispatch_events(repeats: int = REPEATS) -> tuple[DispatchEvent, ...]:
    if repeats <= 0:
        raise ValueError("repeat count")
    result: list[DispatchEvent] = []
    for repeat in range(repeats):
        result.append(DispatchEvent(repeat, None, "embedding", "SYNTHETIC_NATIVE_EVENT", 1))
        for layer in range(LAYERS):
            for stage in PROJECTION_STAGES[1:]:
                result.append(DispatchEvent(repeat, layer, stage, "SYNTHETIC_NATIVE_EVENT", 1))
            for stage in ("normalization", "range_fill", "softmax", "silu", "residual"):
                result.append(DispatchEvent(repeat, layer, stage, "CPU_SEMANTIC", 0))
    return tuple(result)


def reconcile_dispatch_events(events: Sequence[DispatchEvent], repeats: int = REPEATS) -> dict[str, int]:
    expected = expected_dispatch_events(repeats)
    if tuple(events) != expected:
        raise ValueError("dense-prefix dispatch event surface differs")
    native = sum(event.native_dispatches for event in events)
    per_repeat = native // repeats
    if native % repeats or per_repeat <= 0:
        raise ValueError("dense-prefix native dispatch reconciliation differs")
    return {
        "repeats": repeats,
        "synthetic_observed_native_per_repeat": per_repeat,
        "synthetic_observed_native_total": native,
        "future_real_count_frozen": False,
        "fallback": 0,
        "reference": 0,
        "scaffold": 0,
        "backend_errors": 0,
    }


CONFIG_FIELDS = {
    "schema", "schema_version", "status", "scope", "identity", "prior_evidence",
    "input", "tensor_inventory", "decoder_contracts", "numerical_contract",
    "dispatch_contract", "hidden_retention", "access_budget", "attempt",
    "oracle_package", "evidence_destination",
}


def validate_dense_prefix_config(value: Mapping[str, Any]) -> None:
    if set(value) != CONFIG_FIELDS:
        raise ValueError("dense-prefix config fields differ")
    if value["scope"] != "EMBEDDING_PLUS_DENSE_LAYERS_0_2_TO_LAYER3_ENTRY":
        raise ValueError("dense-prefix scope differs")
    if value["input"] != {"prompt_id": "P-MIN", "token_ids": [9703], "positions": [0], "dsa": "range_fill([0])"}:
        raise ValueError("dense-prefix input differs")
    attempt = value["attempt"]
    if attempt.get("consumed"):
        raise ValueError("dense-prefix attempt already consumed")
    authorized = value["status"] == "AUTHORIZED_NOT_EXECUTED"
    if authorized != bool(attempt.get("authorized")):
        raise ValueError("dense-prefix authorization state differs")
    if authorized:
        if any(value["identity"].get(key) is None for key in ("tooling_sha", "tooling_tree", "authorization_head", "environment_sha256")):
            raise ValueError("dense-prefix execution identity incomplete")
        if value["access_budget"] != {
            "shard_opens": 1,
            "positional_reads": 40,
            "payloads": 40,
            "compressed_bytes": 1_431_263_232,
            "decoded_bytes": 8_504_653_824,
        }:
            raise ValueError("dense-prefix payload budget differs")
        if not value["tensor_inventory"].get("sha256"):
            raise ValueError("dense-prefix tensor inventory unbound")
        if value["attempt"].get("number") is None:
            raise ValueError("dense-prefix attempt identity incomplete")
        for field in ("numerical_contract", "dispatch_contract", "hidden_retention"):
            if not isinstance(value.get(field), str) or len(value[field]) != 64:
                raise ValueError(f"dense-prefix {field} unbound")
        required_decoder_families = {"F32", "Q8_0", "Q5_K", "Q6_K", "Q4_K"}
        if set(value["decoder_contracts"]) != required_decoder_families or any(
            not isinstance(item, str) or len(item) != 64
            for item in value["decoder_contracts"].values()
        ):
            raise ValueError("dense-prefix decoder contracts incomplete")
        oracle = value["oracle_package"]
        if not oracle.get("completed_before_candidate") or oracle.get("rust_or_mlx") or oracle.get("candidate_metrics"):
            raise ValueError("dense-prefix independent oracle package invalid")
        for key in ("package_sha256", "source_surface_sha256", "decoded_tensor_set_sha256"):
            if not isinstance(oracle.get(key), str) or len(oracle[key]) != 64:
                raise ValueError("dense-prefix oracle identity incomplete")
        destination = value["evidence_destination"].get("symbolic_path")
        if not isinstance(destination, str) or not destination.startswith("docs/architecture/reviews/evidence/"):
            raise ValueError("dense-prefix evidence destination incomplete")


def dense_prefix_config_template() -> dict[str, Any]:
    value = {
        "schema": "pulsarmlx.f017.dense-prefix-execution-config",
        "schema_version": "1.0.0",
        "status": "PREPARED_NOT_AUTHORIZED",
        "scope": "EMBEDDING_PLUS_DENSE_LAYERS_0_2_TO_LAYER3_ENTRY",
        "identity": {"tooling_sha": None, "tooling_tree": None, "authorization_head": None, "environment_sha256": None},
        "prior_evidence": {"routing_v3": V3_SHA256},
        "input": {"prompt_id": "P-MIN", "token_ids": [9703], "positions": [0], "dsa": "range_fill([0])"},
        "tensor_inventory": {"sha256": None, "tensor_count": 40},
        "decoder_contracts": {},
        "numerical_contract": None,
        "dispatch_contract": None,
        "hidden_retention": None,
        "access_budget": {"shard_opens": None, "positional_reads": None, "payloads": None, "compressed_bytes": None, "decoded_bytes": None},
        "attempt": {"number": None, "authorized": False, "consumed": False, "consumption_boundary": "EXECUTION_STARTED"},
        "oracle_package": {"package_sha256": None, "source_surface_sha256": None, "decoded_tensor_set_sha256": None, "completed_before_candidate": False, "rust_or_mlx": False, "candidate_metrics": False},
        "evidence_destination": {"symbolic_path": None, "fresh_required": True},
    }
    validate_dense_prefix_config(value)
    return value


def validate_hidden_manifest(value: Mapping[str, Any]) -> None:
    required = {"schema", "schema_version", "status", "source", "hidden", "state", "immutability", "checkpoint_access"}
    if set(value) != required or value.get("checkpoint_access") != 0:
        raise ValueError("hidden-retention manifest fields")
    hidden = value["hidden"]
    if hidden.get("dtype") != "little_endian_f32" or hidden.get("shape") != [HIDDEN] or hidden.get("element_count") != HIDDEN:
        raise ValueError("hidden-retention vector contract")
    if not isinstance(hidden.get("sha256"), str) or len(hidden["sha256"]) != 64:
        raise ValueError("hidden-retention identity")
    if not value["immutability"].get("read_only") or value["immutability"].get("absolute_path_public"):
        raise ValueError("hidden-retention immutability/privacy")


def validate_representative_route_binding(value: Mapping[str, Any]) -> None:
    required = {
        "schema", "schema_version", "status", "dense_prefix_evidence_sha256",
        "layer3_entry_sha256", "m1f0_route_artifact_sha256", "routing_v3_sha256",
        "membership_h2_pass", "atomic_pairs_sha256", "analytical_retention_complete",
        "m1_f_authorized",
    }
    if set(value) != required:
        raise ValueError("representative route-binding fields")
    if value["routing_v3_sha256"] != V3_SHA256:
        raise ValueError("representative route-binding v3 identity")
    if value["status"] == "ACCEPTED_REPRESENTATIVE_ROUTE":
        for field in ("dense_prefix_evidence_sha256", "layer3_entry_sha256", "m1f0_route_artifact_sha256", "atomic_pairs_sha256"):
            if not isinstance(value[field], str) or len(value[field]) != 64:
                raise ValueError("representative route identity incomplete")
        if not value["membership_h2_pass"] or not value["analytical_retention_complete"]:
            raise ValueError("representative route semantic gate failed")
    if value["m1_f_authorized"]:
        raise ValueError("representative route handoff cannot authorize M1-F")


def representative_route_handoff() -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.m1f0-representative-route-handoff",
        "schema_version": "1.0.0",
        "status": "PREPARED_NOT_AUTHORIZED",
        "source_boundary": "accepted dense-prefix layer-3 entry hidden state",
        "m1f0_scope": "accepted 12-payload attention/router-only route discovery",
        "routing_contract": V3_SHA256,
        "qualification": {
            "exact_membership": True,
            "membership_h2_required": True,
            "id_keyed_weight_qualification_required": True,
            "rank_order_diagnostic_only": True,
            "full_analytical_retention_required": True,
        },
        "input_binding": {
            "prompt_id": "P-MIN",
            "token_ids": [9703],
            "positions": [0],
            "dsa": "range_fill([0])",
            "accepted_hidden_retention_manifest_required": True,
            "alternate_prompt_or_hidden_substitution": "FAIL_CLOSED",
        },
        "phase_separation": {
            "dense_prefix_and_route_share_authorization": False,
            "route_and_m1_f_share_authorization": False,
            "m1_f_authorized": False,
        },
        "ledger_before_future_access": LEDGER,
        "checkpoint_access": 0,
    }
