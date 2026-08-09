#!/usr/bin/env python3
"""GLM-C02 helpers: embedding, RMSNorm, dense F32/Q8_0 matvec (CPU oracle).

Works against Glm52TensorStore. IQ2_XXS rows use iq2_xxs_dequant.
"""

from __future__ import annotations

import math
import struct
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any, Iterator

from glm52_tensor_store import Glm52TensorStore, TensorLoc, nbytes_for_tensor
from iq2_xxs_dequant import dequantize_row_iq2_xxs
from ggml_kquants import (
    dequantize_row_q4_k,
    dequantize_row_q5_k,
    dequantize_row_q6_k,
)

EPS_DEFAULT = 1e-5  # override from KV when present
_REQUIRE_MLX: ContextVar[bool] = ContextVar("glm52_require_mlx", default=False)
_DENSE_READ_MODE: ContextVar[str] = ContextVar(
    "glm52_dense_read_mode", default="row_reference"
)


@dataclass(frozen=True)
class DenseOperationMetrics:
    tensor: str
    quantization: str
    rows: int
    cols: int
    encoded_bytes: int
    storage_read_count: int
    storage_read_seconds: float
    dequant_seconds: float
    contiguous_buffer_seconds: float
    mlx_matrix_build_seconds: float
    mlx_matvec_seconds: float
    total_seconds: float
    read_mode: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScalarMatrixLoadMetrics:
    encoded_bytes: int
    storage_read_count: int
    storage_read_seconds: float
    dequant_seconds: float
    contiguous_buffer_seconds: float
    read_mode: str


@dataclass
class DenseMetricsCapture:
    operations: list[DenseOperationMetrics] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        fields = (
            "encoded_bytes",
            "storage_read_count",
            "storage_read_seconds",
            "dequant_seconds",
            "contiguous_buffer_seconds",
            "mlx_matrix_build_seconds",
            "mlx_matvec_seconds",
            "total_seconds",
        )
        return {
            "operation_count": len(self.operations),
            "totals": {
                name: sum(getattr(operation, name) for operation in self.operations)
                for name in fields
            },
            "operations": [operation.to_dict() for operation in self.operations],
        }


_DENSE_METRICS: ContextVar[DenseMetricsCapture | None] = ContextVar(
    "glm52_dense_metrics", default=None
)


def mlx_backend_required() -> bool:
    return _REQUIRE_MLX.get()


@contextmanager
def require_mlx_backend() -> Iterator[None]:
    """Make every auto matvec fail closed instead of selecting CPU."""

    token = _REQUIRE_MLX.set(True)
    try:
        yield
    finally:
        _REQUIRE_MLX.reset(token)


@contextmanager
def dense_read_mode(mode: str) -> Iterator[None]:
    """Select the experimental dense matrix read strategy for this context."""

    if mode not in {"row_reference", "whole_matrix_scalar"}:
        raise ValueError(f"unsupported dense read mode {mode}")
    reset_handle = _DENSE_READ_MODE.set(mode)
    try:
        yield
    finally:
        _DENSE_READ_MODE.reset(reset_handle)


@contextmanager
def capture_dense_metrics() -> Iterator[DenseMetricsCapture]:
    """Capture bounded per-matrix timings without changing execution mode."""

    capture = DenseMetricsCapture()
    reset_handle = _DENSE_METRICS.set(capture)
    try:
        yield capture
    finally:
        _DENSE_METRICS.reset(reset_handle)


def rms_norm(x: list[float], w: list[float], eps: float = EPS_DEFAULT) -> list[float]:
    ms = sum(v * v for v in x) / len(x)
    scale = 1.0 / math.sqrt(ms + eps)
    return [w[i] * x[i] * scale for i in range(len(x))]


def load_f32_vector(store: Glm52TensorStore, name: str) -> list[float]:
    loc = store.tensors[name]
    if loc.type_id != 0:
        raise TypeError(f"{name} expected F32 got {loc.type_name}")
    raw = store.read_bytes(name)
    n = loc.n_elem
    return list(struct.unpack(f"<{n}f", raw))


def dequant_row(store: Glm52TensorStore, loc: TensorLoc, row: int) -> list[float]:
    """Dequant one output-row of a 2D weight [cols, rows] GGUF layout.

    GGUF ne0 is typically the fastest dim (cols for matvec y = W @ x).
    For shape dims=[ne0, ne1] → cols=ne0, rows=ne1.
    """
    if len(loc.dims) != 2:
        raise ValueError(f"{loc.name}: need 2D, got {loc.dims}")
    cols, rows = int(loc.dims[0]), int(loc.dims[1])
    if row < 0 or row >= rows:
        raise IndexError(row)
    row_b = nbytes_for_tensor(loc.type_id, cols)
    raw = store.pread(loc.name, row * row_b, row_b)
    if len(raw) != row_b:
        raise OSError(f"{loc.name}: truncated row {row}")
    return _dequant_row_bytes(loc, raw, cols)


def _dequant_row_bytes(loc: TensorLoc, raw: bytes, cols: int) -> list[float]:
    """Apply the existing scalar row decoder to already-read encoded bytes."""

    expected = nbytes_for_tensor(loc.type_id, cols)
    if len(raw) != expected:
        raise ValueError(f"{loc.name}: encoded row length {len(raw)} != {expected}")
    if loc.type_id == 0:
        return list(struct.unpack(f"<{cols}f", raw))
    if loc.type_id == 8:
        return _decode_q8_0_row(raw, cols)
    if loc.type_id == 16:
        return dequantize_row_iq2_xxs(raw, cols)
    if loc.type_id == 12:
        return dequantize_row_q4_k(raw, cols)
    if loc.type_id == 13:
        return dequantize_row_q5_k(raw, cols)
    if loc.type_id == 14:
        return dequantize_row_q6_k(raw, cols)
    raise TypeError(f"unsupported type {loc.type_name} for {loc.name}")


def _decode_q8_0_row(encoded: bytes, cols: int) -> list[float]:
    out: list[float] = []
    for b in range(cols // 32):
        base = b * 34
        scale = struct.unpack_from("<e", encoded, base)[0]
        qs = struct.unpack_from("<32b", encoded, base + 2)
        out.extend(scale * float(q) for q in qs)
    return out


def matvec_weight(
    store: Glm52TensorStore, name: str, x: list[float], *, backend: str = "auto"
) -> list[float]:
    """y = W @ x for 2D GGUF weight [cols, rows].

    backend:
      - auto: MLX matmul after bulk dequant when available
      - cpu: pure-Python row dots (oracle / fallback)
      - mlx: force MLX
    """
    loc = store.tensors[name]
    if len(loc.dims) != 2:
        raise ValueError(f"{name}: expected 2D weight")
    cols, rows = int(loc.dims[0]), int(loc.dims[1])
    if len(x) != cols:
        raise ValueError(f"{name}: act {len(x)} != cols {cols}")
    if mlx_backend_required():
        if backend == "cpu":
            raise RuntimeError("CPU matvec forbidden while MLX is required")
        backend = "mlx"
    use_mlx = backend == "mlx" or (backend == "auto" and rows * cols >= 256 * 256)
    if use_mlx:
        try:
            return _matvec_mlx(store, loc, x, cols, rows)
        except Exception:
            if backend == "mlx":
                raise
    y = [0.0] * rows
    for r in range(rows):
        w = dequant_row(store, loc, r)
        y[r] = sum(a * b for a, b in zip(w, x, strict=True))
    return y


def _matvec_mlx(
    store: Glm52TensorStore, loc: TensorLoc, x: list[float], cols: int, rows: int
) -> list[float]:
    import mlx.core as mx

    total_start = time.perf_counter()
    flat, load = _load_scalar_dense_matrix(store, loc, cols, rows, _DENSE_READ_MODE.get())
    build_start = time.perf_counter()
    w = mx.array(flat, dtype=mx.float32).reshape((rows, cols))
    mx.eval(w)
    matrix_build_seconds = time.perf_counter() - build_start
    matvec_start = time.perf_counter()
    xv = mx.array(x, dtype=mx.float32)
    y = w @ xv
    mx.eval(y)
    result = y.tolist()
    mlx_matvec_seconds = time.perf_counter() - matvec_start
    metrics = DenseOperationMetrics(
        tensor=loc.name,
        quantization=loc.type_name,
        rows=rows,
        cols=cols,
        encoded_bytes=load.encoded_bytes,
        storage_read_count=load.storage_read_count,
        storage_read_seconds=load.storage_read_seconds,
        dequant_seconds=load.dequant_seconds,
        contiguous_buffer_seconds=load.contiguous_buffer_seconds,
        mlx_matrix_build_seconds=matrix_build_seconds,
        mlx_matvec_seconds=mlx_matvec_seconds,
        total_seconds=time.perf_counter() - total_start,
        read_mode=load.read_mode,
    )
    capture = _DENSE_METRICS.get()
    if capture is not None:
        capture.operations.append(metrics)
    return result


def _load_scalar_dense_matrix(
    store: Glm52TensorStore,
    loc: TensorLoc,
    cols: int,
    rows: int,
    read_mode: str,
) -> tuple[list[float], ScalarMatrixLoadMetrics]:
    """Read and scalar-decode one complete matrix with exact byte accounting."""

    if read_mode not in {"row_reference", "whole_matrix_scalar"}:
        raise ValueError(f"unsupported dense read mode {read_mode}")
    row_bytes = nbytes_for_tensor(loc.type_id, cols)
    encoded_bytes = row_bytes * rows
    if loc.n_bytes != encoded_bytes:
        raise ValueError(f"{loc.name}: encoded matrix size mismatch")
    storage_read_seconds = 0.0
    dequant_seconds = 0.0
    contiguous_buffer_seconds = 0.0
    storage_read_count = 0
    complete_raw: bytes | None = None
    if read_mode == "whole_matrix_scalar":
        read_start = time.perf_counter()
        complete_raw = store.pread(loc.name, 0, encoded_bytes)
        storage_read_seconds = time.perf_counter() - read_start
        storage_read_count = 1
        if len(complete_raw) != encoded_bytes:
            raise OSError(f"{loc.name}: truncated complete matrix")

    # Decode rows in the same order with the same scalar decoder as the reference.
    flat: list[float] = []
    for r in range(rows):
        if complete_raw is None:
            read_start = time.perf_counter()
            raw = store.pread(loc.name, r * row_bytes, row_bytes)
            storage_read_seconds += time.perf_counter() - read_start
            storage_read_count += 1
            if len(raw) != row_bytes:
                raise OSError(f"{loc.name}: truncated row {r}")
        else:
            start = r * row_bytes
            raw = complete_raw[start : start + row_bytes]
        decode_start = time.perf_counter()
        decoded = _dequant_row_bytes(loc, raw, cols)
        dequant_seconds += time.perf_counter() - decode_start
        buffer_start = time.perf_counter()
        flat.extend(decoded)
        contiguous_buffer_seconds += time.perf_counter() - buffer_start
    return flat, ScalarMatrixLoadMetrics(
        encoded_bytes=encoded_bytes,
        storage_read_count=storage_read_count,
        storage_read_seconds=storage_read_seconds,
        dequant_seconds=dequant_seconds,
        contiguous_buffer_seconds=contiguous_buffer_seconds,
        read_mode=read_mode,
    )


def matvec_weight_profiled(
    store: Glm52TensorStore,
    name: str,
    x: list[float],
    *,
    read_mode: str,
) -> tuple[list[float], DenseOperationMetrics]:
    """Execute one MLX dense matvec and return its exact bounded measurements."""

    with dense_read_mode(read_mode), capture_dense_metrics() as capture:
        result = matvec_weight(store, name, x, backend="mlx")
    if len(capture.operations) != 1:
        raise RuntimeError(f"{name}: expected exactly one captured dense operation")
    return result, capture.operations[0]


def embed_token(store: Glm52TensorStore, token_id: int) -> list[float]:
    """token_embd.weight shape [n_embd, n_vocab] → columns = embd, rows = vocab."""
    name = "token_embd.weight"
    loc = store.tensors[name]
    cols, rows = int(loc.dims[0]), int(loc.dims[1])
    if token_id < 0 or token_id >= rows:
        raise IndexError(token_id)
    return dequant_row(store, loc, token_id)


def compare_vectors(
    actual: list[float], reference: list[float], abs_tol: float, rel_tol: float
) -> dict[str, Any]:
    n = len(actual)
    if n != len(reference):
        raise ValueError("length mismatch")
    max_abs = 0.0
    mean_abs = 0.0
    sum_sq = 0.0
    max_rel = 0.0
    mismatches = 0
    first = None
    for i, (a, r) in enumerate(zip(actual, reference, strict=True)):
        err = abs(a - r)
        mean_abs += err
        sum_sq += err * err
        max_abs = max(max_abs, err)
        denom = abs(r)
        rel = err / denom if denom > 0 else err
        max_rel = max(max_rel, rel)
        if err > abs_tol + rel_tol * denom:
            mismatches += 1
            first = first if first is not None else i
    return {
        "compared_count": n,
        "mismatch_count": mismatches,
        "first_mismatch": first,
        "maximum_absolute_error": max_abs,
        "maximum_relative_error": max_rel,
        "mean_absolute_error": mean_abs / n if n else 0.0,
        "rmse": math.sqrt(sum_sq / n) if n else 0.0,
        "passed": mismatches == 0,
        "absolute_tolerance": abs_tol,
        "relative_tolerance": rel_tol,
    }
