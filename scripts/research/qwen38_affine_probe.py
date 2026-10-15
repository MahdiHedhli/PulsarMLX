"""Tiny, checkpoint-free MLX affine geometry probe for the Qwen pager.

The scalar oracle uses Python integer bit extraction and arithmetic. MLX is
imported only by ``run_mlx``; this is not a model or checkpoint parity test.
"""
from __future__ import annotations

import importlib.metadata
import json
import platform
import sys


def fixtures():
    """Use exact binary floats and distinct rows to expose packing/orientation."""
    return (
        (4, 32, (
            tuple(i % 16 for i in range(64)),
            tuple(15 - i % 16 for i in range(64)),
        ), ((0.25, 0.5), (0.5, -0.25)), ((-1.0, 2.0), (2.0, -4.0))),
        (8, 64, (
            tuple((3 * i) % 256 for i in range(128)),
            tuple((255 - 2 * i) % 256 for i in range(128)),
        ), ((0.125, 0.25), (-0.25, 0.5)), ((-4.0, -8.0), (12.0, 1.0))),
    )


def packed_words(rows, bits):
    if (bits not in (4, 8) or not rows or
            any(len(row) != len(rows[0]) or len(row) == 0 or len(row) % (32 // bits) for row in rows)):
        raise ValueError("invalid affine geometry")
    width = 32 // bits
    limit = 1 << bits
    if any(type(value) is not int or not 0 <= value < limit for row in rows for value in row):
        raise ValueError("quantized value out of range")
    return tuple(tuple(sum(value << (bits * offset) for offset, value in enumerate(row[start:start + width]))
                       for start in range(0, len(row), width)) for row in rows)


def scalar_dequantize(words, scales, biases, bits, group_size):
    if bits not in (4, 8) or group_size not in (32, 64) or len(words) != len(scales) or len(words) != len(biases):
        raise ValueError("invalid affine metadata")
    width = 32 // bits
    mask = (1 << bits) - 1
    result = []
    for row, row_scales, row_biases in zip(words, scales, biases):
        count = len(row) * width
        if count % group_size or len(row_scales) != count // group_size or len(row_biases) != count // group_size:
            raise ValueError("invalid affine group shape")
        result.append(tuple(row_scales[i // group_size] * ((row[i // width] >> (bits * (i % width))) & mask)
                            + row_biases[i // group_size] for i in range(count)))
    return tuple(result)


def run_mlx():
    import mlx.core as mx

    # The bounded probe uses CPU intentionally. Sandboxed Codex sessions do
    # not necessarily expose Metal; this cannot qualify GPU fences or memory.
    mx.set_default_device(mx.cpu)
    results = []
    for bits, group_size, rows, scales, biases in fixtures():
        words = packed_words(rows, bits)
        expected = scalar_dequantize(words, scales, biases, bits, group_size)
        if expected != tuple(tuple(scales[r][i // group_size] * code + biases[r][i // group_size]
                                   for i, code in enumerate(row)) for r, row in enumerate(rows)):
            raise AssertionError("scalar fixture mismatch")
        w = mx.array(words, dtype=mx.uint32)
        # The admitted checkpoint stores these affine partners as BF16.
        s = mx.array(scales, dtype=mx.bfloat16)
        b = mx.array(biases, dtype=mx.bfloat16)
        actual = mx.dequantize(w, s, b, group_size=group_size, bits=bits, mode="affine", dtype=mx.float32)
        # Sparse and nonsymmetric inputs check both default Qwen linear orientation
        # and that the last packed word is not silently dropped.
        x_values = tuple(1.0 if i == 0 else (-2.0 if i == len(rows[0]) - 1 else 0.0)
                         for i in range(len(rows[0])))
        x = mx.array((x_values,), dtype=mx.float32)
        product = mx.quantized_matmul(x, w, s, b, transpose=True,
                                      group_size=group_size, bits=bits, mode="affine")
        mx.eval(actual, product)
        dense_values = tuple(tuple(float(v) for v in row) for row in actual.tolist())
        product_values = tuple(float(v) for v in product.tolist()[0])
        expected_product = tuple(row[0] - 2 * row[-1] for row in expected)
        if dense_values != expected or product_values != expected_product:
            raise AssertionError({"bits": bits, "group_size": group_size,
                                  "dequantized_match": dense_values == expected,
                                  "product_actual": product_values,
                                  "product_expected": expected_product})
        results.append({"bits": bits, "group_size": group_size, "rows": len(rows),
                        "columns": len(rows[0]), "dequantized_values": sum(map(len, rows)),
                        "dequantized_exact": True, "matmul_exact": True})
    return {"scope": "tiny_fixture_only", "device": "cpu", "checkpoint_read": False,
            "model_parity": False, "python": sys.version.split()[0],
            "platform": platform.platform(), "mlx": importlib.metadata.version("mlx"),
            "results": results}


if __name__ == "__main__":
    if sys.argv[1:] != ["--run-tiny-mlx"]:
        raise SystemExit("usage: qwen38_affine_probe.py --run-tiny-mlx")
    print(json.dumps(run_mlx(), sort_keys=True))
