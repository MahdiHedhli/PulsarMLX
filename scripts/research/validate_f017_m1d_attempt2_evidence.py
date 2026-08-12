#!/usr/bin/env python3
"""Fail-closed validator for banked F017 M1-D attempt-2 rejection evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED = {
    "runtime_sha": "258127d4b5e4d2cca592c8b3ec5403a98e39f29f",
    "tooling_sha": "dc95783c9e2666989b038f2744f7b12e2756aa18",
    "repository_head": "53165bb5ac78bca087e82fe769bdb14110a4df4c",
    "preparer": "0d1d70671ab424e0dc9bead70dfba58756126bd6d6669cb08fe5e022ed4761d4",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def validate(document: dict) -> None:
    require(document.get("schema") == "pulsarmlx.f017.m1d-pre-candidate-failure-evidence", "schema mismatch")
    require(document.get("schema_version") == "1.0.0", "schema version mismatch")
    require(document.get("attempt") == 2, "attempt mismatch")
    require(document.get("evidence_origin") == "operator_banked_pre_candidate_failure", "origin mismatch")
    for key, value in EXPECTED.items():
        actual = document["provenance"]["real_reference_preparer_source_sha256"] if key == "preparer" else document["identity"][key]
        require(actual == value, f"{key} mismatch")
    require(document["admission"]["passed"] is True, "admission was not completed")
    preparer = document["preparer"]
    require(preparer["started"] is True and preparer["completed"] is False, "preparer state mismatch")
    require(preparer["failure_stage"] == "activation_fixture_open", "wrong first failure stage")
    require(preparer["activation_opened"] is False, "activation unexpectedly opened")
    require(preparer["checkpoint_opened"] is False, "checkpoint unexpectedly opened")
    require(preparer["matrix_payload_read_count"] == 0, "real payload unexpectedly read")
    require(preparer["oracle_package_created"] is False, "oracle unexpectedly created")
    execution = document["execution"]
    for field in ("checkpoint_read_count", "real_matrix_payload_count", "conceptual_projection_count", "production_repeat_count", "native_dispatch_count", "quant_decode_count", "expert_execution_count", "layer_execution_count", "logits_count"):
        require(execution[field] == 0, f"{field} must be zero")
    require(execution["candidate_started"] is False, "candidate unexpectedly started")
    require(execution["repeat_hashes"] == [], "repeat hashes must be empty")
    require(execution["p1"] is False, "P1 must remain false")
    result = document["result"]
    require(result["verdict"] == "M1-D ATTEMPT 2 REJECTED", "verdict mismatch")
    require(result["classification"] == "FAIL_INFRASTRUCTURE_EVIDENCE", "classification mismatch")
    require(result["first_failure"]["code"] == "m1d_activation_fixture_read", "failure code mismatch")
    require(result["authorization_consumed"] is True, "authorization must be consumed")
    require(result["retry_permitted"] is False, "retry must be forbidden")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    document = json.loads(args.evidence.read_text(), object_pairs_hook=reject_duplicate_keys)
    validate(document)
    print("f017 M1-D attempt-2 rejection evidence valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
