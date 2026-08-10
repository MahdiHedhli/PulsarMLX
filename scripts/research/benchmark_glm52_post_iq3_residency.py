#!/usr/bin/env python3
"""Process-isolated host-buffer and MLX-ready reuse study for dense hotspots."""

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

from glm52_dense_primitives import (  # noqa: E402
    EPS_DEFAULT,
    _load_scalar_dense_matrix,
    embed_token,
    load_f32_vector,
    matvec_weight_profiled,
    rms_norm,
)
from glm52_inference import _checkpoint_identity, _source_identity  # noqa: E402
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore  # noqa: E402
MODE = "whole_matrix_numpy_q5_q8_q6_head_numpy"
WARMUPS = 3
MEASURED = 10
CANDIDATES = ("transient", "decoded_host_rebuild", "mlx_ready")
TARGETS = {
    "output_q4": {
        "tensor": "output.weight",
        "quantization": "Q4_K",
        "shape": [6144, 154880],
        "activation": "normalized_token_embedding_profile_fixture",
        "transient_record": "docs/research/glm52/raw/post-f018-output-head-profile-0001.json",
    },
    "late_attention_q5": {
        "tensor": "blk.78.attn_output.weight",
        "quantization": "Q5_K",
        "shape": [16384, 6144],
        "activation": "deterministic_sine_fixture",
        "transient_record": None,
    },
}


def _summary_nonnegative(samples: list[float]) -> dict[str, float | int]:
    if not samples or any(not math.isfinite(value) or value < 0 for value in samples):
        raise ValueError("samples must be finite and nonnegative")
    values = np.asarray(samples, dtype=np.float64)
    mean = float(values.mean())
    standard_deviation = float(values.std(ddof=1)) if len(samples) > 1 else 0.0
    return {
        "sample_count": len(samples),
        "median_seconds": float(np.median(values)),
        "mean_seconds": mean,
        "standard_deviation_seconds": standard_deviation,
        "minimum_seconds": float(values.min()),
        "maximum_seconds": float(values.max()),
        "p5_seconds": float(np.percentile(values, 5)),
        "p25_seconds": float(np.percentile(values, 25)),
        "p75_seconds": float(np.percentile(values, 75)),
        "p95_seconds": float(np.percentile(values, 95)),
        "coefficient_of_variation": standard_deviation / mean if mean else 0.0,
    }


def _hash(values: Any) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f4").reshape(-1).tobytes()).hexdigest()


def _cleanup() -> float:
    import mlx.core as mx

    started = time.perf_counter()
    gc.collect()
    clear = getattr(mx, "clear_cache", None)
    if clear is not None:
        clear()
    return time.perf_counter() - started


def _activation(store: Glm52TensorStore, target: str, cols: int) -> np.ndarray:
    if target == "output_q4":
        values = rms_norm(
            embed_token(store, 9703),
            load_f32_vector(store, "output_norm.weight"),
            EPS_DEFAULT,
        )
        return np.asarray(values, dtype=np.float32)
    index = np.arange(cols, dtype=np.float64)
    return np.asarray(np.sin(index * 0.0019) * 0.25, dtype=np.float32)


def _load_host(store: Glm52TensorStore, tensor: str) -> tuple[np.ndarray, dict[str, Any]]:
    loc = store.tensors[tensor]
    cols, rows = map(int, loc.dims)
    flat, metrics = _load_scalar_dense_matrix(store, loc, cols, rows, MODE)
    buffer_started = time.perf_counter()
    host = np.ascontiguousarray(np.asarray(flat, dtype=np.float32).reshape(rows, cols))
    conversion_seconds = time.perf_counter() - buffer_started
    del flat
    return host, {
        "storage_read_count": metrics.storage_read_count,
        "storage_bytes_read": metrics.encoded_bytes,
        "storage_read_seconds": metrics.storage_read_seconds,
        "dequant_seconds": metrics.dequant_seconds,
        "contiguous_buffer_seconds": metrics.contiguous_buffer_seconds + conversion_seconds,
        "decoder_mode": metrics.decoder_mode,
    }


def _worker(model: Path, target: str, candidate: str) -> dict[str, Any]:
    import mlx.core as mx

    definition = TARGETS[target]
    tensor = str(definition["tensor"])
    before = sample_pressure().to_public_dict()
    if before["level"] != "normal":
        raise RuntimeError(f"normal memory pressure required, got {before['level']}")
    store = Glm52TensorStore(model)
    try:
        loc = store.tensors[tensor]
        cols, rows = map(int, loc.dims)
        if loc.type_name != definition["quantization"] or [cols, rows] != definition["shape"]:
            raise RuntimeError(f"{target}: tensor identity changed")
        activation = _activation(store, target, cols)
        setup_started = time.perf_counter()
        setup: dict[str, Any] = {
            "storage_read_count": 0,
            "storage_bytes_read": 0,
            "storage_read_seconds": 0.0,
            "dequant_seconds": 0.0,
            "contiguous_buffer_seconds": 0.0,
            "mlx_matrix_build_seconds": 0.0,
        }
        host: np.ndarray | None = None
        matrix = None
        if candidate != "transient":
            host, setup_load = _load_host(store, tensor)
            setup.update(setup_load)
            if candidate == "mlx_ready":
                build_started = time.perf_counter()
                matrix = mx.array(host, dtype=mx.float32)
                mx.eval(matrix)
                setup["mlx_matrix_build_seconds"] = time.perf_counter() - build_started
                del host
                host = None
        setup["total_seconds"] = time.perf_counter() - setup_started
        after_setup = sample_pressure().to_public_dict()
        if after_setup["level"] != "normal":
            raise RuntimeError(f"{candidate}: memory pressure changed to {after_setup['level']}")

        def once() -> tuple[dict[str, Any], str]:
            total_started = time.perf_counter()
            if candidate == "transient":
                output, operation = matvec_weight_profiled(store, tensor, activation.tolist(), read_mode=MODE)
                sample = operation.to_dict()
                output_array = np.asarray(output, dtype=np.float32)
                del output
            else:
                local_matrix = matrix
                build_seconds = 0.0
                if candidate == "decoded_host_rebuild":
                    build_started = time.perf_counter()
                    local_matrix = mx.array(host, dtype=mx.float32)
                    mx.eval(local_matrix)
                    build_seconds = time.perf_counter() - build_started
                matvec_started = time.perf_counter()
                output_value = local_matrix @ mx.array(activation, dtype=mx.float32)
                mx.eval(output_value)
                output_array = np.asarray(output_value, dtype=np.float32)
                matvec_seconds = time.perf_counter() - matvec_started
                sample = {
                    "storage_read_count": 0,
                    "encoded_bytes": 0,
                    "storage_read_seconds": 0.0,
                    "dequant_seconds": 0.0,
                    "contiguous_buffer_seconds": 0.0,
                    "mlx_matrix_build_seconds": build_seconds,
                    "mlx_matvec_seconds": matvec_seconds,
                    "total_seconds": time.perf_counter() - total_started,
                    "decoder_mode": "retained_host_f32" if candidate == "decoded_host_rebuild" else "retained_mlx_f32",
                }
                del output_value
                if candidate == "decoded_host_rebuild":
                    del local_matrix
            output_hash = _hash(output_array)
            del output_array
            sample["cleanup_seconds"] = _cleanup()
            sample["total_with_cleanup_seconds"] = sample["total_seconds"] + sample["cleanup_seconds"]
            sample["resource_after"] = sample_pressure().to_public_dict()
            return sample, output_hash

        for _ in range(WARMUPS):
            once()
        samples = []
        hashes = []
        for index in range(MEASURED):
            sample, output_hash = once()
            sample["sample_index"] = index
            samples.append(sample)
            hashes.append(output_hash)
        retained_rss = sample_pressure().to_public_dict()
        matrix = None
        host = None
        teardown_started = time.perf_counter()
        teardown_cleanup = _cleanup()
        teardown_seconds = time.perf_counter() - teardown_started
        after_teardown = sample_pressure().to_public_dict()
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
            "setup": setup,
            "setup_rss_delta_bytes": after_setup["rss_bytes"] - before["rss_bytes"],
            "retained_rss_bytes": retained_rss["rss_bytes"],
            "samples": samples,
            "summaries": {
                field: _summary_nonnegative([float(sample[field]) for sample in samples])
                for field in fields
            },
            "determinism": {"unique_output_hashes": len(set(hashes)), "output_f32_sha256": sorted(set(hashes))},
            "resource_before": before,
            "resource_after_setup": after_setup,
            "resource_after_teardown": after_teardown,
            "teardown_cleanup_seconds": teardown_cleanup,
            "teardown_seconds": teardown_seconds,
        }
    finally:
        store.close()


def _child(model: Path, target: str, candidate: str) -> dict[str, Any]:
    env = dict(os.environ)
    env["PULSARMLX_GLM_GGUF"] = str(model)
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--target", target, "--worker", candidate],
        capture_output=True,
        text=True,
        env=env,
    )
    if completed.returncode:
        raise RuntimeError(f"{target}/{candidate} failed: {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def benchmark(model: Path, target: str) -> dict[str, Any]:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before checkpoint measurement")
    definition = TARGETS[target]
    candidates = CANDIDATES
    baseline_hashes: list[str] = []
    if definition["transient_record"]:
        candidates = tuple(candidate for candidate in candidates if candidate != "transient")
        baseline = json.loads(Path(str(definition["transient_record"])).read_text())
        baseline_hashes = list(baseline["determinism"]["output_f32_sha256"])
    results = [_child(model, target, candidate) for candidate in candidates]
    hashes = set(baseline_hashes)
    for result in results:
        hashes.update(result["determinism"]["output_f32_sha256"])
    passed = (
        len(hashes) == 1
        and all(result["determinism"]["unique_output_hashes"] == 1 for result in results)
        and all(result["resource_after_setup"]["level"] == "normal" for result in results)
        and all(result["resource_after_teardown"]["level"] == "normal" for result in results)
    )
    record = {
        "schema": "pulsarmlx.research.post-f018-dense-residency",
        "schema_version": "1.0.0",
        "feature_id": "018-direct-quantized-metal-runtime",
        "experiment_id": f"post-f018-{target}-residency-0001",
        "actual_status": "passed" if passed else "failed",
        "source": {"commit": source["source_commit"], "dirty": source["source_dirty"]},
        "checkpoint": _checkpoint_identity(),
        "environment": {
            "machine_class": "apple_silicon_m1_ultra",
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
            "mlx_version": version("mlx"),
            "storage_role": "internal_ssd",
        },
        "binding": {
            "target": target,
            "tensor": definition["tensor"],
            "quantization": definition["quantization"],
            "shape": definition["shape"],
            "activation_kind": definition["activation"],
        },
        "protocol": {
            "process_isolation": "one fresh process per measured candidate",
            "warmups": WARMUPS,
            "measured_samples": MEASURED,
            "mlx_synchronized": True,
            "changed_variable": "decoded host buffer versus evaluated MLX matrix lifetime only",
            "transient_baseline_record": definition["transient_record"],
        },
        "candidates": results,
        "comparison": {"exact_output_hash_across_candidates": len(hashes) == 1, "output_f32_sha256": sorted(hashes)},
        "unsupported_interpretations": [
            "complete-layer or token speedup",
            "decoded-all trunk admission",
            "production cache policy",
            "direct quantized Metal qualification",
        ],
    }
    assert_public_safe(record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=TARGETS)
    parser.add_argument("--worker", choices=CANDIDATES)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    model_value = os.environ.get("PULSARMLX_GLM_GGUF")
    if not model_value:
        raise SystemExit("PULSARMLX_GLM_GGUF is required; no checkpoint was searched")
    if args.worker:
        result = _worker(Path(model_value), args.target, args.worker)
        assert_public_safe(result)
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
        return 0
    if args.out is None:
        raise SystemExit("--out is required")
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite {args.out}")
    record = benchmark(Path(model_value), args.target)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_name(f".{args.out.name}.tmp")
    temporary.write_text(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
    temporary.replace(args.out)
    print(json.dumps({"actual_status": record["actual_status"], "target": args.target}, sort_keys=True))
    return 0 if record["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
