#!/usr/bin/env python3
"""Bounded real-byte Q5_K decoder cross-qualification for F017 M1-F0.

This tool admits exactly one catalog-bound tensor range.  It performs no
attention, router, expert, MLX, or candidate computation.  Decoder A is the
existing M1-F0 scalar oracle decoder.  Decoder B is an independent NumPy
transcription of the pinned upstream gguf-py Q5_K layout.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import struct
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "pulsarmlx.f017.m1f0-q5-k-real-byte-qualification"
SCHEMA_VERSION = "1.0.0"
QK_K = 256
BLOCK_BYTES = 176
TENSOR = {
    "symbolic_name": "blk.3.attn_output.weight",
    "role": "attention_output",
    "shard_ordinal": 2,
    "shard_basename": "GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf",
    "shard_sha256": "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36",
    "offset": 2_008_658_784,
    "packed_length": 69_206_016,
    "quantization": "Q5_K",
    "gguf_shape": [16_384, 6_144],
    "logical_shape": [6_144, 16_384],
    "element_count": 100_663_296,
    "packed_row_width": 11_264,
    "catalog_entry_sha256": "eb3f2e1d6f3f5238a84a9778aef2e07bf6a4d77e9a3aa9f2e9aad6df37e89ad7",
}
UPSTREAM = {
    "repository": "https://github.com/ggml-org/llama.cpp",
    "commit": "a94d563ed801d1da1b8c2432946de07d0231bb3d",
    "path": "gguf-py/gguf/quants.py",
    "symbol": "Q5_K.dequantize_blocks",
}


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_decoder_a(repository_root: Path):
    path = repository_root / "scripts/research/prepare_f017_m1f0_real_reference.py"
    spec = importlib.util.spec_from_file_location("m1f0_q5_decoder_a", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.decode_q5_k_spec, path


def _upstream_scale_min(scales: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Decode the 8 six-bit scales/mins via the upstream 3x4 representation."""
    blocks = scales.shape[0]
    fields = scales.reshape((blocks, 3, 4))
    low_scales, low_mins, high = np.split(fields, 3, axis=1)
    decoded_scales = np.concatenate(
        [low_scales & np.uint8(0x3F), (high & np.uint8(0x0F)) | ((low_scales >> np.uint8(2)) & np.uint8(0x30))],
        axis=-1,
    )
    decoded_mins = np.concatenate(
        [low_mins & np.uint8(0x3F), (high >> np.uint8(4)) | ((low_mins >> np.uint8(2)) & np.uint8(0x30))],
        axis=-1,
    )
    return decoded_scales.reshape((blocks, 8)), decoded_mins.reshape((blocks, 8))


def decode_q5_k_upstream_spec(raw: bytes) -> np.ndarray:
    """Independent vector transcription of pinned upstream gguf-py Q5_K."""
    if len(raw) == 0 or len(raw) % BLOCK_BYTES:
        raise ValueError("Q5_K packed length")
    blocks = np.frombuffer(raw, dtype=np.uint8).reshape((-1, BLOCK_BYTES))
    block_count = blocks.shape[0]
    d = blocks[:, 0:2].copy().reshape(-1).view("<f2").astype(np.float32)
    dmin = blocks[:, 2:4].copy().reshape(-1).view("<f2").astype(np.float32)
    scales, mins = _upstream_scale_min(blocks[:, 4:16])
    ds = np.multiply(d[:, None], scales.astype(np.float32), dtype=np.float32).reshape((block_count, 8, 1))
    dm = np.multiply(dmin[:, None], mins.astype(np.float32), dtype=np.float32).reshape((block_count, 8, 1))

    high = blocks[:, 16:48].reshape((block_count, 1, 32))
    high = high >> np.arange(8, dtype=np.uint8).reshape((1, 8, 1))
    high = high & np.uint8(1)
    low = blocks[:, 48:176].reshape((block_count, 4, 1, 32))
    low = low >> np.asarray([0, 4], dtype=np.uint8).reshape((1, 1, 2, 1))
    low = (low & np.uint8(0x0F)).reshape((block_count, 8, 32))
    quant = (low | (high << np.uint8(4))).astype(np.float32)
    return np.subtract(np.multiply(ds, quant, dtype=np.float32), dm, dtype=np.float32).reshape(-1)


def _stats(values: np.ndarray, current: dict[str, Any]) -> None:
    current["min"] = min(current["min"], float(np.min(values)))
    current["max"] = max(current["max"], float(np.max(values)))
    current["non_finite_count"] += int(np.count_nonzero(~np.isfinite(values)))
    bits = np.asarray(values, dtype="<f4").view("<u4")
    current["signed_zero_count"] += int(np.count_nonzero(bits == np.uint32(0x80000000)))


def compare_decoders(raw: bytes, repository_root: Path, chunk_blocks: int = 1024) -> dict[str, Any]:
    decoder_a, decoder_a_path = load_decoder_a(repository_root)
    if chunk_blocks < 1:
        raise ValueError("chunk_blocks")
    chunk_bytes = chunk_blocks * BLOCK_BYTES
    hashes = {"decoder_a": hashlib.sha256(), "decoder_b": hashlib.sha256()}
    stats = {
        name: {"min": math.inf, "max": -math.inf, "non_finite_count": 0, "signed_zero_count": 0}
        for name in hashes
    }
    first_divergence = None
    compared = 0
    started = time.monotonic()
    for packed_offset in range(0, len(raw), chunk_bytes):
        chunk = raw[packed_offset : packed_offset + chunk_bytes]
        decoded_a = np.asarray(decoder_a(chunk), dtype="<f4")
        decoded_b = np.asarray(decode_q5_k_upstream_spec(chunk), dtype="<f4")
        bytes_a = decoded_a.tobytes(order="C")
        bytes_b = decoded_b.tobytes(order="C")
        hashes["decoder_a"].update(bytes_a)
        hashes["decoder_b"].update(bytes_b)
        _stats(decoded_a, stats["decoder_a"])
        _stats(decoded_b, stats["decoder_b"])
        if first_divergence is None and bytes_a != bytes_b:
            bits_a = decoded_a.view("<u4")
            bits_b = decoded_b.view("<u4")
            local = int(np.flatnonzero(bits_a != bits_b)[0])
            absolute = compared + local
            block = absolute // QK_K
            raw_block = raw[block * BLOCK_BYTES : (block + 1) * BLOCK_BYTES]
            first_divergence = {
                "element_index": absolute,
                "row": absolute // TENSOR["logical_shape"][1],
                "column": absolute % TENSOR["logical_shape"][1],
                "compressed_block_index": block,
                "packed_byte_offset": block * BLOCK_BYTES,
                "decoder_a_bits": f"{int(bits_a[local]):08x}",
                "decoder_b_bits": f"{int(bits_b[local]):08x}",
                "decoder_a_value": float(decoded_a[local]),
                "decoder_b_value": float(decoded_b[local]),
                "raw_block_hex": raw_block.hex(),
            }
        compared += decoded_a.size
    return {
        "decoder_a": {
            "role": "existing_m1f0_scalar_oracle",
            "path": str(decoder_a_path.relative_to(repository_root)),
            "source_sha256": sha256(decoder_a_path.read_bytes()),
            "decoded_sha256": hashes["decoder_a"].hexdigest(),
            **stats["decoder_a"],
        },
        "decoder_b": {
            "role": "independent_pinned_upstream_vector_transcription",
            "path": "scripts/research/qualify_f017_m1f0_q5_k_real.py",
            "decoded_sha256": hashes["decoder_b"].hexdigest(),
            **stats["decoder_b"],
        },
        "element_count": compared,
        "exact_bitwise_equal": first_divergence is None and hashes["decoder_a"].digest() == hashes["decoder_b"].digest(),
        "first_divergence": first_divergence,
        "elapsed_seconds": time.monotonic() - started,
    }


def qualify(repository_root: Path, shard_path: Path) -> dict[str, Any]:
    if shard_path.name != TENSOR["shard_basename"]:
        raise ValueError("Q5_K qualification shard basename")
    if shard_path.stat().st_size != 49_105_028_960:
        raise ValueError("Q5_K qualification shard size")
    with shard_path.open("rb", buffering=0) as shard:
        shard.seek(TENSOR["offset"])
        raw = shard.read(TENSOR["packed_length"])
    if len(raw) != TENSOR["packed_length"]:
        raise ValueError("Q5_K qualification short read")
    packed_sha = sha256(raw)
    # The packed identity is finalized before either decoder is invoked.
    comparison = compare_decoders(raw, repository_root)
    if comparison["element_count"] != TENSOR["element_count"] or not comparison["exact_bitwise_equal"]:
        raise ValueError("Q5_K decoder identity mismatch")
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "decoder_qualification_only": True,
            "tensor_payloads": 1,
            "shard_opens": 1,
            "positional_reads": 1,
            "attention_computation": 0,
            "router_computation": 0,
            "expert_computation": 0,
            "mlx_candidate_computation": 0,
            "m1f0_route_discovery": False,
        },
        "checkpoint_bindings": {
            "checkpoint_set_sha256": "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
            "catalog_sha256": "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0",
            "tensor_map_sha256": "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223",
        },
        "tensor": {**TENSOR, "packed_sha256": packed_sha},
        "canonical_decoded_representation": "row_major_logical_little_endian_f32_no_padding_no_transpose",
        "authoritative_reference": UPSTREAM,
        "comparison": comparison,
        "status": "exact_real_byte_identity_passed",
        "private_paths_persisted": False,
        "packed_or_decoded_bytes_persisted": False,
    }


def synthetic_blocks() -> list[bytes]:
    fixtures = []
    for salt, scale in [(19, "0030002c"), (71, "003c0038"), (131, "00340030")]:
        block = bytearray(((index * 73 + salt) & 255) for index in range(BLOCK_BYTES))
        block[:4] = bytes.fromhex(scale)
        fixtures.append(bytes(block))
    return fixtures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--shard", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--synthetic-only", action="store_true")
    args = parser.parse_args()
    root = args.repository_root.resolve(strict=True)
    if args.synthetic_only:
        decoder_a, _ = load_decoder_a(root)
        records = []
        for ordinal, block in enumerate(synthetic_blocks()):
            a = np.asarray(decoder_a(block), dtype="<f4").tobytes()
            b = np.asarray(decode_q5_k_upstream_spec(block), dtype="<f4").tobytes()
            if a != b:
                raise ValueError(f"Q5_K synthetic identity mismatch at fixture {ordinal}")
            records.append({"ordinal": ordinal, "packed_sha256": sha256(block), "decoded_sha256": sha256(a)})
        result = {"schema": "pulsarmlx.f017.m1f0-q5-k-synthetic-exactness", "records": records, "status": "passed"}
    else:
        if args.shard is None:
            parser.error("real qualification requires --shard")
        result = qualify(root, args.shard.resolve(strict=True))
    raw = canonical_json(result)
    if args.output:
        args.output.write_bytes(raw)
    print(sha256(raw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
