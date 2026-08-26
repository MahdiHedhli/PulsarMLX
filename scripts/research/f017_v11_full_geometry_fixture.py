#!/usr/bin/env python3
"""Synthetic-only full-geometry output objects for V11 qualification."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct


@dataclass(frozen=True)
class SyntheticLayerCapture:
    layer: int
    selected_expert_ids: tuple[int, ...]


@dataclass(frozen=True)
class SyntheticTopRecord:
    token_id: int
    logit_f64_bits: str | None = None
    logit_f32_bits: str | None = None


@dataclass(frozen=True)
class SyntheticNumericalOutputs:
    role: str
    dtype: str
    core_execution_count: int
    final_hidden_element_count: int
    final_normalized_element_count: int
    full_logits_element_count: int
    final_hidden_payload: bytes
    final_normalized_payload: bytes
    full_logits_payload: bytes
    final_hidden_sha256: str
    final_normalized_sha256: str
    full_logits_sha256: str
    layer_captures: tuple[SyntheticLayerCapture, ...]
    selected_token: int
    top_32: tuple[SyntheticTopRecord, ...]
    top_1_margin: float
    tie_rule: str


DISTRIBUTIONS = (
    "ZEROS", "SIGNED_ZEROS", "MONOTONIC", "ALTERNATING", "SPARSE_LARGE",
    "SMALL_NORMALS", "SUBNORMALS", "EXACT_TIES", "NEAR_TIES", "PSEUDORANDOM",
)


def _value(distribution: str, index: int, count: int, seed: int) -> float:
    if distribution == "ZEROS": return 0.0
    if distribution == "SIGNED_ZEROS": return -0.0 if index % 2 else 0.0
    if distribution == "MONOTONIC": return (index - count / 2) / max(count, 1) / 16.0
    if distribution == "ALTERNATING": return (1.0 if index % 2 else -1.0) * ((index % 251) / 4096.0)
    if distribution == "SPARSE_LARGE": return float((index % 31) - 15) if index % 997 == 0 else 0.0
    if distribution == "SMALL_NORMALS": return ((index % 17) - 8) * 2.0 ** -20
    if distribution == "SUBNORMALS": return (-1.0 if index % 2 else 1.0) * 2.0 ** -140
    if distribution == "EXACT_TIES": return 1.0 if index < 64 else float(index % 7) / 32.0
    if distribution == "NEAR_TIES": return 1.0 - index * 2.0 ** -20 if index < 64 else float(index % 11) / 64.0
    if distribution == "PSEUDORANDOM":
        mixed = (index * 1_103_515_245 + seed * 12_345 + 0x9E3779B9) & 0xFFFFFFFF
        return (mixed / 0xFFFFFFFF - 0.5) / 8.0
    raise ValueError("synthetic distribution")


def _payload(role: str, distribution: str, count: int, seed: int) -> tuple[bytes, list[float]]:
    code = "d" if role == "PRIMARY" else "f"
    values = [_value(distribution, index, count, seed) for index in range(count)]
    raw = bytearray()
    for start in range(0, count, 4_096):
        chunk = values[start:start + 4_096]
        raw.extend(struct.pack(f"<{len(chunk)}{code}", *chunk))
    decoded = [item[0] for item in struct.iter_unpack(f"<{code}", raw)]
    return bytes(raw), decoded


def make_output(role: str, distribution: str, seed: int = 0) -> SyntheticNumericalOutputs:
    if role not in {"PRIMARY", "SECONDARY"} or distribution not in DISTRIBUTIONS:
        raise ValueError("synthetic output identity")
    hidden, _ = _payload(role, distribution, 6_144, seed)
    normalized, _ = _payload(role, distribution, 6_144, seed + 1)
    logits, decoded = _payload(role, distribution, 154_880, seed + 2)
    order = sorted(range(len(decoded)), key=lambda index: (-decoded[index], index))
    code = "d" if role == "PRIMARY" else "f"
    if role == "PRIMARY":
        top = tuple(SyntheticTopRecord(token_id=index, logit_f64_bits=struct.pack("<d", decoded[index]).hex()) for index in order[:32])
    else:
        top = tuple(SyntheticTopRecord(token_id=index, logit_f32_bits=struct.pack("<f", decoded[index]).hex()) for index in order[:32])
    if not all(math.isfinite(value) for value in decoded):
        raise ValueError("nonfinite synthetic output")
    return SyntheticNumericalOutputs(
        role=role, dtype="f64le" if role == "PRIMARY" else "f32le",
        core_execution_count=1,
        final_hidden_element_count=6_144, final_normalized_element_count=6_144,
        full_logits_element_count=154_880,
        final_hidden_payload=hidden, final_normalized_payload=normalized,
        full_logits_payload=logits,
        final_hidden_sha256=hashlib.sha256(hidden).hexdigest(),
        final_normalized_sha256=hashlib.sha256(normalized).hexdigest(),
        full_logits_sha256=hashlib.sha256(logits).hexdigest(),
        layer_captures=tuple(SyntheticLayerCapture(layer=index,
            selected_expert_ids=tuple() if index < 3 else (index % 256, (index + 1) % 256)) for index in range(79)),
        selected_token=order[0], top_32=top,
        top_1_margin=float(decoded[order[0]] - decoded[order[1]]),
        tie_rule=f"LOWEST_TOKEN_ID_ON_EQUAL_BINARY{'64' if role == 'PRIMARY' else '32'}_LOGIT",
    )
