#!/usr/bin/env python3
"""Single expert SwiGLU for GLM-5.2 (architecture CPU path)."""

from __future__ import annotations

import math
from pathlib import Path

from glm52_tensor_store import Glm52TensorStore, nbytes_for_tensor
from iq2_xxs_dequant import dequantize_row_iq2_xxs, BLOCK_BYTES as IQ2_B, QK_K
from iq3_xxs_dequant import dequantize_row_iq3_xxs, BLOCK_BYTES as IQ3_B
from iq2_s_dequant import dequantize_row_iq2_s
from iq4_xs_dequant import dequantize_row_iq4_xs
from ggml_kquants import (
    dequantize_row_q2_k,
    dequantize_row_q3_k,
    dequantize_row_q5_k,
    dequantize_row_q6_k,
    Q5_K_BLOCK,
    Q6_K_BLOCK,
)


def _silu(x: float) -> float:
    # x * sigmoid(x)
    if x >= 0:
        return x / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return x * ex / (1.0 + ex)


def _row_bytes(type_id: int, cols: int) -> int:
    return nbytes_for_tensor(type_id, cols)


def _dequant_row_bytes(type_id: int, raw: bytes, cols: int) -> list[float]:
    if type_id == 16:  # IQ2_XXS
        return dequantize_row_iq2_xxs(raw, cols)
    if type_id == 18:  # IQ3_XXS
        return dequantize_row_iq3_xxs(raw, cols)
    if type_id == 22:  # IQ2_S
        return dequantize_row_iq2_s(raw, cols)
    if type_id == 23:  # IQ4_XS
        return dequantize_row_iq4_xs(raw, cols)
    if type_id == 10:  # Q2_K
        return dequantize_row_q2_k(raw, cols)
    if type_id == 11:  # Q3_K
        return dequantize_row_q3_k(raw, cols)
    if type_id == 13:  # Q5_K
        return dequantize_row_q5_k(raw, cols)
    if type_id == 14:  # Q6_K
        return dequantize_row_q6_k(raw, cols)
    if type_id == 8:  # Q8_0 (some shexp / rare slabs)
        from glm52_dense_primitives import _decode_q8_0_row

        return _decode_q8_0_row(raw, cols)
    if type_id == 0:
        import struct

        return list(struct.unpack(f"<{cols}f", raw))
    raise TypeError(type_id)


def expert_matvec(
    store: Glm52TensorStore,
    name: str,
    expert: int,
    x: list[float],
) -> list[float]:
    """3D expert tensor [cols, rows, n_expert] or 2D shexp [cols, rows]."""
    loc = store.tensors[name]
    if len(loc.dims) == 2:
        # shared expert full matrix
        cols, rows = int(loc.dims[0]), int(loc.dims[1])
        assert len(x) == cols
        rb = _row_bytes(loc.type_id, cols)
        y = [0.0] * rows
        for r in range(rows):
            raw = store.pread(name, r * rb, rb)
            w = _dequant_row_bytes(loc.type_id, raw, cols)
            y[r] = sum(a * b for a, b in zip(w, x, strict=True))
        return y
    if len(loc.dims) != 3:
        raise ValueError(name)
    cols, rows, n_exp = int(loc.dims[0]), int(loc.dims[1]), int(loc.dims[2])
    if expert < 0 or expert >= n_exp:
        raise IndexError(expert)
    assert len(x) == cols
    rb = _row_bytes(loc.type_id, cols)
    expert_bytes = rb * rows
    base = expert * expert_bytes
    y = [0.0] * rows
    for r in range(rows):
        raw = store.pread(name, base + r * rb, rb)
        w = _dequant_row_bytes(loc.type_id, raw, cols)
        y[r] = sum(a * b for a, b in zip(w, x, strict=True))
    return y


def run_expert_swiglu(
    store: Glm52TensorStore,
    layer: int,
    expert: int,
    x: list[float],
    weight: float = 1.0,
    *,
    shared: bool = False,
) -> list[float]:
    if shared:
        g = expert_matvec(store, f"blk.{layer}.ffn_gate_shexp.weight", 0, x)
        u = expert_matvec(store, f"blk.{layer}.ffn_up_shexp.weight", 0, x)
        h = [_silu(a) * b for a, b in zip(g, u, strict=True)]
        d = expert_matvec(store, f"blk.{layer}.ffn_down_shexp.weight", 0, h)
    else:
        g = expert_matvec(store, f"blk.{layer}.ffn_gate_exps.weight", expert, x)
        u = expert_matvec(store, f"blk.{layer}.ffn_up_exps.weight", expert, x)
        h = [_silu(a) * b for a, b in zip(g, u, strict=True)]
        d = expert_matvec(store, f"blk.{layer}.ffn_down_exps.weight", expert, h)
    return [weight * v for v in d]
