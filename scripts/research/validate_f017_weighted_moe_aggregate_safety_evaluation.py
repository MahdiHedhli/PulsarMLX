#!/usr/bin/env python3
"""Validate the public F017 weighted-MoE aggregate evaluation evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.research import evaluate_f017_weighted_moe_aggregate_safety as evaluator


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-weighted-moe-aggregate-safety-evaluation-v1.json"
EVIDENCE_SHA256 = "672884e0c217600f9104d7a4d6fdd27a87e0a73fac686044de86461af98781e7"


class AggregateEvaluationValidationError(ValueError):
    """Fail-closed public evidence validation error."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AggregateEvaluationValidationError(message)


def validate_document(document: dict[str, Any]) -> None:
    required = {
        "schema", "schema_version", "starting_authoritative_head", "consumer_id", "authority",
        "inputs", "nominal_aggregate", "enclosures", "bounds", "budgets", "qualifications",
        "private_artifact_verification", "isolation", "historical_immutability",
    }
    require(set(document) == required, "top-level evidence fields")
    require(document.get("schema") == "pulsarmlx.f017.weighted-moe-aggregate-safety-evaluation"
            and document.get("schema_version") == "1.0.0", "evidence schema")
    require(document.get("starting_authoritative_head") == evaluator.STARTING_HEAD, "starting head")
    require(document.get("consumer_id") == evaluator.CONSUMER_ID, "consumer identity")
    authority = document.get("authority", {})
    require(authority == {
        "DPREFIX_EXACT_1_sha256": evaluator.CANONICAL_STATE_SHA256,
        "aggregate_contract_sha256": evaluator.AGGREGATE_CONTRACT_SHA256,
        "aggregate_implementation_sha256": evaluator.AGGREGATE_IMPLEMENTATION_SHA256,
        "route_evidence_sha256": evaluator.ROUTE_EVIDENCE_SHA256,
        "weight_qualification_evidence_sha256": evaluator.WEIGHT_EVIDENCE_SHA256,
        "expert_output_reuse_authorization_sha256": evaluator.REUSE_AUTHORIZATION_SHA256,
    }, "authority identities")
    inputs = document.get("inputs", {})
    require(inputs.get("selected_expert_ids") == list(evaluator.SELECTED_IDS), "selected experts")
    require(inputs.get("joint_selected_weight_sum_interval") == {
        "lower": 2.4999999999999996, "upper": 2.5000000000000004,
    }, "joint selected-weight sum")
    require(set(inputs.get("expert_output_sha256_by_id", {})) == {str(value) for value in evaluator.SELECTED_IDS},
            "expert output inventory")
    nominal = document.get("nominal_aggregate", {})
    require(nominal.get("dtype") == "f64" and nominal.get("shape") == [6144]
            and nominal.get("finite_count") == 6144, "nominal aggregate surface")
    enclosures = document.get("enclosures", {})
    require(enclosures.get("selection_rule") ==
            "INTERSECTION_OF_FROZEN_DIRECT_AND_CENTERED_SOUND_ENCLOSURES", "enclosure selection")
    for name in ("direct", "normalization_centered", "sound_intersection"):
        require(enclosures.get(name, {}).get("component_count") == 6144, f"{name} census")
    bounds = document.get("bounds", {})
    require(bounds == {
        "maximum_absolute_perturbation": 1.3373477198218997e-05,
        "rmse_perturbation": 2.0649012042555876e-06,
        "cosine_similarity_lower_bound": 0.9990571244636769,
    }, "frozen evaluation bounds")
    budgets = document.get("budgets", {})
    require(budgets.get("maximum_absolute") == {
        "threshold": 0.015625, "pass": True, "factor": 1168.357321615716,
    }, "max-absolute qualification")
    require(budgets.get("rmse") == {
        "threshold": 0.0078125, "pass": True, "factor": 3783.4739908616907,
    }, "RMSE qualification")
    require(budgets.get("cosine") == {
        "minimum": 0.9999, "pass": False, "factor": 0.10605853704716413,
    }, "cosine qualification")
    require(budgets.get("global_aggregate_safety_factor") == 0.10605853704716413,
            "global safety factor")
    require(document.get("qualifications") == {
        "membership": "PASS_UNCHANGED_1984_OF_1984",
        "coefficient_rule": "FAIL_UNCHANGED_0_OF_8",
        "aggregate_mathematical": "FAIL",
        "aggregate_engineering_h2": "FAIL",
        "final_route_disposition": "ROUTE NOT PROVEN INVARIANT",
    }, "qualification disposition")
    private = document.get("private_artifact_verification", {})
    require(private.get("all_8_equal") is True
            and private.get("before_sha256_by_id") == private.get("after_sha256_by_id")
            and private.get("before_sha256_by_id") == inputs.get("expert_output_sha256_by_id"),
            "before/after expert output identities")
    require(private.get("read_only_single_link_regular_non_symlink") is True, "private immutability")
    require(document.get("isolation") == {
        "checkpoint_reads": 0, "shard_opens": 0, "payload_reads": 0,
        "candidate_or_model_dispatches": 0, "real_payload_ledger_before": 163,
        "real_payload_ledger_after": 163, "ledger_mutated": False,
    }, "zero-access ledger isolation")
    require(document.get("historical_immutability") == {
        "DPREFIX_REAL_1": "REJECTED_UNCHANGED", "DPREFIX_REAL_2": "REJECTED_UNCHANGED",
        "DPREFIX_REAL_3": "REJECTED_UNCHANGED", "DPREFIX_EXACT_1": "CANONICAL_UNCHANGED",
        "membership": "PASS_UNCHANGED_1984_OF_1984",
        "coefficient_qualification": "FAIL_UNCHANGED_0_OF_8",
    }, "historical immutability")
    public = json.dumps(document, sort_keys=True)
    require("/Users/" not in public and "/home/" not in public and "file://" not in public,
            "private path leak")


def validate_repository(private_root: Path | None = None) -> None:
    document = evaluator.load_json(EVIDENCE)
    require(evaluator.sha256_path(EVIDENCE) == EVIDENCE_SHA256, "evidence identity")
    validate_document(document)
    evaluator._source_authority()
    if private_root is not None:
        reproduced = evaluator.evaluate(private_root)
        require(evaluator.canonical_json_bytes(reproduced) == EVIDENCE.read_bytes(),
                "deterministic private-input replay")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-root", type=Path)
    args = parser.parse_args()
    validate_repository(args.private_root)
    print("F017_WEIGHTED_MOE_AGGREGATE_SAFETY_EVALUATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
