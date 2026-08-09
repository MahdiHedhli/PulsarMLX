#!/usr/bin/env python3
"""Exact scalar-contract NumPy decoding for GGML Q8_0 blocks."""

from __future__ import annotations

QK = 32
BLOCK_BYTES = 34


def dequantize_blocks_q8_0_numpy(encoded: bytes):
    """Decode complete Q8_0 blocks with scalar-Python f64 arithmetic order."""

    import numpy as np

    if len(encoded) == 0 or len(encoded) % BLOCK_BYTES != 0:
        raise ValueError("encoded length must be a nonzero multiple of 34")
    blocks = np.frombuffer(encoded, dtype=np.uint8).reshape(-1, BLOCK_BYTES)
    scales = (
        np.ascontiguousarray(blocks[:, :2])
        .view("<f2")
        .reshape(-1)
        .astype(np.float64)
    )
    if not np.isfinite(scales).all():
        raise ValueError("Q8_0 scales must be finite")
    quants = np.ascontiguousarray(blocks[:, 2:]).view(np.int8).astype(np.float64)
    decoded = (scales[:, None] * quants).astype(np.float32)
    return np.ascontiguousarray(decoded.reshape(-1))


def dequantize_matrix_q8_0_numpy(encoded: bytes, rows: int, cols: int):
    """Decode one exact row-major Q8_0 matrix to ``[rows, cols]`` f32."""

    if rows <= 0 or cols <= 0:
        raise ValueError("rows and cols must be positive")
    if cols % QK != 0:
        raise ValueError("cols must be multiple of 32 for pure Q8_0 rows")
    row_bytes = (cols // QK) * BLOCK_BYTES
    expected = rows * row_bytes
    if len(encoded) != expected:
        raise ValueError(f"matrix size mismatch {len(encoded)} != {expected}")
    return dequantize_blocks_q8_0_numpy(encoded).reshape(rows, cols)
