#!/usr/bin/env python3
"""Deep validator for representative shared-expert single-use release v1."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RELEASE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-shared-expert-recovery-single-use-release-v1.json"
AUTH_SHA = "45b25de7978e01898eb5ea948202d70d5b43f33c2cbc84ec7b11a9955c5d9596"
REVIEW_SHA = "c403c36e67a2816c6572bd2127a330a8fffa125ef4bbadd25c06db06f3b5678c"
EXECUTOR_SHA = "d57cd1ea3e9a74655ac2a3881f9b5aa1f5ee3036b76d18518b8834357273e0ec"
REHEARSAL_SHA = "54f80a379948dfd1697c9d5a7962ad3c39cf75d404d4c7c1c166ac9ca2f184f9"
INPUT_SHA = "687a692a452e30860c34055942061f4ff368ec0e1c815439c71e457a444fe62c"
PARAMETERS = [
    ("gate", "750b148ada60dbbfc9bd3b2d4c2bbfa70f304c34328b025f912626dea70c1414", "0dbb53a88bae423154f385ec547c9b778afe8127df6a19955dce2b1653d2282b", "Q5_K", 8650752, [2048, 6144]),
    ("up", "13727df9b9129906538081fcef3a23d4db8ba37235bb96605c46b3ff683c59fe", "86aae8655c565eeed20a3f87fd701fa15aff976600d095694cd163a0303e3000", "Q5_K", 8650752, [2048, 6144]),
    ("down", "48c5469bf71d1c5291f806a79388901f094d5fd7adaec5c25c0f3391b0d67083", "97e654b6e4903cd35ae8fae15c03e9953b15ef3ad4f5c0c60210a1e7864fe4a3", "Q6_K", 10321920, [6144, 2048]),
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate key {key}")
        result[key] = value
    return result


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=unique)
    require(isinstance(value, dict), "object required")
    return value


def validate_release(doc: dict[str, Any], *, repo_mode: bool = False) -> None:
    require(doc.get("schema") == "pulsarmlx.f017.representative-shared-expert-recovery-single-use-release", "schema")
    require(doc.get("schema_version") == "1.0.0", "schema version")
    require(doc.get("event_id") == "F017-REPRESENTATIVE-M1F0-SHARED-EXPERT-RECOVERY-1", "event")
    require(doc.get("release_id") == "F017-REPRESENTATIVE-M1F0-SHARED-EXPERT-RECOVERY-1-RELEASE-1", "release")
    require(doc.get("attempt_id") == "F017-REPRESENTATIVE-M1F0-SHARED-EXPERT-RECOVERY-1-ATTEMPT-1", "attempt")
    require(doc.get("status") == "PREPARED_FOR_INDEPENDENT_APPROVAL", "status")
    require(doc.get("real_event_authorized") is False and doc.get("approval_asserted") is False, "authorization separation")
    require(doc.get("head_semantics") == "EXACT_LOAD_BEARING_BYTES_AT_CODE_HEAD;APPEND_ONLY_RELEASE_REVIEW_APPROVAL_AND_BANKING_COMMITS_PERMITTED", "head semantics")
    bindings = doc.get("bindings", {})
    expected_binding_keys = {"authorization", "authorization_review", "executor", "authorization_rehearsal", "parameter_reuse", "computation_contract", "output_contract", "path_contract", "publication_contract", "reproduction_contract", "input_vocabulary", "release_wrapper", "reproduction_producer", "terminalizer", "release_validator", "release_tests", "release_rehearsal"}
    require(set(bindings) == expected_binding_keys, "binding set")
    require(bindings["authorization"]["sha256"] == AUTH_SHA, "authorization binding")
    require(bindings["authorization_review"]["sha256"] == REVIEW_SHA, "review binding")
    require(bindings["executor"]["sha256"] == EXECUTOR_SHA, "executor binding")
    require(bindings["authorization_rehearsal"]["sha256"] == REHEARSAL_SHA, "rehearsal binding")
    if repo_mode:
        for binding in bindings.values():
            path = ROOT / binding["path"]
            require(path.is_file() and sha(path) == binding["sha256"], f"binding bytes {binding['path']}")
        subprocess.run(["git", "merge-base", "--is-ancestor", doc["authoritative_execution_code_head"], "HEAD"], cwd=ROOT, check=True, capture_output=True)

    shared_input = doc.get("representative_input", {})
    require(shared_input == {"path": "/Users/mhedhli/.local/share/pulsarmlx/f017/representative-expert-input-v1/router_normalized.f32le", "semantic_role": "CANONICAL_REPRESENTATIVE_POST_ATTENTION_FFN_NORMALIZED_SHARED_EXPERT_INPUT", "sha256": INPUT_SHA, "dtype": "little-endian-f32", "shape": [6144], "byte_length": 24576, "consume_what_you_validated": True}, "representative input")
    parameters = doc.get("retained_parameters", [])
    require(len(parameters) == 3 and sum(item.get("packed_bytes", 0) for item in parameters) == 27623424, "parameter inventory")
    observed = [(item.get("role"), item.get("packed_sha256"), item.get("decoded_sha256"), item.get("quantization"), item.get("packed_bytes"), item.get("decoded_shape")) for item in parameters]
    require(observed == PARAMETERS, "parameter identities")
    require(doc.get("retained_parameter_root") == "/Users/mhedhli/Documents/Coding/PulsarMLX-f017-runner/.pulsarmlx-local/canonical-shared-expert-output-recovery-1/package", "parameter root")

    paths = doc.get("machine_local_paths", {})
    require(paths.get("attempt_state_root") == "/Users/mhedhli/.local/share/pulsarmlx/f017/representative-shared-expert-release-1/attempt-state", "state root")
    require(paths.get("output_root") == "/Users/mhedhli/.local/share/pulsarmlx/f017/representative-shared-expert-release-1/outputs", "output root")
    require(paths.get("output") == "/Users/mhedhli/.local/share/pulsarmlx/f017/representative-shared-expert-release-1/outputs/representative-shared-expert-output.f32le", "output path")
    require(paths.get("caller_selected_paths") is False and paths.get("checkpoint_or_shard_path") is None, "path closure")

    one_shot = doc.get("single_use", {})
    require(one_shot.get("attempts") == 1 and one_shot.get("exclusive_attempt_creation") is True, "one shot")
    require(one_shot.get("consumed_at") == "DURABLE_ATTEMPT_START_BEFORE_SHARED_EXPERT_COMPUTATION", "consumption")
    require(one_shot.get("shared_expert_execution_counted_at") == "DURABLE_SHARED_COMPUTATION_START_BEFORE_COMPUTATION_REGARDLESS_OF_OUTCOME", "execution accounting")
    for key in ("retry", "resume", "second_attempt", "concurrent_invocation"):
        require(one_shot.get(key) is False, f"single use {key}")

    output = doc.get("output_publication", {})
    require(output.get("dtype") == "little-endian-f32" and output.get("shape") == [6144] and output.get("byte_length") == 24576, "output geometry")
    for key in ("finite", "descriptor_relative_temp_creation", "file_fsync", "no_replace_hard_link_publish", "parent_fsync", "descriptor_readback", "authority_requires_matching_complete_terminal"):
        require(output.get(key) is True, f"publication {key}")
    require(output.get("overwrite") is False and output.get("partial_output_authority") is False, "publication exclusion")

    reproduction = doc.get("reproduction", {})
    require(reproduction.get("runs") == 2 and reproduction.get("fresh_processes") == 2, "2/2 reproduction")
    require(reproduction.get("exact_primary_output_identity") == "2_OF_2", "reproduction identity")
    require(reproduction.get("checkpoint_reads") == 0 and reproduction.get("shard_opens") == 0, "reproduction access")
    require(reproduction.get("routed_aggregate_executions") == 0 and reproduction.get("ffn_completions") == 0 and reproduction.get("s2_constructions") == 0, "reproduction boundary")

    accounting = doc.get("accounting", {})
    require(accounting == {"starting_ledger": 175, "terminal_ledger": 175, "checkpoint_reads": 0, "shard_opens": 0, "preparation_shared_expert_executions": 0, "future_shared_expert_executions": 1, "verification_reproduction_computations": 2, "routed_aggregate_executions": 0, "ffn_completions": 0, "s2_constructions": 0}, "accounting")
    prohibited = doc.get("prohibitions", {})
    for key in ("checkpoint_access", "checkpoint_fallback", "shard_open", "historical_direct_dprefix_input", "historical_shared_output_substitution", "routed_shared_combination", "routed_aggregate_execution", "ffn_completion", "s2_construction", "gpu", "blas", "alternate_executor", "caller_selected_paths", "overwrite", "retry", "resume", "second_attempt", "go_token_in_this_phase"):
        require(prohibited.get(key) is True, f"prohibition {key}")
    require(doc.get("stop_boundary") == "AFTER_REPRESENTATIVE_SHARED_EXPERT_OUTPUT_ONLY", "stop boundary")
    require(doc.get("future_approval", {}).get("separate_committed_independent_approval_required") is True, "future approval")
    require(doc.get("future_approval", {}).get("token_exact_fields") == ["approval_sha256", "attempt_id", "authorization_sha256", "disposition", "event_id", "real_event_authorized", "release_id", "release_sha256"], "token schema")
    did = doc.get("defense_in_depth_closeout", {})
    require(did.get("D1") == "CLOSED_BY_DESCRIPTOR_RELATIVE_PUBLICATION_AND_READBACK", "D1")
    require(did.get("D2") == "CLOSED_BY_FIXED_MACHINE_WIDE_STATE_AND_OUTPUT_ROOTS", "D2")
    require(did.get("D3") == "CLOSED_BY_HASHING_EXACT_PARSED_AUTHORIZATION_BYTES", "D3")
    require(did.get("D4") == "CLOSED_BY_BOUND_INPUT_VOCABULARY_ARTIFACT", "D4")
    require(did.get("D5") == "RETAINED_DEFENSE_IN_DEPTH_UNREACHABLE_FROM_WRAPPER_OR_CLI", "D5")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, default=DEFAULT_RELEASE)
    args = parser.parse_args()
    doc = load(args.release)
    validate_release(doc, repo_mode=args.release.resolve() == DEFAULT_RELEASE.resolve())
    print("REPRESENTATIVE_SHARED_EXPERT_SINGLE_USE_RELEASE_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
