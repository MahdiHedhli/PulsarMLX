#!/usr/bin/env python3
"""Bounded short-prompt greedy generation (architecture path).

Starts from frozen direct token ids, greedily extends --new-tokens steps.
Each step:
  - MLX full stack on current prefix (architecture Q8_0×f32)
  - CPU logits head on MLX residual (independent dequant) for token check
  - Optional full dual residual check on the final prefix only

Does not claim tokens/sec, sampling, or llama bit-parity.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from expert_oracle import (  # noqa: E402
    ABS_TOL,
    REL_TOL,
    _f32le_sha,
    compare_vectors,
)
from layer0_attention import vector_geometry  # noqa: E402
from layer_stack_parity import (  # noqa: E402
    CHECKPOINT_SHA,
    embed_token,
    attention_layer_mlx,
    attention_layer_cpu,
    moe_layer_mlx,
    moe_layer_cpu,
)
from full_logits_greedy import logits_cpu, logits_mlx, topk_ids  # noqa: E402


def forward_mlx(model: Path, tokens: list[int], positions: list[int], n_layers: int) -> list[list[float]]:
    stream = [embed_token(model, t) for t in tokens]
    for layer in range(n_layers):
        attn = attention_layer_mlx(model, layer, stream, positions)
        stream = [moe_layer_mlx(model, layer, attn["ffn_inp"][r])["block"] for r in range(len(tokens))]
    return stream


def forward_cpu(model: Path, tokens: list[int], positions: list[int], n_layers: int) -> list[list[float]]:
    stream = [embed_token(model, t) for t in tokens]
    for layer in range(n_layers):
        attn = attention_layer_cpu(model, layer, stream, positions)
        stream = [moe_layer_cpu(model, layer, attn["ffn_inp"][r])["block"] for r in range(len(tokens))]
    return stream


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--evidence-out", type=Path, required=True)
    p.add_argument("--source-commit", type=str, required=True)
    p.add_argument("--prompt-tokens", type=str, default="0,1")
    p.add_argument("--new-tokens", type=int, default=4)
    p.add_argument("--layers", type=int, default=48)
    p.add_argument("--dual-check-final", action="store_true", default=True)
    args = p.parse_args(argv)

    if args.evidence_out.exists():
        print("generate_short: refuse overwrite", file=sys.stderr)
        return 1

    prompt = [int(x) for x in args.prompt_tokens.split(",")]
    tokens = list(prompt)
    positions = list(range(len(tokens)))
    steps = []
    t0 = time.perf_counter()

    for step in range(args.new_tokens):
        t_step = time.perf_counter()
        print(f"generate_short: step {step+1}/{args.new_tokens} prefix={tokens} ...", flush=True)
        stream_mlx = forward_mlx(args.model, tokens, positions, args.layers)
        logits_m, meta_m = logits_mlx(args.model, stream_mlx[-1])
        # CPU head on MLX residual (independent weight dequant)
        logits_c_head, meta_c = logits_cpu(args.model, stream_mlx[-1])
        g_m = topk_ids(logits_m, 1)[0]
        g_c = topk_ids(logits_c_head, 1)[0]
        top5_m = topk_ids(logits_m, 5)
        top5_c = topk_ids(logits_c_head, 5)
        cmp = compare_vectors(logits_m, logits_c_head, ABS_TOL, REL_TOL)
        geo = vector_geometry(logits_m, logits_c_head)
        step_rec = {
            "step": step,
            "prefix_tokens": list(tokens),
            "prefix_len": len(tokens),
            "greedy_mlx": g_m,
            "greedy_cpu_head": g_c,
            "top1_agreement": g_m == g_c,
            "topk5_mlx": top5_m,
            "topk5_cpu_head": top5_c,
            "logits_comparison": cmp,
            "logits_geometry": geo,
            "residual_last_sha256_mlx": _f32le_sha(stream_mlx[-1]),
            "timing_step_wall_seconds": time.perf_counter() - t_step,
        }
        steps.append(step_rec)
        print(
            json.dumps(
                {
                    "step": step,
                    "greedy": g_m,
                    "agree": g_m == g_c,
                    "logits_max_abs": cmp["maximum_absolute_error"],
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if g_m != g_c:
            print("generate_short: top-1 disagreement; stopping", flush=True)
            break
        tokens.append(g_m)
        positions.append(len(positions))

    dual = None
    if args.dual_check_final and all(s["top1_agreement"] for s in steps):
        print("generate_short: final dual residual check ...", flush=True)
        t_d = time.perf_counter()
        # Compare residual on the last prefix that produced a token (or final sequence if all done)
        check_tokens = tokens if len(steps) == args.new_tokens else tokens
        # If we appended all, dual-check full final sequence; else last successful prefix
        stream_c = forward_cpu(args.model, check_tokens, list(range(len(check_tokens))), args.layers)
        stream_m = forward_mlx(args.model, check_tokens, list(range(len(check_tokens))), args.layers)
        dual_rows = []
        for r in range(len(check_tokens)):
            dual_rows.append(
                {
                    "row": r,
                    "comparison": compare_vectors(stream_m[r], stream_c[r], ABS_TOL, REL_TOL),
                    "geometry": vector_geometry(stream_m[r], stream_c[r]),
                }
            )
        dual = {
            "tokens": check_tokens,
            "rows": dual_rows,
            "passed": all(d["comparison"]["passed"] for d in dual_rows),
            "timing_wall_seconds": time.perf_counter() - t_d,
        }

    gen_tokens = [s["greedy_mlx"] for s in steps if s["top1_agreement"]]
    passed = (
        len(gen_tokens) == args.new_tokens
        and all(s["top1_agreement"] for s in steps)
        and (dual is None or dual["passed"])
    )
    # Deterministic repeatability: re-run first step only
    print("generate_short: repeatability first step ...", flush=True)
    stream_r = forward_mlx(args.model, prompt, list(range(len(prompt))), args.layers)
    g_r = topk_ids(logits_mlx(args.model, stream_r[-1])[0], 1)[0]
    repeat_ok = g_r == steps[0]["greedy_mlx"] if steps else False

    record = {
        "schema": "pulsarmlx.research.short-prompt-generation",
        "schema_version": "1.0.0",
        "feature_id": "014-short-prompt-generation",
        "experiment_id": "f014-short-prompt-gen-0001",
        "actual_status": "passed" if passed and repeat_ok else "failed",
        "source_commit": args.source_commit,
        "checkpoint_sha256": CHECKPOINT_SHA,
        "layers": args.layers,
        "prompt_token_ids": prompt,
        "new_tokens_requested": args.new_tokens,
        "generated_token_ids": gen_tokens,
        "full_sequence_token_ids": prompt + gen_tokens,
        "steps": steps,
        "dual_residual_check": dual,
        "deterministic_repeatability_first_token": {
            "matched": repeat_ok,
            "first_greedy": steps[0]["greedy_mlx"] if steps else None,
            "repeat_greedy": g_r,
        },
        "timing_total_wall_seconds": time.perf_counter() - t0,
        "claim_boundary": {
            "operation": f"greedy_extend_{args.new_tokens}_tokens",
            "status": "verified" if passed and repeat_ok else "failed",
            "decoding": "argmax",
            "matmul_contract": "q8_0_weight_dequant_x_f32_activation",
            "unsupported_interpretations": [
                "sampling",
                "tokens_per_second",
                "llama_bit_parity",
                "kv_cache_optimized_runtime",
                "glm_5_2",
            ],
        },
    }
    args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
    args.evidence_out.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": record["actual_status"],
                "prompt": prompt,
                "generated": gen_tokens,
                "full_sequence": prompt + gen_tokens,
                "repeat_ok": repeat_ok,
                "dual_passed": None if dual is None else dual["passed"],
                "seconds": record["timing_total_wall_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0 if record["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
