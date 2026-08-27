#!/usr/bin/env python3
"""Mechanical gates for the Event-05 readiness-interface design authority."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-readiness-consumer-interface-v1.json"
DESIGN = ROOT / "docs/architecture/reviews/evidence/f017-event05-readiness-interface-design-authority-v1.json"
MUTATION_PLAN = ROOT / "docs/architecture/reviews/evidence/f017-event05-readiness-interface-mutation-plan-v1.json"
REPRODUCTION = ROOT / "docs/architecture/reviews/evidence/f017-event05-readiness-interface-mismatch-reproduction-v1.json"


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
    if type(predicates) is not dict or any(key not in fields for key in predicates):
        raise ValueError("readiness predicate census")
    free = contract.get("free_value_fields")
    if type(free) is not list or len(free) != len(set(free)) or any(name not in fields for name in free):
        raise ValueError("readiness free-value census")
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
    if plan.get("minimum_substantive_cases") < 200 or plan.get("minimum_planned_cases") < 200 or planned < 200:
        raise ValueError("readiness mutation floor")
    if plan.get("required_unexpected_passes") != 0:
        raise ValueError("readiness mutation expectation")
    if any(value != 0 for value in plan.get("required_side_effects", {}).values()):
        raise ValueError("readiness side-effect expectation")


def validate_design() -> dict:
    contract = load_contract()
    validate_contract(contract)
    design = json.loads(DESIGN.read_text())
    plan = json.loads(MUTATION_PLAN.read_text())
    reproduction = json.loads(REPRODUCTION.read_text())
    validate_mutation_plan(plan)
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
    )):
        raise ValueError("readiness design path")
    return {
        "schema":"pulsarmlx.f017.event05-readiness-interface-design-validation/1.0.0",
        "field_count":len(contract["required_fields"]),
        "uppercase_alias_fields":sum(field.upper() == field for field in contract["required_fields"]),
        "planned_mutations":sum(plan["categories"].values()),
        "checkpoint_access":0,
        "result":"PASS",
    }


def main() -> int:
    print(json.dumps(validate_design(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
