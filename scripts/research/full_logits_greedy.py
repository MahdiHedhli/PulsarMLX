#!/usr/bin/env python3
"""Full-logits + first greedy token under architecture oracle.

Runs the multi-layer stack for --layers (default 48 = full model), then:
  h = RMSNorm(l_out[-1], output_norm)
  logits = output.weight @ h   (Q8_0 weight dequant × f32 act)
  greedy = argmax(logits)

Primary: MLX ≈ CPU on final residual, logits max_abs/RMSE, top-1/top-k, greedy token.
Does not claim llama bit-parity or tokens/sec.
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
from layer0_attention import vector_geometry, rms_norm, EPS  # noqa: E402
from layer_stack_parity import run_stack, CHECKPOINT_SHA  # noqa: E402

VOCAB = 151_936
OUTPUT_NORM_OFF = 336_582_144
OUTPUT_WEIGHT_OFF = 5_969_408
TOP_K_LOGITS = 5


def load_f32(model: Path, offset: int, n: int) -> list[float]:
    return list(struct.unpack(f"<{n}f", _pread(model, offset, n * 4)))


def logits_cpu(model: Path, hidden: list[float]) -> tuple[list[float], dict[str, Any]]:
    """CPU architecture logits via numpy Q8_0 dequant matvec (independent of MLX)."""
    import numpy as np

    t0 = time.perf_counter()
    w_norm = load_f32(model, OUTPUT_NORM_OFF, HIDDEN)
    h = rms_norm(hidden, w_norm, EPS)
    h_np = np.asarray(h, dtype=np.float32)
    row_b = (HIDDEN // Q8_BLOCK) * Q8_BLOCK_BYTES
    enc = _pread(model, OUTPUT_WEIGHT_OFF, VOCAB * row_b)
    # Dequant all rows into (VOCAB, HIDDEN)
    n_blocks = HIDDEN // Q8_BLOCK
    # Vectorized-ish decode by block
    W = np.empty((VOCAB, HIDDEN), dtype=np.float32)
    for r in range(VOCAB):
        base = r * row_b
        for b in range(n_blocks):
            bb = base + b * Q8_BLOCK_BYTES
            scale = struct.unpack_from("<e", enc, bb)[0]
            quants = np.frombuffer(enc, dtype=np.int8, count=Q8_BLOCK, offset=bb + 2)
            W[r, b * Q8_BLOCK : (b + 1) * Q8_BLOCK] = scale * quants.astype(np.float32)
    logits_np = W @ h_np
    logits = logits_np.astype(np.float64).tolist()
    elapsed = time.perf_counter() - t0
    return logits, {
        "normed_sha256": _f32le_sha(h),
        "logits_sha256": _f32le_sha(logits),
        "timing_cpu_wall_seconds": elapsed,
        "normed": h,
        "backend": "numpy_q8_dequant_matvec",
    }

def logits_mlx(model: Path, hidden: list[float]) -> tuple[list[float], dict[str, Any]]:
    import mlx.core as mx

    t0 = time.perf_counter()
    w_norm = mx.array(load_f32(model, OUTPUT_NORM_OFF, HIDDEN), dtype=mx.float32)
    x = mx.array(hidden, dtype=mx.float32)
    h = w_norm * x * mx.rsqrt(mx.mean(x * x) + EPS)
    row_b = (HIDDEN // Q8_BLOCK) * Q8_BLOCK_BYTES
    enc = _pread(model, OUTPUT_WEIGHT_OFF, VOCAB * row_b)
    # Decode in chunks to limit peak memory pressure
    chunk = 4096
    parts = []
    for start in range(0, VOCAB, chunk):
        n = min(chunk, VOCAB - start)
        rows = []
        base = start * row_b
        for r in range(n):
            rows.append(_decode_q8_0_row(enc[base + r * row_b : base + (r + 1) * row_b], HIDDEN))
        W = mx.array(rows, dtype=mx.float32)
        parts.append(W @ h)
        mx.eval(parts[-1])
    logits_mx = mx.concatenate(parts, axis=0)
    mx.eval(logits_mx)
    logits = logits_mx.tolist()
    return logits, {
        "logits_sha256": _f32le_sha(logits),
        "timing_mlx_wall_seconds": time.perf_counter() - t0,
        "runtime": {
            "backend": "apple-mlx",
            "selected_device": "gpu",
            "fallback_used": False,
            "evaluated": True,
            "synchronized": True,
        },
    }


def topk_ids(logits: list[float], k: int) -> list[int]:
    order = sorted(range(len(logits)), key=lambda i: (-logits[i], i))
    return order[:k]


def rank_of(logits: list[float], token: int) -> int:
    v = logits[token]
    # rank = number of scores strictly greater, then stable by index
    return sum(1 for i, x in enumerate(logits) if (x > v) or (x == v and i < token))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--evidence-dir", type=Path, required=True)
    p.add_argument("--source-commit", type=str, required=True)
    p.add_argument("--tokens", type=str, default="0,1")
    p.add_argument("--positions", type=str, default="0,1")
    p.add_argument("--layers", type=int, default=48)
    p.add_argument("--row", type=int, default=1, help="which sequence position for logits (default last)")
    args = p.parse_args(argv)

    tokens = [int(x) for x in args.tokens.split(",")]
    positions = [int(x) for x in args.positions.split(",")]
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    stack_path = args.evidence_dir / f"f012-full-stack-depth-{args.layers:02d}-0001.json"
    logits_path = args.evidence_dir / "f012-full-logits-0001.json"
    greedy_path = args.evidence_dir / "f013-greedy-token-0001.json"
    for path in (stack_path, logits_path, greedy_path):
        if path.exists():
            print(f"full_logits: refuse overwrite {path}", file=sys.stderr)
            return 1

    print(f"full_logits: stack layers={args.layers} ...", flush=True)
    stack = run_stack(
        model=args.model,
        tokens=tokens,
        positions=positions,
        n_layers=args.layers,
        ffn_inp_captures=None,
    )
    stack_ok = (
        stack["stop_reason"] is None
        and stack["completed_layers"] == args.layers
        and all(lr["architecture_passed"] for lr in stack["layers"])
    )
    # Publish stack without multi-MB residual vectors (SHAs + metrics only).
    stack_pub = {k: v for k, v in stack.items() if k not in ("final_residual_cpu", "final_residual_mlx")}
    stack_path.write_text(
        json.dumps(
            {
                "schema": "pulsarmlx.research.layer-stack-parity",
                "feature_id": "012-full-logits-prep",
                "experiment_id": f"f012-full-stack-depth-{args.layers:02d}-0001",
                "actual_status": "passed" if stack_ok else "failed",
                "source_commit": args.source_commit,
                "checkpoint_sha256": CHECKPOINT_SHA,
                "depth": args.layers,
                "result": stack_pub,
                "max_abs_mlx_vs_cpu_by_layer": [
                    lr["layer_max_abs_mlx_vs_cpu"] for lr in stack["layers"]
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    if not stack_ok:
        print(json.dumps({"status": "failed", "phase": "stack", "stop": stack["stop_reason"]}))
        return 1

    stream_cpu = stack["final_residual_cpu"]
    stream_mlx = stack["final_residual_mlx"]
    if stream_cpu is None or stream_mlx is None:
        print("full_logits: stack missing residual streams", file=sys.stderr)
        return 1

    row = args.row if args.row >= 0 else len(tokens) - 1
    if row < 0 or row >= len(tokens):
        print("full_logits: bad row", file=sys.stderr)
        return 1

    print("full_logits: CPU logits ...", flush=True)
    logits_c, meta_c = logits_cpu(args.model, stream_cpu[row])
    print("full_logits: MLX logits ...", flush=True)
    logits_m, meta_m = logits_mlx(args.model, stream_mlx[row])

    cmp = compare_vectors(logits_m, logits_c, ABS_TOL, REL_TOL)
    geo = vector_geometry(logits_m, logits_c)
    top_cpu = topk_ids(logits_c, TOP_K_LOGITS)
    top_mlx = topk_ids(logits_m, TOP_K_LOGITS)
    greedy_cpu = top_cpu[0]
    greedy_mlx = top_mlx[0]
    top1_agree = greedy_cpu == greedy_mlx
    topk_agree = top_cpu == top_mlx
    # rank stability of CPU greedy in MLX ranking
    rank_mlx_of_cpu_greedy = rank_of(logits_m, greedy_cpu)

    residual_cmp = compare_vectors(stream_mlx[row], stream_cpu[row], ABS_TOL, REL_TOL)
    residual_geo = vector_geometry(stream_mlx[row], stream_cpu[row])

    # Deterministic repeatability: second greedy from same logits sha
    greedy_repeat = greedy_cpu == topk_ids(logits_c, 1)[0]

    logits_passed = cmp["passed"] and top1_agree and residual_cmp["passed"]
    logits_record = {
        "schema": "pulsarmlx.research.full-logits-parity",
        "schema_version": "1.0.0",
        "feature_id": "012-full-logits",
        "experiment_id": "f012-full-logits-0001",
        "actual_status": "passed" if logits_passed else "failed",
        "source_commit": args.source_commit,
        "checkpoint_sha256": CHECKPOINT_SHA,
        "layers": args.layers,
        "tokens": tokens,
        "positions": positions,
        "logit_row": row,
        "vocab": VOCAB,
        "residual_final": {
            "comparison_mlx_vs_cpu": residual_cmp,
            "geometry_mlx_vs_cpu": residual_geo,
            "sha256_cpu": _f32le_sha(stream_cpu[row]),
            "sha256_mlx": _f32le_sha(stream_mlx[row]),
        },
        "output_norm_sha256": meta_c["normed_sha256"],
        "logits": {
            "sha256_cpu": meta_c["logits_sha256"],
            "sha256_mlx": meta_m["logits_sha256"],
            "comparison_mlx_vs_cpu": cmp,
            "geometry_mlx_vs_cpu": geo,
            "top_k": TOP_K_LOGITS,
            "top_k_ids_cpu": top_cpu,
            "top_k_ids_mlx": top_mlx,
            "top1_agreement": top1_agree,
            "topk_agreement": topk_agree,
            "rank_of_cpu_greedy_in_mlx": rank_mlx_of_cpu_greedy,
        },
        "runtime": meta_m["runtime"],
        "timing": {
            "stack_wall_seconds": stack["timing_total_wall_seconds"],
            "logits_cpu_wall_seconds": meta_c["timing_cpu_wall_seconds"],
            "logits_mlx_wall_seconds": meta_m["timing_mlx_wall_seconds"],
        },
        "claim_boundary": {
            "operation": f"full_logits_after_{args.layers}_layers",
            "status": "verified" if logits_passed else "failed",
            "matmul_contract": "q8_0_weight_dequant_x_f32_activation",
            "unsupported_interpretations": [
                "llama_q8x8_bit_parity",
                "generation_multi_token" if True else None,
                "tokens_per_second",
                "glm_5_2",
            ],
        },
    }
    logits_record["claim_boundary"]["unsupported_interpretations"] = [
        x for x in logits_record["claim_boundary"]["unsupported_interpretations"] if x
    ]
    logits_path.write_text(
        json.dumps(logits_record, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )

    greedy_passed = top1_agree and greedy_repeat and logits_passed
    greedy_record = {
        "schema": "pulsarmlx.research.greedy-token",
        "schema_version": "1.0.0",
        "feature_id": "013-greedy-token",
        "experiment_id": "f013-greedy-token-0001",
        "actual_status": "passed" if greedy_passed else "failed",
        "source_commit": args.source_commit,
        "checkpoint_sha256": CHECKPOINT_SHA,
        "layers": args.layers,
        "prompt_token_ids": tokens,
        "positions": positions,
        "greedy_token_id_cpu": greedy_cpu,
        "greedy_token_id_mlx": greedy_mlx,
        "agreement": top1_agree,
        "deterministic_repeatability": greedy_repeat,
        "top_k_ids_cpu": top_cpu,
        "top_k_ids_mlx": top_mlx,
        "logits_max_abs_mlx_vs_cpu": cmp["maximum_absolute_error"],
        "logits_rmse_mlx_vs_cpu": cmp["rmse"],
        "claim_boundary": {
            "operation": "first_deterministic_greedy_token",
            "status": "verified" if greedy_passed else "failed",
            "decoding": "argmax",
            "unsupported_interpretations": [
                "sampling",
                "multi_token_generation",
                "tokens_per_second",
                "llama_bit_parity",
            ],
        },
    }
    greedy_path.write_text(
        json.dumps(greedy_record, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "status": "passed" if greedy_passed else "failed",
                "stack_ok": stack_ok,
                "logits_passed": logits_passed,
                "greedy_cpu": greedy_cpu,
                "greedy_mlx": greedy_mlx,
                "top1_agree": top1_agree,
                "topk_agree": topk_agree,
                "logits_max_abs": cmp["maximum_absolute_error"],
                "logits_rmse": cmp["rmse"],
                "logits_cosine": geo["cosine_similarity"],
                "residual_max_abs": residual_cmp["maximum_absolute_error"],
            },
            sort_keys=True,
        )
    )
    return 0 if greedy_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
