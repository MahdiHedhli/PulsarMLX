#!/usr/bin/env python3
"""Canonical binary numerical-result envelopes for F017 lifecycle V11.

Large numerical arrays never pass through the bounded control-plane JSON
decoder.  Their byte geometry is derived from the role, payload kind, shape,
and IEEE-754 item size frozen below.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import stat
import struct
from typing import Iterable, Iterator


class ResultEnvelopeError(ValueError):
    """Stable fail-closed boundary for malformed result envelopes."""


HIDDEN_SIZE = 6_144
VOCAB_SIZE = 154_880
TOP_N = 32
DEFAULT_CHUNK_ELEMENTS = 4_096


@dataclass(frozen=True)
class PayloadSpec:
    role: str
    kind: str
    dtype: str
    shape: tuple[int, ...]

    @property
    def itemsize(self) -> int:
        return {"f32le": 4, "f64le": 8}[self.dtype]

    @property
    def element_count(self) -> int:
        result = 1
        for dimension in self.shape:
            result *= dimension
        return result

    @property
    def byte_count(self) -> int:
        return self.element_count * self.itemsize

    @property
    def struct_code(self) -> str:
        return "f" if self.dtype == "f32le" else "d"

    def record(self) -> dict:
        return {
            "role": self.role,
            "payload_kind": self.kind,
            "dtype": self.dtype,
            "endianness": "LITTLE",
            "shape": list(self.shape),
            "element_count": self.element_count,
            "expected_byte_count": self.byte_count,
        }


PAYLOAD_SPECS = {
    (role, kind): PayloadSpec(role, kind, dtype, shape)
    for role, dtype in (("PRIMARY", "f64le"), ("SECONDARY", "f32le"))
    for kind, shape in (
        ("final_hidden", (HIDDEN_SIZE,)),
        ("final_normalized", (HIDDEN_SIZE,)),
        ("full_logits", (VOCAB_SIZE,)),
    )
}


def payload_spec(role: str, kind: str) -> PayloadSpec:
    if type(role) is not str or type(kind) is not str:
        raise ResultEnvelopeError("payload identity type")
    try:
        return PAYLOAD_SPECS[(role, kind)]
    except KeyError as exc:
        raise ResultEnvelopeError("unknown payload identity") from exc


def _validate_leaf(leaf: str) -> None:
    if type(leaf) is not str or not leaf or "/" in leaf or leaf in {".", ".."}:
        raise ResultEnvelopeError("payload leaf")


def _pack_chunk(values: list[float], spec: PayloadSpec) -> bytes:
    if any(type(value) not in (int, float) or not math.isfinite(float(value)) for value in values):
        raise ResultEnvelopeError("payload value is not finite")
    try:
        return struct.pack(f"<{len(values)}{spec.struct_code}", *values)
    except (OverflowError, struct.error, TypeError, ValueError) as exc:
        raise ResultEnvelopeError("payload value is not representable") from exc


def _write_all(descriptor: int, raw: bytes) -> None:
    offset = 0
    while offset < len(raw):
        written = os.write(descriptor, raw[offset:])
        if written <= 0:
            raise ResultEnvelopeError("short payload write")
        offset += written


def bank_payload(directory: Path, leaf: str, spec: PayloadSpec, values: Iterable[float],
                 *, chunk_elements: int = DEFAULT_CHUNK_ELEMENTS) -> dict:
    """Exclusively bank, fsync, and descriptor-readback an exact payload."""
    if not isinstance(directory, Path) or not isinstance(spec, PayloadSpec):
        raise ResultEnvelopeError("payload bank arguments")
    _validate_leaf(leaf)
    if type(chunk_elements) is not int or type(chunk_elements) is bool or chunk_elements <= 0:
        raise ResultEnvelopeError("chunk element count")
    directory.mkdir(parents=True, exist_ok=True)
    directory_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    descriptor = -1
    written = 0
    count = 0
    write_digest = hashlib.sha256()
    try:
        descriptor = os.open(
            leaf,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        chunk: list[float] = []
        for value in values:
            chunk.append(value)
            if len(chunk) == chunk_elements:
                raw = _pack_chunk(chunk, spec)
                _write_all(descriptor, raw)
                write_digest.update(raw)
                written += len(raw); count += len(chunk); chunk.clear()
        if chunk:
            raw = _pack_chunk(chunk, spec)
            _write_all(descriptor, raw)
            write_digest.update(raw)
            written += len(raw); count += len(chunk)
        if count != spec.element_count or written != spec.byte_count:
            raise ResultEnvelopeError("payload geometry mismatch during write")
        os.fsync(descriptor)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ResultEnvelopeError("payload is not a regular file")
        os.close(descriptor); descriptor = -1
        os.fsync(directory_fd)
        read_descriptor = os.open(leaf, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        try:
            after = os.fstat(read_descriptor)
            if (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, after.st_size):
                raise ResultEnvelopeError("payload identity changed before readback")
            if after.st_size != spec.byte_count:
                raise ResultEnvelopeError("payload readback byte count")
            read_digest = hashlib.sha256()
            observed = 0
            while True:
                raw = os.read(read_descriptor, 1 << 20)
                if not raw:
                    break
                read_digest.update(raw); observed += len(raw)
            if observed != spec.byte_count or read_digest.digest() != write_digest.digest():
                raise ResultEnvelopeError("payload readback mismatch")
        finally:
            os.close(read_descriptor)
    except ResultEnvelopeError:
        raise
    except OSError as exc:
        raise ResultEnvelopeError("payload filesystem failure") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory_fd)
    return {
        **spec.record(),
        "path_role": leaf,
        "observed_byte_count": written,
        "sha256": write_digest.hexdigest(),
        "finite_values": True,
        "signed_zero_policy": "PRESERVE_IEEE754_BITS",
        "producer_identity": f"F017_V11_{spec.role}_RESULT_ENVELOPE",
    }


def validate_payload(directory: Path, record: dict, *, expected_spec: PayloadSpec | None = None) -> dict:
    """Validate one payload and its exact geometry without following symlinks."""
    if type(record) is not dict:
        raise ResultEnvelopeError("payload record type")
    required = set((expected_spec or payload_spec(record.get("role"), record.get("payload_kind"))).record()) | {
        "path_role", "observed_byte_count", "sha256", "finite_values",
        "signed_zero_policy", "producer_identity",
    }
    if type(record) is not dict or set(record) != required:
        raise ResultEnvelopeError("payload record key census")
    spec = expected_spec or payload_spec(record["role"], record["payload_kind"])
    expected = spec.record()
    for key, value in expected.items():
        if record.get(key) != value:
            raise ResultEnvelopeError(f"payload record mismatch: {key}")
    if type(record["sha256"]) is not str or len(record["sha256"]) != 64:
        raise ResultEnvelopeError("payload SHA")
    if record["observed_byte_count"] != spec.byte_count or record["finite_values"] is not True:
        raise ResultEnvelopeError("payload size or finite status")
    if record["signed_zero_policy"] != "PRESERVE_IEEE754_BITS":
        raise ResultEnvelopeError("signed-zero policy")
    leaf = record["path_role"]; _validate_leaf(leaf)
    directory_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        descriptor = os.open(leaf, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size != spec.byte_count:
                raise ResultEnvelopeError("payload file geometry")
            digest = hashlib.sha256(); finite = True; observed = 0
            carry = b""
            while True:
                raw = os.read(descriptor, 1 << 20)
                if not raw: break
                digest.update(raw); observed += len(raw); raw = carry + raw
                whole = len(raw) - len(raw) % spec.itemsize
                for (value,) in struct.iter_unpack(f"<{spec.struct_code}", raw[:whole]):
                    finite = finite and math.isfinite(value)
                carry = raw[whole:]
            if carry or observed != spec.byte_count or not finite:
                raise ResultEnvelopeError("payload content invalid")
            if digest.hexdigest() != record["sha256"]:
                raise ResultEnvelopeError("payload SHA mismatch")
        finally:
            os.close(descriptor)
    except ResultEnvelopeError:
        raise
    except OSError as exc:
        raise ResultEnvelopeError("payload validation filesystem failure") from exc
    finally:
        os.close(directory_fd)
    return {"result": "PASS", "sha256": record["sha256"], "element_count": spec.element_count}


def iter_payload(directory: Path, record: dict, *, chunk_elements: int = DEFAULT_CHUNK_ELEMENTS) -> Iterator[list[float]]:
    spec = payload_spec(record.get("role"), record.get("payload_kind"))
    validate_payload(directory, record, expected_spec=spec)
    if type(chunk_elements) is not int or type(chunk_elements) is bool or chunk_elements <= 0:
        raise ResultEnvelopeError("chunk element count")
    descriptor = os.open(directory / record["path_role"], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        remaining = spec.element_count
        while remaining:
            count = min(chunk_elements, remaining)
            raw = bytearray()
            while len(raw) < count * spec.itemsize:
                part = os.read(descriptor, count * spec.itemsize - len(raw))
                if not part: raise ResultEnvelopeError("short payload read")
                raw.extend(part)
            yield [value[0] for value in struct.iter_unpack(f"<{spec.struct_code}", raw)]
            remaining -= count
        if os.read(descriptor, 1):
            raise ResultEnvelopeError("excess payload bytes")
    finally:
        os.close(descriptor)
