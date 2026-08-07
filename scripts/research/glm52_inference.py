#!/usr/bin/env python3
"""GLM inference mode: architecture-correct forward with expert cache.

Modes:
  research  — uncached (default research helpers)
  inference — ExpertSlabCache + MLX matmul after dequant

Does not delete the research path. Golden check: compare tokens to C11.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glm52_dense_primitives import embed_token, load_f32_vector, matvec_weight, rms_norm
from glm52_expert import run_expert_swiglu
from glm52_expert_cache_runtime import ExpertSlabCache, expert_matvec_cached
from glm52_layer import layer_forward_token, moe_ffn
from glm52_mla import CompactKVCache, RMS_EPS
from glm52_tensor_store import Glm52TensorStore

GOLDEN = [9703, 21615, 220, 16, 13, 16, 16, 15, 15]
N_LAYER = 79


def silu(v: float) -> float:
    if v >= 0:
        return v / (1.0 + math.exp(-v))
    ex = math.exp(v)
    return v * ex / (1.0 + ex)


def run_expert_swiglu_cached(
    store: Glm52TensorStore,
    cache: ExpertSlabCache,
    layer: int,
    expert: int,
    x: list[float],
    weight: float = 1.0,
    *,
    shared: bool = False,
) -> list[float]:
    if shared:
        g = expert_matvec_cached(store, cache, f"blk.{layer}.ffn_gate_shexp.weight", 0, x)
        u = expert_matvec_cached(store, cache, f"blk.{layer}.ffn_up_shexp.weight", 0, x)
        h = [silu(a) * b for a, b in zip(g, u, strict=True)]
        d = expert_matvec_cached(store, cache, f"blk.{layer}.ffn_down_shexp.weight", 0, h)
    else:
        g = expert_matvec_cached(store, cache, f"blk.{layer}.ffn_gate_exps.weight", expert, x)
        u = expert_matvec_cached(store, cache, f"blk.{layer}.ffn_up_exps.weight", expert, x)
        h = [silu(a) * b for a, b in zip(g, u, strict=True)]
        d = expert_matvec_cached(store, cache, f"blk.{layer}.ffn_down_exps.weight", expert, h)
    return [weight * v for v in d]


def moe_ffn_cached(
    store: Glm52TensorStore,
    cache: ExpertSlabCache,
    layer: int,
    residual: list[float],
) -> list[float]:
    from glm52_router import glm_route_real

    x = rms_norm(residual, load_f32_vector(store, f"blk.{layer}.ffn_norm.weight"), RMS_EPS)
    logits = matvec_weight(store, f"blk.{layer}.ffn_gate_inp.weight", x)
    bias = load_f32_vector(store, f"blk.{layer}.exp_probs_b.bias")
    route = glm_route_real(logits, bias)
    acc = [0.0] * len(residual)
    for eid, w in zip(route["expert_ids"], route["weights"], strict=True):
        part = run_expert_swiglu_cached(store, cache, layer, eid, x, w, shared=False)
        for i, v in enumerate(part):
            acc[i] += v
    she = run_expert_swiglu_cached(store, cache, layer, 0, x, 1.0, shared=True)
    for i, v in enumerate(she):
        acc[i] += v
    return [a + b for a, b in zip(residual, acc, strict=True)]


def layer_forward_inference(
    store: Glm52TensorStore,
    cache: ExpertSlabCache,
    layer: int,
    residual: list[float],
    kv: CompactKVCache,
    pos: int,
) -> list[float]:
    from glm52_mla import mla_forward_token, N_LEADING_DENSE, dense_ffn

    mid, _ = mla_forward_token(store, layer, residual, kv, pos)
    if layer < N_LEADING_DENSE:
        return dense_ffn(store, layer, mid)
    return moe_ffn_cached(store, cache, layer, mid)


def logits_from_hidden(store: Glm52TensorStore, h: list[float]) -> list[float]:
    xn = rms_norm(h, load_f32_vector(store, "output_norm.weight"), RMS_EPS)
    return matvec_weight(store, "output.weight", xn)


def argmax(v: list[float]) -> int:
    bi, bv = 0, v[0]
    for i, x in enumerate(v):
        if x > bv:
            bi, bv = i, x
    return bi


def generate(
    store: Glm52TensorStore,
    seed: list[int],
    n_new: int,
    *,
    mode: str = "inference",
    cache_bytes: int = 2 * 1024**3,
) -> dict:
    expert_cache = ExpertSlabCache(max_bytes=cache_bytes) if mode == "inference" else None
    kvs = [CompactKVCache() for _ in range(N_LAYER)]
    generated = list(seed)
    timings: list[dict] = []
    t_all = time.perf_counter()

    x: list[float] | None = None
    for pos, tid in enumerate(seed):
        t0 = time.perf_counter()
        x = embed_token(store, tid)
        for layer in range(N_LAYER):
            if mode == "inference" and expert_cache is not None:
                x = layer_forward_inference(store, expert_cache, layer, x, kvs[layer], pos)
            else:
                x, _ = layer_forward_token(store, layer, x, kvs[layer], pos)
        timings.append({"phase": "prefill", "pos": pos, "sec": time.perf_counter() - t0})

    assert x is not None
    for step in range(n_new):
        t0 = time.perf_counter()
        tid = argmax(logits_from_hidden(store, x))
        t_logits = time.perf_counter() - t0
        generated.append(tid)
        pos = len(seed) + step
        t1 = time.perf_counter()
        x = embed_token(store, tid)
        for layer in range(N_LAYER):
            if mode == "inference" and expert_cache is not None:
                x = layer_forward_inference(store, expert_cache, layer, x, kvs[layer], pos)
            else:
                x, _ = layer_forward_token(store, layer, x, kvs[layer], pos)
        timings.append(
            {
                "phase": "decode",
                "step": step,
                "token": tid,
                "logits_sec": t_logits,
                "stack_sec": time.perf_counter() - t1,
            }
        )

    golden_ok = generated[: len(GOLDEN)] == GOLDEN[: len(generated)]
    return {
        "mode": mode,
        "generated_token_ids": generated,
        "golden": GOLDEN,
        "matches_golden_prefix": golden_ok,
        "matches_golden_full": generated == GOLDEN if len(generated) == len(GOLDEN) else False,
        "seconds": time.perf_counter() - t_all,
        "timings": timings,
        "expert_cache": expert_cache.stats.to_dict() if expert_cache else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="GLM MLX/architecture inference mode")
    ap.add_argument("--mode", choices=("research", "inference"), default="inference")
    ap.add_argument("--n-new", type=int, default=1, help="new tokens (default 1 for smoke)")
    ap.add_argument("--cache-gib", type=float, default=2.0)
    ap.add_argument("--out", type=Path, default=Path("docs/research/glm52/raw/f016-inference-run.json"))
    args = ap.parse_args()

    store = Glm52TensorStore(Path.home() / "Models/PulsarMLX/GLM-5.2-UD-IQ2_XXS")
    result = generate(
        store,
        [9703],
        args.n_new,
        mode=args.mode,
        cache_bytes=int(args.cache_gib * 1024**3),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: result[k] for k in result if k != "timings"}, indent=2))
    store.close()
    return 0 if result["matches_golden_prefix"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
