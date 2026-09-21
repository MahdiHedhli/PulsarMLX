#!/usr/bin/env python3
"""Streaming comparison for canonical V11 binary result payloads."""
from __future__ import annotations

import heapq
import hashlib
import math
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
from f017_result_artifacts_v11 import validate_routing_manifest
from f017_result_envelope_v11 import iter_payload, ResultEnvelopeError, TOP_N
from f017_binary_comparison_authority_v11 import validate_summary as validate_authoritative_summary

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
                   primary_routing_manifest: dict, secondary_routing_manifest: dict,
                   primary_manifest: dict, secondary_manifest: dict,
                   primary_top32: dict, secondary_top32: dict,
                   primary_receipt: dict, secondary_receipt: dict, authorization_id: str,
                   *, chunk_elements: int = 4_096) -> dict:
    if primary_record.get("role") != "PRIMARY" or primary_record.get("payload_kind") != "full_logits":
        raise ResultEnvelopeError("primary comparison payload")
    if secondary_record.get("role") != "SECONDARY" or secondary_record.get("payload_kind") != "full_logits":
        raise ResultEnvelopeError("secondary comparison payload")
    if primary_record.get("package_attempt_id") != secondary_record.get("package_attempt_id"):
        raise ResultEnvelopeError("comparison package identity")
    primary_route = validate_routing_manifest(primary_routing_manifest, expected_role="PRIMARY",
        expected_package_attempt_id=primary_record["package_attempt_id"], expected_consumer_event_id=primary_record["consumer_event_id"])
    secondary_route = validate_routing_manifest(secondary_routing_manifest, expected_role="SECONDARY",
        expected_package_attempt_id=secondary_record["package_attempt_id"], expected_consumer_event_id=secondary_record["consumer_event_id"])
    route_structure_equal = [item["selected_expert_ids"] for item in primary_routing_manifest["layers"]] == [item["selected_expert_ids"] for item in secondary_routing_manifest["layers"]]
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
    primary_margin = p_order[0][1] - p_order[1][1]
    secondary_margin = s_order[0][1] - s_order[1][1]
    margin_requirement = 2.0 * MAX_ABS_LIMIT
    margin_stable = min(primary_margin, secondary_margin) > margin_requirement
    thresholds_pass = maximum <= MAX_ABS_LIMIT and rmse <= RMSE_LIMIT and cosine >= COSINE_MINIMUM
    if not route_structure_equal or not thresholds_pass:
        classification = "ORACLE_DISAGREEMENT"
    elif top1_equal and margin_stable:
        classification = "EXACT_EXPECTED_TOKEN_STABLE"
    elif top_ids_equal:
        classification = "NUMERICALLY_STABLE_TOP_K_ONLY"
    else:
        classification = "TOP1_UNSTABLE_WITHIN_FROZEN_UNCERTAINTY"
    result = {
        "schema": "pulsarmlx.f017.corrected-oracle-binary-comparison-summary/11.0.0",
        "authorization_id": authorization_id,
        "package_attempt_id": primary_record["package_attempt_id"],
        "primary_payload_manifest_sha256": hashlib.sha256(canonical_bytes(primary_manifest)).hexdigest(),
        "secondary_payload_manifest_sha256": hashlib.sha256(canonical_bytes(secondary_manifest)).hexdigest(),
        "primary_top32_summary_sha256": hashlib.sha256(canonical_bytes(primary_top32)).hexdigest(),
        "secondary_top32_summary_sha256": hashlib.sha256(canonical_bytes(secondary_top32)).hexdigest(),
        "primary_logits_payload_sha256": primary_record["sha256"],
        "secondary_logits_payload_sha256": secondary_record["sha256"],
        "primary_routing_manifest_sha256": primary_route["routing_manifest_sha256"],
        "secondary_routing_manifest_sha256": secondary_route["routing_manifest_sha256"],
        "element_count": count,
        "max_absolute_error": maximum,
        "rmse": rmse,
        "cosine_similarity": cosine,
        "thresholds": {"max_absolute_error": MAX_ABS_LIMIT, "rmse": RMSE_LIMIT, "cosine_minimum": COSINE_MINIMUM},
        "primary_top32_ids": [item[0] for item in p_order],
        "secondary_top32_ids": [item[0] for item in s_order],
        "primary_selected_token": p_order[0][0],
        "secondary_selected_token": s_order[0][0],
        "primary_top_1_margin": primary_margin,
        "secondary_top_1_margin": secondary_margin,
        "frozen_margin_requirement": margin_requirement,
        "margin_stable": margin_stable,
        "route_structure_equal": route_structure_equal,
        "top32_order_equal": top_ids_equal,
        "top1_stable": top1_equal,
        "classification": classification,
    }
    validate_comparison_summary(result, primary_dir, primary_record, secondary_dir, secondary_record,
                                primary_routing_manifest, secondary_routing_manifest,
                                primary_manifest, secondary_manifest, primary_top32, secondary_top32,
                                primary_receipt, secondary_receipt, authorization_id, chunk_elements=chunk_elements)
    return result


def validate_comparison_summary(summary: dict, primary_dir: Path, primary_record: dict,
                                secondary_dir: Path, secondary_record: dict,
                                primary_routing_manifest: dict, secondary_routing_manifest: dict,
                                primary_manifest: dict, secondary_manifest: dict,
                                primary_top32: dict, secondary_top32: dict,
                                primary_receipt: dict, secondary_receipt: dict, authorization_id: str,
                                *, chunk_elements: int = 4_096) -> dict:
    return validate_authoritative_summary(summary, primary_dir, primary_record, secondary_dir,
        secondary_record, primary_routing_manifest, secondary_routing_manifest,
        primary_manifest, secondary_manifest, primary_top32, secondary_top32,
        primary_receipt, secondary_receipt, authorization_id, chunk_elements=chunk_elements)
