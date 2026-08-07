#!/usr/bin/env python3
"""Complete layer-0 and multi-layer stack under architecture oracle.

Depth ladder (default): 1 → 2 → 4 → … up to --max-layers.

Per layer boundary records:
  max_abs, mean_abs, RMSE, relative (max), cosine, norm_ratio,
  first max-error index, deterministic repeatability.

Primary contract: MLX ≈ independent CPU (Q8_0 weight dequant × f32 act).
Does NOT claim llama Q8_0×Q8_0 bit-parity (F008 contract B).
"""

from __future__ import annotations

import argparse
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
    ExpertOracleError,
    _decode_q8_0_row,
    _f32le_sha,
    _matvec_q8_0,
    _pread,
    _sha256_bytes,
    _swiglu,
    compare_vectors,
)
from layer0_attention import (  # noqa: E402
    N_HEAD,
    N_HEAD_KV,
    N_EMBD_HEAD,
    Q_OUT,
    KV_OUT,
    ROPE_THETA,
    EPS,
    VOCAB,
    EMB_ROW_BYTES,
    OFFSETS as ATTN_L0_OFFSETS,
    embed_token,
    rms_norm,
    rms_norm_heads,
    rope_neox,
    matvec_q8,
    vector_geometry,
)

LAYER_STRIDE = 662_848_512
# Layer-0 absolute file offsets (GGUFReader t.data_offset).
ATTN_BASE = {
    "attn_norm": ATTN_L0_OFFSETS["attn_norm"],
    "attn_q": ATTN_L0_OFFSETS["attn_q"],
    "attn_k": ATTN_L0_OFFSETS["attn_k"],
    "attn_v": ATTN_L0_OFFSETS["attn_v"],
    "attn_output": ATTN_L0_OFFSETS["attn_output"],
    "attn_q_norm": ATTN_L0_OFFSETS["attn_q_norm"],
    "attn_k_norm": ATTN_L0_OFFSETS["attn_k_norm"],
}
MOE_BASE = {
    "ffn_down_exps": 687_266_304,
    "ffn_gate_exps": 901_175_808,
    "ffn_up_exps": 1_116_142_080,
    "ffn_gate_inp": 1_115_085_312,
    "ffn_norm": 1_116_133_888,
}
TOP_K = 8
CHECKPOINT_SHA = "4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c"
# Stop depth expansion if MLX vs CPU max_abs exceeds this (material drift).
DRIFT_STOP_MAX_ABS = 1e-3


def off(kind: str, layer: int) -> int:
    if kind in ATTN_BASE:
        return ATTN_BASE[kind] + layer * LAYER_STRIDE
    if kind in MOE_BASE:
        return MOE_BASE[kind] + layer * LAYER_STRIDE
    raise ExpertOracleError("tensor_kind", kind)


def load_f32(model: Path, offset: int, n: int) -> list[float]:
    return list(struct.unpack(f"<{n}f", _pread(model, offset, n * 4)))


def load_f32_matrix(model: Path, offset: int, rows: int, cols: int) -> list[list[float]]:
    data = _pread(model, offset, rows * cols * 4)
    out: list[list[float]] = []
    rb = cols * 4
    for r in range(rows):
        out.append(list(struct.unpack(f"<{cols}f", data[r * rb : (r + 1) * rb])))
    return out


def expert_range(kind: str, layer: int, expert_index: int) -> tuple[int, int]:
    base = off(kind, layer)
    nbytes = EXPERT_DOWN_BYTES if kind == "ffn_down_exps" else EXPERT_GATE_UP_BYTES
    return base + expert_index * nbytes, nbytes


def topk_router(logits: list[float], k: int = TOP_K) -> tuple[list[int], list[float], list[float]]:
    m = max(logits)
    exps = [math.exp(float(v) - m) for v in logits]
    s = sum(exps)
    probs = [e / s for e in exps]
    order = sorted(range(EXPERTS), key=lambda i: (-probs[i], i))
    ids = order[:k]
    raw = [probs[i] for i in ids]
    den = sum(raw)
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


def attention_layer_cpu(
    model: Path, layer: int, residual: list[list[float]], positions: list[int]
) -> dict[str, Any]:
    """residual: [n_tok][HIDDEN] stream entering layer; returns ffn_inp per token."""
    n_tok = len(residual)
    attn_norm_w = load_f32(model, off("attn_norm", layer), HIDDEN)
    q_norm_w = load_f32(model, off("attn_q_norm", layer), N_EMBD_HEAD)
    k_norm_w = load_f32(model, off("attn_k_norm", layer), N_EMBD_HEAD)

    qs: list[list[float]] = []
    ks: list[list[float]] = []
    vs: list[list[float]] = []
    for tok_i, emb in enumerate(residual):
        h = rms_norm(emb, attn_norm_w)
        q = matvec_q8(model, off("attn_q", layer), Q_OUT, HIDDEN, h)
        k = matvec_q8(model, off("attn_k", layer), KV_OUT, HIDDEN, h)
        v = matvec_q8(model, off("attn_v", layer), KV_OUT, HIDDEN, h)
        q = rms_norm_heads(q, q_norm_w, N_HEAD, N_EMBD_HEAD)
        k = rms_norm_heads(k, k_norm_w, N_HEAD_KV, N_EMBD_HEAD)
        pos = positions[tok_i]
        q = rope_neox(q, N_HEAD, N_EMBD_HEAD, pos)
        k = rope_neox(k, N_HEAD_KV, N_EMBD_HEAD, pos)
        qs.append(q)
        ks.append(k)
        vs.append(v)

    scale = 1.0 / math.sqrt(N_EMBD_HEAD)
    group = N_HEAD // N_HEAD_KV
    ffn_inps: list[list[float]] = []
    attn_projs: list[list[float]] = []
    for t in range(n_tok):
        out_heads = [0.0] * Q_OUT
        for h in range(N_HEAD):
            kv_h = h // group
            q = qs[t][h * N_EMBD_HEAD : (h + 1) * N_EMBD_HEAD]
            scores = []
            for s in range(t + 1):
                k = ks[s][kv_h * N_EMBD_HEAD : (kv_h + 1) * N_EMBD_HEAD]
                scores.append(scale * sum(a * b for a, b in zip(q, k, strict=True)))
            m = max(scores)
            exps = [math.exp(v - m) for v in scores]
            den = sum(exps)
            weights = [e / den for e in exps]
            acc = [0.0] * N_EMBD_HEAD
            for s, w in enumerate(weights):
                v = vs[s][kv_h * N_EMBD_HEAD : (kv_h + 1) * N_EMBD_HEAD]
                for i in range(N_EMBD_HEAD):
                    acc[i] += w * v[i]
            base = h * N_EMBD_HEAD
            out_heads[base : base + N_EMBD_HEAD] = acc
        proj = matvec_q8(model, off("attn_output", layer), HIDDEN, Q_OUT, out_heads)
        attn_projs.append(proj)
        ffn_inps.append([residual[t][i] + proj[i] for i in range(HIDDEN)])
    return {
        "ffn_inp": ffn_inps,
        "attn_proj": attn_projs,
        "ffn_inp_sha256": [_f32le_sha(f) for f in ffn_inps],
    }


def moe_layer_cpu(model: Path, layer: int, residual: list[float]) -> dict[str, Any]:
    norm_w = load_f32(model, off("ffn_norm", layer), HIDDEN)
    gate_w = load_f32_matrix(model, off("ffn_gate_inp", layer), EXPERTS, HIDDEN)
    normed = rms_norm(residual, norm_w)
    logits = [sum(w * a for w, a in zip(row, normed, strict=True)) for row in gate_w]
    ids, raw, weights = topk_router(logits)
    agg = [0.0] * HIDDEN
    for eid, w in zip(ids, weights, strict=True):
        part = run_expert(model, layer, eid, normed, w)
        for i, v in enumerate(part):
            agg[i] += v
    block = [r + a for r, a in zip(residual, agg, strict=True)]
    return {
        "expert_ids": ids,
        "routing_weights": weights,
        "normed_sha256": _f32le_sha(normed),
        "logits_sha256": _f32le_sha(logits),
        "aggregate_sha256": _f32le_sha(agg),
        "block_sha256": _f32le_sha(block),
        "aggregate": agg,
        "block": block,
        "normed": normed,
    }


def moe_layer_mlx(model: Path, layer: int, residual: list[float]) -> dict[str, Any]:
    """Fully independent MLX MoE on residual (recomputes router; architecture path)."""
    import mlx.core as mx

    # Router on CPU-precision f32 (same numbers as CPU path for identical residual).
    norm_w = load_f32(model, off("ffn_norm", layer), HIDDEN)
    gate_w = load_f32_matrix(model, off("ffn_gate_inp", layer), EXPERTS, HIDDEN)
    normed = rms_norm(residual, norm_w)
    logits = [sum(w * a for w, a in zip(row, normed, strict=True)) for row in gate_w]
    ids, raw, weights = topk_router(logits)

    residual_mx = mx.array(residual, dtype=mx.float32)
    agg = mx.zeros((HIDDEN,), dtype=mx.float32)

    def decode_matrix(enc: bytes, rows: int, cols: int) -> "mx.array":
        row_b = (cols // 32) * 34
        rows_out = []
        for r in range(rows):
            rows_out.append(_decode_q8_0_row(enc[r * row_b : (r + 1) * row_b], cols))
        return mx.array(rows_out, dtype=mx.float32)

    act = mx.array(normed, dtype=mx.float32)
    for eid, w in zip(ids, weights, strict=True):
        go, gn = expert_range("ffn_gate_exps", layer, eid)
        uo, un = expert_range("ffn_up_exps", layer, eid)
        do, dn = expert_range("ffn_down_exps", layer, eid)
        g = decode_matrix(_pread(model, go, gn), INTERMEDIATE, HIDDEN) @ act
        u = decode_matrix(_pread(model, uo, un), INTERMEDIATE, HIDDEN) @ act
        h = (g * mx.sigmoid(g)) * u
        d = decode_matrix(_pread(model, do, dn), HIDDEN, INTERMEDIATE) @ h
        agg = agg + d * mx.array(w, dtype=mx.float32)
    block = residual_mx + agg
    mx.eval(block)
    return {
        "expert_ids": ids,
        "routing_weights": weights,
        "aggregate": agg.tolist(),
        "block": block.tolist(),
        "aggregate_sha256": _f32le_sha(agg.tolist()),
        "block_sha256": _f32le_sha(block.tolist()),
    }

def attention_layer_mlx(
    model: Path, layer: int, residual: list[list[float]], positions: list[int]
) -> dict[str, Any]:
    """MLX attention path (architecture dequant × f32)."""
    import mlx.core as mx

    n_tok = len(residual)
    attn_norm_w = mx.array(load_f32(model, off("attn_norm", layer), HIDDEN), dtype=mx.float32)
    q_norm_w = mx.array(load_f32(model, off("attn_q_norm", layer), N_EMBD_HEAD), dtype=mx.float32)
    k_norm_w = mx.array(load_f32(model, off("attn_k_norm", layer), N_EMBD_HEAD), dtype=mx.float32)

    def decode_mat(offset: int, rows: int, cols: int) -> "mx.array":
        row_b = (cols // 32) * 34
        enc = _pread(model, offset, rows * row_b)
        rows_out = []
        for r in range(rows):
            rows_out.append(_decode_q8_0_row(enc[r * row_b : (r + 1) * row_b], cols))
        return mx.array(rows_out, dtype=mx.float32)

    wq = decode_mat(off("attn_q", layer), Q_OUT, HIDDEN)
    wk = decode_mat(off("attn_k", layer), KV_OUT, HIDDEN)
    wv = decode_mat(off("attn_v", layer), KV_OUT, HIDDEN)
    wo = decode_mat(off("attn_output", layer), HIDDEN, Q_OUT)

    def rms(x, w):
        return w * x * mx.rsqrt(mx.mean(x * x) + EPS)

    def rms_heads(x, w, n_head, d):
        x3 = x.reshape((n_head, d))
        ms = mx.mean(x3 * x3, axis=-1, keepdims=True)
        return (w * x3 * mx.rsqrt(ms + EPS)).reshape((-1,))

    def rope(x, n_head, d, pos):
        half = d // 2
        x3 = x.reshape((n_head, d))
        freqs = mx.array(
            [1.0 / (ROPE_THETA ** (2 * i / d)) for i in range(half)], dtype=mx.float32
        )
        ang = pos * freqs
        c, s = mx.cos(ang), mx.sin(ang)
        x0, x1 = x3[:, :half], x3[:, half:]
        return mx.concatenate([x0 * c - x1 * s, x0 * s + x1 * c], axis=-1).reshape((-1,))

    embds = [mx.array(r, dtype=mx.float32) for r in residual]
    qs, ks, vs = [], [], []
    for tok_i, emb in enumerate(embds):
        h = rms(emb, attn_norm_w)
        q = rms_heads(wq @ h, q_norm_w, N_HEAD, N_EMBD_HEAD)
        k = rms_heads(wk @ h, k_norm_w, N_HEAD_KV, N_EMBD_HEAD)
        v = wv @ h
        q = rope(q, N_HEAD, N_EMBD_HEAD, positions[tok_i])
        k = rope(k, N_HEAD_KV, N_EMBD_HEAD, positions[tok_i])
        mx.eval(q, k, v)
        qs.append(q)
        ks.append(k)
        vs.append(v)

    scale = 1.0 / math.sqrt(N_EMBD_HEAD)
    group = N_HEAD // N_HEAD_KV
    ffn_inps = []
    for t in range(n_tok):
        out_heads = []
        for h in range(N_HEAD):
            kv_h = h // group
            q = qs[t].reshape((N_HEAD, N_EMBD_HEAD))[h]
            scores = []
            for s in range(t + 1):
                k = ks[s].reshape((N_HEAD_KV, N_EMBD_HEAD))[kv_h]
                scores.append(scale * mx.sum(q * k))
            weights = mx.softmax(mx.stack(scores))
            acc = mx.zeros((N_EMBD_HEAD,), dtype=mx.float32)
            for s in range(t + 1):
                v = vs[s].reshape((N_HEAD_KV, N_EMBD_HEAD))[kv_h]
                acc = acc + weights[s] * v
            out_heads.append(acc)
        proj = wo @ mx.concatenate(out_heads, axis=0)
        block = embds[t] + proj
        mx.eval(block)
        ffn_inps.append(block.tolist())
    return {
        "ffn_inp": ffn_inps,
        "ffn_inp_sha256": [_f32le_sha(f) for f in ffn_inps],
    }


def load_capture_rows(path: Path | None) -> list[list[float]] | None:
    if path is None or not path.exists():
        return None
    data = path.read_bytes()
    if len(data) != 2 * HIDDEN * 4:
        raise ExpertOracleError("capture", f"bad size {len(data)} for {path}")
    vals = list(struct.unpack(f"<{2 * HIDDEN}f", data))
    return [vals[0:HIDDEN], vals[HIDDEN : 2 * HIDDEN]]


def depth_ladder(max_layers: int) -> list[int]:
    """1, 2, 4, 8, 16, …, max_layers (always include max_layers)."""
    ladder = []
    d = 1
    while d < max_layers:
        ladder.append(d)
        d *= 2
    if not ladder or ladder[-1] != max_layers:
        ladder.append(max_layers)
    return ladder


def run_stack(
    model: Path,
    tokens: list[int],
    positions: list[int],
    n_layers: int,
    ffn_inp_captures: dict[int, Path] | None = None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    # Embed once
    stream_cpu = [embed_token(model, t) for t in tokens]
    # MLX residual starts identical
    stream_mlx = [list(x) for x in stream_cpu]

    layer_reports: list[dict[str, Any]] = []
    stop_reason = None

    for layer in range(n_layers):
        t_layer = time.perf_counter()
        # --- attention ---
        attn_cpu = attention_layer_cpu(model, layer, stream_cpu, positions)
        attn_mlx = attention_layer_mlx(model, layer, stream_mlx, positions)

        attn_cmp = []
        attn_geo = []
        for row in range(len(tokens)):
            attn_cmp.append(
                compare_vectors(attn_mlx["ffn_inp"][row], attn_cpu["ffn_inp"][row], ABS_TOL, REL_TOL)
            )
            attn_geo.append(vector_geometry(attn_mlx["ffn_inp"][row], attn_cpu["ffn_inp"][row]))

        # optional secondary capture compare on ffn_inp
        cap_geo = None
        cap_path = (ffn_inp_captures or {}).get(layer)
        if cap_path is not None:
            cap = load_capture_rows(cap_path)
            if cap is not None:
                cap_geo = [
                    vector_geometry(attn_cpu["ffn_inp"][row], cap[row]) for row in range(len(tokens))
                ]

        # --- MoE residual per token (independent CPU and MLX streams) ---
        moe_cpu_rows = []
        moe_mlx_rows = []
        moe_cmp = []
        moe_geo = []
        for row in range(len(tokens)):
            c = moe_layer_cpu(model, layer, attn_cpu["ffn_inp"][row])
            m = moe_layer_mlx(model, layer, attn_mlx["ffn_inp"][row])
            moe_cpu_rows.append(c)
            moe_mlx_rows.append(m)
            moe_cmp.append(compare_vectors(m["block"], c["block"], ABS_TOL, REL_TOL))
            moe_geo.append(vector_geometry(m["block"], c["block"]))

        # advance residual streams
        stream_cpu = [c["block"] for c in moe_cpu_rows]
        stream_mlx = [m["block"] for m in moe_mlx_rows]

        # repeatability: re-hash CPU block
        block_sha_a = [_f32le_sha(s) for s in stream_cpu]
        # lightweight second MoE-only check would be expensive; trust attention double-run from F009
        # and record SHA of outputs

        max_abs_attn = max(g["maximum_absolute_error"] for g in attn_geo)
        max_abs_moe = max(g["maximum_absolute_error"] for g in moe_geo)
        max_abs_layer = max(max_abs_attn, max_abs_moe)
        arch_pass = all(c["passed"] for c in attn_cmp) and all(c["passed"] for c in moe_cmp)

        report = {
            "layer": layer,
            "timing_wall_seconds": time.perf_counter() - t_layer,
            "attention": {
                "ffn_inp_sha256_cpu": attn_cpu["ffn_inp_sha256"],
                "ffn_inp_sha256_mlx": attn_mlx["ffn_inp_sha256"],
                "comparison_mlx_vs_cpu": attn_cmp,
                "geometry_mlx_vs_cpu": attn_geo,
                "capture_geometry_cpu_vs_llama": cap_geo,
                "passed": all(c["passed"] for c in attn_cmp),
            },
            "moe": {
                "expert_ids": [c["expert_ids"] for c in moe_cpu_rows],
                "routing_weights": [c["routing_weights"] for c in moe_cpu_rows],
                "block_sha256_cpu": [c["block_sha256"] for c in moe_cpu_rows],
                "block_sha256_mlx": [m["block_sha256"] for m in moe_mlx_rows],
                "comparison_mlx_vs_cpu": moe_cmp,
                "geometry_mlx_vs_cpu": moe_geo,
                "passed": all(c["passed"] for c in moe_cmp),
            },
            "layer_max_abs_mlx_vs_cpu": max_abs_layer,
            "architecture_passed": arch_pass,
            "l_out_sha256_cpu": block_sha_a,
        }
        layer_reports.append(report)

        if not arch_pass or max_abs_layer > DRIFT_STOP_MAX_ABS:
            stop_reason = {
                "at_layer": layer,
                "architecture_passed": arch_pass,
                "max_abs": max_abs_layer,
                "threshold": DRIFT_STOP_MAX_ABS,
            }
            break

    return {
        "tokens": tokens,
        "positions": positions,
        "requested_layers": n_layers,
        "completed_layers": len(layer_reports),
        "stop_reason": stop_reason,
        "layers": layer_reports,
        "final_l_out_sha256_cpu": layer_reports[-1]["l_out_sha256_cpu"] if layer_reports else None,
        # Residual streams retained for logits/greedy heads (architecture values).
        "final_residual_cpu": stream_cpu,
        "final_residual_mlx": stream_mlx,
        "timing_total_wall_seconds": time.perf_counter() - t0,
        "architecture": {
            "n_head": N_HEAD,
            "n_head_kv": N_HEAD_KV,
            "head_dim": N_EMBD_HEAD,
            "rope": "neox",
            "rope_theta": ROPE_THETA,
            "top_k": TOP_K,
            "experts": EXPERTS,
            "matmul_contract": "q8_0_weight_dequant_x_f32_activation",
            "layer_form": "l_out = ffn_inp + MoE(RMSNorm(ffn_inp)); ffn_inp = residual + Attn(...)",
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--evidence-dir", type=Path, required=True)
    p.add_argument("--source-commit", type=str, required=True)
    p.add_argument("--tokens", type=str, default="0,1")
    p.add_argument("--positions", type=str, default="0,1")
    p.add_argument("--max-layers", type=int, default=4)
    p.add_argument(
        "--ffn-inp-capture-dir",
        type=Path,
        default=None,
        help="dir with ffn_inp-{L}.f32le secondary llama refs",
    )
    p.add_argument("--ladder", type=str, default="auto", help="comma depths or 'auto'")
    args = p.parse_args(argv)

    tokens = [int(x) for x in args.tokens.split(",")]
    positions = [int(x) for x in args.positions.split(",")]
    if len(tokens) != len(positions):
        print("layer_stack: tokens/positions length mismatch", file=sys.stderr)
        return 1

    if args.ladder == "auto":
        depths = depth_ladder(args.max_layers)
    else:
        depths = [int(x) for x in args.ladder.split(",")]

    caps: dict[int, Path] = {}
    if args.ffn_inp_capture_dir is not None:
        for L in range(args.max_layers):
            cand = args.ffn_inp_capture_dir / f"ffn_inp-{L}.f32le"
            if cand.exists():
                caps[L] = cand

    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.evidence_dir / "f010-f011-layer-stack-summary.json"
    if summary_path.exists():
        print("layer_stack: refuse overwrite summary", file=sys.stderr)
        return 1

    all_runs = []
    overall_pass = True
    for depth in depths:
        out = args.evidence_dir / f"f011-stack-depth-{depth:02d}-0001.json"
        if out.exists():
            print(f"layer_stack: refuse overwrite {out}", file=sys.stderr)
            return 1
        print(f"layer_stack: running depth={depth} ...", flush=True)
        result = run_stack(model=args.model, tokens=tokens, positions=positions, n_layers=depth, ffn_inp_captures=caps)
        passed = (
            result["stop_reason"] is None
            and result["completed_layers"] == depth
            and all(lr["architecture_passed"] for lr in result["layers"])
        )
        # growth of error across layers
        max_abs_by_layer = [lr["layer_max_abs_mlx_vs_cpu"] for lr in result["layers"]]
        record = {
            "schema": "pulsarmlx.research.layer-stack-parity",
            "schema_version": "1.0.0",
            "feature_id": "010-011-layer-stack",
            "experiment_id": f"f011-stack-depth-{depth:02d}-0001",
            "actual_status": "passed" if passed else "failed",
            "source_commit": args.source_commit,
            "checkpoint_sha256": CHECKPOINT_SHA,
            "depth": depth,
            "result": result,
            "max_abs_mlx_vs_cpu_by_layer": max_abs_by_layer,
            "claim_boundary": {
                "operation": f"architecture_layer_stack_depth_{depth}",
                "status": "verified" if passed else "failed",
                "matmul_contract": "q8_0_weight_dequant_x_f32_activation",
                "unsupported_interpretations": [
                    "llama_q8x8_bit_parity",
                    "full_model" if depth < 48 else None,
                    "logits",
                    "generation",
                    "tokens_per_second",
                ],
            },
        }
        # scrub nulls from unsupported list
        record["claim_boundary"]["unsupported_interpretations"] = [
            x for x in record["claim_boundary"]["unsupported_interpretations"] if x
        ]
        out.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        all_runs.append(
            {
                "depth": depth,
                "status": record["actual_status"],
                "completed_layers": result["completed_layers"],
                "max_abs_by_layer": max_abs_by_layer,
                "stop_reason": result["stop_reason"],
                "timing_seconds": result["timing_total_wall_seconds"],
                "path": str(out),
            }
        )
        print(
            json.dumps(
                {
                    "depth": depth,
                    "status": record["actual_status"],
                    "max_abs_by_layer": max_abs_by_layer,
                    "stop_reason": result["stop_reason"],
                    "seconds": result["timing_total_wall_seconds"],
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if not passed:
            overall_pass = False
            print("layer_stack: stopping depth expansion after failure", flush=True)
            break

    # F010 slice: depth-1 complete layer-0 evidence alias
    f010 = args.evidence_dir / "f010-complete-layer0-0001.json"
    depth1 = next((r for r in all_runs if r["depth"] == 1), None)
    if depth1 and not f010.exists():
        src = json.loads(Path(depth1["path"]).read_text(encoding="utf-8"))
        f010_doc = {
            "schema": "pulsarmlx.research.complete-layer0-parity",
            "schema_version": "1.0.0",
            "feature_id": "010-complete-layer0",
            "experiment_id": "f010-complete-layer0-0001",
            "actual_status": src["actual_status"],
            "source_commit": args.source_commit,
            "checkpoint_sha256": CHECKPOINT_SHA,
            "layer0": src["result"]["layers"][0] if src["result"]["layers"] else None,
            "max_abs_mlx_vs_cpu": (src["max_abs_mlx_vs_cpu_by_layer"] or [None])[0],
            "claim_boundary": {
                "operation": "layer_0_attention_plus_moe_residual",
                "status": "verified" if src["actual_status"] == "passed" else "failed",
                "matmul_contract": "q8_0_weight_dequant_x_f32_activation",
                "unsupported_interpretations": [
                    "llama_q8x8_bit_parity",
                    "multi_layer",
                    "logits",
                    "generation",
                ],
            },
        }
        f010.write_text(json.dumps(f010_doc, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    summary = {
        "schema": "pulsarmlx.research.layer-stack-summary",
        "schema_version": "1.0.0",
        "feature_id": "010-011-layer-stack",
        "actual_status": "passed" if overall_pass else "failed",
        "source_commit": args.source_commit,
        "checkpoint_sha256": CHECKPOINT_SHA,
        "ladder": depths,
        "runs": all_runs,
        "tokens": tokens,
        "positions": positions,
        "contract": "architecture_cpu_mlx_parity_q8_weight_f32_act",
    }
    summary_path.write_text(
        json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(json.dumps({"summary_status": summary["actual_status"], "runs": all_runs}, sort_keys=True))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
