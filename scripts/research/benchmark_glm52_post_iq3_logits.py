#!/usr/bin/env python3
"""Profile the current full-vocabulary Q4_K output-head boundary."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glm52_dense_primitives import (  # noqa: E402
    EPS_DEFAULT,
    embed_token,
    load_f32_vector,
    matvec_weight_profiled,
    rms_norm,
)
from glm52_inference import _checkpoint_identity, _source_identity  # noqa: E402
from glm52_memory_pressure import sample_pressure  # noqa: E402
from glm52_telemetry import assert_public_safe  # noqa: E402
from glm52_tensor_store import Glm52TensorStore  # noqa: E402
from qualify_iq2_xxs_numpy import _summary  # noqa: E402

TENSOR = "output.weight"
TOKEN_ID = 9703
MODE = "whole_matrix_numpy_q5_q8_q6_head_numpy"
WARMUPS = 3
MEASURED = 10
FIELDS = (
    "storage_read_seconds",
    "dequant_seconds",
    "contiguous_buffer_seconds",
    "mlx_matrix_build_seconds",
    "mlx_matvec_seconds",
    "total_seconds",
    "cleanup_seconds",
    "total_with_cleanup_seconds",
)


def _hash(values: list[float]) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<f4").tobytes()).hexdigest()


def _cleanup() -> float:
    import mlx.core as mx

    import time

    started = time.perf_counter()
    gc.collect()
    clear_cache = getattr(mx, "clear_cache", None)
    if clear_cache is not None:
        clear_cache()
    return time.perf_counter() - started


def _once(store: Glm52TensorStore, activation: list[float]) -> tuple[dict[str, Any], str]:
    before = sample_pressure().to_public_dict()
    if before["level"] != "normal":
        raise RuntimeError("output-head profile requires normal memory pressure")
    output, metrics = matvec_weight_profiled(store, TENSOR, activation, read_mode=MODE)
    result = metrics.to_dict()
    result["cleanup_seconds"] = _cleanup()
    result["total_with_cleanup_seconds"] = result["total_seconds"] + result["cleanup_seconds"]
    result["resource_before"] = before
    result["resource_after"] = sample_pressure().to_public_dict()
    output_hash = _hash(output)
    del output
    return result, output_hash


def benchmark(model: Path) -> dict[str, Any]:
    source = _source_identity()
    if source["source_dirty"]:
        raise RuntimeError("worktree must be clean before output-head profiling")
    resource_before = sample_pressure().to_public_dict()
    if resource_before["level"] != "normal":
        raise RuntimeError("output-head profiling requires normal memory pressure")
    store = Glm52TensorStore(model)
    try:
        activation = rms_norm(
            embed_token(store, TOKEN_ID),
            load_f32_vector(store, "output_norm.weight"),
            EPS_DEFAULT,
        )
        activation_hash = _hash(activation)
        loc = store.tensors[TENSOR]
        if loc.type_name != "Q4_K" or list(map(int, loc.dims)) != [6144, 154880]:
            raise RuntimeError("output-head tensor identity changed")
        for _ in range(WARMUPS):
            _once(store, activation)
        samples = []
        hashes = []
        for index in range(MEASURED):
            sample, output_hash = _once(store, activation)
            sample["sample_index"] = index
            samples.append(sample)
            hashes.append(output_hash)
            print(json.dumps({"progress": "post-iq3-output-head", "measured": index + 1}), flush=True)
        unique_hashes = sorted(set(hashes))
        passed = (
            len(unique_hashes) == 1
            and all(sample["decoder_mode"] == "scalar_reference" for sample in samples)
            and all(sample["storage_read_count"] == 1 for sample in samples)
            and all(sample["resource_after"]["level"] == "normal" for sample in samples)
        )
        record = {
            "schema": "pulsarmlx.research.post-f018-output-head-profile",
            "schema_version": "1.0.0",
            "feature_id": "018-direct-quantized-metal-runtime",
            "experiment_id": "post-f018-output-head-profile-0001",
            "actual_status": "passed" if passed else "failed",
            "classification": "deterministic_current_path" if passed else "failed",
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
                "tensor": TENSOR,
                "quantization": loc.type_name,
                "shape": list(map(int, loc.dims)),
                "compressed_bytes": int(loc.n_bytes),
                "decoded_f32_bytes": int(loc.n_elem) * 4,
                "activation_kind": "normalized_token_embedding_profile_fixture",
                "activation_f32_sha256": activation_hash,
            },
            "protocol": {
                "read_mode": MODE,
                "decoder_mode": "scalar_reference",
                "warmups": WARMUPS,
                "measured_samples": MEASURED,
                "mlx_synchronized": True,
                "os_page_cache_controlled": False,
                "changed_variable": "none; attribution of the existing output-head path",
            },
            "samples": samples,
            "summaries": {
                field: _summary([float(sample[field]) for sample in samples])
                for field in FIELDS
            },
            "determinism": {
                "unique_output_hashes": len(unique_hashes),
                "output_f32_sha256": unique_hashes,
            },
            "resource_before": resource_before,
            "resource_after": sample_pressure().to_public_dict(),
            "unsupported_interpretations": [
                "greedy-token correctness from this synthetic activation",
                "complete layer or stack timing",
                "direct Q4_K Metal qualification",
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
    print(json.dumps({"actual_status": record["actual_status"], "median_seconds": record["summaries"]["total_seconds"]["median_seconds"]}, sort_keys=True))
    return 0 if record["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
