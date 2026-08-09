#!/usr/bin/env python3
"""Bounded process-isolated residency study for one real Q6_K trunk matrix."""

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
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ggml_kquants import dequantize_matrix_q6_k_numpy  # noqa: E402
from glm52_inference import _checkpoint_identity, _source_identity  # noqa: E402
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore  # noqa: E402
from qualify_iq2_xxs_numpy import _summary  # noqa: E402

TENSOR = "blk.8.attn_output.weight"
CANDIDATES = ("transient", "compressed_resident", "decoded_hot", "hybrid_compressed_decoded_hot")
WARMUPS = 3
MEASURED = 10


def _cleanup() -> float:
    start = time.perf_counter()
    gc.collect()
    try:
        import mlx.core as mx

        clear = getattr(mx, "clear_cache", None)
        if clear is not None:
            clear()
    except ImportError:
        pass
    return time.perf_counter() - start


def _activation(cols: int) -> list[float]:
    return [math.sin(index * 0.0019) * 0.25 for index in range(cols)]


def _worker(model: Path, candidate: str) -> dict[str, Any]:
    import mlx.core as mx

    pressure_before = sample_pressure().to_public_dict()
    if pressure_before["level"] != "normal":
        raise RuntimeError(f"resource admission requires normal pressure, got {pressure_before['level']}")
    store = Glm52TensorStore(model)
    try:
        loc = store.tensors[TENSOR]
        cols, rows = map(int, loc.dims)
        x = _activation(cols)
        encoded: bytes | None = None
        matrix = None
        setup = {
            "storage_read_count": 0,
            "storage_bytes_read": 0,
            "storage_read_seconds": 0.0,
            "dequant_seconds": 0.0,
            "mlx_matrix_build_seconds": 0.0,
        }
        rss_before_setup = pressure_before["rss_bytes"]
        if candidate in {"compressed_resident", "decoded_hot", "hybrid_compressed_decoded_hot"}:
            start = time.perf_counter()
            encoded = store.pread(TENSOR, 0, loc.n_bytes)
            setup["storage_read_seconds"] = time.perf_counter() - start
            setup["storage_read_count"] = 1
            setup["storage_bytes_read"] = len(encoded)
            if len(encoded) != loc.n_bytes:
                raise OSError("truncated complete Q6_K matrix")
        if candidate in {"decoded_hot", "hybrid_compressed_decoded_hot"}:
            start = time.perf_counter()
            decoded = dequantize_matrix_q6_k_numpy(encoded, rows, cols)
            setup["dequant_seconds"] = time.perf_counter() - start
            start = time.perf_counter()
            matrix = mx.array(decoded, dtype=mx.float32).reshape((rows, cols))
            mx.eval(matrix)
            setup["mlx_matrix_build_seconds"] = time.perf_counter() - start
            del decoded
            if candidate == "decoded_hot":
                encoded = None
        pressure_after_setup = sample_pressure().to_public_dict()

        def run_once() -> tuple[dict[str, Any], str]:
            local_encoded = encoded
            local_matrix = matrix
            total_start = time.perf_counter()
            storage_start = time.perf_counter()
            storage_count = 0
            storage_bytes = 0
            if candidate == "transient":
                local_encoded = store.pread(TENSOR, 0, loc.n_bytes)
                storage_count = 1
                storage_bytes = len(local_encoded)
            storage_seconds = time.perf_counter() - storage_start
            decode_seconds = 0.0
            build_seconds = 0.0
            if local_matrix is None:
                decode_start = time.perf_counter()
                decoded = dequantize_matrix_q6_k_numpy(local_encoded, rows, cols)
                decode_seconds = time.perf_counter() - decode_start
                build_start = time.perf_counter()
                local_matrix = mx.array(decoded, dtype=mx.float32).reshape((rows, cols))
                mx.eval(local_matrix)
                build_seconds = time.perf_counter() - build_start
                del decoded
            matvec_start = time.perf_counter()
            y = local_matrix @ mx.array(x, dtype=mx.float32)
            mx.eval(y)
            output = np.asarray(y, dtype=np.float32)
            matvec_seconds = time.perf_counter() - matvec_start
            output_hash = hashlib.sha256(output.astype("<f4", copy=False).tobytes()).hexdigest()
            total_seconds = time.perf_counter() - total_start
            if matrix is None:
                del local_matrix
            del y, output
            cleanup_seconds = _cleanup()
            return {
                "storage_read_count": storage_count,
                "storage_bytes_read": storage_bytes,
                "storage_read_seconds": storage_seconds,
                "dequant_seconds": decode_seconds,
                "contiguous_buffer_seconds": 0.0,
                "mlx_matrix_build_seconds": build_seconds,
                "mlx_matvec_seconds": matvec_seconds,
                "total_seconds": total_seconds,
                "cleanup_seconds": cleanup_seconds,
                "total_with_cleanup_seconds": total_seconds + cleanup_seconds,
                "resource_after": sample_pressure().to_public_dict(),
            }, output_hash

        for _ in range(WARMUPS):
            run_once()
        samples = []
        hashes = []
        for index in range(MEASURED):
            sample, output_hash = run_once()
            sample["sample_index"] = index
            samples.append(sample)
            hashes.append(output_hash)
        teardown_start = time.perf_counter()
        matrix = None
        encoded = None
        teardown_cleanup_seconds = _cleanup()
        teardown_seconds = time.perf_counter() - teardown_start
        pressure_after_teardown = sample_pressure().to_public_dict()
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
            "candidate": candidate,
            "tensor": {
                "name": loc.name,
                "quantization": loc.type_name,
                "shape_rows_cols": [rows, cols],
                "compressed_bytes": loc.n_bytes,
                "decoded_f32_bytes": rows * cols * 4,
                "shard": loc.file.name,
            },
            "setup": setup,
            "setup_rss_delta_bytes": pressure_after_setup["rss_bytes"] - rss_before_setup,
            "samples": samples,
            "summaries": {field: _summary([float(sample[field]) for sample in samples]) for field in fields},
            "deterministic_output_sha256": sorted(set(hashes)),
            "pressure_before_setup": pressure_before,
            "pressure_after_setup": pressure_after_setup,
            "teardown_cleanup_seconds": teardown_cleanup_seconds,
            "teardown_seconds": teardown_seconds,
            "pressure_after_teardown": pressure_after_teardown,
            "lifecycle": {
                "transient": "read, decode, build, matvec, and cleanup each use",
                "compressed_resident": "one setup read; decode, build, matvec, and cleanup each use",
                "decoded_hot": "one setup read/decode/build; retain MLX matrix; matvec each use",
                "hybrid_compressed_decoded_hot": "retain both compressed bytes and decoded MLX matrix; matvec each use",
            }[candidate],
        }
    finally:
        store.close()


def _run_child(model: Path, candidate: str) -> dict[str, Any]:
    env = dict(os.environ)
    env["PULSARMLX_GLM_GGUF"] = str(model)
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker", candidate],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(completed.stdout)


def benchmark(model: Path) -> dict[str, Any]:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before real checkpoint measurement")
    candidates = [_run_child(model, candidate) for candidate in CANDIDATES]
    hashes = {value for candidate in candidates for value in candidate["deterministic_output_sha256"]}
    passed = (
        len(hashes) == 1
        and all(len(candidate["samples"]) == MEASURED for candidate in candidates)
        and all(candidate["pressure_after_setup"]["level"] == "normal" for candidate in candidates)
        and all(candidate["pressure_after_teardown"]["level"] == "normal" for candidate in candidates)
    )
    budgets = json.loads((Path(__file__).resolve().parents[2] / "docs/research/glm52/raw/f016-golden8-post-run-calculations-0001.json").read_text())["trunk_residency_memory_budgets"]
    return {
        "schema": "pulsarmlx.research.glm52-trunk-residency-microbenchmark",
        "schema_version": "1.0.0",
        "feature_id": "post-f016-trunk-optimization",
        "experiment_id": "trunk-q6-residency-0001",
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
        "protocol": {
            "process_isolation": "one fresh child process per candidate",
            "warmups_per_candidate": WARMUPS,
            "measured_samples_per_candidate": MEASURED,
            "timer": "time.perf_counter",
            "mlx_synchronized": True,
            "os_page_cache_controlled": False,
            "changed_variable": "matrix residency lifecycle only; exact Q6_K NumPy decoder, activation, MLX matvec, and checkpoint remain fixed",
        },
        "candidates": candidates,
        "logical_full_trunk_budgets": budgets,
        "comparison": {
            "exact_output_hash_across_all_candidates": len(hashes) == 1,
            "output_f32_sha256": sorted(hashes),
        },
        "model_inference_executed": False,
        "recommendation_scope": "representative matrix lifecycle plus previously committed logical catalog budgets; not allocator proof for all-trunk residency",
        "unsupported_interpretations": [
            "complete layer, P1, or token speedup",
            "decoded-all or compressed-all runtime admission",
            "production cache policy",
            "Rust or direct quantized Metal evidence",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", choices=CANDIDATES)
    args = parser.parse_args()
    model_value = os.environ.get("PULSARMLX_GLM_GGUF")
    if not model_value:
        raise SystemExit("PULSARMLX_GLM_GGUF is required; no checkpoint was searched")
    model = Path(model_value)
    if args.worker:
        result = _worker(model, args.worker)
        assert_public_safe(result)
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
        return 0
    if args.output is None:
        raise SystemExit("--output is required outside worker mode")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.output}")
    result = benchmark(model)
    assert_public_safe(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp")
    temporary.write_text(json.dumps(result, separators=(",", ":"), sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(json.dumps({"actual_status": result["actual_status"], "exact": result["comparison"]["exact_output_hash_across_all_candidates"]}, sort_keys=True))
    return 0 if result["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
