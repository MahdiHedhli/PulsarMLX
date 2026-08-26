#!/usr/bin/env python3
"""Offline, non-authoritative conversion of the exact retained Event 04 output."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from f017_result_envelope_v11 import bank_payload, payload_spec, ResultEnvelopeError

EXPECTED_BYTES = 3_104_598
EXPECTED_SHA256 = "17255fd412b07275ed422f827bbd884fd3a19ba8a870153ca226143c5f0eca4a"


def convert(raw_path: Path, output_directory: Path, grant: dict) -> dict:
    required = {"schema", "event04_package_attempt_id", "raw_output_path", "expected_size",
                "expected_sha256", "consumer", "purpose", "checkpoint_access", "promotion",
                "event04_receipt_creation", "event04_terminal_creation", "output_root_policy"}
    if (type(grant) is not dict or set(grant) != required
            or grant["consumer"] != "EVENT04_RESULT_ENVELOPE_DIAGNOSTIC_CONVERTER"
            or grant["purpose"] != "NON_AUTHORITATIVE_FORMAT_QUALIFICATION"
            or grant["checkpoint_access"] != "PROHIBITED" or grant["promotion"] != "PROHIBITED"
            or grant["event04_receipt_creation"] != "PROHIBITED"
            or grant["event04_terminal_creation"] != "PROHIBITED"
            or grant["output_root_policy"] != "TEMPORARY_ROOT_OUTSIDE_REPOSITORY_AND_EVENT04_TREE"
            or grant["expected_size"] != EXPECTED_BYTES or grant["expected_sha256"] != EXPECTED_SHA256):
        raise ResultEnvelopeError("diagnostic reuse grant")
    repository = Path(__file__).resolve().parents[2]
    granted_raw = Path(grant["raw_output_path"])
    if not granted_raw.is_absolute(): granted_raw = repository / granted_raw
    if granted_raw.resolve(strict=True) != raw_path.resolve(strict=True):
        raise ResultEnvelopeError("diagnostic raw path binding")
    resolved_output = output_directory.resolve(strict=False)
    raw_parent = raw_path.parent.resolve()
    if (resolved_output == repository or repository in resolved_output.parents
            or resolved_output == raw_parent or raw_parent in resolved_output.parents):
        raise ResultEnvelopeError("diagnostic output root isolation")
    raw = raw_path.read_bytes()
    if len(raw) != EXPECTED_BYTES or hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise ResultEnvelopeError("diagnostic raw output identity")
    try:
        document = json.loads(raw.decode("utf-8"))
        result = document["result"]; logits = result["full_logits"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ResultEnvelopeError("diagnostic output decode") from exc
    if type(logits) is not list or len(logits) != 154_880:
        raise ResultEnvelopeError("diagnostic logits geometry")
    record = bank_payload(output_directory, "event04-primary-full-logits.f64le.bin",
                          payload_spec("PRIMARY", "full_logits"), logits,
                          package_attempt_id=grant["event04_package_attempt_id"],
                          consumer_event_id="EVENT04_NON_AUTHORITATIVE_DIAGNOSTIC")
    record = {**record, "role":"DIAGNOSTIC_EVENT04", "payload_kind":"event04_primary_full_logits",
              "producer_identity":"F017_V11_EVENT04_NON_AUTHORITATIVE_DIAGNOSTIC"}
    return {"schema": "pulsarmlx.f017.event04-result-envelope-diagnostic/11.0.0",
            "authority": "NON_AUTHORITATIVE_DIAGNOSTIC_ONLY", "event04_promotion": "PROHIBITED",
            "event04_receipt_created": False, "event04_terminal_created": False,
            "raw_output_sha256": EXPECTED_SHA256, "payload": record,
            "final_hidden_payload": "UNAVAILABLE_SOURCE_CONTAINS_HASH_ONLY",
            "final_normalized_payload": "UNAVAILABLE_SOURCE_CONTAINS_HASH_ONLY",
            "original_checkpoint_access": 0}
