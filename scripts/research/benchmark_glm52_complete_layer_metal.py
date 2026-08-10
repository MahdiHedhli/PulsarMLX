#!/usr/bin/env python3
"""Benchmark a complete layer-3 boundary with direct routed IQ2 gate/up."""

from __future__ import annotations

import argparse
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

from benchmark_glm52_moe_metal import (  # noqa: E402
    _direct_run_once,
    _summaries as direct_moe_summaries,
)
from benchmark_glm52_moe_profile import _nonnegative_summary  # noqa: E402
from f018_numerical_contract import (  # noqa: E402
    CLASS_NUMERICALLY_FAILED,
    classify_boundary,
)
from glm52_dense_primitives import (  # noqa: E402
    capture_dense_metrics,
    dense_read_mode,
    embed_token,
    require_mlx_backend,
)
from glm52_direct_metal_runtime import DirectIq2MetalWorker  # noqa: E402
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

ROOT = Path(__file__).resolve().parents[2]
LAYER = 3
TOKEN_ID = 9703
DENSE_MODE = "whole_matrix_numpy_q5_q8_q6_head_numpy"
WARMUPS = 3
MEASURED = 10
HISTORICAL_REFERENCE = (
    ROOT / "docs/research/glm52/raw/post-f016-moe-stage-profile-0001.json"
)


def _sha(values: list[float]) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f4").tobytes()).hexdigest()


def _historical_layer3() -> dict[str, Any]:
    evidence = json.loads(HISTORICAL_REFERENCE.read_text())
    layers = [layer for layer in evidence.get("layers", []) if layer.get("layer") == LAYER]
    if len(layers) != 1 or not layers[0].get("reference_output_f32_sha256"):
        raise ValueError("committed historical layer-3 reference is missing or ambiguous")
    return layers[0]


def _reference_run(
    store: Glm52TensorStore,
    embedding: list[float],
    cache: ExpertSlabCache,
) -> tuple[dict[str, Any], list[float]]:
    resource_before = sample_pressure().to_public_dict()
    with require_mlx_backend(), dense_read_mode(DENSE_MODE), capture_dense_metrics() as dense:
        total_start = time.perf_counter()
        attention_start = time.perf_counter()
        midpoint, attention_diag = mla_forward_token(
            store, LAYER, embedding, CompactKVCache(), 0
        )
        attention_seconds = time.perf_counter() - attention_start
        routes: list[dict[str, Any]] = []
        moe_start = time.perf_counter()
        output = moe_ffn_cached(store, cache, LAYER, midpoint, routes)
        moe_seconds = time.perf_counter() - moe_start
        total_seconds = time.perf_counter() - total_start
    if len(routes) != 1 or len(routes[0]["expert_ids"]) != 8:
        raise RuntimeError("complete-layer reference did not retain one top-8 route")
    dense_record = dense.to_dict()
    return {
        "total_seconds": total_seconds,
        "attention_seconds": attention_seconds,
        "moe_seconds": moe_seconds,
        "boundary_overhead_seconds": max(0.0, total_seconds - attention_seconds - moe_seconds),
        "dense_total_seconds": float(dense_record["totals"]["total_seconds"]),
        "dense_storage_seconds": float(dense_record["totals"]["storage_read_seconds"]),
        "dense_dequant_seconds": float(dense_record["totals"]["dequant_seconds"]),
        "dense_buffer_seconds": float(dense_record["totals"]["contiguous_buffer_seconds"]),
        "dense_build_seconds": float(dense_record["totals"]["mlx_matrix_build_seconds"]),
        "dense_matvec_seconds": float(dense_record["totals"]["mlx_matvec_seconds"]),
        "midpoint_f32_sha256": _sha(midpoint),
        "output_f32_sha256": _sha(output),
        "route": routes[0],
        "attention_diag": attention_diag,
        "resource_before": resource_before,
        "resource_after": sample_pressure().to_public_dict(),
    }, output


def _direct_run(
    store: Glm52TensorStore,
    embedding: list[float],
    cache: ExpertSlabCache,
    worker: DirectIq2MetalWorker,
    expected_expert_ids: list[int],
) -> tuple[dict[str, Any], list[float]]:
    resource_before = sample_pressure().to_public_dict()
    with require_mlx_backend(), dense_read_mode(DENSE_MODE), capture_dense_metrics() as dense:
        total_start = time.perf_counter()
        attention_start = time.perf_counter()
        midpoint, attention_diag = mla_forward_token(
            store, LAYER, embedding, CompactKVCache(), 0
        )
        attention_seconds = time.perf_counter() - attention_start
        moe_sample, output = _direct_run_once(
            store,
            midpoint,
            cache,
            worker,
            expected_expert_ids=expected_expert_ids,
        )
        total_seconds = time.perf_counter() - total_start
    dense_record = dense.to_dict()
    return {
        "total_seconds": total_seconds,
        "attention_seconds": attention_seconds,
        "moe_seconds": moe_sample["total_seconds"],
        "boundary_overhead_seconds": max(
            0.0, total_seconds - attention_seconds - moe_sample["total_seconds"]
        ),
        "dense_total_seconds": float(dense_record["totals"]["total_seconds"]),
        "dense_storage_seconds": float(dense_record["totals"]["storage_read_seconds"]),
        "dense_dequant_seconds": float(dense_record["totals"]["dequant_seconds"]),
        "dense_buffer_seconds": float(dense_record["totals"]["contiguous_buffer_seconds"]),
        "dense_build_seconds": float(dense_record["totals"]["mlx_matrix_build_seconds"]),
        "dense_matvec_seconds": float(dense_record["totals"]["mlx_matvec_seconds"]),
        "midpoint_f32_sha256": _sha(midpoint),
        "output_f32_sha256": _sha(output),
        "route": moe_sample["route"],
        "attention_diag": attention_diag,
        "moe": moe_sample,
        "resource_before": resource_before,
        "resource_after": sample_pressure().to_public_dict(),
    }, output


def _layer_summaries(samples: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "total_seconds",
        "attention_seconds",
        "moe_seconds",
        "boundary_overhead_seconds",
        "dense_total_seconds",
        "dense_storage_seconds",
        "dense_dequant_seconds",
        "dense_buffer_seconds",
        "dense_build_seconds",
        "dense_matvec_seconds",
    )
    return {
        field: _nonnegative_summary([float(sample[field]) for sample in samples])
        for field in fields
    }


def benchmark(model: Path, worker_path: Path) -> dict[str, Any]:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before complete-layer measurement")
    resource_before = sample_pressure().to_public_dict()
    if resource_before["level"] != "normal":
        raise RuntimeError("complete-layer admission requires normal memory pressure")
    store = Glm52TensorStore(model)
    try:
        embedding = embed_token(store, TOKEN_ID)
        reference_cache = ExpertSlabCache(
            max_bytes=16 * 1024**3,
            policy="decoded_shared_only",
            decoder_mode="numpy_vectorized",
        )
        process_first_reference, _ = _reference_run(store, embedding, reference_cache)
        expected_expert_ids = list(process_first_reference["route"]["expert_ids"])
        for _ in range(WARMUPS):
            _reference_run(store, embedding, reference_cache)
        reference_samples: list[dict[str, Any]] = []
        reference_outputs: list[list[float]] = []
        for index in range(MEASURED):
            sample, output = _reference_run(store, embedding, reference_cache)
            sample["sample_index"] = index
            reference_samples.append(sample)
            reference_outputs.append(output)

        direct_cache = ExpertSlabCache(
            max_bytes=16 * 1024**3,
            policy="decoded_shared_only",
            decoder_mode="numpy_vectorized",
            capture_events=True,
        )
        with DirectIq2MetalWorker(worker_path, source["source_commit"]) as worker:
            process_first_direct, process_first_output = _direct_run(
                store, embedding, direct_cache, worker, expected_expert_ids
            )
            direct_warmups = []
            for _ in range(WARMUPS):
                sample, _ = _direct_run(
                    store, embedding, direct_cache, worker, expected_expert_ids
                )
                direct_warmups.append(sample)
            direct_samples: list[dict[str, Any]] = []
            direct_outputs: list[list[float]] = []
            for index in range(MEASURED):
                sample, output = _direct_run(
                    store, embedding, direct_cache, worker, expected_expert_ids
                )
                sample["sample_index"] = index
                direct_samples.append(sample)
                direct_outputs.append(output)
            worker_identity = dict(worker.identity)

        reference_hashes = {_sha(output) for output in reference_outputs}
        direct_hashes = {_sha(output) for output in direct_outputs}
        midpoint_hashes = {
            sample["midpoint_f32_sha256"]
            for sample in reference_samples + direct_samples
        }
        numerical = classify_boundary(
            reference=reference_outputs[0],
            candidate=direct_outputs[0],
            boundary="composed",
            reference_argmax=None,
            candidate_argmax=None,
            identity_matches=len(midpoint_hashes) == 1,
            routes_match=all(
                sample["route"]["expert_ids"] == expected_expert_ids
                for sample in direct_samples
            ),
            deterministic=len(direct_hashes) == 1,
            cpu_fallback_count=sum(
                int(sample["moe"]["direct_iq2"]["cpu_fallback_count"])
                for sample in direct_samples
            ),
            complete_f32_weight_materialized_bytes=sum(
                int(
                    sample["moe"]["direct_iq2"][
                        "complete_f32_weight_materialized_bytes"
                    ]
                )
                for sample in direct_samples
            ),
        )
        historical_layer = _historical_layer3()
        historical_reference_hash = historical_layer["reference_output_f32_sha256"]
        reference_hash = next(iter(reference_hashes))
        historical_hash_match = reference_hash == historical_reference_hash
        resource_after = sample_pressure().to_public_dict()
        passed = (
            len(reference_hashes) == 1
            and len(direct_hashes) == 1
            and len(midpoint_hashes) == 1
            and historical_hash_match
            and numerical["classification"] != CLASS_NUMERICALLY_FAILED
            and all(sample["resource_after"]["level"] == "normal" for sample in direct_samples)
            and resource_after["level"] == "normal"
        )
        record = {
            "schema": "pulsarmlx.research.f018-direct-iq2-complete-layer",
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
                "input_token_id": TOKEN_ID,
                "input_identity": "token_embedding[9703]",
                "input_sha256": _sha(embedding),
                "midpoint_sha256": next(iter(midpoint_hashes)),
                "expert_ids": expected_expert_ids,
                "reference_output_sha256": reference_hash,
                "historical_reference_evidence": "docs/research/glm52/raw/post-f016-moe-stage-profile-0001.json",
                "historical_reference_output_sha256": historical_reference_hash,
                "historical_reference_hash_match": historical_hash_match,
            },
            "worker": {
                "source_commit": worker_identity["source_commit"],
                "compilation_seconds": worker_identity["compilation_seconds"],
                "max_resident_matrices": worker_identity["max_resident_matrices"],
            },
            "protocol": {
                "dense_mode": DENSE_MODE,
                "optimized_reference_process_first": 1,
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
            "process_first_reference": process_first_reference,
            "optimized_reference": {
                "samples": reference_samples,
                "summaries": _layer_summaries(reference_samples),
                "output_sha256": reference_hash,
            },
            "process_first_direct": process_first_direct,
            "process_first_direct_output_sha256": _sha(process_first_output),
            "direct_warmups": direct_warmups,
            "direct_samples": direct_samples,
            "direct_summaries": {
                "layer": _layer_summaries(direct_samples),
                "moe": direct_moe_summaries([sample["moe"] for sample in direct_samples]),
            },
            "numerical_qualification": numerical,
            "resource_before": resource_before,
            "resource_after": resource_after,
            "claim_boundary": "one complete real layer-3 MLA plus top-8/shared MoE boundary",
            "unsupported_interpretations": [
                "79-layer stack, P1, P2, or token generation",
                "direct attention, IQ3_XXS, or shared-expert support",
                "general model speedup",
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
    temporary.write_text(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
    temporary.replace(args.out)
    print(
        json.dumps(
            {
                "actual_status": record["actual_status"],
                "classification": record["classification"],
                "direct_median_seconds": record["direct_summaries"]["layer"][
                    "total_seconds"
                ]["median_seconds"],
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
