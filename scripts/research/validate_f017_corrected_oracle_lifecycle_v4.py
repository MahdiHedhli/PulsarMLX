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
CELL_KEYS = {"required", "json_path", "type", "source", "equality_rule", "validator", "failure_classification", "required_outcomes"}
EXPECTED_BY_TYPE = {
    "ABSOLUTE_PATH": {"canonical_install_path", "checkpoint_root", "package_state_root", "package_output_root", "primary_state_root", "primary_output_root", "secondary_state_root", "secondary_output_root"},
    "ACCOUNTING_CLASS": {"package_accounting_class", "primary_accounting_class", "secondary_accounting_class"},
    "AUTHORITY_SCOPE": {"authority_scope"}, "AUTHORIZATION_STATE": {"authorization_state"},
    "BOOLEAN": {"authorization_live", "package_resume", "primary_resume", "secondary_resume"}, "BRANCH": {"branch"},
    "GIT_COMMIT": {"implementation_head", "authority_head"},
    "INTEGER": {"historical_ledger_terminal", "historical_ledger_delta", "prompt_token", "position", "top_n", "memory_observed_at_unix_ns", "memory_available_bytes", "package_attempts", "package_retries", "primary_attempts", "primary_retries", "secondary_attempts", "secondary_retries", "package_ledger_sequence", "primary_ledger_sequence", "secondary_ledger_sequence"},
    "LEDGER_EVENT_CLASS": {"package_ledger_event_class", "primary_ledger_event_class", "secondary_ledger_event_class"},
    "LEDGER_PREDECESSOR": {"package_ledger_prior_entry", "primary_ledger_prior_entry", "secondary_ledger_prior_entry"},
    "LEDGER_RESULT": {"package_ledger_result", "primary_ledger_result", "secondary_ledger_result"},
    "LIVE_ID": {"operator_approval_id", "authorization_id", "package_attempt_id", "primary_event_id", "secondary_event_id", "primary_candidate_validation_report_id", "secondary_candidate_validation_report_id", "installation_receipt_id", "coordinator_handshake_id", "package_claim_id", "package_durable_start_id", "package_ledger_entry_id", "package_receipt_id", "package_terminal_id", "primary_durable_start_id", "primary_ledger_entry_id", "primary_receipt_id", "primary_terminal_id", "secondary_durable_start_id", "secondary_ledger_entry_id", "secondary_receipt_id", "secondary_terminal_id", "final_declaration_id", "candidate_nonce"},
    "P1_AUTHORITY": {"p1_authority"},
    "REPO_RELATIVE_PATH": {"checkpoint_catalog_path", "primary_producer_path", "primary_decoder_path", "secondary_producer_path", "secondary_decoder_path"},
    "ROLE": {"primary_consumer_role", "secondary_consumer_role"},
    "SCHEMA_ID": {"authorization_schema", "package_durable_start_schema", "package_receipt_schema", "package_terminal_schema", "primary_durable_start_schema", "primary_receipt_schema", "primary_terminal_schema", "secondary_durable_start_schema", "secondary_receipt_schema", "secondary_terminal_schema"},
    "SHA256": {"authorization_interface_sha256", "contract_sha256", "coordinator_sha256", "authorizer_sha256", "numerical_methodology_sha256", "checkpoint_manifest_sha256", "checkpoint_catalog_sha256", "checkpoint_set_sha256", "historical_ledger_sha256", "primary_producer_sha256", "primary_capability_sha256", "primary_decoder_sha256", "secondary_producer_sha256", "secondary_capability_sha256", "secondary_decoder_sha256", "memory_preflight_sha256", "geometry_sha256", "memory_observer_sha256", "memory_parser_contract_sha256", "synthetic_qualification_sha256", "operator_approval_sha256", "candidate_sha256", "primary_candidate_validation_report_sha256", "secondary_candidate_validation_report_sha256", "installed_authorization_sha256", "installation_receipt_sha256", "coordinator_handshake_sha256", "package_claim_sha256", "package_durable_start_sha256", "package_ledger_entry_sha256", "primary_durable_start_sha256", "primary_ledger_entry_sha256", "primary_receipt_sha256", "primary_terminal_sha256", "secondary_durable_start_sha256", "secondary_ledger_entry_sha256", "secondary_receipt_sha256", "secondary_terminal_sha256", "package_receipt_sha256", "package_terminal_sha256"},
    "START_DISPOSITION": {"primary_start_disposition", "secondary_start_disposition"},
}
EXPECTED_COLUMN_COUNTS = {"candidate_authorization": 96, "coordinator_handshake": 101, "final_declaration": 121, "installation_receipt": 100, "installed_authorization": 96, "operator_approval": 95, "package_claim": 102, "package_durable_start": 103, "package_ledger_entry": 108, "package_receipt": 119, "package_terminal": 120, "primary_candidate_validation_report": 97, "primary_durable_start": 109, "primary_ledger_entry": 114, "primary_receipt": 115, "primary_terminal": 116, "secondary_candidate_validation_report": 98, "secondary_durable_start": 117, "secondary_ledger_entry": 122, "secondary_receipt": 123, "secondary_terminal": 124}
EXPECTED_GRAMMAR_FACTS = {
    "live_forbidden": ["INERT", "FIXTURE", "TEST", "SYNTHETIC"],
    "roles": ["INDEPENDENT_CPU_REFERENCE", "INDEPENDENT_ACCELERATED_CROSS_CHECK"],
    "accounting": ["PACKAGE_ATTEMPT_DURABLE_START", "PRIMARY_CONSUMER_DURABLE_START", "SECONDARY_CONSUMER_DURABLE_START"],
    "p1": ["PROHIBITED"],
}
EXPECTED_IDENTITY_COUNT = 129
EXPECTED_REQUIRED_CELLS = 2296

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
    actual_by_type = {}
    for item in identities:
        actual_by_type.setdefault(item.get("type"), set()).add(item.get("name"))
    if actual_by_type != EXPECTED_BY_TYPE or len(names) != EXPECTED_IDENTITY_COUNT:
        raise ValueError("frozen identity census/type drift")
    if grammars.get("LIVE_ID", {}).get("forbidden_markers") != EXPECTED_GRAMMAR_FACTS["live_forbidden"]:
        raise ValueError("live identity grammar drift")
    if grammars.get("ROLE", {}).get("enum") != EXPECTED_GRAMMAR_FACTS["roles"]:
        raise ValueError("role grammar drift")
    if grammars.get("ACCOUNTING_CLASS", {}).get("enum") != EXPECTED_GRAMMAR_FACTS["accounting"]:
        raise ValueError("accounting grammar drift")
    if grammars.get("P1_AUTHORITY", {}).get("enum") != EXPECTED_GRAMMAR_FACTS["p1"]:
        raise ValueError("P1 prohibition grammar drift")
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
        conditional_paths = identity.get("conditional_artifact_json_paths", {})
        if first not in EXPECTED_COLUMNS or not isinstance(downstream, list) or (first not in downstream and first not in conditional_paths): raise ValueError(f"identity introduction: {name}")
        if len(downstream) != len(set(downstream)) or any(column not in EXPECTED_COLUMNS for column in downstream): raise ValueError(f"identity downstream: {name}")
        if set(paths or {}) != set(downstream): raise ValueError(f"identity paths: {name}")
        if identity.get("derivation_permitted") is not False or identity.get("derivation_rule") is not None: raise ValueError(f"unstated identity derivation: {name}")
        row = rows[name]
        if set(row.get("cells", {})) != set(EXPECTED_COLUMNS): raise ValueError(f"matrix columns: {name}")
        required_columns = []
        for column, cell in row["cells"].items():
            if set(cell) != CELL_KEYS or type(cell["required"]) is not bool: raise ValueError(f"matrix cell census: {name}/{column}")
            if not isinstance(cell["required_outcomes"], list): raise ValueError(f"matrix outcome census: {name}/{column}")
            details = [cell[key] for key in CELL_KEYS - {"required", "required_outcomes"}]
            if cell["required"]:
                required_cell_count += 1
                required_columns.append(column)
                if any(not isinstance(value, str) or not value for value in details): raise ValueError(f"unresolved required cell: {name}/{column}")
                schema = schemas[column]
                if cell["json_path"] != paths[column] or schema.get("identity_paths", {}).get(name) != cell["json_path"]: raise ValueError(f"interface path drift: {name}/{column}")
                if cell["type"] != kind or schema.get("identity_types", {}).get(name) != kind: raise ValueError(f"interface type drift: {name}/{column}")
                if cell["equality_rule"] != identity.get("equality_rule"): raise ValueError(f"equality-rule drift: {name}/{column}")
                if cell["required_outcomes"]: raise ValueError(f"always-required cell has outcomes: {name}/{column}")
            elif cell["required_outcomes"]:
                conditional = conditional_paths.get(column, {})
                if conditional.get("json_path") != cell.get("json_path") or conditional.get("required_outcomes") != cell["required_outcomes"]:
                    raise ValueError(f"conditional binding drift: {name}/{column}")
                if any(not isinstance(value, str) or not value for value in details): raise ValueError(f"unresolved conditional cell: {name}/{column}")
            elif any(value is not None for value in details): raise ValueError(f"unexpected optional details: {name}/{column}")
        if set(required_columns) != set(downstream): raise ValueError(f"registry/matrix propagation drift: {name}")
    for column, schema in schemas.items():
        paths, types = schema.get("identity_paths"), schema.get("identity_types")
        conditional_paths, conditional_types = schema.get("conditional_identity_paths"), schema.get("conditional_identity_types")
        top = schema.get("top_level_keys")
        if not isinstance(top, list) or len(top) != len(set(top)): raise ValueError(f"top-level census: {column}")
        if set(paths or {}) != set(types or {}) or schema.get("required_identity_count") != len(paths): raise ValueError(f"artifact identity census: {column}")
        if set(conditional_paths or {}) != set(conditional_types or {}) or set(conditional_paths or {}) != set(schema.get("conditional_identity_outcomes", {})): raise ValueError(f"conditional artifact census: {column}")
        if schema.get("required_identity_count") != EXPECTED_COLUMN_COUNTS[column]: raise ValueError(f"frozen column census drift: {column}")
        expected = {name for name, row in rows.items() if row["cells"][column]["required"]}
        if set(paths) != expected: raise ValueError(f"artifact required-set drift: {column}")
        combined_paths = {**paths, **conditional_paths}
        if len(set(combined_paths.values())) != len(combined_paths): raise ValueError(f"identity path collision: {column}")
        for name, path in combined_paths.items():
            if not isinstance(path, str) or not path.startswith("$."): raise ValueError(f"unresolvable JSON path: {column}/{name}")
            root = path[2:].split(".", 1)[0]
            if root not in top: raise ValueError(f"JSON path outside key census: {column}/{name}")
            parts = path[2:].split(".")
            nested = {"lifecycle_plan": "lifecycle_plan_keys", "package": "package_grant_keys", "primary": "primary_grant_keys", "secondary": "secondary_grant_keys"}
            if len(parts) == 2 and parts[0] in nested and parts[1] not in interface.get(nested[parts[0]], []):
                raise ValueError(f"nested leaf outside key census: {column}/{name}")
        if column not in {"candidate_authorization", "installed_authorization"}:
            if not isinstance(schema.get("artifact_schema_id"), str) or not schema.get("artifact_schema_id"):
                raise ValueError(f"artifact schema identity: {column}")
            if not isinstance(schema.get("payload_keys"), list) or not schema["payload_keys"]:
                raise ValueError(f"payload census: {column}")
    if matrix.get("status") != "LIFECYCLE_BINDING_COVERAGE: COMPLETE": raise ValueError("coverage status")
    if interface.get("authorization_schema") != "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/4.0.0": raise ValueError("authorization schema")
    candidate = schemas["candidate_authorization"]
    if candidate["identity_paths"].get("package_attempt_id") != "$.package_attempt_id": raise ValueError("canonical package attempt ID")
    if interface.get("package_attempt_canonical_source") != "$.package_attempt_id" or interface.get("authority_semantics", {}).get("candidate_is_live_authority") is not False: raise ValueError("package/install authority semantics")
    installed = schemas["installed_authorization"]
    if candidate["top_level_keys"] != installed["top_level_keys"] or candidate["identity_paths"] != installed["identity_paths"] or candidate["required_identity_count"] != installed["required_identity_count"]:
        raise ValueError("candidate/installed byte-identity census")
    if required_cell_count != EXPECTED_REQUIRED_CELLS: raise ValueError("frozen required-cell census drift")
    if interface.get("validation_boundary") != {"checkpoint_opens": 0, "checkpoint_hash_reads": 0, "checkpoint_mmaps": 0, "tensor_reads": 0, "state_roots_created": 0, "numerical_operations": 0}: raise ValueError("validation boundary")
    expected_historical = {"branch": "feat/017-real-checkpoint-runner", "path": "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v2.json", "sha256": "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e", "terminal": 175, "delta": 0}
    if interface.get("historical_master") != expected_historical: raise ValueError("historical ledger")
    pins = interface.get("pinned_values", {})
    expected_pins = {"authorization_schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/4.0.0", "authorization_state": "AUTHORIZED", "authorization_live": True, "authority_scope": "F017_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT", "primary_consumer_role": "INDEPENDENT_CPU_REFERENCE", "secondary_consumer_role": "INDEPENDENT_ACCELERATED_CROSS_CHECK", "package_accounting_class": "PACKAGE_ATTEMPT_DURABLE_START", "primary_accounting_class": "PRIMARY_CONSUMER_DURABLE_START", "secondary_accounting_class": "SECONDARY_CONSUMER_DURABLE_START", "package_attempts": 1, "package_retries": 0, "package_resume": False, "primary_attempts": 1, "primary_retries": 0, "primary_resume": False, "secondary_attempts": 1, "secondary_retries": 0, "secondary_resume": False, "prompt_token": 9703, "position": 0, "top_n": 32, "p1_authority": "PROHIBITED", "historical_ledger_terminal": 175, "historical_ledger_delta": 0}
    if pins != expected_pins: raise ValueError("pinned values drift")
    if interface.get("required_distinct") != [["primary_consumer_role", "secondary_consumer_role"], ["primary_producer_sha256", "secondary_producer_sha256"], ["primary_decoder_sha256", "secondary_decoder_sha256"], ["primary_capability_sha256", "secondary_capability_sha256"], ["primary_event_id", "secondary_event_id"]]:
        raise ValueError("consumer independence drift")
    outcomes = interface.get("terminal_outcomes", {})
    if set(outcomes) != {"SUCCESS", "ABORT_BEFORE_PRIMARY_START", "ABORT_BEFORE_SECONDARY_START", "ABORT_AFTER_SECONDARY_START"}:
        raise ValueError("terminal outcome closure")
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
    bad_r, bad_m, bad_i = copy.deepcopy(registry), copy.deepcopy(matrix), copy.deepcopy(interface)
    for identity in bad_r["identities"]:
        if identity["name"] == "secondary_consumer_role":
            identity["artifact_json_paths"]["candidate_authorization"] = "$.primary.role"
    for row in bad_m["rows"]:
        if row["identity"] == "secondary_consumer_role": row["cells"]["candidate_authorization"]["json_path"] = "$.primary.role"
    bad_i["artifact_schemas"]["candidate_authorization"]["identity_paths"]["secondary_consumer_role"] = "$.primary.role"
    mutations.append((bad_r, bad_m, bad_i))
    bad_r, bad_m, bad_i = copy.deepcopy(registry), copy.deepcopy(matrix), copy.deepcopy(interface)
    bad_r["identities"] = [x for x in bad_r["identities"] if x["name"] != "checkpoint_root"]; bad_r["identity_count"] -= 1
    bad_m["rows"] = [x for x in bad_m["rows"] if x["identity"] != "checkpoint_root"]; bad_m["row_count"] -= 1
    for schema in bad_i["artifact_schemas"].values():
        if "checkpoint_root" in schema["identity_paths"]:
            del schema["identity_paths"]["checkpoint_root"]; del schema["identity_types"]["checkpoint_root"]; schema["required_identity_count"] -= 1
    mutations.append((bad_r, bad_m, bad_i))
    bad = copy.deepcopy(registry); bad["grammars"]["ROLE"]["enum"] = ["INDEPENDENT_CPU_REFERENCE"]; mutations.append((bad, matrix, interface))
    bad = copy.deepcopy(registry); bad["grammars"]["LIVE_ID"]["forbidden_markers"] = []; mutations.append((bad, matrix, interface))
    bad = copy.deepcopy(interface); bad["lifecycle_plan_keys"] = [x for x in bad["lifecycle_plan_keys"] if x != "final_declaration_id"]; mutations.append((registry, matrix, bad))
    bad = copy.deepcopy(interface); bad["artifact_schemas"]["installed_authorization"]["identity_paths"]["candidate_sha256"] = "$.lifecycle_plan.candidate_sha256"; bad["artifact_schemas"]["installed_authorization"]["identity_types"]["candidate_sha256"] = "SHA256"; bad["artifact_schemas"]["installed_authorization"]["required_identity_count"] += 1; mutations.append((registry, matrix, bad))
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
