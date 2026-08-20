#!/usr/bin/env python3
"""Fail-closed validator for the representative FFN output reuse authority."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from f017_representative_ffn_output_reuse_v1 import (
    APPROVAL_SHA,
    ARITHMETIC_SHA,
    AUTH,
    EXECUTION_EVIDENCE_SHA,
    FFN_AUTHORIZATION_SHA,
    MANIFEST_SHA,
    OUTPUT_SHA,
    RELEASE_SHA,
    ROLE,
    ROOT,
    SURFACE,
    ReuseError,
    load,
    validate_authorization,
)


EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-representative-ffn-composition-real-execution-result-v1.json"


class ValidationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_execution_evidence(document: dict[str, Any]) -> None:
    expected_keys = {
        "schema", "schema_version", "result", "execution_head", "process_exit", "authority",
        "attempt", "accounting", "retained_inputs", "output", "private_manifest", "receipt",
        "terminal", "authority_separation", "reproduction", "downstream_prohibitions", "next_action",
    }
    require(set(document) == expected_keys, "evidence keys")
    require(document.get("schema") == "pulsarmlx.f017.representative-ffn-composition-real-execution-result", "evidence schema")
    require(document.get("schema_version") == "1.0.0" and document.get("result") == "SUCCESS", "evidence result")
    require(document.get("execution_head") == "52a68bcd1d7dce66668a5c062065961133799c28" and document.get("process_exit") == 0, "execution identity")

    authority = document.get("authority", {})
    require(authority == {
        "release_sha256": RELEASE_SHA,
        "independent_approval_sha256": APPROVAL_SHA,
        "approval_review_sha256": "23468de7972c6dfd08dd87b43571233850e81a9fb8249c04d0f33ab463b4dae9",
        "go_token_sha256": "788e27911d22cfe66c9d6f878fe0a5485b4ad87e1afa6e69673c07ee858567ca",
        "authorization_sha256": FFN_AUTHORIZATION_SHA,
        "arithmetic_contract_sha256": ARITHMETIC_SHA,
        "executor_sha256": "7632b19af4a0b3bb16ec7032cec049bcab45dabd246cac5d77f0daaec24d256c",
        "release_wrapper_sha256": "0dbf1e08efa112215302d708709d5ef31771ff4e4f2fb03cbe065c9349a06522",
        "terminalizer_sha256": "10069418ad94b39a504d95b1984529a42177917db54be1c9f9029f926c438161",
        "execution_code_head": "0c5ac29777e78aa8a2755feb378ab47dbcfaae0b",
    }, "execution authority")

    attempt = document.get("attempt", {})
    require(attempt.get("event_id") == "F017-REPRESENTATIVE-FFN-COMPOSITION-PROOF-REFERENCE-1", "event id")
    require(attempt.get("release_id") == "F017-REPRESENTATIVE-FFN-COMPOSITION-PROOF-REFERENCE-1-RELEASE-2", "release id")
    require(attempt.get("attempt_id") == "F017-REPRESENTATIVE-FFN-COMPOSITION-PROOF-REFERENCE-1-ATTEMPT-1", "attempt id")
    require(attempt.get("attempt_start_present") is True and attempt.get("attempt_start_sha256") == "cc76bf06bd4fff4a616d2a16407bfe1639134ed0c6f3290865dc424e6501634c", "attempt start")
    require(attempt.get("ffn_start_present") is True and attempt.get("ffn_start_sha256") == "0f97e1958d3e5e133b8725fc84693bb01001d06514f4d89f87c41390e179c853", "ffn start")
    require(attempt.get("token_file_present") is True and attempt.get("token_consumed") is True, "token consumption")
    require(attempt.get("token_consumed_at") == "DURABLE_ATTEMPT_START_BEFORE_FFN_COMPUTATION", "consumption boundary")
    require(attempt.get("ffn_counted_at") == "DURABLE_FFN_START_BEFORE_COMPUTATION_REGARDLESS_OF_OUTCOME", "FFN boundary")
    require(attempt.get("retry") is False and attempt.get("resume") is False and attempt.get("second_attempt") is False, "one shot")

    require(document.get("accounting") == {
        "ledger_before": 175, "ledger_after": 175, "checkpoint_reads": 0, "shard_opens": 0,
        "expert_executions": 0, "shared_expert_executions": 0, "durable_attempt_starts": 1,
        "ffn_starts": 1, "ffn_compositions": 1, "s1_materializations": 0, "s2_constructions": 0,
    }, "accounting")

    retained = document.get("retained_inputs", {})
    require(set(retained) == {"routed", "shared"}, "retained input census")
    for name, expected_sha in {
        "routed": "872487d337305aab82e80a87b84763b6e3dd2901f88ae2ed6b64277aba9a20f9",
        "shared": "8285fecf6e3232f19a0cc11b5d98ee5003f036db6bcd3cd52a7e9dbde9bb1b5b",
    }.items():
        entry = retained[name]
        require(entry.get("expected_sha256") == entry.get("before_sha256") == entry.get("consumed_sha256") == entry.get("after_sha256") == expected_sha, f"{name} consumed identity")
        require(entry.get("identity_unchanged") is True, f"{name} unchanged")

    output = document.get("output", {})
    require(output.get("semantic_role") == ROLE and output.get("semantic_surface") == SURFACE, "output surface")
    require(output.get("path") == "$HOME/.local/share/pulsarmlx/f017/representative-ffn-composition-release-2/outputs/representative-ffn-output.f64le", "output path")
    require(output.get("present") is True and output.get("authority") is True and output.get("sha256") == OUTPUT_SHA, "output authority")
    require(output.get("dtype") == "little-endian-f64" and output.get("shape") == [6144] and output.get("byte_length") == 49152, "output geometry")
    require(output.get("finite") is True and output.get("finite_elements") == 6144, "output finite")
    require(output.get("mode") == "0400" and output.get("hard_link_count") == 1, "output immutability")
    require(output.get("complete_terminal_identity_required") is True, "output terminal binding")

    manifest = document.get("private_manifest", {})
    require(manifest.get("sha256") == MANIFEST_SHA and manifest.get("byte_length") == 627, "manifest identity")
    require(manifest.get("output_sha256_matches") is True and manifest.get("mode") == "0400" and manifest.get("hard_link_count") == 1, "manifest authority")
    receipt = document.get("receipt", {})
    require(receipt.get("sha256") == "8c55a32198070e3f9ef087242cebc0474151259ed0564d7963044ec5ad24b84e", "receipt identity")
    require(all(receipt.get(key) is True for key in ("output_sha256_matches", "manifest_sha256_matches", "input_identities_match")), "receipt cross consistency")
    terminal = document.get("terminal", {})
    require(terminal.get("disposition") == "COMPLETE" and terminal.get("terminal_sha256") == "22cd0d23a72470acf8ce706140578602831b047e8562e577a7e1297d444ed1d9", "terminal identity")
    require(terminal.get("output_authority") is True, "terminal output authority")
    require(all(terminal.get(key) is True for key in ("output_sha256_matches", "manifest_sha256_matches", "receipt_sha256_matches")), "terminal consistency")
    require(terminal.get("stop_boundary") == "AFTER_REPRESENTATIVE_FFN_OUTPUT_ONLY", "terminal boundary")

    separation = document.get("authority_separation", {})
    require(set(separation) == {
        "release_authorized_one_future_attempt", "go_token_authorized_exact_release_attempt",
        "durable_attempt_start_consumed_release", "durable_ffn_start_counted_arithmetic",
        "complete_terminal_and_retained_bytes_establish_output_authority",
        "present_go_token_file_does_not_mean_unconsumed",
    } and all(separation.values()), "authority separation")
    require(document.get("reproduction") == {
        "post_event_reproduction_authorized_by_release": False,
        "post_event_reproduction_performed": False,
        "new_ffn_compositions": 0,
        "adjudication": "DEFERRED_TO_SEPARATE_CROSS_EVENT_REUSE_REVIEW_NO_RETROACTIVE_AUTHORITY_EXPANSION",
    }, "reproduction evidence")
    require(document.get("downstream_prohibitions") == {
        "release_v2_rerun": False,
        "checkpoint_accessed": False,
        "expert_or_shared_expert_reexecuted": False,
        "s1_materialized": False,
        "s2_constructed": False,
    }, "downstream prohibitions")


def validate(document: dict[str, Any], *, repo: bool) -> None:
    try:
        validate_authorization(document)
    except ReuseError as error:
        raise ValidationError(str(error)) from error
    evidence = load(EVIDENCE)
    validate_execution_evidence(evidence)
    if repo:
        require(sha256_path(EVIDENCE) == EXECUTION_EVIDENCE_SHA, "execution evidence bytes")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, default=AUTH)
    parser.add_argument("--no-repo", action="store_true")
    arguments = parser.parse_args()
    if not arguments.no_repo:
        require(arguments.authorization.resolve() == AUTH.resolve(), "committed authorization path")
    validate(load(arguments.authorization), repo=not arguments.no_repo)
    print("REPRESENTATIVE_FFN_OUTPUT_REUSE_AUTHORIZATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
