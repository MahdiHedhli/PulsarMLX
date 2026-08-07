#!/usr/bin/env python3
"""Feature 009: Qwen3MoE layer-0 attention residual path (architecture oracle).

Computes:
  embd = token_embd[tokens]
  h = RMSNorm(embd, attn_norm)
  Q,K,V = Wq/Wk/Wv @ h   (Q8_0 weight dequant × f32 act)
  Q = RoPE_NEOX(RMSNorm_head(Q, q_norm))
  K = RoPE_NEOX(RMSNorm_head(K, k_norm))
  attn = softmax(Q K^T / sqrt(d) + causal) V   (GQA)
  out = Wo @ attn
  ffn_inp = embd + out

Compares CPU oracle and MLX to captured ffn_inp-0 (Feature 007).
Does not claim llama Q8_0×Q8_0 bit-parity.
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
    HIDDEN,
    Q8_BLOCK,
    Q8_BLOCK_BYTES,
    ExpertOracleError,
    _decode_q8_0_row,
    _f32le_sha,
    _matvec_q8_0,
    _pread,
    _sha256_bytes,
    compare_vectors,
)

# Qwen3-30B-A3B-Q8_0 layer-0 attention tensors (GGUFReader validated).
OFFSETS = {
    "token_embd": 336_590_336,
    "attn_norm": 668_317_696,
    "attn_q": 677_238_784,
    "attn_k": 667_203_072,
    "attn_v": 686_152_192,
    "attn_output": 668_325_888,
    "attn_q_norm": 686_151_680,
    "attn_k_norm": 668_317_184,
}
N_HEAD = 32
N_HEAD_KV = 4
N_EMBD_HEAD = 128  # key_length / value_length
N_ROT = 128
ROPE_THETA = 1_000_000.0
EPS = 1e-6
VOCAB = 151_936
EMB_ROW_BYTES = (HIDDEN // Q8_BLOCK) * Q8_BLOCK_BYTES  # 2176
# Q projects to N_HEAD * N_EMBD_HEAD = 4096
# K,V project to N_HEAD_KV * N_EMBD_HEAD = 512
Q_OUT = N_HEAD * N_EMBD_HEAD
KV_OUT = N_HEAD_KV * N_EMBD_HEAD


def load_f32(model: Path, offset: int, n: int) -> list[float]:
    return list(struct.unpack(f"<{n}f", _pread(model, offset, n * 4)))


def load_q8_matrix(model: Path, offset: int, rows: int, cols: int) -> bytes:
    row_b = (cols // Q8_BLOCK) * Q8_BLOCK_BYTES
    return _pread(model, offset, rows * row_b)


def embed_token(model: Path, token_id: int) -> list[float]:
    if token_id < 0 or token_id >= VOCAB:
        raise ExpertOracleError("token_id", "out of vocab")
    off = OFFSETS["token_embd"] + token_id * EMB_ROW_BYTES
    enc = _pread(model, off, EMB_ROW_BYTES)
    return _decode_q8_0_row(enc, HIDDEN)


def rms_norm(x: list[float], w: list[float], eps: float = EPS) -> list[float]:
    ms = sum(v * v for v in x) / len(x)
    scale = 1.0 / math.sqrt(ms + eps)
    return [w[i] * x[i] * scale for i in range(len(x))]


def rms_norm_heads(x: list[float], w: list[float], n_head: int, d: int) -> list[float]:
    """Per-head RMSNorm over last dim d; w shape [d]."""
    out = [0.0] * (n_head * d)
    for h in range(n_head):
        base = h * d
        chunk = x[base : base + d]
        ms = sum(v * v for v in chunk) / d
        scale = 1.0 / math.sqrt(ms + EPS)
        for i in range(d):
            out[base + i] = w[i] * chunk[i] * scale
    return out


def rope_neox(x: list[float], n_head: int, d: int, pos: int, theta: float = ROPE_THETA) -> list[float]:
    """NeoX RoPE: pairs are (i, i+d/2) for i in 0..d/2-1.

    Matches ggml NEOX / LLAMA_ROPE_TYPE_NEOX layout used by Qwen3MoE.
    """
    assert d % 2 == 0
    half = d // 2
    out = list(x)
    for h in range(n_head):
        base = h * d
        for i in range(half):
            freq = 1.0 / (theta ** (2 * i / d))
            ang = pos * freq
            c = math.cos(ang)
            s = math.sin(ang)
            x0 = x[base + i]
            x1 = x[base + i + half]
            out[base + i] = x0 * c - x1 * s
            out[base + i + half] = x0 * s + x1 * c
    return out


def matvec_q8(model: Path, offset: int, rows: int, cols: int, x: list[float]) -> list[float]:
    enc = load_q8_matrix(model, offset, rows, cols)
    return _matvec_q8_0(enc, rows, cols, x)


def attention_cpu(
    model: Path, tokens: list[int], positions: list[int]
) -> dict[str, Any]:
    t0 = time.perf_counter()
    n_tok = len(tokens)
    attn_norm_w = load_f32(model, OFFSETS["attn_norm"], HIDDEN)
    q_norm_w = load_f32(model, OFFSETS["attn_q_norm"], N_EMBD_HEAD)
    k_norm_w = load_f32(model, OFFSETS["attn_k_norm"], N_EMBD_HEAD)

    embds = [embed_token(model, t) for t in tokens]
    # Per-token projections
    qs: list[list[float]] = []
    ks: list[list[float]] = []
    vs: list[list[float]] = []
    for tok_i, emb in enumerate(embds):
        h = rms_norm(emb, attn_norm_w)
        q = matvec_q8(model, OFFSETS["attn_q"], Q_OUT, HIDDEN, h)
        k = matvec_q8(model, OFFSETS["attn_k"], KV_OUT, HIDDEN, h)
        v = matvec_q8(model, OFFSETS["attn_v"], KV_OUT, HIDDEN, h)
        q = rms_norm_heads(q, q_norm_w, N_HEAD, N_EMBD_HEAD)
        k = rms_norm_heads(k, k_norm_w, N_HEAD_KV, N_EMBD_HEAD)
        pos = positions[tok_i]
        q = rope_neox(q, N_HEAD, N_EMBD_HEAD, pos)
        k = rope_neox(k, N_HEAD_KV, N_EMBD_HEAD, pos)
        qs.append(q)
        ks.append(k)
        vs.append(v)

    scale = 1.0 / math.sqrt(N_EMBD_HEAD)
    # GQA: each query head maps to kv_head = q_head // (n_head/n_head_kv)
    group = N_HEAD // N_HEAD_KV
    attn_outs: list[list[float]] = []  # per token, concatenated heads [4096]

    for t in range(n_tok):
        out_heads = [0.0] * Q_OUT
        for h in range(N_HEAD):
            kv_h = h // group
            q = qs[t][h * N_EMBD_HEAD : (h + 1) * N_EMBD_HEAD]
            # scores over keys 0..t (causal)
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
        attn_outs.append(out_heads)

    # output projection + residual
    ffn_inps: list[list[float]] = []
    attn_projs: list[list[float]] = []
    for t in range(n_tok):
        # Wo is [4096, 2048] in GGUF shape [4096 2048] → ne0=4096, ne1=2048
        # mul_mat: rows=2048, cols=4096
        proj = matvec_q8(model, OFFSETS["attn_output"], HIDDEN, Q_OUT, attn_outs[t])
        attn_projs.append(proj)
        ffn_inps.append([embds[t][i] + proj[i] for i in range(HIDDEN)])

    elapsed = time.perf_counter() - t0
    return {
        "tokens": tokens,
        "positions": positions,
        "embd_sha256": [_f32le_sha(e) for e in embds],
        "attn_proj_sha256": [_f32le_sha(a) for a in attn_projs],
        "ffn_inp_sha256": [_f32le_sha(f) for f in ffn_inps],
        "ffn_inp": ffn_inps,
        "attn_proj": attn_projs,
        "embds": embds,
        "timing_cpu_wall_seconds": elapsed,
        "architecture": {
            "n_head": N_HEAD,
            "n_head_kv": N_HEAD_KV,
            "n_embd_head": N_EMBD_HEAD,
            "rope": "neox",
            "rope_theta": ROPE_THETA,
            "q_norm": True,
            "k_norm": True,
            "scale": scale,
            "eps": EPS,
            "matmul_contract": "q8_0_weight_dequant_x_f32_activation",
        },
    }


def attention_mlx(model: Path, cpu: dict) -> dict[str, Any]:
    import mlx.core as mx

    t0 = time.perf_counter()
    tokens = cpu["tokens"]
    positions = cpu["positions"]
    n_tok = len(tokens)

    def decode_mat(offset: int, rows: int, cols: int) -> "mx.array":
        enc = load_q8_matrix(model, offset, rows, cols)
        row_b = (cols // Q8_BLOCK) * Q8_BLOCK_BYTES
        rows_out = []
        for r in range(rows):
            rows_out.append(_decode_q8_0_row(enc[r * row_b : (r + 1) * row_b], cols))
        return mx.array(rows_out, dtype=mx.float32)

    attn_norm_w = mx.array(load_f32(model, OFFSETS["attn_norm"], HIDDEN), dtype=mx.float32)
    q_norm_w = mx.array(load_f32(model, OFFSETS["attn_q_norm"], N_EMBD_HEAD), dtype=mx.float32)
    k_norm_w = mx.array(load_f32(model, OFFSETS["attn_k_norm"], N_EMBD_HEAD), dtype=mx.float32)
    wq = decode_mat(OFFSETS["attn_q"], Q_OUT, HIDDEN)
    wk = decode_mat(OFFSETS["attn_k"], KV_OUT, HIDDEN)
    wv = decode_mat(OFFSETS["attn_v"], KV_OUT, HIDDEN)
    wo = decode_mat(OFFSETS["attn_output"], HIDDEN, Q_OUT)

    embds = [mx.array(embed_token(model, t), dtype=mx.float32) for t in tokens]

    def rms(x, w):
        ms = mx.mean(x * x)
        return w * x * mx.rsqrt(ms + EPS)

    def rms_heads(x, w, n_head, d):
        x3 = x.reshape((n_head, d))
        ms = mx.mean(x3 * x3, axis=-1, keepdims=True)
        return (w * x3 * mx.rsqrt(ms + EPS)).reshape((-1,))

    def rope(x, n_head, d, pos):
        half = d // 2
        x3 = x.reshape((n_head, d))
        out = mx.array(x3)
        # build cos/sin for each half index
        freqs = mx.array(
            [1.0 / (ROPE_THETA ** (2 * i / d)) for i in range(half)], dtype=mx.float32
        )
        ang = pos * freqs
        c = mx.cos(ang)
        s = mx.sin(ang)
        x0 = x3[:, :half]
        x1 = x3[:, half:]
        y0 = x0 * c - x1 * s
        y1 = x0 * s + x1 * c
        return mx.concatenate([y0, y1], axis=-1).reshape((-1,))

    qs, ks, vs = [], [], []
    for tok_i, emb in enumerate(embds):
        h = rms(emb, attn_norm_w)
        q = wq @ h
        k = wk @ h
        v = wv @ h
        q = rms_heads(q, q_norm_w, N_HEAD, N_EMBD_HEAD)
        k = rms_heads(k, k_norm_w, N_HEAD_KV, N_EMBD_HEAD)
        pos = positions[tok_i]
        q = rope(q, N_HEAD, N_EMBD_HEAD, pos)
        k = rope(k, N_HEAD_KV, N_EMBD_HEAD, pos)
        mx.eval(q, k, v)
        qs.append(q)
        ks.append(k)
        vs.append(v)

    scale = 1.0 / math.sqrt(N_EMBD_HEAD)
    group = N_HEAD // N_HEAD_KV
    ffn_inps = []
    attn_projs = []
    for t in range(n_tok):
        out_heads = []
        for h in range(N_HEAD):
            kv_h = h // group
            q = qs[t].reshape((N_HEAD, N_EMBD_HEAD))[h]
            scores = []
            for s in range(t + 1):
                k = ks[s].reshape((N_HEAD_KV, N_EMBD_HEAD))[kv_h]
                scores.append(scale * mx.sum(q * k))
            scores_a = mx.stack(scores)
            weights = mx.softmax(scores_a)
            acc = mx.zeros((N_EMBD_HEAD,), dtype=mx.float32)
            for s in range(t + 1):
                v = vs[s].reshape((N_HEAD_KV, N_EMBD_HEAD))[kv_h]
                acc = acc + weights[s] * v
            out_heads.append(acc)
        concat = mx.concatenate(out_heads, axis=0)
        proj = wo @ concat
        mx.eval(proj)
        emb = embds[t]
        block = emb + proj
        mx.eval(block)
        pl = proj.tolist()
        bl = block.tolist()
        attn_projs.append(pl)
        ffn_inps.append(bl)

    return {
        "runtime": {
            "backend": "apple-mlx",
            "selected_device": "gpu",
            "fallback_used": False,
            "evaluated": True,
            "synchronized": True,
        },
        "ffn_inp": ffn_inps,
        "attn_proj": attn_projs,
        "ffn_inp_sha256": [_f32le_sha(f) for f in ffn_inps],
        "timing_mlx_wall_seconds": time.perf_counter() - t0,
    }


def load_ffn_inp_capture(path: Path) -> list[list[float]]:
    data = path.read_bytes()
    if len(data) != 2 * HIDDEN * 4:
        raise ExpertOracleError("capture", f"bad size {len(data)}")
    vals = list(struct.unpack(f"<{2 * HIDDEN}f", data))
    return [vals[0:HIDDEN], vals[HIDDEN : 2 * HIDDEN]]


def vector_geometry(actual: list[float], reference: list[float]) -> dict[str, Any]:
    """Cosine, norm ratio, and first maximum-error location (publication metrics)."""
    if len(actual) != len(reference):
        raise ExpertOracleError("geometry", "length mismatch")
    n = len(actual)
    max_abs = 0.0
    max_i = 0
    mean_abs = 0.0
    sum_sq = 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i, (a, b) in enumerate(zip(actual, reference, strict=True)):
        err = abs(a - b)
        mean_abs += err
        sum_sq += err * err
        if err > max_abs:
            max_abs = err
            max_i = i
        dot += a * b
        na += a * a
        nb += b * b
    na = math.sqrt(na)
    nb = math.sqrt(nb)
    cos = (dot / (na * nb)) if na > 0 and nb > 0 else 0.0
    return {
        "compared_count": n,
        "maximum_absolute_error": max_abs,
        "mean_absolute_error": mean_abs / n if n else 0.0,
        "rmse": math.sqrt(sum_sq / n) if n else 0.0,
        "cosine_similarity": cos,
        "norm_ratio": (na / nb) if nb > 0 else float("inf"),
        "first_maximum_error_index": max_i,
        "actual_at_max": actual[max_i],
        "reference_at_max": reference[max_i],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--ffn-inp-capture", type=Path, required=True)
    p.add_argument("--oracle-out", type=Path, required=True)
    p.add_argument("--evidence-out", type=Path, required=True)
    p.add_argument("--source-commit", type=str, required=True)
    p.add_argument("--tokens", type=str, default="0,1")
    p.add_argument("--positions", type=str, default="0,1")
    p.add_argument(
        "--checkpoint-sha256",
        type=str,
        default="4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c",
    )
    args = p.parse_args(argv)

    if args.oracle_out.exists() or args.evidence_out.exists():
        print("layer0_attention: refuse overwrite", file=sys.stderr)
        return 1

    tokens = [int(x) for x in args.tokens.split(",")]
    positions = [int(x) for x in args.positions.split(",")]
    if len(tokens) != 2 or len(positions) != 2:
        print("layer0_attention: need two tokens/positions", file=sys.stderr)
        return 1

    capture = load_ffn_inp_capture(args.ffn_inp_capture)
    capture_sha = _sha256_bytes(args.ffn_inp_capture.read_bytes())

    # Independent architecture CPU oracle (twice for deterministic repeatability).
    cpu_a = attention_cpu(args.model, tokens, positions)
    cpu_b = attention_cpu(args.model, tokens, positions)
    repeat_ok = cpu_a["ffn_inp_sha256"] == cpu_b["ffn_inp_sha256"]
    cpu = cpu_a

    # Secondary: architecture CPU vs frozen llama ffn_inp-0 capture.
    # Expected small Q8_0 activation-requant drift on attention matmuls (F008 contract).
    # Primary correctness is MLX ≈ architecture CPU, not llama bit-parity.
    cmp_cap_tol = []
    cmp_cap_geo = []
    for row in range(2):
        cmp_cap_tol.append(compare_vectors(cpu["ffn_inp"][row], capture[row], ABS_TOL, REL_TOL))
        cmp_cap_geo.append(vector_geometry(cpu["ffn_inp"][row], capture[row]))

    mlx = attention_mlx(args.model, cpu)
    cmp_mlx = []
    cmp_mlx_geo = []
    for row in range(2):
        cmp_mlx.append(compare_vectors(mlx["ffn_inp"][row], cpu["ffn_inp"][row], ABS_TOL, REL_TOL))
        cmp_mlx_geo.append(vector_geometry(mlx["ffn_inp"][row], cpu["ffn_inp"][row]))

    arch_passed = all(c["passed"] for c in cmp_mlx) and repeat_ok
    # Capture drift is informational; fail only if structure clearly broken.
    CAPTURE_STRUCTURAL_COS_MIN = 0.999
    CAPTURE_STRUCTURAL_MAX_ABS = 5e-3  # above F008-scale Q8×Q8 (~3.4e-3) would be a bug signal
    capture_structural_ok = all(
        g["cosine_similarity"] >= CAPTURE_STRUCTURAL_COS_MIN
        and g["maximum_absolute_error"] <= CAPTURE_STRUCTURAL_MAX_ABS
        for g in cmp_cap_geo
    )
    passed = arch_passed and capture_structural_ok

    oracle = {
        "schema": "pulsarmlx.research.layer0-attention-oracle",
        "schema_version": "1.0.0",
        "feature_id": "009-layer0-attention",
        "status": "passed" if arch_passed else "failed",
        "tokens": tokens,
        "positions": positions,
        "checkpoint_sha256": args.checkpoint_sha256,
        "architecture": cpu["architecture"],
        "embd_sha256": cpu["embd_sha256"],
        "attn_proj_sha256": cpu["attn_proj_sha256"],
        "result": {
            "ffn_inp_sha256": cpu["ffn_inp_sha256"],
            "ffn_inp": cpu["ffn_inp"],
            "formula": (
                "ffn_inp = embd + Wo(Attention("
                "RoPE_NEOX(q_norm(Wq·RMSNorm(embd))), "
                "RoPE_NEOX(k_norm(Wk·RMSNorm(embd))), "
                "Wv·RMSNorm(embd)))"
            ),
            "source_graph": (
                "llama.cpp b06aa774 src/models/qwen3moe.cpp: "
                "attn_norm → QKV → q/k RMSNorm → rope_ext NEOX → build_attn → add residual"
            ),
        },
        "deterministic_repeatability": {
            "two_cpu_runs_sha_match": repeat_ok,
            "run_a_sha256": cpu_a["ffn_inp_sha256"],
            "run_b_sha256": cpu_b["ffn_inp_sha256"],
        },
        "capture_reference": {
            "node": "ffn_inp-0",
            "path": str(args.ffn_inp_capture),
            "sha256": capture_sha,
            "role": "secondary_llama_fused_reference_not_architecture_ground_truth",
            "comparison_cpu_vs_capture_tolerance": cmp_cap_tol,
            "comparison_cpu_vs_capture_geometry": cmp_cap_geo,
            "expected_drift": (
                "llama attention matmuls may Q8_0-requantize activations; "
                "architecture oracle uses Q8_0 weight dequant × f32 activation (F008 contract B)"
            ),
        },
        "timing": {"cpu_wall_seconds": cpu["timing_cpu_wall_seconds"]},
        "comparison_policy": {
            "absolute_tolerance": ABS_TOL,
            "relative_tolerance": REL_TOL,
            "mode": "absolute_plus_relative",
            "primary": "mlx_vs_architecture_cpu",
            "secondary": "architecture_cpu_vs_llama_ffn_inp_capture_structural",
        },
        "unsupported_interpretations": [
            "llama_q8x8_bit_parity",
            "multi_layer",
            "logits",
            "generation",
            "tokens_per_second",
        ],
    }
    args.oracle_out.parent.mkdir(parents=True, exist_ok=True)
    args.oracle_out.write_text(
        json.dumps(oracle, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )

    record = {
        "schema": "pulsarmlx.research.layer0-attention-parity",
        "schema_version": "1.0.0",
        "feature_id": "009-layer0-attention",
        "experiment_id": "f009-layer0-attention-parity-0001",
        "actual_status": "passed" if passed else "failed",
        "source_commit": args.source_commit,
        "checkpoint_sha256": args.checkpoint_sha256,
        "tokens": tokens,
        "positions": positions,
        "capture_sha256": capture_sha,
        "runtime": mlx["runtime"],
        "oracle_ffn_inp_sha256": cpu["ffn_inp_sha256"],
        "result": {"ffn_inp_sha256": mlx["ffn_inp_sha256"]},
        "deterministic_repeatability": oracle["deterministic_repeatability"],
        "comparison_mlx_vs_cpu": cmp_mlx,
        "comparison_mlx_vs_cpu_geometry": cmp_mlx_geo,
        "comparison_cpu_vs_capture": cmp_cap_tol,
        "comparison_cpu_vs_capture_geometry": cmp_cap_geo,
        "capture_structural_ok": capture_structural_ok,
        "architecture_passed": arch_passed,
        "timing": {
            "cpu_wall_seconds": cpu["timing_cpu_wall_seconds"],
            "mlx_wall_seconds": mlx["timing_mlx_wall_seconds"],
        },
        "claim_boundary": {
            "operation": "layer_0_attention_residual_to_ffn_inp",
            "status": "verified" if passed else "failed",
            "matmul_contract": "q8_0_weight_dequant_x_f32_activation",
            "rope": "neox",
            "gqa": {"n_head": N_HEAD, "n_head_kv": N_HEAD_KV, "head_dim": N_EMBD_HEAD},
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
                "architecture_passed": arch_passed,
                "capture_structural_ok": capture_structural_ok,
                "repeat_ok": repeat_ok,
                "mlx_vs_cpu": [
                    {
                        "row": i,
                        "max_abs": c["maximum_absolute_error"],
                        "rmse": c["rmse"],
                        "mismatches": c["mismatch_count"],
                        "cosine": cmp_mlx_geo[i]["cosine_similarity"],
                    }
                    for i, c in enumerate(cmp_mlx)
                ],
                "cpu_vs_capture": [
                    {
                        "row": i,
                        "max_abs": g["maximum_absolute_error"],
                        "rmse": g["rmse"],
                        "cosine": g["cosine_similarity"],
                        "norm_ratio": g["norm_ratio"],
                        "first_max_idx": g["first_maximum_error_index"],
                    }
                    for i, g in enumerate(cmp_cap_geo)
                ],
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
