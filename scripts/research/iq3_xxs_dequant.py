#!/usr/bin/env python3
"""CPU dequant for GGML IQ3_XXS blocks."""

from __future__ import annotations

import struct
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
                    s1 = -1.0 if (signs & KMASK_IQ2XS[j + 4]) else 1.0
                    out.append(db * b1[j] * s0)
                    out.append(db * b2[j] * s1)
            qoff += 8
    return out
