#!/usr/bin/env python3
"""Bounded V11 control artifacts and causal result closure."""
from __future__ import annotations

import hashlib
from pathlib import Path

from f017_bounded_artifact_decode_v1 import ArtifactLimits, parse_artifact_bytes
from f017_canonical_serialization_v10 import bank_exclusive, canonical_bytes
from f017_result_envelope_v11 import PAYLOAD_SPECS, ResultEnvelopeError, validate_payload

CONTROL_LIMITS = ArtifactLimits(
    max_bytes=65_536, max_depth=12, max_object_keys=256,
    max_array_elements=64, max_string_chars=4_096,
    max_integer_digits=32, max_number_chars=128,
)


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _validate_sha(value: object, field: str) -> None:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ResultEnvelopeError(field)


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
    for record, kind in zip(payloads, expected_order, strict=True):
        validate_payload(directory, record, expected_spec=PAYLOAD_SPECS[(role, kind)])
    if "full_logits" in manifest or any("full_logits" in record and type(record.get("full_logits")) is list for record in payloads):
        raise ResultEnvelopeError("full logits entered control JSON")
    raw = canonical_bytes(manifest)
    parse_artifact_bytes(raw, limits=CONTROL_LIMITS)
    return {"result": "PASS", "manifest_sha256": hashlib.sha256(raw).hexdigest()}


def bank_manifest(path: Path, directory: Path, manifest: dict) -> str:
    validate_manifest(directory, manifest)
    return bank_exclusive(path, manifest)


def build_top32(role: str, event_id: str, entries: list[dict], selected_token: int,
                top1_margin: float, logits_payload_sha256: str) -> dict:
    if role not in {"PRIMARY", "SECONDARY"} or type(entries) is not list or len(entries) != 32:
        raise ResultEnvelopeError("top32 census")
    expected_bits = "logit_f64_bits" if role == "PRIMARY" else "logit_f32_bits"
    seen: set[int] = set()
    for entry in entries:
        if type(entry) is not dict or set(entry) != {"token_id", expected_bits}:
            raise ResultEnvelopeError("top32 entry")
        if type(entry["token_id"]) is not int or type(entry["token_id"]) is bool or entry["token_id"] in seen:
            raise ResultEnvelopeError("top32 token")
        seen.add(entry["token_id"])
        if type(entry[expected_bits]) is not str or len(entry[expected_bits]) != (16 if role == "PRIMARY" else 8):
            raise ResultEnvelopeError("top32 bits")
    _validate_sha(logits_payload_sha256, "logits payload SHA")
    return {"schema": "pulsarmlx.f017.corrected-oracle-top32-summary/11.0.0", "role": role,
            "consumer_event_id": event_id, "top_n": 32, "entries": entries,
            "selected_token": selected_token, "top_1_margin": top1_margin,
            "logits_payload_sha256": logits_payload_sha256,
            "historical_token_quarantine": [21615, 17351, 154820]}


def build_receipt(role: str, authorization_id: str, package_attempt_id: str, consumer_event_id: str,
                  producer_measurement_sha256: str, numerical_contract_sha256: str,
                  payload_manifest_sha256: str, top32_summary_sha256: str,
                  durable_start_sha256: str, access_census_sha256: str) -> dict:
    for name, value in (("producer", producer_measurement_sha256), ("numerical", numerical_contract_sha256),
                        ("manifest", payload_manifest_sha256), ("summary", top32_summary_sha256),
                        ("start", durable_start_sha256), ("access", access_census_sha256)):
        _validate_sha(value, name)
    return {"schema": "pulsarmlx.f017.corrected-oracle-result-receipt/11.0.0",
            "role": role, "authorization_id": authorization_id, "package_attempt_id": package_attempt_id,
            "consumer_event_id": consumer_event_id, "producer_measurement_sha256": producer_measurement_sha256,
            "numerical_contract_sha256": numerical_contract_sha256,
            "payload_manifest_sha256": payload_manifest_sha256, "top32_summary_sha256": top32_summary_sha256,
            "durable_start_sha256": durable_start_sha256, "access_census_sha256": access_census_sha256,
            "result_state": "COMPLETE"}


def build_terminal(role: str, receipt_sha256: str, manifest_sha256: str) -> dict:
    _validate_sha(receipt_sha256, "receipt SHA"); _validate_sha(manifest_sha256, "manifest SHA")
    return {"schema": "pulsarmlx.f017.corrected-oracle-consumer-terminal/11.0.0",
            "role": role, "result": "COMPLETE", "result_receipt_sha256": receipt_sha256,
            "payload_manifest_sha256": manifest_sha256, "secondary_eligible": role == "PRIMARY"}


def require_primary_terminal(terminal: dict, expected_receipt_sha256: str,
                             expected_manifest_sha256: str | None = None) -> None:
    keys = {"schema", "role", "result", "result_receipt_sha256", "payload_manifest_sha256", "secondary_eligible"}
    if (type(terminal) is not dict or set(terminal) != keys
            or terminal["schema"] != "pulsarmlx.f017.corrected-oracle-consumer-terminal/11.0.0"
            or terminal["role"] != "PRIMARY" or terminal["result"] != "COMPLETE"
            or terminal["secondary_eligible"] is not True
            or terminal["result_receipt_sha256"] != expected_receipt_sha256
            or (expected_manifest_sha256 is not None
                and terminal["payload_manifest_sha256"] != expected_manifest_sha256)):
        raise ResultEnvelopeError("primary terminal prerequisite")


def closure_root(primary_manifest: dict, primary_receipt: dict, primary_terminal: dict,
                 secondary_manifest: dict, secondary_receipt: dict, secondary_terminal: dict,
                 comparison_terminal_sha256: str, release_terminal_sha256: str) -> dict:
    for field in (comparison_terminal_sha256, release_terminal_sha256): _validate_sha(field, "closure SHA")
    return {"schema": "pulsarmlx.f017.corrected-oracle-package-result-closure/11.0.0",
            "primary": {"manifest_sha256": _sha(primary_manifest), "receipt_sha256": _sha(primary_receipt),
                        "terminal_sha256": _sha(primary_terminal),
                        "payload_sha256s": [record["sha256"] for record in primary_manifest["payloads"]]},
            "secondary": {"manifest_sha256": _sha(secondary_manifest), "receipt_sha256": _sha(secondary_receipt),
                          "terminal_sha256": _sha(secondary_terminal),
                          "payload_sha256s": [record["sha256"] for record in secondary_manifest["payloads"]]},
            "comparison_terminal_sha256": comparison_terminal_sha256,
            "release_terminal_sha256": release_terminal_sha256,
            "payload_count": 6, "result": "COMPLETE"}
