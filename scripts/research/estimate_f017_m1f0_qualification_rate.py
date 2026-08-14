#!/usr/bin/env python3
"""Checkpoint-free planning estimator for the frozen M1-F0 fixture ladder."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

CONTRACT = "specs/017-rust-native-inference-runtime/contracts/f017-m1f0-fixture-qualification-estimator-v1.json"
RECOVERY = "docs/architecture/reviews/evidence/f017-m1-f0-router-analytical-recovery-v1.json"


def load_contract(root: Path) -> dict[str, object]:
    return json.loads((root / CONTRACT).read_text())


def _vectors(root: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    doc = json.loads((root / RECOVERY).read_text())
    canonical = doc.get("canonical_analytics", {})
    values = canonical.get("values", canonical)
    # Recovery schema names are deliberately discovered with fail-closed aliases.
    probabilities = (values.get("pre_bias_probabilities") or values.get("pre_bias_probability_vector")
                     or values.get("probabilities"))
    biases = values.get("router_bias") or values.get("router_bias_vector") or values.get("bias")
    bounds = (values.get("post_bias_score_error_bounds") or values.get("score_error_bounds")
              or values.get("score_bounds"))
    if probabilities is None or biases is None:
        analytics = doc.get("analytics", {})
        probabilities = probabilities or analytics.get("pre_bias_probabilities")
        biases = biases or analytics.get("router_bias")
        bounds = bounds or analytics.get("score_error_bounds")
    if probabilities is None or biases is None:
        raise ValueError("banked recovery lacks estimator vectors")
    p = np.asarray(probabilities, dtype=np.float64)
    b = np.asarray(biases, dtype=np.float64)
    if bounds is None:
        # The accepted rank bounds are the only banked componentwise exemplars;
        # use the larger for every expert, conservatively.
        bound = max(0.0033056307117125656, 0.0033937161438668565)
        q = np.full(256, bound, dtype=np.float64)
    else:
        q = np.asarray(bounds, dtype=np.float64)
    if p.shape != (256,) or b.shape != (256,) or q.shape != (256,):
        raise ValueError("estimator vectors must contain 256 elements")
    return p, b, q


def simulate(root: Path, sample_count: int | None = None, seed: int | None = None) -> dict[str, object]:
    contract = load_contract(root)
    n = int(sample_count or contract["official_sample_count"])
    rng = np.random.Generator(np.random.PCG64(seed or int(contract["official_seed"])))
    p, bias, bounds = _vectors(root)
    qualified = 0
    s_values = np.empty(n, dtype=np.float64)
    chunk = 4096
    for start in range(0, n, chunk):
        size = min(chunk, n - start)
        sampled = p[rng.integers(0, 256, size=(size, 256))]
        scores = sampled + bias
        order = np.argsort(-scores, axis=1, kind="stable")
        row = np.arange(size)
        eighth, ninth = order[:, 7], order[:, 8]
        margin = scores[row, eighth] - scores[row, ninth]
        denominator = bounds[eighth] + bounds[ninth]
        s = margin / denominator
        s_values[start:start + size] = s
        qualified += int(np.count_nonzero(s >= float(contract["minimum_safety_factor"])))
    rate = qualified / n
    z = 1.959963984540054
    denominator = 1 + z * z / n
    center = (rate + z * z / (2 * n)) / denominator
    half = z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / denominator
    low, high = max(0.0, center - half), min(1.0, center + half)
    if qualified == 0:
        low = 0.0
    p_any = 1 - (1 - rate) ** 8
    p_any_low = 1 - (1 - low) ** 8
    return {
        "schema": "pulsarmlx.f017.m1f0-fixture-qualification-estimate", "sample_count": n,
        "seed": seed or int(contract["official_seed"]), "qualifying_samples": qualified,
        "predicted_qualification_rate": rate, "wilson_95": [low, high],
        "s_quantiles": {str(q): float(np.quantile(s_values, q)) for q in (0.01, 0.1, 0.5, 0.9, 0.99)},
        "maximum_observed_s": float(np.max(s_values)),
        "ladder_size": 8, "p_zero_independent": (1 - rate) ** 8,
        "p_at_least_one_independent": p_any, "p_at_least_one_using_wilson_lower": p_any_low,
        "p_at_least_one_using_wilson_upper": 1 - (1 - high) ** 8,
        "planning_threshold": float(contract["planning_threshold_probability_at_least_one"]),
        "adequate": p_any_low >= float(contract["planning_threshold_probability_at_least_one"]),
        "checkpoint_access": 0, "planning_only": True,
    }
