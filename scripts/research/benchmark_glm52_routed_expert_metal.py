#!/usr/bin/env python3
"""Benchmark one routed expert with direct IQ2 gate/up and reference IQ3 down."""

from __future__ import annotations

import argparse
import json
import os
import platform
import math
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_glm52_routed_expert import (  # noqa: E402
    EXPERT,
    LAYER,
    _activation_and_route,
    _comparison,
    _run_once,
    _sha256_f32,
    _summary,
)
from f018_numerical_contract import (  # noqa: E402
    CLASS_NUMERICALLY_FAILED,
    classify_boundary,
)
from glm52_direct_metal_runtime import DirectIq2MetalWorker  # noqa: E402
from glm52_expert import run_expert_swiglu  # noqa: E402
from glm52_expert_cache_runtime import (  # noqa: E402
    ExpertSlabCache,
    run_routed_expert_direct_iq2,
)
from glm52_inference import _checkpoint_identity, _source_identity  # noqa: E402
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WARMUPS = 3
MEASURED = 10


def _nonnegative_summary(samples: list[float]) -> dict[str, float | int]:
    if not samples or any(not math.isfinite(value) or value < 0.0 for value in samples):
        raise ValueError("timing samples must be finite and nonnegative")
    ordered = sorted(samples)

    def percentile(fraction: float) -> float:
        position = (len(ordered) - 1) * fraction
        lower = int(math.floor(position))
        upper = int(math.ceil(position))
        if lower == upper:
            return ordered[lower]
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

    mean = sum(samples) / len(samples)
    standard_deviation = (
        math.sqrt(
            sum((value - mean) ** 2 for value in samples) / (len(samples) - 1)
        )
        if len(samples) > 1
        else 0.0
    )
    midpoint = len(ordered) // 2
    median = (
        ordered[midpoint]
        if len(ordered) % 2
        else (ordered[midpoint - 1] + ordered[midpoint]) / 2.0
    )
    return {
        "sample_count": len(samples),
        "median_seconds": median,
        "mean_seconds": mean,
        "standard_deviation_seconds": standard_deviation,
        "minimum_seconds": ordered[0],
        "maximum_seconds": ordered[-1],
        "p5_seconds": percentile(0.05),
        "p25_seconds": percentile(0.25),
        "p75_seconds": percentile(0.75),
        "p95_seconds": percentile(0.95),
        "coefficient_of_variation": standard_deviation / mean if mean else 0.0,
    }


def _direct_sample(
    store: Glm52TensorStore,
    worker: DirectIq2MetalWorker,
    activation: list[float],
    weight: float,
) -> tuple[dict[str, Any], list[float]]:
    cache = ExpertSlabCache(
        max_bytes=0,
        policy="decoded_shared_only",
        decoder_mode="numpy_vectorized",
        capture_events=True,
    )
    resource_before = sample_pressure().to_public_dict()
    output, detail = run_routed_expert_direct_iq2(
        store,
        cache,
        worker,
        layer=LAYER,
        expert=EXPERT,
        activation=activation,
        weight=weight,
    )
    gate = detail["gate_direct_metal"]
    up = detail["up_direct_metal"]
    down = detail["down_reference_events"]
    if len(down) != 1 or down[0]["projection"] != "down":
        raise RuntimeError("direct routed expert did not retain one reference down event")
    down = down[0]
    direct_events = (gate, up)
    return {
        "total_seconds": detail["total_seconds"],
        "output_f32_sha256": _sha256_f32(output),
        "direct_iq2": {
            "storage_read_count": sum(int(event["storage_read_count"]) for event in direct_events),
            "storage_bytes_read": sum(int(event["storage_bytes_read"]) for event in direct_events),
            "storage_read_seconds": sum(float(event["storage_read_seconds"]) for event in direct_events),
            "registration_seconds": sum(float(event["registration_seconds"]) for event in direct_events),
            "dispatch_seconds": sum(float(event["dispatch_seconds"]) for event in direct_events),
            "kernel_seconds": sum(float(event["kernel_seconds"]) for event in direct_events),
            "synchronization_seconds": sum(float(event["synchronization_seconds"]) for event in direct_events),
            "total_seconds": sum(float(event["total_seconds"]) for event in direct_events),
            "cache_hits": sum(bool(event["cache_hit"]) for event in direct_events),
            "resident_entries": max(int(event["resident_entries"]) for event in direct_events),
            "evictions": max(int(event["evictions"]) for event in direct_events),
            "cpu_fallback_count": sum(int(event["cpu_fallback_count"]) for event in direct_events),
            "complete_f32_weight_materialized_bytes": sum(
                int(event["complete_f32_weight_materialized_bytes"])
                for event in direct_events
            ),
            "events": list(direct_events),
        },
        "reference_down": down,
        "activation_swiglu_seconds": detail["activation_swiglu_seconds"],
        "weighting_seconds": detail["weighting_seconds"],
        "resource_before": resource_before,
        "resource_after": sample_pressure().to_public_dict(),
    }, output


def _direct_summaries(samples: list[dict[str, Any]]) -> dict[str, Any]:
    fields = {
        "total_seconds": [float(sample["total_seconds"]) for sample in samples],
        "activation_swiglu_seconds": [
            float(sample["activation_swiglu_seconds"]) for sample in samples
        ],
        "weighting_seconds": [float(sample["weighting_seconds"]) for sample in samples],
    }
    for scope, keys in (
        (
            "direct_iq2",
            (
                "storage_read_seconds",
                "registration_seconds",
                "dispatch_seconds",
                "kernel_seconds",
                "synchronization_seconds",
                "total_seconds",
            ),
        ),
        (
            "reference_down",
            (
                "storage_read_seconds",
                "dequant_seconds",
                "contiguous_buffer_seconds",
                "mlx_matrix_build_seconds",
                "mlx_matvec_seconds",
                "cleanup_seconds",
            ),
        ),
    ):
        for key in keys:
            fields[f"{scope}.{key}"] = [
                float(sample[scope][key]) for sample in samples
            ]
    return {name: _nonnegative_summary(values) for name, values in fields.items()}


def benchmark(model: Path, worker_path: Path) -> dict[str, Any]:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before routed-expert measurement")
    resource_before = sample_pressure().to_public_dict()
    if resource_before["level"] != "normal":
        raise RuntimeError("routed-expert admission requires normal memory pressure")
    store = Glm52TensorStore(model)
    try:
        activation, route = _activation_and_route(store)
        weight = float(route["weights"][0])
        oracle_start = time.perf_counter()
        oracle = run_expert_swiglu(
            store, LAYER, EXPERT, activation, weight, shared=False
        )
        oracle_seconds = time.perf_counter() - oracle_start

        for _ in range(WARMUPS):
            _run_once(store, activation, weight, "numpy_vectorized")
        reference_samples: list[dict[str, Any]] = []
        reference_output: list[float] | None = None
        for index in range(MEASURED):
            sample, reference_output = _run_once(
                store, activation, weight, "numpy_vectorized"
            )
            sample["sample_index"] = index
            reference_samples.append(sample)
        if reference_output is None:
            raise RuntimeError("optimized reference produced no output")
        oracle_comparison = _comparison(oracle, reference_output)

        with DirectIq2MetalWorker(worker_path, source["source_commit"]) as worker:
            process_first, process_first_output = _direct_sample(
                store, worker, activation, weight
            )
            warmups = []
            for _ in range(WARMUPS):
                sample, _ = _direct_sample(store, worker, activation, weight)
                warmups.append(sample)
            direct_samples: list[dict[str, Any]] = []
            direct_outputs: list[list[float]] = []
            for sample_index in range(MEASURED):
                sample, output = _direct_sample(store, worker, activation, weight)
                sample["sample_index"] = sample_index
                direct_samples.append(sample)
                direct_outputs.append(output)
            worker_identity = dict(worker.identity)

        direct_hashes = {_sha256_f32(output) for output in direct_outputs}
        numerical = classify_boundary(
            reference=reference_output,
            candidate=direct_outputs[0],
            boundary="composed",
            reference_argmax=None,
            candidate_argmax=None,
            identity_matches=True,
            routes_match=True,
            deterministic=len(direct_hashes) == 1,
            cpu_fallback_count=sum(
                int(sample["direct_iq2"]["cpu_fallback_count"])
                for sample in direct_samples
            ),
            complete_f32_weight_materialized_bytes=sum(
                int(sample["direct_iq2"]["complete_f32_weight_materialized_bytes"])
                for sample in direct_samples
            ),
        )
        resource_after = sample_pressure().to_public_dict()
        passed = (
            oracle_comparison["passed"]
            and numerical["classification"] != CLASS_NUMERICALLY_FAILED
            and len(direct_hashes) == 1
            and all(sample["direct_iq2"]["cache_hits"] == 2 for sample in direct_samples)
            and all(sample["direct_iq2"]["evictions"] == 0 for sample in direct_samples)
            and resource_after["level"] == "normal"
        )
        record = {
            "schema": "pulsarmlx.research.f018-direct-iq2-routed-expert",
            "schema_version": "1.0.0",
            "feature_id": "018-direct-quantized-metal-runtime",
            "actual_status": "passed" if passed else "failed",
            "classification": numerical["classification"],
            "source": {"commit": source["source_commit"], "dirty": False},
            "checkpoint": _checkpoint_identity(),
            "environment": {
                "machine_class": "apple_silicon_m1_ultra",
                "architecture": platform.machine(),
                "metal_device": worker_identity["device"],
            },
            "binding": {
                "layer": LAYER,
                "expert_id": EXPERT,
                "route_expert_ids": list(route["expert_ids"]),
                "route_weights": list(route["weights"]),
                "applied_weight": weight,
                "activation_identity": "rms_norm(token_embedding[9703], blk.3.ffn_norm.weight)",
                "activation_sha256": _sha256_f32(activation),
                "gate_tensor": f"blk.{LAYER}.ffn_gate_exps.weight",
                "up_tensor": f"blk.{LAYER}.ffn_up_exps.weight",
                "down_tensor": f"blk.{LAYER}.ffn_down_exps.weight",
                "gate_quantization": "IQ2_XXS",
                "up_quantization": "IQ2_XXS",
                "down_quantization": store.tensors[
                    f"blk.{LAYER}.ffn_down_exps.weight"
                ].type_name,
                "reference_output_sha256": _sha256_f32(reference_output),
            },
            "worker": {
                "source_commit": worker_identity["source_commit"],
                "compilation_seconds": worker_identity["compilation_seconds"],
                "max_resident_matrices": worker_identity["max_resident_matrices"],
                "ownership": "Rust-owned page-aligned stable slabs registered with newBufferWithBytesNoCopy",
            },
            "protocol": {
                "cpu_oracle_samples": 1,
                "optimized_reference_warmups": WARMUPS,
                "optimized_reference_measured": MEASURED,
                "direct_process_first": 1,
                "direct_warmups": WARMUPS,
                "direct_measured": MEASURED,
                "timer": "time.perf_counter plus Metal command telemetry",
                "mlx_synchronized": True,
                "os_page_cache_controlled": False,
            },
            "cpu_oracle": {
                "implementation": "glm52_expert.run_expert_swiglu scalar Python",
                "imports_mlx": False,
                "seconds": oracle_seconds,
                "output_sha256": _sha256_f32(oracle),
            },
            "optimized_reference": {
                "samples": reference_samples,
                "summaries": {
                    field: _summary([float(sample[field]) for sample in reference_samples])
                    for field in (
                        "storage_read_seconds",
                        "dequant_seconds",
                        "contiguous_buffer_seconds",
                        "mlx_matrix_build_eval_seconds",
                        "mlx_matvec_seconds",
                        "unattributed_activation_scale_cleanup_seconds",
                        "total_seconds",
                    )
                },
                "output_sha256": _sha256_f32(reference_output),
            },
            "oracle_comparison": oracle_comparison,
            "process_first_direct": process_first,
            "process_first_output_sha256": _sha256_f32(process_first_output),
            "direct_warmups": warmups,
            "direct_samples": direct_samples,
            "direct_summaries": _direct_summaries(direct_samples),
            "numerical_qualification": numerical,
            "resource_before": resource_before,
            "resource_after": resource_after,
            "claim_boundary": "one complete real layer-3 routed expert; direct IQ2 gate/up and reference IQ3 down",
            "unsupported_interpretations": [
                "top-8 plus shared MoE speedup",
                "complete transformer-layer speedup",
                "full-stack inference or token-generation speedup",
                "direct IQ3_XXS support",
                "production readiness",
            ],
        }
        assert_public_safe(record)
        return record
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--worker", type=Path, default=ROOT / "target/debug/iq2-metal-worker"
    )
    args = parser.parse_args()
    model = os.environ.get("PULSARMLX_GLM_GGUF")
    if not model:
        raise SystemExit("PULSARMLX_GLM_GGUF is required; checkpoint discovery is disabled")
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite existing evidence: {args.out}")
    record = benchmark(Path(model), args.worker)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_name(f".{args.out.name}.tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.out)
    print(
        json.dumps(
            {
                "actual_status": record["actual_status"],
                "classification": record["classification"],
                "direct_median_seconds": record["direct_summaries"]["total_seconds"][
                    "median_seconds"
                ],
                "optimized_median_seconds": record["optimized_reference"]["summaries"][
                    "total_seconds"
                ]["median_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0 if record["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
