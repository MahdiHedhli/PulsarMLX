#!/usr/bin/env python3
"""Mechanical gates for the Event-05 readiness-interface design authority."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-readiness-consumer-interface-v3.json"
DESIGN = ROOT / "docs/architecture/reviews/evidence/f017-event05-readiness-interface-design-authority-v3.json"
MUTATION_PLAN = ROOT / "docs/architecture/reviews/evidence/f017-event05-readiness-interface-mutation-plan-v3.json"
REPRODUCTION = ROOT / "docs/architecture/reviews/evidence/f017-event05-readiness-interface-mismatch-reproduction-v1.json"
MANIFEST = ROOT / "docs/architecture/reviews/evidence/f017-event05-readiness-interface-authority-manifest-v5.json"

EXPECTED_FREE_VALUE_FIELDS = {
    "authority_manifest_path", "authority_manifest_sha256", "scientific_access_contract_path",
    "scientific_access_contract_sha256", "result_authority_path", "result_authority_sha256",
    "numerical_contract_path", "numerical_contract_sha256", "measured_implementation_head",
    "measured_implementation_tree", "full_native_evidence_path", "full_native_evidence_sha256",
    "full_native_run", "evidence_only_evidence_path", "evidence_only_evidence_sha256",
    "evidence_only_run", "gemini_result_path", "gemini_result_sha256", "opus_result_path",
    "opus_result_sha256", "defense_in_depth_findings",
}
EXPECTED_SAFETY_PREDICATES = {
    "schema":"pulsarmlx.f017.corrected-oracle-event05-execution-readiness-final-declaration/11.1.0",
    "event_04_retry":False, "event_04_resume":False, "event_05_executed":False,
    "live_event_05_authorization_created":False, "event_05_package_started":False,
    "primary_real_oracle_event05_executions":0, "secondary_real_oracle_event05_executions":0,
    "new_original_checkpoint_shard_opens":0, "new_original_checkpoint_identity_hash_reads":0,
    "new_original_checkpoint_mmaps":0, "new_original_checkpoint_tensor_reads":0,
    "new_original_checkpoint_payload_reads":0, "p1_attempt_2_executed":False,
    "live_p1_attempt_2_authorization_created":False, "historical_master_ledger":175,
    "ready_for_corrected_full_checkpoint_oracle_event_05_execution_go":True,
    "ready_to_prepare_p1_attempt_2_authorization":False,
    "exact_next_safe_action":"REQUEST_A_FRESH_HUMAN_GO_FOR_EXACTLY_ONE_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_05_UNDER_RECONCILED_V11_READINESS_AUTHORITY",
}
REQUIRED_NAMED_MUTATIONS = {
    "PRETTY_PRINTED_DECLARATION", "UNSORTED_DECLARATION_KEYS", "MISSING_TERMINAL_NEWLINE",
    "WRONG_SCHEMA_VALUE", "ZERO_FULL_NATIVE_RUN", "ZERO_EVIDENCE_ONLY_RUN",
    "EXPIRED_LIVE_APPROVAL", "FALSE_LIVE_APPROVAL", "VALIDATION_ONLY_APPROVAL_INSTALL_ATTEMPT",
    "CANDIDATE_POSTURE_NONALLOWLIST_DIVERGENCE",
}

REQUIRED_MANIFEST_ROLES = {
    "terminal_pre_mint_failure", "accepted_predecessor_authority_manifest",
    "accepted_implementation_measurement", "accepted_scientific_access",
    "accepted_numerical_contract_v4", "accepted_result_authority_v11",
    "accepted_full_native_ci", "mismatch_reproduction", "versioning_decision",
    "consumer_interface", "approval_interface", "design_authority",
    "mutation_plan", "review_protocol", "historical_tombstone",
    "design_validator", "design_tests", "claim_ledger", "challenge_ledger",
    "support_ledger", "arbiter_ledger", "graph_state", "r1_repair_receipt",
    "r2_repair_receipt", "r3_receipt", "r4_receipt", "opus_design_exact_response",
    "opus_design_normalized_result",
}


def load_contract() -> dict:
    return json.loads(CONTRACT.read_text())


def _repository_path(value: object) -> bool:
    if type(value) is not str or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts


def validate_contract(contract: dict) -> None:
    fields = contract.get("required_fields")
    if type(fields) is not list or len(fields) != contract.get("field_count") or len(fields) != len(set(fields)):
        raise ValueError("readiness field count")
    if any(type(field) is not str or field.lower() != field for field in fields):
        raise ValueError("readiness lower-case field vocabulary")
    if contract.get("field_vocabulary") != "LOWERCASE_SNAKE_CASE_ONLY":
        raise ValueError("readiness field vocabulary")
    aliases = contract.get("alias_policy")
    if type(aliases) is not dict or any(value is not False for value in aliases.values()):
        raise ValueError("readiness alias policy")
    exact_types = contract.get("exact_types")
    if type(exact_types) is not dict:
        raise ValueError("readiness exact types")
    typed = []
    for names in exact_types.values():
        if type(names) is not list:
            raise ValueError("readiness type census")
        typed.extend(names)
    if len(typed) != len(set(typed)) or any(name not in fields for name in typed):
        raise ValueError("readiness type overlap")
    if set(typed) != set(fields):
        raise ValueError("readiness type exhaustiveness")
    predicates = contract.get("exact_final_predicates")
    prepared = contract.get("exact_prepared_predicates")
    if type(predicates) is not dict or any(key not in fields for key in predicates):
        raise ValueError("readiness predicate census")
    if type(prepared) is not dict or set(prepared) != set(predicates):
        raise ValueError("readiness prepared predicate census")
    free = contract.get("free_value_fields")
    if type(free) is not list or len(free) != len(set(free)) or any(name not in fields for name in free):
        raise ValueError("readiness free-value census")
    if set(free) != EXPECTED_FREE_VALUE_FIELDS:
        raise ValueError("readiness frozen free-value census")
    if set(predicates) & set(free) or set(predicates) | set(free) != set(fields):
        raise ValueError("readiness predicate coverage")
    type_map = {name: category for category, names in exact_types.items() for name in names}
    for name, value in predicates.items():
        category = type_map[name]
        valid = (
            (category == "boolean_fields" and type(value) is bool)
            or (category == "non_boolean_nonnegative_integer_fields" and type(value) is int and type(value) is not bool and value >= 0)
            or (category == "positive_integer_fields" and type(value) is int and type(value) is not bool and value > 0)
            or (category in {"exact_string_fields", "sha256_fields", "git_object_fields", "repository_relative_path_fields"} and type(value) is str)
        )
        if not valid:
            raise ValueError(f"readiness predicate type: {name}")
    for name, required in EXPECTED_SAFETY_PREDICATES.items():
        if predicates.get(name) != required or type(predicates.get(name)) is not type(required):
            raise ValueError(f"readiness frozen safety predicate: {name}")
    if (prepared.get("authority_scope") != "VALIDATION_ONLY_PREPARED"
            or prepared.get("ready_for_corrected_full_checkpoint_oracle_event_05_execution_go") is not False
            or prepared.get("gemini_verdict") != "VALIDATION_ONLY_PREPARED"
            or prepared.get("opus_verdict") != "VALIDATION_ONLY_PREPARED"):
        raise ValueError("readiness prepared scope")
    if set(contract.get("scope_policy", {})) != {"FINAL_EVENT05_EXECUTION_READINESS", "VALIDATION_ONLY_PREPARED"}:
        raise ValueError("readiness scope policy")
    for name in exact_types["repository_relative_path_fields"]:
        if not name.endswith("_path"):
            raise ValueError("readiness path field")
    if contract.get("canonical_serialization") != "REQUIRED" or contract.get("bounded_decode") != "REQUIRED_BEFORE_SEMANTIC_VALIDATION":
        raise ValueError("readiness decode order")
    emitter = contract.get("declaration_emitter")
    if type(emitter) is not dict or emitter.get("serialization") != "f017_canonical_serialization_v10.canonical_bytes":
        raise ValueError("readiness declaration emitter")


def validate_mutation_plan(plan: dict) -> None:
    categories = plan.get("categories")
    if type(categories) is not dict or any(type(value) is not int or value <= 0 for value in categories.values()):
        raise ValueError("readiness mutation categories")
    planned = sum(categories.values())
    if (plan.get("minimum_substantive_cases") != 245 or plan.get("minimum_planned_cases") != 251
            or planned != plan.get("minimum_planned_cases") or planned < plan.get("minimum_substantive_cases")):
        raise ValueError("readiness mutation floor")
    if set(plan.get("mandatory_named_mutations", [])) != REQUIRED_NAMED_MUTATIONS:
        raise ValueError("readiness mandatory mutation census")
    if plan.get("required_unexpected_passes") != 0:
        raise ValueError("readiness mutation expectation")
    if any(value != 0 for value in plan.get("required_side_effects", {}).values()):
        raise ValueError("readiness side-effect expectation")


def validate_authority_manifest(manifest: dict) -> dict:
    artifacts = manifest.get("artifacts")
    if type(artifacts) is not list or manifest.get("binding_count") != len(artifacts):
        raise ValueError("authority manifest binding count")
    roles = [item.get("role") for item in artifacts if type(item) is dict]
    if len(roles) != len(artifacts) or len(roles) != len(set(roles)):
        raise ValueError("authority manifest role census")
    if not REQUIRED_MANIFEST_ROLES.issubset(roles):
        raise ValueError("authority manifest required roles")
    for item in artifacts:
        path = item.get("path")
        digest = item.get("sha256")
        if not _repository_path(path) or type(digest) is not str or len(digest) != 64:
            raise ValueError("authority manifest artifact")
        target = ROOT / path
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError(f"authority manifest sha: {item.get('role')}")
    return {"binding_count": len(artifacts), "sha_mismatches": 0}


def validate_design() -> dict:
    contract = load_contract()
    validate_contract(contract)
    design = json.loads(DESIGN.read_text())
    plan = json.loads(MUTATION_PLAN.read_text())
    reproduction = json.loads(REPRODUCTION.read_text())
    manifest = json.loads(MANIFEST.read_text())
    validate_mutation_plan(plan)
    manifest_report = validate_authority_manifest(manifest)
    if design.get("authorizer_design", {}).get("parallel_ad_hoc_readiness_checks") != 0:
        raise ValueError("parallel readiness logic")
    if design.get("validation_only_isolation", {}).get("installation_guard") != "REVALIDATE_BOUND_APPROVAL_AS_LIVE_BEFORE_INSTALL":
        raise ValueError("validation-only installation guard")
    if reproduction.get("root_cause") != "PRODUCER_AND_CONSUMER_WERE_VALIDATED_SEPARATELY_BUT_NEVER_INSTANTIATED_TOGETHER":
        raise ValueError("readiness root cause")
    if any(not _repository_path(path) for path in (
        design["canonical_contract"],
        design["validator_design"]["path"],
        design["authorizer_design"]["path"],
        design["candidate_builder_design"]["path"],
        design["approval_admission_design"]["path"],
    )):
        raise ValueError("readiness design path")
    return {
        "schema":"pulsarmlx.f017.event05-readiness-interface-design-validation/1.0.0",
        "field_count":len(contract["required_fields"]),
        "uppercase_alias_fields":sum(field.upper() == field for field in contract["required_fields"]),
        "planned_mutations":sum(plan["categories"].values()),
        "authority_bindings":manifest_report["binding_count"],
        "checkpoint_access":0,
        "result":"PASS",
    }


def main() -> int:
    print(json.dumps(validate_design(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
