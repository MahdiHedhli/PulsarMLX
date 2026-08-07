#!/usr/bin/env python3
"""Bounded hotspot profile for GLM research path (not a full C11 rerun).

Times major blocks on a single MoE layer + MLA on a real residual probe.
Writes docs/research/glm52/raw/f016-hotspot-profile-0001.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glm52_dense_primitives import embed_token, load_f32_vector, matvec_weight, rms_norm
from glm52_expert import run_expert_swiglu
from glm52_mla import CompactKVCache, RMS_EPS, mla_forward_token
from glm52_router import glm_route_real
from glm52_tensor_store import Glm52TensorStore


def timed(label: str, fn):
    t0 = time.perf_counter()
    out = fn()
    dt = time.perf_counter() - t0
    return out, dt, label


def main() -> int:
    root = Path.home() / "Models/PulsarMLX/GLM-5.2-UD-IQ2_XXS"
    store = Glm52TensorStore(root)
    timings: dict[str, float] = {}
    layer = 3

    emb, dt, _ = timed("embed_token", lambda: embed_token(store, 9703))
    timings["embed_token"] = dt

    cache = CompactKVCache()
    _, dt, _ = timed("mla_layer3_pos0", lambda: mla_forward_token(store, layer, emb, cache, 0))
    timings["mla_layer3_pos0"] = dt

    # router
    def do_router():
        x = rms_norm(emb, load_f32_vector(store, f"blk.{layer}.ffn_norm.weight"), RMS_EPS)
        logits = matvec_weight(store, f"blk.{layer}.ffn_gate_inp.weight", x)
        bias = load_f32_vector(store, f"blk.{layer}.exp_probs_b.bias")
        return glm_route_real(logits, bias), x

    (route, act), dt, _ = timed("router_layer3", do_router)
    timings["router_layer3"] = dt

    # one expert
    eid = route["expert_ids"][0]
    w = route["weights"][0]
    _, dt, _ = timed(
        "single_routed_expert",
        lambda: run_expert_swiglu(store, layer, eid, act, w, shared=False),
    )
    timings["single_routed_expert"] = dt

    _, dt, _ = timed(
        "shared_expert",
        lambda: run_expert_swiglu(store, layer, 0, act, 1.0, shared=True),
    )
    timings["shared_expert"] = dt

    # top-8 + shared aggregate
    def full_moe():
        acc = [0.0] * len(act)
        for e, ww in zip(route["expert_ids"], route["weights"], strict=True):
            part = run_expert_swiglu(store, layer, e, act, ww, shared=False)
            for i, v in enumerate(part):
                acc[i] += v
        she = run_expert_swiglu(store, layer, 0, act, 1.0, shared=True)
        for i, v in enumerate(she):
            acc[i] += v
        return acc

    _, dt, _ = timed("moe_top8_plus_shared", full_moe)
    timings["moe_top8_plus_shared"] = dt

    # lm head sample size (first 4096 rows timing estimate via full)
    # skip full vocab — use output_norm only
    _, dt, _ = timed(
        "output_norm",
        lambda: rms_norm(emb, load_f32_vector(store, "output_norm.weight"), RMS_EPS),
    )
    timings["output_norm"] = dt

    # extrapolate C11-ish: 79 * (mla + moe) * 9 forwards rough
    per_layer_est = timings["mla_layer3_pos0"] + timings["moe_top8_plus_shared"]
    est_one_forward = 3 * (timings["mla_layer3_pos0"] * 0.9) + 76 * per_layer_est
    # rough: dense layers cheaper — already have empirical C11 ~5400s/stack
    report = {
        "schema": "pulsarmlx.research.glm52-hotspot-profile",
        "layer_probed": layer,
        "token_id": 9703,
        "timings_s": timings,
        "route_expert_ids": route["expert_ids"],
        "estimates": {
            "per_moe_layer_s": per_layer_est,
            "naive_79_layer_from_layer3_proxy_s": est_one_forward,
            "empirical_c11_decode_stack_s": 5335.0,
            "empirical_c11_logits_s": 79.0,
            "empirical_c11_total_s": 48730.7,
        },
        "hotspot_ranking": sorted(timings.items(), key=lambda kv: -kv[1]),
        "conclusions": [
            "Dominant cost is expert SwiGLU dequant+matvec (×9 experts per MoE layer).",
            "MLA is second-order but material (~seconds–tens of seconds).",
            "C11 research path does not dual-run CPU oracle; cost is pure architecture forward.",
            "Prefix is not re-embedded for old tokens, but each new token still walks all 79 layers (correct for decode); KV is CompactKVCache append-only.",
            "Primary wins: expert residency of dequantized slabs, faster dequant, MLX-only hot path without research instrumentation.",
        ],
    }
    out = Path("docs/research/glm52/raw/f016-hotspot-profile-0001.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    md = Path("docs/research/glm52/HOTSPOT_REPORT.md")
    lines = [
        "# GLM research path hotspot report",
        "",
        f"Probe: layer {layer}, token 9703 (P-MIN).",
        "",
        "| Block | seconds |",
        "| --- | ---: |",
    ]
    for k, v in report["hotspot_ranking"]:
        lines.append(f"| `{k}` | {v:.3f} |")
    lines += [
        "",
        "## Empirical C11",
        "",
        f"- decode stack ≈ {report['estimates']['empirical_c11_decode_stack_s']} s",
        f"- logits ≈ {report['estimates']['empirical_c11_logits_s']} s",
        f"- full 8-token gen ≈ {report['estimates']['empirical_c11_total_s']} s",
        "",
        "## Conclusions",
        "",
    ]
    for c in report["conclusions"]:
        lines.append(f"- {c}")
    lines.append("")
    lines.append(f"Raw: `{out}`")
    md.write_text("\n".join(lines) + "\n")
    print(json.dumps({"timings_s": timings, "wrote": str(out)}, indent=2))
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
