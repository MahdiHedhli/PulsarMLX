#!/usr/bin/env python3
"""Generate exact V8 implementation bindings before activation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
FIXTURES = ROOT / "specs/017-rust-native-inference-runtime/fixtures"
RESEARCH = ROOT / "scripts/research"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode() + b"\n"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(relative: str) -> dict:
    return {"path": relative, "sha256": sha(ROOT / relative)}


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def generate() -> None:
    primary = "scripts/research/f017_corrected_oracle_primary_v8.py"
    secondary = "scripts/research/f017_corrected_oracle_secondary_v8.py"
    for role, producer, numerical in (
        ("PRIMARY", primary, "scripts/research/f017_corrected_oracle_primary_numerics_v2.py"),
        ("SECONDARY", secondary, "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py"),
    ):
        write(CONTRACTS / f"f017-corrected-oracle-{role.lower()}-capability-v8.json", {
            "schema": "pulsarmlx.f017.corrected-oracle-consumer-capability/8.0.0",
            "status": "ACTIVE_IMPLEMENTATION_NO_EVENT_AUTHORITY", "active_generation": "V8", "role": role,
            "authorization_schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/8.0.0",
            "producer": binding(producer), "numerical_authority": binding(numerical),
            "descriptor_transport": "INHERITED_FILE_DESCRIPTORS", "descriptor_count": 5,
            "descriptor_ordinals": [2, 3, 4, 5, 6], "path_reopen_count": 0,
            "candidate_validation_side_effects": 0,
        })
    active = {
        "schema": "pulsarmlx.f017.corrected-oracle-active-generation/8.0.0",
        "active_corrected_oracle_generation": "V8",
        "implemented_generation": "V8", "event_04_operator_go_present": False,
        "live_authority_without_fresh_operator_go": False,
        "event_04_authorization_created": False, "event_04_executed": False,
        "superseded_live_generations": ["V1", "V2", "V3", "V6", "V7"],
        "historical_reconstruction": "EXACT_GIT_OBJECTS_ONLY",
    }
    write(CONTRACTS / "f017-corrected-oracle-active-generation-v8.json", active)
    implementation = {
        "authorization_parser": binding("scripts/research/f017_corrected_oracle_authorization_v8.py"),
        "authorizer": binding("scripts/research/validate_f017_corrected_oracle_access_v8.py"),
        "coordinator": binding("scripts/research/execute_f017_corrected_oracle_event_v8.py"),
        "identity_producer": binding("scripts/research/f017_checkpoint_identity_producer_v8.py"),
        "lease_manager": binding("scripts/research/f017_descriptor_lease_manager_v8.py"),
        "primary_target_source": binding("scripts/research/f017_corrected_oracle_primary_target_source_v8.py"),
        "secondary_target_source": binding("scripts/research/f017_corrected_oracle_secondary_target_source_v8.py"),
        "primary_wrapper": binding(primary), "secondary_wrapper": binding(secondary),
        "comparison": binding("scripts/research/f017_corrected_oracle_compare_v8.py"),
        "accounting_implementation": binding("scripts/research/f017_corrected_oracle_event_accounting_v8.py"),
        "serialization_implementation": binding("scripts/research/f017_canonical_serialization_v8.py"),
        "artifact_banker": binding("scripts/research/f017_lifecycle_artifact_v8.py"),
    }
    scientific = {
        "schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-scientific-access/8.0.0",
        "status": "ACTIVE_IMPLEMENTATION_NO_EVENT_AUTHORITY", "active_generation": "V8",
        "authorization_schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/8.0.0",
        "implementation": implementation,
        "primary_capability": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-primary-capability-v8.json"),
        "secondary_capability": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-secondary-capability-v8.json"),
        "causal_artifact_dag": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-causal-artifact-dag-v8.json"),
        "descriptor_scalar_contract": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-descriptor-scalar-contract-v8.json"),
        "checkpoint_identity_contract": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-checkpoint-identity-v8.json"),
        "descriptor_continuity_contract": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-descriptor-continuity-v8.json"),
        "event_accounting_contract": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event-accounting-v8.json"),
        "serialization_contract": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-canonical-serialization-v8.json"),
        "numerical_contract": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json"),
        "checkpoint_metadata": binding("docs/validation/glm52-checkpoint.json"),
        "checkpoint_access": {"future_live_shard_count": 6, "identity_only_count": 1, "graph_descriptor_count": 5, "read_only": True, "path_reopen_count": 0},
        "limits": {"attempts": 1, "retries": 0, "resume": False, "event_04_authorization_created": False, "event_04_executed": False, "p1_authority": False},
    }
    scientific_path = CONTRACTS / "f017-corrected-full-checkpoint-oracle-scientific-access-v8.json"
    write(scientific_path, scientific)
    inert = {
        "schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-inert-authorization/8.0.0",
        "state": "INERT", "live": False, "authority": False,
        "authorization_id": "F017-CORRECTED-ORACLE-INERT-V8",
        "package_attempt_id": "F017-CORRECTED-ORACLE-INERT-PACKAGE-V8",
        "primary_event_id": "F017-CORRECTED-ORACLE-INERT-PRIMARY-V8",
        "secondary_event_id": "F017-CORRECTED-ORACLE-INERT-SECONDARY-V8",
        "scientific_access_contract": {"path": str(scientific_path.relative_to(ROOT)), "sha256": sha(scientific_path)},
        "runtime_observations": None, "expected_token_field_permitted": False,
        "attempts": 1, "retries": 0, "resume": False, "p1_authority": False,
    }
    inert_path = FIXTURES / "f017-corrected-full-checkpoint-oracle-inert-authorization-v8.json"
    write(inert_path, inert)
    manifest = {
        "schema": "pulsarmlx.f017.corrected-oracle-v8-implementation-authority-manifest/1.0.0",
        "status": "ACTIVE_IMPLEMENTATION_NO_EVENT_AUTHORITY", "active_generation": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-active-generation-v8.json"),
        "scientific_access": binding(str(scientific_path.relative_to(ROOT))),
        "inert_authorization": binding(str(inert_path.relative_to(ROOT))),
        "implementation": implementation,
        "design_authority": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-v8-design-authority-manifest.json"),
        "synthetic_qualifier": binding("scripts/research/qualify_f017_lifecycle_v8.py"),
        "synthetic_qualification": binding("docs/architecture/reviews/evidence/f017-corrected-oracle-lifecycle-v8-synthetic-qualification-v3.json"),
        "production_shaped_rehearsal": binding("scripts/research/rehearse_f017_corrected_oracle_event04_v8.py"),
        "production_shaped_rehearsal_evidence": binding("docs/architecture/reviews/evidence/f017-corrected-oracle-event04-production-shaped-rehearsal-v8-v3.json"),
        "implementation_validator": binding("scripts/research/validate_f017_lifecycle_v8_implementation.py"),
        "operator_go_template": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event04-operator-go-template-v8.json"),
        "event_04_authorization_created": False, "event_04_executed": False,
        "original_checkpoint_access": 0,
    }
    write(CONTRACTS / "f017-corrected-oracle-v8-implementation-authority-manifest.json", manifest)


if __name__ == "__main__":
    generate()
