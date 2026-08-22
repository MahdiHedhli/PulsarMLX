#!/usr/bin/env python3
"""Checkpoint-free independent eleven-format decoder differential.

Synthetic encoded blocks are interpreted by independent Python scalar ports
and by the Rust decoder probe. The script has no checkpoint-path option.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import struct
import subprocess
from pathlib import Path

from ggml_kquants import (
    dequantize_row_q2_k,
    dequantize_row_q3_k,
    dequantize_row_q4_k,
    dequantize_row_q5_k,
    dequantize_row_q6_k,
)
from glm52_dense_primitives import _decode_q8_0_row
from iq2_s_dequant import dequantize_row_iq2_s
from iq2_xxs_dequant import dequantize_row_iq2_xxs
from iq3_xxs_dequant import dequantize_row_iq3_xxs
from iq4_xs_dequant import dequantize_row_iq4_xs


FORMATS = {
    "F32": (0, 32, 128),
    "Q2_K": (10, 256, 84),
    "Q3_K": (11, 256, 110),
    "Q4_K": (12, 256, 144),
    "Q5_K": (13, 256, 176),
    "Q6_K": (14, 256, 210),
    "Q8_0": (8, 32, 34),
    "IQ2_S": (22, 256, 82),
    "IQ2_XXS": (16, 256, 66),
    "IQ3_XXS": (18, 256, 98),
    "IQ4_XS": (23, 256, 136),
}


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", f32(value)))[0]


def independent_decode(fmt: str, encoded: bytes, columns: int) -> list[float]:
    if fmt == "F32":
        return list(struct.unpack(f"<{columns}f", encoded))
    if fmt == "Q2_K":
        return dequantize_row_q2_k(encoded, columns)
    if fmt == "Q3_K":
        return dequantize_row_q3_k(encoded, columns)
    if fmt == "Q4_K":
        return dequantize_row_q4_k(encoded, columns)
    if fmt == "Q5_K":
        return dequantize_row_q5_k(encoded, columns)
    if fmt == "Q6_K":
        return dequantize_row_q6_k(encoded, columns)
    if fmt == "Q8_0":
        return _decode_q8_0_row(encoded, columns)
    if fmt == "IQ2_S":
        return dequantize_row_iq2_s(encoded, columns)
    if fmt == "IQ2_XXS":
        return dequantize_row_iq2_xxs(encoded, columns)
    if fmt == "IQ3_XXS":
        return dequantize_row_iq3_xxs(encoded, columns)
    if fmt == "IQ4_XS":
        return dequantize_row_iq4_xs(encoded, columns)
    raise ValueError(fmt)


def synthetic_block(fmt: str, mode: str, seed: int) -> bytes:
    _, columns, size = FORMATS[fmt]
    if fmt == "F32":
        values = [0.0, -0.0, 1.0, -1.0]
        while len(values) < columns:
            index = len(values)
            values.append(f32(((index % 17) - 8) / 13.0))
        if mode == "zero":
            values = [0.0] * columns
        elif mode == "subnormal":
            values = [struct.unpack("<f", struct.pack("<I", 1))[0]] * columns
        return struct.pack(f"<{columns}f", *values)
    if mode == "zero":
        return bytes(size)
    rng = random.Random(seed)
    block = bytearray(rng.randrange(256) for _ in range(size))
    scale = {"pattern": 0x3800, "subnormal": 0x0001, "max_finite": 0x7BFF}[mode]
    scale_bytes = struct.pack("<H", scale)
    if fmt == "Q2_K":
        block[80:82] = scale_bytes
        block[82:84] = struct.pack("<H", 0x3400 if mode == "pattern" else scale)
    elif fmt == "Q3_K":
        block[108:110] = scale_bytes
    elif fmt in {"Q4_K", "Q5_K"}:
        block[0:2] = scale_bytes
        block[2:4] = struct.pack("<H", 0x3400 if mode == "pattern" else scale)
    elif fmt == "Q6_K":
        block[208:210] = scale_bytes
    else:
        block[0:2] = scale_bytes
    return bytes(block)


def activation(columns: int) -> list[float]:
    return [
        f32(((-1.0 if index % 2 else 1.0) * ((index % 19) - 9)) / 11.0)
        for index in range(columns)
    ]


def f32_matvec(matrix: list[float], rows: int, columns: int, vector: list[float]) -> list[float]:
    output = []
    for row in range(rows):
        total = 0.0
        for column in range(columns):
            total = f32(total + f32(matrix[row * columns + column] * vector[column]))
        output.append(total)
    return output


def ocb_bound(matrix: list[float], rows: int, columns: int, vector: list[float]) -> list[float]:
    unit = 2.0**-24
    gamma = (2.0 * columns * unit) / (1.0 - 2.0 * columns * unit)
    minimum_subnormal = 2.0**-149
    return [
        2.0 * gamma * sum(
            abs(float(matrix[row * columns + column]) * float(vector[column]))
            for column in range(columns)
        ) + 4.0 * columns * minimum_subnormal
        for row in range(rows)
    ]


def invoke(
    binary: Path,
    fmt: str,
    type_id: int,
    encoded: bytes,
    rows: int,
    columns: int,
    vector: list[float],
) -> dict:
    request = json.dumps(
        {
            "format": fmt,
            "type_id": type_id,
            "rows": rows,
            "columns": columns,
            "encoded_hex": encoded.hex(),
            "activation_f32_bits": [bits(value) for value in vector],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    completed = subprocess.run([str(binary)], input=request, capture_output=True, check=True)
    response = json.loads(completed.stdout)
    if set(response) != {
        "format", "type_id", "rows", "columns", "decoded_f32_bits",
        "output_f32_bits", "backend", "original_checkpoint_reads",
    }:
        raise ValueError("probe response key census")
    if response["original_checkpoint_reads"] != 0:
        raise ValueError("probe checkpoint access")
    return response


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.binary.is_file() or args.binary.is_symlink():
        raise SystemExit("unsafe decoder probe")
    if args.output.exists():
        raise SystemExit("output must be absent")
    rows = []
    for ordinal, (fmt, (type_id, columns, _)) in enumerate(FORMATS.items()):
        cases = []
        for mode in ("zero", "pattern", "subnormal", "max_finite"):
            row_count = 2
            encoded_rows = [
                synthetic_block(fmt, mode, 17017 + ordinal * 101 + row)
                for row in range(row_count)
            ]
            encoded = b"".join(encoded_rows)
            expected = [
                value for block in encoded_rows for value in independent_decode(fmt, block, columns)
            ]
            vector = activation(columns)
            response = invoke(args.binary, fmt, type_id, encoded, row_count, columns, vector)
            actual_bits = response["decoded_f32_bits"]
            actual = [struct.unpack("<f", struct.pack("<I", value))[0] for value in actual_bits]
            if len(expected) != row_count * columns or len(actual) != row_count * columns:
                raise SystemExit(f"{fmt}/{mode}: shape")
            if any(not math.isfinite(value) for value in expected + actual):
                raise SystemExit(f"{fmt}/{mode}: nonfinite")
            differences = [abs(float(a) - float(b)) for a, b in zip(actual, expected, strict=True)]
            maximum = max((abs(float(value)) for value in expected), default=0.0)
            tolerance = 8.0 * 2.0**-23 * max(1.0, maximum)
            max_abs = max(differences, default=0.0)
            rmse = math.sqrt(sum(value * value for value in differences) / len(differences))
            exact_bits = actual_bits == [bits(value) for value in expected]
            if max_abs > tolerance:
                raise SystemExit(
                    f"{fmt}/{mode}: max_abs={max_abs} exceeds frozen analytical tolerance={tolerance}"
                )
            expected_matvec = f32_matvec(expected, row_count, columns, vector)
            actual_matvec = [
                struct.unpack("<f", struct.pack("<I", value))[0]
                for value in response["output_f32_bits"]
            ]
            matvec_bounds = ocb_bound(expected, row_count, columns, vector)
            matvec_errors = [
                abs(float(actual_value) - float(expected_value))
                for actual_value, expected_value in zip(actual_matvec, expected_matvec, strict=True)
            ]
            if any(error > bound for error, bound in zip(matvec_errors, matvec_bounds, strict=True)):
                raise SystemExit(f"{fmt}/{mode}: native MLX matvec exceeded frozen OCB")
            cases.append(
                {
                    "mode": mode,
                    "encoded_sha256": hashlib.sha256(encoded).hexdigest(),
                    "coordinate_count": row_count * columns,
                    "exact_f32_bits": exact_bits,
                    "max_abs_error": max_abs,
                    "rmse": rmse,
                    "frozen_tolerance": tolerance,
                    "tolerance_derivation": "8*binary32_unit_roundoff*max(1,max_abs_independent_expected)",
                    "native_mlx_matvec_max_abs_error": max(matvec_errors, default=0.0),
                    "native_mlx_matvec_max_ocb": max(matvec_bounds, default=0.0),
                    "native_mlx_matvec_within_frozen_ocb": True,
                }
            )
        malformed = synthetic_block(fmt, "pattern", 17017 + ordinal * 101)[:-1]
        malformed_request = json.dumps(
            {
                "format": fmt,
                "type_id": type_id,
                "rows": 1,
                "columns": columns,
                "encoded_hex": malformed.hex(),
                "activation_f32_bits": [bits(value) for value in activation(columns)],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        malformed_result = subprocess.run([str(args.binary)], input=malformed_request, capture_output=True)
        if malformed_result.returncode == 0:
            raise SystemExit(f"{fmt}: malformed block accepted")
        rows.append(
            {
                "format": fmt,
                "independent_oracle": "PYTHON_SCALAR_FORMAT_PORT",
                "native_implementation": "SECURE_LOADER_DECODER_DISPATCH_PLUS_NATIVE_MLX_F32_MATVEC",
                "cases": cases,
                "malformed_length_rejected": True,
                "result": "PASS",
            }
        )
    document = {
        "schema": "pulsarmlx.f017.native-quantization-eleven-format-differential/1.0.0",
        "result": "PASS",
        "seed": 17017,
        "formats": rows,
        "format_count": len(rows),
        "case_count": sum(len(row["cases"]) for row in rows),
        "type_id_dispatch_validated_separately_by_plan_audit": True,
        "original_checkpoint_shard_opens": 0,
        "original_checkpoint_payload_reads": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")
    print(f"PASS formats={len(rows)} cases={document['case_count']}")


if __name__ == "__main__":
    main()
