#!/usr/bin/env python3
"""Auditable scalar IQ3_XXS decoder transcribed from pinned ggml semantics.

This investigation-only implementation deliberately does not import either
the production Rust decoder or the existing Python decoder functions. The
grid constants are immutable format data shared with ggml; sign parity is
derived locally instead of using the project's sign lookup implementation.
"""

from __future__ import annotations

import struct

from iq3_xxs_tables import IQ3XXS_GRID

QK_K = 256
BLOCK_BYTES = 98
UPSTREAM_COMMIT = "8e7f22b67ef4667b4ddd50230771287f328cfb3f"
UPSTREAM_PATH = "ggml/src/ggml-quants.c"


def _sign_mask(index: int) -> int:
    return index | ((index.bit_count() & 1) << 7)


def decode_block_iq3_xxs_spec(block: bytes) -> list[float]:
    if len(block) != BLOCK_BYTES:
        raise ValueError("IQ3_XXS block must be exactly 98 bytes")
    scale = struct.unpack_from("<e", block, 0)[0]
    if not (-float("inf") < scale < float("inf")):
        raise ValueError("IQ3_XXS scale must be finite")
    output: list[float] = []
    for group in range(8):
        aux = int.from_bytes(block[66 + 4 * group : 70 + 4 * group], "little")
        block_scale = scale * (0.5 + (aux >> 28)) * 0.5
        for pair in range(4):
            signs = _sign_mask((aux >> (7 * pair)) & 127)
            grid1 = IQ3XXS_GRID[block[2 + group * 8 + pair * 2]].to_bytes(4, "little")
            grid2 = IQ3XXS_GRID[block[3 + group * 8 + pair * 2]].to_bytes(4, "little")
            for index in range(4):
                sign = -1.0 if signs & (1 << index) else 1.0
                output.append(block_scale * grid1[index] * sign)
            for index in range(4):
                sign = -1.0 if signs & (1 << (4 + index)) else 1.0
                output.append(block_scale * grid2[index] * sign)
    return output


def decode_iq3_xxs_spec(encoded: bytes) -> list[float]:
    if not encoded or len(encoded) % BLOCK_BYTES:
        raise ValueError("encoded length must be a nonzero multiple of 98")
    output: list[float] = []
    for offset in range(0, len(encoded), BLOCK_BYTES):
        output.extend(decode_block_iq3_xxs_spec(encoded[offset : offset + BLOCK_BYTES]))
    return output
