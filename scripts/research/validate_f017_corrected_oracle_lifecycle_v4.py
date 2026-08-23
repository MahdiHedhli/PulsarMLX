#!/usr/bin/env python3
"""Validate lifecycle-v4 registry, binding matrix, interface, and drift resistance."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
EXPECTED_COLUMNS = [
    "operator_approval", "candidate_authorization", "primary_candidate_validation_report",
    "secondary_candidate_validation_report", "installed_authorization", "installation_receipt",
    "coordinator_handshake", "package_claim", "package_durable_start", "package_ledger_entry",
    "primary_durable_start", "primary_ledger_entry", "primary_receipt", "primary_terminal",
    "secondary_durable_start", "secondary_ledger_entry", "secondary_receipt", "secondary_terminal",
    "package_receipt", "package_terminal", "final_declaration",
]
CELL_KEYS = {"required", "json_path", "type", "source", "equality_rule", "validator", "failure_classification"}

def pairs(items):
    result = {}
    for key, value in items:
        if key in result: raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result

def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)

def validate_documents(registry: dict, matrix: dict, interface: dict) -> dict:
    identities = registry.get("identities")
    if not isinstance(identities, list): raise ValueError("identity registry type")
    names = [item.get("name") for item in identities]
    if any(not isinstance(name, str) or not name for name in names) or len(names) != len(set(names)) or registry.get("identity_count") != len(names):
        raise ValueError("identity registry census")
    grammars = registry.get("grammars")
    if not isinstance(grammars, dict) or not grammars: raise ValueError("grammar registry")
    if matrix.get("columns") != EXPECTED_COLUMNS or matrix.get("row_count") != len(matrix.get("rows", [])): raise ValueError("matrix census")
    rows = {row.get("identity"): row for row in matrix["rows"]}
    if set(rows) != set(names) or len(rows) != len(names): raise ValueError("registry/matrix identity mismatch")
    schemas = interface.get("artifact_schemas")
    if not isinstance(schemas, dict) or set(schemas) != set(EXPECTED_COLUMNS): raise ValueError("artifact schema census")
    required_cell_count = 0
    for identity in identities:
        name, kind = identity["name"], identity.get("type")
        if kind not in grammars or identity.get("grammar") != grammars[kind]: raise ValueError(f"identity grammar drift: {name}")
        first, downstream, paths = identity.get("first_introduction"), identity.get("downstream_artifacts"), identity.get("artifact_json_paths")
        if first not in EXPECTED_COLUMNS or not isinstance(downstream, list) or first not in downstream: raise ValueError(f"identity introduction: {name}")
        if len(downstream) != len(set(downstream)) or any(column not in EXPECTED_COLUMNS for column in downstream): raise ValueError(f"identity downstream: {name}")
        if set(paths or {}) != set(downstream): raise ValueError(f"identity paths: {name}")
        if identity.get("derivation_permitted") is not False or identity.get("derivation_rule") is not None: raise ValueError(f"unstated identity derivation: {name}")
        row = rows[name]
        if set(row.get("cells", {})) != set(EXPECTED_COLUMNS): raise ValueError(f"matrix columns: {name}")
        required_columns = []
        for column, cell in row["cells"].items():
            if set(cell) != CELL_KEYS or type(cell["required"]) is not bool: raise ValueError(f"matrix cell census: {name}/{column}")
            details = [cell[key] for key in CELL_KEYS - {"required"}]
            if cell["required"]:
                required_cell_count += 1
                required_columns.append(column)
                if any(not isinstance(value, str) or not value for value in details): raise ValueError(f"unresolved required cell: {name}/{column}")
                schema = schemas[column]
                if cell["json_path"] != paths[column] or schema.get("identity_paths", {}).get(name) != cell["json_path"]: raise ValueError(f"interface path drift: {name}/{column}")
                if cell["type"] != kind or schema.get("identity_types", {}).get(name) != kind: raise ValueError(f"interface type drift: {name}/{column}")
                if cell["equality_rule"] != identity.get("equality_rule"): raise ValueError(f"equality-rule drift: {name}/{column}")
            elif any(value is not None for value in details): raise ValueError(f"unexpected optional details: {name}/{column}")
        if set(required_columns) != set(downstream): raise ValueError(f"registry/matrix propagation drift: {name}")
    for column, schema in schemas.items():
        paths, types = schema.get("identity_paths"), schema.get("identity_types")
        top = schema.get("top_level_keys")
        if not isinstance(top, list) or len(top) != len(set(top)): raise ValueError(f"top-level census: {column}")
        if set(paths or {}) != set(types or {}) or schema.get("required_identity_count") != len(paths): raise ValueError(f"artifact identity census: {column}")
        expected = {name for name, row in rows.items() if row["cells"][column]["required"]}
        if set(paths) != expected: raise ValueError(f"artifact required-set drift: {column}")
        for name, path in paths.items():
            if not isinstance(path, str) or not path.startswith("$."): raise ValueError(f"unresolvable JSON path: {column}/{name}")
            root = path[2:].split(".", 1)[0]
            if root not in top: raise ValueError(f"JSON path outside key census: {column}/{name}")
    if matrix.get("status") != "LIFECYCLE_BINDING_COVERAGE: COMPLETE": raise ValueError("coverage status")
    if interface.get("authorization_schema") != "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/4.0.0": raise ValueError("authorization schema")
    candidate = schemas["candidate_authorization"]
    if candidate["identity_paths"].get("package_attempt_id") != "$.package_attempt_id": raise ValueError("canonical package attempt ID")
    if interface.get("package_attempt_canonical_source") != "$.package_attempt_id" or interface.get("authority_semantics", {}).get("candidate_is_live_authority") is not False: raise ValueError("package/install authority semantics")
    if interface.get("validation_boundary") != {"checkpoint_opens": 0, "checkpoint_hash_reads": 0, "checkpoint_mmaps": 0, "tensor_reads": 0, "state_roots_created": 0, "numerical_operations": 0}: raise ValueError("validation boundary")
    if interface.get("historical_master") != {"terminal": 175, "delta": 0}: raise ValueError("historical ledger")
    return {"identity_count": len(names), "required_cell_count": required_cell_count}

def assert_drift_rejected(registry: dict, matrix: dict, interface: dict) -> int:
    mutations = []
    bad = copy.deepcopy(matrix)
    first = next(cell for row in bad["rows"] for cell in row["cells"].values() if cell["required"])
    first["json_path"] = "$.THIS_FIELD_DOES_NOT_EXIST"
    mutations.append((registry, bad, interface))
    bad = copy.deepcopy(interface)
    bad["artifact_schemas"]["operator_approval"]["top_level_keys"] = ["JUNK_ONLY"]
    mutations.append((registry, matrix, bad))
    bad = copy.deepcopy(registry)
    bad["identities"][0]["downstream_artifacts"] = []
    bad["identities"][0]["artifact_json_paths"] = {}
    mutations.append((bad, matrix, interface))
    bad = copy.deepcopy(registry)
    bad["identities"][0]["type"] = "SHA256"
    mutations.append((bad, matrix, interface))
    rejected = 0
    for documents in mutations:
        try: validate_documents(*documents)
        except ValueError: rejected += 1
        else: raise ValueError("semantic drift mutation unexpectedly passed")
    return rejected

def validate() -> dict:
    registry = load(CONTRACTS / "f017-corrected-oracle-lifecycle-identity-registry-v1.json")
    matrix = load(CONTRACTS / "f017-corrected-oracle-lifecycle-binding-matrix-v1.json")
    interface = load(CONTRACTS / "f017-corrected-oracle-authorization-consumer-interface-v4.json")
    counts = validate_documents(registry, matrix, interface)
    return {"schema": "pulsarmlx.f017.corrected-oracle-lifecycle-coverage-validation/1.1.0", "result": "PASS",
        "status": "LIFECYCLE_BINDING_COVERAGE: COMPLETE", "identity_count": counts["identity_count"],
        "artifact_column_count": len(EXPECTED_COLUMNS), "required_cell_count": counts["required_cell_count"],
        "semantic_drift_mutations_rejected": assert_drift_rejected(registry, matrix, interface)}

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path); args = parser.parse_args()
    result = validate(); encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output: args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end=""); return 0

if __name__ == "__main__": raise SystemExit(main())
