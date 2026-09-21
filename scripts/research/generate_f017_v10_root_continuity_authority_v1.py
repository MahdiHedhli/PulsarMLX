#!/usr/bin/env python3
"""Generate the append-only V10 root-continuity/decode authority."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
FIXTURES = ROOT / "specs/017-rust-native-inference-runtime/fixtures"
OLD_MANIFEST = CONTRACTS / "f017-corrected-oracle-event04-runtime-authority-manifest-v9.json"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8") + b"\n"


def binding(relative: str) -> dict:
    raw = (ROOT / relative).read_bytes()
    return {"path": relative, "sha256": hashlib.sha256(raw).hexdigest()}


def render() -> dict[Path, bytes]:
    files: dict[Path, bytes] = {}

    def add(relative: str, value: object) -> dict:
        raw = canonical(value)
        files[ROOT / relative] = raw
        return {"path": relative, "sha256": hashlib.sha256(raw).hexdigest()}

    old = json.loads(OLD_MANIFEST.read_bytes())
    successors = {
        "accounting": "scripts/research/f017_corrected_oracle_event_accounting_v10.py",
        "authority_generator": "scripts/research/generate_f017_v10_root_continuity_authority_v1.py",
        "authorization_parser": "scripts/research/f017_corrected_oracle_authorization_v10.py",
        "authorizer": "scripts/research/validate_f017_corrected_oracle_access_v10.py",
        "canonical_serialization": "scripts/research/f017_canonical_serialization_v10.py",
        "coordinator": "scripts/research/execute_f017_corrected_oracle_event_v10.py",
        "identity_producer": "scripts/research/f017_checkpoint_identity_producer_v10.py",
        "lease_manager": "scripts/research/f017_descriptor_lease_manager_v10.py",
        "lifecycle_artifact_banker": "scripts/research/f017_lifecycle_artifact_v10.py",
        "measurement_validator": "scripts/research/validate_f017_event04_implementation_measurement_v10.py",
        "primary_target_source": "scripts/research/f017_corrected_oracle_primary_target_source_v10.py",
        "primary_wrapper": "scripts/research/f017_corrected_oracle_primary_v10.py",
        "rehearsal": "scripts/research/rehearse_f017_event04_runtime_hardening_v10.py",
        "runtime_outcome_realizer": "scripts/research/f017_runtime_outcome_realizer_v10.py",
        "runtime_qualifier": "scripts/research/qualify_f017_event04_runtime_hardening_v10.py",
        "secondary_target_source": "scripts/research/f017_corrected_oracle_secondary_target_source_v10.py",
        "secondary_wrapper": "scripts/research/f017_corrected_oracle_secondary_v10.py",
        "synthetic_checkpoint_builder": "scripts/research/f017_synthetic_checkpoint_v10.py",
    }
    implementation = {
        name: binding(successors.get(name, value["path"]))
        for name, value in old["implementation"].items()
    }
    implementation.update({
        "accounting_root_continuity": binding("scripts/research/f017_accounting_root_continuity_v1.py"),
        "bounded_artifact_decode": binding("scripts/research/f017_bounded_artifact_decode_v1.py"),
        "bounded_decode_policy": binding("scripts/research/check_f017_bounded_artifact_decode_policy_v1.py"),
        "root_decode_qualifier": binding("scripts/research/qualify_f017_v10_root_continuity_bounded_decode_v1.py"),
        "authority_generator": binding("scripts/research/generate_f017_v10_root_continuity_authority_v1.py"),
        "runtime_authority_validator": binding("scripts/research/validate_f017_event04_runtime_hardening_v10.py"),
    })
    root_contract = binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-accounting-root-continuity-v1.json")
    decode_contract = binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-bounded-artifact-decode-v1.json")
    version_decision = binding("docs/architecture/reviews/evidence/f017-v9-root-continuity-version-decision-v1.json")
    production_plan = binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-production-tensor-plan-v9.json")
    runtime = {
        "schema": "pulsarmlx.f017.event04-runtime-hardening/10.0.0",
        "status": "ROOT_CONTINUITY_AND_BOUNDED_DECODE_IMPLEMENTED_PENDING_REVIEW",
        "active_generation": "NONE",
        "activation_candidate": "V10",
        "version_decision": version_decision,
        "implementation": implementation,
        "accounting_root_continuity": root_contract,
        "bounded_artifact_decode": decode_contract,
        "root_identity_selection": "RETAINED_DIRECTORY_DESCRIPTOR_AND_DEVICE_INODE",
        "accounting_source": "BOUND_TRANSITION_JOURNAL_DURABLE_ARTIFACTS_AND_IN_PROCESS_LOWER_BOUND",
        "fallback_semantics": "EVIDENCE_SINK_NOT_ACCOUNTING_SOURCE",
        "direct_active_runtime_json_parser": "PROHIBITED_OUTSIDE_BOUND_CANONICAL_PARSER",
        "did_closure": {f"DID-{index:02d}": "MECHANICALLY_GATED" for index in range(1, 13)},
        "numerical_semantics_changed": False,
        "original_checkpoint_access": 0,
    }
    runtime_binding = add(
        "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event04-runtime-hardening-v10.json",
        runtime,
    )
    active_binding = add(
        "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-active-generation-v10.json",
        {
            "schema": "pulsarmlx.f017.corrected-oracle-active-generation/10.0.0",
            "active_corrected_oracle_generation": "NONE",
            "activation_candidate": "V10",
            "activation_requires_arbiter_acceptance": True,
            "event_04_operator_go_present": False,
            "event_04_authorization_created": False,
            "event_04_executed": False,
        },
    )
    scientific = {
        "schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-scientific-access/10.0.0",
        "status": "V10_IMPLEMENTED_NO_EVENT_AUTHORITY",
        "active_generation": active_binding,
        "authorization_schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/10.0.0",
        "implementation": implementation,
        "runtime_hardening": runtime_binding,
        "accounting_root_continuity": root_contract,
        "bounded_artifact_decode": decode_contract,
        "numerical_contract": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json"),
        "numerical_capability_policy": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-numerical-capability-policy-v1.json"),
        "production_tensor_plan": production_plan,
        "checkpoint_metadata": binding("docs/validation/glm52-checkpoint.json"),
        "checkpoint_catalog": binding("docs/research/glm52/raw/f016-c01-catalog-0001.json"),
        "limits": {"attempts": 1, "retries": 0, "resume": False, "event_04_authorization_created": False, "event_04_executed": False, "p1_authority": False},
    }
    scientific_binding = add(
        "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v10.json",
        scientific,
    )
    inert_binding = add(
        "specs/017-rust-native-inference-runtime/fixtures/f017-corrected-full-checkpoint-oracle-inert-authorization-v10.json",
        {
            "schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-inert-authorization/10.0.0",
            "state": "INERT",
            "live": False,
            "authority": False,
            "scientific_access": scientific_binding,
            "runtime_observations": None,
            "expected_token_field_permitted": False,
            "attempts": 1,
            "retries": 0,
            "resume": False,
            "p1_authority": False,
            "event_04_authorization_created": False,
        },
    )
    go_binding = add(
        "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event04-execution-go-template-v10.json",
        {
            "schema": "pulsarmlx.f017.corrected-oracle-event04-execution-go-template/10.0.0",
            "state": "INERT_TEMPLATE_NOT_APPROVAL",
            "operator_approval_id": None,
            "authorization_id": None,
            "package_attempt_id": None,
            "primary_event_id": None,
            "secondary_event_id": None,
            "checkpoint_root": None,
            "primary_evidence_root": None,
            "fallback_evidence_root": None,
            "scientific_access": scientific_binding,
            "runtime_hardening": runtime_binding,
            "attempts": 1,
            "retries": 0,
            "resume": False,
            "event_04_authorization_created": False,
            "event_04_executed": False,
        },
    )
    add(
        "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event04-runtime-authority-manifest-v10.json",
        {
            "schema": "pulsarmlx.f017.event04-runtime-authority-manifest/10.0.0",
            "status": "IMPLEMENTED_PENDING_CHALLENGE_AND_ARBITRATION",
            "active_generation": active_binding,
            "scientific_access": scientific_binding,
            "runtime_hardening": runtime_binding,
            "accounting_root_continuity": root_contract,
            "bounded_artifact_decode": decode_contract,
            "production_tensor_plan": production_plan,
            "inert_authorization": inert_binding,
            "operator_go_template": go_binding,
            "implementation": implementation,
            "event_04_authorization_created": False,
            "event_04_executed": False,
            "original_checkpoint_access": 0,
        },
    )
    return files


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    files = render(); drift: list[str] = []
    for path, raw in files.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != raw:
                drift.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    if drift:
        print(json.dumps({"result": "FAIL", "drift": drift}, sort_keys=True)); return 1
    print(json.dumps({"result": "PASS", "mode": "CHECK" if args.check else "GENERATE", "file_count": len(files)}, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
