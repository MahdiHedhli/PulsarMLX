#!/usr/bin/env python3
"""Apply the frozen F017 selected-weight contract to banked route evidence.

This evaluator consumes only the committed public Loop 4 result.  It has no
private-package, checkpoint, shard-reader, or model-execution capability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from scripts.research import f017_routing_contract_v31 as v31
from scripts.research import f017_selected_weight_acceptance as acceptance


ROOT = Path(__file__).resolve().parents[2]
ROUTE_EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-dprefix-route-ambiguity-v31-evaluation-v1.json"
ROUTE_EVIDENCE_SHA256 = "a4f3e1afe84be2cade1ed6c1728b2f82cd0ff2d22e8a964779f3216baf124eb4"
EXACT_STATE_SHA256 = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"
SELECTED_IDS = (250, 10, 237, 73, 62, 177, 218, 28)
REQUIRED_MEMBERSHIP_COUNT = 1984
EXPECTED_MINIMUM_FACTOR = 1.180434247555598
EXPECTED_WORST_PAIR = (28, 26)


class ProductionWeightEvaluationError(ValueError):
    """Fail-closed production-evidence rejection."""


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProductionWeightEvaluationError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict):
        raise ProductionWeightEvaluationError("route evidence must be a JSON object")
    return value


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_route_authority(route: dict[str, Any]) -> None:
    authority = route.get("authority", {})
    if authority.get("DPREFIX_EXACT_1_sha256") != EXACT_STATE_SHA256:
        raise ProductionWeightEvaluationError("canonical exact-state identity mismatch")
    isolation = route.get("isolation", {})
    if isolation.get("checkpoint_reads") != 0 or isolation.get("shard_opens") != 0:
        raise ProductionWeightEvaluationError("route evidence is not zero-access")
    if isolation.get("real_payload_ledger_before") != 139 or isolation.get("real_payload_ledger_after") != 139:
        raise ProductionWeightEvaluationError("route evidence ledger mismatch")


def _membership(route: dict[str, Any]) -> dict[str, Any]:
    membership = route.get("evaluation", {}).get("membership", {})
    required = {
        "required": REQUIRED_MEMBERSHIP_COUNT,
        "evaluated": REQUIRED_MEMBERSHIP_COUNT,
        "mathematical_pass_count": REQUIRED_MEMBERSHIP_COUNT,
        "mathematical_fail_count": 0,
        "all_membership_invariant": True,
        "minimum_mathematical_safety_factor": EXPECTED_MINIMUM_FACTOR,
        "worst_pair": list(EXPECTED_WORST_PAIR),
        "engineering_h2_pass_count": 1982,
        "engineering_h2_fail_count": 2,
    }
    if any(membership.get(key) != value for key, value in required.items()):
        raise ProductionWeightEvaluationError("banked membership result changed")
    return membership


def _probability_sum_interval(
    selected_ids: tuple[int, ...], probability_intervals: dict[int, v31.Interval]
) -> v31.Interval:
    total = v31.Interval(0.0, 0.0)
    for expert_id in selected_ids:
        total = v31.interval_add(total, probability_intervals[expert_id])
    return total


def evaluate(route: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the immutable eight banked intervals with the frozen rule."""

    _require_route_authority(route)
    membership = _membership(route)
    evaluation = route.get("evaluation", {})
    selected = tuple(evaluation.get("exact_route", {}).get("selected_top8", []))
    if selected != SELECTED_IDS:
        raise ProductionWeightEvaluationError("selected expert set changed")
    weights = evaluation.get("selected_weights", {})
    if weights.get("key_semantics") != "expert_id" or weights.get("precondition_selected_set_invariant") is not True:
        raise ProductionWeightEvaluationError("banked selected-weight semantics changed")
    banked = weights.get("by_expert_id", {})
    if set(banked) != {str(expert_id) for expert_id in selected}:
        raise ProductionWeightEvaluationError("banked selected-weight inventory mismatch")

    nominal_weights: dict[int, float] = {}
    intervals: dict[int, v31.Interval] = {}
    nominal_probabilities: dict[int, float] = {}
    probability_intervals: dict[int, v31.Interval] = {}
    for expert_id in selected:
        item = banked[str(expert_id)]
        if item.get("expert_id") != expert_id or item.get("exact_weight_contained") is not True:
            raise ProductionWeightEvaluationError(f"banked expert identity/enclosure mismatch: {expert_id}")
        nominal_weights[expert_id] = float(item["exact_routing_weight"])
        weight_interval = item["routing_weight_interval"]
        intervals[expert_id] = v31.Interval(float(weight_interval["lower"]), float(weight_interval["upper"]))
        nominal_probabilities[expert_id] = float(item["exact_probability"])
        probability_interval = item["probability_interval"]
        probability_intervals[expert_id] = v31.Interval(
            float(probability_interval["lower"]), float(probability_interval["upper"])
        )

    nominal_probability_sum = math.fsum(nominal_probabilities[expert_id] for expert_id in selected)
    probability_sum_interval = _probability_sum_interval(selected, probability_intervals)
    result = acceptance.qualify_weight_enclosures(
        selected,
        nominal_weights,
        intervals,
        nominal_probability_sum=nominal_probability_sum,
        probability_sum_interval=probability_sum_interval,
        selected_set_invariant=True,
    )
    serialized = acceptance.result_to_dict(result)
    for record in serialized["by_expert_id"].values():
        record["mathematical_threshold"] = acceptance.R10_ROUTING_WEIGHT_MAX_ABSOLUTE_ERROR
        record["engineering_h2_threshold"] = acceptance.ENGINEERING_ROUTING_WEIGHT_MAX_ABSOLUTE_ERROR

    mathematical_pass_count = sum(
        bool(record["mathematically_qualified"])
        for record in serialized["by_expert_id"].values()
    )
    engineering_pass_count = sum(
        bool(record["engineering_h2"])
        for record in serialized["by_expert_id"].values()
    )
    maximum = max(
        serialized["by_expert_id"].values(),
        key=lambda record: (record["outward_absolute_radius"], -record["expert_id"]),
    )
    if result.mathematically_qualified:
        disposition = "ROUTE INVARIANT OVER DPREFIX ORACLE AMBIGUITY"
    else:
        disposition = "ROUTE NOT PROVEN INVARIANT"

    return {
        "selected_expert_ids": list(selected),
        "membership": {
            "required": membership["required"],
            "evaluated": membership["evaluated"],
            "mathematical_pass_count": membership["mathematical_pass_count"],
            "mathematical_fail_count": membership["mathematical_fail_count"],
            "minimum_mathematical_safety_factor": membership["minimum_mathematical_safety_factor"],
            "worst_pair": membership["worst_pair"],
            "engineering_h2_pass_count": membership["engineering_h2_pass_count"],
            "engineering_h2_fail_count": membership["engineering_h2_fail_count"],
        },
        "qualification": {
            **serialized,
            "mathematical_pass_count": mathematical_pass_count,
            "mathematical_fail_count": len(selected) - mathematical_pass_count,
            "engineering_h2_pass_count": engineering_pass_count,
            "engineering_h2_fail_count": len(selected) - engineering_pass_count,
            "maximum_rho": maximum["outward_absolute_radius"],
            "maximum_rho_expert_id": maximum["expert_id"],
        },
        "final_route_disposition": disposition,
        "isolation": {
            "checkpoint_reads": 0,
            "shard_opens": 0,
            "candidate_or_model_dispatches": 0,
            "real_payload_ledger_before": 139,
            "real_payload_ledger_after": 139,
            "ledger_mutated": False,
        },
    }


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route-evidence", type=Path, default=ROUTE_EVIDENCE)
    args = parser.parse_args()
    if args.route_evidence.resolve() != ROUTE_EVIDENCE.resolve():
        raise ProductionWeightEvaluationError("alternate route evidence is forbidden")
    if sha256_path(args.route_evidence) != ROUTE_EVIDENCE_SHA256:
        raise ProductionWeightEvaluationError("route evidence SHA-256 mismatch")
    print(canonical_json_bytes(evaluate(load_json(args.route_evidence))).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
