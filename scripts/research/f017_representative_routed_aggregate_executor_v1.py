#!/usr/bin/env python3
"""Exact analytical routed-aggregate executor for F017 representative outputs.

The real execution entrypoint is inert without a later independently approved
single-use release.  Synthetic rehearsal is a separate, explicitly marked
mode and never resolves the retained representative package.
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


IDS = (250, 10, 237, 62, 73, 177, 218, 28)
WEIGHTS = (0.7487501576296707, 0.3348627106807668, 0.23863270273063697,
           0.23688715675086147, 0.2514906203405492, 0.23059957299763345,
           0.22915341148588297, 0.22962366738399842)
OUTPUT_SHAS = (
    "0b6036ef2e77142094b673c421b96719619a58e15eee7522347b37f73d9b892b",
    "d9adb474f64c98349dfe0a6c768b2020b27f62ecc85874975c990b880ef304b3",
    "4ac842afb3b1909f9f0e07013c86bbdca90cd246b6190bf190a60fe9767fdd9b",
    "2550cccf9b2f1a83b2e2f03f090ee135dc525a15eaf1bab18d1a2fb97af16128",
    "9aa5e1dae2619c440c65689154de332da313990b4ba07fdac45e78a65ad3a7d3",
    "18260d4936483b6f7d83d2d0ec72d01fc761f2ac5726fa9b7bda243a4db9a201",
    "f4a8fc1e3bb91a8a5635505f766a07ef2cfb135378d224ed5f545617d781537d",
    "45029a47061c43746344d5b0a9366b8129630019a3196d0be146efc5e1a361f0",
)
REUSE_SHA = "1b8b053d60f87c9da8c8c81a41a3d82f7652859a2464941c39b5a1eab3d7c070"
MANIFEST_SHA = "2b3a0ef3bb2d896dd04add67e6fc729b2b400170b58f9038751cee612d58bc7a"
DIMENSION = 6144
INPUT_BYTES = 24576
OUTPUT_BYTES = 49152


class AggregateError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AggregateError(message)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, f"duplicate key: {key}")
            result[key] = value
        return result
    value = json.loads(path.read_text(), object_pairs_hook=no_duplicates)
    require(isinstance(value, dict), "JSON object required")
    return value


def require_environment() -> None:
    require(platform.python_implementation() == "CPython", "CPython required")
    require(sys.version_info[:3] == (3, 14, 6), "CPython 3.14.6 required")
    require(sys.byteorder == "little", "little-endian required")
    require((sys.float_info.radix, sys.float_info.mant_dig, sys.float_info.rounds) == (2, 53, 1),
            "IEEE-754 binary64 environment required")
    require((platform.machine(), platform.system()) == ("arm64", "Darwin"), "Darwin arm64 required")


def _read_exact_fd(fd: int, expected: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = expected
    while remaining:
        chunk = os.read(fd, min(remaining, 1024 * 1024))
        require(bool(chunk), "short input")
        chunks.append(chunk)
        remaining -= len(chunk)
    require(os.read(fd, 1) == b"", "oversized input")
    return b"".join(chunks)


class OpenOnceInputs:
    def __init__(self, root: Path, records: list[dict[str, Any]], *, manifest_sha: str | None) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        self.root_fd = os.open(root, flags)
        self.handles: list[tuple[int, os.stat_result, bytes, str]] = []
        try:
            root_stat = os.fstat(self.root_fd)
            require(stat.S_ISDIR(root_stat.st_mode), "input root must be a directory")
            if manifest_sha is not None:
                manifest_fd = os.open("manifest.json", os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=self.root_fd)
                try:
                    meta = os.fstat(manifest_fd)
                    require(stat.S_ISREG(meta.st_mode), "manifest must be regular")
                    manifest_raw = _read_exact_fd(manifest_fd, meta.st_size)
                    require(sha256_bytes(manifest_raw) == manifest_sha, "private manifest identity")
                finally:
                    os.close(manifest_fd)
            for record in records:
                name = record.get("private_relative_path")
                require(isinstance(name, str) and Path(name).name == name, "pure relative basename required")
                fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=self.root_fd)
                try:
                    meta = os.fstat(fd)
                    require(stat.S_ISREG(meta.st_mode), "input must be regular")
                    require(meta.st_nlink == 1, "input must have one hard link")
                    require(meta.st_mode & 0o222 == 0, "input must be read-only")
                    require(meta.st_size == INPUT_BYTES == record.get("byte_length"), "input size")
                    raw = _read_exact_fd(fd, INPUT_BYTES)
                    expected = record.get("output_sha256")
                    require(sha256_bytes(raw) == expected, "EXPECTED != BEFORE")
                    values = struct.unpack("<6144f", raw)
                    require(all(math.isfinite(value) for value in values), "non-finite input")
                    self.handles.append((fd, meta, raw, expected))
                except Exception:
                    os.close(fd)
                    raise
        except Exception:
            self.close()
            raise

    @property
    def raw_inputs(self) -> tuple[bytes, ...]:
        return tuple(item[2] for item in self.handles)

    def verify_after(self) -> list[str]:
        results: list[str] = []
        for fd, before_meta, consumed, expected in self.handles:
            after_raw = _read_exact_fd(fd, INPUT_BYTES)
            after_meta = os.fstat(fd)
            after_sha = sha256_bytes(after_raw)
            require((before_meta.st_dev, before_meta.st_ino) == (after_meta.st_dev, after_meta.st_ino),
                    "input object changed")
            require(expected == sha256_bytes(consumed) == after_sha, "EXPECTED != CONSUMED != AFTER")
            results.append(after_sha)
        return results

    def close(self) -> None:
        for fd, *_ in getattr(self, "handles", []):
            try:
                os.close(fd)
            except OSError:
                pass
        self.handles = []
        if hasattr(self, "root_fd"):
            try:
                os.close(self.root_fd)
            except OSError:
                pass

    def __enter__(self) -> "OpenOnceInputs":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def validate_records(records: Any, *, synthetic: bool) -> list[dict[str, Any]]:
    require(isinstance(records, list) and len(records) == 8, "eight inputs required")
    require([r.get("ordinal") for r in records] == list(range(8)), "ordinal order")
    require(tuple(r.get("expert_id") for r in records) == IDS, "expert order")
    require(tuple(r.get("routing_weight") for r in records) == WEIGHTS, "weight pairing")
    for i, record in enumerate(records):
        require(record.get("private_relative_path") == f"{i:02d}-expert-{IDS[i]}-down.f32le", "filename binding")
        require(record.get("dtype") == "little-endian-f32" and record.get("shape") == [6144], "input dtype/shape")
        require(record.get("byte_length") == INPUT_BYTES, "input byte length")
        if not synthetic:
            require(record.get("output_sha256") == OUTPUT_SHAS[i], "representative output identity")
    return records


def validate_authorization(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    doc = load_json(path)
    require(doc.get("schema") == "pulsarmlx.f017.representative-routed-aggregate-authorization", "authorization schema")
    require(doc.get("schema_version") == "1.0.0", "authorization version")
    require(doc.get("status") == "PREPARED_REVIEW_REQUIRED" and doc.get("real_event_authorized") is False, "authorization state")
    require(doc.get("expert_output_reuse_authorization", {}).get("sha256") == REUSE_SHA, "reuse authority")
    return doc, validate_records(doc.get("atomic_id_weight_output_triples"), synthetic=False)


def aggregate_bytes(raw_inputs: tuple[bytes, ...], weights: tuple[float, ...] = WEIGHTS) -> bytes:
    require_environment()
    require(len(raw_inputs) == len(weights) == 8, "aggregate width")
    output = bytearray(OUTPUT_BYTES)
    for k in range(DIMENSION):
        terms = tuple(weights[i] * float(struct.unpack_from("<f", raw_inputs[i], 4 * k)[0]) for i in range(8))
        require(all(math.isfinite(term) for term in terms), "non-finite product")
        value = math.fsum(terms)
        require(math.isfinite(value), "non-finite aggregate")
        struct.pack_into("<d", output, 8 * k, value)
    return bytes(output)


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o400)
        os.replace(temporary, path)
        parent_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_release(release_path: Path, authorization_path: Path) -> None:
    release = load_json(release_path)
    expected_keys = {"schema", "schema_version", "status", "real_event_authorized", "authorization_sha256",
                     "executor_sha256", "event_id", "release_id", "attempt_id", "disposition"}
    require(set(release) == expected_keys, "release schema keys")
    require(release.get("schema") == "pulsarmlx.f017.representative-routed-aggregate-single-use-release", "release schema")
    require(release.get("status") == "INDEPENDENTLY_APPROVED" and release.get("real_event_authorized") is True, "release approval")
    require(release.get("authorization_sha256") == sha256_path(authorization_path), "release authorization binding")
    require(release.get("executor_sha256") == sha256_path(Path(__file__)), "release executor binding")
    require(release.get("disposition") == "GO_EXECUTE_ONCE_NO_RETRY", "release disposition")


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight-only", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--synthetic-rehearsal", action="store_true")
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--synthetic-manifest", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--release", type=Path)
    args = parser.parse_args()
    require_environment()

    if args.synthetic_rehearsal:
        require(args.synthetic_manifest is not None and args.authorization is None and args.release is None, "synthetic interface")
        manifest = load_json(args.synthetic_manifest)
        require(manifest.get("schema") == "pulsarmlx.f017.representative-routed-aggregate-synthetic-input", "synthetic schema")
        records = validate_records(manifest.get("inputs"), synthetic=True)
        manifest_sha = None
    else:
        require(args.authorization is not None and args.synthetic_manifest is None, "production interface")
        _, records = validate_authorization(args.authorization)
        manifest_sha = MANIFEST_SHA

    with OpenOnceInputs(args.output_root, records, manifest_sha=manifest_sha) as inputs:
        if args.preflight_only:
            after = inputs.verify_after()
            print(json.dumps({"disposition": "PRODUCTION_BINDINGS_RESOLVED", "inputs": len(after), "ledger": 175,
                              "checkpoint_reads": 0, "shard_opens": 0, "expert_executions": 0,
                              "aggregate_executions": 0}, sort_keys=True))
            return 0
        require(args.output is not None, "output required")
        if args.execute:
            require(args.release is not None, "approved release required")
            validate_release(args.release, args.authorization)
        else:
            require(args.release is None, "synthetic release forbidden")
        raw = aggregate_bytes(inputs.raw_inputs)
        after = inputs.verify_after()
        _atomic_write(args.output, raw)
        print(json.dumps({"disposition": "SYNTHETIC_COMPLETE" if args.synthetic_rehearsal else "COMPLETE",
                          "output_sha256": sha256_bytes(raw), "output_bytes": len(raw), "output_dtype": "little-endian-f64",
                          "output_shape": [6144], "inputs_after": after, "ledger": 175,
                          "checkpoint_reads": 0, "shard_opens": 0, "expert_executions": 0,
                          "aggregate_executions": 0 if args.synthetic_rehearsal else 1}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AggregateError as error:
        print(json.dumps({"disposition": "FAIL_CLOSED", "error": str(error), "checkpoint_reads": 0,
                          "shard_opens": 0, "expert_executions": 0, "aggregate_executions": 0}, sort_keys=True), file=sys.stderr)
        raise SystemExit(2)
