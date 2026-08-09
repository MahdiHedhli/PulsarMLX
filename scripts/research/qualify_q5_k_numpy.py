#!/usr/bin/env python3
"""Qualify whole-matrix NumPy Q5_K decoding against the scalar oracle."""

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
from typing import Any, Callable

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glm52_inference import _checkpoint_identity, _source_identity  # noqa: E402
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_tensor_store import Glm52TensorStore, nbytes_for_tensor  # noqa: E402
from ggml_kquants import (  # noqa: E402
    dequantize_matrix_q5_k_numpy,
    dequantize_row_q5_k,
)
from qualify_iq2_xxs_numpy import _summary  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAYERS = (3, 20, 40, 60)
WARMUPS = 3
SAMPLES = 10


def _sha256_f32(array: np.ndarray) -> str:
    return hashlib.sha256(array.astype("<f4", copy=False).tobytes()).hexdigest()


def _scalar(encoded: bytes, rows: int, cols: int) -> np.ndarray:
    return np.asarray(dequantize_row_q5_k(encoded, rows * cols), dtype=np.float32).reshape(rows, cols)


def _timed(function: Callable[[], np.ndarray]) -> tuple[list[float], list[str]]:
    for _ in range(WARMUPS):
        result = function()
        del result
    samples: list[float] = []
    hashes: list[str] = []
    for _ in range(SAMPLES):
        start = time.perf_counter()
        result = function()
        samples.append(time.perf_counter() - start)
        hashes.append(_sha256_f32(result))
        del result
    return samples, hashes


def _machine() -> dict[str, Any]:
    chip = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
    return {
        "architecture": platform.machine(),
        "chip": chip,
        "macos": platform.mac_ver()[0],
        "logical_cpu_count": os.cpu_count(),
        "numpy_version": np.__version__,
        "python_version": platform.python_version(),
    }


def _case(store: Glm52TensorStore, layer: int) -> tuple[dict[str, Any], bytes, int, int]:
    name = f"blk.{layer}.attn_output.weight"
    loc = store.tensors[name]
    if loc.type_id != 13 or len(loc.dims) != 2:
        raise TypeError(f"{name}: expected 2D Q5_K")
    cols, rows = map(int, loc.dims)
    encoded_bytes = nbytes_for_tensor(loc.type_id, cols) * rows
    read_start = time.perf_counter()
    encoded = store.pread(name, 0, encoded_bytes)
    read_seconds = time.perf_counter() - read_start
    if len(encoded) != encoded_bytes:
        raise OSError(f"{name}: truncated complete matrix")

    scalar_start = time.perf_counter()
    scalar = _scalar(encoded, rows, cols)
    scalar_seconds = time.perf_counter() - scalar_start
    vector_start = time.perf_counter()
    vector = dequantize_matrix_q5_k_numpy(encoded, rows, cols)
    vector_seconds = time.perf_counter() - vector_start
    scalar_bits = scalar.view(np.uint32).reshape(-1)
    vector_bits = vector.view(np.uint32).reshape(-1)
    mismatch = np.flatnonzero(scalar_bits != vector_bits)
    repeated = dequantize_matrix_q5_k_numpy(encoded, rows, cols)
    hashes = [_sha256_f32(vector), _sha256_f32(repeated)]
    signed_zero_scalar = int(np.count_nonzero(scalar_bits == 0x80000000))
    signed_zero_vector = int(np.count_nonzero(vector_bits == 0x80000000))
    result = {
        "layer": layer,
        "tensor": name,
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
        "deterministic_repeat": hashes[0] == hashes[1],
        "signed_zero_count_scalar": signed_zero_scalar,
        "signed_zero_count_vector": signed_zero_vector,
        "signed_zero_exact": signed_zero_scalar == signed_zero_vector,
    }
    del scalar, vector, repeated
    gc.collect()
    return result, encoded, rows, cols


def qualify(model: Path) -> dict[str, Any]:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before real qualification")
    before = sample_pressure().to_public_dict()
    store = Glm52TensorStore(model)
    cases: list[dict[str, Any]] = []
    benchmark_input: tuple[bytes, int, int] | None = None
    try:
        for layer in LAYERS:
            case, encoded, rows, cols = _case(store, layer)
            cases.append(case)
            if benchmark_input is None:
                benchmark_input = (encoded, rows, cols)
    finally:
        store.close()
    assert benchmark_input is not None
    encoded, rows, cols = benchmark_input

    vector_fn = lambda: dequantize_matrix_q5_k_numpy(encoded, rows, cols)
    scalar_fn = lambda: _scalar(encoded, rows, cols)
    vector_samples, vector_hashes = _timed(vector_fn)
    scalar_samples, scalar_hashes = _timed(scalar_fn)

    gc.collect()
    allocation_before = sample_pressure().to_public_dict()
    tracemalloc.start()
    instrumented_start = time.perf_counter()
    instrumented = vector_fn()
    instrumented_seconds = time.perf_counter() - instrumented_start
    traced_current, traced_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    allocation_after = sample_pressure().to_public_dict()
    del instrumented

    vector_summary = _summary(vector_samples)
    scalar_summary = _summary(scalar_samples)
    case_gate = all(
        case["exact_f32_bits"]
        and case["deterministic_repeat"]
        and case["signed_zero_exact"]
        for case in cases
    )
    sample_gate = (
        len(set(vector_hashes)) == 1
        and len(set(scalar_hashes)) == 1
        and vector_hashes[0] == scalar_hashes[0]
    )
    return {
        "schema": "pulsarmlx.research.glm52-q5-k-numpy-qualification",
        "schema_version": "1.0.0",
        "feature_id": "post-f016-trunk-optimization",
        "actual_status": "passed" if case_gate and sample_gate else "failed",
        **source,
        "checkpoint": _checkpoint_identity(),
        "machine": _machine(),
        "decoder_modes": ["scalar_reference", "numpy_vectorized"],
        "scalar_oracle_imports_mlx": False,
        "protocol": {
            "whole_matrix_read_count": 1,
            "warmups_per_mode": WARMUPS,
            "measured_samples_per_mode": SAMPLES,
            "timer": "time.perf_counter",
            "os_page_cache_controlled": False,
            "comparison": "exact f32 uint32 bit patterns including signed zero",
        },
        "cases": cases,
        "benchmark": {
            "tensor": cases[0]["tensor"],
            "shape_rows_cols": cases[0]["shape_rows_cols"],
            "weight_count": rows * cols,
            "encoded_bytes": len(encoded),
            "scalar_reference": {"samples_seconds": scalar_samples, "summary": scalar_summary},
            "numpy_vectorized": {"samples_seconds": vector_samples, "summary": vector_summary},
            "median_decode_speedup": scalar_summary["median_seconds"] / vector_summary["median_seconds"],
            "deterministic_hashes": {
                "scalar_reference": sorted(set(scalar_hashes)),
                "numpy_vectorized": sorted(set(vector_hashes)),
            },
        },
        "allocation_observation": {
            "scope": "Python tracemalloc plus process resource snapshots; does not include all NumPy native allocator or MLX overhead",
            "instrumented_vector_seconds": instrumented_seconds,
            "traced_current_bytes": traced_current,
            "traced_peak_bytes": traced_peak,
            "resource_before": allocation_before,
            "resource_after": allocation_after,
        },
        "resource_before": before,
        "resource_after": sample_pressure().to_public_dict(),
        "unsupported_interpretations": [
            "complete MLA or transformer-layer speedup",
            "full-stack or token-generation speedup",
            "Rust or direct quantized Metal evidence",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    model = args.model or (Path(os.environ["PULSARMLX_GLM_GGUF"]) if "PULSARMLX_GLM_GGUF" in os.environ else None)
    if model is None:
        raise SystemExit("checkpoint required: pass --model or PULSARMLX_GLM_GGUF")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    record = qualify(model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps({"actual_status": record["actual_status"], "median_decode_speedup": record["benchmark"]["median_decode_speedup"]}, sort_keys=True))
    return 0 if record["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
