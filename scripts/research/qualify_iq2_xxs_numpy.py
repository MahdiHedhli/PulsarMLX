#!/usr/bin/env python3
"""Qualify the NumPy IQ2_XXS decoder against the scalar reference path."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
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
from iq2_xxs_dequant import (  # noqa: E402
    dequantize_matrix_iq2_xxs_numpy,
    dequantize_row_iq2_xxs,
)

ROOT = Path(__file__).resolve().parents[2]
QUALIFICATION_LAYERS = (3, 20, 40, 60)


def _sha256_f32(array: np.ndarray) -> str:
    return hashlib.sha256(array.astype("<f4", copy=False).tobytes()).hexdigest()


def _summary(samples: list[float]) -> dict[str, float | int]:
    if not samples or any(not math.isfinite(value) or value <= 0 for value in samples):
        raise ValueError("timing samples must be finite and positive")
    values = np.asarray(samples, dtype=np.float64)
    mean = float(values.mean())
    sample_standard_deviation = (
        float(values.std(ddof=1)) if len(samples) > 1 else 0.0
    )
    return {
        "sample_count": len(samples),
        "median_seconds": float(np.median(values)),
        "mean_seconds": mean,
        "standard_deviation_seconds": sample_standard_deviation,
        "minimum_seconds": float(values.min()),
        "maximum_seconds": float(values.max()),
        "p5_seconds": float(np.percentile(values, 5)),
        "p25_seconds": float(np.percentile(values, 25)),
        "p75_seconds": float(np.percentile(values, 75)),
        "p95_seconds": float(np.percentile(values, 95)),
        "coefficient_of_variation": sample_standard_deviation / mean,
    }


def _timed_samples(
    function: Callable[[], np.ndarray], *, warmups: int, samples: int
) -> tuple[list[float], list[str]]:
    for _ in range(warmups):
        result = function()
        del result
    timings: list[float] = []
    hashes: list[str] = []
    for _ in range(samples):
        start = time.perf_counter()
        result = function()
        timings.append(time.perf_counter() - start)
        hashes.append(_sha256_f32(result))
        del result
    return timings, hashes


def _scalar_matrix(encoded: bytes, rows: int, cols: int) -> np.ndarray:
    values = dequantize_row_iq2_xxs(encoded, rows * cols)
    return np.asarray(values, dtype=np.float32).reshape(rows, cols)


def _route_map() -> dict[int, int]:
    evidence = json.loads(
        (ROOT / "docs/research/glm52/raw/f016-c09-depth-0001.json").read_text()
    )
    return {
        int(entry["layer"]): int(entry["expert_ids"][0])
        for entry in evidence["layer_meta"]
        if entry.get("expert_ids")
    }


def _machine() -> dict[str, Any]:
    chip = subprocess.check_output(
        ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
    ).strip()
    return {
        "architecture": platform.machine(),
        "chip": chip,
        "macos": platform.mac_ver()[0],
        "logical_cpu_count": os.cpu_count(),
        "numpy_version": np.__version__,
        "python_version": platform.python_version(),
    }


def _compare_case(
    store: Glm52TensorStore, *, layer: int, expert: int
) -> tuple[dict[str, Any], bytes, int, int]:
    name = f"blk.{layer}.ffn_gate_exps.weight"
    loc = store.tensors[name]
    if loc.type_id != 16 or len(loc.dims) != 3:
        raise TypeError(f"{name}: expected 3D IQ2_XXS")
    cols, rows, experts = map(int, loc.dims)
    if not 0 <= expert < experts:
        raise IndexError(expert)
    matrix_bytes = nbytes_for_tensor(loc.type_id, cols * rows)
    read_start = time.perf_counter()
    encoded = store.pread(name, expert * matrix_bytes, matrix_bytes)
    read_seconds = time.perf_counter() - read_start
    if len(encoded) != matrix_bytes:
        raise OSError(f"{name}: truncated complete expert matrix")

    scalar_start = time.perf_counter()
    scalar = _scalar_matrix(encoded, rows, cols)
    scalar_seconds = time.perf_counter() - scalar_start
    vector_start = time.perf_counter()
    vector = dequantize_matrix_iq2_xxs_numpy(encoded, rows, cols)
    vector_seconds = time.perf_counter() - vector_start
    scalar_bits = scalar.view(np.uint32).reshape(-1)
    vector_bits = vector.view(np.uint32).reshape(-1)
    mismatch_locations = np.flatnonzero(scalar_bits != vector_bits)
    hashes = [_sha256_f32(vector)]
    repeated = dequantize_matrix_iq2_xxs_numpy(encoded, rows, cols)
    hashes.append(_sha256_f32(repeated))

    row_results = []
    row_bytes = nbytes_for_tensor(loc.type_id, cols)
    for row in (0, rows // 2, rows - 1):
        row_encoded = encoded[row * row_bytes : (row + 1) * row_bytes]
        row_scalar = np.asarray(
            dequantize_row_iq2_xxs(row_encoded, cols), dtype=np.float32
        )
        row_vector = dequantize_matrix_iq2_xxs_numpy(row_encoded, 1, cols)[0]
        row_results.append(
            {
                "row": row,
                "exact_f32_bits": bool(
                    np.array_equal(
                        row_scalar.view(np.uint32), row_vector.view(np.uint32)
                    )
                ),
                "sha256": _sha256_f32(row_vector),
            }
        )

    result = {
        "layer": layer,
        "expert": expert,
        "tensor": name,
        "shard": loc.file.name,
        "quantization": loc.type_name,
        "shape": [rows, cols],
        "encoded_bytes": matrix_bytes,
        "decoded_bytes": int(vector.nbytes),
        "encoded_sha256": hashlib.sha256(encoded).hexdigest(),
        "decoded_f32_sha256": _sha256_f32(vector),
        "read_seconds": read_seconds,
        "scalar_decode_seconds": scalar_seconds,
        "vector_decode_seconds": vector_seconds,
        "exact_f32_bits": mismatch_locations.size == 0,
        "mismatch_count": int(mismatch_locations.size),
        "first_mismatch": (
            int(mismatch_locations[0]) if mismatch_locations.size else None
        ),
        "deterministic_repeat_sha256": hashes,
        "deterministic_repeat": hashes[0] == hashes[1],
        "signed_zero_count": int(np.count_nonzero(vector_bits == 0x80000000)),
        "rows_checked": row_results,
    }
    del scalar, vector, repeated
    gc.collect()
    return result, encoded, rows, cols


def qualify(model: Path) -> dict[str, Any]:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before real qualification")
    routes = _route_map()
    before = sample_pressure().to_public_dict()
    store = Glm52TensorStore(model)
    cases: list[dict[str, Any]] = []
    benchmark_input: tuple[bytes, int, int] | None = None
    try:
        for layer in QUALIFICATION_LAYERS:
            case, encoded, rows, cols = _compare_case(
                store, layer=layer, expert=routes[layer]
            )
            cases.append(case)
            if benchmark_input is None:
                benchmark_input = (encoded, rows, cols)
    finally:
        store.close()
    assert benchmark_input is not None
    encoded, rows, cols = benchmark_input

    vector_function = lambda: dequantize_matrix_iq2_xxs_numpy(encoded, rows, cols)
    scalar_function = lambda: _scalar_matrix(encoded, rows, cols)
    vector_samples, vector_hashes = _timed_samples(
        vector_function, warmups=3, samples=10
    )
    scalar_samples, scalar_hashes = _timed_samples(
        scalar_function, warmups=3, samples=10
    )

    gc.collect()
    allocation_before = sample_pressure().to_public_dict()
    tracemalloc.start()
    instrumented_start = time.perf_counter()
    instrumented = vector_function()
    instrumented_seconds = time.perf_counter() - instrumented_start
    traced_current, traced_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    allocation_after = sample_pressure().to_public_dict()
    del instrumented

    weights = rows * cols
    vector_summary = _summary(vector_samples)
    scalar_summary = _summary(scalar_samples)
    case_gate = all(
        case["exact_f32_bits"]
        and case["deterministic_repeat"]
        and all(row["exact_f32_bits"] for row in case["rows_checked"])
        for case in cases
    )
    sample_gate = (
        len(set(vector_hashes)) == 1
        and len(set(scalar_hashes)) == 1
        and vector_hashes[0] == scalar_hashes[0]
    )
    return {
        "schema": "pulsarmlx.research.glm52-iq2-xxs-numpy-qualification",
        "schema_version": "1.0.0",
        "feature_id": "016-glm52-full-execution",
        "actual_status": "passed" if case_gate and sample_gate else "failed",
        **source,
        "checkpoint": _checkpoint_identity(),
        "machine": _machine(),
        "decoder_modes": ["scalar_reference", "numpy_vectorized"],
        "scalar_oracle_imports_mlx": False,
        "cases": cases,
        "benchmark": {
            "case": {
                "layer": cases[0]["layer"],
                "expert": cases[0]["expert"],
                "tensor": cases[0]["tensor"],
                "weights": weights,
                "encoded_bytes": len(encoded),
            },
            "warmups_per_mode": 3,
            "samples_per_mode": 10,
            "vector_raw_seconds": vector_samples,
            "scalar_raw_seconds": scalar_samples,
            "vector_summary": vector_summary,
            "scalar_summary": scalar_summary,
            "vector_weights_per_second_median": weights
            / float(vector_summary["median_seconds"]),
            "scalar_weights_per_second_median": weights
            / float(scalar_summary["median_seconds"]),
            "median_speedup": float(scalar_summary["median_seconds"])
            / float(vector_summary["median_seconds"]),
            "vector_output_hashes": vector_hashes,
            "scalar_output_hashes": scalar_hashes,
            "exact_and_deterministic_outputs": sample_gate,
        },
        "allocation_observation": {
            "instrumented_vector_seconds": instrumented_seconds,
            "tracemalloc_current_bytes": traced_current,
            "tracemalloc_peak_bytes": traced_peak,
            "rss_before_bytes": allocation_before["rss_bytes"],
            "rss_after_bytes": allocation_after["rss_bytes"],
            "rss_delta_bytes": (
                allocation_after["rss_bytes"] - allocation_before["rss_bytes"]
                if allocation_before["rss_bytes"] is not None
                and allocation_after["rss_bytes"] is not None
                else None
            ),
            "peak_rss_after_bytes": allocation_after["peak_rss_bytes"],
            "decoded_output_bytes": weights * 4,
            "instrumentation_changes_timing": True,
        },
        "resource_before": before,
        "resource_after": sample_pressure().to_public_dict(),
        "unsupported_interpretations": [
            "complete routed expert speedup",
            "complete MoE speedup",
            "full-stack speedup",
            "token generation speedup",
            "non-IQ2_XXS acceleration",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    model = os.environ.get("PULSARMLX_GLM_GGUF")
    if not model:
        raise SystemExit("PULSARMLX_GLM_GGUF is required; no checkpoint was searched")
    result = qualify(Path(model))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(
        json.dumps(
            {
                "actual_status": result["actual_status"],
                "case_count": len(result["cases"]),
                "median_speedup": result["benchmark"]["median_speedup"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
