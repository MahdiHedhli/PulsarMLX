#!/usr/bin/env python3
"""CPU dequant for GGML K-quants used by GLM-5.2 UD-IQ2_XXS (Q4_K, Q5_K, Q6_K)."""

from __future__ import annotations

import struct

QK_K = 256
K_SCALE_SIZE = 12
Q4_K_BLOCK = 144  # 2*f16 + 12 + 128
Q5_K_BLOCK = 176  # 2*f16 + 12 + 128 + 32
Q6_K_BLOCK = 210  # f16 + 128 + 64 + 16?  verify: sizeof = 210


def _get_scale_min_k4(j: int, q: bytes) -> tuple[int, int]:
    if j < 4:
        d = q[j] & 63
        m = q[j + 4] & 63
    else:
        d = (q[j + 4] & 0xF) | ((q[j - 4] >> 6) << 4)
        m = (q[j + 4] >> 4) | ((q[j - 0] >> 6) << 4)
    return d, m


def dequantize_row_q4_k(encoded: bytes, n: int | None = None) -> list[float]:
    if n is None:
        assert len(encoded) % Q4_K_BLOCK == 0
        n = (len(encoded) // Q4_K_BLOCK) * QK_K
    assert n % QK_K == 0
    nb = n // QK_K
    out: list[float] = []
    for i in range(nb):
        base = i * Q4_K_BLOCK
        d = struct.unpack_from("<e", encoded, base)[0]
        dmin = struct.unpack_from("<e", encoded, base + 2)[0]
        scales = encoded[base + 4 : base + 4 + K_SCALE_SIZE]
        q = encoded[base + 4 + K_SCALE_SIZE : base + Q4_K_BLOCK]
        qoff = 0
        is_ = 0
        for _j in range(0, QK_K, 64):
            sc, m = _get_scale_min_k4(is_ + 0, scales)
            d1, m1 = d * sc, dmin * m
            sc, m = _get_scale_min_k4(is_ + 1, scales)
            d2, m2 = d * sc, dmin * m
            for l in range(32):
                out.append(d1 * (q[qoff + l] & 0xF) - m1)
            for l in range(32):
                out.append(d2 * (q[qoff + l] >> 4) - m2)
            qoff += 32
            is_ += 2
    return out


def dequantize_row_q6_k(encoded: bytes, n: int | None = None) -> list[float]:
    """Independent scalar port of ggml dequantize_row_q6_K."""
    if n is None:
        assert len(encoded) % Q6_K_BLOCK == 0
        n = (len(encoded) // Q6_K_BLOCK) * QK_K
    assert n % QK_K == 0
    out: list[float] = []
    for i in range(n // QK_K):
        base = i * Q6_K_BLOCK
        ql = encoded[base : base + 128]
        qh = encoded[base + 128 : base + 192]
        scales = struct.unpack_from("<16b", encoded, base + 192)
        d = struct.unpack_from("<e", encoded, base + 208)[0]
        out.extend(_q6_k_block(ql, qh, scales, d))
    return out


def _q6_k_block(ql: bytes, qh: bytes, scales: tuple, d: float) -> list[float]:
    """Decode one block with the official ql low/high-nibble lane order."""
    out = [0.0] * 256
    for half in range(2):
        ql_offset = 64 * half
        qh_offset = 32 * half
        base = 128 * half
        for lane in range(32):
            high = qh[qh_offset + lane]
            quantized = (
                ((ql[ql_offset + lane] & 0x0F) | ((high & 0x03) << 4)) - 32,
                ((ql[ql_offset + 32 + lane] & 0x0F) | (((high >> 2) & 0x03) << 4)) - 32,
                ((ql[ql_offset + lane] >> 4) | (((high >> 4) & 0x03) << 4)) - 32,
                ((ql[ql_offset + 32 + lane] >> 4) | (((high >> 6) & 0x03) << 4)) - 32,
            )
            for quarter, quantized_value in enumerate(quantized):
                index = base + 32 * quarter + lane
                out[index] = d * scales[index // 16] * quantized_value
    return out


def dequantize_row_q5_k(encoded: bytes, n: int | None = None) -> list[float]:
    """Q5_K block: d,dmin (f16), scales[12], qh[32], qs[128] = 176 bytes."""
    if n is None:
        assert len(encoded) % Q5_K_BLOCK == 0
        n = (len(encoded) // Q5_K_BLOCK) * QK_K
    assert n % QK_K == 0
    # Port from ggml dequantize_row_q5_K - similar to q4_k with high bits
    out: list[float] = []
    nb = n // QK_K
    for i in range(nb):
        base = i * Q5_K_BLOCK
        d = struct.unpack_from("<e", encoded, base)[0]
        dmin = struct.unpack_from("<e", encoded, base + 2)[0]
        scales = encoded[base + 4 : base + 16]
        qh = encoded[base + 16 : base + 48]
        qs = encoded[base + 48 : base + 176]
        # from ggml:
        u1, u2 = 1, 2
        q = qs
        qh_i = 0
        is_ = 0
        # simplified: use reference loop from source
        out.extend(_q5_k_block(d, dmin, scales, qh, qs))
    return out


def _q5_k_block(d: float, dmin: float, scales: bytes, qh: bytes, qs: bytes) -> list[float]:
    # ggml dequantize_row_q5_K
    y: list[float] = []
    q = list(qs)
    qh_b = list(qh)
    u1, u2 = 1, 2
    is_ = 0
    qoff = 0
    for j in range(0, QK_K, 64):
        sc, m = _get_scale_min_k4(is_ + 0, scales)
        d1, m1 = d * sc, dmin * m
        sc, m = _get_scale_min_k4(is_ + 1, scales)
        d2, m2 = d * sc, dmin * m
        for l in range(32):
            y.append(d1 * ((q[qoff + l] & 0xF) + ((qh_b[l] & u1) and 16 or 0)) - m1)
        for l in range(32):
            y.append(d2 * ((q[qoff + l] >> 4) + ((qh_b[l] & u2) and 16 or 0)) - m2)
        qoff += 32
        is_ += 2
        u1 <<= 2
        u2 <<= 2
    return y


Q2_K_BLOCK = 84
Q3_K_BLOCK = 110


def dequantize_row_q2_k(encoded: bytes, n: int | None = None) -> list[float]:
    if n is None:
        assert len(encoded) % Q2_K_BLOCK == 0
        n = (len(encoded) // Q2_K_BLOCK) * QK_K
    assert n % QK_K == 0
    out: list[float] = []
    for i in range(n // QK_K):
        base = i * Q2_K_BLOCK
        scales = encoded[base : base + 16]
        qs = encoded[base + 16 : base + 80]
        d = struct.unpack_from("<e", encoded, base + 80)[0]
        dmin = struct.unpack_from("<e", encoded, base + 82)[0]
        y = [0.0] * QK_K
        for nn in range(2):
            for j in range(32):
                byte = qs[32 * nn + j]
                for s in range(4):
                    idx = 128 * nn + 32 * s + j
                    q = (byte >> (2 * s)) & 3
                    sub = idx // 16
                    y[idx] = d * (scales[sub] & 0xF) * q - dmin * (scales[sub] >> 4)
        out.extend(y)
    return out


def _q3_scales(sb: bytes) -> list[int]:
    sc = [0] * 16
    for j in range(16):
        lo = sb[j] & 0xF if j < 8 else sb[j - 8] >> 4
        hi = (sb[8 + j % 4] >> (2 * (j // 4))) & 3
        sc[j] = (lo | (hi << 4)) - 32
    return sc


def dequantize_row_q3_k(encoded: bytes, n: int | None = None) -> list[float]:
    if n is None:
        assert len(encoded) % Q3_K_BLOCK == 0
        n = (len(encoded) // Q3_K_BLOCK) * QK_K
    assert n % QK_K == 0
    out: list[float] = []
    for i in range(n // QK_K):
        base = i * Q3_K_BLOCK
        hmask = encoded[base : base + 32]
        qs = encoded[base + 32 : base + 96]
        sc = _q3_scales(encoded[base + 96 : base + 108])
        d = struct.unpack_from("<e", encoded, base + 108)[0]
        y = [0.0] * QK_K
        for nn in range(2):
            for j in range(32):
                byte = qs[32 * nn + j]
                for s in range(4):
                    idx = 128 * nn + 32 * s + j
                    q = (byte >> (2 * s)) & 3
                    if (hmask[j] & (1 << (4 * nn + s))) == 0:
                        q -= 4
                    y[idx] = d * sc[idx // 16] * q
        out.extend(y)
    return out
