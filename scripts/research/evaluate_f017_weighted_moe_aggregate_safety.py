#!/usr/bin/env python3
"""Evaluate the frozen F017 weighted-MoE aggregate theorem.

This checkpoint-free consumer is intentionally narrow: it accepts only the
committed route evidence, the committed expert-output reuse authorization, and
the eight authorized persisted expert-output objects.  It never resolves a
checkpoint or model execution surface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import stat
import struct
from typing import Any, Mapping, Sequence

from scripts.research import f017_routing_contract_v31 as v31
from scripts.research import f017_weighted_moe_aggregate_theorem as theorem


ROOT = Path(__file__).resolve().parents[2]
STARTING_HEAD = "e36179c3642bd326c898a9dfa09fe2a48a56c99e"
ROUTE_EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-dprefix-route-ambiguity-v31-evaluation-v1.json"
ROUTE_EVIDENCE_SHA256 = "a4f3e1afe84be2cade1ed6c1728b2f82cd0ff2d22e8a964779f3216baf124eb4"
WEIGHT_EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-selected-routing-weight-qualification-v1.json"
WEIGHT_EVIDENCE_SHA256 = "834eefb7e0f127e12768285097dc3601135c1c1ff8ef0e871d65f59af1bc6b1f"
REUSE_AUTHORIZATION = ROOT / "docs/architecture/reviews/evidence/f017-canonical-expert-output-private-reuse-authorization-v1.json"
REUSE_AUTHORIZATION_SHA256 = "b370d3c3dd938eeadd18f34fabab89077319b979b994b97ffa33afddf2bffa28"
AGGREGATE_CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-weighted-moe-aggregate-perturbation-v1.json"
AGGREGATE_CONTRACT_SHA256 = "ff1a15c29b79681458d74452c8c72dde9c9bf5eb44637d05a7e4ea9eb1525fac"
AGGREGATE_IMPLEMENTATION = ROOT / "scripts/research/f017_weighted_moe_aggregate_theorem.py"
AGGREGATE_IMPLEMENTATION_SHA256 = "74167ce38cfb60189e57877ddba8b96123d7df54963a200658136497700f7974"
LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"
LEDGER_SHA256 = "5120b94e2f304237fb2dcbe04dd04fa4ed3647a23b5119b12776dd02428a345d"
CANONICAL_STATE_SHA256 = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"
CONSUMER_ID = "F017-WEIGHTED-MOE-AGGREGATE-SAFETY-ANALYTICAL-1"
SELECTED_IDS = (250, 10, 237, 73, 62, 177, 218, 28)
DIMENSION = 6144


class AggregateEvaluationError(ValueError):
    """Fail-closed production aggregate evaluation error."""


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AggregateEvaluationError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict):
        raise AggregateEvaluationError(f"expected object: {path.name}")
    return value


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AggregateEvaluationError(message)


def _source_authority() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    expected = (
        (ROUTE_EVIDENCE, ROUTE_EVIDENCE_SHA256),
        (WEIGHT_EVIDENCE, WEIGHT_EVIDENCE_SHA256),
        (REUSE_AUTHORIZATION, REUSE_AUTHORIZATION_SHA256),
        (AGGREGATE_CONTRACT, AGGREGATE_CONTRACT_SHA256),
        (AGGREGATE_IMPLEMENTATION, AGGREGATE_IMPLEMENTATION_SHA256),
        (LEDGER, LEDGER_SHA256),
    )
    for path, identity in expected:
        require(sha256_path(path) == identity, f"source identity mismatch: {path.name}")
    route = load_json(ROUTE_EVIDENCE)
    weights = load_json(WEIGHT_EVIDENCE)
    reuse = load_json(REUSE_AUTHORIZATION)
    ledger = load_json(LEDGER)
    require(ledger.get("cumulative_tensor_payloads") == 163, "real-payload ledger is not 163")
    require(route.get("authority", {}).get("DPREFIX_EXACT_1_sha256") == CANONICAL_STATE_SHA256,
            "canonical state identity mismatch")
    membership = route.get("evaluation", {}).get("membership", {})
    require(membership.get("evaluated") == 1984 and membership.get("mathematical_pass_count") == 1984
            and membership.get("mathematical_fail_count") == 0, "membership evidence changed")
    require(weights.get("qualification", {}).get("mathematical_pass_count") == 0,
            "coefficient qualification changed")
    require(weights.get("final_route_disposition") == "ROUTE NOT PROVEN INVARIANT",
            "pre-evaluation route disposition changed")
    require(reuse.get("authorization_id") == "F017-CANONICAL-EXPERT-OUTPUT-REUSE-1"
            and reuse.get("status") == "AUTHORIZED_NOT_EVALUATED", "reuse authorization state")
    require(reuse.get("consumer", {}).get("consumer_id") == CONSUMER_ID, "consumer identity")
    require(reuse.get("aggregate_theorem", {}).get("sha256") == AGGREGATE_CONTRACT_SHA256,
            "aggregate theorem binding")
    return route, weights, reuse


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts and path.parts[0] == "expert_outputs",
            "unsafe private symbolic path")
    return path


def _load_outputs(private_root: Path, reuse: Mapping[str, Any]) -> tuple[dict[int, tuple[float, ...]], dict[str, str]]:
    package_root = private_root.absolute() / "recovery-package"
    require(package_root.is_dir() and not stat.S_ISLNK(package_root.lstat().st_mode), "private package root")
    records = reuse.get("package", {}).get("artifacts", [])
    require(isinstance(records, list) and len(records) == 8, "authorized output census")
    require(tuple(item.get("expert_id") for item in records) == SELECTED_IDS, "authorized expert ordering")
    outputs: dict[int, tuple[float, ...]] = {}
    identities: dict[str, str] = {}
    for item in records:
        expert_id = int(item["expert_id"])
        relative = _safe_relative(str(item["symbolic_name"]))
        target = package_root
        for part in relative.parts:
            target = target / part
            require(target.exists() and not stat.S_ISLNK(target.lstat().st_mode), "private symlink/path mismatch")
        metadata = target.stat()
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_size == 24_576, "private output surface")
        require(not metadata.st_mode & 0o222 and metadata.st_nlink == 1, "private output immutability")
        raw = target.read_bytes()
        actual = sha256_bytes(raw)
        require(actual == item.get("expected_sha256"), f"private output identity: {expert_id}")
        values = struct.unpack("<6144f", raw)
        require(all(math.isfinite(value) for value in values), f"non-finite expert output: {expert_id}")
        outputs[expert_id] = values
        identities[str(expert_id)] = actual
    return outputs, identities


def _routing_inputs(route: Mapping[str, Any], weight_evidence: Mapping[str, Any]) -> tuple[
    dict[int, float], dict[int, v31.Interval], v31.Interval
]:
    evaluation = route.get("evaluation", {})
    require(tuple(evaluation.get("exact_route", {}).get("selected_top8", [])) == SELECTED_IDS,
            "selected expert set changed")
    records = evaluation.get("selected_weights", {}).get("by_expert_id", {})
    require(set(records) == {str(value) for value in SELECTED_IDS}, "routing-weight inventory")
    nominal: dict[int, float] = {}
    intervals: dict[int, v31.Interval] = {}
    for expert_id in SELECTED_IDS:
        item = records[str(expert_id)]
        require(item.get("expert_id") == expert_id and item.get("exact_weight_contained") is True,
                "atomic expert-weight evidence")
        nominal[expert_id] = float(item["exact_routing_weight"])
        interval = item["routing_weight_interval"]
        intervals[expert_id] = v31.Interval(float(interval["lower"]), float(interval["upper"]))
    qualification = weight_evidence.get("qualification", {})
    joint = qualification.get("joint_weight_sum_interval", {})
    require(qualification.get("joint_normalization_valid") is True
            and joint == {"lower": 2.4999999999999996, "upper": 2.5000000000000004},
            "joint normalization evidence")
    return nominal, intervals, v31.Interval(float(joint["lower"]), float(joint["upper"]))


def _interval_digest(components: Sequence[theorem.ComponentEnclosure], field: str) -> str:
    raw = bytearray()
    for item in components:
        interval = getattr(item, field)
        raw.extend(struct.pack("<dd", interval.lower, interval.upper))
    return sha256_bytes(bytes(raw))


def _enclosure_summary(components: Sequence[theorem.ComponentEnclosure], field: str) -> dict[str, Any]:
    intervals = [getattr(item, field) for item in components]
    radii = [v31.round_up(max(abs(item.lower), abs(item.upper))) for item in intervals]
    squares = [radius * radius for radius in radii]
    return {
        "canonical_le_f64_interval_sha256": _interval_digest(components, field),
        "component_count": len(intervals),
        "maximum_absolute_radius": v31.round_up(max(radii)),
        "rmse_radius": v31.round_up(math.sqrt(math.fsum(squares) / len(squares))),
    }


def evaluate(private_root: Path) -> dict[str, Any]:
    route, weight_evidence, reuse = _source_authority()
    outputs, before = _load_outputs(private_root, reuse)
    nominal_weights, weight_intervals, joint_sum = _routing_inputs(route, weight_evidence)
    result = theorem.qualify_f017_production_aggregate(
        SELECTED_IDS,
        nominal_weights,
        weight_intervals,
        outputs,
        selected_set_invariant=True,
        joint_weight_sum_interval=joint_sum,
    )
    after_outputs, after = _load_outputs(private_root, reuse)
    require(before == after and outputs == after_outputs, "private outputs changed during evaluation")
    nominal = tuple(item.nominal for item in result.component_bounds)
    nominal_raw = struct.pack(f"<{DIMENSION}d", *nominal)
    qualification = theorem.result_to_dict(result)
    max_pass = result.max_absolute_bound <= theorem.R10_INTERMEDIATE_MAX_ABSOLUTE_ERROR
    rmse_pass = result.rmse_bound <= theorem.R10_INTERMEDIATE_RMSE
    cosine_pass = result.cosine_lower_bound is not None and result.cosine_lower_bound >= theorem.R10_INTERMEDIATE_COSINE_MINIMUM
    require(result.mathematically_qualified == (max_pass and rmse_pass and cosine_pass),
            "aggregate qualification inconsistency")
    if result.mathematically_qualified:
        disposition = "ROUTE SET INVARIANT / AGGREGATE SAFE / COEFFICIENT RULE FAILS"
    else:
        disposition = "ROUTE NOT PROVEN INVARIANT"
    return {
        "schema": "pulsarmlx.f017.weighted-moe-aggregate-safety-evaluation",
        "schema_version": "1.0.0",
        "starting_authoritative_head": STARTING_HEAD,
        "consumer_id": CONSUMER_ID,
        "authority": {
            "DPREFIX_EXACT_1_sha256": CANONICAL_STATE_SHA256,
            "aggregate_contract_sha256": AGGREGATE_CONTRACT_SHA256,
            "aggregate_implementation_sha256": AGGREGATE_IMPLEMENTATION_SHA256,
            "route_evidence_sha256": ROUTE_EVIDENCE_SHA256,
            "weight_qualification_evidence_sha256": WEIGHT_EVIDENCE_SHA256,
            "expert_output_reuse_authorization_sha256": REUSE_AUTHORIZATION_SHA256,
        },
        "inputs": {
            "selected_expert_ids": list(SELECTED_IDS),
            "expert_output_sha256_by_id": before,
            "nominal_routing_weights_by_id": {str(key): value for key, value in nominal_weights.items()},
            "routing_weight_intervals_by_id": {
                str(key): {"lower": value.lower, "upper": value.upper}
                for key, value in weight_intervals.items()
            },
            "joint_selected_weight_sum_interval": {"lower": joint_sum.lower, "upper": joint_sum.upper},
        },
        "nominal_aggregate": {
            "dtype": "f64",
            "shape": [DIMENSION],
            "finite_count": sum(math.isfinite(value) for value in nominal),
            "canonical_le_f64_sha256": sha256_bytes(nominal_raw),
            "maximum_absolute_value": max(abs(value) for value in nominal),
            "l2_norm": math.sqrt(math.fsum(value * value for value in nominal)),
        },
        "enclosures": {
            "direct": _enclosure_summary(result.component_bounds, "direct"),
            "normalization_centered": _enclosure_summary(result.component_bounds, "centered"),
            "sound_intersection": _enclosure_summary(result.component_bounds, "enclosure"),
            "selection_rule": "INTERSECTION_OF_FROZEN_DIRECT_AND_CENTERED_SOUND_ENCLOSURES",
        },
        "bounds": {
            "maximum_absolute_perturbation": result.max_absolute_bound,
            "rmse_perturbation": result.rmse_bound,
            "cosine_similarity_lower_bound": result.cosine_lower_bound,
        },
        "budgets": {
            "maximum_absolute": {"threshold": theorem.R10_INTERMEDIATE_MAX_ABSOLUTE_ERROR,
                                  "pass": max_pass, "factor": qualification["max_absolute_factor"]},
            "rmse": {"threshold": theorem.R10_INTERMEDIATE_RMSE,
                     "pass": rmse_pass, "factor": qualification["rmse_factor"]},
            "cosine": {"minimum": theorem.R10_INTERMEDIATE_COSINE_MINIMUM,
                       "pass": cosine_pass, "factor": qualification["cosine_factor"]},
            "global_aggregate_safety_factor": qualification["aggregate_safety_factor"],
        },
        "qualifications": {
            "membership": "PASS_UNCHANGED_1984_OF_1984",
            "coefficient_rule": "FAIL_UNCHANGED_0_OF_8",
            "aggregate_mathematical": "PASS" if result.mathematically_qualified else "FAIL",
            "aggregate_engineering_h2": "PASS" if result.engineering_h2 else "FAIL",
            "final_route_disposition": disposition,
        },
        "private_artifact_verification": {
            "before_sha256_by_id": before,
            "after_sha256_by_id": after,
            "all_8_equal": before == after,
            "read_only_single_link_regular_non_symlink": True,
        },
        "isolation": {
            "checkpoint_reads": 0,
            "shard_opens": 0,
            "payload_reads": 0,
            "candidate_or_model_dispatches": 0,
            "real_payload_ledger_before": 163,
            "real_payload_ledger_after": 163,
            "ledger_mutated": False,
        },
        "historical_immutability": {
            "DPREFIX_REAL_1": "REJECTED_UNCHANGED",
            "DPREFIX_REAL_2": "REJECTED_UNCHANGED",
            "DPREFIX_REAL_3": "REJECTED_UNCHANGED",
            "DPREFIX_EXACT_1": "CANONICAL_UNCHANGED",
            "membership": "PASS_UNCHANGED_1984_OF_1984",
            "coefficient_qualification": "FAIL_UNCHANGED_0_OF_8",
        },
    }


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-root", type=Path, required=True)
    args = parser.parse_args()
    print(canonical_json_bytes(evaluate(args.private_root)).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
