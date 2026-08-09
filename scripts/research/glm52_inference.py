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
import os
import subprocess
import sys
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glm52_dense_primitives import (
    embed_token,
    load_f32_vector,
    matvec_weight,
    require_mlx_backend,
    rms_norm,
)
from glm52_expert import run_expert_swiglu
from glm52_expert_cache_runtime import (
    ExpertSlabCache,
    MlxMatrixBackend,
    expert_matvec_cached,
)
from glm52_layer import layer_forward_token, moe_ffn
from glm52_memory_pressure import sample_pressure
from glm52_mla import CompactKVCache, RMS_EPS
from glm52_tensor_store import Glm52TensorStore

GOLDEN = [9703, 21615, 220, 16, 13, 16, 16, 15, 15]
N_LAYER = 79
ROOT = Path(__file__).resolve().parents[2]

_CACHE_DELTA_FIELDS = (
    "hits",
    "misses",
    "evictions",
    "admissions",
    "admission_rejections",
    "policy_bypasses",
    "storage_cache_hits",
    "storage_cache_misses",
    "decoded_cache_hits",
    "decoded_cache_misses",
    "storage_bytes_read",
    "storage_read_count",
    "storage_bytes_avoided",
    "decoded_bytes_materialized",
    "decoded_bytes_avoided",
    "expert_redecode_count",
    "storage_read_seconds",
    "dequant_seconds",
    "contiguous_buffer_seconds",
    "mlx_matrix_build_seconds",
    "mlx_matvec_count",
    "mlx_matvec_seconds",
    "transient_releases",
    "cpu_fallbacks",
)


def _stats_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    for field in _CACHE_DELTA_FIELDS:
        if field in before and field in after:
            delta[field] = after[field] - before[field]
    delta["bytes_resident_end"] = int(after.get("bytes_resident", 0))
    delta["resident_entries_end"] = int(after.get("resident_entries", 0))
    return delta


def _write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _source_identity() -> dict[str, Any]:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain=v1"],
        cwd=ROOT,
        text=True,
    ).strip()
    return {"source_commit": commit, "source_dirty": bool(status)}


def _checkpoint_identity() -> dict[str, Any]:
    manifest = json.loads((ROOT / "docs/validation/glm52-checkpoint.json").read_text())
    revision_binding = json.loads(
        (ROOT / "docs/validation/glm52-revision-binding.json").read_text()
    )
    if revision_binding["checkpoint_set_sha256"] != manifest["checkpoint_set_sha256"]:
        raise ValueError("checkpoint revision binding does not match acquisition identity")
    for local, remote in zip(
        manifest["files"], revision_binding["files"], strict=True
    ):
        if (
            local["filename"] != remote["filename"]
            or local["sha256"] != remote["local_sha256"]
            or local["sha256"] != remote["remote_lfs_etag"]
        ):
            raise ValueError("checkpoint revision binding file identity mismatch")
    return {
        "checkpoint_set_sha256": manifest["checkpoint_set_sha256"],
        "repo": manifest["repo"],
        "revision": revision_binding["revision"],
        "revision_status": "post_acquisition_content_binding",
        "revision_binding_evidence": "docs/validation/glm52-revision-binding.json",
        "quant": manifest["quant"],
        "file_count": manifest["file_count"],
        "total_bytes": manifest["total_bytes"],
        "files": manifest["files"],
    }


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
    route_sink: list[dict[str, Any]] | None = None,
) -> list[float]:
    from glm52_router import glm_route_real

    x = rms_norm(residual, load_f32_vector(store, f"blk.{layer}.ffn_norm.weight"), RMS_EPS)
    logits = matvec_weight(store, f"blk.{layer}.ffn_gate_inp.weight", x)
    bias = load_f32_vector(store, f"blk.{layer}.exp_probs_b.bias")
    route = glm_route_real(logits, bias)
    if route_sink is not None:
        route_sink.append(
            {
                "layer": layer,
                "expert_ids": list(route["expert_ids"]),
                "weights": list(route["weights"]),
                "shared_expert": 0,
            }
        )
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
    route_sink: list[dict[str, Any]] | None = None,
) -> list[float]:
    from glm52_mla import mla_forward_token, N_LEADING_DENSE, dense_ffn

    mid, _ = mla_forward_token(store, layer, residual, kv, pos)
    if layer < N_LEADING_DENSE:
        return dense_ffn(store, layer, mid)
    return moe_ffn_cached(store, cache, layer, mid, route_sink)


def logits_from_hidden(store: Glm52TensorStore, h: list[float]) -> list[float]:
    xn = rms_norm(h, load_f32_vector(store, "output_norm.weight"), RMS_EPS)
    return matvec_weight(store, "output.weight", xn)


def argmax(v: list[float]) -> int:
    bi, bv = 0, v[0]
    for i, x in enumerate(v):
        if x > bv:
            bi, bv = i, x
    return bi


def _run_stack(
    store: Glm52TensorStore,
    *,
    token_id: int,
    position: int,
    mode: str,
    cache: ExpertSlabCache | None,
    kvs: list[CompactKVCache],
) -> tuple[list[float], dict[str, Any]]:
    stack_start = time.perf_counter()
    x = embed_token(store, token_id)
    routes: list[dict[str, Any]] = []
    layer_timings: list[dict[str, Any]] = []
    for layer in range(N_LAYER):
        before = cache.stats.to_dict() if cache is not None else {}
        layer_start = time.perf_counter()
        if mode == "inference" and cache is not None:
            x = layer_forward_inference(
                store, cache, layer, x, kvs[layer], position, routes
            )
        else:
            x, _ = layer_forward_token(store, layer, x, kvs[layer], position)
        layer_record: dict[str, Any] = {
            "layer": layer,
            "seconds": time.perf_counter() - layer_start,
        }
        if cache is not None:
            layer_record["cache_delta"] = _stats_delta(before, cache.stats.to_dict())
        layer_timings.append(layer_record)
    return x, {
        "token_id": token_id,
        "position": position,
        "stack_seconds": time.perf_counter() - stack_start,
        "layers": layer_timings,
        "routes": routes,
        "resource_after": sample_pressure().to_public_dict(),
    }


def generate(
    store: Glm52TensorStore,
    seed: list[int],
    n_new: int,
    *,
    mode: str = "inference",
    cache_bytes: int = 16 * 1024**3,
    cache_policy: str = "decoded_shared_only",
    decoder_mode: str = "scalar_reference",
    progress_path: Path | None = None,
    evidence_context: dict[str, Any] | None = None,
) -> dict:
    expert_cache = (
        ExpertSlabCache(
            max_bytes=cache_bytes,
            policy=cache_policy,
            decoder_mode=decoder_mode,
        )
        if mode == "inference"
        else None
    )
    kvs = [CompactKVCache() for _ in range(N_LAYER)]
    generated = list(seed)
    timings: list[dict] = []
    routing: list[dict[str, Any]] = []
    t_all = time.perf_counter()
    context = dict(evidence_context or {})

    def snapshot(status: str) -> dict[str, Any]:
        golden_ok = generated[: len(GOLDEN)] == GOLDEN[: len(generated)]
        return {
            "schema": "pulsarmlx.research.glm52-inference",
            "schema_version": "2.0.0",
            "feature_id": "016-glm52-full-execution",
            "actual_status": status,
            **context,
            "mode": mode,
            "cache_policy": cache_policy if expert_cache is not None else "not_applicable",
            "decoder_mode": decoder_mode if expert_cache is not None else "not_applicable",
            "cache_budget_bytes": cache_bytes if expert_cache is not None else 0,
            "generated_token_ids": list(generated),
            "golden": GOLDEN,
            "matches_golden_prefix": golden_ok,
            "matches_golden_full": (
                generated == GOLDEN if len(generated) == len(GOLDEN) else False
            ),
            "seconds": time.perf_counter() - t_all,
            "timings": list(timings),
            "routing": list(routing),
            "expert_cache": expert_cache.stats.to_dict() if expert_cache else None,
        }

    def checkpoint_progress() -> None:
        if progress_path is not None:
            _write_json_atomic(progress_path, snapshot("in_progress"))

    execution_context = require_mlx_backend() if mode == "inference" else nullcontext()
    with execution_context:
        x: list[float] | None = None
        for pos, tid in enumerate(seed):
            before = expert_cache.stats.to_dict() if expert_cache is not None else {}
            x, stack = _run_stack(
                store,
                token_id=tid,
                position=pos,
                mode=mode,
                cache=expert_cache,
                kvs=kvs,
            )
            stack_routes = stack.pop("routes")
            record = {
                "phase": "prefill",
                "position": pos,
                "token": tid,
                **stack,
            }
            if expert_cache is not None:
                record["cache_delta"] = _stats_delta(
                    before, expert_cache.stats.to_dict()
                )
            timings.append(record)
            routing.append(
                {
                    "phase": "prefill",
                    "position": pos,
                    "token": tid,
                    "layers": stack_routes,
                }
            )
            checkpoint_progress()

        assert x is not None
        for step in range(n_new):
            logits_start = time.perf_counter()
            tid = argmax(logits_from_hidden(store, x))
            logits_seconds = time.perf_counter() - logits_start
            generated.append(tid)
            if generated != GOLDEN[: len(generated)]:
                final = snapshot("failed")
                if progress_path is not None:
                    _write_json_atomic(progress_path, final)
                return final
            position = len(seed) + step
            before = expert_cache.stats.to_dict() if expert_cache is not None else {}
            x, stack = _run_stack(
                store,
                token_id=tid,
                position=position,
                mode=mode,
                cache=expert_cache,
                kvs=kvs,
            )
            stack_routes = stack.pop("routes")
            record = {
                "phase": "decode",
                "step": step,
                "token": tid,
                "logits_seconds": logits_seconds,
                **stack,
            }
            if expert_cache is not None:
                record["cache_delta"] = _stats_delta(
                    before, expert_cache.stats.to_dict()
                )
            timings.append(record)
            routing.append(
                {
                    "phase": "decode",
                    "step": step,
                    "position": position,
                    "token": tid,
                    "layers": stack_routes,
                }
            )
            checkpoint_progress()

    golden_ok = generated[: len(GOLDEN)] == GOLDEN[: len(generated)]
    final = snapshot("passed" if golden_ok else "failed")
    if progress_path is not None:
        _write_json_atomic(progress_path, final)
    return final


def main() -> int:
    ap = argparse.ArgumentParser(description="GLM MLX/architecture inference mode")
    ap.add_argument("--mode", choices=("research", "inference"), default="inference")
    ap.add_argument("--n-new", type=int, default=1, help="new tokens (default 1 for smoke)")
    ap.add_argument("--cache-gib", type=float, default=16.0)
    ap.add_argument(
        "--cache-policy", choices=("decoded_shared_only",), default="decoded_shared_only"
    )
    ap.add_argument(
        "--decoder-mode",
        choices=MlxMatrixBackend.DECODER_MODES,
        default="scalar_reference",
    )
    ap.add_argument("--out", type=Path, default=Path("docs/research/glm52/raw/f016-inference-run.json"))
    args = ap.parse_args()

    model = os.environ.get("PULSARMLX_GLM_GGUF")
    if not model:
        raise SystemExit("PULSARMLX_GLM_GGUF is required; no model was searched or downloaded")
    source = _source_identity()
    if source["source_dirty"]:
        raise SystemExit("worktree is dirty; commit the protocol and move local artifacts first")
    before = sample_pressure().to_public_dict()
    if before["level"] in {"critical", "urgent"}:
        raise SystemExit(f"memory admission failed: {before['level']}")

    store = Glm52TensorStore(Path(model))
    try:
        result = generate(
            store,
            [9703],
            args.n_new,
            mode=args.mode,
            cache_bytes=int(args.cache_gib * 1024**3),
            cache_policy=args.cache_policy,
            decoder_mode=args.decoder_mode,
            progress_path=args.out,
            evidence_context={
                **source,
                "checkpoint": _checkpoint_identity(),
                "model_path_env": "PULSARMLX_GLM_GGUF",
                "prompt_id": "P-MIN",
                "prompt_text": "Hello",
                "prompt_token_ids": [9703],
                "requested_new_tokens": args.n_new,
                "resource_before": before,
            },
        )
    finally:
        store.close()
    print(
        json.dumps(
            {k: result[k] for k in result if k not in {"timings", "routing"}},
            indent=2,
        )
    )
    return 0 if result["matches_golden_prefix"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
