#!/usr/bin/env python3
"""Independent, fail-closed validation of the F017 lifecycle-v5 domain."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any

from f017_lifecycle_semantics_v5 import (
    MODEL_PATH,
    ROOT,
    canonical_json_bytes,
    canonical_sha256,
    derive_accounting,
    derive_outcome_obligations,
    derive_path_timing,
    derive_serialization,
    load_json,
    validate_model,
)

CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
PATHS = {
    "outcomes": CONTRACTS / "f017-corrected-oracle-outcome-obligations-v5.json",
    "accounting": CONTRACTS / "f017-corrected-oracle-event-accounting-v5.json",
    "paths": CONTRACTS / "f017-corrected-oracle-path-timing-v1.json",
    "serialization": CONTRACTS / "f017-canonical-json-bytes-v1.json",
    "interface": CONTRACTS / "f017-corrected-oracle-authorization-consumer-interface-v5.json",
    "registry": CONTRACTS / "f017-corrected-oracle-lifecycle-identity-registry-v5.json",
    "matrix": CONTRACTS / "f017-corrected-oracle-lifecycle-binding-matrix-v5.json",
    "schemas": CONTRACTS / "f017-corrected-oracle-artifact-schemas-v5.json",
}

EXPECTED_ACCOUNTING = {
    "HISTORICAL_REAL_PAYLOAD_LEDGER": (None, 0),
    "CORRECTED_ORACLE_PACKAGE_ATTEMPT_LEDGER": ("T11_START_PACKAGE", 1),
    "CORRECTED_ORACLE_PRIMARY_EVENT_LEDGER": ("T12_START_PRIMARY", 1),
    "CORRECTED_ORACLE_SECONDARY_EVENT_LEDGER": ("T14_START_SECONDARY", 1),
}
EXPECTED_SERIALIZATION = {
    "identity": "F017_CANONICAL_JSON_BYTES_V1",
    "encoding": "UTF-8",
    "bom": False,
    "ensure_ascii": True,
    "duplicate_keys": "REJECT",
    "nonfinite_numbers": "REJECT",
    "sort_keys": True,
    "separators": [",", ":"],
    "insignificant_whitespace": False,
    "trailing_newline_count": 1,
    "artifact_sha256_domain": "SHA256_EXACT_CANONICAL_BYTES_OF_COMPLETE_ARTIFACT",
    "self_sha_inside_artifact": False,
}

# These fixed digests are the independent reviewed semantic anchor.  Generated
# views may change only when this validator is deliberately revised and reviewed;
# regenerating documents from a coordinated model mutation is insufficient.
EXPECTED_SEMANTIC_PROJECTION_SHAS = {
    "authorization_document": "2c70b27182a9c5c6a1e77f56056fd0ec6a89e7ac64139b9be14ca2edc0e8a63a",
    "transitions": "4f5d08ac6c5e2a963581285dc7abdaa91853cc181d06a8a87c327e5f3655197c",
    "outcomes": "73d636a9b24e1d317c8870dbe90b47d06d1cff7559bb25983309175f70ba7494",
    "artifact_authority": "f13cabf377fe9ad2312b95adf25830ce7852a07b409733759dd6eb04f019235c",
    "path_authority": "12c215e3aa2f4d8f734e5f93daf8ff3360c49d1f4abd84a7c3f8a274523add74",
    "serialization": "24fff464845971036876016a93401fee9bb239d08f5111798ae7eeabba857975",
    "measurement_authority": "aedc88f53bdfcffa7e0ef2e950d822540c54afd18459a1f2518b415847684d71",
    "accounting": "1de6086dade7f80c32d0b1f855137c7c21d41edc06cbfb8b4d01884a5daf98e9",
    "activation_supersession": "78a4e2e8e25e462fd6c7bc1e1ca04f0c90dc924314bd79861a583263cfb10fae",
    "registry_grammars": "4b822649c36b1fc5e75bd600a0266cf2f93607720a3063f3dc74af3ca66f2129",
}


def _semantic_projections(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "authorization_document": model["authorization_document"],
        "transitions": model["transitions"],
        "outcomes": {
            "outcome_classes": model["outcome_classes"],
            "terminal_branches": model["terminal_branches"],
        },
        "artifact_authority": {
            "artifact_classes": model["artifact_classes"],
            "artifact_payload_key_census": model["artifact_payload_key_census"],
            "artifact_self_sha_identities": model["artifact_self_sha_identities"],
            "artifact_file_validation": model["artifact_file_validation"],
            "artifact_path_descriptors": model["artifact_path_descriptors"],
            "artifact_removals": model["artifact_removals"],
        },
        "path_authority": {
            "path_roles": model["path_roles"],
            "absent_path_validation": model["absent_path_validation"],
            "root_relation_matrix": model["root_relation_matrix"],
        },
        "serialization": model["serialization"],
        "measurement_authority": model["measurement_authority"],
        "accounting": {
            "accounting_semantics": model["accounting_semantics"],
            "ledger_targets": model["ledger_targets"],
            "start_transition_by_actor": model["start_transition_by_actor"],
        },
        "activation_supersession": {
            "authority_activation": model["authority_activation"],
            "supersession": model["supersession"],
        },
    }


def _identity_type(name: str) -> str:
    if name.endswith("_sha256"): return "SHA256"
    if name.endswith("_id"): return "LIVE_ID"
    if name.endswith("_root") or name.endswith("_path"): return "PATH_DESCRIPTOR"
    if name.endswith("_head"): return "GIT_COMMIT"
    if name.endswith("_terminal") or name.endswith("_delta") or name.endswith("_count") or name.endswith("_ns") or name in {"prompt_token", "position", "top_n"}: return "INTEGER"
    if name.endswith("_role"): return "ROLE"
    return "EXACT_SCALAR"


def _authorization_identities(model: dict[str, Any]) -> set[str]:
    doc = model["authorization_document"]
    result = {key for key in doc["top_level_keys"] if key not in {"schema", "package", "primary", "secondary", "context", "limits", "state", "live"}}
    result.update(f"package_{key}" for key in doc["package_keys"])
    result.update(f"primary_{key}" for key in doc["consumer_keys"])
    result.update(f"secondary_{key}" for key in doc["consumer_keys"])
    result.update(doc["context_keys"])
    result.update(doc["limits_keys"])
    result.update({"authorization_schema", "authorization_state", "authorization_live"})
    return result


def _authorization_json_path(model: dict[str, Any], name: str) -> str:
    doc = model["authorization_document"]
    if name == "authorization_schema": return "$.schema"
    if name == "authorization_state": return "$.state"
    if name == "authorization_live": return "$.live"
    if name in doc["top_level_keys"]: return f"$.{name}"
    for prefix, keys in (("package", doc["package_keys"]), ("primary", doc["consumer_keys"]), ("secondary", doc["consumer_keys"])):
        marker = prefix + "_"
        if name.startswith(marker) and name[len(marker):] in keys:
            return f"$.{prefix}.{name[len(marker):]}"
    if name in doc["context_keys"]: return f"$.context.{name}"
    if name in doc["limits_keys"]: return f"$.limits.{name}"
    raise ValueError(f"authorization path absent: {name}")


def _expected_binding_surface(model: dict[str, Any], obligations: dict[str, Any]) -> tuple[set[str], dict[str, dict[str, set[str]]]]:
    transitions = {item["id"]: item for item in model["transitions"]}
    base = _authorization_identities(model)
    all_names = set(base)
    by_artifact: dict[str, dict[str, set[str]]] = {name: {} for name in model["artifact_classes"]}
    authorization_artifacts = {"candidate_authorization", "installed_authorization"}
    for outcome_name, outcome in obligations["variants"].items():
        visible = set(base)
        for tid in outcome["trace"]:
            transition = transitions[tid]
            introduced = set(transition["identities_introduced"])
            all_names.update(introduced)
            for artifact in transition["artifacts_created"]:
                own_sha = model["artifact_self_sha_identities"][artifact]
                by_artifact[artifact][outcome_name] = base if artifact in authorization_artifacts else (visible | introduced) - {own_sha}
            visible.update(introduced)
    for transition in model["transitions"]:
        all_names.update(transition["identities_introduced"])
    return all_names, by_artifact


def _expected_interface(model: dict[str, Any], schemas: dict[str, Any]) -> dict[str, Any]:
    doc = model["authorization_document"]
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-authorization-consumer-interface/5.0.0",
        "authorization_schema": model["authorization_schema"],
        "semantic_model_path": str(MODEL_PATH.relative_to(ROOT)),
        "semantic_model_sha256": canonical_sha256(model),
        "top_level_keys": doc["top_level_keys"],
        "package_keys": doc["package_keys"],
        "consumer_keys": doc["consumer_keys"],
        "context_keys": doc["context_keys"],
        "limits_keys": doc["limits_keys"],
        "pinned_values": doc["pinned_values"],
        "artifact_schema_authority": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-artifact-schemas-v5.json",
        "artifact_schema_authority_sha256": canonical_sha256(schemas),
        "candidate_authority": False,
        "live_authority_requirements": ["CANONICAL_INSTALL_PATH", "CANDIDATE_INSTALL_BYTE_IDENTITY", "INSTALLATION_RECEIPT", "OPERATOR_APPROVAL", "DUAL_CONSUMER_VALIDATION", "UNUSED_ROOTS"],
        "target_mode_requires_installation_receipt": True,
        "candidate_path_descriptor": {**model["artifact_path_descriptors"]["candidate_authorization"], "authority": False},
        "installed_path_descriptor": {**model["artifact_path_descriptors"]["installed_authorization"], "authorization_field": "canonical_install_path", "exact_path_equality": True},
        "expected_token_field_permitted": False,
        "validation_side_effect_limits": {"checkpoint_opens": 0, "checkpoint_reads": 0, "checkpoint_mmaps": 0, "state_roots_created": 0, "numerical_operations": 0},
    }


def _exact_canonical(path: Path, value: Any) -> None:
    if path.read_bytes() != canonical_json_bytes(value):
        raise ValueError(f"noncanonical or readback byte drift: {path.relative_to(ROOT)}")


def validate_semantics(model: dict[str, Any]) -> None:
    validate_model(model)
    for name, projection in _semantic_projections(model).items():
        if canonical_sha256(projection) != EXPECTED_SEMANTIC_PROJECTION_SHAS[name]:
            raise ValueError(f"independently anchored semantic projection drift: {name}")
    if model["authorization_schema"] != "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/5.0.0":
        raise ValueError("authorization generation")
    if model["supersession"] != {
        "v1_v2_v3_live_mint": "HISTORICAL_ONLY_REJECT_LIVE_MINT",
        "v1_v2_v3_target_execution": "HISTORICAL_ONLY_REJECT_NEW_EXECUTION",
        "v4_design": "REJECTED_HISTORICAL_DESIGN_ONLY",
        "event_04_requires_generation": 5,
    }:
        raise ValueError("supersession semantics")
    if model.get("accounting_semantics") != {"authorization_mint_execution_delta": 0, "consumer_grant_is_start": False, "reservation_is_execution": False}:
        raise ValueError("reservation/execution semantic drift")
    for target, (transition, delta) in EXPECTED_ACCOUNTING.items():
        actual = model["ledger_targets"].get(target)
        if actual is None or actual.get("advance_transition") != transition or actual.get("delta") != delta:
            raise ValueError(f"accounting semantic drift: {target}")
    historical = model["ledger_targets"]["HISTORICAL_REAL_PAYLOAD_LEDGER"]
    if historical.get("before") != 175 or historical.get("after") != 175 or historical.get("authority_sha256") != "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e":
        raise ValueError("historical ledger drift")
    if any(model["serialization"].get(key) != value for key, value in EXPECTED_SERIALIZATION.items()):
        raise ValueError("serialization semantic drift")
    absent = model["absent_path_validation"]
    if absent.get("resolve_absent_leaf_strictly") is not False or absent.get("resolve_parent_strictly") is not True or absent.get("leaf_absence_check") != "LSTAT_ENOENT":
        raise ValueError("absent path timing drift")
    if model["authority_activation"].get("candidate_is_authority") is not False or model["authority_activation"].get("requires_installation_receipt") is not True:
        raise ValueError("candidate/live authority drift")
    doc = model["authorization_document"]
    if "package_attempt_id" not in doc["top_level_keys"] or doc["top_level_keys"].count("package_attempt_id") != 1:
        raise ValueError("package attempt identity not canonical")
    if doc["pinned_values"].get("expected_token_field_permitted") is not False:
        raise ValueError("expected-token quarantine drift")
    if doc["pinned_values"].get("p1_authority") != "PROHIBITED" or doc["pinned_values"].get("authority_generation") != 5:
        raise ValueError("generation/P1 authority drift")
    if set(model["artifact_payload_key_census"]) != set(model["artifact_classes"]):
        raise ValueError("payload census authority")
    required_measurements = {
        "scripts/research/f017_lifecycle_semantics_v5.py",
        "scripts/research/generate_f017_lifecycle_v5_authorities.py",
        "scripts/research/validate_f017_lifecycle_semantic_authority_v5.py",
        "scripts/research/validate_f017_corrected_oracle_access.py",
        "scripts/research/execute_f017_corrected_oracle_event.py",
        "scripts/research/validate_f017_corrected_oracle_access_v2.py",
        "scripts/research/execute_f017_corrected_oracle_event_v2.py",
        "scripts/research/validate_f017_corrected_oracle_access_v3.py",
        "scripts/research/execute_f017_corrected_oracle_event_v3.py",
        "scripts/research/f017_corrected_oracle_primary_v3.py",
        "scripts/research/f017_corrected_oracle_secondary_v3.py",
        "scripts/research/f017_corrected_oracle_authorization_v5.py",
        "scripts/research/f017_corrected_oracle_primary_v5.py",
        "scripts/research/f017_corrected_oracle_secondary_v5.py",
        "scripts/research/validate_f017_corrected_oracle_access_v5.py",
        "scripts/research/execute_f017_corrected_oracle_event_v5.py",
        "scripts/research/f017_corrected_oracle_primary.py",
        "scripts/research/f017_corrected_oracle_secondary.py",
        "scripts/research/f017_oracle_primary_decoders.py",
        "scripts/research/f017_macos_memory_observation_v1.py",
        "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-semantic-model-v1.json",
        "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-authorization-consumer-interface-v5.json",
        "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event-accounting-v5.json",
        "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v5.json",
    }
    if set(model["measurement_authority"].get("required_entries", [])) != required_measurements:
        raise ValueError("implementation measurement entry census")
    retirement_sentinels = {
        "scripts/research/validate_f017_corrected_oracle_access.py": "HISTORICAL_ONLY: v1 live mint is permanently retired",
        "scripts/research/execute_f017_corrected_oracle_event.py": "HISTORICAL_ONLY: corrected-oracle coordinator v1 is superseded and ineligible for live authority",
        "scripts/research/validate_f017_corrected_oracle_access_v2.py": "HISTORICAL_ONLY: v2 live mint is permanently retired",
        "scripts/research/execute_f017_corrected_oracle_event_v2.py": "HISTORICAL_ONLY: v2 execution is permanently retired",
        "scripts/research/validate_f017_corrected_oracle_access_v3.py": "HISTORICAL_ONLY: v3 live mint is permanently retired",
        "scripts/research/execute_f017_corrected_oracle_event_v3.py": "HISTORICAL_ONLY: v3 production execution is permanently retired",
        "scripts/research/f017_corrected_oracle_primary_v3.py": "HISTORICAL_ONLY: v3 primary production target is permanently retired",
        "scripts/research/f017_corrected_oracle_secondary_v3.py": "HISTORICAL_ONLY: v3 secondary production target is permanently retired",
    }
    for relative, sentinel in retirement_sentinels.items():
        source = (ROOT / relative).read_text(encoding="utf-8")
        if sentinel not in source:
            raise ValueError(f"historical live surface remains reachable: {relative}")


def validate_bundle(model: dict[str, Any], documents: dict[str, dict[str, Any]]) -> dict[str, int]:
    validate_semantics(model)
    expected = {
        "outcomes": derive_outcome_obligations(model),
        "accounting": derive_accounting(model),
        "paths": derive_path_timing(model),
        "serialization": derive_serialization(model),
    }
    for name, value in expected.items():
        if documents[name] != value:
            raise ValueError(f"generated semantic authority drift: {name}")
    model_sha = canonical_sha256(model)
    for name, document in documents.items():
        if name in {"registry", "matrix", "schemas", "interface"} and document.get("semantic_model_sha256") != model_sha:
            raise ValueError(f"unbound semantic model: {name}")
    registry, matrix, schemas, interface = (documents[name] for name in ("registry", "matrix", "schemas", "interface"))
    expected_names, expected_bindings = _expected_binding_surface(model, expected["outcomes"])
    identities = registry.get("identities")
    if not isinstance(identities, list) or registry.get("identity_count") != len(identities):
        raise ValueError("identity registry census")
    names = [item.get("name") for item in identities]
    if len(names) != len(set(names)) or set(names) != expected_names:
        raise ValueError("identity registry completeness")
    if canonical_sha256(registry.get("grammars")) != EXPECTED_SEMANTIC_PROJECTION_SHAS["registry_grammars"]:
        raise ValueError("independently anchored registry grammar drift")
    identity_key_census = {
        "name", "type", "grammar", "authority_source", "derivation_permitted",
        "mismatch_behavior", "bound_artifact_outcomes",
    }
    authorization_names = _authorization_identities(model)
    for identity in identities:
        if set(identity) != identity_key_census:
            raise ValueError(f"identity record key census: {identity.get('name')}")
        name = identity["name"]
        expected_bound = {
            artifact: sorted(outcome for outcome, values in outcomes.items() if name in values)
            for artifact, outcomes in expected_bindings.items()
            if any(name in values for values in outcomes.values())
        }
        expected_source = "AUTHORIZATION_DOCUMENT" if name in authorization_names else "SEMANTIC_TRANSITION_READBACK"
        expected_grammar = registry["grammars"][_identity_type(name)]
        if identity.get("type") != _identity_type(name) or identity.get("grammar") != expected_grammar or identity.get("authority_source") != expected_source or identity.get("derivation_permitted") is not False or identity.get("mismatch_behavior") != "FAIL_CLOSED_BEFORE_NEXT_TRANSITION" or identity.get("bound_artifact_outcomes") != expected_bound:
            raise ValueError(f"identity semantic drift: {name}")
    artifact_names = set(model["artifact_classes"])
    if matrix.get("columns") != sorted(artifact_names) or matrix.get("row_count") != len(matrix.get("rows", [])):
        raise ValueError("binding matrix census")
    if {row.get("identity") for row in matrix["rows"]} != set(names):
        raise ValueError("binding registry/matrix mismatch")
    required_cells = 0
    for row in matrix["rows"]:
        if set(row.get("cells", {})) != artifact_names:
            raise ValueError(f"matrix artifact census: {row.get('identity')}")
        for artifact, cell in row["cells"].items():
            outcomes = cell.get("required_outcomes")
            expected_outcomes = sorted(outcome for outcome, values in expected_bindings[artifact].items() if row["identity"] in values)
            if outcomes != expected_outcomes:
                raise ValueError(f"matrix outcome: {row['identity']}/{artifact}")
            if outcomes:
                required_cells += 1
                expected_path = _authorization_json_path(model, row["identity"]) if artifact in {"candidate_authorization", "installed_authorization"} and row["identity"] in _authorization_identities(model) else f"$.bindings.{row['identity']}"
                if cell.get("json_path") != expected_path or cell.get("type") != _identity_type(row["identity"]) or not all(cell.get(key) for key in ("source", "equality_rule", "validator", "failure_classification")):
                    raise ValueError(f"unresolved binding cell: {row['identity']}/{artifact}")
            elif any(cell.get(key) is not None for key in ("json_path", "type", "source", "equality_rule", "validator", "failure_classification")):
                raise ValueError(f"spurious optional binding cell: {row['identity']}/{artifact}")
    if matrix.get("required_cell_count") != required_cells or matrix.get("status") != "LIFECYCLE_BINDING_COVERAGE: COMPLETE":
        raise ValueError("binding coverage count/status")
    artifact_schemas = schemas.get("artifacts")
    if not isinstance(artifact_schemas, dict) or set(artifact_schemas) != artifact_names:
        raise ValueError("artifact schema bidirectional census")
    for artifact, schema in artifact_schemas.items():
        if schema.get("artifact_schema_id") != model["artifact_classes"][artifact]["schema"]:
            raise ValueError(f"artifact schema ID drift: {artifact}")
        authorization_artifact = artifact in {"candidate_authorization", "installed_authorization"}
        expected_top = model["authorization_document"]["top_level_keys"] if authorization_artifact else ["schema", "bindings", "payload"]
        if schema.get("top_level_keys") != expected_top or schema.get("payload_key_census") != model["artifact_payload_key_census"][artifact]:
            raise ValueError(f"artifact key census: {artifact}")
        expected_identity_names = sorted(set().union(*expected_bindings[artifact].values()) if expected_bindings[artifact] else set())
        if authorization_artifact and set(expected_identity_names) != _authorization_identities(model):
            raise ValueError(f"authorization document contains non-document lifecycle bindings: {artifact}")
        expected_paths = {
            name: _authorization_json_path(model, name) if authorization_artifact and name in _authorization_identities(model) else f"$.bindings.{name}"
            for name in expected_identity_names
        }
        expected_required = {
            name: sorted(outcome for outcome, values in expected_bindings[artifact].items() if name in values)
            for name in expected_identity_names
        }
        expected_payload_equality = {
            key: expected_paths[key]
            for key in model["artifact_payload_key_census"][artifact]
            if key in expected_paths
        }
        if schema.get("identity_paths") != expected_paths or schema.get("identity_required_outcomes") != expected_required or schema.get("payload_binding_equality") != expected_payload_equality:
            raise ValueError(f"artifact binding channel drift: {artifact}")
        if authorization_artifact and any(path.startswith("$.bindings") for path in schema["identity_paths"].values()):
            raise ValueError(f"authorization document has unrealizable bindings channel: {artifact}")
    if interface != _expected_interface(model, schemas):
        raise ValueError("authorization interface semantic drift")
    accounting = documents["accounting"]
    if accounting.get("authorization_mint_execution_delta") != 0 or accounting.get("consumer_grant_is_start") is not False or accounting.get("reservation_is_execution") is not False:
        raise ValueError("reservation/execution semantic drift")
    paths = documents["paths"]
    for outcome_name, obligation in expected["outcomes"]["variants"].items():
        final = paths["legal_trace_final_path_states"][outcome_name]
        for artifact in obligation["required_artifacts"]:
            if final.get(f"ARTIFACT::{artifact}") != "MUST_EXIST_REGULAR_FILE":
                raise ValueError(f"required artifact path unsatisfied: {outcome_name}/{artifact}")
        for artifact in obligation["forbidden_artifacts"]:
            if final.get(f"ARTIFACT::{artifact}") != "MUST_NOT_EXIST":
                raise ValueError(f"forbidden artifact path present: {outcome_name}/{artifact}")
    return {"identity_count": len(names), "required_cell_count": required_cells, "artifact_count": len(artifact_names)}


def assert_mutations_rejected(model: dict[str, Any], docs: dict[str, dict[str, Any]]) -> int:
    mutations: list[tuple[dict[str, Any], dict[str, dict[str, Any]]]] = []
    def add_model(mutator):
        bad = copy.deepcopy(model); mutator(bad); mutations.append((bad, copy.deepcopy(docs)))
    def add_doc(name, mutator):
        bad_docs = copy.deepcopy(docs); mutator(bad_docs[name]); mutations.append((copy.deepcopy(model), bad_docs))

    add_model(lambda m: m["ledger_targets"]["CORRECTED_ORACLE_SECONDARY_EVENT_LEDGER"].update(delta=0))
    add_model(lambda m: m["ledger_targets"]["HISTORICAL_REAL_PAYLOAD_LEDGER"].update(after=176, delta=1))
    add_model(lambda m: m["ledger_targets"]["CORRECTED_ORACLE_PACKAGE_ATTEMPT_LEDGER"].update(advance_transition="T06_INSTALL_AUTHORIZATION"))
    add_model(lambda m: m["terminal_branches"]["SECONDARY_PRE_START_FAILURE"].update(secondary_started=True))
    add_model(lambda m: m["terminal_branches"]["COMPLETE_SUCCESS"].update(primary_started=False))
    add_model(lambda m: m["absent_path_validation"].update(resolve_absent_leaf_strictly=True))
    add_model(lambda m: m["root_relation_matrix"]["pairs"].pop())
    add_model(lambda m: m["serialization"].update(sort_keys=False))
    add_model(lambda m: m["authorization_document"]["top_level_keys"].remove("package_attempt_id"))
    add_model(lambda m: m["authority_activation"].update(candidate_is_authority=True))
    add_model(lambda m: m["supersession"].update(v1_v2_v3_live_mint="ACTIVE"))
    add_model(lambda m: m["accounting_semantics"].update(authorization_mint_execution_delta=1, consumer_grant_is_start=True, reservation_is_execution=True))
    add_model(lambda m: m["artifact_payload_key_census"].__setitem__("package_terminal", ["result"]))
    add_model(lambda m: m["artifact_path_descriptors"].pop("package_terminal"))
    add_model(lambda m: m["artifact_removals"].clear())
    add_model(lambda m: m["measurement_authority"].update(required_entries=[]))
    add_model(lambda m: m["transitions"][1].update(preconditions=[]))
    add_model(lambda m: m["transitions"][1].update(prohibited_side_effects=[]))
    add_model(lambda m: m["states"].append("P1_EXECUTION_AUTHORIZED"))
    add_model(lambda m: m["authorization_document"]["pinned_values"].update(prompt_token=9704))
    add_model(lambda m: m["root_relation_matrix"]["pairs"][0].update(relation="EQUAL"))
    add_model(lambda m: m["serialization"]["readback_sequence"].remove("DESCRIPTOR_RELATIVE_REOPEN"))
    add_model(lambda m: m["measurement_authority"].update(measurement_head_semantics="UNDEFINED"))
    add_model(lambda m: m["start_transition_by_actor"].update(secondary="T12_START_PRIMARY"))
    add_model(lambda m: m["artifact_file_validation"].update(post_create_validation="NONE"))
    add_model(lambda m: m["artifact_self_sha_identities"].update(candidate_authorization="installed_authorization_sha256"))
    add_doc("accounting", lambda d: d["variant_deltas"]["TERMINAL::SECONDARY_PRE_START_FAILURE"].update(CORRECTED_ORACLE_SECONDARY_EVENT_LEDGER=1))
    add_doc("outcomes", lambda d: d["variants"]["TERMINAL::SECONDARY_PRE_START_FAILURE"]["forbidden_artifacts"].remove("secondary_terminal"))
    add_doc("outcomes", lambda d: d["variants"]["TERMINAL::PRIMARY_POST_START_FAILURE"]["required_artifacts"].remove("primary_receipt"))
    add_doc("schemas", lambda d: d["artifacts"]["package_terminal"].update(artifact_schema_id="forged/1.0.0"))
    add_doc("interface", lambda d: d["top_level_keys"].append("unknown"))
    add_doc("interface", lambda d: d["pinned_values"].update(p1_authority="PERMITTED"))
    add_doc("interface", lambda d: d.update(expected_token_field_permitted=True, candidate_authority=True, target_mode_requires_installation_receipt=False))
    add_doc("interface", lambda d: d["validation_side_effect_limits"].update(checkpoint_opens=999, checkpoint_reads=999, state_roots_created=7))
    add_doc("interface", lambda d: d.update(live_authority_requirements=[]))
    add_doc("matrix", lambda d: d["rows"][0]["cells"].pop(next(iter(d["rows"][0]["cells"]))))
    add_doc("serialization", lambda d: d.update(artifact_sha256_domain="UNDEFINED"))
    add_doc("registry", lambda d: d["identities"][0].update(derivation_permitted=True, mismatch_behavior="IGNORE"))
    add_doc("schemas", lambda d: d["artifacts"]["package_terminal"].update(payload_key_census=["result"]))
    add_doc("schemas", lambda d: d["artifacts"]["candidate_authorization"]["identity_paths"].update(candidate_sha256="$.bindings.candidate_sha256"))
    add_doc("outcomes", lambda d: d["variants"]["FAILED::T07_BANK_INSTALL_RECEIPT"]["required_artifacts"].remove("installed_authorization"))
    add_doc("outcomes", lambda d: d["variants"]["TERMINAL::SECONDARY_PRE_START_FAILURE"]["required_artifacts"].append("secondary_terminal"))
    add_doc("paths", lambda d: d["artifact_file_validation"].update(create_mode="REPLACE_ALLOWED"))
    add_doc("registry", lambda d: d["grammars"]["LIVE_ID"].update(pattern=".*"))
    add_doc("registry", lambda d: d["identities"][0].pop("authority_source"))
    bad_docs = copy.deepcopy(docs)
    removed = "primary_terminal_sha256"
    bad_docs["registry"]["identities"] = [item for item in bad_docs["registry"]["identities"] if item["name"] != removed]
    bad_docs["registry"]["identity_count"] -= 1
    bad_docs["matrix"]["rows"] = [row for row in bad_docs["matrix"]["rows"] if row["identity"] != removed]
    bad_docs["matrix"]["row_count"] -= 1
    for schema in bad_docs["schemas"]["artifacts"].values():
        schema["identity_paths"].pop(removed, None)
        schema["identity_required_outcomes"].pop(removed, None)
    mutations.append((copy.deepcopy(model), bad_docs))

    rejected = 0
    for bad_model, bad_docs in mutations:
        try:
            validate_bundle(bad_model, bad_docs)
        except (ValueError, KeyError):
            rejected += 1
        else:
            raise ValueError("semantic mutation unexpectedly accepted")
    return rejected


def validate() -> dict[str, Any]:
    model = load_json(MODEL_PATH)
    _exact_canonical(MODEL_PATH, model)
    documents = {name: load_json(path) for name, path in PATHS.items()}
    for name, path in PATHS.items():
        _exact_canonical(path, documents[name])
    counts = validate_bundle(model, documents)
    mutations = assert_mutations_rejected(model, documents)
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-lifecycle-semantic-authority-validation/5.0.0",
        "result": "PASS",
        "semantic_model_sha256": canonical_sha256(model),
        **counts,
        "semantic_mutations_rejected": mutations,
        "event_accounting_loaded_and_pinned": True,
        "conditional_outcome_validation": "PASS",
        "path_satisfiability": "PASS",
        "readback_sha_domain": "EXACT_CANONICAL_COMPLETE_ARTIFACT_BYTES",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate()
    encoded = canonical_json_bytes(result)
    if args.output:
        args.output.write_bytes(encoded)
    print(encoded.decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
