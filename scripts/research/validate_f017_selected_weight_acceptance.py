#!/usr/bin/env python3
"""Validate the pre-application F017 selected-weight acceptance freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from scripts.research import validate_f017_routing_contract_v31 as v31_validation
except ModuleNotFoundError:  # direct script execution from scripts/research
    import validate_f017_routing_contract_v31 as v31_validation


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-selected-routing-weight-acceptance-v1.json"
SPECIFICATION = ROOT / "docs/architecture/reviews/f017-selected-routing-weight-acceptance-contract.md"
IMPLEMENTATION = ROOT / "scripts/research/f017_selected_weight_acceptance.py"
TESTS = ROOT / "scripts/research/tests/test_f017_selected_weight_acceptance.py"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-selected-routing-weight-acceptance-freeze-v1.json"
LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"
PRIOR_ROUTE_EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-dprefix-route-ambiguity-v31-evaluation-v1.json"

STARTING_HEAD = "eb1701732b9c729fb6357c98bed7aaf03a95b004"
PRIOR_ROUTE_EVIDENCE_SHA256 = "a4f3e1afe84be2cade1ed6c1728b2f82cd0ff2d22e8a964779f3216baf124eb4"
EXACT_STATE_SHA256 = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"


class WeightFreezeValidationError(ValueError):
    pass


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WeightFreezeValidationError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict):
        raise WeightFreezeValidationError(f"expected JSON object: {path}")
    return value


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_contract(contract: dict[str, Any], root: Path = ROOT) -> None:
    if contract.get("schema") != "pulsarmlx.f017.selected-routing-weight-acceptance-contract":
        raise WeightFreezeValidationError("contract schema")
    if contract.get("schema_version") != "1.0.0" or contract.get("contract_id") != "f017-selected-routing-weight-acceptance-v1":
        raise WeightFreezeValidationError("contract version")
    if contract.get("status") != "FROZEN_BEFORE_REAL_F017_WEIGHT_INTERVAL_EVALUATION":
        raise WeightFreezeValidationError("contract was not frozen before production application")

    anti = contract.get("anti_fitting", {})
    if anti != {
        "real_f017_weight_intervals_loaded": False,
        "real_f017_weight_intervals_evaluated": False,
        "thresholds_derived_from_real_f017_weight_widths": False,
        "later_application_requires_a_separate_bounded_loop": True,
    }:
        raise WeightFreezeValidationError("anti-fitting declaration")

    semantics = contract.get("semantics", {})
    if semantics.get("weight") != "q_i=2.5*p_i/max(sum_{k in T}(p_k),2^-14)":
        raise WeightFreezeValidationError("selected-weight semantics")
    if semantics.get("atomic_key") != "expert_id" or semantics.get("rank_position_keying") != "forbidden":
        raise WeightFreezeValidationError("ID-key semantics")

    mathematical = contract.get("mathematical_acceptance", {})
    if mathematical.get("budget") != 1.0e-5 or mathematical.get("per_id_pass") != "rho_i<=1e-5":
        raise WeightFreezeValidationError("mathematical budget")
    if mathematical.get("relative_width_rule") != "none; relative radius is diagnostic only":
        raise WeightFreezeValidationError("unreviewed relative threshold")
    if mathematical.get("candidate_pass_substitution") != "forbidden":
        raise WeightFreezeValidationError("candidate qualification conflation")

    engineering = contract.get("engineering_acceptance", {})
    if engineering.get("headroom") != 2.0 or engineering.get("per_id_budget") != 5.0e-6:
        raise WeightFreezeValidationError("engineering H=2 budget")
    if engineering.get("engineering_is_mathematical_truth") is not False:
        raise WeightFreezeValidationError("engineering truth conflation")

    joint = contract.get("joint_normalization", {})
    if joint.get("weight_sum") != "sum_i(q_i)=2.5*P/max(P,2^-14)":
        raise WeightFreezeValidationError("joint denominator theorem")
    if "never sum independently" not in str(joint.get("dependency_rule")):
        raise WeightFreezeValidationError("joint dependency rule")
    if joint.get("additional_aggregate_width_threshold") != "none; no pre-existing expert-output norm budget authorizes one":
        raise WeightFreezeValidationError("unreviewed aggregate threshold")

    lineage = contract.get("threshold_lineage", [])
    if len(lineage) != 2:
        raise WeightFreezeValidationError("threshold lineage")
    for item in lineage:
        path = Path(str(item.get("path", "")))
        if path.is_absolute() or ".." in path.parts or sha256_path(root / path) != item.get("sha256"):
            raise WeightFreezeValidationError(f"threshold source identity: {path}")
    if lineage[0].get("value") != 1.0e-5:
        raise WeightFreezeValidationError("R10 threshold value")

    sources = contract.get("semantic_sources", [])
    if len(sources) != 4:
        raise WeightFreezeValidationError("semantic source inventory")
    for item in sources:
        path = Path(str(item.get("path", "")))
        if path.is_absolute() or ".." in path.parts or sha256_path(root / path) != item.get("sha256"):
            raise WeightFreezeValidationError(f"semantic source identity: {path}")

    isolation = contract.get("isolation", {})
    if isolation != {
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "candidate_or_model_dispatches": 0,
        "real_payload_ledger_before": 139,
        "real_payload_ledger_after": 139,
    }:
        raise WeightFreezeValidationError("isolation or ledger")

    public = json.dumps(contract, sort_keys=True)
    if "/Users/" in public or "/home/" in public or "file://" in public or "antecedents/" in public:
        raise WeightFreezeValidationError("private path leak")


def validate_implementation(root: Path = ROOT) -> None:
    source = (root / IMPLEMENTATION.relative_to(ROOT)).read_text()
    forbidden = (
        "f017-dprefix-route-ambiguity-v31-evaluation-v1.json",
        "argparse",
        "Path(",
        ".open(",
        "read_text(",
        "read_bytes(",
    )
    if any(token in source for token in forbidden):
        raise WeightFreezeValidationError("implementation exposes production input or I/O authority")
    required = (
        "R10_ROUTING_WEIGHT_MAX_ABSOLUTE_ERROR = 1.0e-5",
        "ENGINEERING_HEADROOM = 2.0",
        "v31.round_up(max(",
        "joint_weight_sum_enclosure",
    )
    if any(token not in source for token in required):
        raise WeightFreezeValidationError("implementation rule drift")


def validate_history(root: Path = ROOT) -> None:
    v31_validation.validate_history(root)
    ledger = load_json(root / LEDGER.relative_to(ROOT))
    if ledger.get("cumulative_tensor_payloads") != 139:
        raise WeightFreezeValidationError("real-payload ledger changed")
    if sha256_path(root / PRIOR_ROUTE_EVIDENCE.relative_to(ROOT)) != PRIOR_ROUTE_EVIDENCE_SHA256:
        raise WeightFreezeValidationError("banked route-set evidence changed")


def validate_evidence(evidence: dict[str, Any], root: Path = ROOT) -> None:
    expected_keys = {
        "schema", "schema_version", "starting_head", "result", "authority",
        "anti_fitting", "criterion", "artifacts", "validation",
        "historical_immutability", "isolation", "next_action",
    }
    if set(evidence) != expected_keys:
        raise WeightFreezeValidationError("freeze evidence schema drift")
    if evidence.get("schema") != "pulsarmlx.f017.selected-routing-weight-acceptance-freeze" or evidence.get("schema_version") != "1.0.0":
        raise WeightFreezeValidationError("freeze evidence identity")
    if evidence.get("starting_head") != STARTING_HEAD or evidence.get("result") != "WEIGHT QUALIFICATION CONTRACT FROZEN":
        raise WeightFreezeValidationError("freeze disposition")
    authority = evidence.get("authority", {})
    if authority.get("DPREFIX_EXACT_1_sha256") != EXACT_STATE_SHA256:
        raise WeightFreezeValidationError("exact-state authority")
    if authority.get("prior_route_disposition") != "ROUTE SET INVARIANT / WEIGHTS REQUIRE QUALIFICATION":
        raise WeightFreezeValidationError("prior route disposition")
    if authority.get("prior_route_evidence_sha256") != PRIOR_ROUTE_EVIDENCE_SHA256:
        raise WeightFreezeValidationError("prior route evidence binding")
    if evidence.get("anti_fitting") != {
        "real_f017_weight_intervals_loaded": False,
        "real_f017_weight_intervals_evaluated": False,
        "real_f017_weight_interval_fields_read": 0,
        "synthetic_or_symbolic_inputs_only": True,
    }:
        raise WeightFreezeValidationError("freeze anti-fitting evidence")
    criterion = evidence.get("criterion", {})
    if criterion.get("mathematical_per_id_max_abs") != 1.0e-5 or criterion.get("engineering_h2_per_id_max_abs") != 5.0e-6:
        raise WeightFreezeValidationError("freeze criterion")
    if criterion.get("aggregate_output_qualification_deferred") is not True:
        raise WeightFreezeValidationError("aggregate output overclaim")

    artifacts = evidence.get("artifacts", [])
    if len(artifacts) != 6:
        raise WeightFreezeValidationError("freeze artifact inventory")
    for item in artifacts:
        path = Path(str(item.get("path", "")))
        if path.is_absolute() or ".." in path.parts or sha256_path(root / path) != item.get("sha256"):
            raise WeightFreezeValidationError(f"freeze artifact identity: {path}")

    validation = evidence.get("validation", {})
    if validation.get("synthetic_test_count", 0) < 15 or validation.get("property_samples_contained") is not True:
        raise WeightFreezeValidationError("synthetic validation")
    if validation.get("deterministic_replay") is not True or validation.get("mutation_fail_closed") is not True:
        raise WeightFreezeValidationError("replay or mutation validation")
    if validation.get("real_values_evaluated") is not False:
        raise WeightFreezeValidationError("real application leaked into freeze")

    if evidence.get("historical_immutability") != {
        "DPREFIX_REAL_1": "REJECTED_UNCHANGED",
        "DPREFIX_REAL_2": "REJECTED_UNCHANGED",
        "DPREFIX_REAL_3": "REJECTED_UNCHANGED",
        "DPREFIX_EXACT_1": "CANONICAL_UNCHANGED",
        "membership_1984_of_1984": "PASS_UNCHANGED",
        "route_disposition": "ROUTE SET INVARIANT / WEIGHTS REQUIRE QUALIFICATION",
    }:
        raise WeightFreezeValidationError("historical classification drift")
    if evidence.get("isolation") != {
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "candidate_or_model_dispatches": 0,
        "real_payload_ledger_before": 139,
        "real_payload_ledger_after": 139,
    }:
        raise WeightFreezeValidationError("freeze isolation")
    public = json.dumps(evidence, sort_keys=True)
    if "/Users/" in public or "/home/" in public or "file://" in public or "antecedents/" in public:
        raise WeightFreezeValidationError("freeze path leak")


def validate_repository(root: Path = ROOT) -> None:
    validate_contract(load_json(root / CONTRACT.relative_to(ROOT)), root)
    validate_implementation(root)
    validate_history(root)
    evidence_path = root / EVIDENCE.relative_to(ROOT)
    evidence = load_json(evidence_path)
    validate_evidence(evidence, root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    validate_repository(ROOT)
    print("SELECTED_ROUTING_WEIGHT_ACCEPTANCE_FREEZE_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
