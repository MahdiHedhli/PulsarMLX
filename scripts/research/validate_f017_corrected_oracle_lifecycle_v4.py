#!/usr/bin/env python3
"""Validate the F017 lifecycle identity registry, coverage matrix, and v4 interface."""
from __future__ import annotations

import argparse
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

def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result

def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)

def validate() -> dict:
    registry = load(CONTRACTS / "f017-corrected-oracle-lifecycle-identity-registry-v1.json")
    matrix = load(CONTRACTS / "f017-corrected-oracle-lifecycle-binding-matrix-v1.json")
    interface = load(CONTRACTS / "f017-corrected-oracle-authorization-consumer-interface-v4.json")
    identities = registry["identities"]
    names = [item["name"] for item in identities]
    if len(names) != len(set(names)) or registry["identity_count"] != len(names):
        raise ValueError("identity registry census")
    if matrix["columns"] != EXPECTED_COLUMNS or matrix["row_count"] != len(matrix["rows"]):
        raise ValueError("matrix census")
    rows = {row["identity"]: row for row in matrix["rows"]}
    if set(rows) != set(names):
        raise ValueError("registry/matrix identity mismatch")
    required_cell_count = 0
    for name, row in rows.items():
        if set(row["cells"]) != set(EXPECTED_COLUMNS):
            raise ValueError(f"matrix columns: {name}")
        for column, cell in row["cells"].items():
            if set(cell) != {"required", "json_path", "type", "source", "equality_rule", "validator", "failure_classification"}:
                raise ValueError(f"matrix cell census: {name}/{column}")
            if type(cell["required"]) is not bool:
                raise ValueError("required type")
            details = [cell[key] for key in ("json_path", "type", "source", "equality_rule", "validator", "failure_classification")]
            if cell["required"]:
                required_cell_count += 1
                if any(not isinstance(value, str) or not value for value in details):
                    raise ValueError(f"unresolved required cell: {name}/{column}")
            elif any(value is not None for value in details):
                raise ValueError(f"unexpected optional details: {name}/{column}")
    mandatory = {
        "operator_approval_id", "operator_approval_sha256", "authorization_id", "authorization_schema",
        "authorization_interface_sha256", "candidate_sha256", "installed_authorization_sha256",
        "installation_receipt_sha256", "package_attempt_id", "package_state_root", "package_output_root",
        "package_claim_sha256", "package_durable_start_sha256", "package_ledger_entry_id",
        "package_ledger_entry_sha256", "package_receipt_id", "package_receipt_sha256",
        "package_terminal_id", "package_terminal_sha256", "primary_event_id", "primary_consumer_role",
        "primary_producer_sha256", "primary_capability_sha256", "primary_state_root", "primary_output_root",
        "primary_durable_start_sha256", "primary_ledger_entry_id", "primary_ledger_entry_sha256",
        "primary_receipt_id", "primary_receipt_sha256", "primary_terminal_id", "primary_terminal_sha256",
        "secondary_event_id", "secondary_consumer_role", "secondary_producer_sha256", "secondary_capability_sha256",
        "secondary_state_root", "secondary_output_root", "secondary_durable_start_sha256",
        "secondary_ledger_entry_id", "secondary_ledger_entry_sha256", "secondary_receipt_id",
        "secondary_receipt_sha256", "secondary_terminal_id", "secondary_terminal_sha256",
        "branch", "implementation_head", "contract_sha256", "coordinator_sha256", "authorizer_sha256",
        "numerical_methodology_sha256", "checkpoint_manifest_sha256", "catalog_sha256",
        "checkpoint_set_sha256", "historical_ledger_sha256", "historical_ledger_terminal",
        "package_accounting_class", "primary_accounting_class", "secondary_accounting_class",
    }
    if set(names) != mandatory:
        raise ValueError("mandatory lifecycle inventory mismatch")
    if matrix["status"] != "LIFECYCLE_BINDING_COVERAGE: COMPLETE":
        raise ValueError("coverage status")
    if interface["authorization_schema"] != "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/4.0.0":
        raise ValueError("authorization schema")
    if "package_attempt_id" not in interface["top_level_keys"] or len(interface["top_level_keys"]) != len(set(interface["top_level_keys"])):
        raise ValueError("canonical package attempt ID")
    for key in ("package_grant_keys", "primary_grant_keys", "secondary_grant_keys", "accounting_keys", "shard_keys", "operator_approval_keys", "installation_receipt_keys"):
        values = interface[key]
        if not values or len(values) != len(set(values)):
            raise ValueError(f"interface census: {key}")
    if interface["package_attempt_canonical_source"] != "$.package_attempt_id" or interface["authority_semantics"]["candidate_is_live_authority"]:
        raise ValueError("package/install authority semantics")
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-lifecycle-coverage-validation/1.0.0",
        "result": "PASS", "status": "LIFECYCLE_BINDING_COVERAGE: COMPLETE",
        "identity_count": len(names), "artifact_column_count": len(EXPECTED_COLUMNS),
        "required_cell_count": required_cell_count,
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate()
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
