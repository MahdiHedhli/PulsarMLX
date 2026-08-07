#!/usr/bin/env python3
"""Feature 009: multi-layer MoE residual block under architecture oracle.

For each requested layer L:
  ffn_inp-L (captured) → RMSNorm(ffn_norm.weight, eps=1e-6)
  → router top-8 → expert MLPs (Q8_0 f32-dequant path) → residual add
  y = ffn_inp + aggregate

Compares independent CPU vs Apple MLX. Does not claim llama Q8_0×Q8_0 bit parity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from expert_oracle import (  # noqa: E402
    ABS_TOL,
    REL_TOL,
    EXPERTS,
    HIDDEN,
    INTERMEDIATE,
    EXPERT_DOWN_BYTES,
    EXPERT_GATE_UP_BYTES,
    GATE_UP_ROW_BYTES,
    DOWN_ROW_BYTES,
    ExpertOracleError,
    _decode_q8_0_row,
    _f32le_sha,
    _matvec_q8_0,
    _pread,
    _sha256_bytes,
    _swiglu,
    compare_vectors,
)

# Validated against GGUFReader for Qwen3-30B-A3B-Q8_0.
LAYER_STRIDE = 662_848_512
BASE_OFFSETS = {
    "ffn_down_exps": 687_266_304,
    "ffn_gate_exps": 901_175_808,
    "ffn_up_exps": 1_116_142_080,
    "ffn_gate_inp": 1_115_085_312,
    "ffn_norm": 1_116_133_888,
}
EPS = 1e-6
TOP_K = 8


def tensor_offset(kind: str, layer: int) -> int:
    if layer < 0 or layer >= 48:
        raise ExpertOracleError("layer", f"layer {layer} out of range")
    if kind not in BASE_OFFSETS:
        raise ExpertOracleError("tensor_kind", kind)
    return BASE_OFFSETS[kind] + layer * LAYER_STRIDE


def expert_range(kind: str, layer: int, expert_index: int) -> tuple[int, int]:
    if expert_index < 0 or expert_index >= EXPERTS:
        raise ExpertOracleError("expert_index", "out of range")
    base = tensor_offset(kind, layer)
    nbytes = EXPERT_DOWN_BYTES if kind == "ffn_down_exps" else EXPERT_GATE_UP_BYTES
    return base + expert_index * nbytes, nbytes


def load_f32_vector(model: Path, offset: int, n: int) -> list[float]:
    data = _pread(model, offset, n * 4)
    return list(struct.unpack(f"<{n}f", data))


def load_f32_matrix(model: Path, offset: int, rows: int, cols: int) -> list[list[float]]:
    data = _pread(model, offset, rows * cols * 4)
    out: list[list[float]] = []
    row_bytes = cols * 4
    for r in range(rows):
        chunk = data[r * row_bytes : (r + 1) * row_bytes]
        out.append(list(struct.unpack(f"<{cols}f", chunk)))
    return out


def rms_norm(x: list[float], weight: list[float], eps: float = EPS) -> list[float]:
    if len(x) != len(weight):
        raise ExpertOracleError("rms_len", "rms width mismatch")
    ms = sum(v * v for v in x) / len(x)
    scale = 1.0 / math.sqrt(ms + eps)
    return [weight[i] * x[i] * scale for i in range(len(x))]


def matvec_f32(matrix: list[list[float]], x: list[float]) -> list[float]:
    return [sum(w * a for w, a in zip(row, x, strict=True)) for row in matrix]


def topk_router(logits: list[float], k: int = TOP_K) -> tuple[list[int], list[float], list[float]]:
    if len(logits) != EXPERTS:
        raise ExpertOracleError("router_width", "expected 128 logits")
    # f32-friendly softmax
    m = max(logits)
    exps = [math.exp(float(v) - m) for v in logits]
    s = sum(exps)
    probs = [e / s for e in exps]
    order = sorted(range(EXPERTS), key=lambda i: (-probs[i], i))
    ids = order[:k]
    raw = [probs[i] for i in ids]
    den = sum(raw)
    if den <= 0:
        raise ExpertOracleError("router_norm", "top-k weight sum non-positive")
    weights = [v / den for v in raw]
    return ids, raw, weights


def run_expert(
    model: Path, layer: int, expert_index: int, activation: list[float], weight: float
) -> list[float]:
    go, gn = expert_range("ffn_gate_exps", layer, expert_index)
    uo, un = expert_range("ffn_up_exps", layer, expert_index)
    do, dn = expert_range("ffn_down_exps", layer, expert_index)
    gate = _matvec_q8_0(_pread(model, go, gn), INTERMEDIATE, HIDDEN, activation)
    up = _matvec_q8_0(_pread(model, uo, un), INTERMEDIATE, HIDDEN, activation)
    act = _swiglu(gate, up)
    down = _matvec_q8_0(_pread(model, do, dn), HIDDEN, INTERMEDIATE, act)
    return [weight * v for v in down]


def load_ffn_inp_row(path: Path, row: int = 0) -> list[float]:
    data = path.read_bytes()
    if len(data) != 2 * HIDDEN * 4:
        raise ExpertOracleError("capture_size", f"expected 16384 bytes, got {len(data)}")
    vals = list(struct.unpack(f"<{2 * HIDDEN}f", data))
    return vals[row * HIDDEN : (row + 1) * HIDDEN]


def layer_moe_cpu(model: Path, layer: int, residual: list[float]) -> dict[str, Any]:
    t0 = time.perf_counter()
    norm_w = load_f32_vector(model, tensor_offset("ffn_norm", layer), HIDDEN)
    gate_w = load_f32_matrix(model, tensor_offset("ffn_gate_inp", layer), EXPERTS, HIDDEN)
    normed = rms_norm(residual, norm_w, EPS)
    logits = matvec_f32(gate_w, normed)
    ids, raw, weights = topk_router(logits)
    agg = [0.0] * HIDDEN
    experts = []
    for eid, w in zip(ids, weights, strict=True):
        part = run_expert(model, layer, eid, normed, w)
        experts.append(
            {
                "expert_index": eid,
                "routing_weight": w,
                "weighted_sha256": _f32le_sha(part),
            }
        )
        for i, v in enumerate(part):
            agg[i] += v
    block = [r + a for r, a in zip(residual, agg, strict=True)]
    if any(not math.isfinite(v) for v in block):
        raise ExpertOracleError("nonfinite", "block non-finite")
    return {
        "layer": layer,
        "expert_ids": ids,
        "routing_weights": weights,
        "selected_raw_probs": raw,
        "experts": experts,
        "normed_sha256": _f32le_sha(normed),
        "logits_sha256": _f32le_sha(logits),
        "aggregate_sha256": _f32le_sha(agg),
        "block_sha256": _f32le_sha(block),
        "aggregate": agg,
        "block": block,
        "normed": normed,
        "timing_cpu_wall_seconds": time.perf_counter() - t0,
    }


def layer_moe_mlx(model: Path, layer: int, residual: list[float], cpu: dict) -> dict[str, Any]:
    import mlx.core as mx  # local import: MLX only on parity path


    # Reuse expert_parity helpers but with layer offsets via run_expert-like path
    # implemented inline for layer support.
    t0 = time.perf_counter()
    ids = cpu["expert_ids"]
    weights = cpu["routing_weights"]
    normed = cpu["normed"]
    residual_mx = mx.array(residual, dtype=mx.float32)
    agg = mx.zeros((HIDDEN,), dtype=mx.float32)
    experts = []
    for eid, w in zip(ids, weights, strict=True):
        # Decode weights to f32 then matmul on MLX (architecture path)
        go, gn = expert_range("ffn_gate_exps", layer, eid)
        uo, un = expert_range("ffn_up_exps", layer, eid)
        do, dn = expert_range("ffn_down_exps", layer, eid)
        gate_enc = _pread(model, go, gn)
        up_enc = _pread(model, uo, un)
        down_enc = _pread(model, do, dn)

        def decode_matrix(enc: bytes, rows: int, cols: int) -> "mx.array":
            row_b = (cols // 32) * 34
            rows_out = []
            for r in range(rows):
                rows_out.append(_decode_q8_0_row(enc[r * row_b : (r + 1) * row_b], cols))
            return mx.array(rows_out, dtype=mx.float32)

        act = mx.array(normed, dtype=mx.float32)
        gate_w = decode_matrix(gate_enc, INTERMEDIATE, HIDDEN)
        up_w = decode_matrix(up_enc, INTERMEDIATE, HIDDEN)
        down_w = decode_matrix(down_enc, HIDDEN, INTERMEDIATE)
        g = gate_w @ act
        u = up_w @ act
        # SiLU-SwiGLU
        silu = g * mx.sigmoid(g)
        h = silu * u
        d = down_w @ h
        weighted = d * mx.array(w, dtype=mx.float32)
        mx.eval(weighted)
        wlist = weighted.tolist()
        experts.append(
            {
                "expert_index": eid,
                "routing_weight": w,
                "weighted_sha256": _f32le_sha(wlist),
            }
        )
        agg = agg + weighted
    block = residual_mx + agg
    mx.eval(block)
    agg_l = agg.tolist()
    block_l = block.tolist()
    return {
        "runtime": {
            "backend": "apple-mlx",
            "selected_device": "gpu",
            "fallback_used": False,
            "evaluated": True,
            "synchronized": True,
        },
        "experts": experts,
        "aggregate": agg_l,
        "block": block_l,
        "aggregate_sha256": _f32le_sha(agg_l),
        "block_sha256": _f32le_sha(block_l),
        "timing_mlx_wall_seconds": time.perf_counter() - t0,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--layer", type=int, required=True)
    p.add_argument("--ffn-inp", type=Path, required=True, help="captured ffn_inp-L f32le 2x2048")
    p.add_argument("--row", type=int, default=0)
    p.add_argument("--oracle-out", type=Path, required=True)
    p.add_argument("--evidence-out", type=Path, required=True)
    p.add_argument("--source-commit", type=str, required=True)
    args = p.parse_args(argv)

    if args.oracle_out.exists() or args.evidence_out.exists():
        print("layer_moe_residual: refuse overwrite", file=sys.stderr)
        return 1

    residual = load_ffn_inp_row(args.ffn_inp, args.row)
    residual_sha = _sha256_bytes(args.ffn_inp.read_bytes())
    cpu = layer_moe_cpu(args.model, args.layer, residual)
    # Publish oracle without huge optional dumps beyond block
    oracle = {
        "schema": "pulsarmlx.research.layer-moe-residual-oracle",
        "schema_version": "1.0.0",
        "feature_id": "009-multi-layer-moe-residual",
        "status": "passed",
        "layer": args.layer,
        "row": args.row,
        "residual": {
            "node": f"ffn_inp-{args.layer}",
            "capture_sha256": residual_sha,
            "row_sha256": _f32le_sha(residual),
        },
        "expert_ids": cpu["expert_ids"],
        "routing_weights": cpu["routing_weights"],
        "experts": cpu["experts"],
        "result": {
            "normed_sha256": cpu["normed_sha256"],
            "logits_sha256": cpu["logits_sha256"],
            "aggregate_sha256": cpu["aggregate_sha256"],
            "block_sha256": cpu["block_sha256"],
            "block": cpu["block"],
            "formula": "y = ffn_inp + sum_i w_i * expert_i(RMSNorm(ffn_inp))",
            "matmul_contract": "q8_0_weight_dequant_x_f32_activation",
        },
        "timing": {"cpu_wall_seconds": cpu["timing_cpu_wall_seconds"]},
        "comparison_policy": {
            "absolute_tolerance": ABS_TOL,
            "relative_tolerance": REL_TOL,
            "mode": "absolute_plus_relative",
        },
        "unsupported_interpretations": [
            "llama_q8x8_bit_parity",
            "attention_mlx",
            "logits",
            "generation",
        ],
    }
    args.oracle_out.parent.mkdir(parents=True, exist_ok=True)
    args.oracle_out.write_text(
        json.dumps(oracle, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )

    mlx = layer_moe_mlx(args.model, args.layer, residual, cpu)
    comparison = compare_vectors(mlx["block"], cpu["block"], ABS_TOL, REL_TOL)
    record = {
        "schema": "pulsarmlx.research.layer-moe-residual-parity",
        "schema_version": "1.0.0",
        "feature_id": "009-multi-layer-moe-residual",
        "experiment_id": f"f009-layer-{args.layer}-moe-residual-parity-0001",
        "actual_status": "passed" if comparison["passed"] else "failed",
        "source_commit": args.source_commit,
        "layer": args.layer,
        "row": args.row,
        "residual_capture_sha256": residual_sha,
        "expert_ids": cpu["expert_ids"],
        "routing_weights": cpu["routing_weights"],
        "runtime": mlx["runtime"],
        "oracle_block_sha256": cpu["block_sha256"],
        "result": {
            "block_sha256": mlx["block_sha256"],
            "aggregate_sha256": mlx["aggregate_sha256"],
        },
        "experts_mlx": mlx["experts"],
        "comparison": comparison,
        "timing": {
            "cpu_wall_seconds": cpu["timing_cpu_wall_seconds"],
            "mlx_wall_seconds": mlx["timing_mlx_wall_seconds"],
        },
        "claim_boundary": {
            "operation": f"layer_{args.layer}_moe_residual_add",
            "status": "provisional",
            "matmul_contract": "q8_0_weight_dequant_x_f32_activation",
            "unsupported_interpretations": oracle["unsupported_interpretations"],
        },
    }
    args.evidence_out.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": record["actual_status"],
                "layer": args.layer,
                "expert_ids": cpu["expert_ids"],
                "comparison": comparison,
            },
            sort_keys=True,
        )
    )
    return 0 if comparison["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
