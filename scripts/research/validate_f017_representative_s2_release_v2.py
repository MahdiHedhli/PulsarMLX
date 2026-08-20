#!/usr/bin/env python3
"""Fail-closed validator for append-only representative S2 release v2."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

import validate_f017_representative_s2_release_v1 as validator_v1


ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-construction-authorization-v1.json"
RELEASE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-single-use-release-v2.json"
RELEASE_V1 = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-single-use-release-v1.json"
APPROVAL_CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-release-approval-contract-v2.json"
S1_MANIFEST_SHA = "9ddf842ceec92eee3ae51e9386e4774315965654d711b5751d98ad96868d876e"
FFN_MANIFEST_SHA = "0f6a887fed8e0e4a96494f50bf94879ffec74ef6bc1d0fa64f9b0a3771efc04c"
SUPERSESSION_SHA = "dbc73f9fbccb8262f6151a488cb37a452a5e5576bab987ca02d037604b777e80"


ValidationError = validator_v1.ValidationError
require = validator_v1.require
load = validator_v1.load
sha = validator_v1.sha
validate_authorization = validator_v1.validate_authorization


def git_sha(head: str, relative_path: str) -> str:
    require(re.fullmatch(r"[0-9a-f]{40}", head) is not None, "execution head format")
    result = subprocess.run(["git", "-C", str(ROOT), "show", f"{head}:{relative_path}"], capture_output=True, check=False)
    require(result.returncode == 0, f"execution head missing {relative_path}")
    return hashlib.sha256(result.stdout).hexdigest()


def validate_release(doc: dict[str, Any], repo: bool = True) -> None:
    require(doc.get("schema") == "pulsarmlx.f017.representative-s2-single-use-release", "release schema")
    require(doc.get("schema_version") == "2.0.0", "release version")
    require(doc.get("status") == "PREPARED_FOR_INDEPENDENT_APPROVAL" and doc.get("real_event_authorized") is False and doc.get("approval_asserted") is False, "release state")
    require((doc.get("event_id"), doc.get("release_id"), doc.get("attempt_id")) == (
        "F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1",
        "F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1-RELEASE-2",
        "F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1-ATTEMPT-1",
    ), "release identity")
    head = doc.get("authoritative_execution_code_head")
    require(isinstance(head, str) and re.fullmatch(r"[0-9a-f]{40}", head) is not None, "execution head")
    require(doc.get("head_semantics") == "EXACT_LOAD_BEARING_BYTES_AT_CODE_HEAD;APPEND_ONLY_RELEASE_REVIEW_APPROVAL_AND_BANKING_COMMITS_PERMITTED", "head semantics")

    required = {"authorization", "arithmetic_contract", "s1_reuse_authorization", "ffn_reuse_authorization", "approval_contract", "executor", "release_wrapper", "terminalizer", "validator", "tests", "synthetic_rehearsal", "v1_supersession"}
    require(set(doc["bindings"]) == required, "release binding census")
    for name, binding in doc["bindings"].items():
        require(set(binding) == {"path", "sha256"} and re.fullmatch(r"[0-9a-f]{64}", binding["sha256"]), f"binding shape {name}")
        if repo:
            require(sha(ROOT / binding["path"]) == binding["sha256"], f"binding bytes {name}")
    require(doc["bindings"]["authorization"]["sha256"] == sha(AUTH), "authorization binding")
    require(doc["bindings"]["arithmetic_contract"]["sha256"] == validator_v1.ARITHMETIC_SHA, "arithmetic binding")
    require(doc["bindings"]["s1_reuse_authorization"]["sha256"] == validator_v1.S1_REUSE_SHA, "s1 reuse binding")
    require(doc["bindings"]["ffn_reuse_authorization"]["sha256"] == validator_v1.FFN_REUSE_SHA, "ffn reuse binding")
    require(doc["bindings"]["v1_supersession"]["sha256"] == SUPERSESSION_SHA, "supersession binding")
    if repo:
        for name in required - {"synthetic_rehearsal"}:
            binding = doc["bindings"][name]
            require(git_sha(head, binding["path"]) == binding["sha256"], f"code head {name}")
        rehearsal = load(ROOT / doc["bindings"]["synthetic_rehearsal"]["path"])
        require(rehearsal.get("result") == "PASS" and rehearsal.get("production_preflight") == "PRODUCTION_BINDINGS_RESOLVED", "rehearsal")
        require(rehearsal.get("real_s1_operand_execution_consumptions") == 0 and rehearsal.get("real_ffn_operand_execution_consumptions") == 0 and rehearsal.get("real_s2_constructions") == 0, "rehearsal accounting")

    v1 = load(RELEASE_V1)
    for section in ("operands", "numerical_surface", "single_use", "input_preflight", "output_banking", "runtime", "accounting", "storage_required_bytes", "prohibitions", "stop_boundary"):
        require(doc.get(section) == v1.get(section), f"preserved v1 semantics {section}")
    require(doc["v1_disposition"] == {
        "release_sha256": "1b05c09355974d53ddf4585eee8b4801bd726e3ecd626ea753f066c9e504a3b9",
        "status": "SUPERSEDED_FOR_EXECUTION_AUTHORITY_DUE_TO_S1_MANIFEST_SCHEMA_INCOMPATIBILITY",
        "arithmetic_semantics_remain_accepted": True,
        "historical_review_remains_valid": True,
        "v1_go_token_prohibited": True,
        "v1_execution_occurred": False,
    }, "v1 disposition")
    require(doc["operand_manifest_contracts"] == {
        "s1": {
            "manifest_sha256": S1_MANIFEST_SHA,
            "schema": "pulsarmlx.f017.representative-s1-private-manifest",
            "schema_version": "1.0.0",
            "collection": "SINGULAR_ARTIFACT_OBJECT_ONLY",
            "artifact_path_field": "path",
            "producer_semantic_role": "LAYER3_POST_ATTENTION_RESIDUAL",
            "consumer_alias_after_validation": "REPRESENTATIVE_M1F0_S1_POST_ATTENTION_RESIDUAL",
            "ambiguous_or_plural_collection_rejected": True,
        },
        "ffn": {
            "manifest_sha256": FFN_MANIFEST_SHA,
            "schema": "pulsarmlx.f017.representative-ffn-output-private-manifest",
            "schema_version": "1.0.0",
            "collection": "ONE_ELEMENT_ARTIFACTS_ARRAY_ONLY",
            "artifact_path_field": "symbolic_path",
            "producer_semantic_role": "REPRESENTATIVE_M1F0_FFN_PROOF_REFERENCE_OUTPUT",
            "ambiguous_or_singular_collection_rejected": True,
        },
        "normalization": "NONE_EXACT_PRODUCER_SCHEMAS_VALIDATED_SEPARATELY",
    }, "manifest contracts")
    require(doc["machine_local_paths"] == {
        "resolution": "FIXED_PATHLIB_HOME_AND_REPOSITORY_EXPRESSIONS_NO_CALLER_SELECTION",
        "s1_root": "$HOME/.local/share/pulsarmlx/f017/representative-s1-materialization-release-2/outputs",
        "ffn_root": "$HOME/.local/share/pulsarmlx/f017/representative-ffn-composition-release-2/outputs",
        "state_root": "$HOME/.local/share/pulsarmlx/f017/representative-s2-release-2/attempt-state",
        "output_root": "$HOME/.local/share/pulsarmlx/f017/representative-s2-release-2/outputs",
        "output": "$HOME/.local/share/pulsarmlx/f017/representative-s2-release-2/outputs/representative-s2.f32le",
        "private_manifest": "$HOME/.local/share/pulsarmlx/f017/representative-s2-release-2/outputs/representative-s2-private-manifest-v1.json",
        "receipt": "$HOME/.local/share/pulsarmlx/f017/representative-s2-release-2/attempt-state/s2-execution-receipt.json",
        "approval": "$REPOSITORY/docs/architecture/reviews/evidence/f017-representative-s2-single-use-release-v2-independent-approval-v1.json",
        "go_token": "$HOME/.local/share/pulsarmlx/f017/representative-s2-release-2/go-token.json",
    }, "machine paths")
    require(doc["future_approval"] == {
        "separate_committed_independent_approval_required": True,
        "approval_contract_sha256": sha(APPROVAL_CONTRACT),
        "approval_statement": "REPRESENTATIVE S2 SINGLE-USE RELEASE V2 APPROVED",
        "release_review_and_reviewed_head_enforced": True,
        "reviewer_identity_model_enforced": True,
        "approval_is_not_go_token": True,
        "token_binding": "TRANSITIVE_THROUGH_EXACT_APPROVAL_SHA256",
        "authority_chain": "RELEASE_V2_TO_COMMITTED_REVIEW_TARGET_HEAD_TO_INDEPENDENT_REVIEW_TO_SEPARATE_APPROVAL_TO_MACHINE_LOCAL_GO_TOKEN",
    }, "future approval")
    contract = load(APPROVAL_CONTRACT)
    require(len(contract["approval_exact_fields"]) == 28 and len(set(contract["approval_exact_fields"])) == 28, "approval field census")
    require(doc["stop_boundary"] == "AFTER_REPRESENTATIVE_S2_OUTPUT_ONLY", "release boundary")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, default=AUTH)
    parser.add_argument("--release", type=Path, default=RELEASE)
    parser.add_argument("--no-repo", action="store_true")
    args = parser.parse_args()
    validate_authorization(load(args.authorization), repo=not args.no_repo)
    validate_release(load(args.release), repo=not args.no_repo)
    print("REPRESENTATIVE_S2_RELEASE_V2_VALID")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValidationError, FileNotFoundError, KeyError, TypeError) as error:
        print(f"INVALID:{error}")
        raise SystemExit(2)
