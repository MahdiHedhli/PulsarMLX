#!/usr/bin/env python3
"""Planning-only v2 estimator; fail closed to v1 bounds without pair antecedents."""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import numpy as np

V2_CONTRACT_SHA256 = "fd300f061307442c56af9ca3183f7485544ecb11752755074a330bb7b5f5f68c"
LADDER_SHA256 = "59c55a26d12ff9e0fdbe488608c4cb7ffb1a2082d322dec85ee5ef37719c3ed2"
GENERATOR_SHA256 = "0097e78a55cf5d8911a2715cebf7e024606a69713d08d7f3bc07ac04864d60f0"
OFFICIAL_SEED = 170_185_002


def _load(root: Path):
    path = root / "scripts/research/estimate_f017_m1f0_qualification_rate.py"
    spec = importlib.util.spec_from_file_location("f017_v1_estimator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wilson(successes: int, count: int) -> list[float]:
    rate = successes / count
    z = 1.959963984540054
    denominator = 1.0 + z * z / count
    center = (rate + z * z / (2.0 * count)) / denominator
    half = z * math.sqrt(rate * (1.0 - rate) / count + z * z / (4.0 * count * count)) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def simulate(root: Path, sample_count: int = 1_000_000, seed: int = OFFICIAL_SEED) -> dict[str, object]:
    v1 = _load(root)
    probabilities, bias, bounds = v1._vectors(root)
    rng = np.random.Generator(np.random.PCG64(seed))
    s_values = np.empty(sample_count, dtype=np.float64)
    mathematical = 0
    engineering = 0
    chunk = 4096
    for start in range(0, sample_count, chunk):
        size = min(chunk, sample_count - start)
        sampled = probabilities[rng.integers(0, 256, size=(size, 256))]
        scores = sampled + bias
        order = np.argsort(-scores, axis=1, kind="stable")
        row = np.arange(size)
        eighth, ninth = order[:, 7], order[:, 8]
        margin = scores[row, eighth] - scores[row, ninth]
        # The recovery retained final independent row bounds but omitted the
        # RMS decomposition and router rows required by v2. The candidate
        # contract therefore mandates its conservative v1 fallback.
        pair_bound = bounds[eighth] + bounds[ninth]
        safety = margin / pair_bound
        s_values[start:start + size] = safety
        mathematical += int(np.count_nonzero(safety > 1.0))
        engineering += int(np.count_nonzero(safety >= 2.0))
    math_ci = wilson(mathematical, sample_count)
    engineering_ci = wilson(engineering, sample_count)
    return {
        "schema": "pulsarmlx.f017.m1f0-fixture-qualification-estimate-v2-candidate",
        "planning_only": True,
        "checkpoint_access": 0,
        "v2_contract_sha256": V2_CONTRACT_SHA256,
        "ladder_sha256": LADDER_SHA256,
        "generator_sha256": GENERATOR_SHA256,
        "seed": seed,
        "sample_count": sample_count,
        "methodology": "PAIRWISE_ANTECEDENTS_UNAVAILABLE_FALLBACK_V1",
        "missing_antecedents": [
            "router rows or exact row-pair summaries",
            "RMSNorm lambda bound",
            "RMSNorm non-radial residual component bounds",
            "independent router reduction/import terms"
        ],
        "mathematical": {
            "threshold": "S_pair>1",
            "qualifiers": mathematical,
            "rate": mathematical / sample_count,
            "wilson_95": math_ci,
            "p_any_8": 1.0 - (1.0 - mathematical / sample_count) ** 8,
        },
        "engineering": {
            "threshold": "S_pair>=2",
            "qualifiers": engineering,
            "rate": engineering / sample_count,
            "wilson_95": engineering_ci,
            "p_any_8": 1.0 - (1.0 - engineering / sample_count) ** 8,
        },
        "s_pair_quantiles": {str(q): float(np.quantile(s_values, q)) for q in (0.01, 0.1, 0.5, 0.9, 0.99)},
        "maximum_s_pair": float(np.max(s_values)),
        "family_disposition": "REQUIRES_REVIEW",
        "real_ladder_execution_authorized": False,
    }


if __name__ == "__main__":
    print(json.dumps(simulate(Path(__file__).resolve().parents[2]), sort_keys=True, separators=(",", ":")))
