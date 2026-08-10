#!/usr/bin/env python3
"""IQ4_XS dequant (ggml block_iq4_xs, 136 bytes)."""
from __future__ import annotations
import struct
from functools import lru_cache
from iq_extra_tables import KVALUES_IQ4NL

QK_K = 256
BLOCK_BYTES = 136

def dequantize_row_iq4_xs(encoded: bytes, n: int | None = None) -> list[float]:
    if n is None:
        assert len(encoded) % BLOCK_BYTES == 0
        n = (len(encoded) // BLOCK_BYTES) * QK_K
    assert n % QK_K == 0
    out: list[float] = []
    for bi in range(n // QK_K):
        base = bi * BLOCK_BYTES
        d = struct.unpack_from("<e", encoded, base)[0]
        scales_h = struct.unpack_from("<H", encoded, base + 2)[0]
        scales_l = encoded[base + 4 : base + 8]
        qs = encoded[base + 8 : base + 136]
        for ib in range(8):
            ls = ((scales_l[ib >> 1] >> (4 * (ib & 1))) & 0xF) | (((scales_h >> (2 * ib)) & 3) << 4)
            ls = ls - 32
            scale = d * float(ls)
            for j in range(16):
                byte = qs[ib * 16 + j]
                out.append(scale * KVALUES_IQ4NL[byte & 0xF])
                out.append(scale * KVALUES_IQ4NL[byte >> 4])
    return out


@lru_cache(maxsize=1)
def _numpy_values():
    import numpy as np

    values = np.asarray(KVALUES_IQ4NL, dtype=np.float64)
    values.setflags(write=False)
    return values


def dequantize_blocks_iq4_xs_numpy(encoded: bytes):
    """Vector-decode complete IQ4_XS blocks with scalar f64 operation order."""

    import numpy as np

    if len(encoded) == 0 or len(encoded) % BLOCK_BYTES != 0:
        raise ValueError("encoded length must be a nonzero multiple of 136")
    blocks = np.frombuffer(encoded, dtype=np.uint8).reshape(-1, BLOCK_BYTES)
    d = (
        np.ascontiguousarray(blocks[:, :2])
        .view("<f2")
        .reshape(-1)
        .astype(np.float64)
    )
    if not np.isfinite(d).all():
        raise ValueError("IQ4_XS scale must be finite")
    scales_h = (
        np.ascontiguousarray(blocks[:, 2:4])
        .view("<u2")
        .reshape(-1)
    )
    scales_l = blocks[:, 4:8]
    quants = blocks[:, 8:].reshape(-1, 8, 16)
    values = _numpy_values()
    decoded = np.empty((len(blocks), QK_K), dtype=np.float32)
    for group in range(8):
        low = (
            scales_l[:, group >> 1] >> np.uint8(4 * (group & 1))
        ) & np.uint8(15)
        high = (scales_h >> np.uint16(2 * group)) & np.uint16(3)
        integer_scale = (low.astype(np.int16) | (high.astype(np.int16) << 4)) - 32
        scale = d * integer_scale.astype(np.float64)
        packed = quants[:, group, :]
        magnitudes = np.stack(
            (values[packed & np.uint8(15)], values[packed >> np.uint8(4)]),
            axis=2,
        )
        decoded[:, 32 * group : 32 * group + 32] = (
            scale[:, None, None] * magnitudes
        ).astype(np.float32).reshape(-1, 32)
    return np.ascontiguousarray(decoded.reshape(-1))


def dequantize_matrix_iq4_xs_numpy(encoded: bytes, rows: int, cols: int):
    """Vector-decode one exact row-major IQ4_XS matrix to ``[rows, cols]`` f32."""

    if rows <= 0 or cols <= 0:
        raise ValueError("rows and cols must be positive")
    if cols % QK_K != 0:
        raise ValueError("cols must be multiple of 256 for pure IQ4_XS rows")
    expected = rows * (cols // QK_K) * BLOCK_BYTES
    if len(encoded) != expected:
        raise ValueError(f"matrix size mismatch {len(encoded)} != {expected}")
    return dequantize_blocks_iq4_xs_numpy(encoded).reshape(rows, cols)
