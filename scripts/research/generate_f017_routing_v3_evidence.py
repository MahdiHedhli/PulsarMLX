#!/usr/bin/env python3
"""Generate checkpoint-free post-freeze F017 routing-v3 evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.research import f017_routing_contract_v3 as v3


CONTRACT = Path(
    "specs/017-rust-native-inference-runtime/contracts/f017-m1f-routing-contract-v3.json"
)
CONTRACT_SHA256 = "befbf30f85e12b779e7d5c778f337a5f7d6019a15805e04805a24e4903ea3969"
FORMULA_FREEZE_COMMIT = "e603a84ae78cbc9d3b8b2943d7d0ddf91e31d983"
CONTRACT_FREEZE_COMMIT = "9d133286c727db33fe716055dc9d48d77e8453ce"
CORRECTED_V2 = Path(
    "docs/architecture/reviews/evidence/f017-v2-recovery-summary-integrity-closure-v1.json"
)
CORRECTED_V2_SHA256 = "739db4e5319dbb0d8f08536b70f4ceb8cfcbe8e99f95ebca13555bb81fed09a7"


def _write(root: Path, relative: str, value: object) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(v3.canonical_json_bytes(value))


def _route_pairs(root: Path) -> tuple[v3.RoutingPair, ...]:
    route_path = root / "docs/architecture/reviews/evidence/f017-m1-f0-layer3-route-v1.json"
    if v3.sha256_path(route_path) != v3.ROUTE_SHA256:
        raise ValueError("accepted route identity mismatch")
    route = v3.parse_json_no_duplicates(route_path)
    return v3.atomic_pairs(route["top8_ids"], route["routing_weights"])


def _assert_frozen(root: Path) -> dict:
    if v3.sha256_path(root / CONTRACT) != CONTRACT_SHA256:
        raise ValueError("v3 pre-observation contract mismatch")
    if v3.sha256_path(root / CORRECTED_V2) != CORRECTED_V2_SHA256:
        raise ValueError("corrected v2 authority mismatch")
    contract = v3.parse_json_no_duplicates(root / CONTRACT)
    if contract["freeze"]["fixture_1_values_used_to_choose_coefficients_or_thresholds"]:
        raise ValueError("fixture 1 influenced frozen v3")
    return contract


def retrospective(root: Path) -> dict[str, object]:
    contract = _assert_frozen(root)
    oracle = _route_pairs(root)
    probabilities = v3.individual_probability_intervals(root)
    weights = v3.normalized_weight_intervals(probabilities, oracle)
    corrected = v3.parse_json_no_duplicates(root / CORRECTED_V2)
    v2_summary = corrected["authoritative_derived_summary"]
    membership = v2_summary["membership"]
    prospective_interval_min = min(
        float(value["positivity_safety_factor"]) for value in weights.values()
    )
    return {
        "schema": "pulsarmlx.f017.routing-v3-fixture1-retrospective",
        "schema_version": "1.0.0",
        "checkpoint_access": 0,
        "real_payload_ledger": 57,
        "pre_observation_freeze": {
            "contract_sha256": CONTRACT_SHA256,
            "formula_freeze_commit": FORMULA_FREEZE_COMMIT,
            "contract_freeze_commit": CONTRACT_FREEZE_COMMIT,
            "fixture_1_evaluation_after_freeze": True,
            "post_observation_retuning": "FORBIDDEN",
        },
        "accepted_route_sha256": v3.ROUTE_SHA256,
        "accepted_raw_v2_recovery_sha256": v3.RAW_RECOVERY_SHA256,
        "corrected_v2_summary_sha256": CORRECTED_V2_SHA256,
        "semantic_classification": contract["semantic_classification"],
        "oracle_pairs_rank_ordered": [
            {"expert_id": item.expert_id, "routing_weight": item.routing_weight}
            for item in oracle
        ],
        "oracle_rank_order": [item.expert_id for item in oracle],
        "canonical_semantic_pairs_id_ordered": [
            {"expert_id": item.expert_id, "routing_weight": item.routing_weight}
            for item in v3.canonical_semantic_pairs(oracle)
        ],
        "canonical_semantic_pairs_sha256": v3.canonical_semantic_sha256(oracle),
        "per_expert_weight_contract": {
            "candidate_observed": False,
            "status": "PREOBSERVATION_INTERVALS_INSTANTIATED_ORACLE_SELF_CONSISTENT",
            "all_oracle_weights_inside_intervals": True,
            "prospective_interval_positivity_minimum_safety_factor": prospective_interval_min,
            "future_candidate_must_pass_inherited_max_abs_error": v3.R10_ROUTING_WEIGHT_ATOL,
            "future_engineering_max_abs_error": v3.R10_ROUTING_WEIGHT_ATOL / v3.ENGINEERING_HEADROOM,
            "by_expert_id": {str(key): value for key, value in sorted(weights.items())},
        },
        "membership": {
            "exact_selected_set": sorted(item.expert_id for item in oracle),
            "worst_pair": membership["minimum_pair"],
            "minimum_mathematical_safety_factor": membership[
                "minimum_mathematical_safety_factor"
            ],
            "minimum_engineering_safety_factor": membership[
                "minimum_engineering_safety_factor"
            ],
            "mathematically_stable": membership["mathematically_stable"],
            "engineering_headroom": membership["engineering_headroom"],
        },
        "rank_diagnostics": {
            "historical_v2_route_order_stable": v2_summary["route_order_stable"],
            "historical_v2_worst_adjacent_pair": v2_summary["ordered"]["minimum_pair"],
            "historical_v2_minimum_safety_factor": v2_summary["ordered"][
                "minimum_mathematical_safety_factor"
            ],
            "v3_semantic_authority": False,
            "retained": True,
        },
        "accumulation": {
            "candidate_expert_outputs_observed": False,
            "policy_qualified_checkpoint_free": True,
            "runtime_policy_changed": False,
            "order_bound": contract["accumulation"]["order_difference_bound_per_element"],
            "future_m1f_requires_observed_bound_and_complete_layer_tier_b": True,
        },
        "retrospective_v3": {
            "semantic_routing_mathematical_status": "PRE_ADMISSION_MATHEMATICALLY_QUALIFIED",
            "engineering_status": "NO_ENGINEERING_HEADROOM",
            "m1f_candidate_execution_qualified": False,
            "reason": "membership is mathematically stable but its minimum factor 1.2497550469932908 is below H=2; no production candidate weights or complete layer were executed",
        },
        "fixture_1_disposition": "SEMANTICALLY_VALID_BUT_INSUFFICIENT_HEADROOM",
        "historical_v1_status_unchanged": True,
        "historical_v2_status_unchanged": True,
        "q6_k": "BLOCKED",
        "m1_f": "BLOCKED",
        "p1": "BLOCKED",
    }


def comparison() -> dict[str, object]:
    return {
        "schema": "pulsarmlx.f017.routing-contract-comparison",
        "schema_version": "1.0.0",
        "checkpoint_access": 0,
        "contracts": [
            {
                "version": "v1",
                "sha256": "da05364470f7fc5fbdc930441be1ea269af01b6a87173df34e467bcc0b0df9d7",
                "question": "Can the oracle rank-8/rank-9 boundary withstand independent score perturbations with historical S>=4?",
                "fixture_1": "UNSUITABLE_UNDER_V1",
                "historical_status_unchanged": True,
            },
            {
                "version": "v2",
                "sha256": v3.V2_CONTRACT_SHA256,
                "question": "Are exact selected membership and exact rank-ordered top-8 bytes pairwise stable?",
                "fixture_1": {
                    "membership_stable": True,
                    "membership_H2": False,
                    "order_stable": False,
                    "overall": "NOT_MATHEMATICALLY_STABLE",
                },
                "historical_status_unchanged": True,
            },
            {
                "version": "v3_candidate",
                "sha256": CONTRACT_SHA256,
                "question": "Does the candidate preserve exact expert membership and every expert-associated weight, with reduction-order effects numerically qualified?",
                "fixture_1": "PRE_ADMISSION_MATHEMATICALLY_QUALIFIED_BUT_NO_ENGINEERING_HEADROOM",
                "future_contract_only": True,
            },
        ],
        "historical_evidence_rewritten": False,
    }


def representative_target() -> dict[str, object]:
    return {
        "schema": "pulsarmlx.f017.routing-v3-representative-fixture-target",
        "schema_version": "1.0.0",
        "status": "PLANNING_ONLY_NOT_AUTHORIZED",
        "checkpoint_access": 0,
        "target": {
            "exact_selected_set_stability": True,
            "all_selected_ID_keyed_weights_qualified": True,
            "semantic_routing_mathematical_pass": True,
            "engineering_H2_pass": True,
            "deterministic_candidate_repeats": 10,
            "complete_layer_numerical_contract": "PASS",
            "rank_diagnostics_retained": True,
            "rank_equality_required": False,
            "runtime_accumulation_policy_disclosed_and_qualified": True,
            "separate_adversarial_stress_fixture": True,
        },
        "fixture_1_role": "ADVERSARIAL_STRESS_AND_SEMANTIC_BOUNDARY_EVIDENCE",
        "fixture_1_not_representative_reason": "membership mathematical safety factor 1.2497550469932908 is below engineering H=2",
        "planning_options": [
            {
                "option": "A_PRECOMMITTED_CORRELATED_SYNTHETIC_STATE",
                "representativeness": "medium",
                "cherry_picking_risk": "low if family and selection rule are frozen before real routing",
                "real_access_cost": "one immutable 12-payload package for a reviewed bounded family",
                "oracle_tractability": "high",
                "authorization": "NOT_AUTHORIZED",
            },
            {
                "option": "B_DETERMINISTIC_SEMANTIC_SURROGATE",
                "representativeness": "medium-low until correlation and scale provenance are independently justified",
                "cherry_picking_risk": "low",
                "real_access_cost": "same attention/router package after separate authorization",
                "oracle_tractability": "high",
                "authorization": "NOT_AUTHORIZED",
            },
            {
                "option": "C_FUTURE_REAL_LAYER3_ENTRY_STATE_CAPTURE",
                "representativeness": "highest",
                "cherry_picking_risk": "low only with prompt/token and capture policy frozen first",
                "real_access_cost": "embedding plus complete dense layers 0-2; substantially wider than M1-F0",
                "oracle_tractability": "requires a separately reviewed multi-layer oracle",
                "authorization": "NOT_AUTHORIZED",
            },
            {
                "option": "D_REPRESENTATIVE_PLUS_STRESS_SPLIT",
                "representativeness": "explicitly separates parity evidence from boundary sensitivity",
                "cherry_picking_risk": "controlled by freezing representative policy before route outcomes",
                "real_access_cost": "inherits the selected representative-source cost",
                "oracle_tractability": "source-dependent",
                "authorization": "NOT_AUTHORIZED",
            },
        ],
        "recommendation_for_review": "D with a separately reviewed representative source; retain fixture 1 as stress evidence. Decide between A and C before any new access.",
        "selection_based_on_route_outcome": False,
    }


def dense_prefix(root: Path) -> dict[str, object]:
    sources = [
        "scripts/research/provision_f017_checkpoint_manifest.py",
        "scripts/research/analyze_glm52_post_run.py",
        "crates/engine/src/lib.rs",
    ]
    return {
        "schema": "pulsarmlx.f017.layer3-entry-state-capture-characterization",
        "schema_version": "1.0.0",
        "status": "CHARACTERIZED_NOT_IMPLEMENTED_NOT_AUTHORIZED",
        "checkpoint_access": 0,
        "finding": "layers 0, 1, and 2 are leading dense blocks; layer 3 is the first MoE block",
        "metadata": {"glm-dsa.leading_dense_block_count": 3},
        "source_identities": [
            {"path": path, "sha256": v3.sha256_path(root / path)} for path in sources
        ],
        "future_gate_name": "F017 M1-FPREP REAL LAYER-3 ENTRY-STATE CAPTURE",
        "honest_boundary": "embedding plus complete transformer layers 0-2, then capture the exact layer-3 entry state",
        "not_a_single_layer_fixture_operation": True,
        "estimated_scope": {
            "conceptual_layers_executed": 3,
            "embedding_required": True,
            "tensor_payload_count": "TO_BE_DERIVED_FROM_EXACT_PRECOMMITTED_PROMPT_AND_GLM52_MAP",
            "tensor_families": [
                "token_embedding",
                "layers_0_2_attention_norm_and_MLA_DSA",
                "layers_0_2_attention_output",
                "layers_0_2_dense_FFN_norm_gate_up_down",
            ],
            "quantization_families": "TO_BE_INVENTORIED_AND_REAL_BYTE_QUALIFIED_BEFORE AUTHORIZATION",
            "compute": "three complete dense transformer layers",
            "oracle_feasibility": "possible but materially broader; requires independent embedding and three-layer composition",
        },
        "disguising_multi_layer_execution_as_fixture_capture": "FORBIDDEN",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.repository_root.resolve()
    outputs = {
        "docs/architecture/reviews/evidence/f017-routing-v3-fixture1-retrospective-v1.json": retrospective(root),
        "docs/architecture/reviews/evidence/f017-routing-contract-comparison-v1.json": comparison(),
        "docs/architecture/reviews/evidence/f017-routing-v3-representative-target-v1.json": representative_target(),
        "docs/architecture/reviews/evidence/f017-routing-v3-dense-prefix-characterization-v1.json": dense_prefix(root),
    }
    for relative, value in outputs.items():
        _write(root, relative, value)
        print(f"{relative} {v3.sha256_path(root / relative)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
