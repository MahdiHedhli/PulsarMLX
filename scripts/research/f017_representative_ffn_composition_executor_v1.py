#!/usr/bin/env python3
"""Checkpoint-free proof/reference FFN composition executor.

The committed CLI exposes real-input preflight and synthetic rehearsal only.
A future independently approved single-use wrapper must import
``compose_from_open_inputs`` after its durable attempt-start gate.
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
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUTHORIZATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-ffn-composition-authorization-v1.json"
ARITHMETIC = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-ffn-composition-arithmetic-v1.json"
ARITHMETIC_SHA256 = "1054d014c23628fa56771518f066d14cfd445b0d7b4ba7da98b638c37981cdbb"
ROUTED_REUSE_SHA256 = "f04a1eb901f4c738f421b34cc065e2ca20b8938ae00e49ee17e67aeffd99fdfb"
SHARED_REUSE_SHA256 = "3642200f50f2ed7140243cd885dfe8c3d8628f5605ab37467cc342ea6376019a"
REAL_ROUTED_SHA256 = "872487d337305aab82e80a87b84763b6e3dd2901f88ae2ed6b64277aba9a20f9"
REAL_SHARED_SHA256 = "8285fecf6e3232f19a0cc11b5d98ee5003f036db6bcd3cd52a7e9dbde9bb1b5b"


class CompositionError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CompositionError(message)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in output, f"DUPLICATE_KEY:{key}")
            output[key] = value
        return output
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)
    require(isinstance(value, dict), "JSON_OBJECT_REQUIRED")
    return value


def require_environment() -> None:
    require(sys.version_info[:3] == (3, 14, 6), "CPYTHON_3_14_6_REQUIRED")
    require(platform.system() == "Darwin" and platform.machine() == "arm64", "DARWIN_ARM64_REQUIRED")
    require(sys.byteorder == "little", "LITTLE_ENDIAN_REQUIRED")
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        require(os.environ.get(name) == "1", f"THREAD_PIN:{name}")


def read_exact(fd: int, size: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = os.read(fd, min(remaining, 1024 * 1024))
        require(bool(chunk), "SHORT_READ")
        chunks.append(chunk)
        remaining -= len(chunk)
    require(os.read(fd, 1) == b"", "LONG_READ")
    return b"".join(chunks)


def open_leaf(directory_fd: int, name: str, size: int) -> tuple[int, os.stat_result, bytes]:
    require(isinstance(name, str) and Path(name).name == name, "PURE_BASENAME_REQUIRED")
    descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
    metadata = os.fstat(descriptor)
    require(stat.S_ISREG(metadata.st_mode), "REGULAR_FILE_REQUIRED")
    require(metadata.st_uid == os.getuid(), "OWNER_REQUIRED")
    require(metadata.st_nlink == 1, "SINGLE_LINK_REQUIRED")
    require(metadata.st_mode & 0o222 == 0, "READ_ONLY_REQUIRED")
    require(metadata.st_size == size, "BYTE_LENGTH")
    return descriptor, metadata, read_exact(descriptor, size)


class OpenInput:
    def __init__(self, root: Path, specification: dict[str, Any]) -> None:
        self.root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        root_metadata = os.fstat(self.root_fd)
        require(stat.S_ISDIR(root_metadata.st_mode), "INPUT_ROOT_DIRECTORY")
        require(root_metadata.st_uid == os.getuid(), "INPUT_ROOT_OWNER")
        manifest = specification["manifest"]
        manifest_fd, _, manifest_raw = open_leaf(self.root_fd, manifest["relative_path"], manifest["byte_length"])
        try:
            require(sha256_bytes(manifest_raw) == manifest["sha256"], "MANIFEST_IDENTITY")
            manifest_document = json.loads(manifest_raw)
            entries = manifest_document.get("artifacts")
            require(isinstance(entries, list) and len(entries) == 1, "MANIFEST_CENSUS")
            entry = entries[0]
            artifact = specification["artifact"]
            for key in ("symbolic_path", "sha256", "semantic_role", "dtype", "shape", "byte_length"):
                manifest_key = "symbolic_path" if key == "symbolic_path" else key
                artifact_key = "relative_path" if key == "symbolic_path" else key
                require(entry.get(manifest_key) == artifact.get(artifact_key), f"MANIFEST_BINDING:{key}")
        finally:
            os.close(manifest_fd)
        artifact = specification["artifact"]
        self.descriptor, self.before_metadata, self.raw = open_leaf(self.root_fd, artifact["relative_path"], artifact["byte_length"])
        self.expected_sha256 = artifact["sha256"]
        self.before_sha256 = sha256_bytes(self.raw)
        require(self.before_sha256 == self.expected_sha256, "INPUT_BEFORE_IDENTITY")

    def verify_after(self) -> dict[str, str]:
        consumed_sha256 = sha256_bytes(self.raw)
        after_raw = read_exact(self.descriptor, len(self.raw))
        after_metadata = os.fstat(self.descriptor)
        after_sha256 = sha256_bytes(after_raw)
        require((self.before_metadata.st_dev, self.before_metadata.st_ino) == (after_metadata.st_dev, after_metadata.st_ino), "INPUT_OBJECT_CHANGED")
        require(self.expected_sha256 == self.before_sha256 == consumed_sha256 == after_sha256, "EXPECTED_BEFORE_CONSUMED_AFTER")
        return {
            "expected_sha256": self.expected_sha256,
            "before_sha256": self.before_sha256,
            "consumed_sha256": consumed_sha256,
            "after_sha256": after_sha256,
        }

    def close(self) -> None:
        os.close(self.descriptor)
        os.close(self.root_fd)


def validate_arithmetic() -> dict[str, Any]:
    require(sha256_path(ARITHMETIC) == ARITHMETIC_SHA256, "ARITHMETIC_IDENTITY")
    arithmetic = load_json(ARITHMETIC)
    require(arithmetic.get("semantic_classification") == "CANONICAL_F017_PROOF_REFERENCE_FFN_SURFACE_INTENTIONALLY_DISTINCT_FROM_PRODUCTION_SERIAL_F32", "ARITHMETIC_SURFACE")
    algorithm = arithmetic.get("algorithm", {})
    require(algorithm.get("formula") == "FFN[k]=Routed[k]+binary64(Shared[k])", "ARITHMETIC_FORMULA")
    require(algorithm.get("shared_scalar_multiplier") == "NONE; exact multiplier is binary64 1.0", "SHARED_MULTIPLIER")
    require(algorithm.get("addition_dtype") == "IEEE-754 binary64", "ADDITION_DTYPE")
    require(algorithm.get("addition_order") == "Routed first, then exactly promoted Shared", "ADDITION_ORDER")
    require(algorithm.get("blas") is False and algorithm.get("gpu") is False and algorithm.get("parallelism") == "none", "ARITHMETIC_FALLBACK")
    return arithmetic


def validate_authorization(document: dict[str, Any]) -> None:
    require(document.get("schema") == "pulsarmlx.f017.representative-ffn-composition-authorization", "AUTHORIZATION_SCHEMA")
    require(document.get("schema_version") == "1.0.0", "AUTHORIZATION_VERSION")
    require(document.get("status") == "PREPARED_REVIEW_REQUIRED" and document.get("real_event_authorized") is False, "AUTHORIZATION_STATE")
    bindings = document.get("bindings", {})
    require(bindings.get("routed_reuse_authorization", {}).get("sha256") == ROUTED_REUSE_SHA256, "ROUTED_REUSE_BINDING")
    require(bindings.get("shared_reuse_authorization", {}).get("sha256") == SHARED_REUSE_SHA256, "SHARED_REUSE_BINDING")
    require(bindings.get("arithmetic_contract", {}).get("sha256") == ARITHMETIC_SHA256, "ARITHMETIC_BINDING")
    inputs = document.get("inputs", {})
    require(inputs.get("routed", {}).get("artifact", {}).get("sha256") == REAL_ROUTED_SHA256, "ROUTED_INPUT")
    require(inputs.get("shared", {}).get("artifact", {}).get("sha256") == REAL_SHARED_SHA256, "SHARED_INPUT")
    require(document.get("future_output") == {
        "semantic_role": "REPRESENTATIVE_M1F0_FFN_PROOF_REFERENCE_OUTPUT",
        "dtype": "little-endian-f64",
        "shape": [6144],
        "byte_length": 49152,
        "serialization": "contiguous-c-order-ieee754-binary64-little-endian",
        "finite": True,
        "concrete_sha256": "NOT_COMPUTED_UNTIL_SEPARATELY_RELEASED_EVENT",
    }, "OUTPUT_CONTRACT")


def compose_bytes(routed_raw: bytes, shared_raw: bytes) -> bytes:
    require(len(routed_raw) == 49152 and len(shared_raw) == 24576, "INPUT_GEOMETRY")
    routed = struct.unpack("<6144d", routed_raw)
    shared = struct.unpack("<6144f", shared_raw)
    require(all(math.isfinite(value) for value in routed), "ROUTED_NONFINITE")
    require(all(math.isfinite(value) for value in shared), "SHARED_NONFINITE")
    output = bytearray(49152)
    for coordinate, (routed_value, shared_value) in enumerate(zip(routed, shared, strict=True)):
        result = routed_value + float(shared_value)
        require(math.isfinite(result), "FFN_NONFINITE")
        struct.pack_into("<d", output, coordinate * 8, result)
    return bytes(output)


def compose_from_open_inputs(routed: OpenInput, shared: OpenInput) -> tuple[bytes, dict[str, dict[str, str]]]:
    """Future single-use wrappers call this only after durable attempt-start."""
    output = compose_bytes(routed.raw, shared.raw)
    after = {"routed": routed.verify_after(), "shared": shared.verify_after()}
    return output, after


def write_no_replace(path: Path, raw: bytes) -> None:
    require(not path.exists(), "OUTPUT_PREEXISTS")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o400)
        os.link(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        os.unlink(temporary)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def open_pair(document: dict[str, Any], routed_root: Path, shared_root: Path) -> tuple[OpenInput, OpenInput]:
    inputs = document["inputs"]
    routed = OpenInput(routed_root, inputs["routed"])
    try:
        shared = OpenInput(shared_root, inputs["shared"])
    except Exception:
        routed.close()
        raise
    return routed, shared


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight-only", action="store_true")
    modes.add_argument("--synthetic-rehearsal", action="store_true")
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--synthetic-config", type=Path)
    parser.add_argument("--routed-root", type=Path, required=True)
    parser.add_argument("--shared-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    require_environment()
    validate_arithmetic()

    if arguments.preflight_only:
        require(arguments.authorization is not None and arguments.synthetic_config is None and arguments.output is None, "PREFLIGHT_INTERFACE")
        document = load_json(arguments.authorization)
        validate_authorization(document)
    else:
        require(arguments.synthetic_config is not None and arguments.authorization is None and arguments.output is not None, "SYNTHETIC_INTERFACE")
        document = load_json(arguments.synthetic_config)
        require(document.get("schema") == "pulsarmlx.f017.representative-ffn-composition-synthetic-input", "SYNTHETIC_SCHEMA")
        protected = {document["inputs"][name]["artifact"]["sha256"] for name in ("routed", "shared")}
        require(REAL_ROUTED_SHA256 not in protected and REAL_SHARED_SHA256 not in protected, "REAL_INPUT_IN_SYNTHETIC_MODE")

    routed, shared = open_pair(document, arguments.routed_root, arguments.shared_root)
    try:
        if arguments.preflight_only:
            after = {"routed": routed.verify_after(), "shared": shared.verify_after()}
            print(json.dumps({
                "disposition": "PRODUCTION_BINDINGS_RESOLVED",
                "inputs_after": after,
                "ledger": 175,
                "checkpoint_reads": 0,
                "shard_opens": 0,
                "expert_executions": 0,
                "shared_expert_executions": 0,
                "ffn_completions": 0,
                "s2_constructions": 0,
            }, sort_keys=True))
            return 0
        raw, after = compose_from_open_inputs(routed, shared)
        write_no_replace(arguments.output, raw)
        print(json.dumps({
            "disposition": "SYNTHETIC_COMPLETE",
            "output_sha256": sha256_bytes(raw),
            "output_bytes": len(raw),
            "output_dtype": "little-endian-f64",
            "output_shape": [6144],
            "inputs_after": after,
            "ledger": 175,
            "checkpoint_reads": 0,
            "shard_opens": 0,
            "expert_executions": 0,
            "shared_expert_executions": 0,
            "ffn_completions": 0,
            "s2_constructions": 0,
        }, sort_keys=True))
        return 0
    finally:
        shared.close()
        routed.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CompositionError as error:
        print(json.dumps({
            "disposition": "FAIL_CLOSED",
            "error": str(error),
            "checkpoint_reads": 0,
            "shard_opens": 0,
            "expert_executions": 0,
            "shared_expert_executions": 0,
            "ffn_completions": 0,
            "s2_constructions": 0,
        }, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)
