#!/usr/bin/env python3
"""Validate Sequence-5 design satisfiability and prepared instantiability."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
import generate_f017_event06_sequence05_design_v5 as design

ROOT = design.ROOT
EVIDENCE = design.EVIDENCE_DIR
RESULT = EVIDENCE / "f017-event06-v12-sequence05-design-mechanical-validation-v2.json"


def load(path: Path, *, canonical: bool = True) -> dict:
    raw = path.read_bytes(); value = json.loads(raw)
    if (canonical and raw != canonical_bytes(value)) or not isinstance(value, dict):
        raise ValueError(f"noncanonical object: {path.relative_to(ROOT)}")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nested(value: dict, expected: dict) -> None:
    for key, item in expected.items():
        if key not in value:
            raise ValueError(f"missing required key: {key}")
        if isinstance(item, dict): nested(value[key], item)
        elif value[key] != item: raise ValueError(f"predicate mismatch: {key}")


def main() -> int:
    for path, expected in design.artifacts().items():
        if path.read_bytes() != canonical_bytes(expected):
            raise ValueError(f"generator drift: {path.relative_to(ROOT)}")
    if design.PREPARED.read_bytes() != canonical_bytes(design.prepared_manifest()):
        raise ValueError("prepared manifest drift")

    readiness = load(design.READINESS); manifest = load(design.MANIFEST); qualification = load(design.QUALIFICATION)
    provenance = load(design.PROVENANCE); prepared = load(design.PREPARED); repro_contract = load(design.REPRO)
    repro = load(EVIDENCE / "f017-event06-v12-sequence05-challenge-reproducibility-cycle04-v1.json")
    correction = load(EVIDENCE / "f017-event06-v12-sequence05-review-correction-index-v2.json")

    roles = manifest["required_roles"]
    if set(roles) != set(qualification["roles"]) or set(roles) != set(prepared["bindings"]):
        raise ValueError("21-role census divergence")
    if len(roles) != 21 or prepared["role_count"] != 21 or prepared["binding_count"] != 21:
        raise ValueError("21-role cardinality")
    if prepared["final_acceptance_eligible"] or prepared["live_authority"]:
        raise ValueError("prepared manifest authority escalation")

    current = set(qualification["current_authority_roles"]); future = set(qualification["future_output_roles"])
    if current & future or current | future != set(roles):
        raise ValueError("qualification role partition")
    for role in current:
        binding = prepared["bindings"][role]; path = ROOT / binding["path"]
        if not path.is_file() or sha(path) != binding["sha256"]:
            raise ValueError(f"prepared binding: {role}")
        value = load(path, canonical=path in design.artifacts() or path == design.PREPARED)
        rule = qualification["roles"][role]
        nested(value, rule.get("required", {})); nested(value, rule.get("nested_required", {}))
    for role in future:
        rule = qualification["roles"][role]
        if rule.get("availability_stage", "").startswith("POST_IMPLEMENTATION") is False:
            raise ValueError(f"future role stage: {role}")
        required = rule.get("required_fields")
        if not isinstance(required, list) or "schema" not in required or len(required) != len(set(required)):
            raise ValueError(f"future role schema census: {role}")
        if not rule.get("required_schema", "").startswith("pulsarmlx.f017."):
            raise ValueError(f"future role schema: {role}")
    for role in ("challenge_result", "opus_result"):
        rule = qualification["roles"][role]
        if "required_findings" in rule["required_fields"] or "non_blocking_required_findings" not in rule["required_fields"]:
            raise ValueError(f"review counter vocabulary: {role}")
        if rule["cross_bindings"]["reviewed_commit"] != "review_head":
            raise ValueError(f"review-head binding: {role}")

    if repro["schema"] != repro_contract["report_schema"] or repro["finding_count"] != len(repro["finding_checks"]):
        raise ValueError("reproduction report structure")
    if repro["unexpected_misses"] != 0 or repro["result"] != "PASS" or any(row["result"] != "PASS" for row in repro["finding_checks"]):
        raise ValueError("reproduction report result")
    if {row["finding_id"] for row in repro["finding_checks"]} != {"R1", "R2", "R3", "U1"}:
        raise ValueError("reproduction finding census")
    false_accepts = [row for row in correction["rows"] if row["finding"] == "FALSE_ZERO_FINDING_ACCEPT"]
    if len(false_accepts) != 3 or any(row["disposition"] != "NONAUTHORITATIVE_MISSED_MATERIAL_FINDINGS" for row in false_accepts):
        raise ValueError("false challenge disposition")
    if not provenance["raw_provider_envelope_required_for_current_acceptance"]:
        raise ValueError("provider envelope requirement")
    if readiness["challenge_reproducibility_contract"] != str(design.REPRO.relative_to(ROOT)):
        raise ValueError("readiness reproduction binding")

    result = {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-design-mechanical-validation/1.1.0",
        "result": "PASS", "readiness_fields": len(readiness["required_fields"]),
        "manifest_roles": len(roles), "current_authority_roles_validated": len(current),
        "future_output_schema_contracts_validated": len(future), "prepared_manifest_bindings_validated": len(prepared["bindings"]),
        "prepared_manifest_final_acceptance_eligible": False, "challenge_findings_reproduced": repro["finding_count"],
        "historical_false_accepts_non_authoritative": len(false_accepts), "qualification_requirements_satisfiable": True,
        "checkpoint_root_resolved": False, "checkpoint_access": 0, "numerical_operations": 0,
        "live_installations": 0, "package_starts": 0, "ids_consumed": 0,
    }
    RESULT.write_bytes(canonical_bytes(result))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
