#!/usr/bin/env python3
"""C11: frozen P-MIN greedy generation ≥8 new tokens (architecture path)."""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glm52_dense_primitives import embed_token, load_f32_vector, matvec_weight, rms_norm
from glm52_layer import layer_forward_token
from glm52_mla import CompactKVCache, RMS_EPS
from glm52_tensor_store import Glm52TensorStore


def argmax(v: list[float]) -> int:
    best_i, best = 0, v[0]
    for i, x in enumerate(v):
        if x > best:
            best_i, best = i, x
    return best_i


def main() -> int:
    raw = Path("docs/research/glm52/raw")
    seed = json.loads((raw / "f016-frozen-prompts-0001.json").read_text())["prompts"][
        "P-MIN"
    ]["token_ids"]
    n_new = 8
    n_layer = 79
    print("seed", seed, flush=True)

    store = Glm52TensorStore(Path.home() / "Models/PulsarMLX/GLM-5.2-UD-IQ2_XXS")
    caches = [CompactKVCache() for _ in range(n_layer)]
    generated = list(seed)
    t_all = time.time()

    def logits_from_hidden(h: list[float]) -> list[float]:
        xn = rms_norm(h, load_f32_vector(store, "output_norm.weight"), RMS_EPS)
        return matvec_weight(store, "output.weight", xn)

    x: list[float] | None = None
    for pos, tid in enumerate(seed):
        x = embed_token(store, tid)
        for layer in range(n_layer):
            x, _ = layer_forward_token(store, layer, x, caches[layer], pos=pos)
        print(
            f"prefill pos={pos} tid={tid} l2={math.sqrt(sum(v * v for v in x)):.4f}",
            flush=True,
        )

    assert x is not None
    for step in range(n_new):
        t0 = time.time()
        logits = logits_from_hidden(x)
        tid = argmax(logits)
        generated.append(tid)
        print(f"step {step} -> {tid} logits_sec={time.time() - t0:.1f}", flush=True)
        pos = len(seed) + step
        x = embed_token(store, tid)
        t1 = time.time()
        for layer in range(n_layer):
            x, _ = layer_forward_token(store, layer, x, caches[layer], pos=pos)
        print(
            f"  decode stack sec={time.time() - t1:.1f} "
            f"l2={math.sqrt(sum(v * v for v in x)):.4f}",
            flush=True,
        )
        (raw / "f016-c11-generation-progress.json").write_text(
            json.dumps(
                {
                    "generated": generated,
                    "step": step,
                    "elapsed": time.time() - t_all,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

    ev = {
        "schema": "pulsarmlx.research.glm52-c11-generation",
        "boundary": "GLM-C11",
        "actual_status": "passed" if len(generated) >= len(seed) + n_new else "failed",
        "prompt_id": "P-MIN",
        "prompt_text": "Hello",
        "seed_token_ids": seed,
        "generated_token_ids": generated,
        "new_tokens": generated[len(seed) :],
        "seconds": time.time() - t_all,
        "note": (
            "Greedy argmax ≥8 new tokens on architecture 79-layer path. "
            "Not a quality claim; residual scale may be large."
        ),
    }
    (raw / "f016-c11-generation-0001.json").write_text(
        json.dumps(ev, indent=2, sort_keys=True) + "\n"
    )
    print("C11", ev["actual_status"], generated, "sec", ev["seconds"], flush=True)
    store.close()
    return 0 if ev["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
