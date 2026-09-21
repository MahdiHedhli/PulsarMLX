#!/usr/bin/env python3
"""Frozen offline comparison for terminal V6 corrected-oracle results."""
from __future__ import annotations

import math
from typing import Any

from f017_corrected_oracle_authorization_v6 import decode_canonical_floats

MAX_ABS = 0.0065169706285814755
RMSE_MAX = 0.003463567697419031
COSINE_MIN = 0.9999999985448085
TOP_N = 32


def _number(value: Any) -> float:
    if type(value) in {int, float}:
        result = float(value)
    else:
        result = decode_canonical_floats(value)
        if type(result) is not float:
            raise ValueError("canonical numerical scalar required")
    if not math.isfinite(result):
        raise ValueError("finite numerical scalar required")
    return result


def _token(result: dict[str, Any]) -> int:
    for key in ("selected_token", "token"):
        if type(result.get(key)) is int:
            return result[key]
    raise ValueError("selected token missing")


def _routes(result: dict[str, Any]) -> list[Any]:
    routes = []
    for layer in result.get("layers", []):
        routes.append(layer.get("selected_expert_ids", layer.get("selected_experts")))
    return routes


def compare(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    left = primary.get("full_logits")
    right = secondary.get("full_logits")
    if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right) or not left:
        raise ValueError("complete matching logits required")
    if not all(math.isfinite(_number(value)) for value in [*left, *right]):
        raise ValueError("finite complete logits required")
    diffs = [abs(_number(a) - _number(b)) for a, b in zip(left, right, strict=True)]
    max_abs = max(diffs)
    rmse = math.sqrt(sum(value * value for value in diffs) / len(diffs))
    dot = sum(_number(a) * _number(b) for a, b in zip(left, right, strict=True))
    norm_left = math.sqrt(sum(_number(value) ** 2 for value in left))
    norm_right = math.sqrt(sum(_number(value) ** 2 for value in right))
    cosine = dot / (norm_left * norm_right) if norm_left and norm_right else 1.0 if left == right else 0.0
    route_match = _routes(primary) == _routes(secondary)
    primary_token = _token(primary)
    secondary_token = _token(secondary)
    primary_top = sorted(range(len(left)), key=lambda index: (-_number(left[index]), index))[:TOP_N]
    secondary_top = sorted(range(len(right)), key=lambda index: (-_number(right[index]), index))[:TOP_N]
    primary_margin = _number(primary.get("top_1_margin", _number(left[primary_top[0]]) - _number(left[primary_top[1]])))
    secondary_margin = _number(secondary.get("top_1_margin", _number(right[secondary_top[0]]) - _number(right[secondary_top[1]])))
    margin_requirement = 2.0 * MAX_ABS
    bounds = max_abs <= MAX_ABS and rmse <= RMSE_MAX and cosine >= COSINE_MIN
    if not route_match or not bounds:
        classification = "ORACLE_DISAGREEMENT"
    elif primary_token == secondary_token and min(primary_margin, secondary_margin) > margin_requirement:
        classification = "EXACT_EXPECTED_TOKEN_STABLE"
    elif primary_top == secondary_top:
        classification = "NUMERICALLY_STABLE_TOP_K_ONLY"
    else:
        classification = "TOP1_UNSTABLE_WITHIN_FROZEN_UNCERTAINTY"
    return {
        "classification": classification,
        "route_structure": "MATCH" if route_match else "MISMATCH",
        "max_absolute_error": max_abs,
        "rmse": rmse,
        "cosine_similarity": cosine,
        "primary_selected_token": primary_token,
        "secondary_selected_token": secondary_token,
        "primary_top_32": primary_top,
        "secondary_top_32": secondary_top,
        "top_32_relationship": "EXACT_ORDER" if primary_top == secondary_top else "DIFFERENT",
        "primary_top_1_margin": primary_margin,
        "secondary_top_1_margin": secondary_margin,
        "frozen_margin_requirement": margin_requirement,
        "margin_stable": min(primary_margin, secondary_margin) > margin_requirement,
        "thresholds": {"max_absolute_error": MAX_ABS, "rmse": RMSE_MAX, "minimum_cosine_similarity": COSINE_MIN, "top_n": TOP_N},
    }
