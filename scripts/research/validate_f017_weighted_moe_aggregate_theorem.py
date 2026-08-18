#!/usr/bin/env python3
"""Validate the synthetic-only F017 weighted-MoE aggregate theorem freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from scripts.research import validate_f017_selected_weight_acceptance as weight_validation
except ModuleNotFoundError:  # direct script execution from scripts/research
    import validate_f017_selected_weight_acceptance as weight_validation


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-weighted-moe-aggregate-perturbation-v1.json"
SPECIFICATION = ROOT / "docs/architecture/reviews/f017-weighted-moe-aggregate-perturbation-theorem.md"
IMPLEMENTATION = ROOT / "scripts/research/f017_weighted_moe_aggregate_theorem.py"
TESTS = ROOT / "scripts/research/tests/test_f017_weighted_moe_aggregate_theorem.py"
VALIDATOR_TESTS = ROOT / "scripts/research/tests/test_validate_f017_weighted_moe_aggregate_theorem.py"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-weighted-moe-aggregate-perturbation-freeze-v1.json"
LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"
PRIOR_QUALIFICATION_EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-selected-routing-weight-qualification-v1.json"

STARTING_HEAD = "7a72bff4bada524a5a57e7b21c31014004cfbc83"
PRIOR_QUALIFICATION_EVIDENCE_SHA256 = "834eefb7e0f127e12768285097dc3601135c1c1ff8ef0e871d65f59af1bc6b1f"
EXACT_STATE_SHA256 = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"


class AggregateFreezeValidationError(ValueError):
    pass


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AggregateFreezeValidationError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict):
        raise AggregateFreezeValidationError(f"expected JSON object: {path}")
    return value


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_source(item: dict[str, Any], root: Path) -> None:
    path = Path(str(item.get("path", "")))
    if path.is_absolute() or ".." in path.parts or sha256_path(root / path) != item.get("sha256"):
        raise AggregateFreezeValidationError(f"source identity: {path}")


def validate_contract(contract: dict[str, Any], root: Path = ROOT) -> None:
    if contract.get("schema") != "pulsarmlx.f017.weighted-moe-aggregate-perturbation-contract":
        raise AggregateFreezeValidationError("contract schema")
    if contract.get("schema_version") != "1.0.0" or contract.get("contract_id") != "f017-weighted-moe-aggregate-perturbation-v1":
        raise AggregateFreezeValidationError("contract version")
    if contract.get("status") != "FROZEN_BEFORE_REAL_F017_EXPERT_OUTPUT_EVALUATION":
        raise AggregateFreezeValidationError("freeze timing")

    anti = contract.get("anti_fitting", {})
    if anti != {
        "real_f017_expert_outputs_loaded": False,
        "real_f017_expert_outputs_evaluated": False,
        "real_f017_aggregate_values_loaded": False,
        "norm_or_reference_selected_from_real_outputs": False,
        "budget_selected_from_real_results": False,
        "later_input_resolution_and_evaluation_require_separate_bounded_loops": True,
    }:
        raise AggregateFreezeValidationError("anti-fitting declaration")

    authority = contract.get("authority_separation", {})
    if authority.get("coefficient_contract_sha256") != "ebf7c89543e95acecc067b1ee10883f7e9d564fc37be347480e40b02d3a8d7ca":
        raise AggregateFreezeValidationError("coefficient contract identity")
    if authority.get("coefficient_threshold") != 1.0e-5 or authority.get("coefficient_qualification") != "FAIL_UNCHANGED_0_OF_8":
        raise AggregateFreezeValidationError("coefficient authority")
    if authority.get("coefficient_pass_substitution") != "forbidden" or authority.get("current_route_disposition") != "ROUTE NOT PROVEN INVARIANT":
        raise AggregateFreezeValidationError("coefficient authority")

    semantics = contract.get("semantics", {})
    if semantics.get("protected_surface") != "routed_aggregate" or semantics.get("dimension") != 6144:
        raise AggregateFreezeValidationError("aggregate semantics")
    if semantics.get("shared_expert", "").startswith("added after routed_aggregate") is False:
        raise AggregateFreezeValidationError("shared-expert boundary")
    if semantics.get("residual", "").startswith("added after combined_moe") is False:
        raise AggregateFreezeValidationError("residual boundary")

    candidates = contract.get("budget_candidates", [])
    if len(candidates) != 3:
        raise AggregateFreezeValidationError("budget candidates")
    for candidate in candidates:
        path = Path(str(candidate.get("source_path", "")))
        if path.is_absolute() or ".." in path.parts or sha256_path(root / path) != candidate.get("source_sha256"):
            raise AggregateFreezeValidationError("budget source identity")
    accepted = contract.get("acceptance", {})
    if accepted.get("max_absolute_error") != 0.015625 or accepted.get("rmse") != 0.0078125 or accepted.get("cosine_similarity_minimum") != 0.9999:
        raise AggregateFreezeValidationError("accepted budget")
    if accepted.get("engineering_headroom") != 2.0 or accepted.get("additional_tolerances") != []:
        raise AggregateFreezeValidationError("unreviewed tolerance")

    theorem = contract.get("perturbation_theorem", {})
    required_theorem = ("weight_only", "joint", "direct_cross_check", "reference", "dependency_rule", "joint_sum_rule", "component_bound", "max_absolute_bound", "rmse_bound", "cosine_bound", "rounding")
    if any(not theorem.get(key) for key in required_theorem):
        raise AggregateFreezeValidationError("theorem completeness")
    if "intersect" not in theorem["dependency_rule"] or "common-denominator" not in theorem["joint_sum_rule"]:
        raise AggregateFreezeValidationError("coupling theorem")

    future = contract.get("required_future_evidence", [])
    if len(future) != 5 or [item.get("availability_class") for item in future] != ["A", "A", "D", "C", "D"]:
        raise AggregateFreezeValidationError("future evidence inventory")
    if "eight exact nominal real routed-expert" not in future[2].get("input", ""):
        raise AggregateFreezeValidationError("future evidence inventory")

    sources = contract.get("semantic_sources", [])
    if len(sources) != 5:
        raise AggregateFreezeValidationError("semantic source inventory")
    for item in sources:
        _validate_source(item, root)

    history = contract.get("historical_immutability", {})
    if history.get("selected_expert_ids") != [250, 10, 237, 73, 62, 177, 218, 28]:
        raise AggregateFreezeValidationError("selected-set history")
    if history.get("membership_1984_of_1984") != "PASS_UNCHANGED" or history.get("coefficient_qualification") != "FAIL_UNCHANGED_0_OF_8" or history.get("route_disposition") != "ROUTE NOT PROVEN INVARIANT":
        raise AggregateFreezeValidationError("historical authority")

    isolation = contract.get("isolation", {})
    if isolation != {
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "candidate_or_model_dispatches": 0,
        "real_expert_output_vectors_evaluated": 0,
        "real_aggregate_vectors_evaluated": 0,
        "real_payload_ledger_before": 139,
        "real_payload_ledger_after": 139,
    }:
        raise AggregateFreezeValidationError("isolation or ledger")

    public = json.dumps(contract, sort_keys=True)
    if "/Users/" in public or "/home/" in public or "file://" in public or "antecedents/" in public:
        raise AggregateFreezeValidationError("private path leak")


def validate_implementation(root: Path = ROOT) -> None:
    source = (root / IMPLEMENTATION.relative_to(ROOT)).read_text()
    forbidden = (
        "f017-selected-routing-weight-qualification-v1.json",
        "f017-dprefix-route-ambiguity-v31-evaluation-v1.json",
        "argparse",
        "Path(",
        ".open(",
        "read_text(",
        "read_bytes(",
    )
    if any(token in source for token in forbidden):
        raise AggregateFreezeValidationError("implementation exposes production input or I/O authority")
    required = (
        "R10_INTERMEDIATE_MAX_ABSOLUTE_ERROR = 0.015625",
        "R10_INTERMEDIATE_RMSE = 0.0078125",
        "R10_INTERMEDIATE_COSINE_MINIMUM = 0.9999",
        "joint_weight_sum_interval",
        "_intersect(direct, centered)",
        "def qualify_f017_production_aggregate(",
        "result.dimension != ROUTED_AGGREGATE_DIMENSION",
        "aggregate_factor >= ENGINEERING_HEADROOM",
    )
    if any(token not in source for token in required):
        raise AggregateFreezeValidationError("implementation rule drift")


def validate_history(root: Path = ROOT) -> None:
    weight_validation.validate_history(root)
    weight_validation.validate_contract(weight_validation.load_json(root / weight_validation.CONTRACT.relative_to(weight_validation.ROOT)), root)
    ledger = load_json(root / LEDGER.relative_to(ROOT))
    real2 = [item for item in ledger.get("events", []) if item.get("attempt") == "DPREFIX-REAL-2"]
    if len(real2) != 1 or real2[0].get("cumulative_tensor_payloads_after_event") != 139:
        raise AggregateFreezeValidationError("aggregate-freeze ledger boundary changed")
    if ledger.get("cumulative_tensor_payloads", 0) < 139:
        raise AggregateFreezeValidationError("real-payload ledger predates aggregate freeze")
    if sha256_path(root / PRIOR_QUALIFICATION_EVIDENCE.relative_to(ROOT)) != PRIOR_QUALIFICATION_EVIDENCE_SHA256:
        raise AggregateFreezeValidationError("prior qualification evidence changed")
    qualification = load_json(root / PRIOR_QUALIFICATION_EVIDENCE.relative_to(ROOT))
    if qualification.get("final_route_disposition") != "ROUTE NOT PROVEN INVARIANT":
        raise AggregateFreezeValidationError("prior route disposition changed")
    if qualification.get("qualification", {}).get("mathematical_pass_count") != 0:
        raise AggregateFreezeValidationError("coefficient result changed")


def validate_evidence(evidence: dict[str, Any], root: Path = ROOT) -> None:
    expected_keys = {
        "schema", "schema_version", "starting_head", "result", "authority",
        "anti_fitting", "semantics", "accepted_budget", "theorem", "future_evidence",
        "artifacts", "validation", "historical_immutability", "isolation", "next_action",
    }
    if set(evidence) != expected_keys:
        raise AggregateFreezeValidationError("freeze evidence schema drift")
    if evidence.get("schema") != "pulsarmlx.f017.weighted-moe-aggregate-perturbation-freeze" or evidence.get("schema_version") != "1.0.0":
        raise AggregateFreezeValidationError("freeze evidence identity")
    if evidence.get("starting_head") != STARTING_HEAD or evidence.get("result") != "AGGREGATE SAFETY THEOREM FROZEN":
        raise AggregateFreezeValidationError("freeze disposition")
    authority = evidence.get("authority", {})
    if authority.get("DPREFIX_EXACT_1_sha256") != EXACT_STATE_SHA256 or authority.get("route_disposition") != "ROUTE NOT PROVEN INVARIANT":
        raise AggregateFreezeValidationError("authority drift")
    if authority.get("prior_weight_qualification_evidence_sha256") != PRIOR_QUALIFICATION_EVIDENCE_SHA256:
        raise AggregateFreezeValidationError("prior evidence binding")
    if evidence.get("anti_fitting") != {
        "real_f017_expert_output_vectors_loaded": 0,
        "real_f017_aggregate_vectors_loaded": 0,
        "synthetic_or_symbolic_inputs_only": True,
        "real_output_based_threshold_or_reference_choices": 0,
    }:
        raise AggregateFreezeValidationError("freeze anti-fitting evidence")

    budget = evidence.get("accepted_budget", {})
    if budget != {"surface": "routed_aggregate", "max_absolute_error": 0.015625, "rmse": 0.0078125, "cosine_similarity_minimum": 0.9999, "engineering_headroom": 2.0}:
        raise AggregateFreezeValidationError("freeze budget")
    if evidence.get("future_evidence", {}).get("real_expert_output_availability") != "D_UNAVAILABLE_PENDING_SEPARATE_RESOLUTION":
        raise AggregateFreezeValidationError("future evidence disposition")

    artifacts = evidence.get("artifacts", [])
    if len(artifacts) != 7:
        raise AggregateFreezeValidationError("freeze artifact inventory")
    for item in artifacts:
        _validate_source(item, root)
    validation = evidence.get("validation", {})
    if validation.get("synthetic_test_count", 0) < 19 or validation.get("property_samples_contained") is not True:
        raise AggregateFreezeValidationError("synthetic validation")
    if validation.get("real_expert_outputs_evaluated") is not False or validation.get("deterministic_replay") is not True or validation.get("mutation_fail_closed") is not True:
        raise AggregateFreezeValidationError("validation authority")

    if evidence.get("historical_immutability") != {
        "DPREFIX_REAL_1": "REJECTED_UNCHANGED",
        "DPREFIX_REAL_2": "REJECTED_UNCHANGED",
        "DPREFIX_REAL_3": "REJECTED_UNCHANGED",
        "DPREFIX_EXACT_1": "CANONICAL_UNCHANGED",
        "selected_set": [250, 10, 237, 73, 62, 177, 218, 28],
        "membership_1984_of_1984": "PASS_UNCHANGED",
        "coefficient_qualification": "FAIL_UNCHANGED_0_OF_8",
        "route_disposition": "ROUTE NOT PROVEN INVARIANT",
    }:
        raise AggregateFreezeValidationError("historical classification drift")
    if evidence.get("isolation") != {
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "candidate_or_model_dispatches": 0,
        "real_payload_ledger_before": 139,
        "real_payload_ledger_after": 139,
    }:
        raise AggregateFreezeValidationError("freeze isolation")
    public = json.dumps(evidence, sort_keys=True)
    if "/Users/" in public or "/home/" in public or "file://" in public or "antecedents/" in public:
        raise AggregateFreezeValidationError("freeze path leak")


def validate_repository(root: Path = ROOT) -> None:
    validate_contract(load_json(root / CONTRACT.relative_to(ROOT)), root)
    validate_implementation(root)
    validate_history(root)
    validate_evidence(load_json(root / EVIDENCE.relative_to(ROOT)), root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    validate_repository(ROOT)
    print("WEIGHTED_MOE_AGGREGATE_PERTURBATION_FREEZE_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
