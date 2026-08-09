#!/usr/bin/env python3
"""Isolate Q8_0 per-head slab reads and decoding at head and MLA boundaries."""

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
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glm52_dense_primitives import capture_dense_metrics, dense_read_mode, embed_token, require_mlx_backend  # noqa: E402
from glm52_inference import _checkpoint_identity, _source_identity  # noqa: E402
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_mla import CompactKVCache, N_HEAD, _matvec_3d_q8, mla_forward_token  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore, nbytes_for_tensor  # noqa: E402
from qualify_iq2_xxs_numpy import _summary  # noqa: E402

LAYER = 3
HEAD = 0
TENSOR = "blk.3.attn_k_b.weight"
WARMUPS = 3
MEASURED = 10
COMPONENT_FIELDS = (
    "encoded_bytes", "storage_read_count", "storage_read_seconds", "dequant_seconds",
    "contiguous_buffer_seconds", "mlx_matrix_build_seconds", "mlx_matvec_seconds", "total_seconds",
)


def _configuration(experiment: str):
    if experiment == "bulk-scalar":
        return {
            "modes": ("whole_matrix_numpy_q5_q8", "whole_matrix_numpy_q5_q8_head_bulk_scalar"),
            "schema": "pulsarmlx.research.glm52-q8-head-bulk-scalar",
            "experiment_id": "q8-head-bulk-scalar-0001",
            "changed_variable": "per-row positional reads versus one complete head-slab read; scalar Q8_0 decoder unchanged",
            "expected_decoders": ("scalar_reference", "scalar_reference"),
        }
    if experiment == "numpy":
        return {
            "modes": ("whole_matrix_numpy_q5_q8_head_bulk_scalar", "whole_matrix_numpy_q5_q8_head_numpy"),
            "schema": "pulsarmlx.research.glm52-q8-head-numpy-integration",
            "experiment_id": "q8-head-numpy-integration-0001",
            "changed_variable": "complete head-slab scalar Q8_0 decode versus exact-bit NumPy Q8_0 decode; one read in both modes",
            "expected_decoders": ("scalar_reference", "numpy_vectorized_q8_0"),
        }
    raise ValueError(experiment)


def _f32_bits(values):
    return np.asarray(values, dtype=np.float32).view(np.uint32)


def _f32_sha256(values):
    return hashlib.sha256(np.asarray(values, dtype="<f4").tobytes()).hexdigest()


def _cleanup():
    import mlx.core as mx

    start = time.perf_counter()
    gc.collect()
    clear_cache = getattr(mx, "clear_cache", None)
    if clear_cache is not None:
        clear_cache()
    return time.perf_counter() - start


def _measure(function):
    before = sample_pressure().to_public_dict()
    if before["level"] in {"critical", "urgent"}:
        raise RuntimeError(f"memory pressure became {before['level']}")
    output, metrics = function()
    cleanup = _cleanup()
    metrics.update({
        "cleanup_seconds": cleanup,
        "total_with_cleanup_seconds": metrics["total_seconds"] + cleanup,
        "output_f32_sha256": _f32_sha256(output),
        "resource_before": before,
        "resource_after": sample_pressure().to_public_dict(),
    })
    return metrics, output


def _sum_operations(operations):
    return {field: sum(float(operation[field]) for operation in operations) for field in COMPONENT_FIELDS}


def _head_once(store, activation, mode):
    start = time.perf_counter()
    with require_mlx_backend(), dense_read_mode(mode), capture_dense_metrics() as capture:
        output = _matvec_3d_q8(store, TENSOR, HEAD, activation, out_dim_key="kv_lora")
    if len(capture.operations) != 1:
        raise RuntimeError("expected one captured head operation")
    metrics = capture.operations[0].to_dict()
    metrics["total_seconds"] = time.perf_counter() - start
    return output, metrics


def _benchmark_head(store, config):
    loc = store.tensors[TENSOR]
    cols, rows, heads = map(int, loc.dims)
    row_bytes = nbytes_for_tensor(loc.type_id, cols)
    head_bytes = row_bytes * rows
    raw = store.pread(TENSOR, HEAD * head_bytes, head_bytes)
    if len(raw) != head_bytes:
        raise OSError("truncated head identity read")
    indices = np.arange(cols, dtype=np.float64)
    activation = np.sin(indices * 0.003 + 0.17).astype(np.float32).tolist()
    modes = config["modes"]
    for mode in modes:
        for _ in range(WARMUPS):
            _, output = _measure(lambda mode=mode: _head_once(store, activation, mode))
            del output
    samples = {mode: [] for mode in modes}
    outputs = {}
    for index in range(MEASURED):
        order = modes if index % 2 == 0 else tuple(reversed(modes))
        for mode in order:
            sample, output = _measure(lambda mode=mode: _head_once(store, activation, mode))
            sample["sample_index"] = index
            samples[mode].append(sample)
            outputs[mode] = output
        print(json.dumps({"progress": "q8-head", "measured_pair": index + 1}), flush=True)
    mismatch = np.flatnonzero(_f32_bits(outputs[modes[0]]) != _f32_bits(outputs[modes[1]]))
    for mode, decoder in zip(modes, config["expected_decoders"], strict=True):
        expected_reads = rows if mode == "whole_matrix_numpy_q5_q8" else 1
        for sample in samples[mode]:
            if sample["storage_read_count"] != expected_reads or sample["decoder_mode"] != decoder:
                raise RuntimeError("head read/decoder contract failed")
    if mismatch.size:
        raise RuntimeError("head output diverged")
    fields = tuple(COMPONENT_FIELDS[2:]) + ("cleanup_seconds", "total_with_cleanup_seconds")
    return {
        "identity": {"tensor": TENSOR, "shard": loc.file.name, "head": HEAD, "head_count": heads, "quantization": loc.type_name, "shape_rows_cols": [rows, cols], "encoded_bytes": head_bytes, "encoded_sha256": hashlib.sha256(raw).hexdigest()},
        "activation": {"kind": "deterministic_sine_f32", "length": cols, "f32_sha256": _f32_sha256(activation)},
        "samples": samples,
        "summaries": {mode: {field: _summary([sample[field] for sample in values]) for field in fields} for mode, values in samples.items()},
        "comparison": {"exact_f32_bits": mismatch.size == 0, "mismatch_count": int(mismatch.size), "first_mismatch": int(mismatch[0]) if mismatch.size else None, "output_f32_sha256": _f32_sha256(outputs[modes[0]])},
    }


def _mla_once(store, residual, mode):
    start = time.perf_counter()
    with require_mlx_backend(), dense_read_mode(mode), capture_dense_metrics() as capture:
        output, diagnostics = mla_forward_token(store, LAYER, residual, CompactKVCache(), 0)
    total_seconds = time.perf_counter() - start
    operations = [operation.to_dict() for operation in capture.operations]
    head_operations = [operation for operation in operations if operation["slice_index"] is not None]
    matrix_operations = [operation for operation in operations if operation["slice_index"] is None]
    if len(head_operations) != 2 * N_HEAD or len(matrix_operations) != 4:
        raise RuntimeError("MLA captured operation-count contract failed")
    head = _sum_operations(head_operations)
    matrix = _sum_operations(matrix_operations)
    attributed = sum(operation["total_seconds"] for operation in operations)
    metrics = {
        "read_mode": mode,
        "total_seconds": total_seconds,
        "head_operation_count": len(head_operations),
        "matrix_operation_count": len(matrix_operations),
        "head_metrics": head,
        "matrix_metrics": matrix,
        "head_storage_read_count": head["storage_read_count"],
        "head_storage_read_seconds": head["storage_read_seconds"],
        "head_dequant_seconds": head["dequant_seconds"],
        "head_contiguous_buffer_seconds": head["contiguous_buffer_seconds"],
        "head_mlx_matrix_build_seconds": head["mlx_matrix_build_seconds"],
        "head_mlx_matvec_seconds": head["mlx_matvec_seconds"],
        "head_total_seconds": head["total_seconds"],
        "matrix_total_seconds": matrix["total_seconds"],
        "uninstrumented_residual_seconds": max(0.0, total_seconds - attributed),
        "head_decoder_modes": sorted({operation["decoder_mode"] for operation in head_operations}),
        "diagnostics": diagnostics,
    }
    return output, metrics


def _benchmark_mla(store, config):
    residual = embed_token(store, 9703)
    modes = config["modes"]
    for mode in modes:
        for _ in range(WARMUPS):
            _, output = _measure(lambda mode=mode: _mla_once(store, residual, mode))
            del output
    samples = {mode: [] for mode in modes}
    outputs = {}
    for index in range(MEASURED):
        order = modes if index % 2 == 0 else tuple(reversed(modes))
        for mode in order:
            sample, output = _measure(lambda mode=mode: _mla_once(store, residual, mode))
            sample["sample_index"] = index
            samples[mode].append(sample)
            outputs[mode] = output
        print(json.dumps({"progress": "mla-q8-head", "measured_pair": index + 1}), flush=True)
    mismatch = np.flatnonzero(_f32_bits(outputs[modes[0]]) != _f32_bits(outputs[modes[1]]))
    if mismatch.size:
        raise RuntimeError("MLA head-mode output diverged")
    for mode, decoder in zip(modes, config["expected_decoders"], strict=True):
        expected_reads = 49_152 if mode == "whole_matrix_numpy_q5_q8" else 2 * N_HEAD
        for sample in samples[mode]:
            if sample["head_storage_read_count"] != expected_reads or sample["head_decoder_modes"] != [decoder]:
                raise RuntimeError("MLA head read/decoder contract failed")
    fields = (
        "head_storage_read_seconds", "head_dequant_seconds", "head_contiguous_buffer_seconds",
        "head_mlx_matrix_build_seconds", "head_mlx_matvec_seconds", "head_total_seconds",
        "matrix_total_seconds", "uninstrumented_residual_seconds", "total_seconds",
        "cleanup_seconds", "total_with_cleanup_seconds",
    )
    return {
        "layer": LAYER, "boundary": "complete_single_position_mla_attention",
        "input": {"token_id": 9703, "length": len(residual), "f32_sha256": _f32_sha256(residual)},
        "samples": samples,
        "summaries": {mode: {field: _summary([sample[field] for sample in values]) for field in fields} for mode, values in samples.items()},
        "comparison": {"exact_f32_bits": mismatch.size == 0, "mismatch_count": int(mismatch.size), "first_mismatch": int(mismatch[0]) if mismatch.size else None, "output_f32_sha256": _f32_sha256(outputs[modes[0]])},
        "operation_contract": {"head_operations_per_sample": 2 * N_HEAD, "matrix_operations_per_sample": 4},
    }


def benchmark(model: Path, experiment: str):
    config = _configuration(experiment)
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before real measurement")
    before = sample_pressure().to_public_dict()
    if before["level"] != "normal":
        raise RuntimeError("normal memory pressure required")
    store = Glm52TensorStore(model)
    try:
        head = _benchmark_head(store, config)
        mla = _benchmark_mla(store, config)
    finally:
        store.close()
    record = {
        "schema": config["schema"], "schema_version": "1.0.0", "feature_id": "post-f016-trunk-optimization",
        "experiment_id": config["experiment_id"], "actual_status": "passed", **source,
        "checkpoint": _checkpoint_identity(),
        "environment": {"machine_class": "apple_silicon_m1_ultra", "architecture": platform.machine(), "python_version": platform.python_version(), "numpy_version": np.__version__, "mlx_version": version("mlx"), "storage_role": "internal_ssd"},
        "protocol": {"changed_variable": config["changed_variable"], "modes": list(config["modes"]), "warmups_per_mode": WARMUPS, "measured_samples_per_mode": MEASURED, "measurement_order": "counterbalanced_alternation", "timer": "time.perf_counter", "mlx_synchronized": True, "os_page_cache_controlled": False, "cleanup_after_each_sample": "gc.collect plus mlx.clear_cache when available"},
        "head_boundary": head, "representative_mla_layer": mla,
        "resource_before": before, "resource_after": sample_pressure().to_public_dict(),
        "model_inference_executed": False,
        "unsupported_interpretations": ["complete transformer-layer speedup", "full-stack or token-generation speedup", "Q6_K vectorization", "Rust or direct quantized Metal evidence"],
    }
    assert_public_safe(record)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", choices=("bulk-scalar", "numpy"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    model = os.environ.get("PULSARMLX_GLM_GGUF")
    if not model:
        raise SystemExit("PULSARMLX_GLM_GGUF is required; no checkpoint was searched")
    if args.output.exists():
        raise SystemExit("output already exists; refusing overwrite")
    record = benchmark(Path(model), args.experiment)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp")
    temporary.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    temporary.replace(args.output)
    print(json.dumps({"actual_status": record["actual_status"], "head_exact": record["head_boundary"]["comparison"]["exact_f32_bits"], "mla_exact": record["representative_mla_layer"]["comparison"]["exact_f32_bits"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
