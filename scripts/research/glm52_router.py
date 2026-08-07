#!/usr/bin/env python3
"""Real GLM-5.2 router (Pulsar mode-0 sigmoid + bias + renorm + scale).

Source: giannisanni/pulsar router_select_kernel softmax_mode==0 and
Family::Mla MoE path (shexp is always-on outside the router).

GGUF:
  expert_used_count=8, expert_shared_count=1 (2D shexp, not router sink)
  expert_weights_scale=2.5
  expert_gating_func=2 (sigmoid)
  exp_probs_b.bias[n_expert] added to sigmoid score for top-k
"""

from __future__ import annotations

import math
from typing import Any


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def glm_route_real(
    logits: list[float],
    bias: list[float] | None,
    *,
    k: int = 8,
    weight_scale: float = 2.5,
    n_shared_outside: int = 1,
) -> dict[str, Any]:
    """Select top-k among n_expert logits; shared expert is outside router.

    score[e] = sigmoid(logits[e]) + bias[e]
    select top-k by score (tie → lower index)
    weight[e] = sigmoid(logits[e]) / sum_selected * weight_scale
    """
    n = len(logits)
    if bias is not None and len(bias) != n:
        raise ValueError("bias length")
    if k <= 0 or k > n:
        raise ValueError("k")
    probs = [sigmoid(float(v)) for v in logits]
    scores = [probs[i] + (float(bias[i]) if bias is not None else 0.0) for i in range(n)]
    order = sorted(range(n), key=lambda i: (-scores[i], i))
    ids = order[:k]
    raw_w = [probs[i] for i in ids]
    s = sum(raw_w)
    if s < 6.103515625e-5:
        s = 6.103515625e-5
    weights = [w / s * weight_scale for w in raw_w]
    return {
        "expert_ids": ids,
        "weights": weights,
        "probs": probs,
        "scores": scores,
        "weight_scale": weight_scale,
        "n_shared_outside": n_shared_outside,
        "contract": "glm_mode0_sigmoid_bias_renorm_scale_shexp_outside",
    }
