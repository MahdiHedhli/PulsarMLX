#!/usr/bin/env python3
"""Qualify one real IQ2_XXS gate/up matrix through the direct Metal boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_glm52_matrix_boundary import (  # noqa: E402
    _activation,
    _component_summaries,
    _run_once,
)
from f018_numerical_contract import (  # noqa: E402
    CLASS_NUMERICALLY_FAILED,
    classify_boundary,
)
from glm52_expert_cache_runtime import MlxMatrixBackend  # noqa: E402
from glm52_inference import _checkpoint_identity, _source_identity  # noqa: E402
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore, nbytes_for_tensor  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAYER = 3
EXPERT = 15
TOKEN_ID = 9703
WARMUPS = 3
MEASURED = 30
PROJECTIONS = ("gate", "up")


def _f32_bytes(values: list[float]) -> bytes:
    return np.asarray(values, dtype="<f4").tobytes()


def _f32_sha256(values: list[float]) -> str:
    return hashlib.sha256(_f32_bytes(values)).hexdigest()


def _decode_output_bits(bits: Any, rows: int) -> list[float]:
    if not isinstance(bits, list) or len(bits) != rows:
        raise ValueError("Metal runner output length does not match matrix rows")
    values = [struct.unpack("<f", struct.pack("<I", int(value)))[0] for value in bits]
    if not all(np.isfinite(values)):
        raise ValueError("Metal runner output contains non-finite values")
    return values


def _bit_mismatches(reference: list[float], candidate: list[float]) -> tuple[int, int | None]:
    left = np.asarray(reference, dtype=np.float32).view(np.uint32)
    right = np.asarray(candidate, dtype=np.float32).view(np.uint32)
    mismatches = np.flatnonzero(left != right)
    return int(mismatches.size), int(mismatches[0]) if mismatches.size else None


def _validate_runner_record(
    record: dict[str, Any],
    *,
    source_commit: str,
    rows: int,
    columns: int,
    packed_sha256: str,
    activation_sha256: str,
) -> None:
    if record.get("schema") != "pulsarmlx.internal.f018-iq2-metal-runner":
        raise ValueError("unexpected Metal runner schema")
    if record.get("schema_version") != "1.1.0":
        raise ValueError("strict Metal runner schema version mismatch")
    if record.get("source") != {"commit": source_commit, "dirty": False}:
        raise ValueError("Metal runner source identity mismatch")
    expected_binding = {
        "rows": rows,
        "columns": columns,
        "packed_sha256": packed_sha256,
        "activation_sha256": activation_sha256,
    }
    binding = record.get("binding", {})
    if any(binding.get(key) != value for key, value in expected_binding.items()):
        raise ValueError("Metal runner immutable input binding mismatch")
    if record.get("protocol") != {"warmups": WARMUPS, "measured": MEASURED}:
        raise ValueError("Metal runner measurement protocol mismatch")
    if record.get("cpu_fallback_count") != 0:
        raise ValueError("Metal runner used a CPU fallback")
    if record.get("complete_f32_weight_materialized_bytes") != 0:
        raise ValueError("Metal candidate materialized a complete f32 matrix")
    if record.get("unique_output_hashes") != 1:
        raise ValueError("Metal runner was not deterministic")
    setup = record.get("setup", {})
    compiler = setup.get("compiler", {})
    if (
        compiler.get("fast_math_enabled") is not False
        or compiler.get("language_version") != "3.2"
        or compiler.get("math_mode") != "safe"
        or compiler.get("math_floating_point_functions") != "precise"
        or compiler.get("pipeline_identity")
        != "iq2_xxs_sequential_scaffold_v1"
    ):
        raise ValueError("strict Metal runner compiler contract mismatch")
    for field in (
        "compilation_seconds",
        "pipeline_creation_seconds",
        "registration_seconds",
        "peak_rss_bytes_after_measurement",
    ):
        value = setup.get(field)
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"Metal runner setup field is invalid: {field}")
    for component in ("total", "dispatch", "dispatch_preparation", "synchronization"):
        summary = record.get("timing", {}).get(component)
        if not isinstance(summary, dict) or summary.get("sample_count") != MEASURED:
            raise ValueError(f"Metal runner {component} samples are incomplete")
        raw = summary.get("measured_samples_seconds")
        if not isinstance(raw, list) or len(raw) != MEASURED:
            raise ValueError(f"Metal runner {component} raw samples are incomplete")


def _run_metal(
    runner: Path,
    *,
    packed: bytes,
    activation: list[float],
    rows: int,
    columns: int,
    source_commit: str,
) -> tuple[dict[str, Any], list[float]]:
    if not runner.is_file():
        raise FileNotFoundError(f"build the bounded Metal runner first: {runner.name}")
    activation_bytes = _f32_bytes(activation)
    packed_sha256 = hashlib.sha256(packed).hexdigest()
    activation_sha256 = hashlib.sha256(activation_bytes).hexdigest()
    with tempfile.TemporaryDirectory(prefix="pulsarmlx-f018-") as temporary:
        root = Path(temporary)
        packed_path = root / "matrix.iq2_xxs"
        activation_path = root / "activation.f32"
        output_path = root / "result.json"
        packed_path.write_bytes(packed)
        activation_path.write_bytes(activation_bytes)
        subprocess.run(
            [
                str(runner),
                "--packed",
                str(packed_path),
                "--activation",
                str(activation_path),
                "--rows",
                str(rows),
                "--columns",
                str(columns),
                "--out",
                str(output_path),
            ],
            cwd=ROOT,
            check=True,
        )
        record = json.loads(output_path.read_text())
    _validate_runner_record(
        record,
        source_commit=source_commit,
        rows=rows,
        columns=columns,
        packed_sha256=packed_sha256,
        activation_sha256=activation_sha256,
    )
    candidate = _decode_output_bits(record["output_f32_bits"], rows)
    if _f32_sha256(candidate) != record["output_sha256"]:
        raise ValueError("Metal runner output hash does not match returned f32 bits")
    return record, candidate


def benchmark(model: Path, runner: Path, *, projection: str) -> dict[str, Any]:
    if projection not in PROJECTIONS:
        raise ValueError(f"unsupported projection: {projection}")
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before real checkpoint measurement")
    resource_before = sample_pressure().to_public_dict()
    if resource_before["level"] != "normal":
        raise RuntimeError(
            f"real matrix admission requires normal memory pressure, got {resource_before['level']}"
        )
    checkpoint = _checkpoint_identity()
    store = Glm52TensorStore(model)
    scalar = MlxMatrixBackend("scalar_reference")
    vector = MlxMatrixBackend("numpy_vectorized")
    try:
        if store.arch() != "glm-dsa" or len(store.shards) != checkpoint["file_count"]:
            raise RuntimeError("checkpoint catalog does not match the admitted GLM binding")
        if sum(int(shard["size"]) for shard in store.shards) != checkpoint["total_bytes"]:
            raise RuntimeError("checkpoint shard sizes do not match the admitted GLM binding")
        tensor = f"blk.{LAYER}.ffn_{projection}_exps.weight"
        location = store.tensors[tensor]
        if location.type_id != 16 or location.type_name != "IQ2_XXS" or len(location.dims) != 3:
            raise RuntimeError("frozen target is not a three-dimensional IQ2_XXS tensor")
        columns, rows, experts = map(int, location.dims)
        if not 0 <= EXPERT < experts:
            raise RuntimeError("frozen expert index is outside the tensor")
        activation, activation_identity = _activation(store, "gate")
        if len(activation) != columns:
            raise RuntimeError("frozen activation length does not match the target matrix")
        matrix_bytes = nbytes_for_tensor(location.type_id, rows * columns)
        storage_start = time.perf_counter()
        packed = store.pread(tensor, EXPERT * matrix_bytes, matrix_bytes)
        checkpoint_storage_seconds = time.perf_counter() - storage_start
        if len(packed) != matrix_bytes:
            raise OSError("real IQ2_XXS matrix read was truncated")

        scalar_sample, scalar_output = _run_once(scalar, store, tensor, activation)
        for _ in range(WARMUPS):
            _run_once(vector, store, tensor, activation)
        optimized_samples: list[dict[str, Any]] = []
        optimized_hashes: set[str] = set()
        optimized_output: list[float] | None = None
        for sample_index in range(MEASURED):
            sample, output = _run_once(vector, store, tensor, activation)
            sample["sample_index"] = sample_index
            optimized_samples.append(sample)
            optimized_hashes.add(sample["output_f32_sha256"])
            optimized_output = output
        if optimized_output is None:
            raise RuntimeError("optimized reference did not produce an output")
        optimized_exact = _f32_bytes(scalar_output) == _f32_bytes(optimized_output)
        if not optimized_exact or len(optimized_hashes) != 1:
            raise RuntimeError("optimized NumPy/MLX reference diverged from the scalar path")

        metal, candidate = _run_metal(
            runner,
            packed=packed,
            activation=activation,
            rows=rows,
            columns=columns,
            source_commit=source["source_commit"],
        )
        numerical = classify_boundary(
            reference=scalar_output,
            candidate=candidate,
            boundary="matrix",
            reference_argmax=None,
            candidate_argmax=None,
            identity_matches=True,
            routes_match=True,
            deterministic=metal["unique_output_hashes"] == 1,
            cpu_fallback_count=metal["cpu_fallback_count"],
            complete_f32_weight_materialized_bytes=metal[
                "complete_f32_weight_materialized_bytes"
            ],
        )
        bit_mismatch_count, first_bit_mismatch = _bit_mismatches(
            scalar_output, candidate
        )
        correctness = {
            **numerical,
            "greedy_applicable": False,
            "deterministic_repetitions": MEASURED,
            "unique_output_hashes": metal["unique_output_hashes"],
            "candidate_output_sha256": metal["output_sha256"],
            "reference_output_sha256": _f32_sha256(scalar_output),
            "optimized_reference_output_sha256": _f32_sha256(optimized_output),
            "f32_bit_mismatch_count": bit_mismatch_count,
            "first_f32_bit_mismatch_index": first_bit_mismatch,
            "optimized_reference_exact_f32_bits": optimized_exact,
        }
        resource_after = sample_pressure().to_public_dict()
        passed = (
            numerical["classification"] != CLASS_NUMERICALLY_FAILED
            and optimized_exact
            and len(optimized_hashes) == 1
            and resource_after["level"] == "normal"
        )
        direct_total = metal["timing"]["total"]
        record = {
            "schema": "pulsarmlx.research.f018-direct-iq2-xxs",
            "schema_version": "1.1.0",
            "feature_id": "018-direct-quantized-metal-runtime",
            "actual_status": "passed" if passed else "failed",
            "classification": numerical["classification"],
            "source": {"commit": source["source_commit"], "dirty": False},
            "checkpoint": checkpoint,
            "environment": {
                "machine_class": "apple_silicon_m1_ultra",
                "architecture": platform.machine(),
                "metal_device": metal["device"],
                "python_version": platform.python_version(),
                "numpy_version": np.__version__,
                "storage_role": "internal_ssd",
            },
            "binding": {
                "layer": LAYER,
                "expert_id": EXPERT,
                "projection": projection,
                "tensor_name": tensor,
                "shard_filename": location.file.name,
                "quantization": location.type_name,
                "shape": [rows, columns],
                "packed_bytes": matrix_bytes,
                "packed_sha256": hashlib.sha256(packed).hexdigest(),
                "activation_identity": activation_identity,
                "activation_token_id": TOKEN_ID,
                "activation_length": len(activation),
                "activation_sha256": _f32_sha256(activation),
                "reference_output_sha256": _f32_sha256(scalar_output),
            },
            "kernel": {
                "quantization": "IQ2_XXS",
                "role": projection,
                "packed_block_bytes": 66,
                "values_per_block": 256,
                "accumulation": "f32_sequential_per_output_row",
                "dispatch_geometry": "one_logical_thread_per_output_row",
                "pipeline_identity": metal["setup"]["compiler"]["pipeline_identity"],
                "compiler": metal["setup"]["compiler"],
                "cpu_fallback_count": metal["cpu_fallback_count"],
                "complete_f32_weight_materialized_bytes": metal[
                    "complete_f32_weight_materialized_bytes"
                ],
            },
            "correctness": correctness,
            "protocol": {
                "scalar_reference_samples": 1,
                "optimized_reference_warmups": WARMUPS,
                "optimized_reference_measured": MEASURED,
                "direct_metal_warmups": WARMUPS,
                "direct_metal_measured": MEASURED,
                "timer": "time.perf_counter and mach_absolute_time-backed Metal command timestamps",
                "mlx_synchronized": True,
                "os_page_cache_controlled": False,
            },
            "setup": {
                "checkpoint_storage_read_count": 1,
                "checkpoint_storage_bytes": matrix_bytes,
                "checkpoint_storage_seconds": checkpoint_storage_seconds,
                "packed_temp_read_seconds": metal["setup"]["packed_read_seconds"],
                "slab_copy_seconds": metal["setup"]["slab_copy_seconds"],
                "registration_seconds": metal["setup"]["registration_seconds"],
                "compilation_seconds": metal["setup"]["compilation_seconds"],
                "pipeline_creation_seconds": metal["setup"][
                    "pipeline_creation_seconds"
                ],
                "process_first": metal["process_first"],
                "slab_logical_bytes": metal["setup"]["slab_logical_bytes"],
                "slab_allocated_bytes": metal["setup"]["slab_allocated_bytes"],
                "runner_peak_rss_bytes": metal["setup"][
                    "peak_rss_bytes_after_measurement"
                ],
            },
            "scalar_reference": scalar_sample,
            "optimized_reference": {
                "identity": vector.identity(),
                "samples": optimized_samples,
                "summaries": _component_summaries(optimized_samples),
                "deterministic": len(optimized_hashes) == 1,
                "exact_f32_bits_vs_scalar": optimized_exact,
            },
            "timing": {
                **direct_total,
                "storage_read_seconds": checkpoint_storage_seconds,
                "dispatch": metal["timing"]["dispatch"],
                "dispatch_preparation": metal["timing"]["dispatch_preparation"],
                "synchronization": metal["timing"]["synchronization"],
                "kernel": metal["timing"]["kernel"],
            },
            "resource": resource_after,
            "resource_before": resource_before,
            "claim_boundary": f"one real layer-{LAYER} expert-{EXPERT} IQ2_XXS {projection} matrix",
            "unsupported_interpretations": [
                "complete routed expert speedup",
                "complete MoE or transformer-layer speedup",
                "full-stack inference or token-generation speedup",
                "general direct-quantized Metal support",
                "production readiness",
            ],
        }
        assert_public_safe(record)
        return record
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--projection", choices=PROJECTIONS, default="gate")
    parser.add_argument(
        "--runner",
        type=Path,
        default=ROOT / "target/debug/iq2-metal-matrix",
    )
    args = parser.parse_args()
    model = os.environ.get("PULSARMLX_GLM_GGUF")
    if not model:
        raise SystemExit("PULSARMLX_GLM_GGUF is required; checkpoint discovery is disabled")
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite existing evidence: {args.out}")
    result = benchmark(Path(model), args.runner, projection=args.projection)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_name(f".{args.out.name}.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.out)
    print(
        json.dumps(
            {
                "actual_status": result["actual_status"],
                "classification": result["classification"],
                "projection": result["binding"]["projection"],
                "direct_median_seconds": result["timing"]["median_seconds"],
                "optimized_median_seconds": result["optimized_reference"]["summaries"][
                    "total_seconds"
                ]["median_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
