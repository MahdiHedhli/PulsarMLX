#!/usr/bin/env python3
"""C10 logits + C11 short greedy generation from C09 final hidden or fresh forward."""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glm52_dense_primitives import (
    compare_vectors,
    dequant_row,
    embed_token,
    load_f32_vector,
    matvec_weight,
    rms_norm,
)
from glm52_layer import layer_forward_token
from glm52_mla import CompactKVCache, RMS_EPS
from glm52_tensor_store import Glm52TensorStore


def logits_from_hidden(store: Glm52TensorStore, hidden: list[float]) -> list[float]:
    xn = rms_norm(hidden, load_f32_vector(store, "output_norm.weight"), RMS_EPS)
    # output.weight [n_embd, n_vocab] → y[v] = embd_row_v · xn
    # full vocab matvec is large; use MLX bulk path via matvec_weight
    return matvec_weight(store, "output.weight", xn)


def argmax(v: list[float]) -> int:
    best_i = 0
    best = v[0]
    for i, x in enumerate(v):
        if x > best:
            best = x
            best_i = i
    return best_i


def forward_prompt(
    store: Glm52TensorStore, token_ids: list[int]
) -> tuple[list[float], list[CompactKVCache]]:
    """Prefill: sequential single-token steps updating per-layer caches."""
    n_layer = 79
    caches = [CompactKVCache() for _ in range(n_layer)]
    x: list[float] | None = None
    for pos, tid in enumerate(token_ids):
        x = embed_token(store, tid)
        for layer in range(n_layer):
            # residual stream continues; for pos>0, we need previous residual
            # Architecture: each position starts from its embedding and
            # attends over KV cache built from prior positions. Layer stack
            # is per-position with residual only within that position's
            # layer path; KV carries cross-position state.
            x, _ = layer_forward_token(store, layer, x, caches[layer], pos=pos)
    assert x is not None
    return x, caches


def main() -> int:
    root = Path.home() / "Models/PulsarMLX/GLM-5.2-UD-IQ2_XXS"
    raw = Path("docs/research/glm52/raw")
    store = Glm52TensorStore(root)

    # ---- C10: logits from C09 final hidden if present, else recompute ----
    t0 = time.time()
    hidden_path = raw / "f016-c09-final-hidden.json"
    if hidden_path.exists():
        hidden = json.loads(hidden_path.read_text())["hidden"]
        source = "c09_final_hidden"
    else:
        caches = [CompactKVCache() for _ in range(79)]
        x = embed_token(store, 0)
        for layer in range(79):
            x, _ = layer_forward_token(store, layer, x, caches[layer], pos=0)
        hidden = x
        source = "recomputed"
    logits = logits_from_hidden(store, hidden)
    assert len(logits) == 154880
    assert all(math.isfinite(v) for v in logits)
    top = sorted(range(len(logits)), key=lambda i: -logits[i])[:8]
    # repeatability: second matvec from same hidden
    logits2 = logits_from_hidden(store, hidden)
    cmp = compare_vectors(logits, logits2, 0.0, 0.0)
    ev10 = {
        "schema": "pulsarmlx.research.glm52-c10-logits",
        "boundary": "GLM-C10",
        "actual_status": "passed" if cmp["passed"] else "failed",
        "source_hidden": source,
        "vocab": len(logits),
        "argmax": argmax(logits),
        "top8": top,
        "top8_values": [logits[i] for i in top],
        "logits_l2": math.sqrt(sum(v * v for v in logits)),
        "repeatability": cmp,
        "seconds": time.time() - t0,
    }
    (raw / "f016-c10-logits-0001.json").write_text(
        json.dumps(ev10, indent=2, sort_keys=True) + "\n"
    )
    print("C10", ev10["actual_status"], "argmax", ev10["argmax"], flush=True)

    # ---- C11: short greedy gen (≥8 tokens) from frozen minimal prompt ----
    prompts_path = raw / "f016-frozen-prompts-0001.json"
    seed_ids = [9703]  # frozen P-MIN "Hello"
    if prompts_path.exists():
        prompts = json.loads(prompts_path.read_text())
        pmin = (prompts.get("prompts") or {}).get("P-MIN") or {}
        if pmin.get("token_ids"):
            seed_ids = list(pmin["token_ids"])
    n_new = 8
    t1 = time.time()
    # fresh forward for prompt
    x, caches = forward_prompt(store, seed_ids)
    generated = list(seed_ids)
    for step in range(n_new):
        logits = logits_from_hidden(store, x)
        tid = argmax(logits)
        generated.append(tid)
        # decode step: new token at pos = len(prompt)+step
        pos = len(seed_ids) + step
        x = embed_token(store, tid)
        for layer in range(79):
            x, _ = layer_forward_token(store, layer, x, caches[layer], pos=pos)
        print(f"gen step {step} -> {tid}", flush=True)
    # dual run first next-token for determinism
    x_a, c_a = forward_prompt(store, seed_ids)
    t_a = argmax(logits_from_hidden(store, x_a))
    x_b, c_b = forward_prompt(store, seed_ids)
    t_b = argmax(logits_from_hidden(store, x_b))
    ev11 = {
        "schema": "pulsarmlx.research.glm52-c11-generation",
        "boundary": "GLM-C11",
        "actual_status": "passed" if t_a == t_b and len(generated) >= len(seed_ids) + n_new else "failed",
        "seed_token_ids": seed_ids,
        "generated_token_ids": generated,
        "new_tokens": generated[len(seed_ids) :],
        "first_next_token_repeatable": t_a == t_b,
        "first_next_token": t_a,
        "seconds": time.time() - t1,
        "note": "Greedy argmax generation ≥8 new tokens. Architecture path; not quality claim.",
    }
    (raw / "f016-c11-generation-0001.json").write_text(
        json.dumps(ev11, indent=2, sort_keys=True) + "\n"
    )
    print("C11", ev11["actual_status"], "tokens", ev11["new_tokens"], flush=True)
    store.close()
    return 0 if ev10["actual_status"] == "passed" and ev11["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
