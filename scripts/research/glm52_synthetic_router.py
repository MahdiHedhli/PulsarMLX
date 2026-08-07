#!/usr/bin/env python3
"""Synthetic GLM-style sigmoid router + shared-expert sink (checkpoint-free)."""

from __future__ import annotations

import math
from typing import Any


def sigmoid(x: float) -> float:
    # stable
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def router_scores(logits: list[float]) -> list[float]:
    return [sigmoid(float(v)) for v in logits]


def topk_ids(scores: list[float], k: int) -> list[int]:
    if k < 0:
        raise ValueError("k")
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    return order[:k]


def glm_route(
    logits: list[float],
    k: int,
    n_shared: int = 1,
    *,
    shared_as_sink: bool = True,
) -> dict[str, Any]:
    """Sigmoid scores, top-k among routed experts [0, n_routed).

    If shared_as_sink, append shared expert ids at end of selection as
    always-on sinks with weight 1.0 each (simplified synthetic contract).
    Real GLM weighting must be re-validated on checkpoint (C03).
    """
    n = len(logits)
    if n_shared < 0 or n_shared > n:
        raise ValueError("n_shared")
    n_routed = n - n_shared if shared_as_sink else n
    if n_routed <= 0:
        raise ValueError("no routed experts")
    if k > n_routed:
        raise ValueError("k exceeds routed experts")
    scores = router_scores(logits[:n_routed])
    ids = topk_ids(scores, k)
    weights = [scores[i] for i in ids]
    s = sum(weights)
    if s <= 0:
        raise ValueError("non-positive weight sum")
    weights = [w / s for w in weights]
    if shared_as_sink and n_shared:
        # synthetic: shared ids = n_routed .. n-1
        for s_id in range(n_routed, n_routed + n_shared):
            ids.append(s_id)
            weights.append(1.0)
    return {
        "expert_ids": ids,
        "weights": weights,
        "scores_routed": scores,
        "n_routed": n_routed,
        "n_shared": n_shared,
        "contract": "synthetic_sigmoid_topk_plus_shared_sink",
    }


def synthetic_moe_forward(
    x: list[float],
    expert_outs: dict[int, list[float]],
    route: dict[str, Any],
) -> list[float]:
    """Weighted sum of expert outputs (already computed)."""
    n = len(x)
    acc = [0.0] * n
    for eid, w in zip(route["expert_ids"], route["weights"], strict=True):
        if eid not in expert_outs:
            raise KeyError(f"missing expert {eid}")
        e = expert_outs[eid]
        if len(e) != n:
            raise ValueError("expert width")
        for i in range(n):
            acc[i] += w * e[i]
    return acc
