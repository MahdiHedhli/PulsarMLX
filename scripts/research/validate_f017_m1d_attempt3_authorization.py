#!/usr/bin/env python3
"""Fail-closed validator for the separately authorized M1-D attempt 3."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import f017_m1d_execution_config as execution

ATTEMPT_1 = execution.PRIOR["attempt_1"]
ATTEMPT_2 = execution.PRIOR["attempt_2"]
HANDOFF_PATH = "docs/architecture/reviews/f017-m1-d-attempt-3-handoff.md"
PACKET_PATH = "docs/architecture/reviews/f017-m1-d-attempt-3-authorization.md"
BINDING_PATH = "docs/architecture/reviews/evidence/f017-m1-d-attempt-3-authorization-v1.json"


class ValidationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    try:
        return execution.load_json_no_duplicates(path)
    except ValueError as error:
        raise ValidationError(str(error)) from error


def validate(document: dict, repo: Path, expected_runtime: str, expected_tooling: str, *, validate_packet: bool = True) -> None:
    require(set(document) == {
        "schema", "schema_version", "status", "attempt", "attempt_consumed",
        "runtime_sha", "tooling_sha", "handoff", "execution_config_sha256",
        "activation_fixture", "activation_payload_sha256", "provenance",
        "repository_artifacts", "prior_evidence", "checkpoint_bindings",
        "path_contract", "package_schema", "runner", "execution", "stop_policy",
    }, "attempt-3 authorization fields mismatch")
    require(document["schema"] == "pulsarmlx.f017.m1d-attempt-3-authorization-binding", "schema mismatch")
    require(document["schema_version"] == "1.0.0", "schema version mismatch")
    require(document["status"] == "authorized_exactly_one_attempt_3_not_executed", "status mismatch")
    require(document["attempt"] == 3 and document["attempt_consumed"] is False, "attempt state mismatch")
    require(document["runtime_sha"] == expected_runtime, "runtime SHA mismatch")
    require(document["tooling_sha"] == expected_tooling, "tooling SHA mismatch")
    require(document["handoff"] == {
        "path": HANDOFF_PATH,
        "sha256": sha(repo / HANDOFF_PATH),
    }, "handoff path/hash mismatch")
    execution.validate_sha(document["execution_config_sha256"], "execution config")
    require(document["execution_config_sha256"] != "0" * 64, "execution config is not bound")
    activation = document["activation_fixture"]
    require(activation == {
        "path_kind": "repository_relative",
        "symbolic_path": execution.ACTIVATION_PATH,
        "content_sha256": execution.ACTIVATION_ARTIFACT_SHA256,
        "logical_role": "activation_fixture",
    }, "activation path/content binding mismatch")
    require(document["activation_payload_sha256"] == execution.ACTIVATION_PAYLOAD_SHA256, "activation payload mismatch")
    provenance = document["provenance"]
    require(set(provenance) == {
        "activation_generation_source_sha256",
        "fixture_finalization_source_sha256",
        "real_reference_preparer_sha256",
    }, "provenance roles are ambiguous")
    require(provenance["activation_generation_source_sha256"] == "29c5c51a8f440e06d6584a71e0b79283d2bd6f806a2435c15ff93f3a0cae7984", "activation generator mismatch")
    require(provenance["fixture_finalization_source_sha256"] == "0299066d46211d1921ded772ab907fcd9e9f1c8e3d2c497d979914a30c3dbd92", "fixture finalizer mismatch")
    require(provenance["real_reference_preparer_sha256"] == sha(repo / "scripts/research/prepare_f017_m1d_real_reference.py"), "real preparer mismatch")
    artifacts = document["repository_artifacts"]
    require(set(artifacts) == set(execution.EXPECTED_REPOSITORY_ARTIFACTS), "repository artifact set mismatch")
    for role, (path, frozen_digest) in execution.EXPECTED_REPOSITORY_ARTIFACTS.items():
        reference = artifacts[role]
        require(reference == {
            "path_kind": "repository_relative",
            "symbolic_path": path,
            "content_sha256": sha(repo / path),
            "logical_role": role,
        }, f"{role} reference mismatch")
        if frozen_digest is not None:
            require(reference["content_sha256"] == frozen_digest, f"{role} frozen hash mismatch")
    require(artifacts["real_reference_preparer"]["content_sha256"] == provenance["real_reference_preparer_sha256"], "preparer role mismatch")
    require(document["prior_evidence"] == execution.PRIOR, "attempt/prior evidence mismatch")
    require(document["checkpoint_bindings"] == execution.CHECKPOINT, "checkpoint binding mismatch")
    require(document["path_contract"] == {
        "version": "f017-m1d-artifact-path-resolution-v1",
        "sha256": "40c66a00ea9dcc2b58dc01c7f336cdb5a9098c0ea59920c384727e6ef9cc360d",
    }, "path contract mismatch")
    require(document["package_schema"] == {
        "version": "2.0.0",
        "sha256": "eec3ae97ac8c2ecb04ac982abe8b1bcec313a57888fa5bb66370e31485fc2e2a",
    }, "package schema mismatch")
    require(document["runner"] == {
        "mode": "real_projection",
        "validation_mode": "golden_strict",
        "stream_mode": "owned_device",
        "numerical_mode": "production_mlx_tier_b",
        "memory_floor_bytes": 17179869184,
    }, "runner configuration mismatch")
    require(document["execution"] == {
        "conceptual_projection_count": 1,
        "production_repeat_count": 10,
        "native_dispatch_count": 10,
        "all_repeat_hashes_equal_required": True,
        "oracle_finalized_before_candidate_required": True,
        "preflight_consumes_attempt": False,
    }, "execution bounds mismatch")
    require(document["stop_policy"] == {
        "no_auto_retry": True,
        "mandatory_stop_before_m1_e": True,
    }, "stop policy mismatch")
    require(document["prior_evidence"]["attempt_1"] == ATTEMPT_1, "attempt 1 was not preserved")
    require(document["prior_evidence"]["attempt_2"] == ATTEMPT_2, "attempt 2 was not preserved")
    if validate_packet:
        packet = (repo / PACKET_PATH).read_text()
        values = [expected_runtime, expected_tooling, document["handoff"]["sha256"], document["execution_config_sha256"]]
        values += list(execution.PRIOR.values()) + list(execution.CHECKPOINT.values())
        values += [execution.ACTIVATION_PATH, execution.ACTIVATION_PAYLOAD_SHA256]
        values += list(provenance.values())
        for reference in artifacts.values():
            values += [reference["symbolic_path"], reference["content_sha256"]]
        for value in values:
            require(value in packet, f"authorization packet omits {value}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("binding", type=Path)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--runtime-sha", required=True)
    parser.add_argument("--tooling-sha", required=True)
    args = parser.parse_args()
    validate(load(args.binding), args.repo.resolve(), args.runtime_sha, args.tooling_sha)
    print("F017 M1-D attempt-3 authorization: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
