#!/usr/bin/env python3
"""IQ4_XS dequant (ggml block_iq4_xs, 136 bytes)."""
from __future__ import annotations
import struct
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
            group = qs[ib * 16 : ib * 16 + 16]
            out.extend(scale * KVALUES_IQ4NL[byte & 0xF] for byte in group)
            out.extend(scale * KVALUES_IQ4NL[byte >> 4] for byte in group)
    return out
