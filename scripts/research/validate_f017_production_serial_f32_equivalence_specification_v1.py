#!/usr/bin/env python3
"""Retained-only validator for the F017 production serial-f32 specification."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from typing import Any

from f017_bound_authority_resolver_v1 import (
    BoundAuthorityError,
    validate_bound_fields,
    validate_executable_numeric_bindings,
)


CONTRACT = pathlib.Path("specs/017-rust-native-inference-runtime/contracts/f017-production-serial-f32-equivalence-specification-v1.json")
REVIEW_RESULT = pathlib.Path("docs/architecture/reviews/evidence/f017-production-serial-f32-equivalence-cycle-01-independent-review-result-v1.json")
INTENDED = ["BYTE_EQUIVALENCE_REQUIRED", "NUMERICAL_EQUIVALENCE_REQUIRED", "INTENTIONAL_DISTINCTION_EXPECTED", "UNRESOLVED_PRODUCTION_SEMANTICS"]
EXECUTION = ["NOT_EXECUTED", "EXECUTION_AUTHORIZATION_REQUIRED", "READY_FOR_EXECUTION_PREPARATION", "BLOCKED"]
OBSERVED = ["BYTE_EQUIVALENT", "NUMERICALLY_EQUIVALENT_WITHIN_FROZEN_TOLERANCE", "INTENTIONALLY_DISTINCT", "FAILED_FROZEN_EQUIVALENCE_CONTRACT"]
REQUIRED_STAGE_IDS = {
    "attention_input_normalization", "q_rank_projection", "q_rank_normalization", "q_projection",
    "kv_a_projection", "compressed_kv_normalization", "rope", "compressed_kv_query_projection",
    "attention_scores", "softmax", "value_accumulation", "attention_output_projection",
    "s1_residual", "ffn_rmsnorm", "router_logits", "router_sigmoid_correction",
    "router_membership", "router_order", "routing_weight_normalization",
    "routed_gate_up_projection", "routed_silu", "routed_gate_up_product",
    "routed_down_projection", "routed_aggregate", "shared_expert", "routed_plus_shared_ffn",
    "s2_residual",
}
EXPECTED_SOURCE_HASHES = {
    "crates/engine/src/lib.rs": "20f672f194b0076c2634c79248e00b2c8a3121a1920adfaa9dda01afbf45b406",
    "crates/kernels/cuda/pulsar_kernels.cu": "0289a24bfd5d4c1ff0cc6632426228f5a5911c18c5acb5110dd3254fe4f39c97",
    "crates/kernels/cuda/mla_kernels.inc": "1c02821bd546d585d6f0a4b7d25c1919b05e762ac3bbb38fa32c56f4ea8430d9",
    "crates/stream/src/apple_mlx_bridge.mm": "27616c153cfe89e9ba81b6deb34109a607ebf3e0a07bc4d87e6b32857466f40d",
    "crates/f017-runner/src/layer_qualification.rs": "4b70a22816a1a14d990bee15a5e57e1ea1963b1c37a666b89b07fa6633b240e3",
    "crates/f017-runner/src/tiny_model.rs": "032e67eb97fd97525a3ca0673a9917f419881226fa1c41020f7ee0ec1c32dc0b",
}
EXACT_METRICS = {
    ("routing_weight_frozen", "max_abs_error"): 0.00001,
    ("routing_weight_frozen", "engineering_half_interval_max_abs_error"): 0.000005,
    ("r10_intermediate", "max_abs_error"): 0.015625,
    ("r10_intermediate", "rmse"): 0.0078125,
    ("r10_intermediate", "cosine_similarity_min"): 0.9999,
    ("routed_aggregate_frozen", "max_abs_error"): 0.015625,
    ("routed_aggregate_frozen", "rmse"): 0.0078125,
    ("routed_aggregate_frozen", "cosine_similarity_min"): 0.9999,
    ("complete_layer_final", "max_abs_error"): 0.0625,
    ("complete_layer_final", "rmse"): 0.03125,
    ("complete_layer_final", "cosine_similarity_min"): 0.999,
}


class Invalid(RuntimeError):
    pass


def load_unique(path: pathlib.Path) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise Invalid(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    try:
        value = json.loads(path.read_text(), object_pairs_hook=pairs)
    except (OSError, json.JSONDecodeError) as exc:
        raise Invalid(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise Invalid(f"{path} must contain an object")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Invalid(message)


def verify_bound(repo: pathlib.Path, binding: dict[str, Any]) -> None:
    path = repo / binding["path"]
    require(path.is_file(), f"missing bound file {binding['path']}")
    require(sha256(path) == binding["sha256"], f"hash mismatch {binding['path']}")


def validate_contract(repo: pathlib.Path, data: dict[str, Any]) -> None:
    require(data.get("schema") == "pulsarmlx.f017.production-serial-f32-equivalence-specification", "wrong schema")
    require(data.get("schema_version") == "1.0.0", "wrong schema version")
    require(data.get("base_head") == "db60f6bd4aeffe6d2f85530ddf5e3bb0e1ebbf71", "wrong base head")
    require(data.get("branch") == "feat/017-real-checkpoint-runner", "wrong branch")
    closed = data.get("closed_program", {})
    for key in ("declaration", "package", "review"):
        verify_bound(repo, closed[key])
    require(closed["review"].get("reviewer_model") == "claude-fable-5", "closure reviewer substitution")
    require(closed["review"].get("verdict") == "ACCEPT", "closure not accepted")
    require(closed.get("production_serial_f32_equivalence_claimed") is False, "closed proof surface relabeled")

    inventory = data.get("implementation_inventory")
    require(isinstance(inventory, list) and len(inventory) == 8, "implementation inventory census")
    classes = {row.get("classification") for row in inventory}
    require(classes <= {"AUTHORITATIVE_PRODUCTION", "SUPPORTED_ALTERNATE", "REFERENCE_ONLY", "TEST_ONLY", "LEGACY", "DEAD_OR_UNREACHABLE", "UNRESOLVED"}, "unknown implementation classification")
    require(any(row.get("scope") == "CANONICAL_APPLE_FULL_SERIAL_F32_S0_TO_S2_RUNTIME" and row.get("classification") == "UNRESOLVED" for row in inventory), "missing Apple full-path blocker")
    for row in inventory:
        if row.get("path"):
            require(row["path"] in EXPECTED_SOURCE_HASHES, "altered implementation path")
            require(row.get("sha256") == EXPECTED_SOURCE_HASHES[row["path"]], f"altered source hash {row['path']}")
            require(sha256(repo / row["path"]) == row["sha256"], f"source bytes mismatch {row['path']}")
    engine = next(row for row in inventory if row.get("scope") == "EXTANT_FULL_LINUX_CUDA_RUNTIME_GRAPH")
    require(engine.get("entry_point") == "crates/engine/src/lib.rs::Model::eval_layer", "altered production symbol")

    vocab = data.get("vocabulary", {})
    require(vocab.get("intended_relationship") == INTENDED, "intended vocabulary changed")
    require(vocab.get("execution_status") == EXECUTION, "execution vocabulary changed")
    require(vocab.get("observed_result") == OBSERVED, "observed vocabulary changed")
    stages = data.get("stage_contracts")
    require(isinstance(stages, list), "stage contracts missing")
    require({row.get("id") for row in stages} == REQUIRED_STAGE_IDS, "stage census changed")
    require(len(stages) == len(REQUIRED_STAGE_IDS), "duplicate stages")
    for row in stages:
        require(row.get("relationship") in INTENDED, f"unknown relationship {row.get('id')}")
        require(row.get("execution_status") in EXECUTION, f"unknown execution status {row.get('id')}")
        require(row.get("observed_result") is None, f"stage claims result before execution {row.get('id')}")
        for field in ("source", "input", "output", "accumulator", "order", "rounding", "behavior", "metric"):
            require(field in row and row[field] not in (None, ""), f"missing {field} for {row.get('id')}")
    stage = {row["id"]: row for row in stages}
    require(stage["routed_aggregate"]["accumulator"] == "f32", "routed aggregate accumulator widened")
    require(stage["routed_aggregate"]["order"] == "SELECTED_SLOT_RANK_0_TO_7_SERIAL_LEFT_FOLD", "routed order changed")
    require(stage["routed_aggregate"]["relationship"] == "INTENTIONAL_DISTINCTION_EXPECTED", "proof/production aggregate distinction weakened")
    require(stage["s2_residual"]["rounding"] == "ONE_BINARY32_ROUNDING", "S2 rounding boundary deleted")
    require(stage["router_membership"]["relationship"] == "BYTE_EQUIVALENCE_REQUIRED", "route membership weakened")
    require(stage["router_order"]["relationship"] == "BYTE_EQUIVALENCE_REQUIRED", "route order removed")

    metrics = data.get("metrics", {})
    require(metrics.get("common", {}).get("relative_error", {}).get("enabled") is False, "relative error silently enabled")
    require(bool(metrics.get("common", {}).get("relative_error", {}).get("reason")), "relative-error disposition missing")
    for (group, field), expected in EXACT_METRICS.items():
        require(metrics.get(group, {}).get(field) == expected, f"threshold changed {group}.{field}")
    require(metrics["byte_equivalence"].get("canonical_bytes_exact") is True, "byte equivalence weakened")
    require(bool(metrics["expert_operand_bound"].get("per_coordinate")), "tolerance justification removed")
    for group in ("expert_operand_bound", "r10_intermediate", "routed_aggregate_frozen", "complete_layer_final", "r9_fixture_not_promoted"):
        verify_bound(repo, metrics[group]["source"])

    routing = data.get("routing_contract", {})
    require(routing.get("selected_membership") == "EXACT_REQUIRED", "route membership approximate")
    require(routing.get("selected_order") == "EXACT_REQUIRED", "route order not exact")
    require(routing.get("order_canonicalization") == "PROHIBITED", "route order canonicalization enabled")
    verify_bound(repo, routing["source"])
    try:
        bound_observations = validate_bound_fields(repo, data)
        numeric_observations = validate_executable_numeric_bindings(repo, data.get("executable_numeric_bindings", []))
    except BoundAuthorityError as exc:
        raise Invalid(str(exc)) from exc
    require(len(bound_observations) == 5, "bound-field census")
    require(len(numeric_observations) == 4, "executable-numeric census")

    matrix = data.get("retained_artifact_matrix")
    require(isinstance(matrix, list) and len(matrix) == 13, "retained matrix census")
    roles = {row.get("role") for row in matrix}
    require({"S0_NEUTRAL_INPUT", "ROUTED_AGGREGATE", "FFN", "S2", "ROUTED_EXPERT_RETAINED_WEIGHTS", "SHARED_EXPERT_RETAINED_WEIGHTS"} <= roles, "retained authority missing")
    expected_artifact_shas = {
        "S0_NEUTRAL_INPUT":"9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11",
        "ROUTED_AGGREGATE":"872487d337305aab82e80a87b84763b6e3dd2901f88ae2ed6b64277aba9a20f9",
        "SHARED_EXPERT_OUTPUT":"8285fecf6e3232f19a0cc11b5d98ee5003f036db6bcd3cd52a7e9dbde9bb1b5b",
        "FFN":"4d7aaeb58c4ee33dcaf2329c8cd46234d69ee7f16bb7e6338ac9e0b7a5e6ad1a",
        "S2":"0341314230654d21fa56506dfe601f90bdb603fc38fd1203b6dd62b1e54c98c1",
    }
    for row in matrix:
        if row.get("role") in expected_artifact_shas:
            require(row.get("sha256") == expected_artifact_shas[row["role"]], f"altered retained SHA {row['role']}")
        if row.get("path"):
            require((repo / row["path"]).is_file(), f"missing retained authority {row['path']}")

    checkpoint = data.get("checkpoint_access", {})
    require(checkpoint.get("decision") == "CHECKPOINT_ACCESS_REQUIRED: NO", "checkpoint decision changed")
    require(checkpoint.get("ledger") == 175, "checkpoint decision ledger changed")
    accounting = data.get("accounting", {})
    require(accounting.get("ledger_before") == 175 and accounting.get("ledger_after") == 175, "ledger changed")
    for field in ("checkpoint_reads", "shard_opens", "attention_executions", "expert_executions", "aggregate_executions", "shared_expert_executions", "ffn_compositions", "s1_materializations", "s2_constructions", "production_equivalence_executions"):
        require(accounting.get(field) == 0, f"nonzero execution counter {field}")
    reconciliation = data.get("master_ledger_reconciliation", {})
    require(reconciliation.get("status") == "PASS_APPEND_ONLY_V2", "master ledger not reconciled")
    require(reconciliation.get("receipt_chain_terminal_count") == 175, "receipt terminal count")
    verify_bound(repo, reconciliation["authoritative_ledger"])
    for key in ("current_adapter", "adapter_implementation", "reconstruction_validator", "supplemental_assurance"):
        verify_bound(repo, reconciliation[key])
    require(reconciliation.get("new_real_payload_consumption") == 0 and reconciliation.get("checkpoint_reads") == 0 and reconciliation.get("shard_opens") == 0, "reconciliation crossed payload boundary")
    rn1 = data.get("rn1_future_execution_gate", {})
    require(rn1.get("current_retained_only_spec_blocked_by_wrapper_fix") is False, "RN1 improperly blocks retained-only spec")
    require(rn1.get("next_execution_capable_generation_blocked_until_accepted") is True and len(rn1.get("requirements", [])) == 9, "RN1 future gate weakened")
    backlog = data.get("next_natural_rebind_backlog")
    require(isinstance(backlog, list) and len(backlog) == 5 and all(row.get("phase_blocking") is False and row.get("natural_generation") and row.get("disposition") for row in backlog), "rebind backlog")
    strengthened = data.get("strengthened_independent_review_schema", {})
    require(strengthened.get("required_from_cycle") == 2 and len(strengthened.get("fields", [])) == 11 and strengthened.get("historical_closure_artifacts_mutated") is False, "review schema strengthening")
    machinery = data.get("generic_validation_machinery", {})
    verify_bound(repo, machinery["bound_field_resolver"])
    require(machinery.get("bound_field_status") == "PASS_5_OF_5" and machinery.get("executable_numeric_status") == "PASS_4_OF_4", "generic validator status")
    phase = data.get("phase_disposition", {})
    require(phase.get("execution_status") == "BLOCKED", "unresolved implementation not blocking")
    require(phase.get("readiness") == "READY_FOR_PRODUCTION_SERIAL_F32_EQUIVALENCE_EXECUTION_PREPARATION: NO", "premature readiness")
    require(data.get("stop_boundary") == "AFTER_ACCEPTED_SPECIFICATION_REVIEW_BEFORE_ANY_PRODUCTION_EQUIVALENCE_EXECUTION_PREPARATION_OR_EXECUTION", "stop boundary changed")


def validate_review(repo: pathlib.Path, result_path: pathlib.Path) -> None:
    result = load_unique(result_path)
    require(result.get("schema") == "pulsarmlx.f017.production-serial-f32-equivalence-independent-review-result", "wrong review result schema")
    require(result.get("reviewer_model") == "claude-fable-5", "reviewer model substitution")
    require(result.get("verdict") == "ACCEPT", "review not accepted")
    require(result.get("blocking_findings") == 0, "BLOCKING findings remain")
    require(result.get("non_blocking_required_findings") == 0, "NON_BLOCKING_REQUIRED findings remain")
    response = result.get("exact_response", {})
    verify_bound(repo, response)
    request = result.get("exact_request", {})
    verify_bound(repo, request)
    require(result.get("reviewed_branch") == "feat/017-real-checkpoint-runner", "review branch mismatch")
    reviewed_head = result.get("reviewed_head")
    require(isinstance(reviewed_head, str) and len(reviewed_head) == 40, "reviewed head missing")
    require(isinstance(result.get("reviewer_track_or_invocation_identity"), str) and result["reviewer_track_or_invocation_identity"], "review invocation identity missing")
    require(isinstance(result.get("reviewed_artifact_hashes"), dict) and result["reviewed_artifact_hashes"], "reviewed hashes missing")
    require(isinstance(result.get("reviewer_tests"), list) and result["reviewer_tests"], "reviewer tests missing")
    findings = result.get("findings")
    require(isinstance(findings, list), "findings missing")
    require(all(isinstance(item, dict) and item.get("id") and item.get("severity") in {"BLOCKING", "NON_BLOCKING_REQUIRED", "DEFENSE_IN_DEPTH"} for item in findings), "finding schema")
    require(isinstance(result.get("finding_to_fix_mapping"), list), "finding-to-fix mapping missing")
    dispositions = result.get("defense_in_depth_dispositions", [])
    require(all(item.get("disposition") and item.get("why_non_blocking") for item in dispositions), "defense-in-depth finding lacks disposition")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--contract", type=pathlib.Path)
    parser.add_argument("--review-result", type=pathlib.Path)
    parser.add_argument("--pre-review", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    contract_path = args.contract or repo / CONTRACT
    try:
        validate_contract(repo, load_unique(contract_path))
        if not args.pre_review:
            validate_review(repo, args.review_result or repo / REVIEW_RESULT)
    except Invalid as exc:
        print(f"FAIL: {exc}")
        return 1
    print("PASS: F017 production serial-f32 equivalence specification")
    print("ledger=175 checkpoint_reads=0 shard_opens=0 production_equivalence_executions=0")
    print("execution_preparation=BLOCKED specification_validation=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
