#!/usr/bin/env python3
"""Checkpoint-free extraction of canonical representative S1 from the accepted oracle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import sys
from typing import Any

import numpy as np

from f017_representative_m1f0_executor import InventoryEntry, RetainedSpec
from f017_representative_m1f0_executor_v3 import EagerDecoderRegistry, OpenRetainedAuthority
import prepare_f017_m1f0_real_reference as oracle


EXPECTED_S1_SHA256 = "8309377ee8e8f34eb91cdb025624144eb5be7821ed9e4a295df29b13aac5a0dd"
EXPECTED_S1_BYTES = 24_576
EXPECTED_S0_SHA256 = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"


class S1Error(RuntimeError):
    pass


class _CapturedS1(BaseException):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_immutable(path: Path, expected_sha: str, expected_bytes: int) -> None:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise S1Error("SOURCE_NOT_REGULAR")
    if before.st_nlink != 1 or before.st_mode & 0o222:
        raise S1Error("SOURCE_WRITABLE_OR_LINKED")
    if before.st_size != expected_bytes or sha_file(path) != expected_sha:
        raise S1Error("SOURCE_IDENTITY")


def _capture_s1(call: Any) -> np.ndarray:
    """Observe the accepted oracle local; do not reimplement attention arithmetic."""
    captured: dict[str, np.ndarray] = {}
    target = oracle.compose_oracle.__code__

    def local_tracer(frame: Any, event: str, arg: Any) -> Any:
        if event == "line" and "attention_residual" in frame.f_locals:
            value = frame.f_locals["attention_residual"]
            if not isinstance(value, np.ndarray):
                raise S1Error("S1_LOCAL_TYPE")
            captured["s1"] = np.array(value, dtype=np.float32, copy=True)
            raise _CapturedS1()
        return local_tracer

    def tracer(frame: Any, event: str, arg: Any) -> Any:
        if event == "call" and frame.f_code is target:
            return local_tracer
        return None

    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        call()
    except _CapturedS1:
        pass
    finally:
        sys.settrace(previous)
    if "s1" not in captured:
        raise S1Error("S1_NOT_OBSERVED")
    return captured["s1"]


def reconstruct(candidate_path: Path, retention_root: Path, canonical_s0: Path) -> tuple[bytes, dict[str, str]]:
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    inventory = candidate.get("attention_payload_inventory")
    if not isinstance(inventory, list) or len(inventory) != 9:
        raise S1Error("ATTENTION_INVENTORY")
    s0_spec_value = candidate.get("retained_inputs", [None])[0]
    if not isinstance(s0_spec_value, dict) or s0_spec_value.get("role") != "canonical_s0":
        raise S1Error("S0_CONTRACT")
    if s0_spec_value.get("sha256") != EXPECTED_S0_SHA256:
        raise S1Error("S0_AUTHORITY")

    decoded: dict[str, Any] = {}
    decoders = EagerDecoderRegistry().instantiate()
    packed_before: dict[str, str] = {}
    for item in inventory:
        entry = InventoryEntry(item["ordinal"], item["key"], item["offset"], item["packed_bytes"],
            item["quantization"], tuple(item["logical_shape"]), item["packed_sha256"], item["decoded_sha256"])
        packed = retention_root / "packed" / f"{entry.ordinal:02d}.bin"
        require_immutable(packed, entry.packed_sha256, entry.packed_bytes)
        packed_before[entry.key] = entry.packed_sha256
        pair = decoders[entry.quantization]
        first, second = pair.a.decode(packed, entry), pair.b.decode(packed, entry)
        if first.identity != second.identity or first.identity != entry.decoded_sha256:
            raise S1Error("DECODER_DISAGREEMENT")
        if first.canonical_bytes is None or not np.isfinite(np.frombuffer(first.canonical_bytes, dtype="<f4")).all():
            raise S1Error("DECODED_NONFINITE")
        decoded[entry.key] = first

    spec = RetainedSpec(s0_spec_value["role"], s0_spec_value["key"], s0_spec_value["sha256"],
        s0_spec_value["dtype"], tuple(s0_spec_value["shape"]), s0_spec_value["byte_length"],
        s0_spec_value.get("private_manifest_sha256"))
    authority = OpenRetainedAuthority(canonical_s0, spec)
    try:
        s0 = authority.array()
        tensors = {key: np.frombuffer(value.canonical_bytes, dtype="<f4").reshape(value.shape)
                   for key, value in decoded.items()}

        def run() -> Any:
            return oracle.compose_oracle(
                s0,
                lambda name: tensors[name],
                lambda name, values: oracle.strict_matvec(tensors[name], values),
                lambda name, head, values: oracle.strict_matvec(tensors[name][head], values),
            )

        value = _capture_s1(run)
        s0_after = authority.verify_after()
    finally:
        authority.close()
    for item in inventory:
        packed = retention_root / "packed" / f"{item['ordinal']:02d}.bin"
        require_immutable(packed, item["packed_sha256"], item["packed_bytes"])
    raw = np.ascontiguousarray(value, dtype="<f4").tobytes()
    if value.shape != (6144,) or len(raw) != EXPECTED_S1_BYTES or not np.isfinite(value).all():
        raise S1Error("S1_GEOMETRY_OR_FINITE")
    if sha256(raw) != EXPECTED_S1_SHA256:
        raise S1Error("S1_EXPECTED_SHA")
    return raw, {"canonical_s0": s0_after, **packed_before}


def synthetic_fixture(seed: int = 17) -> bytes:
    """Real output geometry only; never accepts retained production inputs."""
    rng = np.random.default_rng(seed)
    s0 = rng.normal(size=6144).astype(np.float32)
    attention = rng.normal(scale=0.01, size=6144).astype(np.float32)
    return np.add(s0, attention, dtype=np.float32).astype("<f4").tobytes()
