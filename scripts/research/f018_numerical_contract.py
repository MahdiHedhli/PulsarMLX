#!/usr/bin/env python3
"""Frozen Feature 018 numerical classification.

This module is checkpoint-free and does not import MLX or any candidate kernel.
"""

from __future__ import annotations

import math
import json
import struct
import argparse
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

CONTRACT_VERSION = "f018-numerical-v1"

CLASS_GOLDEN_IDENTICAL = "golden_identical"
CLASS_NUMERICALLY_QUALIFIED_GREEDY_IDENTICAL = (
    "numerically_qualified_greedy_identical"
)
CLASS_NUMERICALLY_QUALIFIED_GREEDY_DIVERGENT = (
    "numerically_qualified_greedy_divergent"
)
CLASS_NUMERICALLY_FAILED = "numerically_failed"

CLASSES = frozenset(
    {
        CLASS_GOLDEN_IDENTICAL,
        CLASS_NUMERICALLY_QUALIFIED_GREEDY_IDENTICAL,
        CLASS_NUMERICALLY_QUALIFIED_GREEDY_DIVERGENT,
        CLASS_NUMERICALLY_FAILED,
    }
)

_ENVELOPES = {
    "matrix": {
        "absolute_tolerance": 0.0005,
        "relative_tolerance": 0.0005,
        "cosine_minimum": 0.999999,
        "norm_ratio_minimum": 0.9995,
        "norm_ratio_maximum": 1.0005,
    },
    "composed": {
        "absolute_tolerance": 0.005,
        "relative_tolerance": 0.005,
        "cosine_minimum": 0.999,
        "norm_ratio_minimum": 0.995,
        "norm_ratio_maximum": 1.005,
    },
}


def contract_manifest() -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.fixture.f018-numerical-contract",
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "classes": sorted(CLASSES),
        "envelopes": {name: dict(values) for name, values in _ENVELOPES.items()},
        "teacher_forced_rule": "continue_all_frozen_positions_after_argmax_divergence",
    }


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def _f32_bytes(values: Iterable[float]) -> bytes:
    return b"".join(struct.pack("<f", _f32(value)) for value in values)


def _is_negative_zero(value: float) -> bool:
    return value == 0.0 and struct.pack("<f", _f32(value)) == b"\x00\x00\x00\x80"


def compare_vectors(
    reference: Sequence[float],
    candidate: Sequence[float],
    *,
    boundary: str,
) -> dict[str, Any]:
    if boundary not in _ENVELOPES:
        raise ValueError(f"unsupported boundary: {boundary}")
    envelope = _ENVELOPES[boundary]
    ref = [_f32(value) for value in reference]
    got = [_f32(value) for value in candidate]
    if len(ref) != len(got) or not ref:
        return {
            **envelope,
            "length_matches": False,
            "finite": False,
            "exact_f32_bits": False,
            "signed_zero_mismatch_count": 0,
            "elementwise_mismatch_count": max(len(ref), len(got)),
            "maximum_absolute_error": math.inf,
            "mean_absolute_error": math.inf,
            "rmse": math.inf,
            "maximum_meaningful_relative_error": math.inf,
            "cosine_similarity": -1.0,
            "norm_ratio": math.inf,
            "numerically_qualified": False,
        }

    finite = all(math.isfinite(value) for value in (*ref, *got))
    exact = finite and _f32_bytes(ref) == _f32_bytes(got)
    signed_zero_mismatches = sum(
        _is_negative_zero(left) != _is_negative_zero(right)
        for left, right in zip(ref, got)
        if left == 0.0 and right == 0.0
    )
    if not finite:
        return {
            **envelope,
            "length_matches": True,
            "finite": False,
            "exact_f32_bits": False,
            "signed_zero_mismatch_count": signed_zero_mismatches,
            "elementwise_mismatch_count": len(ref),
            "maximum_absolute_error": math.inf,
            "mean_absolute_error": math.inf,
            "rmse": math.inf,
            "maximum_meaningful_relative_error": math.inf,
            "cosine_similarity": -1.0,
            "norm_ratio": math.inf,
            "numerically_qualified": False,
        }

    errors = [abs(left - right) for left, right in zip(ref, got)]
    mismatch_count = sum(
        error
        > envelope["absolute_tolerance"]
        + envelope["relative_tolerance"] * abs(left)
        for left, error in zip(ref, errors)
    )
    meaningful_relative = [
        error / abs(left)
        for left, error in zip(ref, errors)
        if abs(left) > envelope["absolute_tolerance"]
    ]
    ref_norm = math.sqrt(sum(value * value for value in ref))
    got_norm = math.sqrt(sum(value * value for value in got))
    if ref_norm == 0.0 and got_norm == 0.0:
        cosine = 1.0
        norm_ratio = 1.0
    elif ref_norm == 0.0 or got_norm == 0.0:
        cosine = -1.0
        norm_ratio = math.inf
    else:
        cosine = sum(left * right for left, right in zip(ref, got)) / (
            ref_norm * got_norm
        )
        norm_ratio = got_norm / ref_norm
    qualified = (
        mismatch_count == 0
        and cosine >= envelope["cosine_minimum"]
        and envelope["norm_ratio_minimum"]
        <= norm_ratio
        <= envelope["norm_ratio_maximum"]
    )
    return {
        **envelope,
        "length_matches": True,
        "finite": True,
        "exact_f32_bits": exact,
        "signed_zero_mismatch_count": signed_zero_mismatches,
        "elementwise_mismatch_count": mismatch_count,
        "maximum_absolute_error": max(errors),
        "mean_absolute_error": sum(errors) / len(errors),
        "rmse": math.sqrt(sum(error * error for error in errors) / len(errors)),
        "maximum_meaningful_relative_error": max(meaningful_relative, default=0.0),
        "cosine_similarity": cosine,
        "norm_ratio": norm_ratio,
        "numerically_qualified": qualified,
    }


def classify_boundary(
    *,
    reference: Sequence[float],
    candidate: Sequence[float],
    boundary: str,
    reference_argmax: int | None = None,
    candidate_argmax: int | None = None,
    identity_matches: bool = True,
    routes_match: bool = True,
    deterministic: bool = True,
    cpu_fallback_count: int = 0,
    complete_f32_weight_materialized_bytes: int = 0,
) -> dict[str, Any]:
    metrics = compare_vectors(reference, candidate, boundary=boundary)
    greedy_matches = reference_argmax == candidate_argmax
    safety_passed = (
        identity_matches
        and routes_match
        and deterministic
        and cpu_fallback_count == 0
        and complete_f32_weight_materialized_bytes == 0
    )
    if not metrics["numerically_qualified"] or not safety_passed:
        classification = CLASS_NUMERICALLY_FAILED
    elif not greedy_matches:
        classification = CLASS_NUMERICALLY_QUALIFIED_GREEDY_DIVERGENT
    elif metrics["exact_f32_bits"]:
        classification = CLASS_GOLDEN_IDENTICAL
    else:
        classification = CLASS_NUMERICALLY_QUALIFIED_GREEDY_IDENTICAL
    return {
        "contract_version": CONTRACT_VERSION,
        "boundary": boundary,
        "classification": classification,
        **metrics,
        "greedy_matches": greedy_matches,
        "identity_matches": identity_matches,
        "routes_match": routes_match,
        "deterministic": deterministic,
        "cpu_fallback_count": cpu_fallback_count,
        "complete_f32_weight_materialized_bytes": complete_f32_weight_materialized_bytes,
    }


def classify_teacher_forced_positions(
    positions: Sequence[Mapping[str, Any]],
    *,
    boundary: str,
) -> dict[str, Any]:
    if not positions:
        raise ValueError("at least one teacher-forced position is required")
    rows = []
    first_divergence = None
    any_nonexact = False
    any_failed = False
    for expected_position, position in enumerate(positions):
        if position.get("position") != expected_position:
            raise ValueError("teacher-forced positions must be contiguous from zero")
        result = classify_boundary(
            reference=position["reference"],
            candidate=position["candidate"],
            boundary=boundary,
            reference_argmax=position["reference_argmax"],
            candidate_argmax=position["candidate_argmax"],
            identity_matches=position.get("identity_matches", True),
            routes_match=position.get("routes_match", True),
            deterministic=position.get("deterministic", True),
            cpu_fallback_count=position.get("cpu_fallback_count", 0),
            complete_f32_weight_materialized_bytes=position.get(
                "complete_f32_weight_materialized_bytes", 0
            ),
        )
        result["position"] = expected_position
        result["teacher_forced_token"] = position["teacher_forced_token"]
        rows.append(result)
        any_nonexact |= not result["exact_f32_bits"]
        any_failed |= result["classification"] == CLASS_NUMERICALLY_FAILED
        if not result["greedy_matches"] and first_divergence is None:
            first_divergence = expected_position
    if any_failed:
        classification = CLASS_NUMERICALLY_FAILED
    elif first_divergence is not None:
        classification = CLASS_NUMERICALLY_QUALIFIED_GREEDY_DIVERGENT
    elif any_nonexact:
        classification = CLASS_NUMERICALLY_QUALIFIED_GREEDY_IDENTICAL
    else:
        classification = CLASS_GOLDEN_IDENTICAL
    return {
        "contract_version": CONTRACT_VERSION,
        "classification": classification,
        "teacher_forced_continued_after_divergence": first_divergence is not None
        and len(rows) > first_divergence + 1,
        "first_greedy_divergence_position": first_divergence,
        "evaluated_position_count": len(rows),
        "positions": rows,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(contract_manifest(), indent=2, sort_keys=True) + "\n"
    if args.check is None:
        print(rendered, end="")
        return 0
    actual = args.check.read_text()
    if actual != rendered:
        raise SystemExit(f"generated numerical contract differs: {args.check}")
    print(f"Feature 018 numerical contract fixture matches: {args.check}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
