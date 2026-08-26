#!/usr/bin/env python3
"""Streaming comparison for canonical V11 binary result payloads."""
from __future__ import annotations

import heapq
import math
from pathlib import Path

from f017_result_envelope_v11 import iter_payload, ResultEnvelopeError, TOP_N

MAX_ABS_LIMIT = 0.0065169706285814755
RMSE_LIMIT = 0.003463567697419031
COSINE_MINIMUM = 0.9999999985448085


def _push(heap: list[tuple[float, int]], value: float, token: int) -> None:
    item = (value, -token)
    if len(heap) < TOP_N:
        heapq.heappush(heap, item)
    elif item > heap[0]:
        heapq.heapreplace(heap, item)


def compare_logits(primary_dir: Path, primary_record: dict, secondary_dir: Path, secondary_record: dict,
                   *, chunk_elements: int = 4_096) -> dict:
    if primary_record.get("role") != "PRIMARY" or primary_record.get("payload_kind") != "full_logits":
        raise ResultEnvelopeError("primary comparison payload")
    if secondary_record.get("role") != "SECONDARY" or secondary_record.get("payload_kind") != "full_logits":
        raise ResultEnvelopeError("secondary comparison payload")
    maximum = 0.0; square_sum = 0.0; dot = 0.0; norm_p = 0.0; norm_s = 0.0
    primary_top: list[tuple[float, int]] = []; secondary_top: list[tuple[float, int]] = []
    count = 0
    primary_iter = iter_payload(primary_dir, primary_record, chunk_elements=chunk_elements)
    secondary_iter = iter_payload(secondary_dir, secondary_record, chunk_elements=chunk_elements)
    for p_chunk, s_chunk in zip(primary_iter, secondary_iter, strict=True):
        if len(p_chunk) != len(s_chunk): raise ResultEnvelopeError("comparison chunk geometry")
        for p_value, s_value in zip(p_chunk, s_chunk, strict=True):
            difference = abs(p_value - s_value)
            maximum = max(maximum, difference); square_sum += difference * difference
            dot += p_value * s_value; norm_p += p_value * p_value; norm_s += s_value * s_value
            _push(primary_top, p_value, count); _push(secondary_top, s_value, count); count += 1
    if count != primary_record["element_count"] or count != secondary_record["element_count"]:
        raise ResultEnvelopeError("comparison element census")
    rmse = math.sqrt(square_sum / count)
    cosine = dot / math.sqrt(norm_p * norm_s) if norm_p and norm_s else (1.0 if norm_p == norm_s else 0.0)
    p_order = [(-token, value) for value, token in sorted(primary_top, reverse=True)]
    s_order = [(-token, value) for value, token in sorted(secondary_top, reverse=True)]
    top_ids_equal = [item[0] for item in p_order] == [item[0] for item in s_order]
    top1_equal = p_order[0][0] == s_order[0][0]
    thresholds_pass = maximum <= MAX_ABS_LIMIT and rmse <= RMSE_LIMIT and cosine >= COSINE_MINIMUM
    classification = ("EXACT_EXPECTED_TOKEN_STABLE" if thresholds_pass and top_ids_equal and top1_equal
                      else "NUMERICALLY_STABLE_TOP_K_ONLY" if thresholds_pass and top1_equal
                      else "TOP1_UNSTABLE_WITHIN_FROZEN_UNCERTAINTY" if thresholds_pass
                      else "ORACLE_DISAGREEMENT")
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-binary-comparison-summary/11.0.0",
        "element_count": count,
        "max_absolute_error": maximum,
        "rmse": rmse,
        "cosine_similarity": cosine,
        "thresholds": {"max_absolute_error": MAX_ABS_LIMIT, "rmse": RMSE_LIMIT, "cosine_minimum": COSINE_MINIMUM},
        "primary_top32_ids": [item[0] for item in p_order],
        "secondary_top32_ids": [item[0] for item in s_order],
        "top32_order_equal": top_ids_equal,
        "top1_stable": top1_equal,
        "classification": classification,
    }
