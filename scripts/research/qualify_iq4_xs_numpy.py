#!/usr/bin/env python3
"""Qualify whole-matrix NumPy IQ4_XS decoding against the scalar oracle."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from glm52_inference import _checkpoint_identity, _source_identity  # noqa: E402
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore, nbytes_for_tensor  # noqa: E402
from iq4_xs_dequant import dequantize_matrix_iq4_xs_numpy, dequantize_row_iq4_xs  # noqa: E402
from qualify_iq2_xxs_numpy import _summary  # noqa: E402

CASES = (
    ("blk.8.ffn_down_exps.weight", 216),
    ("blk.75.ffn_down_exps.weight", 246),
    ("blk.76.ffn_down_exps.weight", 178),
    ("blk.77.ffn_down_exps.weight", 191),
)
BENCHMARK_CASE = CASES[0]
WARMUPS = 3
SAMPLES = 10


def _sha(array: np.ndarray) -> str:
    return hashlib.sha256(array.astype("<f4", copy=False).tobytes()).hexdigest()


def _scalar(encoded: bytes, rows: int, cols: int) -> np.ndarray:
    return np.asarray(dequantize_row_iq4_xs(encoded, rows * cols), dtype=np.float32).reshape(rows, cols)


def _timed(function):
    for _ in range(WARMUPS):
        result = function()
        del result
    timings, hashes = [], []
    for _ in range(SAMPLES):
        start = time.perf_counter()
        result = function()
        timings.append(time.perf_counter() - start)
        hashes.append(_sha(result))
        del result
    return timings, hashes


def _case(store: Glm52TensorStore, name: str, expert_id: int):
    loc = store.tensors[name]
    if loc.type_id != 23 or len(loc.dims) != 3:
        raise TypeError(f"{name}: expected 3D IQ4_XS expert tensor")
    cols, rows, experts = map(int, loc.dims)
    if not 0 <= expert_id < experts:
        raise IndexError(expert_id)
    encoded_bytes = nbytes_for_tensor(loc.type_id, cols) * rows
    start = time.perf_counter()
    encoded = store.pread(name, expert_id * encoded_bytes, encoded_bytes)
    read_seconds = time.perf_counter() - start
    if len(encoded) != encoded_bytes:
        raise OSError(f"{name}: truncated expert matrix {expert_id}")
    start = time.perf_counter()
    scalar = _scalar(encoded, rows, cols)
    scalar_seconds = time.perf_counter() - start
    start = time.perf_counter()
    vector = dequantize_matrix_iq4_xs_numpy(encoded, rows, cols)
    vector_seconds = time.perf_counter() - start
    scalar_bits = scalar.view(np.uint32).reshape(-1)
    vector_bits = vector.view(np.uint32).reshape(-1)
    mismatch = np.flatnonzero(scalar_bits != vector_bits)
    repeated = dequantize_matrix_iq4_xs_numpy(encoded, rows, cols)
    hashes = [_sha(vector), _sha(repeated)]
    result = {
        "tensor": name,
        "layer": int(name.split(".")[1]),
        "expert_id": expert_id,
        "shard": loc.file.name,
        "quantization": loc.type_name,
        "shape_rows_cols": [rows, cols],
        "encoded_bytes": encoded_bytes,
        "decoded_f32_bytes": int(vector.nbytes),
        "encoded_sha256": hashlib.sha256(encoded).hexdigest(),
        "decoded_f32_sha256": hashes[0],
        "storage_read_count": 1,
        "storage_read_seconds": read_seconds,
        "scalar_decode_seconds": scalar_seconds,
        "vector_decode_seconds": vector_seconds,
        "exact_f32_bits": mismatch.size == 0,
        "mismatch_count": int(mismatch.size),
        "first_mismatch": int(mismatch[0]) if mismatch.size else None,
        "deterministic_repeat_sha256": hashes,
        "deterministic_repeat": len(set(hashes)) == 1,
        "signed_zero_count_scalar": int(np.count_nonzero(scalar_bits == 0x80000000)),
        "signed_zero_count_vector": int(np.count_nonzero(vector_bits == 0x80000000)),
    }
    result["signed_zero_exact"] = result["signed_zero_count_scalar"] == result["signed_zero_count_vector"]
    del scalar, vector, repeated
    gc.collect()
    return result, encoded, rows, cols


def qualify(model: Path) -> dict:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before real qualification")
    before = sample_pressure().to_public_dict()
    if before["level"] != "normal":
        raise RuntimeError(f"resource admission requires normal pressure, got {before['level']}")
    store = Glm52TensorStore(model)
    cases, benchmark_input = [], None
    try:
        tensors = sorted(name for name, loc in store.tensors.items() if loc.type_id == 23)
        for name, expert_id in CASES:
            case, encoded, rows, cols = _case(store, name, expert_id)
            cases.append(case)
            if (name, expert_id) == BENCHMARK_CASE:
                benchmark_input = (encoded, rows, cols)
    finally:
        store.close()
    expected_tensors = sorted(name for name, _ in CASES)
    if tensors != expected_tensors:
        raise RuntimeError(f"IQ4_XS checkpoint census changed: {tensors}")
    assert benchmark_input is not None
    encoded, rows, cols = benchmark_input
    vector_fn = lambda: dequantize_matrix_iq4_xs_numpy(encoded, rows, cols)
    scalar_fn = lambda: _scalar(encoded, rows, cols)
    vector_samples, vector_hashes = _timed(vector_fn)
    scalar_samples, scalar_hashes = _timed(scalar_fn)
    gc.collect()
    allocation_before = sample_pressure().to_public_dict()
    tracemalloc.start()
    start = time.perf_counter()
    instrumented = vector_fn()
    instrumented_seconds = time.perf_counter() - start
    traced_current, traced_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    allocation_after = sample_pressure().to_public_dict()
    del instrumented
    vector_summary, scalar_summary = _summary(vector_samples), _summary(scalar_samples)
    gate = all(case["exact_f32_bits"] and case["deterministic_repeat"] and case["signed_zero_exact"] for case in cases)
    gate = gate and len(set(vector_hashes)) == len(set(scalar_hashes)) == 1 and vector_hashes[0] == scalar_hashes[0]
    gate = gate and allocation_before["level"] == allocation_after["level"] == "normal"
    record = {
        "schema": "pulsarmlx.research.glm52-iq4-xs-numpy-qualification",
        "schema_version": "1.0.0",
        "feature_id": "post-f016-moe-optimization",
        "actual_status": "passed" if gate else "failed",
        **source,
        "checkpoint": _checkpoint_identity(),
        "machine": {
            "architecture": platform.machine(),
            "chip": subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip(),
            "macos": platform.mac_ver()[0],
            "logical_cpu_count": os.cpu_count(),
            "numpy_version": np.__version__,
            "python_version": platform.python_version(),
        },
        "protocol": {
            "whole_matrix_read_count": 1,
            "warmups_per_mode": WARMUPS,
            "measured_samples_per_mode": SAMPLES,
            "timer": "time.perf_counter",
            "os_page_cache_controlled": False,
            "comparison": "exact f32 uint32 bit patterns including signed zero",
        },
        "checkpoint_format_census": {"iq4_xs_tensor_names": tensors},
        "scalar_oracle_imports_mlx": False,
        "cases": cases,
        "benchmark": {
            "tensor": BENCHMARK_CASE[0], "expert_id": BENCHMARK_CASE[1],
            "shape_rows_cols": [rows, cols], "weight_count": rows * cols, "encoded_bytes": len(encoded),
            "scalar_reference": {"samples_seconds": scalar_samples, "summary": scalar_summary},
            "numpy_vectorized": {"samples_seconds": vector_samples, "summary": vector_summary},
            "median_decode_speedup": scalar_summary["median_seconds"] / vector_summary["median_seconds"],
            "deterministic_hashes": {"scalar_reference": sorted(set(scalar_hashes)), "numpy_vectorized": sorted(set(vector_hashes))},
        },
        "allocation_observation": {
            "scope": "Python tracemalloc plus process resource snapshots; excludes some NumPy native allocator and all MLX overhead",
            "instrumented_vector_seconds": instrumented_seconds, "traced_current_bytes": traced_current, "traced_peak_bytes": traced_peak,
            "resource_before": allocation_before, "resource_after": allocation_after,
        },
        "resource_before": before, "resource_after": sample_pressure().to_public_dict(),
        "unsupported_interpretations": ["complete expert, MoE, layer, full-stack, or token-generation speedup", "Rust or direct quantized Metal evidence"],
    }
    assert_public_safe(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    model = os.environ.get("PULSARMLX_GLM_GGUF")
    if not model: raise SystemExit("PULSARMLX_GLM_GGUF is required; no checkpoint was searched")
    if args.output.exists(): raise SystemExit("output already exists; refusing overwrite")
    record = qualify(Path(model)); args.output.parent.mkdir(parents=True, exist_ok=True); temporary = args.output.with_name(f".{args.output.name}.tmp"); temporary.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"); temporary.replace(args.output)
    print(json.dumps({"actual_status": record["actual_status"], "median_decode_speedup": record["benchmark"]["median_decode_speedup"]}, sort_keys=True)); return 0 if record["actual_status"] == "passed" else 1


if __name__ == "__main__": raise SystemExit(main())
