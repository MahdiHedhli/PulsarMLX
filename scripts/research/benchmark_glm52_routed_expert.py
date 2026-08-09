#!/usr/bin/env python3
"""Benchmark one complete real routed expert against an independent CPU oracle."""

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

from glm52_dense_primitives import (  # noqa: E402
    embed_token,
    load_f32_vector,
    matvec_weight,
    rms_norm,
)
from glm52_expert import run_expert_swiglu  # noqa: E402
from glm52_expert_cache_runtime import ExpertSlabCache  # noqa: E402
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
from qualify_iq2_xxs_numpy import _summary  # noqa: E402

LAYER = 3
EXPERT = 15
ABSOLUTE_TOLERANCE = 5e-3
RELATIVE_TOLERANCE = 5e-3


def _sha256_f32(values: list[float]) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f4").tobytes()).hexdigest()


def _activation_and_route(store: Glm52TensorStore) -> tuple[list[float], dict[str, Any]]:
    embedded = embed_token(store, 9703)
    activation = rms_norm(
        embedded,
        load_f32_vector(store, f"blk.{LAYER}.ffn_norm.weight"),
        RMS_EPS,
    )
    logits = matvec_weight(store, f"blk.{LAYER}.ffn_gate_inp.weight", activation)
    bias = load_f32_vector(store, f"blk.{LAYER}.exp_probs_b.bias")
    route = glm_route_real(logits, bias)
    if route["expert_ids"][0] != EXPERT:
        raise RuntimeError("frozen golden route no longer selects expert 15 first")
    return activation, route


def _comparison(reference: list[float], actual: list[float]) -> dict[str, Any]:
    ref = np.asarray(reference, dtype=np.float32)
    out = np.asarray(actual, dtype=np.float32)
    delta = out.astype(np.float64) - ref.astype(np.float64)
    absolute = np.abs(delta)
    allowed = ABSOLUTE_TOLERANCE + RELATIVE_TOLERANCE * np.abs(
        ref.astype(np.float64)
    )
    mismatch = np.flatnonzero(absolute > allowed)
    denominator = np.maximum(np.abs(ref.astype(np.float64)), 1e-12)
    dot = float(np.dot(ref.astype(np.float64), out.astype(np.float64)))
    ref_norm = float(np.linalg.norm(ref.astype(np.float64)))
    out_norm = float(np.linalg.norm(out.astype(np.float64)))
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
        "cosine_similarity": dot / (ref_norm * out_norm),
        "norm_ratio": out_norm / ref_norm,
    }


def _run_once(
    store: Glm52TensorStore,
    activation: list[float],
    weight: float,
    mode: str,
) -> tuple[dict[str, Any], list[float]]:
    cache = ExpertSlabCache(
        max_bytes=0,
        policy="decoded_shared_only",
        decoder_mode=mode,
    )
    before = sample_pressure().to_public_dict()
    start = time.perf_counter()
    output = run_expert_swiglu_cached(
        store,
        cache,
        LAYER,
        EXPERT,
        activation,
        weight,
        shared=False,
    )
    total_seconds = time.perf_counter() - start
    stats = cache.stats.to_dict()
    attributed = sum(
        float(stats[field])
        for field in (
            "storage_read_seconds",
            "dequant_seconds",
            "contiguous_buffer_seconds",
            "mlx_matrix_build_seconds",
            "mlx_matvec_seconds",
        )
    )
    return {
        "decoder_mode": mode,
        "total_seconds": total_seconds,
        "unattributed_activation_scale_cleanup_seconds": max(
            0.0, total_seconds - attributed
        ),
        "output_f32_sha256": _sha256_f32(output),
        "storage_read_count": stats["storage_read_count"],
        "storage_bytes_read": stats["storage_bytes_read"],
        "storage_read_seconds": stats["storage_read_seconds"],
        "dequant_seconds": stats["dequant_seconds"],
        "contiguous_buffer_seconds": stats["contiguous_buffer_seconds"],
        "mlx_matrix_build_eval_seconds": stats["mlx_matrix_build_seconds"],
        "mlx_matvec_seconds": stats["mlx_matvec_seconds"],
        "mlx_matvec_count": stats["mlx_matvec_count"],
        "transient_releases": stats["transient_releases"],
        "quantization_metrics": stats["quantization_metrics"],
        "resource_before": before,
        "resource_after": sample_pressure().to_public_dict(),
    }, output


def _summaries(samples: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "storage_read_seconds",
        "dequant_seconds",
        "contiguous_buffer_seconds",
        "mlx_matrix_build_eval_seconds",
        "mlx_matvec_seconds",
        "unattributed_activation_scale_cleanup_seconds",
        "total_seconds",
    )
    return {
        field: _summary([float(sample[field]) for sample in samples])
        for field in fields
    }


def benchmark(model: Path) -> dict[str, Any]:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before the routed-expert benchmark")
    resource_before = sample_pressure().to_public_dict()
    if resource_before["level"] in {"critical", "urgent"}:
        raise RuntimeError(f"memory admission failed: {resource_before['level']}")
    store = Glm52TensorStore(model)
    try:
        activation, route = _activation_and_route(store)
        weight = float(route["weights"][0])
        oracle_outputs: list[list[float]] = []
        oracle_seconds: list[float] = []
        for _ in range(2):
            start = time.perf_counter()
            oracle_outputs.append(
                run_expert_swiglu(
                    store,
                    LAYER,
                    EXPERT,
                    activation,
                    weight,
                    shared=False,
                )
            )
            oracle_seconds.append(time.perf_counter() - start)
        oracle_hashes = [_sha256_f32(output) for output in oracle_outputs]

        first_vector, first_output = _run_once(
            store, activation, weight, "numpy_vectorized"
        )
        for _ in range(3):
            _run_once(store, activation, weight, "scalar_reference")
            _run_once(store, activation, weight, "numpy_vectorized")

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
                sample, output = _run_once(store, activation, weight, mode)
                sample["sample_index"] = index
                measured[mode].append(sample)
                final_outputs[mode] = output

        oracle_comparison = _comparison(oracle_outputs[0], final_outputs["numpy_vectorized"])
        mode_bit_comparison = np.asarray(
            final_outputs["scalar_reference"], dtype=np.float32
        ).view(np.uint32) == np.asarray(
            final_outputs["numpy_vectorized"], dtype=np.float32
        ).view(np.uint32)
        deterministic = {
            mode: len({sample["output_f32_sha256"] for sample in samples}) == 1
            for mode, samples in measured.items()
        }
        exact_mode_hash = (
            measured["scalar_reference"][0]["output_f32_sha256"]
            == measured["numpy_vectorized"][0]["output_f32_sha256"]
            == first_vector["output_f32_sha256"]
        )
        expected_vector_reads = 1 + 1 + 6144
        expected_scalar_reads = 2048 + 2048 + 6144
        pass_gate = (
            len(set(oracle_hashes)) == 1
            and oracle_comparison["passed"]
            and bool(np.all(mode_bit_comparison))
            and all(deterministic.values())
            and exact_mode_hash
            and first_vector["storage_read_count"] == expected_vector_reads
            and all(
                sample["storage_read_count"] == expected_vector_reads
                for sample in measured["numpy_vectorized"]
            )
            and all(
                sample["storage_read_count"] == expected_scalar_reads
                for sample in measured["scalar_reference"]
            )
        )
        disk = shutil.disk_usage(model)
        record = {
            "schema": "pulsarmlx.research.glm52-routed-expert-benchmark",
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
                "expert": EXPERT,
                "selected_expert_ids": list(route["expert_ids"]),
                "selected_weights": list(route["weights"]),
                "applied_weight": weight,
                "activation_identity": "rms_norm(token_embedding[9703], blk.3.ffn_norm.weight)",
                "activation_f32_sha256": _sha256_f32(activation),
                "tensors": [
                    {
                        "name": f"blk.{LAYER}.ffn_{projection}_exps.weight",
                        "quantization": store.tensors[
                            f"blk.{LAYER}.ffn_{projection}_exps.weight"
                        ].type_name,
                        "shard": store.tensors[
                            f"blk.{LAYER}.ffn_{projection}_exps.weight"
                        ].file.name,
                    }
                    for projection in ("gate", "up", "down")
                ],
            },
            "protocol": {
                "cpu_oracle_repetitions": 2,
                "process_first_vector_samples": 1,
                "warmups_per_mode": 3,
                "measured_samples_per_mode": 10,
                "measurement_order": "counterbalanced_alternation_after_warmups",
                "timer": "time.perf_counter",
                "mlx_eval_synchronized": True,
                "os_page_cache_controlled": False,
            },
            "cpu_oracle": {
                "implementation": "glm52_expert.run_expert_swiglu scalar Python",
                "imports_mlx": False,
                "raw_seconds": oracle_seconds,
                "output_f32_sha256": oracle_hashes,
                "deterministic": len(set(oracle_hashes)) == 1,
            },
            "process_first_vector": first_vector,
            "samples": measured,
            "summaries": {
                mode: _summaries(samples) for mode, samples in measured.items()
            },
            "oracle_comparison": oracle_comparison,
            "mode_bit_comparison": {
                "compared_count": int(mode_bit_comparison.size),
                "exact_f32_bits": bool(np.all(mode_bit_comparison)),
                "mismatch_count": int(np.count_nonzero(~mode_bit_comparison)),
            },
            "deterministic_outputs": deterministic,
            "exact_output_hash_across_modes": exact_mode_hash,
            "resource_before": resource_before,
            "resource_after": sample_pressure().to_public_dict(),
            "unsupported_interpretations": [
                "top-8 or shared MoE speedup",
                "complete transformer layer speedup",
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
                "oracle_passed": result["oracle_comparison"]["passed"],
                "vector_total_median_seconds": result["summaries"]["numpy_vectorized"]["total_seconds"]["median_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
