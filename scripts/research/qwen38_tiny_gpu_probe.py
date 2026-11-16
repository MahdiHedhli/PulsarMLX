"""Bounded MLX GPU affine/fence/sampler probe on generated matrices only.

This observes one explicit stream synchronization and independent macOS/MLX
counters. It is not a production pager, device callback, or Qwen model oracle.
Run as a separately time-limited child process in the isolated Python 3.13 venv.
"""
from __future__ import annotations

import gc
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from qwen38_affine_probe import fixtures, packed_words, scalar_dequantize

GIB = 1024**3
MIB = 1024**2
MAX_FIXTURE_BYTES = 16 * 1024
MAX_MLX_BYTES = 16 * MIB
MAX_MLX_CACHE_BYTES = 8 * MIB
MAX_PROCESS_BYTES = 512 * MIB
MIN_FREE_BYTES = 16 * GIB
REFERENCE = (Path(__file__).resolve().parents[2] / "specs" /
             "021-qwen38-io-prefetch-spike" / "evidence" / "tiny-affine-reference-v1.json")
_QUARANTINED = []  # Retain owners in-process if device completion cannot be proved.


def _command(*args):
    result = subprocess.run(args, text=True, capture_output=True, check=True, timeout=3)
    return result.stdout


def parse_host(pressure, swap, rss):
    physical = re.search(r"The system has (\d+) \(", pressure)
    free = re.search(r"System-wide memory free percentage: (\d+)%", pressure)
    used = re.search(r"\bused = (\d+(?:\.\d+)?)M\b", swap)
    if not physical or not free or not used or not rss.strip().isdigit():
        raise RuntimeError("missing or malformed macOS memory observation")
    return {"physical_bytes": int(physical.group(1)), "free_percent": int(free.group(1)),
            "swap_used_mib": float(used.group(1)), "rss_bytes": int(rss.strip()) * 1024}


def host_observation():
    return parse_host(_command("/usr/bin/memory_pressure", "-Q"),
                      _command("/usr/sbin/sysctl", "-n", "vm.swapusage"),
                      _command("/bin/ps", "-o", "rss=", "-p", str(os.getpid())))


def check_observation(host, base_swap, mx=None):
    if (host["physical_bytes"] != 64 * GIB or
            host["physical_bytes"] * host["free_percent"] // 100 < MIN_FREE_BYTES or
            host["rss_bytes"] > MAX_PROCESS_BYTES or
            host["swap_used_mib"] > base_swap):
        raise RuntimeError("tiny GPU host memory/swap gate failed")
    if mx is not None and (mx.get_active_memory() > MAX_MLX_BYTES or
                           mx.get_peak_memory() > MAX_MLX_BYTES or
                           mx.get_cache_memory() > MAX_MLX_CACHE_BYTES):
        raise RuntimeError("tiny GPU MLX allocation gate failed")


def _reference():
    if REFERENCE.is_symlink() or REFERENCE.stat().st_size > 8192:
        raise RuntimeError("reference identity/size rejected")
    data = json.loads(REFERENCE.read_text())
    if data.get("schema") != "pulsarmlx.qwen38.tiny-affine-reference/1":
        raise RuntimeError("unexpected reference schema")
    return data["cases"]


def finish_stream(mx, stream, owners, observe, primary=None):
    """Drain the original stream before releasing owners; retain on fence error."""
    try:
        mx.synchronize(stream)
    except BaseException as fence_error:
        _QUARANTINED.extend((*owners, stream))
        errors = [fence_error] if primary is None else [primary, fence_error]
        group = ExceptionGroup if all(isinstance(e, Exception) for e in errors) else BaseExceptionGroup
        raise group("device fence failed; owners retained until process exit", errors)
    owners.clear()
    gc.collect()
    try:
        mx.clear_cache()
        observe()
    except BaseException as cleanup_error:
        if primary is not None:
            group = (ExceptionGroup if all(isinstance(e, Exception) for e in (primary, cleanup_error))
                     else BaseExceptionGroup)
            raise group("GPU probe and cleanup observations failed", [primary, cleanup_error])
        raise
    if primary is not None:
        raise primary.with_traceback(primary.__traceback__)


def run_tiny_gpu():
    if sys.version_info[:3] != (3, 13, 13) or sys.prefix == sys.base_prefix:
        raise RuntimeError("isolated Python 3.13.13 environment required")
    if (importlib.metadata.version("mlx") != "0.32.0" or
            importlib.metadata.version("mlx-metal") != "0.32.0"):
        raise RuntimeError("pinned MLX 0.32.0 wheels required")
    reference = _reference()
    baseline = host_observation()
    check_observation(baseline, baseline["swap_used_mib"])

    import mlx.core as mx
    if not mx.metal.is_available():
        raise RuntimeError("Metal device unavailable")
    mx.set_default_device(mx.gpu)
    mx.set_memory_limit(MAX_MLX_BYTES)  # advisory; sampled stops remain mandatory
    mx.set_cache_limit(MAX_MLX_CACHE_BYTES)  # advisory; observed gate is equal
    mx.reset_peak_memory()
    samples = []

    def observe(label):
        host = host_observation()
        check_observation(host, baseline["swap_used_mib"], mx)
        samples.append({"label": label, **host, "mlx_active_bytes": mx.get_active_memory(),
                        "mlx_cache_bytes": mx.get_cache_memory(),
                        "mlx_peak_bytes": mx.get_peak_memory()})

    observe("initialized")
    results = []
    for bits, group_size, rows, scales, biases in fixtures():
        key = f"{bits}:{group_size}"
        case = reference[key]
        if len(rows) != 2 or any(len(row) != case["columns"] for row in rows):
            raise RuntimeError("fixture/reference shape mismatch")
        words = packed_words(rows, bits)
        dense_expected = scalar_dequantize(words, scales, biases, bits, group_size)
        for row, col, value in case["samples"]:
            if dense_expected[row][col] != value:
                raise RuntimeError("independent literal reference mismatch")
        x_values = tuple(1.0 if i == 0 else (-2.0 if i == len(rows[0]) - 1 else 0.0)
                         for i in range(len(rows[0])))
        dense_x_values = tuple(2.0 ** -(i % 4) for i in range(len(rows[0])))
        if tuple(row[0] - 2 * row[-1] for row in dense_expected) != tuple(case["sparse_product"]):
            raise RuntimeError("independent sparse-product reference mismatch")
        if tuple(sum(value * dense_x_values[i] for i, value in enumerate(row))
                 for row in dense_expected) != tuple(case["dense_product"]):
            raise RuntimeError("independent dense-product reference mismatch")
        projected_bytes = (sum(len(row) for row in words) * 4 +
                           sum(len(row) for row in scales) * 2 * 2 +
                           (len(x_values) + len(dense_x_values)) * 4 +
                           len(rows) * len(x_values) * 4 + len(rows) * 8)
        if projected_bytes > MAX_FIXTURE_BYTES:
            raise RuntimeError("fixture byte cap exceeded")
        observe(f"{key}:before")
        stream = mx.new_stream(mx.gpu)
        w = s = b = x = dense_x = dense = product = dense_product = None
        primary = None
        try:
            with mx.stream(stream):
                w = mx.array(words, dtype=mx.uint32)
                s = mx.array(scales, dtype=mx.bfloat16)
                b = mx.array(biases, dtype=mx.bfloat16)
                x = mx.array((x_values,), dtype=mx.float32)
                dense_x = mx.array((dense_x_values,), dtype=mx.float32)
                dense = mx.dequantize(w, s, b, group_size=group_size, bits=bits,
                                      mode="affine", dtype=mx.float32)
                product = mx.quantized_matmul(x, w, s, b, transpose=True,
                                              group_size=group_size, bits=bits, mode="affine")
                dense_product = mx.quantized_matmul(dense_x, w, s, b, transpose=True,
                                                    group_size=group_size, bits=bits, mode="affine")
            mx.async_eval(dense, product, dense_product)
            observe(f"{key}:dispatched")
            mx.synchronize(stream)  # original stream completion before releasing owners
            observe(f"{key}:fenced")
            # Host materialization is bounded by MAX_FIXTURE_BYTES.
            actual_dense = tuple(tuple(float(v) for v in row) for row in dense.tolist())
            actual_product = tuple(float(v) for v in product.tolist()[0])
            actual_dense_product = tuple(float(v) for v in dense_product.tolist()[0])
            if actual_dense != dense_expected or actual_product != tuple(case["sparse_product"]):
                raise RuntimeError(f"{key}: GPU/reference numerical mismatch")
            dense_error = max(abs(a - b) for a, b in zip(actual_dense_product, case["dense_product"]))
            if any(abs(a - b) > max(1e-5, 1e-6 * abs(b))
                   for a, b in zip(actual_dense_product, case["dense_product"])):
                raise RuntimeError(f"{key}: dense GPU/reference numerical mismatch")
            results.append({"case": key, "logical_bytes_cap": projected_bytes,
                            "dense_values": sum(map(len, rows)), "literal_samples": len(case["samples"]),
                            "sparse_product": actual_product, "dense_product": actual_dense_product,
                            "dense_product_max_abs_error": dense_error,
                            "synchronize_returned": True})
        except BaseException as error:
            primary = error
        owners = [dense, product, dense_product, w, s, b, x, dense_x]
        dense = product = dense_product = w = s = b = x = dense_x = None
        finish_stream(mx, stream, owners, lambda: observe(f"{key}:released"), primary)
        if mx.get_active_memory() != 0:
            raise RuntimeError("MLX active owners remain after this case's release")
    return {"scope": "tiny_synthetic_affine_gpu_only", "checkpoint_read": False,
            "model_parity": False, "production_fence_qualified": False,
            "python": sys.version.split()[0], "mlx": importlib.metadata.version("mlx"),
            "limits": {"fixture_bytes": MAX_FIXTURE_BYTES, "mlx_peak_bytes": MAX_MLX_BYTES,
                       "mlx_cache_bytes": MAX_MLX_CACHE_BYTES,
                       "process_bytes": MAX_PROCESS_BYTES, "free_system_bytes": MIN_FREE_BYTES,
                       "swap_growth_mib": 0}, "results": results, "observations": samples}


if __name__ == "__main__":
    if sys.argv[1:] != ["--run-tiny-gpu"]:
        raise SystemExit("usage: qwen38_tiny_gpu_probe.py --run-tiny-gpu")
    print(json.dumps(run_tiny_gpu(), sort_keys=True))
