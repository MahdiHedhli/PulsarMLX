#!/usr/bin/env python3
"""CPU dequant for GGML IQ3_XXS blocks."""

from __future__ import annotations

import struct
from functools import lru_cache

from iq2_xxs_tables import KMASK_IQ2XS, KSIGNS_IQ2XS
from iq3_xxs_tables import IQ3XXS_GRID

QK_K = 256
BLOCK_BYTES = 98  # 2 + 96


def dequantize_row_iq3_xxs(encoded: bytes, n: int | None = None) -> list[float]:
    if n is None:
        if len(encoded) % BLOCK_BYTES != 0:
            raise ValueError("bad length")
        n = (len(encoded) // BLOCK_BYTES) * QK_K
    if n % QK_K != 0:
        raise ValueError("n")
    nb = n // QK_K
    out: list[float] = []
    for i in range(nb):
        base = i * BLOCK_BYTES
        d = struct.unpack_from("<e", encoded, base)[0]
        qs = encoded[base + 2 : base + 2 + QK_K // 4]  # 64 bytes indices
        scales_and_signs = encoded[base + 2 + QK_K // 4 : base + BLOCK_BYTES]  # 32 bytes
        qoff = 0
        for ib32 in range(QK_K // 32):
            aux32 = struct.unpack_from("<I", scales_and_signs, 4 * ib32)[0]
            db = d * (0.5 + (aux32 >> 28)) * 0.5
            for l in range(4):
                signs = KSIGNS_IQ2XS[(aux32 >> (7 * l)) & 127]
                g1 = IQ3XXS_GRID[qs[qoff + 2 * l + 0]]
                g2 = IQ3XXS_GRID[qs[qoff + 2 * l + 1]]
                # grid is uint32 packing 4 x uint8
                b1 = g1.to_bytes(4, "little")
                b2 = g2.to_bytes(4, "little")
                for j in range(4):
                    s0 = -1.0 if (signs & KMASK_IQ2XS[j + 0]) else 1.0
                    out.append(db * b1[j] * s0)
                for j in range(4):
                    s1 = -1.0 if (signs & KMASK_IQ2XS[j + 4]) else 1.0
                    out.append(db * b2[j] * s1)
            qoff += 8
    return out


@lru_cache(maxsize=1)
def _numpy_lookup_tables():
    """Return immutable magnitude/sign tables without importing NumPy for scalar use."""

    import numpy as np

    grid = np.frombuffer(
        b"".join(value.to_bytes(4, "little") for value in IQ3XXS_GRID),
        dtype=np.uint8,
    ).reshape(256, 4)
    sign_words = np.asarray(KSIGNS_IQ2XS, dtype=np.uint8)[:, None]
    masks = np.asarray(KMASK_IQ2XS, dtype=np.uint8)[None, :]
    signs = np.where((sign_words & masks) != 0, -1.0, 1.0).astype(np.float64)
    grid.setflags(write=False)
    signs.setflags(write=False)
    return grid, signs


def dequantize_blocks_iq3_xxs_numpy(encoded: bytes):
    """Vector-decode complete IQ3_XXS blocks to one contiguous f32 array.

    Float arithmetic remains in f64 until the one final f32 conversion so the
    operation order matches the independently readable scalar Python oracle.
    Partial, overlong, empty, and non-finite inputs fail closed.
    """

    import numpy as np

    if len(encoded) == 0 or len(encoded) % BLOCK_BYTES != 0:
        raise ValueError("encoded length must be a nonzero multiple of 98")
    blocks = np.frombuffer(encoded, dtype=np.uint8).reshape(-1, BLOCK_BYTES)
    scales = (
        np.ascontiguousarray(blocks[:, :2])
        .view("<f2")
        .reshape(-1)
        .astype(np.float64)
    )
    if not np.isfinite(scales).all():
        raise ValueError("IQ3_XXS scale must be finite")

    grid_indices = blocks[:, 2:66].reshape(-1, QK_K // 32, 4, 2)
    scale_sign_bytes = blocks[:, 66:].reshape(-1, QK_K // 32, 4)
    scale_sign_words = (
        np.ascontiguousarray(scale_sign_bytes)
        .view("<u4")
        .reshape(-1, QK_K // 32)
    )
    shifts = np.asarray([0, 7, 14, 21], dtype=np.uint32)
    sign_indices = (scale_sign_words[:, :, None] >> shifts) & np.uint32(127)
    block_scales = scales[:, None] * (
        0.5 + (scale_sign_words >> np.uint32(28)).astype(np.float64)
    ) * 0.5

    grid_lookup, sign_lookup = _numpy_lookup_tables()
    # GGML writes each eight-value subgroup as grid-1 lanes 0..3 followed by
    # grid-2 lanes 0..3. Keep the [grid, lane] axes in that order so the final
    # row-major reshape preserves the canonical logical element ordering.
    magnitudes = grid_lookup[grid_indices].astype(np.float64)
    signs = sign_lookup[sign_indices].reshape(-1, QK_K // 32, 4, 2, 4)
    decoded = (
        block_scales[:, :, None, None, None]
        * magnitudes
        * signs
    ).astype(np.float32)
    return np.ascontiguousarray(decoded.reshape(-1))


def dequantize_matrix_iq3_xxs_numpy(encoded: bytes, rows: int, cols: int):
    """Vector-decode one exact row-major IQ3_XXS matrix to `[rows, cols]` f32."""

    if rows <= 0 or cols <= 0:
        raise ValueError("rows and cols must be positive")
    if cols % QK_K != 0:
        raise ValueError("cols must be multiple of 256 for pure IQ3_XXS rows")
    row_bytes = (cols // QK_K) * BLOCK_BYTES
    expected = rows * row_bytes
    if len(encoded) != expected:
        raise ValueError(f"matrix size mismatch {len(encoded)} != {expected}")
    return dequantize_blocks_iq3_xxs_numpy(encoded).reshape(rows, cols)
