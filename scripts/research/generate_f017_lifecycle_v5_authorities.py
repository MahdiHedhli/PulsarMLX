#!/usr/bin/env python3
"""Generate all large lifecycle-v5 authority views from the semantic model."""
from __future__ import annotations

import argparse
from collections import defaultdict
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
OUTPUTS = {
    "outcomes": CONTRACTS / "f017-corrected-oracle-outcome-obligations-v5.json",
    "accounting": CONTRACTS / "f017-corrected-oracle-event-accounting-v5.json",
    "paths": CONTRACTS / "f017-corrected-oracle-path-timing-v1.json",
    "serialization": CONTRACTS / "f017-canonical-json-bytes-v1.json",
    "interface": CONTRACTS / "f017-corrected-oracle-authorization-consumer-interface-v5.json",
    "registry": CONTRACTS / "f017-corrected-oracle-lifecycle-identity-registry-v5.json",
    "matrix": CONTRACTS / "f017-corrected-oracle-lifecycle-binding-matrix-v5.json",
    "schemas": CONTRACTS / "f017-corrected-oracle-artifact-schemas-v5.json",
}


def identity_type(name: str) -> str:
    if name.endswith("_sha256"):
        return "SHA256"
    if name.endswith("_id"):
        return "LIVE_ID"
    if name.endswith("_root") or name.endswith("_path"):
        return "PATH_DESCRIPTOR"
    if name.endswith("_head"):
        return "GIT_COMMIT"
    if name.endswith("_terminal") or name.endswith("_delta") or name.endswith("_count") or name.endswith("_ns") or name in {"prompt_token", "position", "top_n"}:
        return "INTEGER"
    if name.endswith("_role"):
        return "ROLE"
    return "EXACT_SCALAR"


def authorization_identities(model: dict[str, Any]) -> set[str]:
    doc = model["authorization_document"]
    result = {
        key for key in doc["top_level_keys"]
        if key not in {"schema", "package", "primary", "secondary", "context", "limits", "state", "live"}
    }
    for key in doc["package_keys"]:
        result.add(f"package_{key}")
    for consumer in ("primary", "secondary"):
        for key in doc["consumer_keys"]:
            result.add(f"{consumer}_{key}")
    result.update(doc["context_keys"])
    result.update(doc["limits_keys"])
    result.update({"authorization_schema", "authorization_state", "authorization_live"})
    return result


def authorization_json_path(model: dict[str, Any], name: str) -> str:
    document = model["authorization_document"]
    aliases = {
        "authorization_schema": "$.schema",
        "authorization_state": "$.state",
        "authorization_live": "$.live",
    }
    if name in aliases:
        return aliases[name]
    if name in document["top_level_keys"]:
        return f"$.{name}"
    for prefix, keys in (("package", document["package_keys"]), ("primary", document["consumer_keys"]), ("secondary", document["consumer_keys"])):
        marker = f"{prefix}_"
        if name.startswith(marker) and name[len(marker):] in keys:
            return f"$.{prefix}.{name[len(marker):]}"
    if name in document["context_keys"]:
        return f"$.context.{name}"
    if name in document["limits_keys"]:
        return f"$.limits.{name}"
    raise ValueError(f"authorization identity has no JSON path: {name}")


def derive_binding_views(model: dict[str, Any], obligations: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    transitions = {item["id"]: item for item in model["transitions"]}
    base = authorization_identities(model)
    artifact_outcome_bindings: dict[str, dict[str, set[str]]] = defaultdict(dict)
    artifact_outcome_paths: dict[str, dict[str, str]] = defaultdict(dict)
    all_identities = set(base)

    authorization_artifacts = {"candidate_authorization", "installed_authorization"}
    for outcome_name, outcome in obligations["variants"].items():
        visible = set(base)
        for transition_id in outcome["trace"]:
            transition = transitions[transition_id]
            introduced = set(transition["identities_introduced"])
            all_identities.update(introduced)
            for artifact in transition["artifacts_created"]:
                # An artifact cannot contain the SHA of its own bytes.  That SHA
                # becomes available only after durable readback and is carried by
                # the next artifact or an external measurement manifest.
                own_sha = model["artifact_self_sha_identities"][artifact]
                bindings = base if artifact in authorization_artifacts else (visible | introduced) - {own_sha}
                artifact_outcome_bindings[artifact][outcome_name] = bindings
                artifact_outcome_paths[artifact][outcome_name] = f"$.bindings"
            visible.update(introduced)

    # All transition-introduced identities remain part of the registry even when
    # their only path is a parameterized evidence-banking failure family.
    for transition in model["transitions"]:
        all_identities.update(transition["identities_introduced"])

    grammar = {
        "LIVE_ID": {"pattern": "^[A-Z0-9](?:[A-Z0-9-]{0,126}[A-Z0-9])?$", "forbidden_markers": ["INERT", "FIXTURE", "TEST", "SYNTHETIC"]},
        "SHA256": {"pattern": "^[0-9a-f]{64}$"},
        "PATH_DESCRIPTOR": {"semantics": "PHASE_AWARE_PATH_DESCRIPTOR_NOT_GENERIC_STRICT_RESOLUTION"},
        "GIT_COMMIT": {"pattern": "^[0-9a-f]{40}$"},
        "INTEGER": {"minimum": 0, "boolean_prohibited": True},
        "ROLE": {"enum": ["INDEPENDENT_CPU_REFERENCE", "INDEPENDENT_ACCELERATED_CROSS_CHECK"]},
        "EXACT_SCALAR": {"semantics": "EXACT_JSON_TYPE_AND_VALUE"},
    }
    identities = []
    for name in sorted(all_identities):
        kind = identity_type(name)
        consumers = {
            artifact: sorted(outcome for outcome, values in outcomes.items() if name in values)
            for artifact, outcomes in artifact_outcome_bindings.items()
            if any(name in values for values in outcomes.values())
        }
        identities.append({
            "name": name,
            "type": kind,
            "grammar": grammar[kind],
            "authority_source": "AUTHORIZATION_DOCUMENT" if name in base else "SEMANTIC_TRANSITION_READBACK",
            "derivation_permitted": False,
            "mismatch_behavior": "FAIL_CLOSED_BEFORE_NEXT_TRANSITION",
            "bound_artifact_outcomes": consumers,
        })

    registry = {
        "schema": "pulsarmlx.f017.corrected-oracle-lifecycle-identity-registry/5.0.0",
        "semantic_model_sha256": canonical_sha256(model),
        "grammars": grammar,
        "identity_count": len(identities),
        "identities": identities,
        "status": "GENERATED_VIEW_NOT_PRIMARY_AUTHORITY",
    }
    artifact_classes = sorted(model["artifact_classes"])
    rows = []
    required_cells = 0
    for identity in identities:
        cells = {}
        name = identity["name"]
        for artifact in artifact_classes:
            outcomes = sorted(
                outcome for outcome, bindings in artifact_outcome_bindings.get(artifact, {}).items()
                if name in bindings
            )
            if outcomes:
                required_cells += 1
            json_path = None
            if outcomes:
                json_path = authorization_json_path(model, name) if artifact in {"candidate_authorization", "installed_authorization"} and name in base else f"$.bindings.{name}"
            cells[artifact] = {
                "required_outcomes": outcomes,
                "json_path": json_path,
                "type": identity["type"] if outcomes else None,
                "source": identity["authority_source"] if outcomes else None,
                "equality_rule": "EXACT_TYPED_EQUALITY_TO_FIRST_INTRODUCTION" if outcomes else None,
                "validator": "validate_f017_lifecycle_semantic_authority_v5.py" if outcomes else None,
                "failure_classification": "LIFECYCLE_BINDING_MISMATCH" if outcomes else None,
            }
        rows.append({"identity": name, "cells": cells})
    matrix = {
        "schema": "pulsarmlx.f017.corrected-oracle-lifecycle-binding-matrix/5.0.0",
        "semantic_model_sha256": canonical_sha256(model),
        "columns": artifact_classes,
        "row_count": len(rows),
        "required_cell_count": required_cells,
        "rows": rows,
        "status": "LIFECYCLE_BINDING_COVERAGE: COMPLETE",
        "authority_status": "GENERATED_VIEW_NOT_PRIMARY_AUTHORITY",
    }
    schemas = {}
    for artifact, meta in model["artifact_classes"].items():
        outcomes = artifact_outcome_bindings.get(artifact, {})
        identity_union = sorted(set().union(*outcomes.values()) if outcomes else set())
        authorization_artifact = artifact in authorization_artifacts
        identity_paths = {
            name: authorization_json_path(model, name) if authorization_artifact and name in base else f"$.bindings.{name}"
            for name in identity_union
        }
        payload_equality = {
            key: identity_paths[key]
            for key in model["artifact_payload_key_census"][artifact]
            if key in identity_paths
        }
        schemas[artifact] = {
            "artifact_schema_id": meta["schema"],
            "top_level_keys": model["authorization_document"]["top_level_keys"] if authorization_artifact else ["schema", "bindings", "payload"],
            "payload_key_census": model["artifact_payload_key_census"][artifact],
            "payload_binding_equality": payload_equality,
            "identity_paths": identity_paths,
            "identity_required_outcomes": {
                name: sorted(outcome for outcome, values in outcomes.items() if name in values)
                for name in identity_union
            },
            "writer": meta["writer"],
        }
    schema_view = {
        "schema": "pulsarmlx.f017.corrected-oracle-artifact-schemas/5.0.0",
        "semantic_model_sha256": canonical_sha256(model),
        "artifacts": schemas,
        "status": "GENERATED_VIEW_NOT_PRIMARY_AUTHORITY",
    }
    return registry, matrix, schema_view


def derive_interface(model: dict[str, Any], schemas: dict[str, Any]) -> dict[str, Any]:
    document = model["authorization_document"]
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-authorization-consumer-interface/5.0.0",
        "authorization_schema": model["authorization_schema"],
        "semantic_model_path": str(MODEL_PATH.relative_to(ROOT)),
        "semantic_model_sha256": canonical_sha256(model),
        "top_level_keys": document["top_level_keys"],
        "package_keys": document["package_keys"],
        "consumer_keys": document["consumer_keys"],
        "context_keys": document["context_keys"],
        "limits_keys": document["limits_keys"],
        "pinned_values": document["pinned_values"],
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


def build() -> dict[str, dict[str, Any]]:
    model = load_json(MODEL_PATH)
    validation = validate_model(model)
    outcomes = derive_outcome_obligations(model)
    accounting = derive_accounting(model)
    paths = derive_path_timing(model)
    serialization = derive_serialization(model)
    registry, matrix, schemas = derive_binding_views(model, outcomes)
    interface = derive_interface(model, schemas)
    return {"outcomes": outcomes, "accounting": accounting, "paths": paths, "serialization": serialization, "interface": interface, "registry": registry, "matrix": matrix, "schemas": schemas, "validation": validation}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    model = load_json(MODEL_PATH)
    canonical_model = canonical_json_bytes(model)
    if args.check:
        if MODEL_PATH.read_bytes() != canonical_model:
            raise SystemExit("semantic model is not stored as F017_CANONICAL_JSON_BYTES_V1")
    else:
        MODEL_PATH.write_bytes(canonical_model)
    documents = build()
    mismatches = []
    for name, path in OUTPUTS.items():
        encoded = canonical_json_bytes(documents[name])
        if args.check:
            if not path.exists() or path.read_bytes() != encoded:
                mismatches.append(str(path.relative_to(ROOT)))
        else:
            path.write_bytes(encoded)
    if mismatches:
        raise SystemExit("generated authority drift: " + ", ".join(mismatches))
    print(canonical_json_bytes({"result": "PASS", "generated": {name: canonical_sha256(documents[name]) for name in OUTPUTS}}).decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
