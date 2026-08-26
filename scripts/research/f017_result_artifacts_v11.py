#!/usr/bin/env python3
"""Bounded V11 control artifacts and causal result closure."""
from __future__ import annotations

import hashlib
import heapq
import math
from pathlib import Path
import struct

from f017_bounded_artifact_decode_v1 import ArtifactLimits, parse_artifact_bytes
from f017_canonical_serialization_v10 import bank_exclusive, canonical_bytes
from f017_result_envelope_v11 import PAYLOAD_SPECS, ResultEnvelopeError, iter_payload, validate_payload

CONTROL_LIMITS = ArtifactLimits(
    max_bytes=65_536, max_depth=12, max_object_keys=256,
    max_array_elements=64, max_string_chars=4_096,
    max_integer_digits=32, max_number_chars=128,
)
ROUTING_LIMITS = ArtifactLimits(
    max_bytes=262_144, max_depth=12, max_object_keys=512,
    max_array_elements=256, max_string_chars=4_096,
    max_integer_digits=32, max_number_chars=128,
)


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _validate_sha(value: object, field: str) -> None:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ResultEnvelopeError(field)


def _bounded(value: dict) -> str:
    try:
        raw = canonical_bytes(value)
        parse_artifact_bytes(raw, limits=CONTROL_LIMITS)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ResultEnvelopeError("bounded control artifact") from exc
    return hashlib.sha256(raw).hexdigest()


def build_manifest(role: str, package_attempt_id: str, consumer_event_id: str,
                   payload_records: list[dict]) -> dict:
    if role not in {"PRIMARY", "SECONDARY"} or type(package_attempt_id) is not str or type(consumer_event_id) is not str:
        raise ResultEnvelopeError("manifest identities")
    if type(payload_records) is not list or len(payload_records) != 3:
        raise ResultEnvelopeError("manifest payload census")
    by_kind = {record.get("payload_kind"): record for record in payload_records if type(record) is dict}
    expected = {"final_hidden", "final_normalized", "full_logits"}
    if set(by_kind) != expected or any(record.get("role") != role for record in payload_records):
        raise ResultEnvelopeError("manifest payload identities")
    if any(record.get("package_attempt_id") != package_attempt_id or record.get("consumer_event_id") != consumer_event_id for record in payload_records):
        raise ResultEnvelopeError("manifest payload authority binding")
    if len({record["path_role"] for record in payload_records}) != 3:
        raise ResultEnvelopeError("manifest payload leaf alias")
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-result-manifest/11.0.0",
        "generation": "V11", "role": role,
        "package_attempt_id": package_attempt_id,
        "consumer_event_id": consumer_event_id,
        "payloads": [by_kind[kind] for kind in ("final_hidden", "final_normalized", "full_logits")],
        "payload_count": 3,
        "control_plane_full_logits_json": "PROHIBITED",
    }


def validate_manifest(directory: Path, manifest: dict) -> dict:
    keys = {"schema", "generation", "role", "package_attempt_id", "consumer_event_id",
            "payloads", "payload_count", "control_plane_full_logits_json"}
    if type(manifest) is not dict or set(manifest) != keys:
        raise ResultEnvelopeError("manifest key census")
    role = manifest["role"]
    if (manifest["schema"] != "pulsarmlx.f017.corrected-oracle-result-manifest/11.0.0"
            or manifest["generation"] != "V11" or role not in {"PRIMARY", "SECONDARY"}
            or manifest["payload_count"] != 3
            or manifest["control_plane_full_logits_json"] != "PROHIBITED"):
        raise ResultEnvelopeError("manifest authority")
    payloads = manifest["payloads"]
    if type(payloads) is not list or len(payloads) != 3:
        raise ResultEnvelopeError("manifest payload census")
    expected_order = ["final_hidden", "final_normalized", "full_logits"]
    identities: set[tuple[int, int]] = set()
    for record, kind in zip(payloads, expected_order, strict=True):
        validate_payload(directory, record, expected_spec=PAYLOAD_SPECS[(role, kind)])
        if record["package_attempt_id"] != manifest["package_attempt_id"] or record["consumer_event_id"] != manifest["consumer_event_id"]:
            raise ResultEnvelopeError("manifest payload authority binding")
        try:
            info = (directory / record["path_role"]).lstat()
        except OSError as exc:
            raise ResultEnvelopeError("manifest payload identity") from exc
        identity = (info.st_dev, info.st_ino)
        if identity in identities:
            raise ResultEnvelopeError("manifest payload inode alias")
        identities.add(identity)
    if len({record["path_role"] for record in payloads}) != 3:
        raise ResultEnvelopeError("manifest payload leaf alias")
    if "full_logits" in manifest or any("full_logits" in record and type(record.get("full_logits")) is list for record in payloads):
        raise ResultEnvelopeError("full logits entered control JSON")
    return {"result": "PASS", "manifest_sha256": _bounded(manifest)}


def bank_manifest(path: Path, directory: Path, manifest: dict) -> str:
    validate_manifest(directory, manifest)
    return bank_exclusive(path, manifest)


def build_routing_manifest(role: str, package_attempt_id: str, consumer_event_id: str,
                           layers: list[dict]) -> dict:
    if role not in {"PRIMARY","SECONDARY"} or type(layers) is not list or len(layers) != 79:
        raise ResultEnvelopeError("routing manifest census")
    routes = []
    for expected_layer, layer in enumerate(layers):
        if type(layer) is not dict or type(layer.get("selected_expert_ids")) is not list:
            raise ResultEnvelopeError("routing layer")
        ids = layer["selected_expert_ids"]
        if len(ids) > 8 or any(type(value) is not int or type(value) is bool or value < 0 for value in ids) or len(ids) != len(set(ids)):
            raise ResultEnvelopeError("routing experts")
        routes.append({"layer":expected_layer,"selected_expert_ids":ids})
    value = {"schema":"pulsarmlx.f017.corrected-oracle-routing-manifest/11.0.0","role":role,
             "package_attempt_id":package_attempt_id,"consumer_event_id":consumer_event_id,
             "layer_count":79,"route_membership":"EXACT","route_order":"EXACT","layers":routes}
    validate_routing_manifest(value, expected_role=role, expected_package_attempt_id=package_attempt_id,
                              expected_consumer_event_id=consumer_event_id)
    return value


def validate_routing_manifest(manifest: dict, *, expected_role: str,
                              expected_package_attempt_id: str, expected_consumer_event_id: str) -> dict:
    keys = {"schema","role","package_attempt_id","consumer_event_id","layer_count",
            "route_membership","route_order","layers"}
    if (type(manifest) is not dict or set(manifest) != keys
            or manifest.get("schema") != "pulsarmlx.f017.corrected-oracle-routing-manifest/11.0.0"
            or manifest.get("role") != expected_role
            or manifest.get("package_attempt_id") != expected_package_attempt_id
            or manifest.get("consumer_event_id") != expected_consumer_event_id
            or manifest.get("layer_count") != 79 or manifest.get("route_membership") != "EXACT"
            or manifest.get("route_order") != "EXACT" or type(manifest.get("layers")) is not list
            or len(manifest["layers"]) != 79):
        raise ResultEnvelopeError("routing manifest authority")
    for expected_layer, record in enumerate(manifest["layers"]):
        if type(record) is not dict or set(record) != {"layer","selected_expert_ids"} or record["layer"] != expected_layer:
            raise ResultEnvelopeError("routing layer census")
        ids = record["selected_expert_ids"]
        if type(ids) is not list or len(ids) > 8 or any(type(value) is not int or type(value) is bool or value < 0 for value in ids) or len(ids) != len(set(ids)):
            raise ResultEnvelopeError("routing expert census")
    try:
        raw = canonical_bytes(manifest); parse_artifact_bytes(raw, limits=ROUTING_LIMITS)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ResultEnvelopeError("bounded routing manifest") from exc
    return {"result":"PASS","routing_manifest_sha256":hashlib.sha256(raw).hexdigest()}


def build_top32(directory: Path, logits_record: dict) -> dict:
    role = logits_record.get("role")
    if role not in {"PRIMARY", "SECONDARY"} or logits_record.get("payload_kind") != "full_logits":
        raise ResultEnvelopeError("top32 source")
    heap: list[tuple[float, int]] = []; token = 0
    for chunk in iter_payload(directory, logits_record):
        for value in chunk:
            item = (value, -token)
            if len(heap) < 32: heapq.heappush(heap, item)
            elif item > heap[0]: heapq.heapreplace(heap, item)
            token += 1
    ordered = [(-neg_token, value) for value, neg_token in sorted(heap, reverse=True)]
    code = "d" if role == "PRIMARY" else "f"; bits_key = "logit_f64_bits" if role == "PRIMARY" else "logit_f32_bits"
    summary = {"schema": "pulsarmlx.f017.corrected-oracle-top32-summary/11.0.0", "role": role,
            "package_attempt_id": logits_record["package_attempt_id"],
            "consumer_event_id": logits_record["consumer_event_id"], "top_n": 32,
            "entries": [{"token_id": item[0], bits_key: struct.pack(f"<{code}", item[1]).hex()} for item in ordered],
            "selected_token": ordered[0][0], "top_1_margin": ordered[0][1] - ordered[1][1],
            "logits_payload_sha256": logits_record["sha256"],
            "historical_token_quarantine": "ENFORCED_BY_NUMERICAL_CONTRACT_V3"}
    validate_top32(directory, logits_record, summary)
    return summary


def validate_top32(directory: Path, logits_record: dict, summary: dict) -> dict:
    keys = {"schema","role","package_attempt_id","consumer_event_id","top_n","entries","selected_token","top_1_margin",
            "logits_payload_sha256","historical_token_quarantine"}
    if type(summary) is not dict or set(summary) != keys or summary.get("schema") != "pulsarmlx.f017.corrected-oracle-top32-summary/11.0.0":
        raise ResultEnvelopeError("top32 key census")
    if (summary["role"] != logits_record.get("role") or summary["logits_payload_sha256"] != logits_record.get("sha256")
            or summary["package_attempt_id"] != logits_record.get("package_attempt_id")
            or summary["consumer_event_id"] != logits_record.get("consumer_event_id")):
        raise ResultEnvelopeError("top32 payload binding")
    if summary["historical_token_quarantine"] != "ENFORCED_BY_NUMERICAL_CONTRACT_V3":
        raise ResultEnvelopeError("top32 quarantine")
    # Independently derive the canonical summary without recursive validation.
    heap: list[tuple[float, int]] = []; token = 0
    for chunk in iter_payload(directory, logits_record):
        for value in chunk:
            item = (value, -token)
            if len(heap) < 32: heapq.heappush(heap, item)
            elif item > heap[0]: heapq.heapreplace(heap, item)
            token += 1
    ordered = [(-neg_token, value) for value, neg_token in sorted(heap, reverse=True)]
    code = "d" if summary["role"] == "PRIMARY" else "f"; bits_key = "logit_f64_bits" if summary["role"] == "PRIMARY" else "logit_f32_bits"
    entries = [{"token_id": item[0], bits_key: struct.pack(f"<{code}", item[1]).hex()} for item in ordered]
    if (type(summary["top_n"]) is not int or type(summary["selected_token"]) is not int
            or type(summary["top_1_margin"]) is not float
            or summary["top_n"] != 32 or canonical_bytes(summary["entries"]) != canonical_bytes(entries) or summary["selected_token"] != ordered[0][0]
            or not math.isfinite(summary["top_1_margin"])
            or float(summary["top_1_margin"]) != ordered[0][1] - ordered[1][1]):
        raise ResultEnvelopeError("top32 derivation")
    return {"result":"PASS","summary_sha256":_bounded(summary)}


def build_receipt(role: str, authorization_id: str, package_attempt_id: str, consumer_event_id: str,
                  producer_measurement_sha256: str, numerical_contract_sha256: str,
                  payload_manifest_sha256: str, top32_summary_sha256: str, routing_manifest_sha256: str,
                  durable_start_sha256: str, access_census_sha256: str) -> dict:
    if role not in {"PRIMARY","SECONDARY"} or any(type(value) is not str or not value for value in (authorization_id, package_attempt_id, consumer_event_id)):
        raise ResultEnvelopeError("receipt authority identity")
    for name, value in (("producer", producer_measurement_sha256), ("numerical", numerical_contract_sha256),
                        ("manifest", payload_manifest_sha256), ("summary", top32_summary_sha256), ("routing", routing_manifest_sha256),
                        ("start", durable_start_sha256), ("access", access_census_sha256)):
        _validate_sha(value, name)
    value = {"schema": "pulsarmlx.f017.corrected-oracle-result-receipt/11.0.0",
            "role": role, "authorization_id": authorization_id, "package_attempt_id": package_attempt_id,
            "consumer_event_id": consumer_event_id, "producer_measurement_sha256": producer_measurement_sha256,
            "numerical_contract_sha256": numerical_contract_sha256,
            "payload_manifest_sha256": payload_manifest_sha256, "top32_summary_sha256": top32_summary_sha256,
            "routing_manifest_sha256": routing_manifest_sha256,
            "durable_start_sha256": durable_start_sha256, "access_census_sha256": access_census_sha256,
            "result_state": "COMPLETE"}
    _bounded(value); return value


def validate_receipt(receipt: dict, *, expected_role: str, expected_manifest_sha256: str,
                     expected_summary_sha256: str, expected_routing_manifest_sha256: str,
                     expected_authorization_id: str, expected_package_attempt_id: str,
                     expected_consumer_event_id: str) -> dict:
    keys = {"schema","role","authorization_id","package_attempt_id","consumer_event_id",
            "producer_measurement_sha256","numerical_contract_sha256","payload_manifest_sha256",
            "top32_summary_sha256","routing_manifest_sha256","durable_start_sha256","access_census_sha256","result_state"}
    if (type(receipt) is not dict or set(receipt) != keys
            or receipt.get("schema") != "pulsarmlx.f017.corrected-oracle-result-receipt/11.0.0"
            or receipt.get("role") != expected_role or receipt.get("result_state") != "COMPLETE"
            or receipt.get("authorization_id") != expected_authorization_id
            or receipt.get("package_attempt_id") != expected_package_attempt_id
            or receipt.get("consumer_event_id") != expected_consumer_event_id
            or receipt.get("payload_manifest_sha256") != expected_manifest_sha256
            or receipt.get("top32_summary_sha256") != expected_summary_sha256
            or receipt.get("routing_manifest_sha256") != expected_routing_manifest_sha256):
        raise ResultEnvelopeError("result receipt")
    for field in ("producer_measurement_sha256","numerical_contract_sha256","payload_manifest_sha256",
                  "top32_summary_sha256","routing_manifest_sha256","durable_start_sha256","access_census_sha256"):
        _validate_sha(receipt[field], field)
    return {"result":"PASS","receipt_sha256":_bounded(receipt)}


def build_result_terminal(role: str, receipt_sha256: str, manifest_sha256: str) -> dict:
    _validate_sha(receipt_sha256, "receipt SHA"); _validate_sha(manifest_sha256, "manifest SHA")
    value = {"schema": "pulsarmlx.f017.corrected-oracle-result-terminal/11.0.0",
            "role": role, "result": "COMPLETE", "result_receipt_sha256": receipt_sha256,
            "payload_manifest_sha256": manifest_sha256}
    _bounded(value); return value


def validate_result_terminal(terminal: dict, *, expected_role: str, expected_receipt_sha256: str,
                             expected_manifest_sha256: str) -> dict:
    keys = {"schema","role","result","result_receipt_sha256","payload_manifest_sha256"}
    if (type(terminal) is not dict or set(terminal) != keys
            or terminal.get("schema") != "pulsarmlx.f017.corrected-oracle-result-terminal/11.0.0"
            or terminal.get("role") != expected_role or terminal.get("result") != "COMPLETE"
            or terminal.get("result_receipt_sha256") != expected_receipt_sha256
            or terminal.get("payload_manifest_sha256") != expected_manifest_sha256):
        raise ResultEnvelopeError("result terminal")
    return {"result":"PASS","result_terminal_sha256":_bounded(terminal)}


def build_consumer_terminal(role: str, result_terminal_sha256: str, receipt_sha256: str, manifest_sha256: str) -> dict:
    for value in (result_terminal_sha256, receipt_sha256, manifest_sha256): _validate_sha(value, "terminal SHA")
    terminal = {"schema": "pulsarmlx.f017.corrected-oracle-consumer-terminal/11.0.0",
            "role": role, "result": "COMPLETE", "result_terminal_sha256": result_terminal_sha256,
            "result_receipt_sha256": receipt_sha256, "payload_manifest_sha256": manifest_sha256,
            "secondary_eligible": role == "PRIMARY"}
    _bounded(terminal); return terminal


def validate_consumer_terminal(terminal: dict, *, expected_role: str, expected_result_terminal_sha256: str,
                               expected_receipt_sha256: str, expected_manifest_sha256: str) -> dict:
    keys = {"schema","role","result","result_terminal_sha256","result_receipt_sha256",
            "payload_manifest_sha256","secondary_eligible"}
    if (type(terminal) is not dict or set(terminal) != keys
            or terminal.get("schema") != "pulsarmlx.f017.corrected-oracle-consumer-terminal/11.0.0"
            or terminal.get("role") != expected_role or terminal.get("result") != "COMPLETE"
            or terminal.get("result_terminal_sha256") != expected_result_terminal_sha256
            or terminal.get("result_receipt_sha256") != expected_receipt_sha256
            or terminal.get("payload_manifest_sha256") != expected_manifest_sha256
            or terminal.get("secondary_eligible") is not (expected_role == "PRIMARY")):
        raise ResultEnvelopeError("consumer terminal")
    return {"result":"PASS","consumer_terminal_sha256":_bounded(terminal)}


def require_primary_terminal(terminal: dict, expected_result_terminal_sha256: str,
                             expected_receipt_sha256: str, expected_manifest_sha256: str) -> None:
    keys = {"schema", "role", "result", "result_terminal_sha256", "result_receipt_sha256", "payload_manifest_sha256", "secondary_eligible"}
    if (type(terminal) is not dict or set(terminal) != keys
            or terminal["schema"] != "pulsarmlx.f017.corrected-oracle-consumer-terminal/11.0.0"
            or terminal["role"] != "PRIMARY" or terminal["result"] != "COMPLETE"
            or terminal["secondary_eligible"] is not True
            or terminal["result_terminal_sha256"] != expected_result_terminal_sha256
            or terminal["result_receipt_sha256"] != expected_receipt_sha256
            or terminal["payload_manifest_sha256"] != expected_manifest_sha256):
        raise ResultEnvelopeError("primary terminal prerequisite")


def closure_root(primary_manifest: dict, primary_receipt: dict, primary_terminal: dict,
                 secondary_manifest: dict, secondary_receipt: dict, secondary_terminal: dict,
                 primary_result_terminal_sha256: str, secondary_result_terminal_sha256: str,
                 comparison_summary_sha256: str, comparison_receipt_sha256: str,
                 comparison_terminal_sha256: str, release_start_sha256: str,
                 release_report_sha256: str, release_receipt_sha256: str, release_terminal_sha256: str,
                 package_receipt_sha256: str) -> dict:
    for field in (primary_result_terminal_sha256, secondary_result_terminal_sha256,
                  comparison_summary_sha256, comparison_receipt_sha256, comparison_terminal_sha256,
                  release_start_sha256, release_report_sha256, release_receipt_sha256,
                  release_terminal_sha256, package_receipt_sha256):
        _validate_sha(field, "closure SHA")
    value = {"schema": "pulsarmlx.f017.corrected-oracle-package-result-closure/11.0.0",
            "primary": {"manifest_sha256": _sha(primary_manifest), "receipt_sha256": _sha(primary_receipt),
                        "terminal_sha256": _sha(primary_terminal),
                        "result_terminal_sha256": primary_result_terminal_sha256,
                        "routing_manifest_sha256": primary_receipt["routing_manifest_sha256"],
                        "payload_sha256s": [record["sha256"] for record in primary_manifest["payloads"]]},
            "secondary": {"manifest_sha256": _sha(secondary_manifest), "receipt_sha256": _sha(secondary_receipt),
                          "terminal_sha256": _sha(secondary_terminal),
                          "result_terminal_sha256": secondary_result_terminal_sha256,
                          "routing_manifest_sha256": secondary_receipt["routing_manifest_sha256"],
                          "payload_sha256s": [record["sha256"] for record in secondary_manifest["payloads"]]},
            "comparison": {"summary_sha256":comparison_summary_sha256,
                           "receipt_sha256":comparison_receipt_sha256,
                           "terminal_sha256":comparison_terminal_sha256},
            "release": {"start_sha256":release_start_sha256,"report_sha256":release_report_sha256,
                        "receipt_sha256":release_receipt_sha256,"terminal_sha256":release_terminal_sha256},
            "package_receipt_sha256": package_receipt_sha256,
            "payload_count": 6, "result": "COMPLETE"}
    _bounded(value); return value


def validate_closure_root(closure: dict, primary_manifest: dict, primary_receipt: dict, primary_terminal: dict,
                          secondary_manifest: dict, secondary_receipt: dict, secondary_terminal: dict,
                          primary_result_terminal_sha256: str, secondary_result_terminal_sha256: str,
                          comparison_summary_sha256: str, comparison_receipt_sha256: str,
                          comparison_terminal_sha256: str, release_start_sha256: str,
                          release_report_sha256: str, release_receipt_sha256: str,
                          release_terminal_sha256: str, package_receipt_sha256: str) -> dict:
    expected = closure_root(primary_manifest, primary_receipt, primary_terminal,
        secondary_manifest, secondary_receipt, secondary_terminal,
        primary_result_terminal_sha256, secondary_result_terminal_sha256,
        comparison_summary_sha256, comparison_receipt_sha256, comparison_terminal_sha256,
        release_start_sha256, release_report_sha256, release_receipt_sha256,
        release_terminal_sha256, package_receipt_sha256)
    if type(closure) is not dict or closure != expected:
        raise ResultEnvelopeError("package result closure")
    return {"result":"PASS","closure_sha256":_bounded(closure)}
