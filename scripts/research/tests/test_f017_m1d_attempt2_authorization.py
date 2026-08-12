from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/research/validate_f017_m1d_attempt2_authorization.py"
SPEC = importlib.util.spec_from_file_location("m1d_attempt2", SCRIPT)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def valid() -> dict:
    return {
        "schema": "pulsarmlx.f017.m1d-attempt-2-authorization",
        "schema_version": "1.0.0",
        "status": "authorized_exactly_one_attempt_2_not_executed",
        "attempt": 2,
        "runtime_sha": validator.RUNTIME_SHA,
        "tooling_sha": validator.RUNTIME_SHA,
        "failed_attempt": {
            "attempt": 1,
            "verdict": "rejected",
            "failure_code": "m1d_contract_read",
            "evidence_sha256": validator.FAILED_ATTEMPT_SHA,
            "authorization_consumed": True,
        },
        "handoff": {
            "path": validator.HANDOFF_PATH,
            "sha256": validator.sha256(ROOT / validator.HANDOFF_PATH),
        },
        "path_contract": {
            "version": "f017-m1d-artifact-path-resolution-v1",
            "sha256": validator.DIRECT_BINDINGS["path_resolution"],
            "package_schema_version": "2.0.0",
            "repository_root": "explicit_git_identity_verified",
            "package_root": "canonical_package_parent",
        },
        "direct_bindings": copy.deepcopy(validator.DIRECT_BINDINGS),
        "provenance": copy.deepcopy(validator.PROVENANCE),
        "execution": {
            "conceptual_projection_count": 1,
            "production_repeat_count": 10,
            "all_repeat_hashes_equal_required": True,
            "oracle_finalized_before_candidate_required": True,
        },
        "stop_policy": {"no_auto_retry": True, "mandatory_stop_before_m1_e": True},
    }


class Attempt2AuthorizationTests(unittest.TestCase):
    def test_complete_document_is_eligible(self) -> None:
        validator.validate(valid(), ROOT, validate_git=False, validate_packet=False)

    def test_every_binding_is_fail_closed(self) -> None:
        mutations = []
        for field in ("runtime_sha", "tooling_sha"):
            value = valid()
            value[field] = "0" * 40
            mutations.append(value)
        for field in validator.DIRECT_BINDINGS:
            value = valid()
            value["direct_bindings"][field] = "0" * 64
            mutations.append(value)
        for field in validator.PROVENANCE:
            value = valid()
            value["provenance"][field] = "0" * 64
            mutations.append(value)
        value = valid()
        value["handoff"]["sha256"] = "0" * 64
        mutations.append(value)
        value = valid()
        value["failed_attempt"]["authorization_consumed"] = False
        mutations.append(value)
        for mutation in mutations:
            with self.assertRaises(validator.ValidationError):
                validator.validate(mutation, ROOT, validate_git=False, validate_packet=False)

    def test_untyped_or_ambiguous_path_contract_is_rejected(self) -> None:
        value = valid()
        value["path_contract"] = {"root": "package_or_repository"}
        with self.assertRaises(validator.ValidationError):
            validator.validate(value, ROOT, validate_git=False, validate_packet=False)


if __name__ == "__main__":
    unittest.main()
