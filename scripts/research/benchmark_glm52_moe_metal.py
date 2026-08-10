#!/usr/bin/env python3
"""Benchmark layer-3 top-8 plus shared MoE with direct routed IQ2 gate/up."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_glm52_moe import (  # noqa: E402
    FROZEN_EXPERT_IDS,
    LAYER,
    _run_once as reference_run_once,
    _sha256_f32,
    _summaries as reference_summaries,
)
from benchmark_glm52_routed_expert_metal import _nonnegative_summary  # noqa: E402
from f018_numerical_contract import (  # noqa: E402
    CLASS_NUMERICALLY_FAILED,
    classify_boundary,
)
from glm52_dense_primitives import (  # noqa: E402
    embed_token,
    load_f32_vector,
    matvec_weight,
    rms_norm,
)
from glm52_direct_metal_runtime import DirectIq2MetalWorker  # noqa: E402
from glm52_expert_cache_runtime import (  # noqa: E402
    ExpertSlabCache,
    run_routed_expert_direct_iq2,
)
from glm52_inference import (  # noqa: E402
    _checkpoint_identity,
    _source_identity,
    run_expert_swiglu_cached,
)
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_mla import RMS_EPS  # noqa: E402
from glm52_router import glm_route_real  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WARMUPS = 3
MEASURED = 10


def _direct_run_once(
    store: Glm52TensorStore,
    residual: list[float],
    cache: ExpertSlabCache,
    worker: DirectIq2MetalWorker,
) -> tuple[dict[str, Any], list[float]]:
    resource_before = sample_pressure().to_public_dict()
    total_start = time.perf_counter()
    norm_start = time.perf_counter()
    activation = rms_norm(
        residual, load_f32_vector(store, f"blk.{LAYER}.ffn_norm.weight"), RMS_EPS
    )
    norm_seconds = time.perf_counter() - norm_start
    router_start = time.perf_counter()
    logits = matvec_weight(store, f"blk.{LAYER}.ffn_gate_inp.weight", activation)
    bias = load_f32_vector(store, f"blk.{LAYER}.exp_probs_b.bias")
    route = glm_route_real(logits, bias)
    router_seconds = time.perf_counter() - router_start
    if route["expert_ids"] != FROZEN_EXPERT_IDS:
        raise RuntimeError("direct MoE route differs from the frozen top-8")

    aggregate = [0.0] * len(residual)
    routed_details: list[dict[str, Any]] = []
    routed_aggregation_seconds = 0.0
    for expert_id, weight in zip(route["expert_ids"], route["weights"], strict=True):
        part, detail = run_routed_expert_direct_iq2(
            store,
            cache,
            worker,
            layer=LAYER,
            expert=int(expert_id),
            activation=activation,
            weight=float(weight),
        )
        aggregation_start = time.perf_counter()
        for index, value in enumerate(part):
            aggregate[index] += value
        routed_aggregation_seconds += time.perf_counter() - aggregation_start
        routed_details.append(detail)

    shared_event_start = len(cache.event_snapshot())
    shared_start = time.perf_counter()
    shared = run_expert_swiglu_cached(
        store,
        cache,
        LAYER,
        0,
        activation,
        1.0,
        shared=True,
    )
    shared_seconds = time.perf_counter() - shared_start
    shared_events = cache.event_snapshot()[shared_event_start:]
    if len(shared_events) != 3:
        raise RuntimeError("direct MoE must retain three shared-expert matrix events")
    shared_aggregation_start = time.perf_counter()
    for index, value in enumerate(shared):
        aggregate[index] += value
    shared_aggregation_seconds = time.perf_counter() - shared_aggregation_start
    result = [left + right for left, right in zip(residual, aggregate, strict=True)]

    direct_events = [
        detail[projection]
        for detail in routed_details
        for projection in ("gate_direct_metal", "up_direct_metal")
    ]
    down_events = [
        detail["down_reference_events"][0] for detail in routed_details
    ]
    return {
        "total_seconds": time.perf_counter() - total_start,
        "output_f32_sha256": _sha256_f32(result),
        "route": {
            "expert_ids": list(route["expert_ids"]),
            "weights": list(route["weights"]),
            "shared_expert": 0,
        },
        "ffn_norm_seconds": norm_seconds,
        "router_seconds": router_seconds,
        "direct_iq2": {
            "matrix_count": len(direct_events),
            "storage_read_count": sum(int(event["storage_read_count"]) for event in direct_events),
            "storage_bytes_read": sum(int(event["storage_bytes_read"]) for event in direct_events),
            "storage_read_seconds": sum(float(event["storage_read_seconds"]) for event in direct_events),
            "registration_seconds": sum(float(event["registration_seconds"]) for event in direct_events),
            "dispatch_seconds": sum(float(event["dispatch_seconds"]) for event in direct_events),
            "kernel_seconds": sum(float(event["kernel_seconds"]) for event in direct_events),
            "synchronization_seconds": sum(float(event["synchronization_seconds"]) for event in direct_events),
            "total_seconds": sum(float(event["total_seconds"]) for event in direct_events),
            "cache_hits": sum(bool(event["cache_hit"]) for event in direct_events),
            "resident_entries_end": int(direct_events[-1]["resident_entries"]),
            "evictions_cumulative_end": int(direct_events[-1]["evictions"]),
            "cpu_fallback_count": sum(int(event["cpu_fallback_count"]) for event in direct_events),
            "complete_f32_weight_materialized_bytes": sum(
                int(event["complete_f32_weight_materialized_bytes"])
                for event in direct_events
            ),
            "events": direct_events,
        },
        "routed_down_reference": {
            "matrix_count": len(down_events),
            **{
                field: sum(float(event[field]) for event in down_events)
                for field in (
                    "storage_read_seconds",
                    "dequant_seconds",
                    "contiguous_buffer_seconds",
                    "mlx_matrix_build_seconds",
                    "mlx_matvec_seconds",
                    "cleanup_seconds",
                )
            },
        },
        "routed_activation_seconds": sum(
            float(detail["activation_swiglu_seconds"]) for detail in routed_details
        ),
        "routed_weighting_seconds": sum(
            float(detail["weighting_seconds"]) for detail in routed_details
        ),
        "routed_aggregation_seconds": routed_aggregation_seconds,
        "shared_reference": {
            "total_seconds": shared_seconds,
            "cache_hits": sum(bool(event["cache_hit"]) for event in shared_events),
            "events": shared_events,
        },
        "shared_aggregation_seconds": shared_aggregation_seconds,
        "resource_before": resource_before,
        "resource_after": sample_pressure().to_public_dict(),
    }, result


def _summaries(samples: list[dict[str, Any]]) -> dict[str, Any]:
    fields: dict[str, list[float]] = {
        field: [float(sample[field]) for sample in samples]
        for field in (
            "total_seconds",
            "ffn_norm_seconds",
            "router_seconds",
            "routed_activation_seconds",
            "routed_weighting_seconds",
            "routed_aggregation_seconds",
            "shared_aggregation_seconds",
        )
    }
    for scope, nested in (
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
            "routed_down_reference",
            (
                "storage_read_seconds",
                "dequant_seconds",
                "contiguous_buffer_seconds",
                "mlx_matrix_build_seconds",
                "mlx_matvec_seconds",
                "cleanup_seconds",
            ),
        ),
        ("shared_reference", ("total_seconds",)),
    ):
        for field in nested:
            fields[f"{scope}.{field}"] = [
                float(sample[scope][field]) for sample in samples
            ]
    return {name: _nonnegative_summary(values) for name, values in fields.items()}


def benchmark(model: Path, worker_path: Path) -> dict[str, Any]:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before top-8 direct-Metal measurement")
    resource_before = sample_pressure().to_public_dict()
    if resource_before["level"] != "normal":
        raise RuntimeError("top-8 direct-Metal admission requires normal memory pressure")
    store = Glm52TensorStore(model)
    try:
        residual = embed_token(store, 9703)
        reference_cache = ExpertSlabCache(
            max_bytes=16 * 1024**3,
            policy="decoded_shared_only",
            decoder_mode="numpy_vectorized",
        )
        reference_run_once(store, residual, reference_cache)
        for _ in range(WARMUPS):
            reference_run_once(store, residual, reference_cache)
        reference_samples: list[dict[str, Any]] = []
        reference_output: list[float] | None = None
        for index in range(MEASURED):
            sample, reference_output = reference_run_once(
                store, residual, reference_cache
            )
            sample["sample_index"] = index
            reference_samples.append(sample)
        if reference_output is None:
            raise RuntimeError("top-8 reference produced no output")

        direct_cache = ExpertSlabCache(
            max_bytes=16 * 1024**3,
            policy="decoded_shared_only",
            decoder_mode="numpy_vectorized",
            capture_events=True,
        )
        with DirectIq2MetalWorker(worker_path, source["source_commit"]) as worker:
            process_first, process_first_output = _direct_run_once(
                store, residual, direct_cache, worker
            )
            warmups = []
            for _ in range(WARMUPS):
                sample, _ = _direct_run_once(store, residual, direct_cache, worker)
                warmups.append(sample)
            direct_samples: list[dict[str, Any]] = []
            direct_outputs: list[list[float]] = []
            for index in range(MEASURED):
                sample, output = _direct_run_once(
                    store, residual, direct_cache, worker
                )
                sample["sample_index"] = index
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
            routes_match=all(
                sample["route"]["expert_ids"] == FROZEN_EXPERT_IDS
                for sample in direct_samples
            ),
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
        prior = json.loads(
            (ROOT / "docs/research/glm52/raw/f016-moe-layer3-iq3-0001.json").read_text()
        )
        prior_hash = prior["samples"]["numpy_vectorized"][0]["output_f32_sha256"]
        reference_hash = _sha256_f32(reference_output)
        historical_hash_match = reference_hash == prior_hash
        resource_after = sample_pressure().to_public_dict()
        passed = (
            numerical["classification"] != CLASS_NUMERICALLY_FAILED
            and len(direct_hashes) == 1
            and historical_hash_match
            and all(sample["shared_reference"]["cache_hits"] == 3 for sample in direct_samples)
            and all(sample["direct_iq2"]["matrix_count"] == 16 for sample in direct_samples)
            and resource_after["level"] == "normal"
        )
        record = {
            "schema": "pulsarmlx.research.f018-direct-iq2-moe",
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
                "residual_identity": "token_embedding[9703]",
                "residual_sha256": _sha256_f32(residual),
                "expert_ids": FROZEN_EXPERT_IDS,
                "shared_expert": 0,
                "reference_output_sha256": reference_hash,
                "historical_reference_evidence": "docs/research/glm52/raw/f016-moe-layer3-iq3-0001.json",
                "historical_reference_output_sha256": prior_hash,
                "historical_reference_hash_match": historical_hash_match,
            },
            "worker": {
                "source_commit": worker_identity["source_commit"],
                "compilation_seconds": worker_identity["compilation_seconds"],
                "max_resident_matrices": worker_identity["max_resident_matrices"],
            },
            "protocol": {
                "optimized_reference_warmups": WARMUPS,
                "optimized_reference_measured": MEASURED,
                "direct_process_first": 1,
                "direct_warmups": WARMUPS,
                "direct_measured": MEASURED,
                "shared_cache_policy": "decoded_shared_only",
                "shared_cache_budget_bytes": 16 * 1024**3,
                "direct_compressed_slot_limit": 2,
                "mlx_synchronized": True,
                "os_page_cache_controlled": False,
            },
            "optimized_reference": {
                "samples": reference_samples,
                "summaries": reference_summaries(reference_samples),
                "output_sha256": reference_hash,
            },
            "process_first_direct": process_first,
            "process_first_output_sha256": _sha256_f32(process_first_output),
            "direct_warmups": warmups,
            "direct_samples": direct_samples,
            "direct_summaries": _summaries(direct_samples),
            "numerical_qualification": numerical,
            "resource_before": resource_before,
            "resource_after": resource_after,
            "claim_boundary": "one real layer-3 top-8 plus shared MoE boundary",
            "unsupported_interpretations": [
                "complete transformer-layer speedup",
                "full-stack inference or token-generation speedup",
                "steady routed-residency benefit",
                "direct IQ3_XXS or shared-expert support",
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
