#!/usr/bin/env python3
"""GLM-C02 helpers: embedding, RMSNorm, dense F32/Q8_0 matvec (CPU oracle).

Works against Glm52TensorStore. IQ2_XXS rows use iq2_xxs_dequant.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import Any

from glm52_tensor_store import Glm52TensorStore, TensorLoc
from iq2_xxs_dequant import dequantize_row_iq2_xxs, QK_K, BLOCK_BYTES as IQ2_BLOCK
from ggml_kquants import (
    dequantize_row_q4_k,
    dequantize_row_q5_k,
    dequantize_row_q6_k,
    Q4_K_BLOCK,
    Q5_K_BLOCK,
    Q6_K_BLOCK,
)

EPS_DEFAULT = 1e-5  # override from KV when present


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
    if loc.type_id == 0:  # F32
        row_b = cols * 4
        raw = store.pread(loc.name, row * row_b, row_b)
        return list(struct.unpack(f"<{cols}f", raw))
    if loc.type_id == 8:  # Q8_0
        row_b = (cols // 32) * 34
        raw = store.pread(loc.name, row * row_b, row_b)
        return _decode_q8_0_row(raw, cols)
    if loc.type_id == 16:  # IQ2_XXS
        if cols % QK_K != 0:
            raise ValueError(f"IQ2_XXS cols {cols} not multiple of 256")
        row_b = (cols // QK_K) * IQ2_BLOCK
        raw = store.pread(loc.name, row * row_b, row_b)
        return dequantize_row_iq2_xxs(raw, cols)
    if loc.type_id == 12:  # Q4_K
        if cols % QK_K != 0:
            raise ValueError(f"Q4_K cols {cols}")
        row_b = (cols // QK_K) * Q4_K_BLOCK
        raw = store.pread(loc.name, row * row_b, row_b)
        return dequantize_row_q4_k(raw, cols)
    if loc.type_id == 13:  # Q5_K
        if cols % QK_K != 0:
            raise ValueError(f"Q5_K cols {cols}")
        row_b = (cols // QK_K) * Q5_K_BLOCK
        raw = store.pread(loc.name, row * row_b, row_b)
        return dequantize_row_q5_k(raw, cols)
    if loc.type_id == 14:  # Q6_K
        if cols % QK_K != 0:
            raise ValueError(f"Q6_K cols {cols}")
        row_b = (cols // QK_K) * Q6_K_BLOCK
        raw = store.pread(loc.name, row * row_b, row_b)
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

    # bulk-dequant rows into a flat row-major [rows, cols] buffer
    flat: list[float] = []
    for r in range(rows):
        flat.extend(dequant_row(store, loc, r))
    w = mx.array(flat, dtype=mx.float32).reshape((rows, cols))
    xv = mx.array(x, dtype=mx.float32)
    y = w @ xv
    mx.eval(y)
    return y.tolist()


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
