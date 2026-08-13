#!/usr/bin/env python3
"""Compare existing Python, Rust, and specification IQ3_XXS decoders."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np

from iq3_xxs_dequant import dequantize_blocks_iq3_xxs_numpy
from iq3_xxs_spec_decoder import BLOCK_BYTES, decode_iq3_xxs_spec


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_exclusive(path: Path, data: bytes) -> None:
    with path.open("xb") as output:
        output.write(data)
        output.flush()


def summary(values: np.ndarray) -> dict[str, object]:
    bits = values.view("<u4")
    return {
        "sha256": sha(values.tobytes()),
        "element_count": int(values.size),
        "first_32_values": values[:32].astype(float).tolist(),
        "first_32_bits": [f"{int(value):08x}" for value in bits[:32]],
        "last_32_values": values[-32:].astype(float).tolist(),
        "last_32_bits": [f"{int(value):08x}" for value in bits[-32:]],
        "minimum": float(values.min()),
        "maximum": float(values.max()),
        "non_finite_count": int(np.count_nonzero(~np.isfinite(values))),
        "signed_zero_count": int(np.count_nonzero(bits == np.uint32(0x80000000))),
    }


def counts(values: np.ndarray, *, limit: int | None = None) -> dict[str, int]:
    keys, amounts = np.unique(values, return_counts=True)
    pairs = sorted(zip(keys.tolist(), amounts.tolist()), key=lambda item: (-item[1], item[0]))
    if limit is not None:
        pairs = pairs[:limit]
    return {str(int(key)): int(amount) for key, amount in pairs}


def mismatch_report(packed: bytes, left: np.ndarray, right: np.ndarray, columns: int) -> dict[str, object]:
    left_bits = left.view("<u4")
    right_bits = right.view("<u4")
    indexes = np.flatnonzero(left_bits != right_bits)
    report: dict[str, object] = {
        "mismatch_count": int(indexes.size),
        "mismatch_fraction": float(indexes.size / left.size),
    }
    if indexes.size == 0:
        return report
    first = int(indexes[0])
    block_index = first // 256
    row = first // columns
    column = first % columns
    left_ordered = int(left_bits[first]) ^ (0xFFFFFFFF if int(left_bits[first]) >> 31 else 0x80000000)
    right_ordered = int(right_bits[first]) ^ (0xFFFFFFFF if int(right_bits[first]) >> 31 else 0x80000000)
    report["first"] = {
        "element_index": first,
        "row": row,
        "column": column,
        "compressed_block_index": block_index,
        "packed_byte_offset": block_index * BLOCK_BYTES,
        "left_bits": f"{int(left_bits[first]):08x}",
        "right_bits": f"{int(right_bits[first]):08x}",
        "left_value": float(left[first]),
        "right_value": float(right[first]),
        "absolute_difference": abs(float(left[first]) - float(right[first])),
        "ulp_difference": abs(left_ordered - right_ordered),
    }
    block_indexes = indexes // 256
    within = indexes % 256
    groups = within // 32
    pairs = (within % 32) // 8
    lanes = within % 8
    packed_blocks = np.frombuffer(packed, dtype=np.uint8).reshape(-1, BLOCK_BYTES)
    aux_bytes = np.ascontiguousarray(packed_blocks[:, 66:]).reshape(-1, 8, 4)
    aux = np.ascontiguousarray(aux_bytes).view("<u4").reshape(-1, 8)
    mismatch_aux = aux[block_indexes, groups]
    grid_side = (lanes >= 4).astype(np.int64)
    grid_indexes = packed_blocks[
        block_indexes,
        2 + groups * 8 + pairs * 2 + grid_side,
    ]
    report["distribution"] = {
        "rows_with_mismatch": int(np.unique(indexes // columns).size),
        "blocks_with_mismatch": int(np.unique(block_indexes).size),
        "mismatches_by_in_block_position": counts(within),
        "mismatches_by_scale_f16_bits_top": counts(
            packed_blocks[block_indexes, 0].astype(np.uint16)
            | (packed_blocks[block_indexes, 1].astype(np.uint16) << 8),
            limit=32,
        ),
        "mismatches_by_scale_nibble": counts((mismatch_aux >> np.uint32(28)).astype(np.uint8)),
        "mismatches_by_grid_index": counts(grid_indexes),
        "mismatches_by_sign_index": counts(
            ((mismatch_aux >> (pairs.astype(np.uint32) * np.uint32(7))) & np.uint32(127)).astype(np.uint8)
        ),
    }
    return report


def block_detail(block: bytes, outputs: dict[str, np.ndarray]) -> dict[str, object]:
    groups = []
    for group in range(8):
        aux = int.from_bytes(block[66 + group * 4 : 70 + group * 4], "little")
        groups.append(
            {
                "group": group,
                "aux32": f"{aux:08x}",
                "scale_nibble": aux >> 28,
                "grid_indices": list(block[2 + group * 8 : 10 + group * 8]),
                "sign_indices": [(aux >> (7 * pair)) & 127 for pair in range(4)],
            }
        )
    return {
        "raw_hex": block.hex(),
        "scale_f16_bits": f"{int.from_bytes(block[:2], 'little'):04x}",
        "scale": struct.unpack_from("<e", block, 0)[0],
        "groups": groups,
        "decoded": {
            name: {
                "values": values[:256].astype(float).tolist(),
                "bits": [f"{int(value):08x}" for value in values[:256].view("<u4")],
            }
            for name, values in outputs.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packed", type=Path, required=True)
    parser.add_argument("--rust-decoded", type=Path, required=True)
    parser.add_argument("--private-output-dir", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=6144)
    parser.add_argument("--columns", type=int, default=2048)
    args = parser.parse_args()

    packed = args.packed.read_bytes()
    expected_elements = args.rows * args.columns
    python_values = dequantize_blocks_iq3_xxs_numpy(packed).astype("<f4", copy=False)
    rust_values = np.fromfile(args.rust_decoded, dtype="<f4")
    spec_values = np.asarray(decode_iq3_xxs_spec(packed), dtype="<f4")
    if any(values.size != expected_elements for values in (python_values, rust_values, spec_values)):
        raise ValueError("decoded element count mismatch")

    write_exclusive(args.private_output_dir / "python-decoded-f32le.bin", python_values.tobytes())
    write_exclusive(args.private_output_dir / "spec-decoded-f32le.bin", spec_values.tobytes())
    outputs = {"python": python_values, "rust": rust_values, "spec": spec_values}
    report = {
        "schema": "pulsarmlx.f017.iq3-decoder-identity-audit",
        "schema_version": "1.0.0",
        "packed_sha256": sha(packed),
        "shape": [args.rows, args.columns],
        "decoders": {name: summary(values) for name, values in outputs.items()},
        "python_vs_rust": mismatch_report(packed, python_values, rust_values, args.columns),
        "python_vs_spec": mismatch_report(packed, python_values, spec_values, args.columns),
        "rust_vs_spec": mismatch_report(packed, rust_values, spec_values, args.columns),
        "first_block": block_detail(packed[:BLOCK_BYTES], outputs),
    }
    write_exclusive(
        args.private_output_dir / "iq3-decoder-identity-audit-v1.json",
        (json.dumps(report, indent=2, sort_keys=True) + "\n").encode(),
    )
    print(json.dumps({"packed_sha256": report["packed_sha256"], "decoders": report["decoders"], "comparisons": {key: report[key] for key in ("python_vs_rust", "python_vs_spec", "rust_vs_spec")}}, sort_keys=True))


if __name__ == "__main__":
    main()
