#!/usr/bin/env python3
"""Benchmark one exact complete layer with the current dense and expert paths."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark_glm52_moe_profile import _exact_bits, _nonnegative_summary, stage_totals  # noqa: E402
from glm52_dense_primitives import capture_dense_metrics, dense_read_mode, embed_token, require_mlx_backend  # noqa: E402
from glm52_expert_cache_runtime import ExpertSlabCache  # noqa: E402
from glm52_inference import _checkpoint_identity, _source_identity, moe_ffn_cached  # noqa: E402
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_mla import CompactKVCache, mla_forward_token  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore  # noqa: E402

LAYER = 8
TOKEN_ID = 9703
DENSE_MODE = "whole_matrix_numpy_q5_q8_q6_head_numpy"
WARMUPS = 3
MEASURED = 10


def _sha(values: list[float]) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f4").tobytes()).hexdigest()


def _run(
    store: Glm52TensorStore,
    embedding: list[float],
    cache: ExpertSlabCache,
    *,
    capture_stages: bool,
) -> tuple[dict[str, Any], list[float]]:
    resource_before = sample_pressure().to_public_dict()
    if resource_before["level"] != "normal":
        raise RuntimeError(f"resource admission requires normal pressure, got {resource_before['level']}")
    routes: list[dict[str, Any]] = []
    detail: dict[str, Any] = {}
    with require_mlx_backend(), dense_read_mode(DENSE_MODE), capture_dense_metrics() as dense_capture:
        total_start = time.perf_counter()
        attention_start = time.perf_counter()
        midpoint, attention_diag = mla_forward_token(store, LAYER, embedding, CompactKVCache(), 0)
        attention_seconds = time.perf_counter() - attention_start
        moe_start = time.perf_counter()
        output = moe_ffn_cached(
            store,
            cache,
            LAYER,
            midpoint,
            routes,
            timing_sink=detail if capture_stages else None,
        )
        moe_seconds = time.perf_counter() - moe_start
        total_seconds = time.perf_counter() - total_start
    if len(routes) != 1 or len(routes[0]["expert_ids"]) != 8:
        raise RuntimeError("complete layer did not retain one top-8 route")
    dense = dense_capture.to_dict()
    sample = {
        "total_seconds": total_seconds,
        "attention_seconds": attention_seconds,
        "moe_seconds": moe_seconds,
        "boundary_overhead_seconds": max(0.0, total_seconds - attention_seconds - moe_seconds),
        "dense": dense,
        "dense_total_seconds": float(dense["totals"]["total_seconds"]),
        "dense_storage_seconds": float(dense["totals"]["storage_read_seconds"]),
        "dense_dequant_seconds": float(dense["totals"]["dequant_seconds"]),
        "dense_buffer_seconds": float(dense["totals"]["contiguous_buffer_seconds"]),
        "dense_build_seconds": float(dense["totals"]["mlx_matrix_build_seconds"]),
        "dense_matvec_seconds": float(dense["totals"]["mlx_matvec_seconds"]),
        "midpoint_f32_sha256": _sha(midpoint),
        "output_f32_sha256": _sha(output),
        "route": routes[0],
        "attention_diag": attention_diag,
        "resource_before": resource_before,
        "resource_after": sample_pressure().to_public_dict(),
    }
    if capture_stages:
        sample["moe_detail"] = detail
        sample["moe_stage_totals"] = stage_totals(detail)
    return sample, output


def _cleanup() -> None:
    gc.collect()
    try:
        import mlx.core as mx

        clear = getattr(mx, "clear_cache", None)
        if clear is not None:
            clear()
    except ImportError:
        pass


def _summaries(samples: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "total_seconds", "attention_seconds", "moe_seconds", "boundary_overhead_seconds",
        "dense_total_seconds", "dense_storage_seconds", "dense_dequant_seconds",
        "dense_buffer_seconds", "dense_build_seconds", "dense_matvec_seconds",
    )
    result = {field: _nonnegative_summary([float(sample[field]) for sample in samples]) for field in fields}
    for field in (
        "activation_swiglu_seconds", "weighting_seconds", "router_projection_seconds",
        "router_selection_seconds", "routed_aggregation_seconds", "shared_aggregation_seconds",
        "explicit_stage_seconds", "uninstrumented_residual_seconds",
    ):
        result[f"moe.{field}"] = _nonnegative_summary([float(sample["moe_stage_totals"][field]) for sample in samples])
    for scope in ("routed_matrix_stages", "shared_matrix_stages"):
        for field in (
            "storage_read_seconds", "dequant_seconds", "contiguous_buffer_seconds",
            "mlx_matrix_construct_seconds", "mlx_matrix_eval_seconds", "mlx_matvec_seconds", "cleanup_seconds",
        ):
            result[f"moe.{scope}.{field}"] = _nonnegative_summary([float(sample["moe_stage_totals"][scope][field]) for sample in samples])
    return result


def benchmark(model: Path) -> dict[str, Any]:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before real checkpoint measurement")
    before = sample_pressure().to_public_dict()
    if before["level"] != "normal":
        raise RuntimeError(f"resource admission requires normal pressure, got {before['level']}")
    store = Glm52TensorStore(model)
    try:
        embedding = embed_token(store, TOKEN_ID)
        reference_cache = ExpertSlabCache(max_bytes=16 * 1024**3, policy="decoded_shared_only", decoder_mode="scalar_reference")
        reference_sample, reference_output = _run(store, embedding, reference_cache, capture_stages=False)
        reference_route = reference_sample["route"]
        reference_midpoint_hash = reference_sample["midpoint_f32_sha256"]
        reference_cache.clear(); del reference_cache; _cleanup()

        cache = ExpertSlabCache(max_bytes=16 * 1024**3, policy="decoded_shared_only", decoder_mode="numpy_vectorized", capture_events=True)
        process_first, process_first_output = _run(store, embedding, cache, capture_stages=True)
        process_first_comparison = _exact_bits(reference_output, process_first_output)
        for _ in range(WARMUPS):
            _, output = _run(store, embedding, cache, capture_stages=True); del output
        measured, outputs = [], []
        for index in range(MEASURED):
            sample, output = _run(store, embedding, cache, capture_stages=True)
            sample["sample_index"] = index; measured.append(sample); outputs.append(output)
            print(json.dumps({"progress": "complete-layer-current", "measured": index + 1}), flush=True)
        comparisons = [_exact_bits(reference_output, output) for output in outputs]
        passed = (
            process_first_comparison["exact_f32_bits"]
            and all(comparison["exact_f32_bits"] for comparison in comparisons)
            and all(sample["route"]["expert_ids"] == reference_route["expert_ids"] for sample in measured)
            and all(sample["midpoint_f32_sha256"] == reference_midpoint_hash for sample in measured)
            and all(sample["resource_after"]["level"] == "normal" for sample in measured)
            and all(sample["moe_stage_totals"]["shared_matrix_hit_count"] == 3 for sample in measured)
            and cache.stats.cpu_fallbacks == 0 and cache.stats.evictions == 0
        )
        record = {
            "schema": "pulsarmlx.research.glm52-complete-layer-current",
            "schema_version": "1.0.0",
            "feature_id": "post-f016-moe-optimization",
            "experiment_id": "post-f016-complete-layer8-all-vector-0001",
            "actual_status": "passed" if passed else "failed",
            **source,
            "checkpoint": _checkpoint_identity(),
            "environment": {"machine_class": "apple_silicon_m1_ultra", "architecture": platform.machine(), "python_version": platform.python_version(), "numpy_version": np.__version__, "storage_role": "internal_ssd"},
            "protocol": {"layer": LAYER, "input_token_id": TOKEN_ID, "dense_mode": DENSE_MODE, "candidate_expert_decoder_mode": "numpy_vectorized", "untimed_reference_expert_decoder_mode": "scalar_reference", "shared_cache_policy": "decoded_shared_only", "warmups": WARMUPS, "measured_samples": MEASURED, "timer": "time.perf_counter", "mlx_synchronized": True, "os_page_cache_controlled": False},
            "reference": {"total_seconds": reference_sample["total_seconds"], "attention_seconds": reference_sample["attention_seconds"], "moe_seconds": reference_sample["moe_seconds"], "midpoint_f32_sha256": reference_midpoint_hash, "output_f32_sha256": _sha(reference_output), "route": reference_route},
            "process_first": process_first,
            "process_first_comparison": process_first_comparison,
            "measured": measured,
            "summaries": _summaries(measured),
            "cache_end": cache.stats.to_dict(),
            "resource_before": before,
            "resource_after": sample_pressure().to_public_dict(),
            "model_inference_executed": False,
            "unsupported_interpretations": ["79-layer stack, P1/P2, token-generation timing, Rust, or direct quantized Metal evidence"],
        }
        assert_public_safe(record)
        return record
    finally:
        store.close()


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--output",type=Path,required=True); args=parser.parse_args(); model=os.environ.get("PULSARMLX_GLM_GGUF")
    if not model: raise SystemExit("PULSARMLX_GLM_GGUF is required; no checkpoint was searched")
    if args.output.exists(): raise SystemExit("output already exists; refusing overwrite")
    record=benchmark(Path(model)); args.output.parent.mkdir(parents=True,exist_ok=True); temporary=args.output.with_name(f".{args.output.name}.tmp"); temporary.write_text(json.dumps(record,sort_keys=True,separators=(",", ":"))+"\n"); temporary.replace(args.output); print(json.dumps({"actual_status":record["actual_status"]},sort_keys=True)); return 0 if record["actual_status"]=="passed" else 1


if __name__=="__main__": raise SystemExit(main())
