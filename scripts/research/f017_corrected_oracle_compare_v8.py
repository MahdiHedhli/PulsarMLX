#!/usr/bin/env python3
"""Frozen V8 offline comparison over complete synthetic logits."""
from __future__ import annotations

import math


MAX_ABS = 0.0065169706285814755
RMSE_MAX = 0.003463567697419031
COSINE_MIN = 0.9999999985448085


def compare(primary: dict, secondary: dict) -> dict:
    left = primary["result"]["full_logits"]
    right = secondary["result"]["full_logits"]
    if len(left) != len(right) or not left:
        raise ValueError("complete-logit census")
    differences = [abs(float(a) - float(b)) for a, b in zip(left, right, strict=True)]
    max_abs = max(differences)
    rmse = math.sqrt(sum(value * value for value in differences) / len(differences))
    dot = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
    norm_left = math.sqrt(sum(float(a) * float(a) for a in left))
    norm_right = math.sqrt(sum(float(b) * float(b) for b in right))
    cosine = dot / (norm_left * norm_right)
    routes_equal = all(a["selected_expert_ids"] == b["selected_expert_ids"] for a, b in zip(primary["result"]["layers"], secondary["result"]["layers"], strict=True))
    tokens_equal = primary["result"]["selected_token"] == secondary["result"]["selected_token"]
    within = max_abs <= MAX_ABS and rmse <= RMSE_MAX and cosine >= COSINE_MIN
    classification = "EXACT_EXPECTED_TOKEN_STABLE" if routes_equal and tokens_equal and within else "ORACLE_DISAGREEMENT"
    return {"classification": classification, "route_structure_equal": routes_equal, "selected_tokens_equal": tokens_equal, "max_absolute_error": max_abs, "rmse": rmse, "cosine_similarity": cosine, "frozen_thresholds": {"max_absolute_error": MAX_ABS, "rmse": RMSE_MAX, "cosine_minimum": COSINE_MIN, "top_n": 32}}
