#!/usr/bin/env python3
"""Feature 018 public evidence parsing and semantic validation."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

from f018_numerical_contract import CLASSES
from glm52_telemetry import assert_public_safe

_HEX40 = re.compile(r"^[0-9a-f]{40}$")


def _unique_pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_unique_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=_unique_pairs)
    if not isinstance(value, dict):
        raise ValueError("Feature 018 evidence root must be an object")
    return value


def _samples(record: dict[str, Any]) -> list[float]:
    timing = record.get("timing")
    if not isinstance(timing, dict):
        raise ValueError("timing must be an object")
    raw = timing.get("measured_samples_seconds")
    if not isinstance(raw, list) or not raw:
        raise ValueError("measured_samples_seconds must be nonempty")
    samples = [float(value) for value in raw]
    if not all(math.isfinite(value) and value >= 0.0 for value in samples):
        raise ValueError("timing samples must be finite and nonnegative")
    if timing.get("sample_count") != len(samples):
        raise ValueError("sample_count does not match raw samples")
    expected = {
        "minimum_seconds": min(samples),
        "maximum_seconds": max(samples),
        "mean_seconds": sum(samples) / len(samples),
    }
    for key, value in expected.items():
        if not math.isclose(float(timing.get(key, math.nan)), value, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"{key} does not match raw samples")
    return samples


def validate_record(record: dict[str, Any]) -> dict[str, Any]:
    try:
        assert_public_safe(record)
    except ValueError as exc:
        raise ValueError(f"record is not public-safe: {exc}") from exc
    if record.get("schema") != "pulsarmlx.research.f018-direct-iq2-xxs":
        raise ValueError("unexpected Feature 018 schema")
    if record.get("schema_version") != "1.0.0":
        raise ValueError("unexpected Feature 018 schema_version")
    if record.get("classification") not in CLASSES:
        raise ValueError("unsupported numerical classification")
    source = record.get("source")
    if not isinstance(source, dict) or not _HEX40.fullmatch(str(source.get("commit", ""))):
        raise ValueError("source commit must be lowercase 40-character SHA")
    if source.get("dirty") is not False:
        raise ValueError("source must be clean")
    kernel = record.get("kernel")
    if not isinstance(kernel, dict) or kernel.get("quantization") != "IQ2_XXS":
        raise ValueError("kernel quantization must be IQ2_XXS")
    if kernel.get("cpu_fallback_count") != 0:
        raise ValueError("cpu_fallback_count must be zero")
    if kernel.get("complete_f32_weight_materialized_bytes") != 0:
        raise ValueError("complete_f32_weight_materialized_bytes must be zero")
    if record.get("resource", {}).get("level") != "normal":
        raise ValueError("resource level must be normal for a passed record")
    if not isinstance(record.get("claim_boundary"), str) or not record["claim_boundary"]:
        raise ValueError("claim_boundary is required")
    if not record.get("unsupported_interpretations"):
        raise ValueError("unsupported_interpretations are required")
    _samples(record)
    return record
