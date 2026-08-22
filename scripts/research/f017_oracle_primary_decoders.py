#!/usr/bin/env python3
"""Independent scalar decoders for the corrected full-checkpoint CPU oracle.

The algorithms in this file are a fresh scalar transcription of the pinned
GGML block specifications.  They deliberately do not import any production,
Rust, MLX, or offline-forensics decoder implementation.  The three immutable
GGML codebook modules contain data only and are separately hash-bound by the
scientific access package.
"""
from __future__ import annotations

import struct

from iq2_xxs_tables import IQ2XXS_GRID, KMASK_IQ2XS, KSIGNS_IQ2XS
from iq3_xxs_tables import IQ3XXS_GRID
from iq_extra_tables import IQ2S_GRID, KVALUES_IQ4NL

QK = 256
LAYOUT = {
    "F32": (1, 4), "Q8_0": (32, 34), "Q2_K": (256, 84),
    "Q3_K": (256, 110), "Q4_K": (256, 144), "Q5_K": (256, 176),
    "Q6_K": (256, 210), "IQ2_S": (256, 82), "IQ2_XXS": (256, 66),
    "IQ3_XXS": (256, 98), "IQ4_XS": (256, 136),
}


def _finite_half(data: bytes, offset: int) -> float:
    value = float(struct.unpack_from("<e", data, offset)[0])
    if value != value or abs(value) == float("inf"):
        raise ValueError("non-finite quantization scale")
    return value


def _k4_scale(index: int, scales: bytes) -> tuple[int, int]:
    if index < 4:
        return scales[index] & 63, scales[index + 4] & 63
    return ((scales[index + 4] & 15) | ((scales[index - 4] >> 6) << 4),
            (scales[index + 4] >> 4) | ((scales[index] >> 6) << 4))


def _decode_block(fmt: str, block: bytes) -> list[float]:
    if fmt == "F32":
        return [float(struct.unpack("<f", block)[0])]
    if fmt == "Q8_0":
        d = _finite_half(block, 0)
        return [d * q for q in struct.unpack_from("<32b", block, 2)]
    if fmt == "Q2_K":
        scales, qs = block[:16], block[16:80]
        d, dm = _finite_half(block, 80), _finite_half(block, 82)
        out = [0.0] * QK
        for half in range(2):
            for lane in range(32):
                packed = qs[32 * half + lane]
                for group in range(4):
                    index = 128 * half + 32 * group + lane
                    code = (packed >> (2 * group)) & 3
                    scale = scales[index // 16]
                    out[index] = d * (scale & 15) * code - dm * (scale >> 4)
        return out
    if fmt == "Q3_K":
        hmask, qs, packed_scales = block[:32], block[32:96], block[96:108]
        d = _finite_half(block, 108)
        scales = []
        for j in range(16):
            low = packed_scales[j] & 15 if j < 8 else packed_scales[j - 8] >> 4
            high = (packed_scales[8 + j % 4] >> (2 * (j // 4))) & 3
            scales.append((low | high << 4) - 32)
        out = [0.0] * QK
        for half in range(2):
            for lane in range(32):
                packed = qs[32 * half + lane]
                for group in range(4):
                    index = 128 * half + 32 * group + lane
                    code = (packed >> (2 * group)) & 3
                    if not hmask[lane] & (1 << (4 * half + group)):
                        code -= 4
                    out[index] = d * scales[index // 16] * code
        return out
    if fmt in {"Q4_K", "Q5_K"}:
        d, dm, scales = _finite_half(block, 0), _finite_half(block, 2), block[4:16]
        if fmt == "Q4_K":
            high, qs = None, block[16:144]
        else:
            high, qs = block[16:48], block[48:176]
        out: list[float] = []
        offset = 0
        high_low, high_high = 1, 2
        for pair in range(4):
            s0, m0 = _k4_scale(2 * pair, scales)
            s1, m1 = _k4_scale(2 * pair + 1, scales)
            for lane in range(32):
                code = qs[offset + lane] & 15
                if high is not None and high[lane] & high_low:
                    code += 16
                out.append(d * s0 * code - dm * m0)
            for lane in range(32):
                code = qs[offset + lane] >> 4
                if high is not None and high[lane] & high_high:
                    code += 16
                out.append(d * s1 * code - dm * m1)
            offset += 32
            high_low <<= 2
            high_high <<= 2
        return out
    if fmt == "Q6_K":
        low, high = block[:128], block[128:192]
        scales = struct.unpack_from("<16b", block, 192)
        d = _finite_half(block, 208)
        out = [0.0] * QK
        for half in range(2):
            for lane in range(32):
                h = high[32 * half + lane]
                codes = (
                    (low[64 * half + lane] & 15) | ((h & 3) << 4),
                    (low[64 * half + 32 + lane] & 15) | (((h >> 2) & 3) << 4),
                    (low[64 * half + lane] >> 4) | (((h >> 4) & 3) << 4),
                    (low[64 * half + 32 + lane] >> 4) | (((h >> 6) & 3) << 4),
                )
                for quarter, code in enumerate(codes):
                    index = 128 * half + 32 * quarter + lane
                    out[index] = d * scales[index // 16] * (code - 32)
        return out
    if fmt == "IQ2_S":
        d, qs, high, scales = _finite_half(block, 0), block[2:66], block[66:74], block[74:82]
        out = []
        for group in range(8):
            for half in range(2):
                nibble = scales[group] >> 4 if half else scales[group] & 15
                scale = d * (2 * nibble + 1) / 8.0
                for subgroup in range(2):
                    j = 2 * half + subgroup
                    grid = IQ2S_GRID[qs[4 * group + j] | ((high[group] << (8 - 2 * j)) & 0x300)]
                    signs = qs[32 + 4 * group + j]
                    out.extend(scale * ((grid >> (8 * k)) & 255) * (-1 if signs & (1 << k) else 1) for k in range(8))
        return out
    if fmt == "IQ2_XXS":
        d, qs = _finite_half(block, 0), block[2:]
        out = []
        for group in range(8):
            grids, aux = struct.unpack_from("<II", qs, 8 * group)
            scale = d * (0.5 + (aux >> 28)) * 0.25
            for lane_group in range(4):
                grid = IQ2XXS_GRID[(grids >> (8 * lane_group)) & 255]
                signs = KSIGNS_IQ2XS[(aux >> (7 * lane_group)) & 127]
                out.extend(scale * ((grid >> (8 * k)) & 255) * (-1 if signs & KMASK_IQ2XS[k] else 1) for k in range(8))
        return out
    if fmt == "IQ3_XXS":
        d, grids, packed = _finite_half(block, 0), block[2:66], block[66:98]
        out = []
        for group in range(8):
            aux = struct.unpack_from("<I", packed, 4 * group)[0]
            scale = d * (0.5 + (aux >> 28)) * 0.5
            for pair in range(4):
                signs = KSIGNS_IQ2XS[(aux >> (7 * pair)) & 127]
                for half in range(2):
                    grid = IQ3XXS_GRID[grids[8 * group + 2 * pair + half]]
                    out.extend(scale * ((grid >> (8 * k)) & 255) * (-1 if signs & KMASK_IQ2XS[4 * half + k] else 1) for k in range(4))
        return out
    if fmt == "IQ4_XS":
        d = _finite_half(block, 0)
        scale_high = struct.unpack_from("<H", block, 2)[0]
        scale_low, qs, out = block[4:8], block[8:], []
        for group in range(8):
            packed = (scale_low[group // 2] >> (4 * (group & 1))) & 15
            scale = d * ((packed | (((scale_high >> (2 * group)) & 3) << 4)) - 32)
            for byte in qs[16 * group:16 * group + 16]:
                out.extend((scale * KVALUES_IQ4NL[byte & 15], scale * KVALUES_IQ4NL[byte >> 4]))
        return out
    raise ValueError(f"unsupported format {fmt}")


def decode(fmt: str, encoded: bytes, count: int) -> list[float]:
    if fmt not in LAYOUT or count <= 0:
        raise ValueError("unsupported format or count")
    block_values, block_bytes = LAYOUT[fmt]
    if count % block_values or len(encoded) != count // block_values * block_bytes:
        raise ValueError("encoded size/geometry mismatch")
    output: list[float] = []
    for offset in range(0, len(encoded), block_bytes):
        output.extend(_decode_block(fmt, encoded[offset:offset + block_bytes]))
    if len(output) != count:
        raise ValueError("decoder output census mismatch")
    return output


def matvec(fmt: str, encoded: bytes, rows: int, columns: int, vector: list[float]) -> list[float]:
    if len(vector) != columns or rows <= 0:
        raise ValueError("matvec geometry")
    values = decode(fmt, encoded, rows * columns)
    return [sum(float(values[r * columns + c]) * float(vector[c]) for c in range(columns)) for r in range(rows)]
