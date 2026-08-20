#!/usr/bin/env python3
"""Fail-closed validator for the append-only representative FFN release v2."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RELEASE_PATH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-ffn-composition-single-use-release-v2.json"
EVENT_ID = "F017-REPRESENTATIVE-FFN-COMPOSITION-PROOF-REFERENCE-1"
RELEASE_ID = EVENT_ID + "-RELEASE-2"
ATTEMPT_ID = EVENT_ID + "-ATTEMPT-1"
AUTH_SHA = "69e6e49b0e2967b9b7cde7ee00154b7abdaa08609904eca75e54c29b8e4ca1a5"
ARITHMETIC_SHA = "1054d014c23628fa56771518f066d14cfd445b0d7b4ba7da98b638c37981cdbb"
ROUTED_REUSE_SHA = "f04a1eb901f4c738f421b34cc065e2ca20b8938ae00e49ee17e67aeffd99fdfb"
SHARED_REUSE_SHA = "3642200f50f2ed7140243cd885dfe8c3d8628f5605ab37467cc342ea6376019a"
EXECUTOR_SHA = "7632b19af4a0b3bb16ec7032cec049bcab45dabd246cac5d77f0daaec24d256c"
SYNTHETIC_SHA = "04c0448a124d36a7510650d725e09d1cc5f2ce66b0c8ee944da0b831a8d67a60"
AUTH_REVIEW_SHA = "72728eed90efae3e9c432d8301324ce26d9a99c580cd0dacf6f88c83a80580da"
ROUTED_SHA = "872487d337305aab82e80a87b84763b6e3dd2901f88ae2ed6b64277aba9a20f9"
SHARED_SHA = "8285fecf6e3232f19a0cc11b5d98ee5003f036db6bcd3cd52a7e9dbde9bb1b5b"
ROUTED_MANIFEST_SHA = "2403f7b321139d85c811e722298ac4bb164ffd3b0e41e1c73ed7fadd10e55d11"
SHARED_MANIFEST_SHA = "fbdfb87783e72f011207cb06007cb91e955f6f824d96522f149fcb0d37d4ea52"
APPROVAL_CONTRACT_SHA = "fb89706c1313dd7c1f8081b1fb2a39596f596dfff37a00e767efe5df83b956b9"
SUPERSESSION_SHA = "d22aecdd123defa5166c3bae44b67efa1a9e3dc8aad343e909e059b3e948ae08"
V1_RELEASE_SHA = "37752ccedadf5db5eb655d4ba4383a37a431197ec41e07d15f6aa7905dfc6b8a"
V1_REVIEW_SHA = "10a0c72e2e8f5be3aa265231ae4565738ad62bdf4417e9fc5bc7c57bb0af2d58"


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


def git_sha(commit: str, relative_path: str) -> str:
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "execution head format")
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{relative_path}"],
        check=False,
        capture_output=True,
    )
    require(result.returncode == 0, f"execution head path: {relative_path}")
    return hashlib.sha256(result.stdout).hexdigest()


def validate(document: dict[str, Any], *, repo: bool) -> None:
    require(document.get("schema") == "pulsarmlx.f017.representative-ffn-composition-single-use-release", "schema")
    require(document.get("schema_version") == "2.0.0", "version")
    require((document.get("event_id"), document.get("release_id"), document.get("attempt_id")) == (EVENT_ID, RELEASE_ID, ATTEMPT_ID), "identities")
    require(document.get("status") == "PREPARED_FOR_INDEPENDENT_APPROVAL", "status")
    require(document.get("real_event_authorized") is False and document.get("approval_asserted") is False, "approval state")
    execution_head = document.get("authoritative_execution_code_head")
    require(isinstance(execution_head, str) and re.fullmatch(r"[0-9a-f]{40}", execution_head) is not None, "execution head")
    require(document.get("head_semantics") == "EXACT_LOAD_BEARING_BYTES_AT_CODE_HEAD;APPEND_ONLY_RELEASE_REVIEW_APPROVAL_AND_BANKING_COMMITS_PERMITTED", "head semantics")
    require(document.get("release_v1_disposition") == "SUPERSEDED_FOR_EXECUTION_AUTHORITY_DUE_TO_APPROVAL_BINDING_DEFECT", "v1 disposition")

    expected = {
        "ffn_authorization": AUTH_SHA,
        "arithmetic_contract": ARITHMETIC_SHA,
        "routed_reuse_authorization": ROUTED_REUSE_SHA,
        "shared_reuse_authorization": SHARED_REUSE_SHA,
        "executor": EXECUTOR_SHA,
        "synthetic_rehearsal": SYNTHETIC_SHA,
        "ffn_authorization_review": AUTH_REVIEW_SHA,
        "approval_contract": APPROVAL_CONTRACT_SHA,
        "v1_supersession": SUPERSESSION_SHA,
        "release_v1": V1_RELEASE_SHA,
        "release_v1_review": V1_REVIEW_SHA,
    }
    bindings = document.get("bindings", {})
    required_names = set(expected) | {
        "path_contract", "publication_contract", "release_wrapper", "terminalizer",
        "release_rehearsal", "release_validator", "release_tests",
    }
    require(set(bindings) == required_names, "binding census")
    for name, identity in expected.items():
        require(bindings.get(name, {}).get("sha256") == identity, f"binding: {name}")
    for name, binding in bindings.items():
        require(set(binding) == {"path", "sha256"}, f"binding shape: {name}")
        require(isinstance(binding["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", binding["sha256"]) is not None, f"binding hash: {name}")
        if repo:
            require(sha(ROOT / binding["path"]) == binding["sha256"], f"binding bytes: {name}")
    if repo:
        code_names = {"ffn_authorization", "arithmetic_contract", "routed_reuse_authorization", "shared_reuse_authorization", "executor", "approval_contract", "v1_supersession", "release_v1", "release_v1_review", "path_contract", "publication_contract", "release_wrapper", "terminalizer", "release_validator", "release_tests"}
        for name in code_names:
            binding = bindings[name]
            require(git_sha(execution_head, binding["path"]) == binding["sha256"], f"execution head binding: {name}")
        supersession = load(ROOT / bindings["v1_supersession"]["path"])
        require(supersession.get("execution_authority_disposition") == document["release_v1_disposition"], "supersession producer")
        require(supersession.get("historical_review_disposition") == "VALID_REVIEW_OF_RELEASE_V1" and supersession.get("reviewer_failure_implied") is False, "v1 review preservation")
        rehearsal = load(ROOT / bindings["release_rehearsal"]["path"])
        require(rehearsal.get("result") == "PASS" and rehearsal.get("real_ffn_compositions") == 0, "release rehearsal")

    inputs = document.get("retained_inputs", {})
    require(set(inputs) == {"routed", "shared"}, "input census")
    require(inputs["routed"] == {
        "reuse_authorization_sha256": ROUTED_REUSE_SHA,
        "private_manifest_sha256": ROUTED_MANIFEST_SHA,
        "relative_path": "routed-aggregate.f64le",
        "sha256": ROUTED_SHA,
        "semantic_role": "REPRESENTATIVE_M1F0_ROUTED_AGGREGATE_PROOF_REFERENCE",
        "dtype": "little-endian-f64", "shape": [6144], "byte_length": 49152,
    }, "routed input")
    require(inputs["shared"] == {
        "reuse_authorization_sha256": SHARED_REUSE_SHA,
        "private_manifest_sha256": SHARED_MANIFEST_SHA,
        "relative_path": "representative-shared-expert-output.f32le",
        "sha256": SHARED_SHA,
        "semantic_role": "REPRESENTATIVE_M1F0_SHARED_EXPERT_OUTPUT",
        "dtype": "little-endian-f32", "shape": [6144], "byte_length": 24576,
    }, "shared input")

    require(document.get("numerical_surface") == {
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
    require(document.get("single_use") == {
        "attempts": 1, "concurrent_invocation": False,
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
        "state_root": "$HOME/.local/share/pulsarmlx/f017/representative-ffn-composition-release-2/attempt-state",
        "output_root": "$HOME/.local/share/pulsarmlx/f017/representative-ffn-composition-release-2/outputs",
        "output": "$HOME/.local/share/pulsarmlx/f017/representative-ffn-composition-release-2/outputs/representative-ffn-output.f64le",
        "output_private_manifest": "$HOME/.local/share/pulsarmlx/f017/representative-ffn-composition-release-2/outputs/representative-ffn-output-private-manifest-v1.json",
        "execution_receipt": "$HOME/.local/share/pulsarmlx/f017/representative-ffn-composition-release-2/attempt-state/ffn-execution-receipt.json",
        "approval": "$REPOSITORY/docs/architecture/reviews/evidence/f017-representative-ffn-composition-single-use-release-v2-independent-approval-v1.json",
        "go_token": "$HOME/.local/share/pulsarmlx/f017/representative-ffn-composition-release-2/go-token.json",
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
    required_prohibitions = {"checkpoint_access", "shard_open", "expert_execution", "shared_expert_execution", "routed_aggregate_recomputation", "production_serial_f32", "alternate_executor", "caller_selected_paths", "s1_materialization", "s1_input_interface", "s2_construction", "overwrite", "retry", "resume", "second_attempt", "go_token_in_this_phase", "release_v1_approval", "release_v1_go_token"}
    require(set(prohibitions) == required_prohibitions and all(prohibitions.values()), "prohibitions")
    require(document.get("stop_boundary") == "AFTER_REPRESENTATIVE_FFN_OUTPUT_ONLY", "boundary")
    approval = document.get("future_approval", {})
    contract = load(ROOT / bindings["approval_contract"]["path"]) if repo else None
    require(approval.get("separate_committed_independent_approval_required") is True and approval.get("release_itself_is_not_a_token") is True, "approval separation")
    require(approval.get("approval_statement") == "REPRESENTATIVE FFN COMPOSITION SINGLE-USE RELEASE V2 APPROVED", "approval statement")
    require(approval.get("approval_schema_version") == "2.0.0", "approval version")
    require(approval.get("release_review_sha256_required") is True and approval.get("reviewed_head_enforced") is True and approval.get("reviewer_identity_model_enforced") is True, "review authority")
    require(approval.get("authority_chain") == "RELEASE_V2_TO_REVIEWED_HEAD_TO_RELEASE_REVIEW_TO_APPROVAL_TO_GO_TOKEN", "authority chain")
    exact_token = ["approval_sha256", "attempt_id", "authorization_sha256", "disposition", "event_id", "real_event_authorized", "release_id", "release_sha256"]
    require(approval.get("token_exact_fields") == exact_token and approval.get("token_review_binding") == "TRANSITIVE_THROUGH_EXACT_APPROVAL_SHA256", "token authority")
    if repo:
        require(approval.get("approval_exact_fields") == contract["approval_exact_fields"], "approval field contract")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, default=RELEASE_PATH)
    parser.add_argument("--no-repo", action="store_true")
    args = parser.parse_args()
    validate(load(args.release), repo=not args.no_repo)
    print("REPRESENTATIVE_FFN_COMPOSITION_SINGLE_USE_RELEASE_V2_VALID")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidationError, FileNotFoundError, KeyError, TypeError) as error:
        print(f"INVALID: {error}")
        raise SystemExit(2)
