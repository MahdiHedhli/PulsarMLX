#!/usr/bin/env python3
"""Qualify scalar whole-matrix reads on real GLM trunk tensors and MLA layer 8."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import sys
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any, Callable

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glm52_dense_primitives import (  # noqa: E402
    capture_dense_metrics,
    dense_read_mode,
    embed_token,
    matvec_weight_profiled,
    require_mlx_backend,
)
from glm52_inference import _checkpoint_identity, _source_identity  # noqa: E402
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_mla import CompactKVCache, mla_forward_token  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore, nbytes_for_tensor  # noqa: E402
from qualify_iq2_xxs_numpy import _summary  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
READ_MODES = ("row_reference", "whole_matrix_scalar")
MATRIX_TENSORS = (
    "blk.3.attn_output.weight",  # Q5_K: largest byte-weighted trunk format
    "blk.3.attn_q_b.weight",  # Q8_0: largest request-count trunk format
    "blk.8.attn_output.weight",  # Q6_K: post-run layer-8 candidate
)
LAYER = 8
WARMUPS = 3
MEASURED = 10


def _f32_sha256(values: list[float]) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f4").tobytes()).hexdigest()


def _f32_bits(values: list[float]) -> np.ndarray:
    return np.asarray(values, dtype=np.float32).view(np.uint32)


def _activation(cols: int, tensor: str) -> tuple[list[float], dict[str, Any]]:
    seed = int(hashlib.sha256(tensor.encode()).hexdigest()[:8], 16)
    indices = np.arange(cols, dtype=np.float64)
    values = np.sin(indices * 0.0007 + (seed % 1000) * 0.001).astype(np.float32)
    result = values.tolist()
    return result, {
        "kind": "deterministic_sine_f32",
        "length": cols,
        "seed_from_tensor_name_sha256_prefix": seed,
        "f32_sha256": _f32_sha256(result),
    }


def _cleanup() -> float:
    import mlx.core as mx

    start = time.perf_counter()
    gc.collect()
    clear_cache = getattr(mx, "clear_cache", None)
    if clear_cache is not None:
        clear_cache()
    return time.perf_counter() - start


def _summaries(samples: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "storage_read_seconds",
        "dequant_seconds",
        "contiguous_buffer_seconds",
        "mlx_matrix_build_seconds",
        "mlx_matvec_seconds",
        "total_seconds",
        "cleanup_seconds",
        "total_with_cleanup_seconds",
    )
    return {
        field: _summary([float(sample[field]) for sample in samples])
        for field in fields
    }


def _measure(
    operation: Callable[[], tuple[list[float], dict[str, Any]]],
) -> tuple[dict[str, Any], list[float]]:
    resource_before = sample_pressure().to_public_dict()
    if resource_before["level"] in {"critical", "urgent"}:
        raise RuntimeError(f"memory pressure became {resource_before['level']}")
    output, metrics = operation()
    cleanup_seconds = _cleanup()
    metrics.update(
        {
            "cleanup_seconds": cleanup_seconds,
            "total_with_cleanup_seconds": metrics["total_seconds"] + cleanup_seconds,
            "output_f32_sha256": _f32_sha256(output),
            "resource_before": resource_before,
            "resource_after": sample_pressure().to_public_dict(),
        }
    )
    return metrics, output


def _matrix_operation(
    store: Glm52TensorStore,
    tensor: str,
    activation: list[float],
    mode: str,
) -> tuple[list[float], dict[str, Any]]:
    output, metrics = matvec_weight_profiled(
        store, tensor, activation, read_mode=mode
    )
    return output, metrics.to_dict()


def _benchmark_matrix(store: Glm52TensorStore, tensor: str) -> dict[str, Any]:
    loc = store.tensors[tensor]
    cols, rows = (int(loc.dims[0]), int(loc.dims[1]))
    activation, activation_identity = _activation(cols, tensor)
    encoded_bytes = nbytes_for_tensor(loc.type_id, cols * rows)
    raw = store.pread(tensor, 0, encoded_bytes)
    if len(raw) != encoded_bytes:
        raise OSError(f"{tensor}: truncated identity read")
    identity = {
        "tensor": tensor,
        "shard": loc.file.name,
        "relative_offset": 0,
        "absolute_tensor_offset": loc.offset,
        "quantization": loc.type_name,
        "type_id": loc.type_id,
        "shape_rows_cols": [rows, cols],
        "encoded_bytes": encoded_bytes,
        "decoded_f32_bytes": rows * cols * 4,
        "encoded_sha256": hashlib.sha256(raw).hexdigest(),
    }
    del raw

    for mode in READ_MODES:
        for _ in range(WARMUPS):
            _, output = _measure(
                lambda mode=mode: _matrix_operation(store, tensor, activation, mode)
            )
            del output

    samples: dict[str, list[dict[str, Any]]] = {mode: [] for mode in READ_MODES}
    outputs: dict[str, list[float]] = {}
    for index in range(MEASURED):
        order = READ_MODES if index % 2 == 0 else tuple(reversed(READ_MODES))
        for mode in order:
            sample, output = _measure(
                lambda mode=mode: _matrix_operation(store, tensor, activation, mode)
            )
            sample["sample_index"] = index
            samples[mode].append(sample)
            outputs[mode] = output

    reference_bits = _f32_bits(outputs["row_reference"])
    bulk_bits = _f32_bits(outputs["whole_matrix_scalar"])
    mismatch = np.flatnonzero(reference_bits != bulk_bits)
    hashes = {
        mode: sorted({sample["output_f32_sha256"] for sample in mode_samples})
        for mode, mode_samples in samples.items()
    }
    if mismatch.size or any(len(values) != 1 for values in hashes.values()):
        raise RuntimeError(f"{tensor}: whole-matrix scalar output diverged")
    expected_reads = {"row_reference": rows, "whole_matrix_scalar": 1}
    for mode, mode_samples in samples.items():
        if any(sample["storage_read_count"] != expected_reads[mode] for sample in mode_samples):
            raise RuntimeError(f"{tensor}: read-count contract failed")
        if any(sample["encoded_bytes"] != encoded_bytes for sample in mode_samples):
            raise RuntimeError(f"{tensor}: encoded-byte contract failed")
    return {
        "identity": identity,
        "activation": activation_identity,
        "samples": samples,
        "summaries": {mode: _summaries(values) for mode, values in samples.items()},
        "comparison": {
            "exact_f32_bits": mismatch.size == 0,
            "mismatch_count": int(mismatch.size),
            "first_mismatch": int(mismatch[0]) if mismatch.size else None,
            "deterministic_hashes": hashes,
            "same_hash_across_modes": hashes["row_reference"] == hashes["whole_matrix_scalar"],
        },
        "read_contract": {
            "row_reference": rows,
            "whole_matrix_scalar": 1,
            "request_reduction_factor": float(rows),
            "encoded_bytes_unchanged": True,
        },
    }


def _mla_operation(
    store: Glm52TensorStore,
    residual: list[float],
    mode: str,
) -> tuple[list[float], dict[str, Any]]:
    total_start = time.perf_counter()
    with require_mlx_backend(), dense_read_mode(mode), capture_dense_metrics() as capture:
        output, diag = mla_forward_token(store, LAYER, residual, CompactKVCache(), 0)
    total_seconds = time.perf_counter() - total_start
    dense = capture.to_dict()
    metrics = {
        "read_mode": mode,
        "total_seconds": total_seconds,
        "dense_2d": dense,
        "storage_read_count": dense["totals"]["storage_read_count"],
        "encoded_bytes": dense["totals"]["encoded_bytes"],
        "storage_read_seconds": dense["totals"]["storage_read_seconds"],
        "dequant_seconds": dense["totals"]["dequant_seconds"],
        "contiguous_buffer_seconds": dense["totals"]["contiguous_buffer_seconds"],
        "mlx_matrix_build_seconds": dense["totals"]["mlx_matrix_build_seconds"],
        "mlx_matvec_seconds": dense["totals"]["mlx_matvec_seconds"],
        "uninstrumented_residual_seconds": max(
            0.0, total_seconds - dense["totals"]["total_seconds"]
        ),
        "diagnostics": diag,
    }
    return output, metrics


def _benchmark_mla(store: Glm52TensorStore) -> dict[str, Any]:
    residual = embed_token(store, 9703)
    residual_identity = {
        "kind": "real_token_embedding",
        "token_id": 9703,
        "length": len(residual),
        "f32_sha256": _f32_sha256(residual),
    }
    for mode in READ_MODES:
        for _ in range(WARMUPS):
            _, output = _measure(
                lambda mode=mode: _mla_operation(store, residual, mode)
            )
            del output
    samples: dict[str, list[dict[str, Any]]] = {mode: [] for mode in READ_MODES}
    outputs: dict[str, list[float]] = {}
    for index in range(MEASURED):
        order = READ_MODES if index % 2 == 0 else tuple(reversed(READ_MODES))
        for mode in order:
            sample, output = _measure(
                lambda mode=mode: _mla_operation(store, residual, mode)
            )
            sample["sample_index"] = index
            samples[mode].append(sample)
            outputs[mode] = output
    reference_bits = _f32_bits(outputs["row_reference"])
    bulk_bits = _f32_bits(outputs["whole_matrix_scalar"])
    mismatch = np.flatnonzero(reference_bits != bulk_bits)
    if mismatch.size:
        raise RuntimeError("MLA layer-8 whole-matrix scalar output diverged")
    fields = (
        "storage_read_seconds",
        "dequant_seconds",
        "contiguous_buffer_seconds",
        "mlx_matrix_build_seconds",
        "mlx_matvec_seconds",
        "uninstrumented_residual_seconds",
        "total_seconds",
        "cleanup_seconds",
        "total_with_cleanup_seconds",
    )
    summaries = {
        mode: {
            field: _summary([float(sample[field]) for sample in values])
            for field in fields
        }
        for mode, values in samples.items()
    }
    read_counts = {
        mode: sorted({int(sample["storage_read_count"]) for sample in values})
        for mode, values in samples.items()
    }
    if len(read_counts["row_reference"]) != 1 or read_counts["whole_matrix_scalar"] != [4]:
        raise RuntimeError("MLA dense 2D read-count contract failed")
    return {
        "layer": LAYER,
        "boundary": "complete_single_position_mla_attention",
        "scope": "2D dense metrics only; per-head 3D Q8_0 work remains in residual",
        "input": residual_identity,
        "samples": samples,
        "summaries": summaries,
        "comparison": {
            "exact_f32_bits": mismatch.size == 0,
            "mismatch_count": int(mismatch.size),
            "first_mismatch": int(mismatch[0]) if mismatch.size else None,
            "output_f32_sha256": _f32_sha256(outputs["row_reference"]),
        },
        "dense_2d_read_counts": read_counts,
    }


def benchmark(model: Path) -> dict[str, Any]:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before real checkpoint measurement")
    resource_before = sample_pressure().to_public_dict()
    if resource_before["level"] != "normal":
        raise RuntimeError(f"resource admission requires normal pressure, got {resource_before['level']}")
    store = Glm52TensorStore(model)
    try:
        matrices = [_benchmark_matrix(store, tensor) for tensor in MATRIX_TENSORS]
        mla = _benchmark_mla(store)
        record = {
            "schema": "pulsarmlx.research.glm52-trunk-bulk-read",
            "schema_version": "1.0.0",
            "feature_id": "post-f016-trunk-optimization",
            "experiment_id": "trunk-bulk-read-0001",
            "actual_status": "passed",
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
            "protocol": {
                "change": "row positional reads versus one whole-matrix read",
                "decoder": "same scalar row decoder in the same row order",
                "warmups_per_mode": WARMUPS,
                "measured_samples_per_mode": MEASURED,
                "measurement_order": "counterbalanced_alternation",
                "timer": "time.perf_counter",
                "mlx_synchronized": True,
                "os_page_cache_controlled": False,
                "cleanup_after_each_sample": "gc.collect plus mlx.clear_cache when available",
            },
            "matrices": matrices,
            "representative_mla_layer": mla,
            "resource_before": resource_before,
            "resource_after": sample_pressure().to_public_dict(),
            "unsupported_interpretations": [
                "vectorized decoder speedup",
                "complete transformer layer speedup",
                "full-stack or token-generation speedup",
                "controlled process-cold storage latency",
                "direct quantized Metal evidence",
            ],
        }
        if record["resource_after"]["level"] in {"critical", "urgent"}:
            raise RuntimeError("resource pressure became unsafe")
        assert_public_safe(record)
        return record
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    model = os.environ.get("PULSARMLX_GLM_GGUF")
    if not model:
        raise SystemExit("PULSARMLX_GLM_GGUF is required; no checkpoint was searched")
    if args.output.exists():
        raise SystemExit("output already exists; refusing overwrite")
    record = benchmark(Path(model))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp")
    temporary.write_text(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(
        json.dumps(
            {
                "actual_status": record["actual_status"],
                "matrix_count": len(record["matrices"]),
                "mla_exact_f32_bits": record["representative_mla_layer"]["comparison"]["exact_f32_bits"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
