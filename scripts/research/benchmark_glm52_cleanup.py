#!/usr/bin/env python3
"""Measure current versus safely batched cleanup on a retained Q6_K matrix."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import platform
import sys
import time
from importlib.metadata import version
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_glm52_trunk_residency import _summary_nonnegative  # noqa: E402
from ggml_kquants import dequantize_matrix_q6_k_numpy  # noqa: E402
from glm52_inference import _checkpoint_identity, _source_identity  # noqa: E402
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore  # noqa: E402

TENSOR = "blk.8.attn_output.weight"
WARMUPS = 5
MEASURED = 30
BATCH_SIZE = 5


def _cleanup() -> float:
    import mlx.core as mx

    start = time.perf_counter()
    gc.collect()
    clear = getattr(mx, "clear_cache", None)
    if clear is not None:
        clear()
    return time.perf_counter() - start


def _matvec(matrix, activation):
    import mlx.core as mx

    start = time.perf_counter()
    output = matrix @ activation
    mx.eval(output)
    values = np.asarray(output, dtype=np.float32)
    elapsed = time.perf_counter() - start
    digest = hashlib.sha256(values.astype("<f4", copy=False).tobytes()).hexdigest()
    del output, values
    return elapsed, digest


def benchmark(model: Path) -> dict:
    import mlx.core as mx

    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before cleanup measurement")
    resource_before = sample_pressure().to_public_dict()
    if resource_before["level"] != "normal":
        raise RuntimeError(f"resource admission requires normal pressure, got {resource_before['level']}")
    store = Glm52TensorStore(model)
    try:
        loc = store.tensors[TENSOR]
        cols, rows = map(int, loc.dims)
        raw = store.pread(TENSOR, 0, loc.n_bytes)
        if len(raw) != loc.n_bytes:
            raise OSError("truncated complete Q6_K matrix")
        decoded = dequantize_matrix_q6_k_numpy(raw, rows, cols)
        matrix = mx.array(decoded, dtype=mx.float32).reshape((rows, cols))
        activation = mx.array(
            [math.sin(index * 0.0019) * 0.25 for index in range(cols)],
            dtype=mx.float32,
        )
        mx.eval(matrix, activation)
        del decoded, raw
        resource_after_setup = sample_pressure().to_public_dict()

        for _ in range(WARMUPS):
            _cleanup()
        cleanup_only = [_cleanup() for _ in range(MEASURED)]

        for _ in range(WARMUPS):
            _matvec(matrix, activation)
            _cleanup()
        current_samples = []
        current_hashes = []
        for index in range(MEASURED):
            total_start = time.perf_counter()
            matvec_seconds, digest = _matvec(matrix, activation)
            cleanup_seconds = _cleanup()
            current_samples.append({
                "sample_index": index,
                "matvec_seconds": matvec_seconds,
                "cleanup_seconds": cleanup_seconds,
                "total_seconds": time.perf_counter() - total_start,
                "resource_after": sample_pressure().to_public_dict(),
            })
            current_hashes.append(digest)

        for _ in range(WARMUPS):
            _matvec(matrix, activation)
        _cleanup()
        batched_samples = []
        batched_hashes = []
        cleanup_events = []
        batch_start = time.perf_counter()
        for index in range(MEASURED):
            operation_start = time.perf_counter()
            matvec_seconds, digest = _matvec(matrix, activation)
            cleanup_seconds = 0.0
            if (index + 1) % BATCH_SIZE == 0:
                cleanup_seconds = _cleanup()
                cleanup_events.append(cleanup_seconds)
            batched_samples.append({
                "sample_index": index,
                "matvec_seconds": matvec_seconds,
                "cleanup_seconds": cleanup_seconds,
                "total_seconds": time.perf_counter() - operation_start,
                "resource_after": sample_pressure().to_public_dict(),
            })
            batched_hashes.append(digest)
        batched_population_wall = time.perf_counter() - batch_start
        resource_after = sample_pressure().to_public_dict()
        hashes = sorted(set(current_hashes + batched_hashes))
        passed = (
            len(hashes) == 1
            and len(cleanup_events) == MEASURED // BATCH_SIZE
            and all(sample["resource_after"]["level"] == "normal" for sample in current_samples + batched_samples)
            and resource_after["level"] == "normal"
        )
        fields = ("matvec_seconds", "cleanup_seconds", "total_seconds")
        return {
            "schema": "pulsarmlx.research.glm52-cleanup-microbenchmark",
            "schema_version": "1.0.0",
            "feature_id": "post-f016-trunk-optimization",
            "experiment_id": "trunk-cleanup-q6-decoded-hot-0001",
            "actual_status": "passed" if passed else "failed",
            **source,
            "checkpoint": _checkpoint_identity(),
            "environment": {
                "machine_class": "apple_silicon_m1_ultra",
                "architecture": platform.machine(),
                "python_version": platform.python_version(),
                "numpy_version": np.__version__,
                "mlx_version": version("mlx"),
                "storage_role": "internal_ssd",
            },
            "boundary": {
                "tensor": loc.name,
                "quantization": loc.type_name,
                "shape_rows_cols": [rows, cols],
                "lifecycle": "decoded MLX matrix retained throughout",
            },
            "protocol": {
                "changed_variable": "cleanup cadence only",
                "cleanup_operation": "gc.collect plus mlx.clear_cache when available",
                "warmups": WARMUPS,
                "measured_operations_per_mode": MEASURED,
                "batched_cleanup_interval": BATCH_SIZE,
                "mlx_synchronized": True,
                "timer": "time.perf_counter",
            },
            "cleanup_only": {
                "samples_seconds": cleanup_only,
                "summary": _summary_nonnegative(cleanup_only),
            },
            "current_cleanup_each_operation": {
                "samples": current_samples,
                "summaries": {field: _summary_nonnegative([float(sample[field]) for sample in current_samples]) for field in fields},
                "deterministic_output_sha256": sorted(set(current_hashes)),
            },
            "batched_cleanup": {
                "samples": batched_samples,
                "summaries": {field: _summary_nonnegative([float(sample[field]) for sample in batched_samples]) for field in fields},
                "cleanup_event_samples_seconds": cleanup_events,
                "cleanup_event_summary": _summary_nonnegative(cleanup_events),
                "amortized_cleanup_seconds_per_operation": sum(cleanup_events) / MEASURED,
                "population_wall_seconds": batched_population_wall,
                "deterministic_output_sha256": sorted(set(batched_hashes)),
            },
            "comparison": {
                "exact_output_hash_across_cleanup_modes": len(hashes) == 1,
                "output_f32_sha256": hashes,
            },
            "resource_before": resource_before,
            "resource_after_setup": resource_after_setup,
            "resource_after": resource_after,
            "model_inference_executed": False,
            "recommendation_scope": "batching was safe for this retained-matrix fixture only; runtime ownership and layer memory gates remain required",
            "unsupported_interpretations": [
                "cleanup removal",
                "complete layer, P1, or token speedup",
                "production cleanup cadence",
                "Rust or direct quantized Metal evidence",
            ],
        }
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    model_value = os.environ.get("PULSARMLX_GLM_GGUF")
    if not model_value:
        raise SystemExit("PULSARMLX_GLM_GGUF is required; no checkpoint was searched")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.output}")
    result = benchmark(Path(model_value))
    assert_public_safe(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp")
    temporary.write_text(json.dumps(result, separators=(",", ":"), sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(json.dumps({"actual_status": result["actual_status"], "exact": result["comparison"]["exact_output_hash_across_cleanup_modes"]}, sort_keys=True))
    return 0 if result["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
