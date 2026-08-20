#!/usr/bin/env python3
"""Fail-closed validator for routed-aggregate single-use release v1."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RELEASE_PATH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-routed-aggregate-single-use-release-v1.json"
AUTH_SHA = "d103ab6abc81cbeffea1c95553ba70b41cd7c430b403b39bcf2542d6cc4d3590"
ARITHMETIC_SHA = "ef4b6f5c4e66efd031d6fba1fafee087e5496dd16b5b6f658204359f89762da2"
EXECUTOR_SHA = "fa85558686caa3a57ca356d7e49e5d73ca1f7cb512c1148b670ce0f504e921d5"
REHEARSAL_SHA = "064d938d5ac2b3bd8a9ed0a6633ec94a25f12c7e7f49f4a3c53c6c059e4f4dcc"
REVIEW_SHA = "3c362e0b5ae337b30727580bac67859811e001a91bbc3d5b9c88165f45951c9a"
REUSE_SHA = "1b8b053d60f87c9da8c8c81a41a3d82f7652859a2464941c39b5a1eab3d7c070"
MANIFEST_SHA = "2b3a0ef3bb2d896dd04add67e6fc729b2b400170b58f9038751cee612d58bc7a"
EXECUTION_CODE_HEAD = "2d3e562c03b76444ae3639f9af08f8e54d7306e4"
PATH_CONTRACT_SHA = "f9f2e24f4529dd47ee8cc966ab4433f3b99fcad76819865f60237802ad4b544f"
PUBLICATION_CONTRACT_SHA = "ad38b4d1fd7ca8b10764eb3e5ab4b765452f9714f949ce077a5e253cb14ba691"
WRAPPER_SHA = "9ac3172ffc0ac2fd4b8a7411a0ef2671cc5dbe9cececae4ad6fc0fa5a2c8bd7e"
TERMINALIZER_SHA = "e087f2c9060fd058a517dc98748193d33acba9c94b6f2cf10bf6b43d12cb8267"
RELEASE_REHEARSAL_SHA = "a3a2db9f8ab819cd43cce196f5bb2ea54474e281a7269d53bd186e8b8401c03b"
IDS = [250, 10, 237, 62, 73, 177, 218, 28]
WEIGHTS = [0.7487501576296707, 0.3348627106807668, 0.23863270273063697, 0.23688715675086147,
           0.2514906203405492, 0.23059957299763345, 0.22915341148588297, 0.22962366738399842]
OUTPUTS = ["0b6036ef2e77142094b673c421b96719619a58e15eee7522347b37f73d9b892b",
           "d9adb474f64c98349dfe0a6c768b2020b27f62ecc85874975c990b880ef304b3",
           "4ac842afb3b1909f9f0e07013c86bbdca90cd246b6190bf190a60fe9767fdd9b",
           "2550cccf9b2f1a83b2e2f03f090ee135dc525a15eaf1bab18d1a2fb97af16128",
           "9aa5e1dae2619c440c65689154de332da313990b4ba07fdac45e78a65ad3a7d3",
           "18260d4936483b6f7d83d2d0ec72d01fc761f2ac5726fa9b7bda243a4db9a201",
           "f4a8fc1e3bb91a8a5635505f766a07ef2cfb135378d224ed5f545617d781537d",
           "45029a47061c43746344d5b0a9366b8129630019a3196d0be146efc5e1a361f0"]


class ValidationError(ValueError):
    pass


def req(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        req(key not in result, f"duplicate key: {key}")
        result[key] = value
    return result


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=_unique)
    req(isinstance(value, dict), "object required")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(document: dict[str, Any], *, repo: bool) -> None:
    req(document.get("schema") == "pulsarmlx.f017.representative-routed-aggregate-single-use-release", "schema")
    req(document.get("schema_version") == "1.0.0", "schema version")
    req(document.get("event_id") == "F017-REPRESENTATIVE-ROUTED-AGGREGATE-ANALYTICAL-1", "event id")
    req(document.get("release_id") == "F017-REPRESENTATIVE-ROUTED-AGGREGATE-ANALYTICAL-1-RELEASE-1", "release id")
    req(document.get("attempt_id") == "F017-REPRESENTATIVE-ROUTED-AGGREGATE-ANALYTICAL-1-ATTEMPT-1", "attempt id")
    req(document.get("status") == "PREPARED_FOR_INDEPENDENT_APPROVAL", "status")
    req(document.get("real_event_authorized") is False and document.get("approval_asserted") is False, "approval state")
    req(document.get("head_semantics") == "EXACT_LOAD_BEARING_BYTES_AT_CODE_HEAD;APPEND_ONLY_RELEASE_REVIEW_APPROVAL_AND_BANKING_COMMITS_PERMITTED", "head semantics")
    req(document.get("authoritative_execution_code_head") == EXECUTION_CODE_HEAD, "code head")
    expected_bindings = {
        "authorization": AUTH_SHA,
        "arithmetic_contract": ARITHMETIC_SHA,
        "executor": EXECUTOR_SHA,
        "synthetic_rehearsal": REHEARSAL_SHA,
        "final_independent_review": REVIEW_SHA,
        "expert_output_reuse_authorization": REUSE_SHA,
    }
    bindings = document.get("bindings", {})
    for key, identity in expected_bindings.items():
        req(bindings.get(key, {}).get("sha256") == identity, f"binding: {key}")
    for key in ("path_contract", "publication_contract", "release_wrapper", "terminalizer", "release_validator", "release_rehearsal"):
        req(isinstance(bindings.get(key, {}).get("sha256"), str) and len(bindings[key]["sha256"]) == 64, f"binding: {key}")
    req(bindings["path_contract"]["sha256"] == PATH_CONTRACT_SHA, "path contract identity")
    req(bindings["publication_contract"]["sha256"] == PUBLICATION_CONTRACT_SHA, "publication contract identity")
    req(bindings["release_wrapper"]["sha256"] == WRAPPER_SHA, "wrapper identity")
    req(bindings["terminalizer"]["sha256"] == TERMINALIZER_SHA, "terminalizer identity")
    req(bindings["release_rehearsal"]["sha256"] == RELEASE_REHEARSAL_SHA, "release rehearsal identity")
    if repo:
        for key, item in bindings.items():
            req(sha(ROOT / item["path"]) == item["sha256"], f"binding bytes: {key}")
    req(document.get("private_manifest_sha256") == MANIFEST_SHA, "private manifest")
    triples = document.get("atomic_id_weight_output_triples")
    req(isinstance(triples, list) and len(triples) == 8, "triple count")
    req([item.get("ordinal") for item in triples] == list(range(8)), "triple ordinals")
    req([item.get("expert_id") for item in triples] == IDS, "expert order")
    req([item.get("routing_weight") for item in triples] == WEIGHTS, "weight pairing")
    req([item.get("output_sha256") for item in triples] == OUTPUTS, "output pairing")
    for ordinal, item in enumerate(triples):
        req(item.get("private_relative_path") == f"{ordinal:02d}-expert-{IDS[ordinal]}-down.f32le", "triple path")
        req(item.get("dtype") == "little-endian-f32" and item.get("shape") == [6144] and item.get("byte_length") == 24576, "triple geometry")
    if repo:
        authorization = load(ROOT / bindings["authorization"]["path"])
        req(authorization.get("atomic_id_weight_output_triples") == triples, "authorization producer schema")
        reuse = load(ROOT / bindings["expert_output_reuse_authorization"]["path"])
        req(reuse.get("atomic_id_weight_output_triples") == [dict(item, semantic_role="REPRESENTATIVE_M1F0_ROUTED_EXPERT_OUTPUT") for item in triples], "reuse producer schema")
        arithmetic = load(ROOT / bindings["arithmetic_contract"]["path"])
        req(arithmetic.get("semantic_classification") == document.get("aggregate_semantic_classification"), "arithmetic classification")
        review = load(ROOT / bindings["final_independent_review"]["path"])
        req(review.get("verdict") == "ACCEPT" and not review.get("blocking_findings") and not review.get("non_blocking_required_findings"), "accepted review")
    req(document.get("aggregate_semantic_classification") == "CANONICAL_F017_PROOF_REFERENCE_SURFACE_INTENTIONALLY_DISTINCT_FROM_PRODUCTION_SERIAL_F32", "semantic surface")
    req(document.get("production_serial_f32") == "SEPARATE_UNAUTHORIZED_SURFACE", "production separation")
    paths = document.get("machine_local_paths", {})
    req(paths.get("path_contract_sha256") == bindings["path_contract"]["sha256"], "path contract binding")
    req(paths.get("resolution") == "FIXED_PATHLIB_HOME_AND_REPOSITORY_EXPRESSIONS_NO_CALLER_SELECTION", "path resolution")
    req(paths.get("state_root") == "$HOME/.local/share/pulsarmlx/f017/representative-routed-aggregate-release-1/attempt-state", "state path")
    req(paths.get("output_root") == "$HOME/.local/share/pulsarmlx/f017/representative-routed-aggregate-release-1/outputs", "output root")
    req(paths.get("output") == "$HOME/.local/share/pulsarmlx/f017/representative-routed-aggregate-release-1/outputs/routed-aggregate.f64le", "output path")
    req(paths.get("approval") == "$REPOSITORY/docs/architecture/reviews/evidence/f017-representative-routed-aggregate-single-use-release-v1-independent-approval-v1.json", "approval path")
    req(paths.get("go_token") == "$HOME/.local/share/pulsarmlx/f017/representative-routed-aggregate-release-1/go-token.json", "token path")
    single = document.get("single_use", {})
    req(single == {
        "attempts": 1, "concurrent_invocation": False,
        "consumed_at": "DURABLE_ATTEMPT_START_BEFORE_AGGREGATE_COMPUTATION",
        "exclusive_attempt_creation": True,
        "pre_attempt_failure_unconsumed_only_if_no_aggregate_computation_and_no_output_authority": True,
        "release_remains_consumed_after_any_post_start_failure": True,
        "interruption_reconciled_by_bound_terminalizer": True,
        "retry": False, "resume": False, "second_attempt": False,
    }, "single use")
    preflight = document.get("preexecution_gates", {})
    required_gates = {"ledger_175", "all_eight_expected_before_consumed_after", "exact_triples", "reuse_authority",
                      "arithmetic_contract", "executor_identity", "runtime_environment", "no_checkpoint_interface",
                      "no_expert_interface", "attempt_state_absent", "authoritative_output_absent", "fixed_paths",
                      "output_parent_open_once", "storage", "same_filesystem"}
    req(set(preflight) == required_gates and all(value is True for value in preflight.values()), "preexecution gates")
    output = document.get("output_publication", {})
    req(output.get("contract_sha256") == bindings["publication_contract"]["sha256"], "publication binding")
    req(output.get("dtype") == "little-endian-f64" and output.get("shape") == [6144] and output.get("byte_length") == 49152, "output geometry")
    req(output.get("serialization") == "contiguous-c-order-ieee754-binary64-little-endian", "output serialization")
    req(output.get("no_replace_hard_link_publish") is True and output.get("file_fsync") is True and output.get("parent_fsync") is True, "durable publication")
    req(output.get("descriptor_relative_temp_creation") is True, "descriptor-relative temporary creation")
    req(output.get("authority_requires_matching_complete_terminal") is True, "complete terminal authority gate")
    req(output.get("overwrite") is False and output.get("partial_output_authority") is False, "output safety")
    reproduction = document.get("reproduction", {})
    req(reproduction == {
        "real_event_reproduction_runs": 0,
        "reason": "ACCEPTED_AUTHORIZATION_BUDGETS_EXACTLY_ONE_REAL_AGGREGATE;TWO_FRESH_PROCESS_DETERMINISM_IS_ALREADY_FROZEN_BY_SYNTHETIC_REHEARSAL",
        "synthetic_fresh_processes": 2,
        "synthetic_exact_identity": True,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
    }, "reproduction")
    req(document.get("accounting") == {
        "starting_ledger": 175, "terminal_ledger": 175, "checkpoint_reads": 0, "shard_opens": 0,
        "expert_executions": 0, "preparation_aggregate_executions": 0, "future_aggregate_executions": 1,
    }, "accounting")
    prohibitions = document.get("prohibitions", {})
    required_prohibitions = {"checkpoint_access", "shard_open", "expert_execution", "shared_expert", "ffn_completion",
                             "residual_addition", "s2_construction", "production_serial_f32", "alternate_executor",
                             "caller_selected_paths", "overwrite", "retry", "resume", "second_attempt", "go_token_in_this_phase"}
    req(set(prohibitions) == required_prohibitions and all(prohibitions.values()), "prohibitions")
    req(document.get("stop_boundary") == "AFTER_ROUTED_AGGREGATE_ONLY", "stop boundary")
    approval = document.get("future_approval", {})
    req(approval.get("separate_committed_independent_approval_required") is True and approval.get("release_itself_is_not_a_token") is True, "approval separation")
    req(approval.get("token_exact_fields") == ["approval_sha256", "attempt_id", "authorization_sha256", "disposition", "event_id", "real_event_authorized", "release_id", "release_sha256"], "token schema")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, default=RELEASE_PATH)
    parser.add_argument("--no-repo", action="store_true")
    args = parser.parse_args()
    validate(load(args.release), repo=not args.no_repo)
    print("REPRESENTATIVE_ROUTED_AGGREGATE_SINGLE_USE_RELEASE_VALID")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidationError, FileNotFoundError, KeyError) as error:
        print(f"INVALID: {error}")
        raise SystemExit(2)
