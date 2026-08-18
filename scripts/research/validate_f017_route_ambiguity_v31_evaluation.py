#!/usr/bin/env python3
"""Validate the committed F017 routing-contract v3.1 real-box evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any

import f017_route_ambiguity_v31_evaluation as evaluation
import f017_routing_contract_v31 as theorem
import validate_f017_v2_antecedent_private_reuse as reuse


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-dprefix-route-ambiguity-v31-evaluation-v1.json"
SCHEMA = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-dprefix-route-ambiguity-v31-evaluation-v1.schema.json"
EXPECTED_ROOT_KEYS = {
    "schema", "schema_version", "schema_contract", "starting_authoritative_head",
    "consumer_id", "scope", "authority", "private_reuse", "evaluation",
    "deterministic_replay", "expectation_check", "historical_immutability",
    "isolation", "result",
}


class ValidationError(ValueError):
    pass


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def _same_number(left: Any, right: Any) -> bool:
    if isinstance(left, str) or isinstance(right, str):
        return left == right
    return float(left) == float(right)


def validate_document(document: dict[str, Any]) -> None:
    if set(document) != EXPECTED_ROOT_KEYS:
        raise ValidationError("evaluation root schema drift")
    if document["schema"] != "pulsarmlx.f017.dprefix-route-ambiguity-v3.1-evaluation" or document["schema_version"] != "1.0.0":
        raise ValidationError("evaluation schema identity")
    schema_contract = document["schema_contract"]
    if schema_contract != {
        "path": "specs/017-rust-native-inference-runtime/contracts/f017-dprefix-route-ambiguity-v31-evaluation-v1.schema.json",
        "sha256": evaluation.EVALUATION_SCHEMA_SHA,
    } or evaluation.sha256_path(SCHEMA) != evaluation.EVALUATION_SCHEMA_SHA:
        raise ValidationError("evaluation schema binding")
    if document["starting_authoritative_head"] != evaluation.STARTING_HEAD:
        raise ValidationError("starting head")
    if document["consumer_id"] != evaluation.CONSUMER_ID or document["scope"] != "ANALYTICAL_ROUTE_PLANNING_ONLY":
        raise ValidationError("consumer or scope")

    authority = document["authority"]
    expected_authority = {
        "DPREFIX_EXACT_1_sha256": evaluation.EXACT_SHA,
        "REAL_2_state_sha256": evaluation.REAL2_SHA,
        "REAL_3_state_sha256": evaluation.REAL3_SHA,
        "routing_contract_v3_1_sha256": evaluation.V31_CONTRACT_SHA,
        "routing_implementation_v3_1_sha256": evaluation.V31_IMPLEMENTATION_SHA,
        "routing_specification_v3_1_sha256": evaluation.V31_SPECIFICATION_SHA,
        "routing_freeze_evidence_sha256": evaluation.V31_FREEZE_EVIDENCE_SHA,
        "private_reuse_authorization_sha256": evaluation.PRIVATE_REUSE_AUTHORIZATION_SHA,
        "private_manifest_sha256": evaluation.PRIVATE_MANIFEST_SHA,
        "recovery_result_sha256": evaluation.RECOVERY_RESULT_SHA,
        "correction_bias_sha256": evaluation.ROUTER_BIAS_SHA,
    }
    for key, value in expected_authority.items():
        if authority.get(key) != value:
            raise ValidationError(f"authority drift: {key}")
    tool = authority.get("evaluation_tool", {})
    tool_path = "scripts/research/f017_route_ambiguity_v31_evaluation.py"
    historical_tool = subprocess.run(
        ["git", "show", f"eb1701732b9c729fb6357c98bed7aaf03a95b004:{tool_path}"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    historical_sha = hashlib.sha256(historical_tool.stdout).hexdigest() if historical_tool.returncode == 0 else ""
    if tool.get("path") != tool_path or tool.get("sha256") not in {evaluation.sha256_path(Path(evaluation.__file__)), historical_sha}:
        raise ValidationError("evaluation-tool identity")
    evaluation._assert_public_identities()

    private = document["private_reuse"]
    manifest = reuse.load_json(evaluation.PRIVATE_MANIFEST)
    inventory = reuse.expected_inventory(manifest)
    expected_hashes = {item["symbolic_name"]: item["sha256"] for item in inventory}
    if private.get("artifact_count") != 8 or private.get("before_sha256") != expected_hashes:
        raise ValidationError("private before identity")
    if private.get("after_sha256") != expected_hashes or private.get("unchanged") is not True:
        raise ValidationError("private after identity")
    if private.get("authorized_symbolic_names") != [item["symbolic_name"] for item in inventory]:
        raise ValidationError("private inventory ordering")
    if private.get("machine_local_paths_published") is not False:
        raise ValidationError("private path policy")

    result = document["evaluation"]
    ambiguity = result["ambiguity_set"]
    if ambiguity.get("center") != "DPREFIX-EXACT-1" or ambiguity.get("component_count") != 6144:
        raise ValidationError("ambiguity center")
    if ambiguity.get("componentwise_radius_max") != 1.1175870895385744e-08:
        raise ValidationError("ambiguity max radius")
    if ambiguity.get("l2_radius") != 2.0736155800732256e-07:
        raise ValidationError("ambiguity L2 radius")

    route = result["exact_route"]
    ranking = route.get("ranking", [])
    if len(ranking) != 256 or set(ranking) != set(range(256)):
        raise ValidationError("ranking is not a 256-expert permutation")
    selected = tuple(route.get("selected_top8", []))
    if len(selected) != 8 or tuple(ranking[:8]) != selected or route.get("selected_set") != sorted(selected):
        raise ValidationError("selected top-8 binding")
    experts = result.get("experts", [])
    if len(experts) != 256 or [item.get("expert_id") for item in experts] != list(range(256)):
        raise ValidationError("expert analytical surface")
    recomputed_ranking = theorem.select_top_k_diagnostic([item["exact_score"] for item in experts], top_k=256)
    if list(recomputed_ranking) != ranking:
        raise ValidationError("ranking recomputation")

    membership = result["membership"]
    pairs = membership.get("pairs", [])
    expected_pairs = {(selected_id, challenger_id) for selected_id in selected for challenger_id in ranking[8:]}
    actual_pairs = {(item.get("selected_expert_id"), item.get("challenger_expert_id")) for item in pairs}
    if len(pairs) != 1984 or actual_pairs != expected_pairs:
        raise ValidationError("membership pair completeness")
    reconstructed = []
    for item in pairs:
        selected_id = item["selected_expert_id"]
        challenger_id = item["challenger_expert_id"]
        selected_interval = theorem.Interval(**item["selected_score_interval"])
        challenger_interval = theorem.Interval(**item["challenger_score_interval"])
        pair = theorem.pair_safety(
            selected_id,
            challenger_id,
            selected_interval,
            challenger_interval,
            experts[selected_id]["exact_score"],
            experts[challenger_id]["exact_score"],
        )
        expected_values = {
            "exact_selected_score": experts[selected_id]["exact_score"],
            "exact_challenger_score": experts[challenger_id]["exact_score"],
            "exact_positive_margin": pair.nominal_margin,
            "difference_lower": pair.difference.lower,
            "ambiguity_allowance": pair.ambiguity_allowance,
            "mathematical_safety_factor": "INFINITE" if pair.factor is None else pair.factor,
            "mathematical_pass": pair.mathematical_factor_pass,
            "engineering_h2_pass": pair.engineering_h2_pass,
        }
        for key, value in expected_values.items():
            if not _same_number(item.get(key), value):
                raise ValidationError(f"pair derivation mismatch: {key}")
        if item.get("score_difference_interval") != {"lower": pair.difference.lower, "upper": pair.difference.upper}:
            raise ValidationError("pair difference interval")
        reconstructed.append(pair)
    summary = theorem.summarize_pair_safety(reconstructed)
    required_summary = {
        "required": 1984,
        "evaluated": 1984,
        "mathematical_pass_count": sum(pair.mathematical_factor_pass for pair in reconstructed),
        "mathematical_fail_count": sum(not pair.mathematical_factor_pass for pair in reconstructed),
        "all_membership_invariant": summary["all_membership_invariant"],
        "minimum_mathematical_safety_factor": summary["minimum_safety_factor"],
        "worst_pair": summary["worst_pair"],
        "count_factor_below_1": summary["count_below_1"],
        "count_factor_below_2": summary["count_below_2"],
        "engineering_h2_pass_count": sum(pair.engineering_h2_pass for pair in reconstructed),
        "engineering_h2_fail_count": sum(not pair.engineering_h2_pass for pair in reconstructed),
        "median_finite_safety_factor": summary["median_finite_safety_factor"],
    }
    for key, value in required_summary.items():
        if membership.get(key) != value:
            raise ValidationError(f"membership summary mismatch: {key}")

    weights = result["selected_weights"]
    if weights.get("precondition_selected_set_invariant") is not True:
        raise ValidationError("weight fixed-set precondition")
    if weights.get("key_semantics") != "expert_id" or set(map(int, weights.get("by_expert_id", {}))) != set(selected):
        raise ValidationError("weight ID semantics")
    probability_intervals = {
        expert_id: theorem.Interval(**experts[expert_id]["probability_interval"])
        for expert_id in selected
    }
    expected_weight_intervals = theorem.selected_weight_intervals(selected, probability_intervals)
    for expert_id in selected:
        item = weights["by_expert_id"][str(expert_id)]
        expected_interval = expected_weight_intervals[expert_id]
        if item["routing_weight_interval"] != {"lower": expected_interval.lower, "upper": expected_interval.upper}:
            raise ValidationError("selected-weight interval")
        if not expected_interval.contains(item["exact_routing_weight"]) or item.get("exact_weight_contained") is not True:
            raise ValidationError("selected-weight containment")
    if weights.get("qualification") != "REQUIRES_FROZEN_ACCEPTANCE_RULE" or weights.get("all_exact_weights_contained") is not True:
        raise ValidationError("weight qualification honesty")

    if result.get("route_insensitivity_disposition") != "ROUTE SET INVARIANT / WEIGHTS REQUIRE QUALIFICATION":
        raise ValidationError("route disposition")
    if document.get("result") != result.get("route_insensitivity_disposition"):
        raise ValidationError("top-level disposition mismatch")
    replay = document["deterministic_replay"]
    core_sha = hashlib.sha256(evaluation.canonical_json(result)).hexdigest()
    if replay != {"run_count": 2, "run_1_sha256": core_sha, "run_2_sha256": core_sha, "identical": True}:
        raise ValidationError("deterministic replay proof")

    isolation = document["isolation"]
    if isolation != {
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "real_payload_ledger_before": 139,
        "real_payload_ledger_after": 139,
        "ledger_mutated": False,
        "candidate_or_model_dispatches": 0,
        "representative_m1f0_execution": False,
    }:
        raise ValidationError("isolation or ledger drift")
    expected_history = {
        "DPREFIX_REAL_1": "REJECTED_UNCHANGED",
        "DPREFIX_REAL_2": "REJECTED_UNCHANGED",
        "DPREFIX_REAL_3": "REJECTED_UNCHANGED",
        "DPREFIX_EXACT_1": "CANONICAL_UNCHANGED",
    }
    if document["historical_immutability"] != expected_history:
        raise ValidationError("historical disposition drift")
    if document["expectation_check"].get("theorem_or_guard_modified_after_observation") is not False:
        raise ValidationError("post-observation theorem mutation")

    public_text = evaluation.canonical_json(document).decode()
    if re.search(r"(?:/Users/|/home/|[A-Za-z]:\\\\|\.pulsarmlx-local|f017-v2-antecedent-recovery-event-1)", public_text):
        raise ValidationError("machine-local private path leak")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    document = load_json(args.evidence)
    validate_document(document)
    if args.evidence == EVIDENCE and args.evidence.read_bytes() != evaluation.canonical_json(document):
        raise ValidationError("committed evidence is not canonical JSON")
    print("ROUTE_AMBIGUITY_V31_EVALUATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
