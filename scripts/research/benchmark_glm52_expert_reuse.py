#!/usr/bin/env python3
"""Bounded process-isolated lifecycle study for one recurrent routed expert."""

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

from glm52_dense_primitives import dense_read_mode, embed_token, require_mlx_backend  # noqa: E402
from glm52_expert_cache_runtime import DecodedMatrix, MlxMatrixBackend  # noqa: E402
from glm52_inference import _checkpoint_identity, _source_identity, silu  # noqa: E402
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_mla import CompactKVCache, mla_forward_token  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore, nbytes_for_tensor  # noqa: E402
from iq2_xxs_dequant import dequantize_matrix_iq2_xxs_numpy  # noqa: E402
from iq3_xxs_dequant import dequantize_matrix_iq3_xxs_numpy  # noqa: E402

LAYER = 64
EXPERT = 183
TOKEN_ID = 9703
WARMUPS = 3
MEASURED = 10
CANDIDATES = ("transient", "decoded_host_rebuild", "mlx_ready_reuse")
DENSE_MODE = "whole_matrix_numpy_q5_q8_q6_head_numpy"
PROJECTIONS = ("gate", "up", "down")


def _summary(values: list[float]) -> dict[str, float | int]:
    if not values or any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("samples must be finite and nonnegative")
    array = np.asarray(values, dtype=np.float64)
    mean = float(array.mean())
    sd = float(array.std(ddof=1)) if len(array) > 1 else 0.0
    return {"sample_count": len(values), "median_seconds": float(np.median(array)), "mean_seconds": mean, "standard_deviation_seconds": sd, "minimum_seconds": float(array.min()), "maximum_seconds": float(array.max()), "p5_seconds": float(np.percentile(array, 5)), "p25_seconds": float(np.percentile(array, 25)), "p75_seconds": float(np.percentile(array, 75)), "p95_seconds": float(np.percentile(array, 95)), "coefficient_of_variation": sd / mean if mean else 0.0}


def _cleanup(backend: MlxMatrixBackend) -> float:
    start = time.perf_counter()
    backend.release_transient()
    return time.perf_counter() - start


def _hash(values: list[float]) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f4").tobytes()).hexdigest()


def _decode_host(store: Glm52TensorStore, name: str, expert: int) -> tuple[np.ndarray, dict[str, Any]]:
    loc = store.tensors[name]
    cols, rows, experts = map(int, loc.dims)
    if not 0 <= expert < experts:
        raise IndexError(expert)
    row_bytes = nbytes_for_tensor(loc.type_id, cols)
    compressed_bytes = row_bytes * rows
    start = time.perf_counter()
    raw = store.pread(name, expert * compressed_bytes, compressed_bytes)
    read_seconds = time.perf_counter() - start
    if len(raw) != compressed_bytes:
        raise OSError(f"{name}: truncated expert slab")
    decoder = {16: dequantize_matrix_iq2_xxs_numpy, 18: dequantize_matrix_iq3_xxs_numpy}.get(loc.type_id)
    if decoder is None:
        raise TypeError(f"{name}: unsupported bounded reuse quantization {loc.type_name}")
    start = time.perf_counter()
    decoded = decoder(raw, rows, cols)
    decode_seconds = time.perf_counter() - start
    if decoded.dtype != np.float32 or not decoded.flags.c_contiguous:
        raise ValueError("decoder must return contiguous f32")
    return decoded, {"storage_read_count": 1, "storage_bytes_read": compressed_bytes, "storage_read_seconds": read_seconds, "dequant_seconds": decode_seconds, "contiguous_buffer_seconds": 0.0, "quantization": loc.type_name, "shape_rows_cols": [rows, cols], "decoded_f32_bytes": rows * cols * 4}


def _matrix_from_host(backend: MlxMatrixBackend, decoded: np.ndarray, metadata: dict[str, Any]) -> tuple[DecodedMatrix, dict[str, float]]:
    construct_start = time.perf_counter()
    value = backend.mx.array(decoded, dtype=backend.mx.float32).reshape(tuple(metadata["shape_rows_cols"]))
    construct_seconds = time.perf_counter() - construct_start
    eval_start = time.perf_counter()
    backend.mx.eval(value)
    eval_seconds = time.perf_counter() - eval_start
    rows, cols = metadata["shape_rows_cols"]
    return DecodedMatrix(value=value, rows=rows, cols=cols, decoded_bytes=metadata["decoded_f32_bytes"], compressed_bytes=metadata["storage_bytes_read"], quantization=metadata["quantization"], decoder_mode="numpy_vectorized"), {"mlx_matrix_construct_seconds": construct_seconds, "mlx_matrix_eval_seconds": eval_seconds, "mlx_matrix_build_seconds": construct_seconds + eval_seconds}


def _worker(model: Path, candidate: str) -> dict[str, Any]:
    pressure_before = sample_pressure().to_public_dict()
    if pressure_before["level"] != "normal":
        raise RuntimeError(f"resource admission requires normal pressure, got {pressure_before['level']}")
    backend = MlxMatrixBackend("numpy_vectorized")
    store = Glm52TensorStore(model)
    try:
        with require_mlx_backend(), dense_read_mode(DENSE_MODE):
            embedded = embed_token(store, TOKEN_ID)
            activation, _ = mla_forward_token(store, LAYER, embedded, CompactKVCache(), 0)
        activation_hash = _hash(activation)
        names = {projection: f"blk.{LAYER}.ffn_{projection}_exps.weight" for projection in PROJECTIONS}
        hosts: dict[str, np.ndarray] = {}
        host_meta: dict[str, dict[str, Any]] = {}
        matrices: dict[str, DecodedMatrix] = {}
        setup = {"storage_read_count": 0, "storage_bytes_read": 0, "storage_read_seconds": 0.0, "dequant_seconds": 0.0, "contiguous_buffer_seconds": 0.0, "mlx_matrix_construct_seconds": 0.0, "mlx_matrix_eval_seconds": 0.0, "mlx_matrix_build_seconds": 0.0}
        rss_before_setup = sample_pressure().to_public_dict()["rss_bytes"]
        if candidate != "transient":
            for projection, name in names.items():
                decoded, metadata = _decode_host(store, name, EXPERT)
                hosts[projection] = decoded
                host_meta[projection] = metadata
                for field in ("storage_read_count", "storage_bytes_read", "storage_read_seconds", "dequant_seconds", "contiguous_buffer_seconds"):
                    setup[field] += metadata[field]
                if candidate == "mlx_ready_reuse":
                    matrix, build = _matrix_from_host(backend, decoded, metadata)
                    matrices[projection] = matrix
                    for field, value in build.items():
                        setup[field] += value
            if candidate == "mlx_ready_reuse":
                hosts.clear()
        pressure_after_setup = sample_pressure().to_public_dict()

        def run_once() -> tuple[dict[str, Any], str]:
            totals = {"storage_read_count": 0, "storage_bytes_read": 0, "storage_read_seconds": 0.0, "dequant_seconds": 0.0, "contiguous_buffer_seconds": 0.0, "mlx_matrix_construct_seconds": 0.0, "mlx_matrix_eval_seconds": 0.0, "mlx_matrix_build_seconds": 0.0, "mlx_matvec_seconds": 0.0, "activation_swiglu_seconds": 0.0, "weighting_seconds": 0.0, "cleanup_seconds": 0.0}
            total_start = time.perf_counter()
            def get_matrix(projection: str) -> DecodedMatrix:
                if candidate == "transient":
                    matrix, metrics = backend.load(store, names[projection], EXPERT)
                    totals["storage_read_count"] += metrics.storage_read_count
                    totals["storage_bytes_read"] += metrics.storage_bytes_read
                    totals["storage_read_seconds"] += metrics.storage_read_seconds
                    totals["dequant_seconds"] += metrics.dequant_seconds
                    totals["contiguous_buffer_seconds"] += metrics.contiguous_buffer_seconds
                    totals["mlx_matrix_construct_seconds"] += metrics.matrix_construct_seconds
                    totals["mlx_matrix_eval_seconds"] += metrics.matrix_eval_seconds
                    totals["mlx_matrix_build_seconds"] += metrics.matrix_build_seconds
                elif candidate == "decoded_host_rebuild":
                    matrix, build = _matrix_from_host(backend, hosts[projection], host_meta[projection])
                    for field, value in build.items():
                        totals[field] += value
                else:
                    matrix = matrices[projection]
                return matrix

            gate_matrix = get_matrix("gate")
            gate, seconds = backend.matvec(gate_matrix, activation)
            totals["mlx_matvec_seconds"] += seconds
            if candidate != "mlx_ready_reuse":
                gate_matrix = None
                totals["cleanup_seconds"] += _cleanup(backend)
            up_matrix = get_matrix("up")
            up, seconds = backend.matvec(up_matrix, activation)
            totals["mlx_matvec_seconds"] += seconds
            if candidate != "mlx_ready_reuse":
                up_matrix = None
                totals["cleanup_seconds"] += _cleanup(backend)
            start = time.perf_counter()
            hidden = [silu(a) * b for a, b in zip(gate, up, strict=True)]
            totals["activation_swiglu_seconds"] += time.perf_counter() - start
            down_matrix = get_matrix("down")
            down, seconds = backend.matvec(down_matrix, hidden)
            totals["mlx_matvec_seconds"] += seconds
            if candidate != "mlx_ready_reuse":
                down_matrix = None
                totals["cleanup_seconds"] += _cleanup(backend)
            start = time.perf_counter()
            output = [float(value) for value in down]
            totals["weighting_seconds"] += time.perf_counter() - start
            totals["total_with_cleanup_seconds"] = time.perf_counter() - total_start
            totals["total_without_cleanup_seconds"] = max(0.0, totals["total_with_cleanup_seconds"] - totals["cleanup_seconds"])
            totals["resource_after"] = sample_pressure().to_public_dict()
            return totals, _hash(output)

        for _ in range(WARMUPS):
            run_once()
        samples, hashes = [], []
        for index in range(MEASURED):
            sample, output_hash = run_once()
            sample["sample_index"] = index
            samples.append(sample)
            hashes.append(output_hash)
        fields = ("storage_read_seconds", "dequant_seconds", "contiguous_buffer_seconds", "mlx_matrix_construct_seconds", "mlx_matrix_eval_seconds", "mlx_matrix_build_seconds", "mlx_matvec_seconds", "activation_swiglu_seconds", "weighting_seconds", "cleanup_seconds", "total_without_cleanup_seconds", "total_with_cleanup_seconds")
        matrices.clear(); hosts.clear(); host_meta.clear()
        teardown_seconds = _cleanup(backend)
        return {"candidate": candidate, "layer": LAYER, "expert_id": EXPERT, "route_history_contract": "selected in all nine frozen golden-eight stacks and all eight adjacent intervals", "representative_activation": {"identity": "layer-64 MLA(token_embedding[9703], position=0)", "f32_sha256": activation_hash}, "setup": setup, "setup_rss_delta_bytes": pressure_after_setup["rss_bytes"] - rss_before_setup, "pressure_before_setup": pressure_before, "pressure_after_setup": pressure_after_setup, "samples": samples, "summaries": {field: _summary([float(sample[field]) for sample in samples]) for field in fields}, "deterministic_output_f32_sha256": sorted(set(hashes)), "teardown_cleanup_seconds": teardown_seconds, "pressure_after_teardown": sample_pressure().to_public_dict()}
    finally:
        store.close()


def _run_child(model: Path, candidate: str) -> dict[str, Any]:
    env = dict(os.environ); env["PULSARMLX_GLM_GGUF"] = str(model)
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", candidate], text=True, capture_output=True, env=env)
    if completed.returncode:
        raise RuntimeError(f"{candidate} worker failed: {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def benchmark(model: Path) -> dict[str, Any]:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before real checkpoint measurement")
    candidates = [_run_child(model, candidate) for candidate in CANDIDATES]
    hashes = {item for candidate in candidates for item in candidate["deterministic_output_f32_sha256"]}
    passed = len(hashes) == 1 and all(len(candidate["samples"]) == MEASURED for candidate in candidates) and all(candidate["pressure_after_setup"]["level"] == "normal" and candidate["pressure_after_teardown"]["level"] == "normal" for candidate in candidates)
    return {"schema": "pulsarmlx.research.glm52-routed-expert-reuse", "schema_version": "1.0.0", "feature_id": "post-f016-moe-optimization", "experiment_id": "routed-expert-64-183-reuse-0001", "actual_status": "passed" if passed else "failed", **source, "checkpoint": _checkpoint_identity(), "environment": {"machine_class": "apple_silicon_m1_ultra", "architecture": platform.machine(), "python_version": platform.python_version(), "numpy_version": np.__version__, "mlx_version": version("mlx"), "storage_role": "internal_ssd"}, "protocol": {"process_isolation": "one fresh child process per candidate", "warmups_per_candidate": WARMUPS, "measured_samples_per_candidate": MEASURED, "timer": "time.perf_counter", "mlx_synchronized": True, "os_page_cache_controlled": False, "changed_variable": "routed expert matrix lifecycle only", "decoder_mode": "numpy_vectorized", "dense_mode_for_activation_fixture": DENSE_MODE}, "candidates": candidates, "comparison": {"exact_output_hash_across_all_candidates": len(hashes) == 1, "output_f32_sha256": sorted(hashes)}, "model_inference_executed": False, "unsupported_interpretations": ["complete MoE, layer, stack, P1, P2, or token speedup", "general routed-cache hit rate", "safe top-one-per-layer residency", "Rust or direct quantized Metal evidence"]}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path); parser.add_argument("--worker", choices=CANDIDATES); args = parser.parse_args()
    model_value = os.environ.get("PULSARMLX_GLM_GGUF")
    if not model_value:
        raise SystemExit("PULSARMLX_GLM_GGUF is required; no checkpoint was searched")
    model = Path(model_value)
    if args.worker:
        result = _worker(model, args.worker); assert_public_safe(result); print(json.dumps(result, separators=(",", ":"), sort_keys=True)); return 0
    if args.output is None:
        raise SystemExit("--output is required outside worker mode")
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.output}")
    result = benchmark(model); assert_public_safe(result); args.output.parent.mkdir(parents=True, exist_ok=True); temporary = args.output.with_name(f".{args.output.name}.tmp"); temporary.write_text(json.dumps(result, separators=(",", ":"), sort_keys=True) + "\n"); temporary.replace(args.output); print(json.dumps({"actual_status": result["actual_status"], "exact": result["comparison"]["exact_output_hash_across_all_candidates"]}, sort_keys=True)); return 0 if result["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
