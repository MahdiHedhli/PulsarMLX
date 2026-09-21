#!/usr/bin/env python3
"""Mechanically validate the closed Sequence-5 design authority."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
import generate_f017_event06_sequence05_design_v4 as design

ROOT = design.ROOT
EVIDENCE = design.EVIDENCE_DIR
RESULT = EVIDENCE / "f017-event06-v12-sequence05-design-mechanical-validation-v1.json"


def load(path: Path, *, canonical: bool = True) -> dict:
    raw = path.read_bytes()
    value = json.loads(raw)
    if canonical and raw != canonical_bytes(value):
        raise ValueError(f"noncanonical current authority: {path.relative_to(ROOT)}")
    if not isinstance(value, dict):
        raise ValueError(f"object required: {path.relative_to(ROOT)}")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    # Generator drift is a first-class failure.
    for path, expected in design.artifacts().items():
        if path.read_bytes() != canonical_bytes(expected):
            raise ValueError(f"generated artifact drift: {path.relative_to(ROOT)}")

    readiness = load(design.READINESS)
    manifest = load(design.MANIFEST)
    provenance = load(design.PROVENANCE)
    qualification = load(design.QUALIFICATION)
    install = load(design.INSTALL)
    failure = load(EVIDENCE / "f017-event06-v12-sequence05-failure-matrix-v4.json")
    machine = load(EVIDENCE / "f017-event06-v12-sequence05-installation-state-machine-v3.json")
    correction = load(EVIDENCE / "f017-event06-v12-sequence05-review-correction-index-v1.json")
    no_access = load(EVIDENCE / "f017-event06-v12-sequence05-no-access-qualification-plan-v4.json")

    required = readiness["required_fields"]
    if len(required) != 84 or len(set(required)) != 84:
        raise ValueError("readiness field census")
    exact = readiness["exact_predicates"]
    if len(exact) != 34:
        raise ValueError("readiness predicate census")
    for field in ("schema", "authority_manifest_path", "authority_manifest_sha256"):
        if field not in required or not any(field in fields for fields in readiness["exact_types"].values()):
            raise ValueError(f"missing readiness authority field: {field}")
    roles = manifest["required_roles"]
    if roles != design.v3.DEPENDENCY_ROLES or manifest["role_count"] != len(roles):
        raise ValueError("manifest role census")
    if set(qualification["roles"]) != set(roles) or qualification["role_count"] != len(roles):
        raise ValueError("qualification role coverage")
    if qualification["all_requirements_mechanically_validated"] is not False:
        raise ValueError("premature qualification acceptance")
    if sum(value for key, value in failure["derivation"].items() if key != "total") != failure["derivation"]["total"]:
        raise ValueError("mutation derivation arithmetic")
    if failure["minimum_mutations"] < 320:
        raise ValueError("mutation floor")
    sources = set(provenance["accepted_independent_attestation_sources"])
    expected_sources = {
        "AGY_JSON_ENVELOPE_CONVERSATION_ID_STATUS_DURATION_USAGE",
        "CLAUDE_JSON_ENVELOPE_SESSION_ID_CANONICAL_MODEL_STATUS_USAGE",
    }
    if sources != expected_sources or not provenance["attestation_must_be_outside_reviewer_wording"]:
        raise ValueError("review provenance source policy")

    provenance_instances = []
    for reviewer, source in (
        ("agy", "AGY_JSON_ENVELOPE_CONVERSATION_ID_STATUS_DURATION_USAGE"),
        ("opus", "CLAUDE_JSON_ENVELOPE_SESSION_ID_CANONICAL_MODEL_STATUS_USAGE"),
    ):
        path = EVIDENCE / f"f017-event06-v12-sequence05-{reviewer}-design-cycle-03-provenance-v1.json"
        value = load(path)
        if value["schema"] != "pulsarmlx.f017.independent-review-transport-provenance/1.0.0":
            raise ValueError("review provenance instance schema")
        if value["independent_attestation_source"] != source or value["result"] != "PASS":
            raise ValueError("review provenance instance source")
        for role in ("request", "response", "normalized_result"):
            bound = ROOT / value[f"{role}_path"]
            if sha(bound) != value[f"{role}_sha256"]:
                raise ValueError(f"review provenance {role} binding")
        provenance_instances.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path)})

    transitions = machine["transitions"]
    states = set(machine["states"])
    if not all(any(t["from"] == state and t["to"] == "TERMINAL_FAILURE" for t in transitions) for state in states - {"TERMINAL_FAILURE"}):
        raise ValueError("failure transition coverage")
    if install["state_machine_contract"] != str((EVIDENCE / "f017-event06-v12-sequence05-installation-state-machine-v3.json").relative_to(ROOT)):
        raise ValueError("installation state-machine binding")
    rows = correction["rows"]
    if correction["row_count"] != 2 or not any(row["finding"] == "FALSE_ZERO_FINDING_ACCEPT" for row in rows):
        raise ValueError("historical review correction census")
    if no_access["safety"] != {
        "checkpoint_root_resolved": False,
        "checkpoint_access": 0,
        "numerical_operations": 0,
        "live_installations": 0,
        "package_starts": 0,
        "ids_consumed": 0,
    }:
        raise ValueError("no-access safety plan")

    result = {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-design-mechanical-validation/1.0.0",
        "result": "PASS",
        "readiness_fields": len(required),
        "exact_acceptance_predicates": len(exact),
        "manifest_roles": len(roles),
        "qualification_roles": len(qualification["roles"]),
        "mutation_floor": failure["minimum_mutations"],
        "state_count": len(states),
        "failure_transition_coverage": "ALL_NONTERMINAL_STATES",
        "review_provenance_instances": provenance_instances,
        "historical_review_corrections": correction["row_count"],
        "checkpoint_root_resolved": False,
        "checkpoint_access": 0,
        "numerical_operations": 0,
        "live_installations": 0,
        "package_starts": 0,
        "ids_consumed": 0,
    }
    RESULT.write_bytes(canonical_bytes(result))
    if RESULT.read_bytes() != canonical_bytes(result):
        raise ValueError("validation result readback")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
