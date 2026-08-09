#!/usr/bin/env python3
"""Benchmark one complete real layer-3 attention-plus-MoE boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glm52_dense_primitives import embed_token  # noqa: E402
from glm52_expert_cache_runtime import ExpertSlabCache  # noqa: E402
from glm52_inference import (  # noqa: E402
    _checkpoint_identity,
    _source_identity,
    moe_ffn_cached,
)
from glm52_layer import layer_forward_token  # noqa: E402
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_mla import CompactKVCache, mla_forward_token  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore  # noqa: E402
from qualify_iq2_xxs_numpy import _summary  # noqa: E402

LAYER = 3
ABSOLUTE_TOLERANCE = 5e-3
RELATIVE_TOLERANCE = 5e-3
FROZEN_EXPERT_IDS = [15, 177, 233, 41, 166, 26, 10, 152]
FROZEN_MID_F32_SHA256 = "7a19b425ae8bdf0009c84daa61c80fb054bffdf5fa0f3f2291d5af87cc7832aa"


def _sha256_f32(values: list[float]) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f4").tobytes()).hexdigest()


def _comparison(reference: list[float], actual: list[float]) -> dict[str, Any]:
    ref = np.asarray(reference, dtype=np.float32).astype(np.float64)
    out = np.asarray(actual, dtype=np.float32).astype(np.float64)
    delta = out - ref
    absolute = np.abs(delta)
    allowed = ABSOLUTE_TOLERANCE + RELATIVE_TOLERANCE * np.abs(ref)
    mismatch = np.flatnonzero(absolute > allowed)
    denominator = np.maximum(np.abs(ref), 1e-12)
    ref_norm = float(np.linalg.norm(ref))
    out_norm = float(np.linalg.norm(out))
    max_index = int(np.argmax(absolute))
    return {
        "compared_count": int(ref.size),
        "absolute_tolerance": ABSOLUTE_TOLERANCE,
        "relative_tolerance": RELATIVE_TOLERANCE,
        "passed": mismatch.size == 0,
        "mismatch_count": int(mismatch.size),
        "first_mismatch": int(mismatch[0]) if mismatch.size else None,
        "first_maximum_error_index": max_index,
        "maximum_absolute_error": float(absolute[max_index]),
        "mean_absolute_error": float(np.mean(absolute)),
        "rmse": float(np.sqrt(np.mean(delta * delta))),
        "maximum_relative_error": float(np.max(absolute / denominator)),
        "cosine_similarity": float(np.dot(ref, out)) / (ref_norm * out_norm),
        "norm_ratio": out_norm / ref_norm,
    }


def _quantization_delta(
    before: dict[str, Any], after: dict[str, Any]
) -> dict[str, dict[str, int | float]]:
    result: dict[str, dict[str, int | float]] = {}
    for quantization in sorted(set(before) | set(after)):
        fields = sorted(set(before.get(quantization, {})) | set(after.get(quantization, {})))
        delta = {
            field: after.get(quantization, {}).get(field, 0)
            - before.get(quantization, {}).get(field, 0)
            for field in fields
        }
        if any(value != 0 for value in delta.values()):
            result[quantization] = delta
    return result


def _run_once(
    store: Glm52TensorStore,
    residual: list[float],
    cache: ExpertSlabCache,
) -> tuple[dict[str, Any], list[float]]:
    before_stats = cache.stats.to_dict()
    resource_before = sample_pressure().to_public_dict()
    kv = CompactKVCache()
    total_start = time.perf_counter()
    attention_start = time.perf_counter()
    mid, attention_diag = mla_forward_token(store, LAYER, residual, kv, 0)
    attention_seconds = time.perf_counter() - attention_start
    if _sha256_f32(mid) != FROZEN_MID_F32_SHA256:
        raise RuntimeError("layer-3 attention midpoint differs from the frozen hash")
    routes: list[dict[str, Any]] = []
    moe_start = time.perf_counter()
    output = moe_ffn_cached(store, cache, LAYER, mid, routes)
    moe_seconds = time.perf_counter() - moe_start
    total_seconds = time.perf_counter() - total_start
    after_stats = cache.stats.to_dict()
    scalar_fields = (
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
    delta = {
        field: after_stats[field] - before_stats[field] for field in scalar_fields
    }
    if len(routes) != 1 or routes[0]["expert_ids"] != FROZEN_EXPERT_IDS:
        raise RuntimeError("complete layer route differs from the frozen top-8")
    return {
        "decoder_mode": cache.decoder_mode,
        "total_seconds": total_seconds,
        "attention_seconds": attention_seconds,
        "moe_seconds": moe_seconds,
        "boundary_overhead_seconds": max(
            0.0, total_seconds - attention_seconds - moe_seconds
        ),
        "mid_f32_sha256": _sha256_f32(mid),
        "output_f32_sha256": _sha256_f32(output),
        "attention_diag": attention_diag,
        "route": routes[0],
        "storage_read_count": delta["storage_read_count"],
        "storage_bytes_read": delta["storage_bytes_read"],
        "storage_read_seconds": delta["storage_read_seconds"],
        "dequant_seconds": delta["dequant_seconds"],
        "contiguous_buffer_seconds": delta["contiguous_buffer_seconds"],
        "mlx_matrix_build_eval_seconds": delta["mlx_matrix_build_seconds"],
        "mlx_matvec_count": delta["mlx_matvec_count"],
        "mlx_matvec_seconds": delta["mlx_matvec_seconds"],
        "transient_releases": delta["transient_releases"],
        "decoded_cache_hits": delta["decoded_cache_hits"],
        "decoded_cache_misses": delta["decoded_cache_misses"],
        "decoded_bytes_avoided": delta["decoded_bytes_avoided"],
        "storage_bytes_avoided": delta["storage_bytes_avoided"],
        "resident_entries_end": after_stats["resident_entries"],
        "bytes_resident_end": after_stats["bytes_resident"],
        "quantization_metrics": _quantization_delta(
            before_stats["quantization_metrics"],
            after_stats["quantization_metrics"],
        ),
        "resource_before": resource_before,
        "resource_after": sample_pressure().to_public_dict(),
    }, output


def _summaries(samples: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "attention_seconds",
        "moe_seconds",
        "storage_read_seconds",
        "dequant_seconds",
        "contiguous_buffer_seconds",
        "mlx_matrix_build_eval_seconds",
        "mlx_matvec_seconds",
        "boundary_overhead_seconds",
        "total_seconds",
    )
    return {
        field: _summary([float(sample[field]) for sample in samples])
        for field in fields
    }


def benchmark(model: Path) -> dict[str, Any]:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before the layer benchmark")
    resource_before = sample_pressure().to_public_dict()
    if resource_before["level"] in {"critical", "urgent"}:
        raise RuntimeError(f"memory admission failed: {resource_before['level']}")
    store = Glm52TensorStore(model)
    try:
        residual = embed_token(store, 9703)
        oracle_outputs: list[list[float]] = []
        oracle_routes: list[list[int]] = []
        oracle_seconds: list[float] = []
        for _ in range(2):
            start = time.perf_counter()
            output, diag = layer_forward_token(
                store, LAYER, residual, CompactKVCache(), 0
            )
            oracle_seconds.append(time.perf_counter() - start)
            oracle_outputs.append(output)
            oracle_routes.append(list(diag["route"]["expert_ids"]))
        oracle_hashes = [_sha256_f32(output) for output in oracle_outputs]

        caches = {
            mode: ExpertSlabCache(
                max_bytes=16 * 1024**3,
                policy="decoded_shared_only",
                decoder_mode=mode,
            )
            for mode in ("scalar_reference", "numpy_vectorized")
        }
        first_vector, _ = _run_once(
            store, residual, caches["numpy_vectorized"]
        )
        for _ in range(3):
            _run_once(store, residual, caches["scalar_reference"])
            _run_once(store, residual, caches["numpy_vectorized"])

        measured: dict[str, list[dict[str, Any]]] = {
            "scalar_reference": [],
            "numpy_vectorized": [],
        }
        final_outputs: dict[str, list[float]] = {}
        for index in range(10):
            order = (
                "numpy_vectorized",
                "scalar_reference",
            ) if index % 2 == 0 else (
                "scalar_reference",
                "numpy_vectorized",
            )
            for mode in order:
                sample, output = _run_once(store, residual, caches[mode])
                sample["sample_index"] = index
                measured[mode].append(sample)
                final_outputs[mode] = output

        oracle_comparison = _comparison(
            oracle_outputs[0], final_outputs["numpy_vectorized"]
        )
        scalar_bits = np.asarray(
            final_outputs["scalar_reference"], dtype=np.float32
        ).view(np.uint32)
        vector_bits = np.asarray(
            final_outputs["numpy_vectorized"], dtype=np.float32
        ).view(np.uint32)
        mode_mismatch = np.flatnonzero(scalar_bits != vector_bits)
        deterministic = {
            mode: len({sample["output_f32_sha256"] for sample in samples}) == 1
            for mode, samples in measured.items()
        }
        exact_mode_hash = (
            measured["scalar_reference"][0]["output_f32_sha256"]
            == measured["numpy_vectorized"][0]["output_f32_sha256"]
            == first_vector["output_f32_sha256"]
        )
        pass_gate = (
            len(set(oracle_hashes)) == 1
            and oracle_routes == [FROZEN_EXPERT_IDS, FROZEN_EXPERT_IDS]
            and oracle_comparison["passed"]
            and mode_mismatch.size == 0
            and all(deterministic.values())
            and exact_mode_hash
            and all(
                sample["decoded_cache_hits"] == 3
                and sample["resident_entries_end"] == 3
                and sample["mid_f32_sha256"] == FROZEN_MID_F32_SHA256
                for samples in measured.values()
                for sample in samples
            )
        )
        disk = shutil.disk_usage(model)
        record = {
            "schema": "pulsarmlx.research.glm52-layer-benchmark",
            "schema_version": "1.0.0",
            "feature_id": "016-glm52-full-execution",
            "actual_status": "passed" if pass_gate else "failed",
            **source,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "checkpoint": _checkpoint_identity(),
            "machine": {
                "architecture": platform.machine(),
                "chip": subprocess.check_output(
                    ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
                ).strip(),
                "macos": platform.mac_ver()[0],
                "logical_cpu_count": os.cpu_count(),
                "load_average_1m_5m_15m": list(os.getloadavg()),
                "python_version": platform.python_version(),
                "numpy_version": np.__version__,
                "storage_role": "internal_ssd",
                "storage_free_gib": round(disk.free / 1024**3, 1),
            },
            "boundary": {
                "layer": LAYER,
                "position": 0,
                "residual_identity": "token_embedding[9703]",
                "residual_f32_sha256": _sha256_f32(residual),
                "attention_mid_f32_sha256": FROZEN_MID_F32_SHA256,
                "selected_expert_ids": FROZEN_EXPERT_IDS,
                "includes_attention": True,
                "includes_moe": True,
                "includes_residual_updates": True,
            },
            "protocol": {
                "architecture_reference_repetitions": 2,
                "process_first_vector_samples": 1,
                "warmups_per_mode": 3,
                "measured_samples_per_mode": 10,
                "measurement_order": "counterbalanced_alternation_after_warmups",
                "shared_cache_policy": "decoded_shared_only",
                "shared_cache_budget_bytes": 16 * 1024**3,
                "measured_cache_state": "shared_expert_warm",
                "timer": "time.perf_counter",
                "mlx_eval_synchronized": True,
                "os_page_cache_controlled": False,
            },
            "architecture_reference": {
                "implementation": "glm52_layer.layer_forward_token scalar expert path",
                "independence_limitation": "attention dense matvec may use the shared MLX reference helper",
                "raw_seconds": oracle_seconds,
                "route_expert_ids": oracle_routes,
                "output_f32_sha256": oracle_hashes,
                "deterministic": len(set(oracle_hashes)) == 1,
            },
            "process_first_vector": first_vector,
            "samples": measured,
            "summaries": {
                mode: _summaries(samples) for mode, samples in measured.items()
            },
            "reference_comparison": oracle_comparison,
            "mode_bit_comparison": {
                "compared_count": int(scalar_bits.size),
                "exact_f32_bits": mode_mismatch.size == 0,
                "mismatch_count": int(mode_mismatch.size),
                "first_mismatch": int(mode_mismatch[0]) if mode_mismatch.size else None,
            },
            "deterministic_outputs": deterministic,
            "exact_output_hash_across_modes": exact_mode_hash,
            "resource_before": resource_before,
            "resource_after": sample_pressure().to_public_dict(),
            "unsupported_interpretations": [
                "independent CPU oracle for the complete attention path",
                "full-stack or token-generation speedup",
                "controlled process-cold storage latency",
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
    result = benchmark(Path(model))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(
        json.dumps(
            {
                "actual_status": result["actual_status"],
                "reference_passed": result["reference_comparison"]["passed"],
                "vector_total_median_seconds": result["summaries"]["numpy_vectorized"]["total_seconds"]["median_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
