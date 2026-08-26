#!/usr/bin/env python3
"""Bank one V11 consumer bundle from one immutable numerical output object."""
from __future__ import annotations

import hashlib
import heapq
from pathlib import Path
import math
import struct

from f017_canonical_serialization_v10 import bank_exclusive, canonical_bytes
from f017_result_artifacts_v11 import (
    NUMERICAL_CONTRACT_V4_SHA256,
    build_consumer_terminal,
    derive_top_1_margin,
    build_manifest,
    build_receipt,
    build_result_terminal,
    build_routing_manifest,
    build_top32,
)
from f017_result_bundle_authority_v11 import validate_bundle
from f017_result_envelope_v11 import (
    ResultEnvelopeError,
    bank_payload_bytes,
    payload_spec,
)


def _sha(value: dict) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _sha_field(value: object, name: str) -> str:
    if (type(value) is not str or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)):
        raise ResultEnvelopeError(name)
    return value


def _attribute(output: object, name: str) -> object:
    try:
        return object.__getattribute__(output, name)
    except (AttributeError, TypeError) as exc:
        raise ResultEnvelopeError(f"numerical output field: {name}") from exc


def validate_numerical_output_summary(output: object, role: str) -> dict:
    """Couple a real pure-core output object to V11 summary semantics.

    This check is geometry-independent so the frozen checkpoint-free numerical
    corpus can exercise the same seam before the production geometry check.
    """
    if role not in {"PRIMARY", "SECONDARY"} or _attribute(output, "role") != role:
        raise ResultEnvelopeError("numerical output summary role")
    payload = _attribute(output, "full_logits_payload")
    code = "d" if role == "PRIMARY" else "f"
    item_size = 8 if role == "PRIMARY" else 4
    if type(payload) is not bytes or len(payload) % item_size:
        raise ResultEnvelopeError("numerical output summary payload")
    values = [item[0] for item in struct.iter_unpack(f"<{code}", payload)]
    if (len(values) != _attribute(output, "full_logits_element_count")
            or hashlib.sha256(payload).hexdigest() != _attribute(output, "full_logits_sha256")
            or len(values) < 2 or any(not math.isfinite(value) for value in values)):
        raise ResultEnvelopeError("numerical output summary payload binding")
    heap: list[tuple[float, int]] = []
    for token, value in enumerate(values):
        item = (value, -token)
        if len(heap) < min(32, len(values)):
            heapq.heappush(heap, item)
        elif item > heap[0]:
            heapq.heapreplace(heap, item)
    ordered = [(-neg_token, value) for value, neg_token in sorted(heap, reverse=True)]
    bits_field = "logit_f64_bits" if role == "PRIMARY" else "logit_f32_bits"
    expected = [
        {"token_id": token, bits_field: struct.pack(f"<{code}", value).hex()}
        for token, value in ordered
    ]
    observed = [
        {
            "token_id": _attribute(record, "token_id"),
            bits_field: _attribute(record, bits_field),
        }
        for record in _attribute(output, "top_32")
    ]
    if (canonical_bytes(observed) != canonical_bytes(expected)
            or _attribute(output, "selected_token") != ordered[0][0]
            or _attribute(output, "top_1_margin")
            != derive_top_1_margin(role, ordered[0][1], ordered[1][1])):
        raise ResultEnvelopeError("numerical output summary binding")
    return {"result": "PASS", "role": role, "logit_count": len(values)}


def _validate_output(output: object, role: str) -> dict[str, bytes]:
    dtype = "f64le" if role == "PRIMARY" else "f32le"
    if (_attribute(output, "role") != role or _attribute(output, "dtype") != dtype
            or _attribute(output, "core_execution_count") != 1):
        raise ResultEnvelopeError("numerical output authority")
    validate_numerical_output_summary(output, role)
    payloads: dict[str, bytes] = {}
    for kind, count_field, payload_field, sha_field in (
        ("final_hidden", "final_hidden_element_count", "final_hidden_payload", "final_hidden_sha256"),
        ("final_normalized", "final_normalized_element_count", "final_normalized_payload", "final_normalized_sha256"),
        ("full_logits", "full_logits_element_count", "full_logits_payload", "full_logits_sha256"),
    ):
        spec = payload_spec(role, kind)
        payload = _attribute(output, payload_field)
        if type(payload) is not bytes:
            raise ResultEnvelopeError("numerical output payload is not immutable bytes")
        if (_attribute(output, count_field) != spec.element_count
                or len(payload) != spec.byte_count
                or hashlib.sha256(payload).hexdigest() != _attribute(output, sha_field)):
            raise ResultEnvelopeError("numerical output payload binding")
        payloads[kind] = payload
    captures = _attribute(output, "layer_captures")
    if type(captures) is not tuple or len(captures) != 79:
        raise ResultEnvelopeError("numerical output layer census")
    top = _attribute(output, "top_32")
    if type(top) is not tuple or len(top) != 32:
        raise ResultEnvelopeError("numerical output top32 census")
    if type(_attribute(output, "selected_token")) is not int:
        raise ResultEnvelopeError("numerical output selected token")
    if type(_attribute(output, "top_1_margin")) is not float:
        raise ResultEnvelopeError("numerical output margin")
    return payloads


def _routing_layers(output: object) -> list[dict]:
    layers = []
    for expected, capture in enumerate(_attribute(output, "layer_captures")):
        if _attribute(capture, "layer") != expected:
            raise ResultEnvelopeError("numerical output layer order")
        selected = _attribute(capture, "selected_expert_ids")
        if type(selected) is not tuple:
            raise ResultEnvelopeError("numerical output route type")
        layers.append({"selected_expert_ids": list(selected)})
    return layers


def _validate_summary_binding(output: object, summary: dict, role: str) -> None:
    bits_field = "logit_f64_bits" if role == "PRIMARY" else "logit_f32_bits"
    expected = []
    for record in _attribute(output, "top_32"):
        expected.append({
            "token_id": _attribute(record, "token_id"),
            bits_field: _attribute(record, bits_field),
        })
    if (canonical_bytes(summary["entries"]) != canonical_bytes(expected)
            or summary["selected_token"] != _attribute(output, "selected_token")
            or summary["top_1_margin"] != _attribute(output, "top_1_margin")):
        raise ResultEnvelopeError("numerical output summary binding")


def bank_output_bundle(output: object, directory: Path, *, authorization_id: str,
                       package_attempt_id: str, consumer_event_id: str,
                       producer_measurement_sha256: str,
                       durable_start_sha256: str, access_census_sha256: str,
                       numerical_contract_sha256: str = NUMERICAL_CONTRACT_V4_SHA256) -> dict:
    """Create the complete causal bundle without rerunning or repacking a core."""
    role = _attribute(output, "role")
    if role not in {"PRIMARY", "SECONDARY"}:
        raise ResultEnvelopeError("numerical output role")
    if not isinstance(directory, Path):
        raise ResultEnvelopeError("bundle directory")
    for name, value in (
        ("producer measurement", producer_measurement_sha256),
        ("durable start", durable_start_sha256),
        ("access census", access_census_sha256),
        ("numerical contract", numerical_contract_sha256),
    ):
        _sha_field(value, name)
    payloads = _validate_output(output, role)
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    role_leaf = role.lower()
    for kind in ("final_hidden", "final_normalized", "full_logits"):
        records.append(bank_payload_bytes(
            directory, f"{role_leaf}-{kind}.bin", payload_spec(role, kind), payloads[kind],
            package_attempt_id=package_attempt_id, consumer_event_id=consumer_event_id,
        ))
    manifest = build_manifest(role, package_attempt_id, consumer_event_id, records)
    manifest_sha = bank_exclusive(directory / f"{role_leaf}-payload-manifest.json", manifest)
    routing = build_routing_manifest(role, package_attempt_id, consumer_event_id,
                                     _routing_layers(output))
    routing_sha = bank_exclusive(directory / f"{role_leaf}-routing-manifest.json", routing)
    top32 = build_top32(directory, records[2])
    _validate_summary_binding(output, top32, role)
    top32_sha = bank_exclusive(directory / f"{role_leaf}-top32-summary.json", top32)
    receipt = build_receipt(
        role, authorization_id, package_attempt_id, consumer_event_id,
        producer_measurement_sha256, numerical_contract_sha256,
        manifest_sha, top32_sha, routing_sha, durable_start_sha256,
        access_census_sha256,
    )
    receipt_sha = bank_exclusive(directory / f"{role_leaf}-result-receipt.json", receipt)
    result_terminal = build_result_terminal(role, receipt_sha, manifest_sha)
    result_terminal_sha = bank_exclusive(
        directory / f"{role_leaf}-result-terminal.json", result_terminal
    )
    consumer_terminal = build_consumer_terminal(
        role, result_terminal_sha, receipt_sha, manifest_sha
    )
    consumer_terminal_sha = bank_exclusive(
        directory / f"{role_leaf}-consumer-terminal.json", consumer_terminal
    )
    artifacts = {
        "consumer_event_id": consumer_event_id,
        "manifest": manifest,
        "top32": top32,
        "routing": routing,
        "receipt": receipt,
        "result_terminal": result_terminal,
        "consumer_terminal": consumer_terminal,
    }
    index = validate_bundle(
        directory, role=role, authorization_id=authorization_id,
        package_attempt_id=package_attempt_id,
        numerical_contract_sha256=numerical_contract_sha256,
        **artifacts,
    )
    if index["consumer_terminal_sha256"] != consumer_terminal_sha:
        raise ResultEnvelopeError("consumer terminal banking identity")
    return {"artifacts": artifacts, "index": index, "result": "PASS"}
