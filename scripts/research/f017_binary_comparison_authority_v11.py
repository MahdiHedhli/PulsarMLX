#!/usr/bin/env python3
"""Independent V11 comparison authority; does not import the comparison builder."""
from __future__ import annotations

import hashlib
import heapq
import math
from pathlib import Path

from f017_bounded_artifact_decode_v1 import ArtifactLimits, parse_artifact_bytes
from f017_canonical_serialization_v10 import canonical_bytes
from f017_result_artifacts_v11 import (validate_manifest, validate_receipt,
    validate_routing_manifest, validate_top32)
from f017_result_envelope_v11 import iter_payload, ResultEnvelopeError, TOP_N

MAX_ABS_LIMIT = 0.0065169706285814755
RMSE_LIMIT = 0.003463567697419031
COSINE_MINIMUM = 0.9999999985448085
LIMITS = ArtifactLimits(max_bytes=65_536, max_depth=8, max_object_keys=64,
                        max_array_elements=64, max_string_chars=4_096,
                        max_integer_digits=32, max_number_chars=128)


def _top_push(heap: list[tuple[float, int]], value: float, token: int) -> None:
    item = (value, -token)
    if len(heap) < TOP_N:
        heapq.heappush(heap, item)
    elif item > heap[0]:
        heapq.heapreplace(heap, item)


def _sha(value: dict) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _bundle_identity(directory: Path, role: str, record: dict, manifest: dict,
                     top32: dict, routing: dict, receipt: dict,
                     authorization_id: str) -> tuple[str, str, str]:
    validate_manifest(directory, manifest)
    if canonical_bytes(record) != canonical_bytes(manifest["payloads"][2]):
        raise ResultEnvelopeError("comparison payload is not receipt manifest logits")
    validate_top32(directory, record, top32)
    routing_result = validate_routing_manifest(routing, expected_role=role,
        expected_package_attempt_id=record["package_attempt_id"], expected_consumer_event_id=record["consumer_event_id"])
    manifest_sha = _sha(manifest); top32_sha = _sha(top32); routing_sha = routing_result["routing_manifest_sha256"]
    validate_receipt(receipt, expected_role=role, expected_manifest_sha256=manifest_sha,
        expected_summary_sha256=top32_sha, expected_routing_manifest_sha256=routing_sha,
        expected_authorization_id=authorization_id, expected_package_attempt_id=record["package_attempt_id"],
        expected_consumer_event_id=record["consumer_event_id"])
    return manifest_sha, top32_sha, routing_sha


def derive_summary(primary_dir: Path, primary_record: dict, secondary_dir: Path,
                   secondary_record: dict, primary_routing: dict, secondary_routing: dict,
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
    pm_sha, pt_sha, pr_sha = _bundle_identity(primary_dir, "PRIMARY", primary_record, primary_manifest,
        primary_top32, primary_routing, primary_receipt, authorization_id)
    sm_sha, st_sha, sr_sha = _bundle_identity(secondary_dir, "SECONDARY", secondary_record, secondary_manifest,
        secondary_top32, secondary_routing, secondary_receipt, authorization_id)
    maximum = square_sum = dot = norm_p = norm_s = 0.0
    primary_top: list[tuple[float, int]] = []; secondary_top: list[tuple[float, int]] = []
    count = 0
    for left, right in zip(iter_payload(primary_dir, primary_record, chunk_elements=chunk_elements),
                           iter_payload(secondary_dir, secondary_record, chunk_elements=chunk_elements), strict=True):
        for p_value, s_value in zip(left, right, strict=True):
            difference = abs(p_value - s_value)
            maximum = max(maximum, difference); square_sum += difference * difference
            dot += p_value * s_value; norm_p += p_value * p_value; norm_s += s_value * s_value
            _top_push(primary_top, p_value, count); _top_push(secondary_top, s_value, count); count += 1
    if count != primary_record["element_count"] or count != secondary_record["element_count"]:
        raise ResultEnvelopeError("comparison element census")
    rmse = math.sqrt(square_sum / count)
    cosine = dot / math.sqrt(norm_p * norm_s) if norm_p and norm_s else (1.0 if norm_p == norm_s else 0.0)
    p_order = [(-token, value) for value, token in sorted(primary_top, reverse=True)]
    s_order = [(-token, value) for value, token in sorted(secondary_top, reverse=True)]
    routes_equal = [x["selected_expert_ids"] for x in primary_routing["layers"]] == [x["selected_expert_ids"] for x in secondary_routing["layers"]]
    top_equal = [x[0] for x in p_order] == [x[0] for x in s_order]
    top1_equal = p_order[0][0] == s_order[0][0]
    p_margin = p_order[0][1] - p_order[1][1]; s_margin = s_order[0][1] - s_order[1][1]
    margin_requirement = 2.0 * MAX_ABS_LIMIT; margin_stable = min(p_margin, s_margin) > margin_requirement
    thresholds_pass = maximum <= MAX_ABS_LIMIT and rmse <= RMSE_LIMIT and cosine >= COSINE_MINIMUM
    classification = ("ORACLE_DISAGREEMENT" if not routes_equal or not thresholds_pass else
        "EXACT_EXPECTED_TOKEN_STABLE" if top1_equal and margin_stable else
        "NUMERICALLY_STABLE_TOP_K_ONLY" if top_equal else "TOP1_UNSTABLE_WITHIN_FROZEN_UNCERTAINTY")
    return {"schema":"pulsarmlx.f017.corrected-oracle-binary-comparison-summary/11.0.0",
        "authorization_id":authorization_id,
        "package_attempt_id":primary_record["package_attempt_id"],
        "primary_payload_manifest_sha256":pm_sha,"secondary_payload_manifest_sha256":sm_sha,
        "primary_top32_summary_sha256":pt_sha,"secondary_top32_summary_sha256":st_sha,
        "primary_logits_payload_sha256":primary_record["sha256"],"secondary_logits_payload_sha256":secondary_record["sha256"],
        "primary_routing_manifest_sha256":pr_sha,"secondary_routing_manifest_sha256":sr_sha,
        "element_count":count,"max_absolute_error":maximum,"rmse":rmse,"cosine_similarity":cosine,
        "thresholds":{"max_absolute_error":MAX_ABS_LIMIT,"rmse":RMSE_LIMIT,"cosine_minimum":COSINE_MINIMUM},
        "primary_top32_ids":[x[0] for x in p_order],"secondary_top32_ids":[x[0] for x in s_order],
        "primary_selected_token":p_order[0][0],"secondary_selected_token":s_order[0][0],
        "primary_top_1_margin":p_margin,"secondary_top_1_margin":s_margin,
        "frozen_margin_requirement":margin_requirement,"margin_stable":margin_stable,
        "route_structure_equal":routes_equal,"top32_order_equal":top_equal,"top1_stable":top1_equal,
        "classification":classification}


def validate_summary(summary: dict, primary_dir: Path, primary_record: dict,
                     secondary_dir: Path, secondary_record: dict, primary_routing: dict,
                     secondary_routing: dict, primary_manifest: dict, secondary_manifest: dict,
                     primary_top32: dict, secondary_top32: dict, primary_receipt: dict,
                     secondary_receipt: dict, authorization_id: str,
                     *, chunk_elements: int = 4_096) -> dict:
    expected = derive_summary(primary_dir, primary_record, secondary_dir, secondary_record,
        primary_routing, secondary_routing, primary_manifest, secondary_manifest,
        primary_top32, secondary_top32, primary_receipt, secondary_receipt, authorization_id,
        chunk_elements=chunk_elements)
    if type(summary) is not dict or canonical_bytes(summary) != canonical_bytes(expected):
        raise ResultEnvelopeError("independent comparison summary mismatch")
    try:
        raw = canonical_bytes(summary); parse_artifact_bytes(raw, limits=LIMITS)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ResultEnvelopeError("bounded comparison summary") from exc
    return {"result":"PASS","comparison_summary_sha256":hashlib.sha256(raw).hexdigest()}
