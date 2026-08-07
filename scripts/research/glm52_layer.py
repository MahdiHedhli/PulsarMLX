#!/usr/bin/env python3
"""Full GLM-5.2 layer forward (MLA + dense/MoE FFN) for C08–C11 ladder."""

from __future__ import annotations

import math
from typing import Any

from glm52_dense_primitives import load_f32_vector, matvec_weight, rms_norm
from glm52_expert import run_expert_swiglu
from glm52_mla import (
    CompactKVCache,
    N_LEADING_DENSE,
    RMS_EPS,
    dense_ffn,
    mla_forward_token,
)
from glm52_router import glm_route_real
from glm52_tensor_store import Glm52TensorStore

EXPERT_WEIGHT_SCALE = 2.5
N_EXPERT = 256
N_EXPERT_USED = 8


def moe_ffn(
    store: Glm52TensorStore,
    layer: int,
    residual: list[float],
) -> tuple[list[float], dict[str, Any]]:
    """Shared expert (always-on, weight 1) + top-8 routed experts."""
    x = rms_norm(residual, load_f32_vector(store, f"blk.{layer}.ffn_norm.weight"), RMS_EPS)
    logits = matvec_weight(store, f"blk.{layer}.ffn_gate_inp.weight", x)
    bias = load_f32_vector(store, f"blk.{layer}.exp_probs_b.bias")
    route = glm_route_real(logits, bias, k=N_EXPERT_USED, weight_scale=EXPERT_WEIGHT_SCALE)
    acc = [0.0] * len(residual)
    for eid, w in zip(route["expert_ids"], route["weights"], strict=True):
        part = run_expert_swiglu(store, layer, eid, x, w, shared=False)
        for i, v in enumerate(part):
            acc[i] += v
    # shared always-on (outside router) weight 1.0
    she = run_expert_swiglu(store, layer, 0, x, 1.0, shared=True)
    for i, v in enumerate(she):
        acc[i] += v
    out = [a + b for a, b in zip(residual, acc, strict=True)]
    return out, {"route": route, "shared_weight": 1.0}


def layer_forward_token(
    store: Glm52TensorStore,
    layer: int,
    residual: list[float],
    cache: CompactKVCache,
    pos: int = 0,
) -> tuple[list[float], dict[str, Any]]:
    mid, adiag = mla_forward_token(store, layer, residual, cache, pos)
    if layer < N_LEADING_DENSE:
        out = dense_ffn(store, layer, mid)
        fdiag: dict[str, Any] = {"ffn": "dense_swiglu"}
    else:
        out, fdiag = moe_ffn(store, layer, mid)
        fdiag["ffn"] = "moe_top8_plus_shexp"
    diag = {**adiag, **fdiag}
    diag["out_l2"] = math.sqrt(sum(v * v for v in out))
    diag["finite"] = all(math.isfinite(v) for v in out)
    return out, diag
