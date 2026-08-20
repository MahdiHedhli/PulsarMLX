#!/usr/bin/env python3
"""Fail-closed validator for representative FFN single-use release v1."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RELEASE_PATH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-ffn-composition-single-use-release-v1.json"
EXECUTION_CODE_HEAD = "ba49351bad99d39cc57a3cea4ce633c43326bd44"
AUTH_SHA = "69e6e49b0e2967b9b7cde7ee00154b7abdaa08609904eca75e54c29b8e4ca1a5"
ARITHMETIC_SHA = "1054d014c23628fa56771518f066d14cfd445b0d7b4ba7da98b638c37981cdbb"
ROUTED_REUSE_SHA = "f04a1eb901f4c738f421b34cc065e2ca20b8938ae00e49ee17e67aeffd99fdfb"
SHARED_REUSE_SHA = "3642200f50f2ed7140243cd885dfe8c3d8628f5605ab37467cc342ea6376019a"
EXECUTOR_SHA = "7632b19af4a0b3bb16ec7032cec049bcab45dabd246cac5d77f0daaec24d256c"
SYNTHETIC_SHA = "04c0448a124d36a7510650d725e09d1cc5f2ce66b0c8ee944da0b831a8d67a60"
REVIEW_SHA = "72728eed90efae3e9c432d8301324ce26d9a99c580cd0dacf6f88c83a80580da"
PATHS_SHA = "6592053ab3ba80fe8957be5b7cbbfcad737980f0952971e8079cc9bb03f05ff0"
PUBLICATION_SHA = "fc139cf0f51c3f114653c421079f390b91a64004bb73a34a143ed8d6a3688f86"
WRAPPER_SHA = "b5983ebf3bc5c6c6f48b57c3ea4af9f600bbe18b05a207f04146bdd4c4564e5d"
TERMINALIZER_SHA = "b7794453e3f9e97273ba43be227413d45672a78e487d182a74461e801eff6ba6"
RELEASE_REHEARSAL_SHA = "c99856201bb674d8ccc2bdd1affb4eb5305c762d86ba1310459951e0b3634418"
ROUTED_SHA = "872487d337305aab82e80a87b84763b6e3dd2901f88ae2ed6b64277aba9a20f9"
SHARED_SHA = "8285fecf6e3232f19a0cc11b5d98ee5003f036db6bcd3cd52a7e9dbde9bb1b5b"
ROUTED_MANIFEST_SHA = "2403f7b321139d85c811e722298ac4bb164ffd3b0e41e1c73ed7fadd10e55d11"
SHARED_MANIFEST_SHA = "fbdfb87783e72f011207cb06007cb91e955f6f824d96522f149fcb0d37d4ea52"


class ValidationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate key: {key}")
        result[key] = value
    return result


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    require(isinstance(value, dict), "object required")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(document: dict[str, Any], *, repo: bool) -> None:
    require(document.get("schema") == "pulsarmlx.f017.representative-ffn-composition-single-use-release", "schema")
    require(document.get("schema_version") == "1.0.0", "version")
    require(document.get("event_id") == "F017-REPRESENTATIVE-FFN-COMPOSITION-PROOF-REFERENCE-1", "event")
    require(document.get("release_id") == "F017-REPRESENTATIVE-FFN-COMPOSITION-PROOF-REFERENCE-1-RELEASE-1", "release id")
    require(document.get("attempt_id") == "F017-REPRESENTATIVE-FFN-COMPOSITION-PROOF-REFERENCE-1-ATTEMPT-1", "attempt id")
    require(document.get("status") == "PREPARED_FOR_INDEPENDENT_APPROVAL", "status")
    require(document.get("real_event_authorized") is False and document.get("approval_asserted") is False, "approval state")
    require(document.get("authoritative_execution_code_head") == EXECUTION_CODE_HEAD, "execution head")
    require(document.get("head_semantics") == "EXACT_LOAD_BEARING_BYTES_AT_CODE_HEAD;APPEND_ONLY_RELEASE_REVIEW_APPROVAL_AND_BANKING_COMMITS_PERMITTED", "head semantics")
    expected = {
        "ffn_authorization": AUTH_SHA,
        "arithmetic_contract": ARITHMETIC_SHA,
        "routed_reuse_authorization": ROUTED_REUSE_SHA,
        "shared_reuse_authorization": SHARED_REUSE_SHA,
        "executor": EXECUTOR_SHA,
        "synthetic_rehearsal": SYNTHETIC_SHA,
        "ffn_authorization_review": REVIEW_SHA,
        "path_contract": PATHS_SHA,
        "publication_contract": PUBLICATION_SHA,
        "release_wrapper": WRAPPER_SHA,
        "terminalizer": TERMINALIZER_SHA,
        "release_rehearsal": RELEASE_REHEARSAL_SHA,
    }
    bindings = document.get("bindings", {})
    require(set(bindings) == set(expected) | {"release_validator", "release_tests"}, "binding census")
    for name, identity in expected.items():
        require(bindings.get(name, {}).get("sha256") == identity, f"binding: {name}")
    for name in ("release_validator", "release_tests"):
        require(isinstance(bindings[name].get("sha256"), str) and len(bindings[name]["sha256"]) == 64, f"binding: {name}")
    if repo:
        for name, binding in bindings.items():
            require(sha(ROOT / binding["path"]) == binding["sha256"], f"binding bytes: {name}")
        authorization = load(ROOT / bindings["ffn_authorization"]["path"])
        require(authorization.get("status") == "PREPARED_REVIEW_REQUIRED" and authorization.get("real_event_authorized") is False, "authorization producer state")
        require(authorization.get("stop_boundary") == "AFTER_REPRESENTATIVE_FFN_OUTPUT_ONLY", "authorization producer boundary")
        review = load(ROOT / bindings["ffn_authorization_review"]["path"])
        require(review.get("verdict") == "ACCEPT" and not review.get("blocking_findings") and not review.get("non_blocking_required_findings"), "authorization acceptance")
        rehearsal = load(ROOT / bindings["release_rehearsal"]["path"])
        require(rehearsal.get("result") == "PASS" and rehearsal.get("case_count") == 8 and rehearsal.get("real_ffn_compositions") == 0, "release rehearsal")
    inputs = document.get("retained_inputs", {})
    require(set(inputs) == {"routed", "shared"}, "input census")
    routed, shared = inputs["routed"], inputs["shared"]
    require(routed == {
        "reuse_authorization_sha256": ROUTED_REUSE_SHA,
        "private_manifest_sha256": ROUTED_MANIFEST_SHA,
        "relative_path": "routed-aggregate.f64le",
        "sha256": ROUTED_SHA,
        "semantic_role": "REPRESENTATIVE_M1F0_ROUTED_AGGREGATE_PROOF_REFERENCE",
        "dtype": "little-endian-f64", "shape": [6144], "byte_length": 49152,
    }, "routed input")
    require(shared == {
        "reuse_authorization_sha256": SHARED_REUSE_SHA,
        "private_manifest_sha256": SHARED_MANIFEST_SHA,
        "relative_path": "representative-shared-expert-output.f32le",
        "sha256": SHARED_SHA,
        "semantic_role": "REPRESENTATIVE_M1F0_SHARED_EXPERT_OUTPUT",
        "dtype": "little-endian-f32", "shape": [6144], "byte_length": 24576,
    }, "shared input")
    numerical = document.get("numerical_surface", {})
    require(numerical == {
        "classification": "CANONICAL_F017_PROOF_REFERENCE_FFN_SURFACE_INTENTIONALLY_DISTINCT_FROM_PRODUCTION_SERIAL_F32",
        "formula": "FFN[k]=Routed_f64[k]+binary64(Shared_f32[k])",
        "shared_promotion": "exact IEEE-754 binary32-to-binary64",
        "shared_multiplier": "NONE; binary64 1.0",
        "addition": "one binary64 addition per coordinate",
        "rounding": "round-to-nearest ties-to-even",
        "coordinate_order": "increasing 0..6143",
        "reduction": False, "blas": False, "gpu": False, "parallel_arithmetic": False,
        "production_serial_f32": "SEPARATE_UNAUTHORIZED_SURFACE",
    }, "numerical surface")
    preflight = document.get("preexecution_gates", {})
    required_gates = {
        "ledger_175", "authorization_and_release_identity", "routed_expected_before_consumed_after",
        "shared_expected_before_consumed_after", "private_manifests", "executor_and_arithmetic",
        "runtime_environment", "no_checkpoint_or_shard_interface", "no_expert_or_shared_compute_interface",
        "attempt_root_absent", "output_and_manifest_absent", "fixed_paths", "output_parent_open_once",
        "same_state_output_filesystem", "storage", "all_locally_checkable_before_ffn",
    }
    require(set(preflight) == required_gates and all(preflight.values()), "preflight gates")
    single = document.get("single_use", {})
    require(single == {
        "attempts": 1,
        "concurrent_invocation": False,
        "consumed_at": "DURABLE_ATTEMPT_START_BEFORE_FFN_COMPUTATION",
        "ffn_execution_counted_at": "DURABLE_FFN_START_BEFORE_COMPUTATION_REGARDLESS_OF_OUTCOME",
        "exclusive_attempt_creation": True,
        "partial_root_without_attempt_start": "UNCONSUMED_ZERO_COMPUTE_MANUAL_ADJUDICATION_REQUIRED",
        "release_remains_consumed_after_any_post_start_outcome": True,
        "interruption_reconciled_by_bound_terminalizer": True,
        "retry": False, "resume": False, "second_attempt": False,
    }, "single use")
    output = document.get("output_banking", {})
    require(output.get("semantic_role") == "REPRESENTATIVE_M1F0_FFN_PROOF_REFERENCE_OUTPUT", "output role")
    require(output.get("dtype") == "little-endian-f64" and output.get("shape") == [6144] and output.get("byte_length") == 49152, "output geometry")
    for field in ("finite", "output_sha256_recorded", "private_manifest", "execution_receipt", "file_fsync", "descriptor_relative_exclusive_temp", "no_replace_publication", "parent_fsync", "descriptor_read_back", "matching_complete_terminal_required", "published_failure_artifacts_retained_for_adjudication"):
        require(output.get(field) is True, f"output banking: {field}")
    require(output.get("overwrite") is False and output.get("partial_output_authority") is False, "output authority")
    paths = document.get("machine_local_paths", {})
    require(paths == {
        "resolution": "FIXED_PATHLIB_HOME_AND_REPOSITORY_EXPRESSIONS_NO_CALLER_SELECTION",
        "state_root": "$HOME/.local/share/pulsarmlx/f017/representative-ffn-composition-release-1/attempt-state",
        "output_root": "$HOME/.local/share/pulsarmlx/f017/representative-ffn-composition-release-1/outputs",
        "output": "$HOME/.local/share/pulsarmlx/f017/representative-ffn-composition-release-1/outputs/representative-ffn-output.f64le",
        "output_private_manifest": "$HOME/.local/share/pulsarmlx/f017/representative-ffn-composition-release-1/outputs/representative-ffn-output-private-manifest-v1.json",
        "execution_receipt": "$HOME/.local/share/pulsarmlx/f017/representative-ffn-composition-release-1/attempt-state/ffn-execution-receipt.json",
        "approval": "$REPOSITORY/docs/architecture/reviews/evidence/f017-representative-ffn-composition-single-use-release-v1-independent-approval-v1.json",
        "go_token": "$HOME/.local/share/pulsarmlx/f017/representative-ffn-composition-release-1/go-token.json",
    }, "machine paths")
    require(document.get("runtime") == {
        "cpython": "3.14.6", "platform": "Darwin-arm64", "endianness": "little",
        "thread_variables_equal_one": ["OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"],
        "arithmetic_backend": "CPYTHON_STRUCT_AND_SCALAR_IEEE754_ONLY", "numpy_required": False,
    }, "runtime")
    require(document.get("accounting") == {
        "starting_ledger": 175, "terminal_ledger": 175, "checkpoint_reads": 0, "shard_opens": 0,
        "expert_executions": 0, "shared_expert_executions": 0,
        "preparation_ffn_compositions": 0, "future_ffn_compositions": 1,
        "s1_materializations": 0, "s2_constructions": 0,
    }, "accounting")
    prohibitions = document.get("prohibitions", {})
    required_prohibitions = {
        "checkpoint_access", "shard_open", "expert_execution", "shared_expert_execution",
        "routed_aggregate_recomputation", "production_serial_f32", "alternate_executor",
        "caller_selected_paths", "s1_materialization", "s1_input_interface", "s2_construction",
        "overwrite", "retry", "resume", "second_attempt", "go_token_in_this_phase",
    }
    require(set(prohibitions) == required_prohibitions and all(prohibitions.values()), "prohibitions")
    require(document.get("stop_boundary") == "AFTER_REPRESENTATIVE_FFN_OUTPUT_ONLY", "boundary")
    approval = document.get("future_approval", {})
    require(approval.get("separate_committed_independent_approval_required") is True and approval.get("release_itself_is_not_a_token") is True, "approval separation")
    require(approval.get("approval_statement") == "REPRESENTATIVE FFN COMPOSITION SINGLE-USE RELEASE V1 APPROVED", "approval statement")
    require(approval.get("token_exact_fields") == ["approval_sha256", "attempt_id", "authorization_sha256", "disposition", "event_id", "real_event_authorized", "release_id", "release_sha256"], "token schema")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, default=RELEASE_PATH)
    parser.add_argument("--no-repo", action="store_true")
    args = parser.parse_args()
    validate(load(args.release), repo=not args.no_repo)
    print("REPRESENTATIVE_FFN_COMPOSITION_SINGLE_USE_RELEASE_VALID")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidationError, FileNotFoundError, KeyError, TypeError) as error:
        print(f"INVALID: {error}")
        raise SystemExit(2)
