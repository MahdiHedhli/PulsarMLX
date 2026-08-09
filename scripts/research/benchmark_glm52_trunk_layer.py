#!/usr/bin/env python3
"""Benchmark one complete layer-8 boundary with only Q6_K dense decode changed."""

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
from typing import Any, Callable

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glm52_dense_primitives import (  # noqa: E402
    capture_dense_metrics,
    dense_read_mode,
    embed_token,
    require_mlx_backend,
)
from glm52_expert_cache_runtime import ExpertSlabCache  # noqa: E402
from glm52_inference import _checkpoint_identity, _source_identity, moe_ffn_cached  # noqa: E402
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_mla import CompactKVCache, mla_forward_token  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore  # noqa: E402
from qualify_iq2_xxs_numpy import _summary  # noqa: E402

LAYER = 8
WARMUPS = 3
MEASURED = 10
BASELINE = "whole_matrix_numpy_q5_q8_head_numpy"
CANDIDATE = "whole_matrix_numpy_q5_q8_q6_head_numpy"
MODES = (BASELINE, CANDIDATE)
FROZEN_TOKEN_ID = 9703


def _f32_bits(values: list[float]) -> np.ndarray:
    return np.asarray(values, dtype=np.float32).view(np.uint32)


def _f32_sha256(values: list[float]) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f4").tobytes()).hexdigest()


def _stats_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "storage_read_count",
        "storage_bytes_read",
        "storage_read_seconds",
        "dequant_seconds",
        "contiguous_buffer_seconds",
        "mlx_matrix_build_seconds",
        "mlx_matvec_count",
        "mlx_matvec_seconds",
        "transient_releases",
        "decoded_cache_hits",
        "decoded_cache_misses",
        "decoded_bytes_avoided",
        "storage_bytes_avoided",
    )
    return {field: after[field] - before[field] for field in fields}


def _cleanup() -> float:
    start = time.perf_counter()
    gc.collect()
    try:
        import mlx.core as mx

        clear = getattr(mx, "clear_cache", None)
        if clear is not None:
            clear()
    except ImportError:
        pass
    return time.perf_counter() - start


def _run_once(
    store: Glm52TensorStore,
    residual: list[float],
    cache: ExpertSlabCache,
    mode: str,
) -> tuple[dict[str, Any], list[float]]:
    resource_before = sample_pressure().to_public_dict()
    if resource_before["level"] in {"critical", "urgent"}:
        raise RuntimeError(f"unsafe resource pressure: {resource_before['level']}")
    cache_before = cache.stats.to_dict()
    total_start = time.perf_counter()
    routes: list[dict[str, Any]] = []
    with require_mlx_backend(), dense_read_mode(mode), capture_dense_metrics() as dense_capture:
        attention_start = time.perf_counter()
        mid, attention_diag = mla_forward_token(
            store, LAYER, residual, CompactKVCache(), 0
        )
        attention_seconds = time.perf_counter() - attention_start
        moe_start = time.perf_counter()
        output = moe_ffn_cached(store, cache, LAYER, mid, routes)
        moe_seconds = time.perf_counter() - moe_start
    total_seconds = time.perf_counter() - total_start
    cache_after = cache.stats.to_dict()
    expert = _stats_delta(cache_before, cache_after)
    dense = dense_capture.to_dict()
    if len(routes) != 1 or len(routes[0]["expert_ids"]) != 8:
        raise RuntimeError("complete layer did not retain one top-8 route")
    return {
        "dense_read_mode": mode,
        "expert_decoder_mode": cache.decoder_mode,
        "total_seconds": total_seconds,
        "attention_seconds": attention_seconds,
        "moe_seconds": moe_seconds,
        "boundary_overhead_seconds": max(0.0, total_seconds - attention_seconds - moe_seconds),
        "dense_trunk": dense,
        "dense_storage_read_count": dense["totals"]["storage_read_count"],
        "dense_encoded_bytes": dense["totals"]["encoded_bytes"],
        "dense_storage_read_seconds": dense["totals"]["storage_read_seconds"],
        "dense_dequant_seconds": dense["totals"]["dequant_seconds"],
        "dense_contiguous_buffer_seconds": dense["totals"]["contiguous_buffer_seconds"],
        "dense_mlx_matrix_build_seconds": dense["totals"]["mlx_matrix_build_seconds"],
        "dense_mlx_matvec_seconds": dense["totals"]["mlx_matvec_seconds"],
        "dense_attributed_seconds": dense["totals"]["total_seconds"],
        "expert_storage_read_count": expert["storage_read_count"],
        "expert_storage_bytes_read": expert["storage_bytes_read"],
        "expert_storage_read_seconds": expert["storage_read_seconds"],
        "expert_dequant_seconds": expert["dequant_seconds"],
        "expert_contiguous_buffer_seconds": expert["contiguous_buffer_seconds"],
        "expert_mlx_matrix_build_seconds": expert["mlx_matrix_build_seconds"],
        "expert_mlx_matvec_count": expert["mlx_matvec_count"],
        "expert_mlx_matvec_seconds": expert["mlx_matvec_seconds"],
        "expert_transient_releases": expert["transient_releases"],
        "shared_cache_hits": expert["decoded_cache_hits"],
        "shared_cache_misses": expert["decoded_cache_misses"],
        "decoded_bytes_avoided": expert["decoded_bytes_avoided"],
        "storage_bytes_avoided": expert["storage_bytes_avoided"],
        "resident_entries_end": cache_after["resident_entries"],
        "bytes_resident_end": cache_after["bytes_resident"],
        "mid_f32_sha256": _f32_sha256(mid),
        "output_f32_sha256": _f32_sha256(output),
        "route": routes[0],
        "attention_diag": attention_diag,
        "uninstrumented_residual_seconds": max(
            0.0,
            total_seconds
            - dense["totals"]["total_seconds"]
            - expert["storage_read_seconds"]
            - expert["dequant_seconds"]
            - expert["contiguous_buffer_seconds"]
            - expert["mlx_matrix_build_seconds"]
            - expert["mlx_matvec_seconds"],
        ),
        "resource_before": resource_before,
        "resource_after": sample_pressure().to_public_dict(),
    }, output


def _measure(operation: Callable[[], tuple[dict[str, Any], list[float]]]):
    sample, output = operation()
    sample["cleanup_seconds"] = _cleanup()
    sample["total_with_cleanup_seconds"] = sample["total_seconds"] + sample["cleanup_seconds"]
    return sample, output


def _summaries(samples: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "total_seconds",
        "total_with_cleanup_seconds",
        "attention_seconds",
        "moe_seconds",
        "dense_storage_read_seconds",
        "dense_dequant_seconds",
        "dense_contiguous_buffer_seconds",
        "dense_mlx_matrix_build_seconds",
        "dense_mlx_matvec_seconds",
        "dense_attributed_seconds",
        "expert_storage_read_seconds",
        "expert_dequant_seconds",
        "expert_contiguous_buffer_seconds",
        "expert_mlx_matrix_build_seconds",
        "expert_mlx_matvec_seconds",
        "boundary_overhead_seconds",
        "uninstrumented_residual_seconds",
        "cleanup_seconds",
    )
    return {field: _summary([float(sample[field]) for sample in samples]) for field in fields}


def benchmark(model: Path) -> dict[str, Any]:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before real checkpoint measurement")
    resource_before = sample_pressure().to_public_dict()
    if resource_before["level"] != "normal":
        raise RuntimeError(f"resource admission requires normal pressure, got {resource_before['level']}")
    store = Glm52TensorStore(model)
    try:
        residual = embed_token(store, FROZEN_TOKEN_ID)
        caches = {
            mode: ExpertSlabCache(
                max_bytes=16 * 1024**3,
                policy="decoded_shared_only",
                decoder_mode="numpy_vectorized",
            )
            for mode in MODES
        }
        for mode in MODES:
            for _ in range(WARMUPS):
                _, output = _measure(lambda mode=mode: _run_once(store, residual, caches[mode], mode))
                del output
        samples = {mode: [] for mode in MODES}
        outputs: dict[str, list[float]] = {}
        for index in range(MEASURED):
            order = MODES if index % 2 == 0 else tuple(reversed(MODES))
            for mode in order:
                sample, output = _measure(lambda mode=mode: _run_once(store, residual, caches[mode], mode))
                sample["sample_index"] = index
                samples[mode].append(sample)
                outputs[mode] = output
            print(json.dumps({"progress": f"complete-layer-{LAYER}", "measured_pair": index + 1}), flush=True)
        baseline_bits = _f32_bits(outputs[BASELINE])
        candidate_bits = _f32_bits(outputs[CANDIDATE])
        mismatch = np.flatnonzero(baseline_bits != candidate_bits)
        mid_hashes = {mode: sorted({sample["mid_f32_sha256"] for sample in values}) for mode, values in samples.items()}
        output_hashes = {mode: sorted({sample["output_f32_sha256"] for sample in values}) for mode, values in samples.items()}
        route_ids = {mode: sorted({tuple(sample["route"]["expert_ids"]) for sample in values}) for mode, values in samples.items()}
        passed = (
            mismatch.size == 0
            and mid_hashes[BASELINE] == mid_hashes[CANDIDATE]
            and output_hashes[BASELINE] == output_hashes[CANDIDATE]
            and route_ids[BASELINE] == route_ids[CANDIDATE]
            and all(len(values) == 1 for values in mid_hashes.values())
            and all(len(values) == 1 for values in output_hashes.values())
            and all(len(values) == 1 for values in route_ids.values())
            and all(
                sample["shared_cache_hits"] == 3
                and sample["shared_cache_misses"] == 24
                and sample["resident_entries_end"] == 3
                and sample["expert_decoder_mode"] == "numpy_vectorized"
                and sample["resource_after"]["level"] == "normal"
                for values in samples.values()
                for sample in values
            )
        )
        record = {
            "schema": "pulsarmlx.research.glm52-trunk-complete-layer",
            "schema_version": "1.0.0",
            "feature_id": "post-f016-trunk-optimization",
            "experiment_id": "trunk-complete-layer8-q6-0001",
            "actual_status": "passed" if passed else "failed",
            **source,
            "checkpoint": _checkpoint_identity(),
            "environment": {
                "machine_class": "apple_silicon_m1_ultra",
                "architecture": platform.machine(),
                "python_version": platform.python_version(),
                "numpy_version": np.__version__,
                "storage_role": "internal_ssd",
            },
            "protocol": {
                "changed_variable": "dense Q6_K scalar decode versus exact-bit whole-matrix NumPy Q6_K decode; Q5_K, Q8_0, expert decoder, cache policy, input, and arithmetic order remain fixed",
                "dense_modes": list(MODES),
                "expert_decoder_mode_both": "numpy_vectorized",
                "shared_cache_policy_both": "decoded_shared_only",
                "shared_cache_budget_bytes": 16 * 1024**3,
                "expected_shared_cache_hits_per_warm_layer": 3,
                "expected_transient_routed_matrix_misses_per_layer": 24,
                "warmups_per_mode": WARMUPS,
                "measured_samples_per_mode": MEASURED,
                "measurement_order": "counterbalanced_alternation",
                "timer": "time.perf_counter",
                "mlx_synchronized": True,
                "os_page_cache_controlled": False,
                "cleanup_after_each_sample": "gc.collect plus mlx.clear_cache when available",
            },
            "boundary": {
                "layer": LAYER,
                "position": 0,
                "input_token_id": FROZEN_TOKEN_ID,
                "input_f32_sha256": _f32_sha256(residual),
                "includes_complete_mla": True,
                "includes_top8_plus_shared_moe": True,
                "includes_residual_updates": True,
            },
            "samples": samples,
            "summaries": {mode: _summaries(values) for mode, values in samples.items()},
            "comparison": {
                "exact_f32_bits": mismatch.size == 0,
                "mismatch_count": int(mismatch.size),
                "first_mismatch": int(mismatch[0]) if mismatch.size else None,
                "mid_hashes": mid_hashes,
                "output_hashes": output_hashes,
                "route_expert_ids": {mode: [list(value) for value in values] for mode, values in route_ids.items()},
            },
            "resource_before": resource_before,
            "resource_after": sample_pressure().to_public_dict(),
            "model_inference_executed": False,
            "unsupported_interpretations": [
                "complete stack, P1, or token-generation speedup",
                "steady-state throughput",
                "Rust or direct quantized Metal evidence",
            ],
        }
        assert_public_safe(record)
        return record
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    model = os.environ.get("PULSARMLX_GLM_GGUF")
    if not model:
        raise SystemExit("PULSARMLX_GLM_GGUF is required; no checkpoint was searched")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.output}")
    result = benchmark(Path(model))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp")
    temporary.write_text(json.dumps(result, separators=(",", ":"), sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(json.dumps({
        "actual_status": result["actual_status"],
        "exact_f32_bits": result["comparison"]["exact_f32_bits"],
    }, sort_keys=True))
    return 0 if result["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
