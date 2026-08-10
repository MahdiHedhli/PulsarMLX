#!/usr/bin/env python3
"""Profile bounded real GLM MoE boundaries with opt-in stage telemetry."""

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
from typing import Any, Iterable

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glm52_dense_primitives import (  # noqa: E402
    dense_read_mode,
    embed_token,
    require_mlx_backend,
)
from glm52_expert_cache_runtime import ExpertSlabCache  # noqa: E402
from glm52_inference import (  # noqa: E402
    _checkpoint_identity,
    _source_identity,
    moe_ffn_cached,
)
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_mla import CompactKVCache, mla_forward_token  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore  # noqa: E402
from qualify_iq2_xxs_numpy import _summary  # noqa: E402

LAYERS = (3, 8, 40, 78)
WARMUPS = 3
MEASURED = 10
TOKEN_ID = 9703
DENSE_MODE = "whole_matrix_numpy_q5_q8_q6_head_numpy"
EVENT_FIELDS = (
    "storage_read_seconds",
    "dequant_seconds",
    "contiguous_buffer_seconds",
    "mlx_matrix_construct_seconds",
    "mlx_matrix_eval_seconds",
    "mlx_matvec_seconds",
    "cleanup_seconds",
)


def _f32_sha256(values: list[float]) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f4").tobytes()).hexdigest()


def _exact_bits(left: list[float], right: list[float]) -> dict[str, Any]:
    left_bits = np.asarray(left, dtype=np.float32).view(np.uint32)
    right_bits = np.asarray(right, dtype=np.float32).view(np.uint32)
    mismatch = np.flatnonzero(left_bits != right_bits)
    return {
        "compared_count": int(left_bits.size),
        "exact_f32_bits": mismatch.size == 0,
        "mismatch_count": int(mismatch.size),
        "first_mismatch": int(mismatch[0]) if mismatch.size else None,
    }


def _events(expert: dict[str, Any]) -> list[dict[str, Any]]:
    events = expert["matrix_events"]
    if len(events) != 3 or [event["projection"] for event in events] != ["gate", "up", "down"]:
        raise ValueError("expert event sequence must be gate/up/down")
    return events


def stage_totals(detail: dict[str, Any]) -> dict[str, Any]:
    routed_events = [event for expert in detail["routed_experts"] for event in _events(expert)]
    shared_events = _events(detail["shared_expert"])
    all_events = routed_events + shared_events
    routed = {field: sum(float(event[field]) for event in routed_events) for field in EVENT_FIELDS}
    shared = {field: sum(float(event[field]) for event in shared_events) for field in EVENT_FIELDS}
    activation = sum(
        float(expert["activation_swiglu_seconds"])
        for expert in detail["routed_experts"] + [detail["shared_expert"]]
    )
    weighting = sum(
        float(expert["weighting_seconds"])
        for expert in detail["routed_experts"] + [detail["shared_expert"]]
    )
    explicit = (
        sum(float(event[field]) for event in all_events for field in EVENT_FIELDS)
        + activation
        + weighting
        + float(detail["ffn_norm_seconds"])
        + float(detail["router_projection_seconds"])
        + float(detail["router_selection_seconds"])
        + float(detail["routed_aggregation_seconds"])
        + float(detail["shared_aggregation_seconds"])
        + float(detail["residual_add_seconds"])
    )
    residual = float(detail["total_seconds"]) - explicit
    if residual < -1e-6:
        raise ValueError("explicit stage timers exceed MoE boundary wall")
    return {
        "routed_matrix_stages": routed,
        "shared_matrix_stages": shared,
        "activation_swiglu_seconds": activation,
        "weighting_seconds": weighting,
        "ffn_norm_seconds": float(detail["ffn_norm_seconds"]),
        "router_projection_seconds": float(detail["router_projection_seconds"]),
        "router_selection_seconds": float(detail["router_selection_seconds"]),
        "routed_aggregation_seconds": float(detail["routed_aggregation_seconds"]),
        "shared_aggregation_seconds": float(detail["shared_aggregation_seconds"]),
        "residual_add_seconds": float(detail["residual_add_seconds"]),
        "explicit_stage_seconds": explicit,
        "uninstrumented_residual_seconds": max(0.0, residual),
        "routed_matrix_event_count": len(routed_events),
        "shared_matrix_event_count": len(shared_events),
        "shared_matrix_hit_count": sum(bool(event["cache_hit"]) for event in shared_events),
    }


def _sample(
    store: Glm52TensorStore,
    layer: int,
    residual: list[float],
    cache: ExpertSlabCache,
) -> tuple[dict[str, Any], list[float]]:
    resource_before = sample_pressure().to_public_dict()
    if resource_before["level"] != "normal":
        raise RuntimeError(f"resource admission requires normal pressure, got {resource_before['level']}")
    routes: list[dict[str, Any]] = []
    detail: dict[str, Any] = {}
    output = moe_ffn_cached(
        store,
        cache,
        layer,
        residual,
        routes,
        timing_sink=detail,
    )
    if len(routes) != 1 or len(routes[0]["expert_ids"]) != 8:
        raise RuntimeError("MoE boundary did not retain one top-8 route")
    totals = stage_totals(detail)
    return {
        "layer": layer,
        "total_seconds": float(detail["total_seconds"]),
        "route": routes[0],
        "output_f32_sha256": _f32_sha256(output),
        "detail": detail,
        "stage_totals": totals,
        "resource_before": resource_before,
        "resource_after": sample_pressure().to_public_dict(),
    }, output


def _untimed_reference(
    store: Glm52TensorStore,
    layer: int,
    residual: list[float],
) -> tuple[list[float], dict[str, Any]]:
    cache = ExpertSlabCache(
        max_bytes=16 * 1024**3,
        policy="decoded_shared_only",
        decoder_mode="numpy_vectorized",
    )
    routes: list[dict[str, Any]] = []
    output = moe_ffn_cached(store, cache, layer, residual, routes)
    if cache.capture_events or cache.event_snapshot():
        raise RuntimeError("reference path unexpectedly captured events")
    return output, routes[0]


def _summaries(samples: list[dict[str, Any]]) -> dict[str, Any]:
    fields: dict[str, list[float]] = {
        "total_seconds": [float(sample["total_seconds"]) for sample in samples],
        "activation_swiglu_seconds": [],
        "weighting_seconds": [],
        "ffn_norm_seconds": [],
        "router_projection_seconds": [],
        "router_selection_seconds": [],
        "routed_aggregation_seconds": [],
        "shared_aggregation_seconds": [],
        "residual_add_seconds": [],
        "explicit_stage_seconds": [],
        "uninstrumented_residual_seconds": [],
    }
    for scope in ("routed_matrix_stages", "shared_matrix_stages"):
        for field in EVENT_FIELDS:
            fields[f"{scope}.{field}"] = []
    for sample in samples:
        totals = sample["stage_totals"]
        for field in tuple(fields):
            if "." in field:
                scope, nested = field.split(".", 1)
                fields[field].append(float(totals[scope][nested]))
            elif field != "total_seconds":
                fields[field].append(float(totals[field]))
    return {field: _summary(values) for field, values in fields.items()}


def _cleanup() -> None:
    gc.collect()
    try:
        import mlx.core as mx

        clear = getattr(mx, "clear_cache", None)
        if clear is not None:
            clear()
    except ImportError:
        pass


def benchmark(model: Path) -> dict[str, Any]:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before real checkpoint measurement")
    resource_before = sample_pressure().to_public_dict()
    if resource_before["level"] != "normal":
        raise RuntimeError(f"resource admission requires normal pressure, got {resource_before['level']}")
    store = Glm52TensorStore(model)
    try:
        embedded = embed_token(store, TOKEN_ID)
        layer_records: list[dict[str, Any]] = []
        for layer in LAYERS:
            with require_mlx_backend(), dense_read_mode(DENSE_MODE):
                attention_start = time.perf_counter()
                residual, _ = mla_forward_token(
                    store, layer, embedded, CompactKVCache(), 0
                )
                attention_setup_seconds = time.perf_counter() - attention_start

            reference, reference_route = _untimed_reference(store, layer, residual)
            _cleanup()
            cache = ExpertSlabCache(
                max_bytes=16 * 1024**3,
                policy="decoded_shared_only",
                decoder_mode="numpy_vectorized",
                capture_events=True,
            )
            process_first, process_first_output = _sample(store, layer, residual, cache)
            process_first_comparison = _exact_bits(reference, process_first_output)
            for _ in range(WARMUPS):
                _sample(store, layer, residual, cache)
            measured: list[dict[str, Any]] = []
            outputs: list[list[float]] = []
            for index in range(MEASURED):
                sample, output = _sample(store, layer, residual, cache)
                sample["sample_index"] = index
                measured.append(sample)
                outputs.append(output)
                print(json.dumps({"progress": "moe-profile", "layer": layer, "measured": index + 1}), flush=True)
            comparisons = [_exact_bits(reference, output) for output in outputs]
            route_lists = [sample["route"]["expert_ids"] for sample in measured]
            passed = (
                process_first_comparison["exact_f32_bits"]
                and all(comparison["exact_f32_bits"] for comparison in comparisons)
                and all(route == reference_route["expert_ids"] for route in route_lists)
                and all(sample["output_f32_sha256"] == _f32_sha256(reference) for sample in measured)
                and all(sample["resource_after"]["level"] == "normal" for sample in measured)
                and all(sample["stage_totals"]["routed_matrix_event_count"] == 24 for sample in measured)
                and all(sample["stage_totals"]["shared_matrix_event_count"] == 3 for sample in measured)
                and all(sample["stage_totals"]["shared_matrix_hit_count"] == 3 for sample in measured)
                and cache.stats.cpu_fallbacks == 0
                and cache.stats.evictions == 0
            )
            layer_records.append(
                {
                    "layer": layer,
                    "actual_status": "passed" if passed else "failed",
                    "representative_residual_identity": f"layer-{layer} MLA(token_embedding[9703], position=0)",
                    "representative_residual_f32_sha256": _f32_sha256(residual),
                    "attention_setup_seconds": attention_setup_seconds,
                    "reference_output_f32_sha256": _f32_sha256(reference),
                    "reference_route": reference_route,
                    "process_first": process_first,
                    "process_first_comparison": process_first_comparison,
                    "warmups": WARMUPS,
                    "measured": measured,
                    "summaries": _summaries(measured),
                    "cache_end": cache.stats.to_dict(),
                }
            )
            cache.clear()
            del cache, reference, process_first_output, outputs, residual
            _cleanup()
        passed = all(layer["actual_status"] == "passed" for layer in layer_records)
        record = {
            "schema": "pulsarmlx.research.glm52-moe-stage-profile",
            "schema_version": "1.0.0",
            "feature_id": "post-f016-moe-optimization",
            "experiment_id": "post-f016-moe-stage-profile-0001",
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
                "layers": list(LAYERS),
                "input_token_id": TOKEN_ID,
                "representative_activation_scope": "real checkpoint MLA boundary from token embedding; not a sequential full-stack hidden state",
                "decoder_mode": "numpy_vectorized with scalar fallback for unsupported formats",
                "dense_read_mode": DENSE_MODE,
                "shared_cache_policy": "decoded_shared_only",
                "shared_cache_budget_bytes": 16 * 1024**3,
                "untimed_reference_repetitions": 1,
                "process_first_samples": 1,
                "warmups": WARMUPS,
                "measured_samples": MEASURED,
                "timer": "time.perf_counter",
                "mlx_synchronized": True,
                "os_page_cache_controlled": False,
            },
            "layers": layer_records,
            "resource_before": resource_before,
            "resource_after": sample_pressure().to_public_dict(),
            "model_inference_executed": False,
            "unsupported_interpretations": [
                "79-layer stack, P1, P2, golden-eight, or token-generation timing",
                "sequential full-stack activation timing",
                "general tokens per second",
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
    print(json.dumps({"actual_status": result["actual_status"]}, sort_keys=True))
    return 0 if result["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
