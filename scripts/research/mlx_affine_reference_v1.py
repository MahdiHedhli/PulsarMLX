#!/usr/bin/env python3
"""R1 -- an independent reference for the MLX affine quantized representation.

Authoring order, stated so the independence claim can be checked rather than
believed: this module was written **first**, from the written format
specification alone, before any line of the Rust decoder
(`crates/mlx-affine/src/decode.rs`) or of the Rust reference
(`crates/mlx-affine/src/reference.rs`) existed.  It imports nothing from
PulsarMLX and nothing from MLX.  Its only inputs are the specification
statements reproduced verbatim below.

Specification used (no code was transcribed):

*  Packing.  "is packed in an unsigned 32-bit integer from the lower to upper
   bits.  For instance, for 4-bit quantization we fit 8 elements in an unsigned
   32 bit integer where the 1st element occupies the 4 least significant bits,
   the 2nd bits 4-7 etc."  (MLX `python/src/ops.cpp` docstring, quoted in the
   F020 Phase 0 inventory W2 section 4.)  Element `j` of the last axis
   therefore occupies bits `[j*bits, j*bits + bits)` of the row's contiguous
   little-endian `uint32` bit stream, and a code may straddle a word boundary
   when `32 % bits != 0`.

*  Grouping.  A group is `group_size` consecutive elements along the **last**
   axis.  `scales` and `biases` have the same shape as the logical weight
   except that the last axis is `in_features / group_size`.

*  Dequantization.  `w_i = scale_g * q_i + bias_g`, with `g = i // group_size`.

*  Shape invariant.  `w.shape[-1] * 32 / bits == scales.shape[-1] * group_size`.

*  Encoder (used only by `quantize_group`, for fixture construction).  The
   implemented encoder is not the documented one: the scale is **signed**, the
   larger-magnitude group edge becomes the bias, and the scale is snapped so
   that the edge quantizes exactly:

       mask  = |w_min| > |w_max|
       s     = max((w_max - w_min) / (2**b - 1), 1e-7);  s = s if mask else -s
       edge  = w_min if mask else w_max
       q0    = round(edge / s);  s = edge / q0 if q0 != 0 else s
       bias  = 0.0 if q0 == 0 else edge
       q     = clip(round((w - bias) / s), 0, 2**b - 1)

All dequantization arithmetic here is Python `float`, i.e. IEEE-754 binary64.
"""

from __future__ import annotations

import math
import struct

MAX_BITS = 8
SUPPORTED_GROUP_SIZES = (32, 64, 128)


class ReferenceError(ValueError):
    """Raised when an input violates the format specification."""


# ---------------------------------------------------------------------------
# Exact conversions of stored metadata to binary64.
# ---------------------------------------------------------------------------


def bf16_to_float(bits: int) -> float:
    """bfloat16 is the leading 16 bits of binary32; widening is exact."""
    if not 0 <= bits <= 0xFFFF:
        raise ReferenceError("bf16 bit pattern out of range")
    return struct.unpack("<f", struct.pack("<I", bits << 16))[0]


def f16_to_float(bits: int) -> float:
    """IEEE-754 binary16 to binary64; every binary16 value is exact in binary64."""
    if not 0 <= bits <= 0xFFFF:
        raise ReferenceError("f16 bit pattern out of range")
    return struct.unpack("<e", struct.pack("<H", bits))[0]


def f32_to_float(bits: int) -> float:
    """IEEE-754 binary32 to binary64; exact."""
    if not 0 <= bits <= 0xFFFFFFFF:
        raise ReferenceError("f32 bit pattern out of range")
    return struct.unpack("<f", struct.pack("<I", bits))[0]


def float_to_f32_bits(value: float) -> int:
    """Round a binary64 to binary32 and return its bit pattern."""
    return struct.unpack("<I", struct.pack("<f", value))[0]


def round_to_f32(value: float) -> float:
    """Round a binary64 to the nearest binary32, returned as a binary64."""
    return struct.unpack("<f", struct.pack("<f", value))[0]


def float_to_bf16_bits(value: float) -> int:
    """Round-to-nearest-even binary32 -> bfloat16, returned as 16 bits."""
    bits = float_to_f32_bits(value)
    if (bits & 0x7F800000) == 0x7F800000 and (bits & 0x007FFFFF):
        return (bits >> 16) & 0xFFFF
    lower = bits & 0xFFFF
    upper = (bits >> 16) & 0xFFFF
    if lower > 0x8000 or (lower == 0x8000 and (upper & 1)):
        upper = (upper + 1) & 0xFFFF
    return upper


def float_to_f16_bits(value: float) -> int:
    return struct.unpack("<H", struct.pack("<e", value))[0]


CONVERTERS = {
    "BF16": bf16_to_float,
    "F16": f16_to_float,
    "F32": f32_to_float,
}


# ---------------------------------------------------------------------------
# Unpacking.
# ---------------------------------------------------------------------------


def extract_code(words, bits: int, index: int) -> int:
    """Code `index` of a contiguous little-endian uint32 bit stream.

    Written from the packing statement above: bit `k` of the stream is bit
    `k % 32` of word `k // 32`, and code `index` occupies the `bits` bit
    positions starting at `index * bits`.  The loop is bit-serial on purpose so
    that codes which straddle a word boundary are handled by construction
    rather than by a special case.
    """
    if bits <= 0 or bits > 32:
        raise ReferenceError("bits out of range")
    value = 0
    for offset in range(bits):
        position = index * bits + offset
        word = position // 32
        if word >= len(words):
            raise ReferenceError("bit position beyond the packed stream")
        value |= ((words[word] >> (position % 32)) & 1) << offset
    return value


def unpack_row(words, bits: int, columns: int):
    """Every code of one logical row, in column order."""
    return [extract_code(words, bits, index) for index in range(columns)]


# ---------------------------------------------------------------------------
# Dequantization (binary64 throughout).
# ---------------------------------------------------------------------------


def check_shape_invariant(packed_columns: int, bits: int, groups: int, group_size: int) -> None:
    left = packed_columns * 32
    right = groups * group_size * bits
    if left != right:
        raise ReferenceError(
            "shape invariant violated: %d * 32 != %d * %d * %d"
            % (packed_columns, groups, group_size, bits)
        )


def dequantize_rows(words, scale_bits, bias_bits, *, bits, group_size, rows, columns,
                    metadata_dtype="BF16"):
    """Dequantize `rows` logical rows of `columns` elements each.

    `words` is the flat little-endian uint32 stream of the whole tensor,
    `scale_bits` and `bias_bits` are the flat stored bit patterns of the
    metadata in `metadata_dtype`.  The result is a flat list of binary64
    values in row-major order.
    """
    if group_size not in SUPPORTED_GROUP_SIZES:
        raise ReferenceError("unsupported group size")
    if bits <= 0 or bits > MAX_BITS:
        raise ReferenceError("unsupported bit width")
    if columns % group_size:
        raise ReferenceError("columns are not a whole number of groups")
    if columns * bits % 32:
        raise ReferenceError("a row is not a whole number of packed words")
    convert = CONVERTERS.get(metadata_dtype)
    if convert is None:
        raise ReferenceError("unsupported metadata dtype")

    groups = columns // group_size
    packed_columns = columns * bits // 32
    check_shape_invariant(packed_columns, bits, groups, group_size)
    if len(words) != rows * packed_columns:
        raise ReferenceError("packed stream length does not match the geometry")
    if len(scale_bits) != rows * groups or len(bias_bits) != rows * groups:
        raise ReferenceError("metadata length does not match the geometry")

    out = []
    for row in range(rows):
        row_words = words[row * packed_columns:(row + 1) * packed_columns]
        codes = unpack_row(row_words, bits, columns)
        for column, code in enumerate(codes):
            group = row * groups + column // group_size
            scale = convert(scale_bits[group])
            bias = convert(bias_bits[group])
            out.append(scale * code + bias)
    return out


# ---------------------------------------------------------------------------
# Encoder, for fixture construction only.
# ---------------------------------------------------------------------------


def quantize_group(values, bits: int, metadata_dtype="BF16"):
    """Quantize one group, following the implemented MLX encoder.

    Returns `(codes, scale_bits, bias_bits)` with the metadata already rounded
    to `metadata_dtype`, which is what a checkpoint stores.
    """
    if not values:
        raise ReferenceError("empty group")
    low = min(values)
    high = max(values)
    mask = abs(low) > abs(high)
    scale = max((high - low) / (2 ** bits - 1), 1e-7)
    if not mask:
        scale = -scale
    edge = low if mask else high
    q0 = math.floor(edge / scale + 0.5) if scale != 0.0 else 0.0
    if q0 != 0:
        scale = edge / q0
        bias = edge
    else:
        bias = 0.0

    if metadata_dtype == "BF16":
        scale_bits = float_to_bf16_bits(scale)
        bias_bits = float_to_bf16_bits(bias)
    elif metadata_dtype == "F16":
        scale_bits = float_to_f16_bits(scale)
        bias_bits = float_to_f16_bits(bias)
    elif metadata_dtype == "F32":
        scale_bits = float_to_f32_bits(scale)
        bias_bits = float_to_f32_bits(bias)
    else:
        raise ReferenceError("unsupported metadata dtype")

    scale = CONVERTERS[metadata_dtype](scale_bits)
    bias = CONVERTERS[metadata_dtype](bias_bits)
    codes = []
    for value in values:
        if scale == 0.0:
            code = 0
        else:
            code = int(math.floor((value - bias) / scale + 0.5))
        codes.append(min(max(code, 0), 2 ** bits - 1))
    return codes, scale_bits, bias_bits


def pack_codes(codes, bits: int):
    """Pack codes into a little-endian uint32 stream, lowest bits first."""
    total = len(codes) * bits
    if total % 32:
        raise ReferenceError("codes do not fill a whole number of words")
    words = [0] * (total // 32)
    for index, code in enumerate(codes):
        if not 0 <= code < 2 ** bits:
            raise ReferenceError("code out of range")
        for offset in range(bits):
            if (code >> offset) & 1:
                position = index * bits + offset
                words[position // 32] |= 1 << (position % 32)
    return words


def quantize_rows(values, *, bits, group_size, rows, columns, metadata_dtype="BF16"):
    """Quantize a row-major binary64 matrix.  Returns (words, scales, biases)."""
    if len(values) != rows * columns:
        raise ReferenceError("value count does not match the geometry")
    codes = []
    scales = []
    biases = []
    for row in range(rows):
        for group in range(columns // group_size):
            start = row * columns + group * group_size
            chunk = values[start:start + group_size]
            group_codes, scale_bits, bias_bits = quantize_group(chunk, bits, metadata_dtype)
            codes.extend(group_codes)
            scales.append(scale_bits)
            biases.append(bias_bits)
    words = []
    packed_columns = columns * bits // 32
    for row in range(rows):
        words.extend(pack_codes(codes[row * columns:(row + 1) * columns], bits))
    if len(words) != rows * packed_columns:
        raise ReferenceError("packing produced the wrong word count")
    return words, scales, biases
