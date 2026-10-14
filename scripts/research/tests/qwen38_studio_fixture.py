"""Reproduce the analytic fixture with Decimal derivations, not candidate code.

Prints JSON only; no model source, upstream arrays or checkpoint data is used.
"""
from decimal import Decimal, localcontext
import hashlib
import json


def fixture():
    with localcontext() as context:
        context.prec = 60
        denominator = (Decimal("12.5") + Decimal("0.000001")).sqrt()
        norm = [float(Decimal("3.75") / denominator), float(Decimal("3") / denominator)]
        gated = [float(Decimal("0.75") / denominator), float(Decimal("-1") / denominator)]
        boundary = [float(Decimal(-11) / 3), -2.75, -2.0, float(Decimal(-17) / 7)]
    tokens = [(17 * i + 3) % 127 for i in range(2080)]
    raw = json.dumps(tokens, separators=(",", ":")).encode("ascii")
    keys = [0, 2046, 2047, 2048, 2049, 2078, 2079]
    return {
        "schema": "pulsarmlx.qwen38.analytic-probes/1",
        "provenance": "Original project analytic inputs; Decimal 60-digit norm and rational boundary goldens. Not upstream model goldens.",
        "seed": 1234,
        "stop_ids": [248046, 248044],
        "analytic_tolerance": {"atol": 1e-12, "rtol": 1e-12},
        "norm": {"x": [3, 4], "raw_hf": [.25, -.25], "converted": [1.25, .75],
                 "epsilon": 1e-6, "expected": norm},
        "gated_norm": {"x": [3, 4], "weights": [.25, -.25], "epsilon": 1e-6, "expected": gated},
        "l2": [{"x": [3, 4], "expected": [.6, .8]},
               {"x": [1, -2, 2], "expected": [1/3, -2/3, 2/3]},
               {"x": [0, 0], "expected": [0, 0]},
               {"x": [1e-14, 0], "expected": [.01, 0]}],
        "resets": [{"tokens": [7, 8, 248046, 9, 10, 248044, 11],
                    "expected": [[7], [7, 8], [], [9], [9, 10], [], [11]]},
                   {"tokens": [248044, 248046, 12, 13, 14],
                    "expected": [[], [], [12], [12, 13], [13, 14]]}],
        "boundary": [dict(query=q, candidates=keys, expected_keys=visible,
                          expected_uniform_attention=golden)
                     for q, visible, golden in zip(
                         (2047, 2048, 2049, 2079),
                         (keys[:3], keys[:4], keys[:5], keys), boundary)],
        "generated_boundary_tokens": {"length": 2080, "encoding": "compact-json-ascii",
                                      "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
    }


if __name__ == "__main__":
    print(json.dumps(fixture(), indent=2, allow_nan=False))
