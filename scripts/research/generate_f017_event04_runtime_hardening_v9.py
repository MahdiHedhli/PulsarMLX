#!/usr/bin/env python3
"""Generate V9 execution-hardening authorities; ``--check`` is read-only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from f017_event04_tensor_plan_v9 import build_plan, validate_plan


ROOT = Path(__file__).resolve().parents[2]; CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"; FIXTURES = ROOT / "specs/017-rust-native-inference-runtime/fixtures"


def canonical(value: object) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode() + b"\n"
def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def binding(relative: str) -> dict: return {"path": relative, "sha256": sha(ROOT / relative)}


def render() -> dict[Path, bytes]:
    files: dict[Path, bytes] = {}
    def add(relative: str, value: object) -> dict:
        path = ROOT / relative; raw = canonical(value); files[path] = raw
        return {"path": relative, "sha256": hashlib.sha256(raw).hexdigest()}
    plan_binding = add("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-production-tensor-plan-v9.json", validate_plan(build_plan()))
    implementation = {name: binding(path) for name, path in {
        "authorization_parser": "scripts/research/f017_corrected_oracle_authorization_v9.py",
        "authorizer": "scripts/research/validate_f017_corrected_oracle_access_v9.py",
        "coordinator": "scripts/research/execute_f017_corrected_oracle_event_v9.py",
        "identity_producer": "scripts/research/f017_checkpoint_identity_producer_v9.py",
        "lease_manager": "scripts/research/f017_descriptor_lease_manager_v9.py",
        "primary_target_source": "scripts/research/f017_corrected_oracle_primary_target_source_v9.py",
        "secondary_target_source": "scripts/research/f017_corrected_oracle_secondary_target_source_v9.py",
        "primary_wrapper": "scripts/research/f017_corrected_oracle_primary_v9.py",
        "secondary_wrapper": "scripts/research/f017_corrected_oracle_secondary_v9.py",
        "accounting": "scripts/research/f017_corrected_oracle_event_accounting_v9.py",
        "runtime_outcome_realizer": "scripts/research/f017_runtime_outcome_realizer_v9.py",
        "runtime_qualifier": "scripts/research/qualify_f017_event04_runtime_hardening_v9.py",
        "rehearsal": "scripts/research/rehearse_f017_event04_runtime_hardening_v9.py",
        "memory_gate": "scripts/research/f017_memory_gate_v9.py",
        "tensor_plan_builder": "scripts/research/f017_event04_tensor_plan_v9.py",
        "independent_descriptor_checker": "scripts/research/check_f017_descriptor_type_safety_v9.py",
        "authority_generator": "scripts/research/generate_f017_event04_runtime_hardening_v9.py",
        "measurement_validator": "scripts/research/validate_f017_event04_implementation_measurement_v9.py",
    }.items()}
    runtime = {"schema": "pulsarmlx.f017.event04-runtime-hardening/9.0.0", "status": "IMPLEMENTED_PENDING_WHOLE_DOMAIN_ACCEPTANCE",
               "supersedes_execution_preparation": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v8.json"),
               "base_causal_authority": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-causal-artifact-dag-v8.json"),
               "versioning_decision": "V9_REQUIRED_BY_LEASE_STATE_RELEASE_EVIDENCE_SCOPE_AND_FAILURE_TERMINALIZATION_SEMANTICS",
               "implementation": implementation, "production_tensor_plan": plan_binding,
               "did_closure": {f"DID-{index:02d}": "MECHANICALLY_GATED" for index in range(1, 13)},
               "release_states": ["OPEN", "CLOSE_ATTEMPTED", "CLOSED", "CLOSE_FAILED", "UNKNOWN"],
               "release_artifacts": ["descriptor_release_start", "descriptor_close_event", "descriptor_release_report", "descriptor_release_receipt", "descriptor_release_terminal"],
               "accounting_source": "VALIDATED_DURABLE_START_ARTIFACTS", "runtime_failure_outcomes": 47,
               "synthetic_root_authority": "STRUCTURAL_MANIFEST_AND_CANONICAL_ROOT", "memory_gates": ["MINT_TIME", "PACKAGE_START"],
               "numerical_semantics_changed": False, "original_checkpoint_access": 0}
    runtime_binding = add("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event04-runtime-hardening-v9.json", runtime)
    for role, wrapper, numerical in (("PRIMARY", "scripts/research/f017_corrected_oracle_primary_v9.py", "scripts/research/f017_corrected_oracle_primary_numerics_v2.py"),
                                     ("SECONDARY", "scripts/research/f017_corrected_oracle_secondary_v9.py", "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py")):
        add(f"specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-{role.lower()}-capability-v9.json",
            {"schema": "pulsarmlx.f017.corrected-oracle-consumer-capability/9.0.0", "role": role,
             "authorization_schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/9.0.0",
             "producer": binding(wrapper), "numerical_authority": binding(numerical), "descriptor_transport": "INHERITED_FILE_DESCRIPTORS",
             "descriptor_ordinals": [2, 3, 4, 5, 6], "all_descriptors_materially_consumed": True, "path_reopen_count": 0})
    active_binding = add("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-active-generation-v9.json",
        {"schema": "pulsarmlx.f017.corrected-oracle-active-generation/9.0.0", "active_corrected_oracle_generation": "V9",
         "activation_requires_whole_domain_acceptance": True, "event_04_operator_go_present": False,
         "event_04_authorization_created": False, "event_04_executed": False,
         "superseded_live_generations": ["V1", "V2", "V3", "V6", "V7", "V8"]})
    scientific = {"schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-scientific-access/9.0.0",
                  "status": "EXECUTION_HARDENING_IMPLEMENTED_NO_EVENT_AUTHORITY", "active_generation": active_binding,
                  "authorization_schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/9.0.0",
                  "implementation": implementation, "runtime_hardening": runtime_binding, "production_tensor_plan": plan_binding,
                  "numerical_contract": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json"),
                  "numerical_capability_policy": binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-numerical-capability-policy-v1.json"),
                  "checkpoint_metadata": binding("docs/validation/glm52-checkpoint.json"), "checkpoint_catalog": binding("docs/research/glm52/raw/f016-c01-catalog-0001.json"),
                  "limits": {"attempts": 1, "retries": 0, "resume": False, "event_04_authorization_created": False,
                             "event_04_executed": False, "p1_authority": False, "graph_tensors": 1410, "non_access_tensors": 399,
                             "graph_shards": [2, 3, 4, 5, 6], "path_reopen_count": 0}}
    scientific_binding = add("specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v9.json", scientific)
    inert_binding = add("specs/017-rust-native-inference-runtime/fixtures/f017-corrected-full-checkpoint-oracle-inert-authorization-v9.json",
        {"schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-inert-authorization/9.0.0", "state": "INERT", "live": False,
         "authority": False, "scientific_access": scientific_binding, "runtime_observations": None, "expected_token_field_permitted": False,
         "attempts": 1, "retries": 0, "resume": False, "p1_authority": False, "event_04_authorization_created": False})
    template_binding = add("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event04-execution-go-template-v9.json",
        {"schema": "pulsarmlx.f017.corrected-oracle-event04-execution-go-template/9.0.0", "state": "INERT_TEMPLATE_NOT_APPROVAL",
         "operator_approval_id": None, "authorization_id": None, "package_attempt_id": None, "primary_event_id": None, "secondary_event_id": None,
         "scientific_access": scientific_binding, "runtime_hardening": runtime_binding, "attempts": 1, "retries": 0, "resume": False,
         "event_04_authorization_created": False, "event_04_executed": False})
    add("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event04-runtime-authority-manifest-v9.json",
        {"schema": "pulsarmlx.f017.event04-runtime-authority-manifest/9.0.0", "status": "IMPLEMENTED_PENDING_WHOLE_DOMAIN_ACCEPTANCE",
         "active_generation": active_binding, "scientific_access": scientific_binding, "runtime_hardening": runtime_binding,
         "production_tensor_plan": plan_binding, "inert_authorization": inert_binding, "operator_go_template": template_binding,
         "implementation": implementation, "event_04_authorization_created": False, "event_04_executed": False, "original_checkpoint_access": 0})
    return files


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args(); files = render()
    drift = []
    for path, raw in files.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != raw: drift.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    if drift: print(json.dumps({"result": "FAIL", "drift": drift}, sort_keys=True)); return 1
    print(json.dumps({"result": "PASS", "mode": "CHECK" if args.check else "GENERATE", "file_count": len(files)}, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
