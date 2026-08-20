#!/usr/bin/env python3
"""Deterministic proof/reference-derived S2 arithmetic and open-once inputs.

The production interface is imported by the separately gated single-use
release wrapper.  This CLI exposes synthetic rehearsal only and rejects either
real retained operand identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import stat
import struct
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ARITHMETIC = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-arithmetic-v1.json"
ARITHMETIC_SHA = "abbf158320d1fdfade5b8553e9ea1871c34830f541e4186074262fc702776e86"
S1_SHA = "8309377ee8e8f34eb91cdb025624144eb5be7821ed9e4a295df29b13aac5a0dd"
FFN_SHA = "4d7aaeb58c4ee33dcaf2329c8cd46234d69ee7f16bb7e6338ac9e0b7a5e6ad1a"
S1_BYTES = 24576
FFN_BYTES = 49152
S2_BYTES = 24576


class S2Error(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise S2Error(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256(path.read_bytes())


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"DUPLICATE_KEY:{key}")
        result[key] = value
    return result


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    require(isinstance(value, dict), "JSON_OBJECT_REQUIRED")
    return value


def require_environment() -> None:
    require(sys.version_info[:3] == (3, 14, 6), "CPYTHON_3_14_6_REQUIRED")
    require(platform.system() == "Darwin" and platform.machine() == "arm64", "DARWIN_ARM64_REQUIRED")
    require(sys.byteorder == "little", "LITTLE_ENDIAN_REQUIRED")
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        require(os.environ.get(name) == "1", f"THREAD_PIN:{name}")


def validate_arithmetic() -> None:
    require(sha256_path(ARITHMETIC) == ARITHMETIC_SHA, "ARITHMETIC_IDENTITY")
    doc = load(ARITHMETIC)
    require(doc.get("formula") == "S2_f32[k]=binary32(binary64(S1_f32[k])+FFN_f64[k])", "FORMULA")
    require(doc.get("semantic_classification") == "CANONICAL_F017_PROOF_REFERENCE_DERIVED_S2_SURFACE_INTENTIONALLY_NOT_CLAIMED_EQUIVALENT_TO_PRODUCTION_SERIAL_F32", "SURFACE")
    addition = doc.get("addition", {})
    require(addition.get("left_operand") == "exactly-promoted-S1-binary64", "OPERAND_ORDER")
    require(addition.get("right_operand") == "FFN-binary64", "OPERAND_ORDER")
    require(addition.get("dtype") == "IEEE-754 binary64" and addition.get("operations_per_coordinate") == 1, "ADDITION")
    require(addition.get("rounding_mode") == "round-to-nearest-ties-to-even", "ADDITION_ROUNDING")
    require(all(addition.get(key) is False for key in ("fma", "reduction", "blas", "gpu", "parallel_arithmetic")), "ALTERNATE_ARITHMETIC")
    final = doc.get("final_cast", {})
    require(final.get("operation") == "IEEE-754 binary64-to-binary32 conversion", "FINAL_CAST")
    require(final.get("rounding_mode") == "round-to-nearest-ties-to-even" and final.get("roundings_per_coordinate") == 1, "FINAL_ROUNDING")
    require(final.get("saturation") is False and final.get("flush_to_zero") is False, "FINAL_CAST_MODE")


def read_exact(descriptor: int, size: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    parts: list[bytes] = []
    remaining = size
    while remaining:
        chunk = os.read(descriptor, min(remaining, 1024 * 1024))
        require(bool(chunk), "SHORT_READ")
        parts.append(chunk)
        remaining -= len(chunk)
    require(os.read(descriptor, 1) == b"", "LONG_READ")
    return b"".join(parts)


def open_directory(path: Path) -> tuple[int, os.stat_result]:
    before = path.lstat()
    require(stat.S_ISDIR(before.st_mode) and not stat.S_ISLNK(before.st_mode), "DIRECTORY_IDENTITY")
    require(before.st_uid == os.getuid(), "DIRECTORY_OWNER")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    observed = os.fstat(descriptor)
    require((before.st_dev, before.st_ino) == (observed.st_dev, observed.st_ino), "DIRECTORY_SUBSTITUTION")
    return descriptor, observed


def open_leaf(root_fd: int, name: str, size: int) -> tuple[int, os.stat_result, bytes]:
    require(Path(name).name == name, "PURE_BASENAME_REQUIRED")
    descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
    metadata = os.fstat(descriptor)
    require(stat.S_ISREG(metadata.st_mode), "REGULAR_FILE_REQUIRED")
    require(metadata.st_uid == os.getuid(), "OWNER_REQUIRED")
    require(metadata.st_nlink == 1, "SINGLE_LINK_REQUIRED")
    require(metadata.st_mode & 0o222 == 0, "READ_ONLY_REQUIRED")
    require(metadata.st_size == size, "BYTE_LENGTH")
    return descriptor, metadata, read_exact(descriptor, size)


class OpenOperand:
    """One immutable descriptor is validated, consumed, and verified after."""

    def __init__(self, root: Path, specification: dict[str, Any]) -> None:
        self.root_fd, _ = open_directory(root)
        manifest = specification["manifest"]
        manifest_fd, _, manifest_raw = open_leaf(self.root_fd, manifest["relative_path"], manifest["byte_length"])
        try:
            require(sha256(manifest_raw) == manifest["sha256"], "MANIFEST_SHA")
            manifest_doc = json.loads(manifest_raw)
            entries = manifest_doc.get("artifacts")
            require(isinstance(entries, list) and len(entries) == 1, "MANIFEST_CENSUS")
            entry = entries[0]
            artifact = specification["artifact"]
            expected = {
                "symbolic_path": artifact["relative_path"],
                "sha256": artifact["sha256"],
                "semantic_role": artifact["semantic_role"],
                "dtype": artifact["dtype"],
                "shape": artifact["shape"],
                "byte_length": artifact["byte_length"],
            }
            require(all(entry.get(key) == value for key, value in expected.items()), "MANIFEST_BINDING")
        finally:
            os.close(manifest_fd)
        artifact = specification["artifact"]
        self.descriptor, self.before_metadata, self.raw = open_leaf(self.root_fd, artifact["relative_path"], artifact["byte_length"])
        self.expected_sha = artifact["sha256"]
        self.before_sha = sha256(self.raw)
        require(self.expected_sha == self.before_sha, "EXPECTED_BEFORE")
        fmt = "<6144f" if artifact["dtype"] == "little-endian-f32" else "<6144d"
        require(all(math.isfinite(value) for value in struct.unpack(fmt, self.raw)), "INPUT_NONFINITE")

    def verify_after(self) -> dict[str, str]:
        consumed = sha256(self.raw)
        after_raw = read_exact(self.descriptor, len(self.raw))
        after_metadata = os.fstat(self.descriptor)
        after = sha256(after_raw)
        require((self.before_metadata.st_dev, self.before_metadata.st_ino, self.before_metadata.st_size) == (after_metadata.st_dev, after_metadata.st_ino, after_metadata.st_size), "INPUT_OBJECT_CHANGED")
        require(self.expected_sha == self.before_sha == consumed == after, "EXPECTED_BEFORE_CONSUMED_AFTER")
        return {"expected_sha256": self.expected_sha, "before_sha256": self.before_sha, "consumed_sha256": consumed, "after_sha256": after}

    def close(self) -> None:
        os.close(self.descriptor)
        os.close(self.root_fd)


def compose_bytes(s1_raw: bytes, ffn_raw: bytes) -> bytes:
    """Apply the frozen scalar proof/reference-derived S2 algorithm."""
    require(len(s1_raw) == S1_BYTES and len(ffn_raw) == FFN_BYTES, "INPUT_GEOMETRY")
    s1_values = struct.iter_unpack("<f", s1_raw)
    ffn_values = struct.iter_unpack("<d", ffn_raw)
    output = bytearray(S2_BYTES)
    for coordinate, (s1_item, ffn_item) in enumerate(zip(s1_values, ffn_values, strict=True)):
        s1_value = s1_item[0]
        ffn_value = ffn_item[0]
        require(math.isfinite(s1_value) and math.isfinite(ffn_value), "INPUT_NONFINITE")
        promoted_s1 = float(s1_value)
        temporary = promoted_s1 + ffn_value
        require(math.isfinite(temporary), "INTERMEDIATE_NONFINITE")
        try:
            struct.pack_into("<f", output, coordinate * 4, temporary)
        except (OverflowError, struct.error) as error:
            raise S2Error("FINAL_CAST_INVALID") from error
        require(math.isfinite(struct.unpack_from("<f", output, coordinate * 4)[0]), "OUTPUT_NONFINITE")
    return bytes(output)


def compose_from_open_operands(s1: OpenOperand, ffn: OpenOperand) -> tuple[bytes, dict[str, dict[str, str]]]:
    output = compose_bytes(s1.raw, ffn.raw)
    return output, {"s1": s1.verify_after(), "ffn": ffn.verify_after()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic-s1", type=Path, required=True)
    parser.add_argument("--synthetic-ffn", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    require_environment()
    validate_arithmetic()
    s1_raw = arguments.synthetic_s1.read_bytes()
    ffn_raw = arguments.synthetic_ffn.read_bytes()
    require(sha256(s1_raw) != S1_SHA and sha256(ffn_raw) != FFN_SHA, "REAL_OPERAND_IN_SYNTHETIC_MODE")
    output = compose_bytes(s1_raw, ffn_raw)
    require(not arguments.output.exists(), "OUTPUT_PREEXISTS")
    arguments.output.write_bytes(output)
    print(json.dumps({"result": "SYNTHETIC_COMPLETE", "output_sha256": sha256(output), "output_bytes": len(output), "s2_constructions": 0, "checkpoint_reads": 0, "shard_opens": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except S2Error as error:
        print(json.dumps({"result": "FAIL_CLOSED", "error": str(error), "s2_constructions": 0, "checkpoint_reads": 0, "shard_opens": 0}, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)
