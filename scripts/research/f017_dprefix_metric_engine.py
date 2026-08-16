#!/usr/bin/env python3
"""Standalone deterministic Tier-B metric engine for DPREFIX paired f32 values."""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import asdict, dataclass
from functools import reduce
from operator import mul


@dataclass(frozen=True)
class MetricResult:
    shape: list[int]
    count: int
    dtype: str
    serialization: str
    candidate_sha256: str
    oracle_sha256: str
    max_absolute_error: float
    rmse: float
    cosine_similarity: float
    candidate_non_finite_count: int
    oracle_non_finite_count: int
    signed_zero_mismatch_count: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _values(payload: bytes, count: int, label: str) -> tuple[list[float], list[int]]:
    if len(payload) != count * 4:
        raise ValueError(f"{label} byte length does not match shape")
    floats: list[float] = []
    bits: list[int] = []
    for offset in range(0, len(payload), 4):
        word = struct.unpack_from("<I", payload, offset)[0]
        value = struct.unpack_from("<f", payload, offset)[0]
        bits.append(word)
        floats.append(value)
    return floats, bits


def compare_f32le(candidate: bytes, oracle: bytes, shape: list[int]) -> MetricResult:
    if not shape or any(not isinstance(value, int) or value <= 0 for value in shape):
        raise ValueError("shape must contain positive integers")
    count = reduce(mul, shape, 1)
    candidate_values, candidate_bits = _values(candidate, count, "candidate")
    oracle_values, oracle_bits = _values(oracle, count, "oracle")
    candidate_non_finite = sum(not math.isfinite(value) for value in candidate_values)
    oracle_non_finite = sum(not math.isfinite(value) for value in oracle_values)
    if candidate_non_finite or oracle_non_finite:
        raise ValueError("non-finite paired value")

    differences = [float(left) - float(right) for left, right in zip(candidate_values, oracle_values)]
    max_absolute_error = max((abs(value) for value in differences), default=0.0)
    rmse = math.sqrt(math.fsum(value * value for value in differences) / count)
    dot = math.fsum(float(left) * float(right) for left, right in zip(candidate_values, oracle_values))
    candidate_norm = math.sqrt(math.fsum(float(value) * float(value) for value in candidate_values))
    oracle_norm = math.sqrt(math.fsum(float(value) * float(value) for value in oracle_values))
    if candidate == oracle:
        cosine = 1.0
    elif candidate_norm == 0.0 or oracle_norm == 0.0:
        cosine = 1.0 if candidate == oracle else 0.0
    else:
        cosine = dot / (candidate_norm * oracle_norm)
        cosine = min(1.0, max(-1.0, cosine))
    signed_zero_mismatch = sum(
        left != right and (left & 0x7FFFFFFF) == 0 and (right & 0x7FFFFFFF) == 0
        for left, right in zip(candidate_bits, oracle_bits)
    )
    return MetricResult(
        shape=list(shape),
        count=count,
        dtype="f32",
        serialization="canonical_little_endian_ieee754_binary32_c_order",
        candidate_sha256=hashlib.sha256(candidate).hexdigest(),
        oracle_sha256=hashlib.sha256(oracle).hexdigest(),
        max_absolute_error=max_absolute_error,
        rmse=rmse,
        cosine_similarity=cosine,
        candidate_non_finite_count=candidate_non_finite,
        oracle_non_finite_count=oracle_non_finite,
        signed_zero_mismatch_count=signed_zero_mismatch,
    )
