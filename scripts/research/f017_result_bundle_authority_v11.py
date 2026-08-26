#!/usr/bin/env python3
"""Strict V11 consumer-result bundle authority."""
from __future__ import annotations

import hashlib
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
from f017_binary_comparison_authority_v11 import validate_summary
from f017_result_artifacts_v11 import (NUMERICAL_CONTRACT_V4_SHA256,
    validate_consumer_terminal, validate_manifest,
    validate_receipt, validate_result_terminal, validate_routing_manifest, validate_top32)
from f017_result_envelope_v11 import ResultEnvelopeError


def _sha(value: dict) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_bundle(directory: Path, *, role: str, authorization_id: str,
                    package_attempt_id: str, consumer_event_id: str,
                    manifest: dict, top32: dict, routing: dict, receipt: dict,
                    result_terminal: dict, consumer_terminal: dict,
                    numerical_contract_sha256: str = NUMERICAL_CONTRACT_V4_SHA256) -> dict:
    if role not in {"PRIMARY","SECONDARY"}:
        raise ResultEnvelopeError("bundle role")
    validate_manifest(directory, manifest)
    if (manifest.get("role"), manifest.get("package_attempt_id"), manifest.get("consumer_event_id")) != (role, package_attempt_id, consumer_event_id):
        raise ResultEnvelopeError("bundle manifest identity")
    logits = manifest["payloads"][2]
    validate_top32(directory, logits, top32)
    validate_routing_manifest(routing, expected_role=role,
        expected_package_attempt_id=package_attempt_id, expected_consumer_event_id=consumer_event_id)
    manifest_sha = _sha(manifest); summary_sha = _sha(top32); routing_sha = _sha(routing)
    validate_receipt(receipt, expected_role=role, expected_manifest_sha256=manifest_sha,
        expected_summary_sha256=summary_sha, expected_routing_manifest_sha256=routing_sha,
        expected_authorization_id=authorization_id, expected_package_attempt_id=package_attempt_id,
        expected_consumer_event_id=consumer_event_id,
        expected_numerical_contract_sha256=numerical_contract_sha256)
    receipt_sha = _sha(receipt)
    validate_result_terminal(result_terminal, expected_role=role,
        expected_receipt_sha256=receipt_sha, expected_manifest_sha256=manifest_sha)
    result_terminal_sha = _sha(result_terminal)
    validate_consumer_terminal(consumer_terminal, expected_role=role,
        expected_result_terminal_sha256=result_terminal_sha,
        expected_receipt_sha256=receipt_sha, expected_manifest_sha256=manifest_sha)
    return {"schema":"pulsarmlx.f017.corrected-oracle-result-bundle-index/11.0.0",
        "role":role,"authorization_id":authorization_id,"package_attempt_id":package_attempt_id,
        "consumer_event_id":consumer_event_id,"manifest_sha256":manifest_sha,
        "top32_summary_sha256":summary_sha,"routing_manifest_sha256":routing_sha,
        "result_receipt_sha256":receipt_sha,"result_terminal_sha256":result_terminal_sha,
        "consumer_terminal_sha256":_sha(consumer_terminal),
        "payload_sha256s":[item["sha256"] for item in manifest["payloads"]],"result":"PASS"}


def compose_comparison_closure(*, primary_directory: Path, secondary_directory: Path,
                               authorization_id: str, package_attempt_id: str,
                               primary_artifacts: dict, secondary_artifacts: dict,
                               comparison_summary: dict,
                               numerical_contract_sha256: str = NUMERICAL_CONTRACT_V4_SHA256) -> dict:
    """Validate raw six-leaf bundles and comparison before composing closure."""
    artifact_keys = {"consumer_event_id", "manifest", "top32", "routing", "receipt",
                     "result_terminal", "consumer_terminal"}
    if (type(primary_artifacts) is not dict or set(primary_artifacts) != artifact_keys
            or type(secondary_artifacts) is not dict or set(secondary_artifacts) != artifact_keys):
        raise ResultEnvelopeError("comparison raw bundle census")
    primary_bundle = validate_bundle(primary_directory, role="PRIMARY",
        authorization_id=authorization_id, package_attempt_id=package_attempt_id,
        numerical_contract_sha256=numerical_contract_sha256, **primary_artifacts)
    secondary_bundle = validate_bundle(secondary_directory, role="SECONDARY",
        authorization_id=authorization_id, package_attempt_id=package_attempt_id,
        numerical_contract_sha256=numerical_contract_sha256, **secondary_artifacts)
    if primary_bundle["consumer_event_id"] == secondary_bundle["consumer_event_id"]:
        raise ResultEnvelopeError("comparison bundle closure identity")
    validate_summary(comparison_summary, primary_directory,
        primary_artifacts["manifest"]["payloads"][2], secondary_directory,
        secondary_artifacts["manifest"]["payloads"][2], primary_artifacts["routing"],
        secondary_artifacts["routing"], primary_artifacts["manifest"],
        secondary_artifacts["manifest"], primary_artifacts["top32"],
        secondary_artifacts["top32"], primary_artifacts["receipt"],
        secondary_artifacts["receipt"], authorization_id)
    expected = {
        "authorization_id":primary_bundle["authorization_id"],
        "package_attempt_id":primary_bundle["package_attempt_id"],
        "primary_payload_manifest_sha256":primary_bundle["manifest_sha256"],
        "secondary_payload_manifest_sha256":secondary_bundle["manifest_sha256"],
        "primary_top32_summary_sha256":primary_bundle["top32_summary_sha256"],
        "secondary_top32_summary_sha256":secondary_bundle["top32_summary_sha256"],
        "primary_routing_manifest_sha256":primary_bundle["routing_manifest_sha256"],
        "secondary_routing_manifest_sha256":secondary_bundle["routing_manifest_sha256"],
    }
    if any(comparison_summary.get(k) != v for k,v in expected.items()):
        raise ResultEnvelopeError("comparison summary bundle binding")
    return {"schema":"pulsarmlx.f017.corrected-oracle-comparison-closure/11.0.0",
        **expected,"primary_bundle_sha256":_sha(primary_bundle),
        "secondary_bundle_sha256":_sha(secondary_bundle),
        "comparison_summary_sha256":_sha(comparison_summary),"result":"PASS"}
