#!/usr/bin/env python3
"""Validate the bounded F017 production selected-weight qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.research import f017_selected_weight_qualification_evaluation as production
from scripts.research import validate_f017_selected_weight_acceptance as frozen_validation


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-selected-routing-weight-qualification-v1.json"
ROUTE_EVIDENCE = production.ROUTE_EVIDENCE
LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"
STARTING_HEAD = "62ca1ef7e64cdea839cf2a2517ec684a1b960104"
CONTRACT_SHA256 = "ebf7c89543e95acecc067b1ee10883f7e9d564fc37be347480e40b02d3a8d7ca"
SPECIFICATION_SHA256 = "9e4d5d9baa37137947379445e39642fa342d982c91b607ff420df150335646fc"
IMPLEMENTATION_SHA256 = "8af70f24bfdfd79dbfe87b4d30d932bd923c0e2d4b0ca45039528afcf4177196"
FREEZE_EVIDENCE_SHA256 = "2b5611b9f8852ddfbaae48b9185b7d7349eed8654827ba8fd17b52a8d34399b1"


class QualificationValidationError(ValueError):
    pass


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise QualificationValidationError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict):
        raise QualificationValidationError(f"expected object: {path}")
    return value


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_evidence(evidence: dict[str, Any], root: Path = ROOT) -> None:
    expected_keys = {
        "schema", "schema_version", "starting_head", "authority", "selected_expert_ids",
        "membership", "qualification", "final_route_disposition", "historical_immutability",
        "isolation", "artifacts", "validation", "next_action",
    }
    if set(evidence) != expected_keys:
        raise QualificationValidationError("qualification evidence schema drift")
    if evidence.get("schema") != "pulsarmlx.f017.selected-routing-weight-qualification" or evidence.get("schema_version") != "1.0.0":
        raise QualificationValidationError("qualification evidence identity")
    if evidence.get("starting_head") != STARTING_HEAD:
        raise QualificationValidationError("starting head")
    authority = evidence.get("authority", {})
    required_authority = {
        "route_evaluation_evidence_sha256": production.ROUTE_EVIDENCE_SHA256,
        "weight_acceptance_contract_sha256": CONTRACT_SHA256,
        "weight_acceptance_specification_sha256": SPECIFICATION_SHA256,
        "weight_acceptance_implementation_sha256": IMPLEMENTATION_SHA256,
        "weight_acceptance_freeze_evidence_sha256": FREEZE_EVIDENCE_SHA256,
        "DPREFIX_EXACT_1_sha256": production.EXACT_STATE_SHA256,
    }
    if authority != required_authority:
        raise QualificationValidationError("frozen authority binding")
    route_path = root / ROUTE_EVIDENCE.relative_to(ROOT)
    if sha256_path(route_path) != production.ROUTE_EVIDENCE_SHA256:
        raise QualificationValidationError("route evidence identity")
    expected = production.evaluate(production.load_json(route_path))
    for key in (
        "selected_expert_ids", "membership", "qualification", "final_route_disposition", "isolation"
    ):
        if evidence.get(key) != expected[key]:
            raise QualificationValidationError(f"derived result mismatch: {key}")

    if expected["qualification"]["mathematical_pass_count"] != 0:
        raise QualificationValidationError("unexpected mathematical pass count")
    if expected["qualification"]["engineering_h2_pass_count"] != 0:
        raise QualificationValidationError("unexpected engineering pass count")
    if expected["qualification"]["joint_normalization_valid"] is not True:
        raise QualificationValidationError("joint normalization")
    if expected["final_route_disposition"] != "ROUTE NOT PROVEN INVARIANT":
        raise QualificationValidationError("fail-closed route disposition")

    historical = evidence.get("historical_immutability", {})
    if historical != {
        "DPREFIX_REAL_1": "REJECTED_UNCHANGED",
        "DPREFIX_REAL_2": "REJECTED_UNCHANGED",
        "DPREFIX_REAL_3": "REJECTED_UNCHANGED",
        "DPREFIX_EXACT_1": "CANONICAL_UNCHANGED",
        "selected_top8": [250, 10, 237, 73, 62, 177, 218, 28],
        "membership_mathematical_pass": "1984/1984_UNCHANGED",
        "membership_minimum_safety_factor": 1.180434247555598,
        "membership_worst_pair": [28, 26],
        "membership_engineering_h2_pass": "1982/1984_UNCHANGED",
    }:
        raise QualificationValidationError("historical immutability")
    if evidence.get("isolation") != expected["isolation"]:
        raise QualificationValidationError("isolation")

    artifacts = evidence.get("artifacts", [])
    if len(artifacts) != 6:
        raise QualificationValidationError("artifact inventory")
    for artifact in artifacts:
        path = Path(str(artifact.get("path", "")))
        if path.is_absolute() or ".." in path.parts:
            raise QualificationValidationError("unsafe artifact path")
        current = sha256_path(root / path)
        historical = subprocess.run(
            ["git", "show", f"7a72bff4bada524a5a57e7b21c31014004cfbc83:{path.as_posix()}"],
            cwd=root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
        )
        historical_sha = hashlib.sha256(historical.stdout).hexdigest() if historical.returncode == 0 else ""
        if artifact.get("sha256") not in {current, historical_sha}:
            raise QualificationValidationError(f"artifact identity: {path}")
    public = json.dumps(evidence, sort_keys=True)
    if "/Users/" in public or "/home/" in public or "file://" in public or "antecedents/" in public:
        raise QualificationValidationError("private path leak")

    validation = evidence.get("validation", {})
    if validation.get("deterministic_replay") is not True or validation.get("joint_normalization") != "PASS":
        raise QualificationValidationError("validation record")
    if validation.get("thresholds_modified") is not False or validation.get("route_recomputed") is not False:
        raise QualificationValidationError("unauthorized mutation record")

    ledger = load_json(root / LEDGER.relative_to(ROOT))
    real2 = [item for item in ledger.get("events", []) if item.get("attempt") == "DPREFIX-REAL-2"]
    if len(real2) != 1 or real2[0].get("cumulative_tensor_payloads_after_event") != 139:
        raise QualificationValidationError("qualification-time real-payload ledger")
    if ledger.get("cumulative_tensor_payloads", 0) < 139:
        raise QualificationValidationError("real-payload ledger predates qualification")


def validate(root: Path = ROOT) -> None:
    frozen_validation.validate_repository(root)
    validate_evidence(load_json(root / EVIDENCE.relative_to(ROOT)), root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    validate()
    print("F017_SELECTED_WEIGHT_QUALIFICATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
