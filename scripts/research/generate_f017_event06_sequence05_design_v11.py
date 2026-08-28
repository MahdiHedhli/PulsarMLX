#!/usr/bin/env python3
"""Generate the Cycle-11 design-only repair projection."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
import generate_f017_event06_sequence05_design_v10 as v10


ROOT = v10.ROOT
C = v10.C
E = v10.E
S = ROOT / "specs/017-rust-native-inference-runtime/contracts"

SCHEMA4 = S / "f017-event06-sequence05-qualification-schema-authority-v4.json"
INSTALL10 = S / "f017-corrected-oracle-event06-live-installation-interface-v10.json"
QUAL8 = S / "f017-event06-sequence05-qualification-role-requirements-v8.json"
MANIFEST9 = S / "f017-corrected-oracle-event06-readiness-authority-manifest-v9.json"
BEHAVIOR2 = S / "f017-event06-sequence05-generator-behavioral-reproduction-policy-v2.json"
PREPARED6 = E / "f017-event06-v12-sequence05-readiness-authority-manifest-prepared-v6.json"
ADVISORY5 = E / "f017-event06-v12-sequence05-advisory-disposition-ledger-v5.json"
OPUS4_DISPOSITION = E / "f017-event06-v12-sequence05-opus-design-cycle-04-unretained-response-disposition-v1.json"
CYCLE10_REPAIR = E / "f017-event06-v12-sequence05-cycle10-repair-ledger-v1.json"
GRAPH12 = E / "f017-event06-v12-sequence05-design-graph-state-v12.json"
CLAIMS12 = E / "f017-event06-v12-sequence05-design-claim-ledger-v12.json"
GRAPH13 = E / "f017-event06-v12-sequence05-design-graph-state-v13.json"
CLAIMS13 = E / "f017-event06-v12-sequence05-design-claim-ledger-v13.json"

OPUS4_NORMALIZED = E / "f017-event06-v12-sequence05-opus-design-cycle-04-normalized-result.json"
OPUS4_PROVENANCE = E / "f017-event06-v12-sequence05-opus-design-cycle-04-provenance-v1.json"
OPUS10_RESPONSE = E / "f017-event06-v12-sequence05-opus-design-cycle-10-exact-response.md"
OPUS10_NORMALIZED = E / "f017-event06-v12-sequence05-opus-design-cycle-10-normalized-result.json"


def load(path: Path) -> dict:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"not object: {path.relative_to(ROOT)}")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_sha(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def write(path: Path, value: object, check: bool) -> None:
    raw = canonical_bytes(value)
    if check:
        if not path.is_file() or path.read_bytes() != raw:
            raise SystemExit(f"drift: {path.relative_to(ROOT)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def build_schema4() -> dict:
    value = copy.deepcopy(load(v10.v9.SCHEMA))
    value["schema"] = "pulsarmlx.f017.event06-sequence05-qualification-schema-authority/1.3.0"
    value["qualification_schema"] = "pulsarmlx.f017.event06-sequence05-qualification-role-requirements/1.7.0"
    value["installation_schema"] = "pulsarmlx.f017.corrected-oracle-event06-live-installation-interface/1.9.0"
    return value


def build_install10() -> dict:
    value = copy.deepcopy(load(v10.v9.INSTALL))
    value["schema"] = "pulsarmlx.f017.corrected-oracle-event06-live-installation-interface/1.9.0"
    for posture, item in value["posture_mapping"].items():
        scope = item["authority_scope"]
        item["authority_scope"] = scope if isinstance(scope, list) else [scope]
        item["live_authority"] = posture == "PRODUCTION_INSTALLED"
    return value


def build_qual8() -> dict:
    value = copy.deepcopy(load(v10.v9.QUAL))
    schema = build_schema4()
    schema_path = str(SCHEMA4.relative_to(ROOT))
    schema_sha = value_sha(schema)
    value["schema"] = schema["qualification_schema"]
    value["active_validation_gap_ids"] = ["PENDING_CYCLE11_MECHANICAL_VALIDATION"]
    value["validation_result_source"] = "scripts/research/validate_f017_event06_sequence05_design_v8.py"
    for role in ("qualification_role_requirements", "readiness_interface", "live_installation_interface"):
        item = value["roles"][role]
        path_key = "external_schema_authority_path" if role == "qualification_role_requirements" else "schema_authority_path"
        sha_key = "external_schema_authority_sha256" if role == "qualification_role_requirements" else "schema_authority_sha256"
        item[path_key] = schema_path
        item[sha_key] = schema_sha
    return value


def build_manifest9() -> dict:
    value = copy.deepcopy(load(v10.v9.MANIFEST))
    value["schema"] = "pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest-contract/1.8.0"
    value["manifest_schema"] = "pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest/1.8.0"
    value["prepared_instance_path"] = str(PREPARED6.relative_to(ROOT))
    value["prepared_instance_schema"] = "pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest-prepared/1.5.0"
    forbidden = list(value["forbidden_current_binding_paths"])
    prior = str(v10.v9.PREPARED.relative_to(ROOT))
    if prior not in forbidden:
        forbidden.append(prior)
    value["forbidden_current_binding_paths"] = forbidden
    return value


def build_behavior2() -> dict:
    value = copy.deepcopy(load(v10.BEHAVIOR_POLICY))
    value["schema"] = "pulsarmlx.f017.event06-sequence05-generator-behavioral-reproduction-policy/1.1.0"
    value["generator_path"] = str(Path(__file__).relative_to(ROOT))
    return value


def build_opus4_disposition() -> dict:
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-unretained-review-response-disposition/1.0.0",
        "review_cycle": 4,
        "reviewer": "opus",
        "exact_response_bytes_retained": False,
        "normalized_result_path": str(OPUS4_NORMALIZED.relative_to(ROOT)),
        "normalized_result_sha256": sha(OPUS4_NORMALIZED),
        "provenance_path": str(OPUS4_PROVENANCE.relative_to(ROOT)),
        "provenance_sha256": sha(OPUS4_PROVENANCE),
        "provenance_result": load(OPUS4_PROVENANCE)["result"],
        "source_use": "FINDING_ID_CENSUS_ONLY_NOT_EXACT_RESPONSE_SUBSTITUTE",
    }


def support_path(finding_id: str) -> Path:
    return E / f"f017-event06-v12-sequence05-advisory-support-cycle04-{finding_id.lower()}-v2.json"


def build_support(finding_id: str) -> dict:
    disposition = build_opus4_disposition()
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-advisory-support/1.1.0",
        "source_cycle": "cycle04",
        "finding_id": finding_id,
        "disposition": "MECHANICALLY_RESOLVED_PENDING_INDEPENDENT_REVIEW",
        "finding_specific_claim": f"cycle04 {finding_id} is enumerated by the retained Opus normalized result; exact response bytes were not retained",
        "source_response_path": str(OPUS4_NORMALIZED.relative_to(ROOT)),
        "source_response_sha256": sha(OPUS4_NORMALIZED),
        "source_artifact_kind": "NORMALIZED_RESULT_EXACT_RESPONSE_BYTES_UNRETAINED",
        "source_transport_disposition_path": str(OPUS4_DISPOSITION.relative_to(ROOT)),
        "source_transport_disposition_sha256": value_sha(disposition),
        "support_authority_path": str(OPUS4_DISPOSITION.relative_to(ROOT)),
        "support_authority_sha256": value_sha(disposition),
    }


def build_advisory5() -> dict:
    value = copy.deepcopy(load(v10.v9.ADVISORY_LEDGER))
    value["schema"] = "pulsarmlx.f017.event06-v12-sequence05-advisory-disposition-ledger/1.4.0"
    for row in value["rows"]:
        if row["source_cycle"] == "cycle04":
            path = support_path(row["finding_id"])
            support = build_support(row["finding_id"])
            row["support_path"] = str(path.relative_to(ROOT))
            row["support_sha256"] = value_sha(support)
    return value


def build_cycle10_repair() -> dict:
    normalized = load(OPUS10_NORMALIZED)
    rows = [
        ("F-C10-01", "advisory_source_finding_membership"),
        ("F-C10-02", "ast_membership_compare"),
        ("F-C10-03", "qualification_validator_successor"),
        ("F-C10-04", "posture_mapping_types"),
        ("F-C10-05", "generator_contract_path"),
    ]
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-cycle10-repair-ledger/1.0.0",
        "source_response_path": str(OPUS10_RESPONSE.relative_to(ROOT)),
        "source_response_sha256": sha(OPUS10_RESPONSE),
        "source_normalized_path": str(OPUS10_NORMALIZED.relative_to(ROOT)),
        "source_normalized_sha256": sha(OPUS10_NORMALIZED),
        "source_counts": {
            "blocking": normalized["blocking_findings"],
            "required": normalized["required_findings"],
            "advisory": normalized["advisory_findings"],
            "unresolved": normalized["unresolved_claims"],
        },
        "rows": [
            {"finding_id": finding_id, "validator_predicate": predicate, "disposition": "MECHANICALLY_CLOSED_PENDING_INDEPENDENT_REVIEW"}
            for finding_id, predicate in rows
        ],
        "row_count": len(rows),
        "status": "MECHANICALLY_CLOSED_PENDING_INDEPENDENT_REVIEW",
    }


def build_graph12() -> dict:
    normalized = load(OPUS10_NORMALIZED)
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-design-graph-state/1.11.0",
        "review_cycle": 10,
        "reviewed_commit": normalized["reviewed_commit"],
        "reviewed_tree": normalized["reviewed_tree"],
        "opus_counts": {"blocking": 1, "required": 3, "advisory": 1, "unresolved": 0},
        "opus_verdict": normalized["global_verdict"],
        "running_nodes": 0,
        "status": "REPAIR_REQUIRED",
    }


def build_claims12() -> dict:
    normalized = load(OPUS10_NORMALIZED)
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-design-claim-ledger/1.11.0",
        "review_cycle": 10,
        "claim_verdicts": normalized["claim_verdicts"],
        "finding_ids": normalized["finding_ids"],
        "independently_accepted": sum(value == "ACCEPT" for value in normalized["claim_verdicts"].values()),
        "status": "REPAIR_REQUIRED",
    }


def build_graph13() -> dict:
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-design-graph-state/1.12.0",
        "source_review_cycle": 10,
        "source_opus_counts": build_graph12()["opus_counts"],
        "repair_rows": 5,
        "mechanically_closed_rows": 5,
        "independent_review_status": "PENDING",
        "running_nodes": 0,
        "status": "PENDING_INDEPENDENT_REVIEW",
    }


def build_claims13() -> dict:
    rows = build_cycle10_repair()["rows"]
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence05-design-claim-ledger/1.12.0",
        "source_review_cycle": 10,
        "rows": [{"claim_id": row["finding_id"], "state": "MECHANICALLY_SUPPORTED_PENDING_INDEPENDENT_REVIEW"} for row in rows],
        "row_count": len(rows),
        "mechanically_supported": len(rows),
        "independently_accepted": 0,
        "status": "PENDING_INDEPENDENT_REVIEW",
    }


def build_prepared6(implementation_head: str) -> dict:
    value = copy.deepcopy(load(v10.v9.PREPARED))
    value["schema"] = build_manifest9()["prepared_instance_schema"]
    value["implementation_head"] = implementation_head
    value["implementation_tree"] = subprocess.run(
        ["git", "rev-parse", f"{implementation_head}^{{tree}}"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    replacements = {
        "live_installation_interface": (INSTALL10, build_install10()),
        "qualification_role_requirements": (QUAL8, build_qual8()),
    }
    for role, (path, document) in replacements.items():
        value["bindings"][role] = {
            "binding_state": "CURRENT_DESIGN_AUTHORITY",
            "path": str(path.relative_to(ROOT)),
            "sha256": value_sha(document),
        }
    value["validated_binding_count"] = len(load(v10.v9.QUAL)["current_authority_roles"])
    return value


BASE_BUILDERS = {
    SCHEMA4: build_schema4,
    INSTALL10: build_install10,
    QUAL8: build_qual8,
    MANIFEST9: build_manifest9,
    BEHAVIOR2: build_behavior2,
    OPUS4_DISPOSITION: build_opus4_disposition,
    **{support_path(finding_id): (lambda finding_id=finding_id: build_support(finding_id)) for finding_id in ("A1", "A2", "A3", "A4", "A5", "A6")},
    ADVISORY5: build_advisory5,
    CYCLE10_REPAIR: build_cycle10_repair,
    GRAPH12: build_graph12,
    CLAIMS12: build_claims12,
    GRAPH13: build_graph13,
    CLAIMS13: build_claims13,
}


def artifacts() -> dict[Path, object]:
    return {path: builder() for path, builder in BASE_BUILDERS.items()}


def generator_predicate_source_membership() -> bool:
    source = OPUS4_NORMALIZED.read_text()
    return all(f'"{finding_id}"' in source for finding_id in ("A1", "A2", "A3", "A4", "A5", "A6"))


def generator_predicate_posture_types() -> bool:
    mapping = build_install10()["posture_mapping"]
    return all(type(item["live_authority"]) is bool and isinstance(item["authority_scope"], list) for item in mapping.values()) and [key for key, item in mapping.items() if item["live_authority"]] == ["PRODUCTION_INSTALLED"]


GENERATOR_PREDICATES = {
    "source_membership": generator_predicate_source_membership,
    "posture_types": generator_predicate_posture_types,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--implementation-head")
    args = parser.parse_args()
    if not all(predicate() for predicate in v10.GENERATOR_PREDICATES.values()):
        raise SystemExit("predecessor generator predicate failure")
    if not all(predicate() for predicate in GENERATOR_PREDICATES.values()):
        raise SystemExit("successor generator predicate failure")
    for path, value in v10.artifacts().items():
        write(path, value, True)
    for path, value in artifacts().items():
        write(path, value, args.check)
    if args.check:
        if not PREPARED6.is_file():
            raise SystemExit(f"drift: {PREPARED6.relative_to(ROOT)}")
        prepared = load(PREPARED6)
        write(PREPARED6, build_prepared6(prepared["implementation_head"]), True)
    elif args.implementation_head:
        write(PREPARED6, build_prepared6(args.implementation_head), False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
