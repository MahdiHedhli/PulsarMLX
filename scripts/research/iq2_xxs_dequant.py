#!/usr/bin/env python3
"""CPU dequant for GGML IQ2_XXS blocks (architecture oracle path).

Port of ggml dequantize_row_iq2_xxs. Block layout: 256 f32 → 66 bytes
(f16 scale + 64 qs bytes).
"""

from __future__ import annotations

import struct
from typing import Iterable

from iq2_xxs_tables import IQ2XXS_GRID, KMASK_IQ2XS, KSIGNS_IQ2XS

QK_K = 256
BLOCK_BYTES = 66  # 2 + 64


def dequantize_row_iq2_xxs(encoded: bytes, n: int | None = None) -> list[float]:
    if n is None:
        if len(encoded) % BLOCK_BYTES != 0:
            raise ValueError("encoded length not multiple of IQ2_XXS block")
        n = (len(encoded) // BLOCK_BYTES) * QK_K
    if n % QK_K != 0:
        raise ValueError("n must be multiple of 256")
    nb = n // QK_K
    if len(encoded) < nb * BLOCK_BYTES:
        raise ValueError("encoded buffer too short")
    out: list[float] = []
    for i in range(nb):
        base = i * BLOCK_BYTES
        d = struct.unpack_from("<e", encoded, base)[0]
        qs = encoded[base + 2 : base + 66]
        for ib32 in range(QK_K // 32):
            # 8 bytes → two uint32 little-endian
            off = 8 * ib32
            aux0, aux1 = struct.unpack_from("<II", qs, off)
            aux8 = struct.pack("<I", aux0)  # 4 grid indices as bytes
            db = d * (0.5 + (aux1 >> 28)) * 0.25
            for l in range(4):
                grid_idx = aux8[l]
                grid = IQ2XXS_GRID[grid_idx]
                gbytes = grid.to_bytes(8, "little")
                signs = KSIGNS_IQ2XS[(aux1 >> (7 * l)) & 127]
                for j in range(8):
                    s = -1.0 if (signs & KMASK_IQ2XS[j]) else 1.0
                    out.append(db * gbytes[j] * s)
    return out


def dequantize_matrix_iq2_xxs(encoded: bytes, rows: int, cols: int) -> list[list[float]]:
    """Row-major matrix; each row is IQ2_XXS packed with cols % 256 == 0."""
    if cols % QK_K != 0:
        raise ValueError("cols must be multiple of 256 for pure IQ2_XXS rows")
    row_bytes = (cols // QK_K) * BLOCK_BYTES
    if len(encoded) != rows * row_bytes:
        raise ValueError(f"matrix size mismatch {len(encoded)} != {rows*row_bytes}")
    return [
        dequantize_row_iq2_xxs(encoded[r * row_bytes : (r + 1) * row_bytes], cols)
        for r in range(rows)
    ]


def selftest() -> None:
    # Empty / length checks
    assert BLOCK_BYTES == 66
    assert len(IQ2XXS_GRID) == 256
    # One zeroish block: d=1.0, qs all zero → grid[0], signs from ksigns[0]
    d = struct.pack("<e", 1.0)
    qs = bytes(64)
    enc = d + qs
    y = dequantize_row_iq2_xxs(enc, 256)
    assert len(y) == 256
    assert all(abs(v) < 10 for v in y)
    print("iq2_xxs_dequant selftest ok", "sample", y[:8])


if __name__ == "__main__":
    selftest()
