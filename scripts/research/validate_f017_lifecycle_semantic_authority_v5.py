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


def _exact_canonical(path: Path, value: Any) -> None:
    if path.read_bytes() != canonical_json_bytes(value):
        raise ValueError(f"noncanonical or readback byte drift: {path.relative_to(ROOT)}")


def validate_semantics(model: dict[str, Any]) -> None:
    validate_model(model)
    if model["authorization_schema"] != "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/5.0.0":
        raise ValueError("authorization generation")
    if model["supersession"] != {
        "v1_v2_v3_live_mint": "HISTORICAL_ONLY_REJECT_LIVE_MINT",
        "v1_v2_v3_target_execution": "HISTORICAL_ONLY_REJECT_NEW_EXECUTION",
        "v4_design": "REJECTED_HISTORICAL_DESIGN_ONLY",
        "event_04_requires_generation": 5,
    }:
        raise ValueError("supersession semantics")
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
    identities = registry.get("identities")
    if not isinstance(identities, list) or registry.get("identity_count") != len(identities):
        raise ValueError("identity registry census")
    names = [item.get("name") for item in identities]
    if len(names) != len(set(names)) or "package_attempt_id" not in names:
        raise ValueError("identity registry completeness")
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
            if not isinstance(outcomes, list) or any(outcome not in expected["outcomes"]["outcomes"] for outcome in outcomes):
                raise ValueError(f"matrix outcome: {row['identity']}/{artifact}")
            if outcomes:
                required_cells += 1
                if cell.get("json_path") != f"$.bindings.{row['identity']}" or not all(cell.get(key) for key in ("type", "source", "equality_rule", "validator", "failure_classification")):
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
        if schema.get("top_level_keys") != ["schema", "bindings", "payload"] or not isinstance(schema.get("payload_key_census"), list):
            raise ValueError(f"artifact key census: {artifact}")
        if set(schema.get("identity_paths", {})) != set(schema.get("identity_required_outcomes", {})):
            raise ValueError(f"artifact binding channel drift: {artifact}")
    doc = model["authorization_document"]
    if interface.get("top_level_keys") != doc["top_level_keys"] or interface.get("package_keys") != doc["package_keys"] or interface.get("consumer_keys") != doc["consumer_keys"]:
        raise ValueError("authorization key census drift")
    if interface.get("artifact_schema_authority_sha256") != canonical_sha256(schemas):
        raise ValueError("artifact schema authority pin")
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
    add_model(lambda m: m["terminal_outcomes"]["SECONDARY_PRE_START_FAILURE"].update(secondary_started=True))
    add_model(lambda m: m["terminal_outcomes"]["COMPLETE_SUCCESS"].update(primary_started=False))
    add_model(lambda m: m["absent_path_validation"].update(resolve_absent_leaf_strictly=True))
    add_model(lambda m: m["root_relation_matrix"]["pairs"].pop())
    add_model(lambda m: m["serialization"].update(sort_keys=False))
    add_model(lambda m: m["authorization_document"]["top_level_keys"].remove("package_attempt_id"))
    add_model(lambda m: m["authority_activation"].update(candidate_is_authority=True))
    add_model(lambda m: m["supersession"].update(v1_v2_v3_live_mint="ACTIVE"))
    add_doc("accounting", lambda d: d["outcome_deltas"]["SECONDARY_PRE_START_FAILURE"].update(CORRECTED_ORACLE_SECONDARY_EVENT_LEDGER=1))
    add_doc("outcomes", lambda d: d["outcomes"]["SECONDARY_PRE_START_FAILURE"]["forbidden_artifacts"].remove("secondary_terminal"))
    add_doc("outcomes", lambda d: d["outcomes"]["PRIMARY_POST_START_FAILURE"]["required_artifacts"].remove("primary_receipt"))
    add_doc("schemas", lambda d: d["artifacts"]["package_terminal"].update(artifact_schema_id="forged/1.0.0"))
    add_doc("interface", lambda d: d["top_level_keys"].append("unknown"))
    add_doc("matrix", lambda d: d["rows"][0]["cells"].pop(next(iter(d["rows"][0]["cells"]))))
    add_doc("serialization", lambda d: d.update(artifact_sha256_domain="UNDEFINED"))

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
