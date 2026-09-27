"""Declare F020 Sequence 002 synthetic cases without running either candidate.

This generator is intentionally limited to deterministic case identities and
guard metadata. It never imports MLX, Metal, checkpoint data, or candidate code.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "fixtures/f020-fused-swiglu/fixture-declarations-v1.json"


def declaration() -> dict:
    positives = [
        f"positive-d{d}-h{h}-m{m}-e{e}-{profile}"
        for d in (64, 128)
        for h in (64, 128)
        for m in (1, 32)
        for e in (0, 1, 2)
        for profile in ("all-4bit-default", "gate-down-8bit-up-4bit")
    ]
    refusals = [
        "initial-x-out-of-range",
        "metadata-out-of-range",
        "gate-below-activation-floor",
        "up-above-activation-cap",
        "normal-product-below-2^-32",
        "cross-expert-tuple-mismatch",
    ]
    mutations = [
        "activation-argument-swap",
        "gate-up-projection-swap",
        "down-expert-swap",
        "illicit-lower-gate-clamp",
        "missing-upper-gate-clamp",
        "missing-lower-up-clamp",
        "missing-upper-up-clamp",
        "ignored-quantization-override",
        "skipped-down-admission",
        "end-to-end-reference-replaced-by-actual-h3",
    ]
    assert len(positives) == 48
    assert len(refusals) == 6
    assert len(mutations) == 10
    return {
        "schema": "pulsarmlx.f020.fused-swiglu-fixtures/1.0.0",
        "status": "FROZEN_DECLARATION_NO_BYTES_GENERATED",
        "gate_domain": [-16, 16],
        "gate_clamp": "upper-only min(gate, 10); no lower clamp",
        "up_domain": [-16, 16],
        "up_clamp": "clip(up, -10, 10)",
        "candidate_n_graph": [
            "g=min(gate,10)",
            "s=native MLX sigmoid(g)",
            "silu=native MLX multiply(g,s)",
            "h=native MLX multiply(silu,clip(up,-10,10))",
        ],
        "candidate_n_runtime_fail_closed": True,
        "candidate_b_table_grid": "x_num/32, x_num=-512..320",
        "case_ids": positives + refusals + mutations,
        "positive_cases": len(positives),
        "refusal_cases": len(refusals),
        "mutation_controls": len(mutations),
        "total_case_ids": 64,
        "candidate_observations": 0,
    }


if __name__ == "__main__":
    value = declaration()
    OUT.write_text(json.dumps(value, indent=2) + chr(10), encoding="utf-8")
    print(json.dumps({"path": str(OUT), "case_count": value["total_case_ids"]}))
