#!/usr/bin/env python3
"""Exactly-once Q4K-REAL-1 payload qualification executor.

The only checkpoint operation is one os.pread over the config-bound range.
All decoder passes consume an immutable private copy created from that read.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib
import json
import math
import os
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from scripts.research.validate_f017_q4_k_authorization import load_package, validate_documents
from scripts.research.validate_f017_q4_k_evidence import validate_evidence_object


ATTEMPT_ID = "Q4K-REAL-1"
READY = "READY_TO_EXECUTE_Q4_K_REAL_BYTE_QUALIFICATION"
BLOCK_BYTES = 144
BLOCK_ELEMENTS = 256
CHUNK_BLOCKS = 4096
EXPECTED = {
    "execution_head": "a84e9179dc0ad4b82a695cdbc07373a4311e4589",
    "execution_config_sha256": "fddffb9359b2cac545afe969d90211f77ca5ef2547057949f75db118522d22da",
    "authorization_binding_sha256": "0a58ca7b1ba3b16c29e7f657b29f48cb9a6ffb4d65377d108a0b20df98dfb865",
    "authorization_amendment_sha256": "62bb1f429fc7c1b0acc2ed7cc88391491758a9e09f62d5745fc991c67e0e502c",
    "checkpoint_set_sha256": "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
    "catalog_sha256": "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0",
    "tensor_map_sha256": "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223",
    "format_contract_sha256": "bbdb296744910dbec5e95496d73df62b1e1b5cae4a9438b41de9962385399305",
    "decoder_sources": [
        ("A_scalar_reference", "1d285e58d5b5c55368191cccb881a56dc78560d7e2541e8d94b5217cd382548d"),
        ("B_spec_transcription", "cfac692461a8772bf7c0d1605b78ab88c43ac593c4431236453e0c8902f51501"),
        ("C_rust_matrix_reference", "c5a3114037a91dee63b5e0c2b7d1d1f2f3b045cb4441c2d5fc6e52b8677ed859"),
    ],
}
TARGET = {
    "tensor_name": "token_embd.weight",
    "shard_ordinal": 2,
    "shard_basename": "GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf",
    "shard_size": 49_105_028_960,
    "offset": 535_316_320,
    "packed_length": 535_265_280,
    "gguf_shape": [6144, 154880],
    "logical_shape": [154880, 6144],
    "quantization": "Q4_K",
    "element_count": 951_582_720,
    "blocks": 3_717_120,
    "catalog_entry_sha256": "5603f0b4638dca0c56a96a58e0e4967cff08bab131dde459529e19f76001b2f0",
}


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path, chunk: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while data := source.read(chunk):
            digest.update(data)
    return digest.hexdigest()


def write_exclusive(path: Path, value: object) -> None:
    raw = canonical_json(value)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _decode_worker(task: tuple[str, int, int, str, str]) -> tuple[bytes, dict[str, Any]]:
    private_path, offset, length, decoder, root = task
    descriptor = os.open(private_path, os.O_RDONLY)
    try:
        packed = os.pread(descriptor, length, offset)
    finally:
        os.close(descriptor)
    if len(packed) != length:
        raise RuntimeError("private packed copy short read")
    sys.path.insert(0, root)
    if decoder == "A":
        implementation = importlib.import_module("scripts.research.ggml_kquants").dequantize_row_q4_k
        values = implementation(packed, len(packed) // BLOCK_BYTES * BLOCK_ELEMENTS)
    elif decoder == "B":
        implementation = importlib.import_module(
            "scripts.research.f017_m1f_minus1_dense_prefix_prep"
        ).decode_q4_k_spec
        values = []
        for block in range(0, len(packed), BLOCK_BYTES):
            values.extend(implementation(packed[block : block + BLOCK_BYTES]))
    else:
        raise RuntimeError("unknown decoder")
    array = np.asarray(values, dtype="<f4")
    bits = array.view("<u4")
    return array.tobytes(order="C"), {
        "element_count": int(array.size),
        "non_finite_count": int(np.count_nonzero(~np.isfinite(array))),
        "signed_zero_count": int(np.count_nonzero(bits == np.uint32(0x80000000))),
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
        "first_f32_bits": f"{int(bits[0]):08x}",
        "last_f32_bits": f"{int(bits[-1]):08x}",
    }


def _tasks(private_path: Path, decoder: str, root: Path) -> Iterable[tuple[str, int, int, str, str]]:
    chunk_bytes = CHUNK_BLOCKS * BLOCK_BYTES
    for offset in range(0, TARGET["packed_length"], chunk_bytes):
        yield (
            str(private_path),
            offset,
            min(chunk_bytes, TARGET["packed_length"] - offset),
            decoder,
            str(root),
        )


def run_python_decoder(private_path: Path, output: Path, decoder: str, root: Path, workers: int) -> dict[str, Any]:
    digest = hashlib.sha256()
    totals = {
        "element_count": 0,
        "non_finite_count": 0,
        "signed_zero_count": 0,
        "minimum": math.inf,
        "maximum": -math.inf,
        "first_f32_bits": None,
        "last_f32_bits": None,
    }
    started = time.monotonic()
    with output.open("xb") as sink, concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        for canonical, stats in pool.map(_decode_worker, _tasks(private_path, decoder, root), chunksize=1):
            sink.write(canonical)
            digest.update(canonical)
            totals["element_count"] += stats["element_count"]
            totals["non_finite_count"] += stats["non_finite_count"]
            totals["signed_zero_count"] += stats["signed_zero_count"]
            totals["minimum"] = min(totals["minimum"], stats["minimum"])
            totals["maximum"] = max(totals["maximum"], stats["maximum"])
            if totals["first_f32_bits"] is None:
                totals["first_f32_bits"] = stats["first_f32_bits"]
            totals["last_f32_bits"] = stats["last_f32_bits"]
        sink.flush()
        os.fsync(sink.fileno())
    output.chmod(0o400)
    return {**totals, "decoded_sha256": digest.hexdigest(), "elapsed_seconds": time.monotonic() - started}


def run_rust_decoder(private_path: Path, output: Path, summary: Path, binary: Path) -> dict[str, Any]:
    started = time.monotonic()
    subprocess.run(
        [str(binary), "--input", str(private_path), "--output", str(output), "--summary", str(summary)],
        check=True,
    )
    output.chmod(0o400)
    summary.chmod(0o400)
    value = json.loads(summary.read_text())
    value["elapsed_seconds"] = time.monotonic() - started
    return value


def first_divergence(paths: list[Path], private_packed: Path) -> dict[str, Any] | None:
    chunk = 4 << 20
    descriptors = [path.open("rb") for path in paths]
    absolute = 0
    try:
        while True:
            values = [source.read(chunk) for source in descriptors]
            if not any(values):
                return None
            if len({len(value) for value in values}) != 1:
                raise RuntimeError("decoded output length divergence")
            if values[0] != values[1] or values[0] != values[2]:
                count = len(values[0]) // 4
                arrays = [np.frombuffer(value, dtype="<u4", count=count) for value in values]
                differing = np.flatnonzero((arrays[0] != arrays[1]) | (arrays[0] != arrays[2]))
                local = int(differing[0])
                element = absolute // 4 + local
                block = element // BLOCK_ELEMENTS
                with private_packed.open("rb") as packed:
                    packed.seek(block * BLOCK_BYTES)
                    raw_block = packed.read(BLOCK_BYTES)
                return {
                    "element_index": element,
                    "row": element // TARGET["logical_shape"][1],
                    "column": element % TARGET["logical_shape"][1],
                    "block_index": block,
                    "packed_block_sha256": sha256_bytes(raw_block),
                    "packed_block_hex": raw_block.hex(),
                    "a_bits": f"{int(arrays[0][local]):08x}",
                    "b_bits": f"{int(arrays[1][local]):08x}",
                    "c_bits": f"{int(arrays[2][local]):08x}",
                    "a_value": struct.unpack("<f", arrays[0][local].tobytes())[0],
                    "b_value": struct.unpack("<f", arrays[1][local].tobytes())[0],
                    "c_value": struct.unpack("<f", arrays[2][local].tobytes())[0],
                }
            absolute += len(values[0])
    finally:
        for descriptor in descriptors:
            descriptor.close()


def validate_banked_evidence(value: dict[str, Any]) -> str:
    return validate_evidence_object(value)


def validate_target(root: Path, shard: Path) -> None:
    config = json.loads((root / "docs/architecture/reviews/evidence/f017-q4-k-execution-config-v2.json").read_text())
    if config["target"] != {
        "tensor_name": TARGET["tensor_name"], "shard_ordinal": 2, "offset": TARGET["offset"],
        "packed_length": TARGET["packed_length"], "gguf_shape": TARGET["gguf_shape"],
        "quantization": "Q4_K", "catalog_entry_sha256": TARGET["catalog_entry_sha256"],
    }:
        raise RuntimeError("execution-config target mismatch")
    inventory = json.loads((root / "docs/architecture/reviews/evidence/f017-m1f-minus1-exact-inventory-v1.json").read_text())
    matches = [item for item in inventory["tensors"] if item["name"] == TARGET["tensor_name"]]
    if len(matches) != 1:
        raise RuntimeError("catalog target multiplicity")
    item = matches[0]
    for field in ("offset", "packed_length", "gguf_shape", "quantization", "catalog_entry_sha256", "shard_ordinal"):
        if item[field] != config["target"][field]:
            raise RuntimeError(f"catalog target mismatch: {field}")
    if TARGET["gguf_shape"][0] * TARGET["gguf_shape"][1] != TARGET["element_count"]:
        raise RuntimeError("element arithmetic")
    if TARGET["element_count"] // BLOCK_ELEMENTS != TARGET["blocks"]:
        raise RuntimeError("block arithmetic")
    if TARGET["blocks"] * BLOCK_BYTES != TARGET["packed_length"]:
        raise RuntimeError("packed arithmetic")
    if shard.name != TARGET["shard_basename"] or shard.stat().st_size != TARGET["shard_size"]:
        raise RuntimeError("shard identity")


def execute(root: Path, shard: Path, private_dir: Path, rust_binary: Path, output: Path, start_output: Path, workers: int) -> dict[str, Any]:
    if validate_documents(load_package(root)) != READY:
        raise RuntimeError("authorization preflight")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if head != EXPECTED["execution_head"]:
        raise RuntimeError("execution head")
    validate_target(root, shard)
    for path, expected in (
        (root / "scripts/research/ggml_kquants.py", EXPECTED["decoder_sources"][0][1]),
        (root / "scripts/research/f017_m1f_minus1_dense_prefix_prep.py", EXPECTED["decoder_sources"][1][1]),
        (root / "crates/f017-runner/src/final_output_qualification.rs", EXPECTED["decoder_sources"][2][1]),
    ):
        if sha256_file(path) != expected:
            raise RuntimeError(f"decoder source identity: {path.name}")
    if output.exists() or start_output.exists():
        raise RuntimeError("attempt output already exists")
    private_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    packed_path = private_dir / "token_embd.weight.q4_k.packed"
    decoder_paths = [private_dir / f"decoder-{name}.lef32" for name in ("a", "b", "c")]
    rust_summary = private_dir / "decoder-c-summary.json"

    shard_fd = os.open(shard, os.O_RDONLY)
    start = {
        "schema": "pulsarmlx.f017.q4-k-real-execution-start",
        "schema_version": "1.0.0",
        "attempt_id": ATTEMPT_ID,
        "execution_head": head,
        "authorized": True,
        "consumed": True,
        "executed": True,
        "checkpoint_accessed": False,
        "execution_start_boundary": "IMMEDIATELY_BEFORE_FIRST_AUTHORIZED_POSITIONAL_READ",
        "automatic_retry": False,
        "automatic_q6_continuation": False,
        "automatic_dense_prefix_continuation": False,
        "ledger_before": 57,
        "target": {key: TARGET[key] for key in ("tensor_name", "shard_ordinal", "offset", "packed_length")},
    }
    write_exclusive(start_output, start)
    try:
        packed = os.pread(shard_fd, TARGET["packed_length"], TARGET["offset"])
    finally:
        os.close(shard_fd)
    if len(packed) != TARGET["packed_length"]:
        raise RuntimeError(f"authorized positional read was short: {len(packed)}")
    packed_sha = sha256_bytes(packed)
    with packed_path.open("xb") as retained:
        retained.write(packed)
        retained.flush()
        os.fsync(retained.fileno())
    del packed
    packed_path.chmod(0o400)

    stats_a = run_python_decoder(packed_path, decoder_paths[0], "A", root, workers)
    stats_b = run_python_decoder(packed_path, decoder_paths[1], "B", root, workers)
    stats_c = run_rust_decoder(packed_path, decoder_paths[2], rust_summary, rust_binary)
    divergence = first_divergence(decoder_paths, packed_path)
    exact = len({stats_a["decoded_sha256"], stats_b["decoded_sha256"], stats_c["decoded_sha256"]}) == 1
    if exact != (divergence is None):
        raise RuntimeError("hash/detail comparison inconsistency")

    decoder_records = []
    for (name, source), stats, path in zip(EXPECTED["decoder_sources"], (stats_a, stats_b, stats_c), decoder_paths, strict=True):
        if sha256_file(path) != stats["decoded_sha256"]:
            raise RuntimeError(f"decoded output rehash mismatch: {name}")
        decoder_records.append({
            "name": name,
            "source_sha256": source,
            "decoded_sha256": stats["decoded_sha256"],
            "element_count": stats["element_count"],
            "logical_shape": TARGET["logical_shape"],
            "dtype": "f32",
            "serialization": "canonical_little_endian_ieee754_binary32",
            "non_finite_count": stats["non_finite_count"],
            "signed_zero_count": stats["signed_zero_count"],
            "minimum": stats["minimum"],
            "maximum": stats["maximum"],
            "first_f32_bits": stats["first_f32_bits"],
            "last_f32_bits": stats["last_f32_bits"],
            "elapsed_seconds": stats["elapsed_seconds"],
        })

    terminal = "EXACT_REAL_BYTE_QUALIFIED" if exact else "DECODER_TRUTH_UNRESOLVED"
    evidence = {
        "schema": "pulsarmlx.f017.q4-k-real-byte-qualification-evidence",
        "schema_version": "1.0.0",
        "attempt": {
            "attempt_id": ATTEMPT_ID, "authorized": True, "consumed": True, "executed": True,
            "checkpoint_accessed": True, "execution_start_recorded": True, "terminal_class": terminal,
            "automatic_retry": False, "automatic_q6_continuation": False,
            "automatic_dense_prefix_continuation": False,
        },
        "identity": {
            "execution_head": head,
            "execution_tooling": {
                "executor_source_sha256": sha256_file(root / "scripts/research/execute_f017_q4_k_real.py"),
                "validator_source_sha256": sha256_file(root / "scripts/research/validate_f017_q4_k_evidence.py"),
                "rust_wrapper_source_sha256": sha256_file(root / "crates/f017-runner/src/bin/f017-q4-k-decode-hash.rs"),
                "rust_wrapper_binary_sha256": sha256_file(rust_binary),
                "python_version": sys.version.split()[0],
                "numpy_version": np.__version__,
            },
            "execution_config_sha256": EXPECTED["execution_config_sha256"],
            "authorization_binding_sha256": EXPECTED["authorization_binding_sha256"],
            "authorization_amendment_sha256": EXPECTED["authorization_amendment_sha256"],
            "checkpoint_set_sha256": EXPECTED["checkpoint_set_sha256"],
            "catalog_sha256": EXPECTED["catalog_sha256"],
            "tensor_map_sha256": EXPECTED["tensor_map_sha256"],
            "tensor_name": TARGET["tensor_name"], "shard_ordinal": 2, "offset": TARGET["offset"],
            "packed_length": TARGET["packed_length"], "packed_sha256": packed_sha,
            "gguf_shape": TARGET["gguf_shape"], "quantization": "Q4_K",
            "format_contract_sha256": EXPECTED["format_contract_sha256"],
            "private_artifacts": {
                "packed": {"sha256": packed_sha, "bytes": TARGET["packed_length"], "read_only": True},
                "decoded": [
                    {"decoder": record["name"], "sha256": record["decoded_sha256"], "bytes": TARGET["element_count"] * 4, "read_only": True}
                    for record in decoder_records
                ],
                "machine_local_paths_published": False,
            },
        },
        "access": {"shard_opens": 1, "positional_reads": 1, "tensor_payloads": 1, "packed_bytes": TARGET["packed_length"]},
        "decoder_outputs": decoder_records,
        "comparison": {"bitwise_equal": exact, "first_divergence": divergence, "signed_zero_policy": "PRESERVE_AND_COUNT_EXACT_F32_BITS"},
        "isolation": {"model_compute": 0, "mlx_candidate_dispatches": 0, "additional_payloads": 0, "q6_k_executed": False, "dense_prefix_executed": False, "fallback": False},
        "ledger": {"before": 57, "actual_payloads": 1, "after": 58},
        "verdict": terminal,
    }
    validate_banked_evidence(evidence)
    write_exclusive(output, evidence)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--shard", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--rust-decoder", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 20:
        parser.error("workers must be between 1 and 20")
    evidence = execute(
        args.repository_root.resolve(strict=True), args.shard.resolve(strict=True), args.private_dir,
        args.rust_decoder.resolve(strict=True), args.output, args.start_output, args.workers,
    )
    print(json.dumps({"verdict": evidence["verdict"], "packed_sha256": evidence["identity"]["packed_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
