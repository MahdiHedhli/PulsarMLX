#!/usr/bin/env python3
"""IQ2_S dequant (ggml block_iq2_s, 82 bytes)."""
from __future__ import annotations
import struct
from functools import lru_cache
from iq_extra_tables import IQ2S_GRID

QK_K = 256
BLOCK_BYTES = 82

def dequantize_row_iq2_s(encoded: bytes, n: int | None = None) -> list[float]:
    if n is None:
        assert len(encoded) % BLOCK_BYTES == 0
        n = (len(encoded) // BLOCK_BYTES) * QK_K
    assert n % QK_K == 0
    out: list[float] = []
    for bi in range(n // QK_K):
        base = bi * BLOCK_BYTES
        d = struct.unpack_from("<e", encoded, base)[0]
        qs = encoded[base + 2 : base + 2 + 64]  # 32 idx + 32 signs
        qh = encoded[base + 66 : base + 74]
        scales = encoded[base + 74 : base + 82]
        for g in range(8):  # groups of 32
            for h in range(2):  # halves of 16
                nibble = (scales[g] >> 4) if h else (scales[g] & 0xF)
                scale = 0.125 * d * float(2 * nibble + 1)
                for k in range(2):  # sub-groups of 8
                    j = h * 2 + k
                    idx = qs[g * 4 + j] | ((qh[g] << (8 - 2 * j)) & 0x300)
                    gr = IQ2S_GRID[idx]
                    sgn = qs[32 + g * 4 + j]
                    for t in range(8):
                        mag = (gr >> (8 * t)) & 0xFF
                        sign = -1.0 if (sgn & (1 << t)) else 1.0
                        out.append(scale * sign * float(mag))
    return out


@lru_cache(maxsize=1)
def _numpy_grid():
    import numpy as np

    grid = np.frombuffer(
        b"".join(value.to_bytes(8, "little") for value in IQ2S_GRID),
        dtype=np.uint8,
    ).reshape(len(IQ2S_GRID), 8)
    grid.setflags(write=False)
    return grid


def dequantize_blocks_iq2_s_numpy(encoded: bytes):
    """Vector-decode complete IQ2_S blocks with scalar f64 operation order."""

    import numpy as np

    if len(encoded) == 0 or len(encoded) % BLOCK_BYTES != 0:
        raise ValueError("encoded length must be a nonzero multiple of 82")
    blocks = np.frombuffer(encoded, dtype=np.uint8).reshape(-1, BLOCK_BYTES)
    d = (
        np.ascontiguousarray(blocks[:, :2])
        .view("<f2")
        .reshape(-1)
        .astype(np.float64)
    )
    if not np.isfinite(d).all():
        raise ValueError("IQ2_S scale must be finite")
    indices = blocks[:, 2:34]
    sign_bytes = blocks[:, 34:66]
    high = blocks[:, 66:74].astype(np.uint16)
    scales = blocks[:, 74:82]
    grid = _numpy_grid()
    bit_masks = np.left_shift(np.uint8(1), np.arange(8, dtype=np.uint8))
    decoded = np.empty((len(blocks), QK_K), dtype=np.float32)
    offset = 0
    for group in range(8):
        for half in range(2):
            nibble = (
                scales[:, group] >> np.uint8(4)
                if half
                else scales[:, group] & np.uint8(15)
            )
            # Match 0.125 * d * float(2*nibble + 1) in binary64.
            scale = (0.125 * d) * (2 * nibble.astype(np.float64) + 1.0)
            for subgroup in range(2):
                j = half * 2 + subgroup
                lookup = indices[:, group * 4 + j].astype(np.uint16) | (
                    (high[:, group] << np.uint16(8 - 2 * j)) & np.uint16(0x300)
                )
                magnitudes = grid[lookup].astype(np.float64)
                signs = np.where(
                    (sign_bytes[:, group * 4 + j, None] & bit_masks[None, :]) != 0,
                    -1.0,
                    1.0,
                )
                values = ((scale[:, None] * signs) * magnitudes).astype(np.float32)
                decoded[:, offset : offset + 8] = values
                offset += 8
    return np.ascontiguousarray(decoded.reshape(-1))


def dequantize_matrix_iq2_s_numpy(encoded: bytes, rows: int, cols: int):
    """Vector-decode one exact row-major IQ2_S matrix to ``[rows, cols]`` f32."""

    if rows <= 0 or cols <= 0:
        raise ValueError("rows and cols must be positive")
    if cols % QK_K != 0:
        raise ValueError("cols must be multiple of 256 for pure IQ2_S rows")
    expected = rows * (cols // QK_K) * BLOCK_BYTES
    if len(encoded) != expected:
        raise ValueError(f"matrix size mismatch {len(encoded)} != {expected}")
    return dequantize_blocks_iq2_s_numpy(encoded).reshape(rows, cols)
