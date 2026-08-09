#!/usr/bin/env python3
"""Benchmark one real expert matrix through read, decode, MLX build, and matvec."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glm52_dense_primitives import embed_token, load_f32_vector, rms_norm  # noqa: E402
from glm52_expert import _silu, expert_matvec  # noqa: E402
from glm52_expert_cache_runtime import MlxMatrixBackend  # noqa: E402
from glm52_inference import _checkpoint_identity, _source_identity  # noqa: E402
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_mla import RMS_EPS  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore, nbytes_for_tensor  # noqa: E402
from qualify_iq2_xxs_numpy import _summary  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAYER = 3
EXPERT = 15
PROJECTIONS = {
    "gate": {"type_id": 16, "quantization": "IQ2_XXS"},
    "down": {"type_id": 18, "quantization": "IQ3_XXS"},
}


def _sha256_f32(values: list[float]) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f4").tobytes()).hexdigest()


def _mlx_memory(backend: MlxMatrixBackend) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for public_name, method_name in (
        ("active_bytes", "get_active_memory"),
        ("peak_bytes", "get_peak_memory"),
        ("cache_bytes", "get_cache_memory"),
    ):
        method = getattr(backend.mx, method_name, None)
        try:
            result[public_name] = int(method()) if method is not None else None
        except Exception:
            result[public_name] = None
    return result


def _activation(store: Glm52TensorStore, projection: str) -> tuple[list[float], str]:
    embedded = embed_token(store, 9703)
    norm = load_f32_vector(store, f"blk.{LAYER}.ffn_norm.weight")
    normalized = rms_norm(embedded, norm, RMS_EPS)
    if projection == "gate":
        return normalized, "rms_norm(token_embedding[9703], blk.3.ffn_norm.weight)"
    if projection == "down":
        gate = expert_matvec(
            store, f"blk.{LAYER}.ffn_gate_exps.weight", EXPERT, normalized
        )
        up = expert_matvec(
            store, f"blk.{LAYER}.ffn_up_exps.weight", EXPERT, normalized
        )
        swiglu = [_silu(left) * right for left, right in zip(gate, up, strict=True)]
        return swiglu, (
            "scalar_reference_swiglu(blk.3.ffn_gate_exps.weight, "
            "blk.3.ffn_up_exps.weight, expert=15, token=9703)"
        )
    raise ValueError(f"unsupported matrix projection {projection}")


def _run_once(
    backend: MlxMatrixBackend,
    store: Glm52TensorStore,
    tensor: str,
    activation: list[float],
) -> tuple[dict[str, Any], list[float]]:
    resource_before = sample_pressure().to_public_dict()
    mlx_before = _mlx_memory(backend)
    total_start = time.perf_counter()
    matrix, load = backend.load(store, tensor, EXPERT)
    result, matvec_seconds = backend.matvec(matrix, activation)
    total_seconds = time.perf_counter() - total_start
    cleanup_start = time.perf_counter()
    del matrix
    backend.release_transient()
    cleanup_seconds = time.perf_counter() - cleanup_start
    record = {
        "decoder_mode": backend.decoder_mode,
        "storage_read_count": load.storage_read_count,
        "storage_bytes_read": load.storage_bytes_read,
        "storage_read_seconds": load.storage_read_seconds,
        "dequant_seconds": load.dequant_seconds,
        "contiguous_buffer_seconds": load.contiguous_buffer_seconds,
        "mlx_matrix_build_eval_seconds": load.matrix_build_seconds,
        "mlx_matvec_seconds": matvec_seconds,
        "total_seconds": total_seconds,
        "cleanup_seconds": cleanup_seconds,
        "total_with_cleanup_seconds": total_seconds + cleanup_seconds,
        "output_f32_sha256": _sha256_f32(result),
        "resource_before": resource_before,
        "resource_after": sample_pressure().to_public_dict(),
        "mlx_memory_before": mlx_before,
        "mlx_memory_after": _mlx_memory(backend),
    }
    return record, result


def _component_summaries(samples: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "storage_read_seconds",
        "dequant_seconds",
        "contiguous_buffer_seconds",
        "mlx_matrix_build_eval_seconds",
        "mlx_matvec_seconds",
        "total_seconds",
        "cleanup_seconds",
        "total_with_cleanup_seconds",
    )
    return {
        field: _summary([float(sample[field]) for sample in samples])
        for field in fields
    }


def _compare(left: list[float], right: list[float]) -> dict[str, Any]:
    lhs = np.asarray(left, dtype=np.float32)
    rhs = np.asarray(right, dtype=np.float32)
    delta = lhs.astype(np.float64) - rhs.astype(np.float64)
    mismatch = np.flatnonzero(lhs.view(np.uint32) != rhs.view(np.uint32))
    return {
        "compared_count": int(lhs.size),
        "exact_f32_bits": mismatch.size == 0,
        "mismatch_count": int(mismatch.size),
        "first_mismatch": int(mismatch[0]) if mismatch.size else None,
        "maximum_absolute_error": float(np.max(np.abs(delta))),
        "mean_absolute_error": float(np.mean(np.abs(delta))),
        "rmse": float(np.sqrt(np.mean(delta * delta))),
    }


def benchmark(model: Path, *, projection: str = "gate") -> dict[str, Any]:
    if projection not in PROJECTIONS:
        raise ValueError(f"unsupported matrix projection {projection}")
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before the real matrix benchmark")
    before = sample_pressure().to_public_dict()
    if before["level"] in {"critical", "urgent"}:
        raise RuntimeError(f"memory admission failed: {before['level']}")
    store = Glm52TensorStore(model)
    scalar = MlxMatrixBackend("scalar_reference")
    vector = MlxMatrixBackend("numpy_vectorized")
    try:
        identities = {"scalar_reference": scalar.identity(), "numpy_vectorized": vector.identity()}
        if any("gpu" not in identity["device"].lower() for identity in identities.values()):
            raise RuntimeError("matrix benchmark requires the MLX GPU device")
        tensor = f"blk.{LAYER}.ffn_{projection}_exps.weight"
        activation, activation_identity = _activation(store, projection)
        location = store.tensors[tensor]
        cols, rows, experts = map(int, location.dims)
        expected = PROJECTIONS[projection]
        if location.type_id != expected["type_id"] or not 0 <= EXPERT < experts:
            raise RuntimeError(
                f"frozen matrix is not an admitted {expected['quantization']} expert"
            )

        first_vector, first_output = _run_once(vector, store, tensor, activation)
        for _ in range(3):
            _run_once(scalar, store, tensor, activation)
            _run_once(vector, store, tensor, activation)

        measured: dict[str, list[dict[str, Any]]] = {
            "scalar_reference": [],
            "numpy_vectorized": [],
        }
        last_outputs: dict[str, list[float]] = {}
        for index in range(10):
            order = (
                ("numpy_vectorized", vector),
                ("scalar_reference", scalar),
            ) if index % 2 == 0 else (
                ("scalar_reference", scalar),
                ("numpy_vectorized", vector),
            )
            for mode, backend in order:
                sample, output = _run_once(backend, store, tensor, activation)
                sample["sample_index"] = index
                measured[mode].append(sample)
                last_outputs[mode] = output

        comparison = _compare(
            last_outputs["scalar_reference"], last_outputs["numpy_vectorized"]
        )
        deterministic = {
            mode: len({sample["output_f32_sha256"] for sample in samples}) == 1
            for mode, samples in measured.items()
        }
        exact_hash = (
            measured["scalar_reference"][0]["output_f32_sha256"]
            == measured["numpy_vectorized"][0]["output_f32_sha256"]
            == first_vector["output_f32_sha256"]
        )
        summaries = {
            mode: _component_summaries(samples) for mode, samples in measured.items()
        }
        actual_status = "passed" if (
            comparison["exact_f32_bits"]
            and exact_hash
            and all(deterministic.values())
            and first_vector["storage_read_count"] == 1
            and all(sample["storage_read_count"] == 1 for sample in measured["numpy_vectorized"])
            and all(sample["storage_read_count"] == rows for sample in measured["scalar_reference"])
        ) else "failed"
        disk = shutil.disk_usage(model)
        record = {
            "schema": "pulsarmlx.research.glm52-matrix-boundary-benchmark",
            "schema_version": "1.0.0",
            "feature_id": "016-glm52-full-execution",
            "actual_status": actual_status,
            **source,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "checkpoint": _checkpoint_identity(),
            "machine": {
                "architecture": platform.machine(),
                "chip": subprocess.check_output(
                    ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
                ).strip(),
                "macos": platform.mac_ver()[0],
                "logical_cpu_count": os.cpu_count(),
                "load_average_1m_5m_15m": list(os.getloadavg()),
                "python_version": platform.python_version(),
                "numpy_version": np.__version__,
                "storage_role": "internal_ssd",
                "storage_free_gib": round(disk.free / 1024**3, 1),
            },
            "backend_identities": identities,
            "matrix": {
                "layer": LAYER,
                "expert": EXPERT,
                "projection": projection,
                "tensor": tensor,
                "shard": location.file.name,
                "quantization": location.type_name,
                "shape": [rows, cols],
                "encoded_bytes": nbytes_for_tensor(location.type_id, rows * cols),
                "decoded_bytes": rows * cols * 4,
            },
            "activation": {
                "identity": activation_identity,
                "length": len(activation),
                "f32_sha256": _sha256_f32(activation),
            },
            "protocol": {
                "process_first_vector_samples": 1,
                "warmups_per_mode": 3,
                "measured_samples_per_mode": 10,
                "measurement_order": "counterbalanced_alternation_after_warmups",
                "timer": "time.perf_counter",
                "mlx_eval_synchronized": True,
                "os_page_cache_controlled": False,
            },
            "process_first_vector": first_vector,
            "samples": measured,
            "summaries": summaries,
            "comparison": comparison,
            "deterministic_outputs": deterministic,
            "exact_output_hash_across_modes": exact_hash,
            "resource_before": before,
            "resource_after": sample_pressure().to_public_dict(),
            "unsupported_interpretations": [
                "complete routed expert speedup",
                "complete MoE speedup",
                "complete transformer layer speedup",
                "full-stack or token-generation speedup",
                "controlled process-cold storage latency",
            ],
        }
        assert_public_safe(record)
        return record
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--projection", choices=tuple(PROJECTIONS), default="gate")
    args = parser.parse_args()
    model = os.environ.get("PULSARMLX_GLM_GGUF")
    if not model:
        raise SystemExit("PULSARMLX_GLM_GGUF is required; no checkpoint was searched")
    result = benchmark(Path(model), projection=args.projection)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(args.output)
    print(
        json.dumps(
            {
                "actual_status": result["actual_status"],
                "exact_f32_bits": result["comparison"]["exact_f32_bits"],
                "vector_total_median_seconds": result["summaries"]["numpy_vectorized"]["total_seconds"]["median_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
