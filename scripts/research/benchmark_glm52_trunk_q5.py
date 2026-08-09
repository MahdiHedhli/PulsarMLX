#!/usr/bin/env python3
"""Benchmark exact selected NumPy trunk decoders at matrix and MLA boundaries."""

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

MODES = ("whole_matrix_scalar", "whole_matrix_numpy_q5")
TENSOR = "blk.3.attn_output.weight"
EXPECTED_TYPE_ID = 13
SCHEMA = "pulsarmlx.research.glm52-trunk-q5-integration"
EXPERIMENT_ID = "trunk-q5-integration-0001"
CHANGED_VARIABLE = "Q5_K scalar row decode versus exact-bit whole-matrix NumPy Q5_K decode"
LAYER = 3
WARMUPS = 3
MEASURED = 10


def _expected_decoder(mode: str, quantization: str) -> str:
    if quantization == "Q5_K" and mode in {
        "whole_matrix_numpy_q5",
        "whole_matrix_numpy_q5_q8",
    }:
        return "numpy_vectorized_q5_k"
    if quantization == "Q8_0" and mode == "whole_matrix_numpy_q5_q8":
        return "numpy_vectorized_q8_0"
    if quantization == "Q8_0" and mode in {
        "whole_matrix_numpy_q5_q8_head_bulk_scalar",
        "whole_matrix_numpy_q5_q8_head_numpy",
        "whole_matrix_numpy_q5_q8_q6_head_numpy",
    }:
        return "numpy_vectorized_q8_0"
    if quantization == "Q6_K" and mode == "whole_matrix_numpy_q5_q8_q6_head_numpy":
        return "numpy_vectorized_q6_k"
    return "scalar_reference"


def _configure(experiment: str) -> None:
    global MODES, TENSOR, EXPECTED_TYPE_ID, SCHEMA, EXPERIMENT_ID, CHANGED_VARIABLE, LAYER
    if experiment == "q5":
        return
    if experiment == "q8-2d":
        MODES = ("whole_matrix_numpy_q5", "whole_matrix_numpy_q5_q8")
        TENSOR = "blk.3.attn_q_b.weight"
        EXPECTED_TYPE_ID = 8
        SCHEMA = "pulsarmlx.research.glm52-trunk-q8-2d-integration"
        EXPERIMENT_ID = "trunk-q8-2d-integration-0001"
        CHANGED_VARIABLE = "Q8_0 scalar row decode versus exact-bit whole-matrix NumPy Q8_0 decode; Q5_K remains vectorized"
        return
    if experiment == "q6":
        MODES = ("whole_matrix_numpy_q5_q8_head_numpy", "whole_matrix_numpy_q5_q8_q6_head_numpy")
        TENSOR = "blk.8.attn_output.weight"
        EXPECTED_TYPE_ID = 14
        LAYER = 8
        SCHEMA = "pulsarmlx.research.glm52-trunk-q6-integration"
        EXPERIMENT_ID = "trunk-q6-integration-0001"
        CHANGED_VARIABLE = "Q6_K scalar row decode versus exact-bit whole-matrix NumPy Q6_K decode; Q5_K and all Q8_0 paths remain vectorized"
        return
    raise ValueError(f"unsupported experiment {experiment}")


def _f32_bits(values: list[float]) -> np.ndarray:
    return np.asarray(values, dtype=np.float32).view(np.uint32)


def _f32_sha256(values: list[float]) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f4").tobytes()).hexdigest()


def _activation(cols: int) -> tuple[list[float], dict[str, Any]]:
    indices = np.arange(cols, dtype=np.float64)
    values = np.sin(indices * 0.0007 + 0.319).astype(np.float32).tolist()
    return values, {
        "kind": "deterministic_sine_f32",
        "length": cols,
        "f32_sha256": _f32_sha256(values),
    }


def _cleanup() -> float:
    import mlx.core as mx

    start = time.perf_counter()
    gc.collect()
    clear_cache = getattr(mx, "clear_cache", None)
    if clear_cache is not None:
        clear_cache()
    return time.perf_counter() - start


def _measure(operation: Callable[[], tuple[list[float], dict[str, Any]]]):
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
    return {field: _summary([float(sample[field]) for sample in samples]) for field in fields}


def _matrix_operation(store, activation, mode):
    output, metrics = matvec_weight_profiled(store, TENSOR, activation, read_mode=mode)
    return output, metrics.to_dict()


def _benchmark_matrix(store: Glm52TensorStore) -> dict[str, Any]:
    loc = store.tensors[TENSOR]
    if loc.type_id != EXPECTED_TYPE_ID:
        raise TypeError(f"{TENSOR}: unexpected quantization {loc.type_name}")
    cols, rows = map(int, loc.dims)
    activation, activation_identity = _activation(cols)
    encoded_bytes = nbytes_for_tensor(loc.type_id, cols) * rows
    encoded = store.pread(TENSOR, 0, encoded_bytes)
    if len(encoded) != encoded_bytes:
        raise OSError(f"{TENSOR}: truncated identity read")
    identity = {
        "tensor": TENSOR,
        "shard": loc.file.name,
        "quantization": loc.type_name,
        "shape_rows_cols": [rows, cols],
        "encoded_bytes": encoded_bytes,
        "decoded_f32_bytes": rows * cols * 4,
        "encoded_sha256": hashlib.sha256(encoded).hexdigest(),
    }
    del encoded
    for mode in MODES:
        for _ in range(WARMUPS):
            _, output = _measure(lambda mode=mode: _matrix_operation(store, activation, mode))
            del output
    samples = {mode: [] for mode in MODES}
    outputs: dict[str, list[float]] = {}
    for index in range(MEASURED):
        order = MODES if index % 2 == 0 else tuple(reversed(MODES))
        for mode in order:
            sample, output = _measure(lambda mode=mode: _matrix_operation(store, activation, mode))
            sample["sample_index"] = index
            samples[mode].append(sample)
            outputs[mode] = output
        print(json.dumps({"progress": "trunk-matrix", "measured_pair": index + 1}), flush=True)
    scalar_bits = _f32_bits(outputs[MODES[0]])
    vector_bits = _f32_bits(outputs[MODES[1]])
    mismatch = np.flatnonzero(scalar_bits != vector_bits)
    hashes = {
        mode: sorted({sample["output_f32_sha256"] for sample in mode_samples})
        for mode, mode_samples in samples.items()
    }
    for mode, mode_samples in samples.items():
        expected_decoder = _expected_decoder(mode, loc.type_name)
        if any(sample["storage_read_count"] != 1 for sample in mode_samples):
            raise RuntimeError("Q5 matrix read-count contract failed")
        if any(sample["decoder_mode"] != expected_decoder for sample in mode_samples):
            raise RuntimeError("Q5 matrix decoder-mode contract failed")
    if mismatch.size or any(len(values) != 1 for values in hashes.values()):
        raise RuntimeError("Q5 integrated matrix output diverged")
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
            "same_hash_across_modes": hashes[MODES[0]] == hashes[MODES[1]],
        },
    }


def _mla_operation(store, residual, mode):
    total_start = time.perf_counter()
    with require_mlx_backend(), dense_read_mode(mode), capture_dense_metrics() as capture:
        output, diagnostics = mla_forward_token(store, LAYER, residual, CompactKVCache(), 0)
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
        "uninstrumented_residual_seconds": max(0.0, total_seconds - dense["totals"]["total_seconds"]),
        "diagnostics": diagnostics,
    }
    return output, metrics


def _benchmark_mla(store: Glm52TensorStore) -> dict[str, Any]:
    residual = embed_token(store, 9703)
    input_identity = {
        "kind": "real_token_embedding",
        "token_id": 9703,
        "length": len(residual),
        "f32_sha256": _f32_sha256(residual),
    }
    for mode in MODES:
        for _ in range(WARMUPS):
            _, output = _measure(lambda mode=mode: _mla_operation(store, residual, mode))
            del output
    samples = {mode: [] for mode in MODES}
    outputs: dict[str, list[float]] = {}
    for index in range(MEASURED):
        order = MODES if index % 2 == 0 else tuple(reversed(MODES))
        for mode in order:
            sample, output = _measure(lambda mode=mode: _mla_operation(store, residual, mode))
            sample["sample_index"] = index
            samples[mode].append(sample)
            outputs[mode] = output
        print(json.dumps({"progress": f"mla-layer-{LAYER}", "measured_pair": index + 1}), flush=True)
    scalar_bits = _f32_bits(outputs[MODES[0]])
    vector_bits = _f32_bits(outputs[MODES[1]])
    mismatch = np.flatnonzero(scalar_bits != vector_bits)
    if mismatch.size:
        raise RuntimeError("Q5 integrated MLA output diverged")
    candidate_mode = MODES[1]
    for sample in samples[candidate_mode]:
        operations = sample["dense_2d"]["operations"]
        if any(
            op["decoder_mode"] != _expected_decoder(candidate_mode, op["quantization"])
            for op in operations
        ):
            raise RuntimeError("MLA decoder contract failed")
    fields = tuple(_summaries(samples[MODES[0]])) + ("uninstrumented_residual_seconds",)
    summaries = {
        mode: {field: _summary([float(sample[field]) for sample in values]) for field in fields}
        for mode, values in samples.items()
    }
    vector_ops = samples[candidate_mode][0]["dense_2d"]["operations"]
    return {
        "layer": LAYER,
        "boundary": "complete_single_position_mla_attention",
        "scope": "all instrumented dense MLA projections, including per-head Q8_0 slabs",
        "input": input_identity,
        "samples": samples,
        "summaries": summaries,
        "comparison": {
            "exact_f32_bits": mismatch.size == 0,
            "mismatch_count": int(mismatch.size),
            "first_mismatch": int(mismatch[0]) if mismatch.size else None,
            "output_f32_sha256": _f32_sha256(outputs[MODES[0]]),
        },
        "captured_operation_contract": {
            "operation_count": len(vector_ops),
            "q5_vectorized_count": sum(op["decoder_mode"] == "numpy_vectorized_q5_k" for op in vector_ops),
            "q8_vectorized_count": sum(op["decoder_mode"] == "numpy_vectorized_q8_0" for op in vector_ops),
            "q6_vectorized_count": sum(op["decoder_mode"] == "numpy_vectorized_q6_k" for op in vector_ops),
            "other_scalar_count": sum(op["decoder_mode"] == "scalar_reference" for op in vector_ops),
        },
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
        matrix = _benchmark_matrix(store)
        mla = _benchmark_mla(store)
    finally:
        store.close()
    record = {
        "schema": SCHEMA,
        "schema_version": "1.0.0",
        "feature_id": "post-f016-trunk-optimization",
        "experiment_id": EXPERIMENT_ID,
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
            "changed_variable": CHANGED_VARIABLE,
            "read_mode_both": "one bounded whole-matrix positional read",
            "decoder_contract": {mode: {quant: _expected_decoder(mode, quant) for quant in ("Q5_K", "Q8_0", "Q6_K")} for mode in MODES},
            "warmups_per_mode": WARMUPS,
            "measured_samples_per_mode": MEASURED,
            "measurement_order": "counterbalanced_alternation",
            "timer": "time.perf_counter",
            "mlx_synchronized": True,
            "os_page_cache_controlled": False,
            "cleanup_after_each_sample": "gc.collect plus mlx.clear_cache when available",
        },
        "matrix": matrix,
        "representative_mla_layer": mla,
        "resource_before": resource_before,
        "resource_after": sample_pressure().to_public_dict(),
        "model_inference_executed": False,
        "unsupported_interpretations": [
            "complete transformer-layer speedup",
            "full-stack or token-generation speedup",
            *([] if EXPECTED_TYPE_ID == 14 else ["Q6_K vectorization"]),
            "Rust or direct quantized Metal evidence",
        ],
    }
    if record["resource_after"]["level"] in {"critical", "urgent"}:
        raise RuntimeError("resource pressure became unsafe")
    assert_public_safe(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--experiment", choices=("q5", "q8-2d", "q6"), default="q5")
    args = parser.parse_args()
    _configure(args.experiment)
    model = os.environ.get("PULSARMLX_GLM_GGUF")
    if not model:
        raise SystemExit("PULSARMLX_GLM_GGUF is required; no checkpoint was searched")
    if args.output.exists():
        raise SystemExit("output already exists; refusing overwrite")
    try:
        record = benchmark(Path(model))
    except Exception as error:
        record = {
            "schema": SCHEMA,
            "schema_version": "1.0.0",
            "feature_id": "post-f016-trunk-optimization",
            "experiment_id": EXPERIMENT_ID,
            "actual_status": "failed",
            **_source_identity(),
            "failure": {"reason": "bounded_experiment_failed", "error_type": type(error).__name__},
            "model_inference_executed": False,
        }
        assert_public_safe(record)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(f".{args.output.name}.tmp")
        temporary.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        temporary.replace(args.output)
        print(json.dumps({"actual_status": "failed", "error_type": type(error).__name__}), file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp")
    temporary.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    temporary.replace(args.output)
    print(json.dumps({"actual_status": "passed", "matrix_exact": record["matrix"]["comparison"]["exact_f32_bits"], "mla_exact": record["representative_mla_layer"]["comparison"]["exact_f32_bits"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
