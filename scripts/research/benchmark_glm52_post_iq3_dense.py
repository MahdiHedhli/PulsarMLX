#!/usr/bin/env python3
"""Profile current GLM dense/MLA operations across representative layers."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import platform
import sys
import time
from collections import defaultdict
from importlib.metadata import version
from pathlib import Path
from typing import Any, Iterable

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glm52_dense_primitives import (  # noqa: E402
    DenseOperationMetrics,
    capture_dense_metrics,
    dense_read_mode,
    embed_token,
    require_mlx_backend,
)
from glm52_inference import _checkpoint_identity, _source_identity  # noqa: E402
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_mla import CompactKVCache, mla_forward_token  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore  # noqa: E402
from qualify_iq2_xxs_numpy import _summary  # noqa: E402

LAYERS = (3, 8, 40, 78)
TOKEN_ID = 9703
REFERENCE_MODE = "whole_matrix_scalar"
CANDIDATE_MODE = "whole_matrix_numpy_q5_q8_q6_head_numpy"
WARMUPS = 3
MEASURED = 10
STAGE_FIELDS = (
    "storage_read_seconds",
    "dequant_seconds",
    "contiguous_buffer_seconds",
    "mlx_matrix_build_seconds",
    "mlx_matvec_seconds",
    "total_seconds",
)


def _f32_sha256(values: Iterable[float]) -> str:
    return hashlib.sha256(np.asarray(list(values), dtype="<f4").tobytes()).hexdigest()


def _cleanup() -> float:
    import mlx.core as mx

    started = time.perf_counter()
    gc.collect()
    clear_cache = getattr(mx, "clear_cache", None)
    if clear_cache is not None:
        clear_cache()
    return time.perf_counter() - started


def group_operations(operations: list[DenseOperationMetrics]) -> list[dict[str, Any]]:
    """Aggregate per-head records without hiding their slice count."""

    grouped: dict[tuple[str, str, int, int], list[DenseOperationMetrics]] = defaultdict(list)
    for operation in operations:
        grouped[(operation.tensor, operation.quantization, operation.rows, operation.cols)].append(operation)
    rows = []
    for (tensor, quantization, matrix_rows, matrix_cols), values in sorted(grouped.items()):
        decoder_modes = sorted({value.decoder_mode for value in values})
        read_modes = sorted({value.read_mode for value in values})
        if len(decoder_modes) != 1 or len(read_modes) != 1:
            raise RuntimeError(f"{tensor}: mixed execution modes within one sample")
        rows.append(
            {
                "tensor": tensor,
                "quantization": quantization,
                "shape_rows_cols_per_slice": [matrix_rows, matrix_cols],
                "slice_count": len(values),
                "slice_indices": sorted(
                    value.slice_index for value in values if value.slice_index is not None
                ),
                "encoded_bytes": sum(value.encoded_bytes for value in values),
                "storage_read_count": sum(value.storage_read_count for value in values),
                "read_mode": read_modes[0],
                "decoder_mode": decoder_modes[0],
                **{
                    field: sum(float(getattr(value, field)) for value in values)
                    for field in STAGE_FIELDS
                },
            }
        )
    return rows


def _run_layer(store: Glm52TensorStore, layer: int, residual: list[float], mode: str) -> tuple[list[float], dict[str, Any]]:
    pressure_before = sample_pressure().to_public_dict()
    if pressure_before["level"] != "normal":
        raise RuntimeError(f"layer {layer}: resource admission requires normal pressure")
    started = time.perf_counter()
    with require_mlx_backend(), dense_read_mode(mode), capture_dense_metrics() as capture:
        output, diagnostics = mla_forward_token(store, layer, residual, CompactKVCache(), 0)
    wall_seconds = time.perf_counter() - started
    cleanup_seconds = _cleanup()
    operations = group_operations(capture.operations)
    attributed = sum(float(row["total_seconds"]) for row in operations)
    return output, {
        "layer": layer,
        "mode": mode,
        "wall_seconds": wall_seconds,
        "cleanup_seconds": cleanup_seconds,
        "wall_with_cleanup_seconds": wall_seconds + cleanup_seconds,
        "dense_operation_count": len(capture.operations),
        "dense_tensor_count": len(operations),
        "dense_attributed_seconds": attributed,
        "orchestration_other_seconds": wall_seconds - attributed,
        "operations": operations,
        "diagnostics": diagnostics,
        "output_f32_sha256": _f32_sha256(output),
        "resource_before": pressure_before,
        "resource_after": sample_pressure().to_public_dict(),
    }


def _tensor_summaries(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_tensor: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        for operation in sample["operations"]:
            by_tensor[operation["tensor"]].append(operation)
    rows = []
    for tensor, values in sorted(by_tensor.items()):
        first = values[0]
        if len(values) != len(samples):
            raise RuntimeError(f"{tensor}: missing measured sample")
        rows.append(
            {
                "tensor": tensor,
                "quantization": first["quantization"],
                "shape_rows_cols_per_slice": first["shape_rows_cols_per_slice"],
                "slice_count": first["slice_count"],
                "encoded_bytes_per_use": first["encoded_bytes"],
                "storage_read_count_per_use": first["storage_read_count"],
                "read_mode": first["read_mode"],
                "decoder_mode": first["decoder_mode"],
                "summaries": {
                    field: _summary([float(value[field]) for value in values])
                    for field in STAGE_FIELDS
                },
            }
        )
    return rows


def _layer_summaries(samples: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "wall_seconds",
        "cleanup_seconds",
        "wall_with_cleanup_seconds",
        "dense_attributed_seconds",
        "orchestration_other_seconds",
    )
    return {
        field: _summary([float(sample[field]) for sample in samples])
        for field in fields
    }


def benchmark(model: Path) -> dict[str, Any]:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before post-IQ3 dense profiling")
    before = sample_pressure().to_public_dict()
    if before["level"] != "normal":
        raise RuntimeError("post-IQ3 dense profiling requires normal memory pressure")
    store = Glm52TensorStore(model)
    try:
        residual = embed_token(store, TOKEN_ID)
        layer_records = []
        for layer in LAYERS:
            reference_output, reference = _run_layer(
                store, layer, residual, REFERENCE_MODE
            )
            reference_hash = _f32_sha256(reference_output)
            del reference_output
            for _ in range(WARMUPS):
                output, _ = _run_layer(store, layer, residual, CANDIDATE_MODE)
                del output
            samples = []
            for index in range(MEASURED):
                output, sample = _run_layer(store, layer, residual, CANDIDATE_MODE)
                sample["sample_index"] = index
                samples.append(sample)
                del output
                print(json.dumps({"progress": "post-iq3-dense", "layer": layer, "measured": index + 1}), flush=True)
            hashes = sorted({sample["output_f32_sha256"] for sample in samples})
            exact = hashes == [reference_hash]
            if not exact:
                raise RuntimeError(f"layer {layer}: vector dense output diverged from scalar oracle")
            layer_records.append(
                {
                    "layer": layer,
                    "reference": {
                        "mode": REFERENCE_MODE,
                        "wall_seconds": reference["wall_seconds"],
                        "dense_attributed_seconds": reference["dense_attributed_seconds"],
                        "output_f32_sha256": reference_hash,
                    },
                    "candidate_samples": samples,
                    "candidate_summaries": _layer_summaries(samples),
                    "tensor_summaries": _tensor_summaries(samples),
                    "comparison": {
                        "exact_f32_output_hash": exact,
                        "deterministic_output_hashes": hashes,
                    },
                }
            )
        record = {
            "schema": "pulsarmlx.research.post-f018-dense-multilayer-profile",
            "schema_version": "1.0.0",
            "feature_id": "018-direct-quantized-metal-runtime",
            "experiment_id": "post-f018-dense-multilayer-profile-0001",
            "actual_status": "passed",
            "classification": "golden_identical",
            "source": {
                "commit": source["source_commit"],
                "dirty": source["source_dirty"],
            },
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
                "layers": list(LAYERS),
                "token_id": TOKEN_ID,
                "position": 0,
                "reference_mode": REFERENCE_MODE,
                "candidate_mode": CANDIDATE_MODE,
                "warmups_per_layer": WARMUPS,
                "measured_samples_per_layer": MEASURED,
                "timer": "time.perf_counter",
                "mlx_synchronized": True,
                "os_page_cache_controlled": False,
                "claim_boundary": "independent position-0 MLA boundaries with per-tensor dense attribution",
            },
            "layers": layer_records,
            "resource_before": before,
            "resource_after": sample_pressure().to_public_dict(),
            "unsupported_interpretations": [
                "sequential 79-layer stack or token timing",
                "long-context DSA indexer cost",
                "output-head or logits attribution",
                "third-kernel selection without integration with P1 evidence",
                "production performance",
            ],
        }
        assert_public_safe(record)
        return record
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    model_value = os.environ.get("PULSARMLX_GLM_GGUF")
    if not model_value:
        raise SystemExit("PULSARMLX_GLM_GGUF is required; no checkpoint was searched")
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.out}")
    record = benchmark(Path(model_value))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_name(f".{args.out.name}.tmp")
    temporary.write_text(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
    temporary.replace(args.out)
    print(json.dumps({"actual_status": record["actual_status"], "layers": list(LAYERS)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
