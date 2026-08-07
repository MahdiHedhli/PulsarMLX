#!/usr/bin/env python3
"""IQ2_S dequant (ggml block_iq2_s, 82 bytes)."""
from __future__ import annotations
import struct
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
