#!/usr/bin/env python3
"""Generate the F017 corrected-oracle lifecycle-v4 design authorities."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
COLUMNS = [
    "operator_approval", "candidate_authorization", "primary_candidate_validation_report",
    "secondary_candidate_validation_report", "installed_authorization", "installation_receipt",
    "coordinator_handshake", "package_claim", "package_durable_start", "package_ledger_entry",
    "primary_durable_start", "primary_ledger_entry", "primary_receipt", "primary_terminal",
    "secondary_durable_start", "secondary_ledger_entry", "secondary_receipt", "secondary_terminal",
    "package_receipt", "package_terminal", "final_declaration",
]
GRAMMARS = {
    "LIVE_ID": {"description": "ASCII live identifier", "pattern": r"^[A-Z0-9](?:[A-Z0-9-]{0,126}[A-Z0-9])?$", "forbidden_markers": ["INERT", "FIXTURE", "TEST", "SYNTHETIC"]},
    "SHA256": {"description": "lowercase hexadecimal SHA-256", "pattern": r"^[0-9a-f]{64}$"},
    "ABSOLUTE_PATH": {"description": "canonical absolute non-symlink path without NUL or Unicode separators"},
    "SCHEMA_ID": {"description": "exact committed schema identifier"},
    "ROLE": {"description": "closed consumer role", "enum": ["INDEPENDENT_CPU_REFERENCE", "INDEPENDENT_ACCELERATED_CROSS_CHECK"]},
    "BRANCH": {"description": "exact authoritative branch"},
    "GIT_COMMIT": {"description": "lowercase 40-character Git object ID", "pattern": r"^[0-9a-f]{40}$"},
    "INTEGER": {"description": "JSON integer; boolean prohibited", "minimum": 0},
    "ACCOUNTING_CLASS": {"description": "closed durable-start accounting class", "enum": ["PACKAGE_ATTEMPT_DURABLE_START", "PRIMARY_CONSUMER_DURABLE_START", "SECONDARY_CONSUMER_DURABLE_START"]},
}
IDENTITIES: dict[str, tuple[str, str, str, list[str]]] = {}

def add(name: str, kind: str, source: str, first: str, columns: list[str]) -> None:
    assert name not in IDENTITIES and first in COLUMNS and first in columns
    IDENTITIES[name] = (kind, source, first, columns)

ALL = COLUMNS
FROM = lambda column: COLUMNS[COLUMNS.index(column):]

# All non-content identities are literal operator-approved values. Artifact IDs
# are never derived from paths or filenames.
for name, kind, source in [
    ("operator_approval_id", "LIVE_ID", "operator"),
    ("authorization_id", "LIVE_ID", "operator"),
    ("package_attempt_id", "LIVE_ID", "operator"),
    ("primary_event_id", "LIVE_ID", "operator"),
    ("secondary_event_id", "LIVE_ID", "operator"),
    ("primary_candidate_validation_report_id", "LIVE_ID", "operator"),
    ("secondary_candidate_validation_report_id", "LIVE_ID", "operator"),
    ("installation_receipt_id", "LIVE_ID", "operator"),
    ("coordinator_handshake_id", "LIVE_ID", "operator"),
    ("package_claim_id", "LIVE_ID", "operator"),
    ("package_durable_start_id", "LIVE_ID", "operator"),
    ("package_ledger_entry_id", "LIVE_ID", "operator"),
    ("package_receipt_id", "LIVE_ID", "operator"),
    ("package_terminal_id", "LIVE_ID", "operator"),
    ("primary_durable_start_id", "LIVE_ID", "operator"),
    ("primary_ledger_entry_id", "LIVE_ID", "operator"),
    ("primary_receipt_id", "LIVE_ID", "operator"),
    ("primary_terminal_id", "LIVE_ID", "operator"),
    ("secondary_durable_start_id", "LIVE_ID", "operator"),
    ("secondary_ledger_entry_id", "LIVE_ID", "operator"),
    ("secondary_receipt_id", "LIVE_ID", "operator"),
    ("secondary_terminal_id", "LIVE_ID", "operator"),
    ("final_declaration_id", "LIVE_ID", "operator"),
    ("authorization_schema", "SCHEMA_ID", "operator"),
    ("authorization_interface_sha256", "SHA256", "committed interface v4"),
    ("branch", "BRANCH", "operator"),
    ("implementation_head", "GIT_COMMIT", "operator"),
    ("contract_sha256", "SHA256", "committed scientific-access contract v4"),
    ("coordinator_sha256", "SHA256", "committed coordinator v4"),
    ("authorizer_sha256", "SHA256", "committed authorizer v4"),
    ("numerical_methodology_sha256", "SHA256", "frozen numerical contract"),
    ("checkpoint_manifest_sha256", "SHA256", "committed checkpoint manifest"),
    ("checkpoint_catalog_sha256", "SHA256", "committed checkpoint catalog"),
    ("checkpoint_set_sha256", "SHA256", "committed checkpoint set"),
    ("historical_ledger_sha256", "SHA256", "historical branch authority"),
    ("historical_ledger_terminal", "INTEGER", "historical branch authority"),
    ("historical_ledger_delta", "INTEGER", "event-accounting v4"),
    ("candidate_nonce", "LIVE_ID", "operator"),
    ("canonical_install_path", "ABSOLUTE_PATH", "operator"),
    ("checkpoint_root", "ABSOLUTE_PATH", "operator"),
    ("package_state_root", "ABSOLUTE_PATH", "operator"),
    ("package_output_root", "ABSOLUTE_PATH", "operator"),
    ("primary_state_root", "ABSOLUTE_PATH", "operator"),
    ("primary_output_root", "ABSOLUTE_PATH", "operator"),
    ("secondary_state_root", "ABSOLUTE_PATH", "operator"),
    ("secondary_output_root", "ABSOLUTE_PATH", "operator"),
    ("primary_consumer_role", "ROLE", "interface v4"),
    ("secondary_consumer_role", "ROLE", "interface v4"),
    ("primary_producer_sha256", "SHA256", "committed primary wrapper v4"),
    ("primary_capability_sha256", "SHA256", "committed primary capability v4"),
    ("primary_decoder_sha256", "SHA256", "frozen primary decoder"),
    ("secondary_producer_sha256", "SHA256", "committed secondary wrapper v4"),
    ("secondary_capability_sha256", "SHA256", "committed secondary capability v4"),
    ("secondary_decoder_sha256", "SHA256", "frozen secondary decoder dispatch"),
    ("memory_preflight_sha256", "SHA256", "fresh reviewed memory preflight"),
    ("package_accounting_class", "ACCOUNTING_CLASS", "event-accounting v4"),
    ("primary_accounting_class", "ACCOUNTING_CLASS", "event-accounting v4"),
    ("secondary_accounting_class", "ACCOUNTING_CLASS", "event-accounting v4"),
]:
    add(name, kind, source, "operator_approval", ALL)

for name, first, source in [
    ("operator_approval_sha256", "candidate_authorization", "banked operator approval bytes"),
    ("candidate_sha256", "primary_candidate_validation_report", "authorizer candidate bytes"),
    ("primary_candidate_validation_report_sha256", "secondary_candidate_validation_report", "primary validation-report readback"),
    ("secondary_candidate_validation_report_sha256", "installation_receipt", "secondary validation-report readback"),
    ("installed_authorization_sha256", "installation_receipt", "descriptor-relative installed authorization readback"),
    ("installation_receipt_sha256", "coordinator_handshake", "installation-receipt readback"),
    ("coordinator_handshake_sha256", "package_claim", "coordinator-handshake readback"),
    ("package_claim_sha256", "package_durable_start", "package-claim readback"),
    ("package_durable_start_sha256", "package_ledger_entry", "package durable-start readback"),
    ("package_ledger_entry_sha256", "primary_durable_start", "package-ledger readback"),
    ("primary_durable_start_sha256", "primary_ledger_entry", "primary durable-start readback"),
    ("primary_ledger_entry_sha256", "primary_receipt", "primary-ledger readback"),
    ("primary_receipt_sha256", "primary_terminal", "primary-receipt readback"),
    ("primary_terminal_sha256", "secondary_durable_start", "primary-terminal readback"),
    ("secondary_durable_start_sha256", "secondary_ledger_entry", "secondary durable-start readback"),
    ("secondary_ledger_entry_sha256", "secondary_receipt", "secondary-ledger readback"),
    ("secondary_receipt_sha256", "secondary_terminal", "secondary-receipt readback"),
    ("secondary_terminal_sha256", "package_receipt", "secondary-terminal readback"),
    ("package_receipt_sha256", "package_terminal", "package-receipt readback"),
    ("package_terminal_sha256", "final_declaration", "package-terminal readback"),
]:
    add(name, "SHA256", source, first, FROM(first))

def equality_rule(kind: str) -> str:
    if kind == "ABSOLUTE_PATH": return "EXACT_CANONICAL_PATH_AND_DECLARED_PAIRWISE_RELATION"
    if kind == "INTEGER": return "EXACT_JSON_INTEGER_AND_DECLARED_MONOTONIC_RULE"
    return "EXACT_TYPED_EQUALITY_TO_FIRST_INTRODUCTION"

def uniqueness_scope(name: str, kind: str) -> str:
    return {"LIVE_ID": "GLOBAL_REPOSITORY_AND_MACHINE_EVENT_STATE", "ABSOLUTE_PATH": "DECLARED_ROOT_RELATION_TABLE", "SHA256": "CONTENT_ADDRESS", "INTEGER": "DECLARED_LEDGER_OR_LIFECYCLE_SCOPE"}.get(kind, f"EXACT_{name.upper()}_AUTHORITY_SCOPE")

def generic_path(name: str) -> str: return f"$.bindings.{name}"

def candidate_path(name: str) -> str:
    direct = {
        "authorization_schema": "$.schema", "authorization_id": "$.authorization_id", "operator_approval_id": "$.operator_approval_id",
        "operator_approval_sha256": "$.operator_approval_sha256", "package_attempt_id": "$.package_attempt_id",
        "authorization_interface_sha256": "$.authorization_interface_sha256", "branch": "$.branch", "implementation_head": "$.implementation_head",
        "contract_sha256": "$.contract_sha256", "coordinator_sha256": "$.coordinator_sha256", "authorizer_sha256": "$.authorizer_sha256",
        "numerical_methodology_sha256": "$.numerical_methodology_sha256", "checkpoint_manifest_sha256": "$.checkpoint_manifest_sha256",
        "checkpoint_catalog_sha256": "$.checkpoint_catalog_sha256", "checkpoint_set_sha256": "$.checkpoint_set_sha256",
        "historical_ledger_sha256": "$.historical_ledger_sha256", "historical_ledger_terminal": "$.historical_ledger_terminal",
        "historical_ledger_delta": "$.historical_ledger_delta", "candidate_nonce": "$.candidate_nonce", "canonical_install_path": "$.canonical_install_path",
        "checkpoint_root": "$.checkpoint_root", "memory_preflight_sha256": "$.memory_preflight_sha256",
        "package_state_root": "$.package.state_root", "package_output_root": "$.package.output_root", "package_accounting_class": "$.package.accounting_class",
        "primary_event_id": "$.primary.event_id", "primary_consumer_role": "$.primary.role", "primary_producer_sha256": "$.primary.producer_sha256",
        "primary_capability_sha256": "$.primary.capability_sha256", "primary_decoder_sha256": "$.primary.decoder_sha256",
        "primary_state_root": "$.primary.state_root", "primary_output_root": "$.primary.output_root", "primary_accounting_class": "$.primary.accounting_class",
        "secondary_event_id": "$.secondary.event_id", "secondary_consumer_role": "$.secondary.role", "secondary_producer_sha256": "$.secondary.producer_sha256",
        "secondary_capability_sha256": "$.secondary.capability_sha256", "secondary_decoder_sha256": "$.secondary.decoder_sha256",
        "secondary_state_root": "$.secondary.state_root", "secondary_output_root": "$.secondary.output_root", "secondary_accounting_class": "$.secondary.accounting_class",
    }
    return direct.get(name, f"$.lifecycle_plan.{name}")

def path_for(column: str, name: str) -> str:
    return candidate_path(name) if column in ("candidate_authorization", "installed_authorization") else generic_path(name)

def artifact_schemas() -> dict:
    result = {}
    candidate_top = ["schema", "state", "live", "authority_scope", "branch", "implementation_head", "authorization_id", "operator_approval_id",
        "operator_approval_sha256", "package_attempt_id", "authorization_interface_sha256", "authorizer_sha256", "coordinator_sha256", "contract_sha256",
        "numerical_methodology_sha256", "checkpoint_manifest_sha256", "checkpoint_catalog_sha256", "checkpoint_set_sha256", "checkpoint_root",
        "historical_ledger_sha256", "historical_ledger_terminal", "historical_ledger_delta", "memory_preflight_sha256", "candidate_nonce",
        "canonical_install_path", "package", "primary", "secondary", "lifecycle_plan", "event_accounting", "shards"]
    for column in COLUMNS:
        required = [name for name, (_kind, _source, _first, cols) in IDENTITIES.items() if column in cols]
        result[column] = {
            "top_level_keys": candidate_top if column in ("candidate_authorization", "installed_authorization") else ["schema", "artifact_id", "bindings", "payload"],
            "identity_paths": {name: path_for(column, name) for name in required},
            "identity_types": {name: IDENTITIES[name][0] for name in required},
            "required_identity_count": len(required), "unknown_keys": "REJECT", "missing_keys": "REJECT",
        }
    return result

def registry() -> dict:
    rows = []
    for name, (kind, source, first, downstream) in IDENTITIES.items():
        rows.append({"name": name, "type": kind, "grammar": GRAMMARS[kind], "uniqueness_scope": uniqueness_scope(name, kind),
            "authority_source": source, "first_introduction": first, "downstream_artifacts": downstream,
            "artifact_json_paths": {column: path_for(column, name) for column in downstream},
            "validators": ["validate_f017_corrected_oracle_lifecycle_v4.py", "v4_artifact_schema_validator"],
            "derivation_permitted": False, "derivation_rule": None, "repetition_permitted": kind != "LIVE_ID",
            "equality_rule": equality_rule(kind), "mismatch_behavior": "FAIL_CLOSED_BEFORE_NEXT_LIFECYCLE_TRANSITION",
            "terminal_failure_class": "LIFECYCLE_IDENTITY_BINDING_FAILURE"})
    return {"schema": "pulsarmlx.f017.corrected-oracle-lifecycle-identity-registry/1.1.0", "identity_count": len(rows), "grammars": GRAMMARS, "identities": rows}

def matrix() -> dict:
    rows = []
    for name, (kind, source, _first, downstream) in IDENTITIES.items():
        cells = {}
        for column in COLUMNS:
            required = column in downstream
            cells[column] = {"required": required, "json_path": path_for(column, name) if required else None, "type": kind if required else None,
                "source": source if required else None, "equality_rule": equality_rule(kind) if required else None,
                "validator": "validate_f017_corrected_oracle_lifecycle_v4.py" if required else None,
                "failure_classification": "LIFECYCLE_IDENTITY_BINDING_COVERAGE_FAILURE" if required else None}
        rows.append({"identity": name, "cells": cells})
    return {"schema": "pulsarmlx.f017.corrected-oracle-lifecycle-binding-matrix/1.1.0", "status": "LIFECYCLE_BINDING_COVERAGE: COMPLETE", "columns": COLUMNS, "row_count": len(rows), "rows": rows}

def interface() -> dict:
    schemas = artifact_schemas()
    lifecycle_ids = [name for name, (kind, _s, first, _c) in IDENTITIES.items() if kind == "LIVE_ID" and first == "operator_approval" and name not in {"operator_approval_id", "authorization_id", "package_attempt_id", "primary_event_id", "secondary_event_id", "candidate_nonce"}]
    grant = ["event_id", "role", "producer_path", "producer_sha256", "capability_sha256", "decoder_path", "decoder_sha256", "state_root", "output_root", "attempts", "retries", "resume", "accounting_class", "durable_start_schema", "receipt_schema", "terminal_schema"]
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-authorization-consumer-interface/4.0.0",
        "authorization_schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/4.0.0",
        "supersedes_schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/3.0.0",
        "version_reason": "COMPLETE_TYPED_LIFECYCLE_IDENTITY_AND_INSTALLATION_RECEIPT_BINDING",
        "top_level_keys": schemas["candidate_authorization"]["top_level_keys"],
        "package_grant_keys": ["state_root", "output_root", "attempts", "retries", "resume", "accounting_class", "durable_start_schema", "receipt_schema", "terminal_schema"],
        "primary_grant_keys": grant, "secondary_grant_keys": grant, "lifecycle_plan_keys": lifecycle_ids,
        "accounting_keys": ["authorization_mint_delta", "package_attempt_delta_on_durable_start", "primary_event_delta_on_primary_durable_start", "secondary_event_delta_on_secondary_durable_start", "unstarted_consumer_delta", "reservation_is_not_execution", "event_counts_derived_from_durable_start_receipts"],
        "shard_keys": ["access_role", "filename", "sha256", "size_bytes"], "artifact_schemas": schemas,
        "identity_uniqueness": {"pairwise_distinct_live_ids": True, "all_live_ids_previously_unused": True, "scan_authorities": ["repository_history", "canonical_event_state_root", "historical_event_roots"]},
        "root_relations": {"allowed_ancestry": [["package_state_root", "primary_state_root"], ["package_state_root", "secondary_state_root"], ["package_output_root", "primary_output_root"], ["package_output_root", "secondary_output_root"]],
            "required_disjoint": [["checkpoint_root", "package_state_root"], ["checkpoint_root", "package_output_root"], ["canonical_install_path", "package_state_root"], ["canonical_install_path", "package_output_root"], ["primary_state_root", "secondary_state_root"], ["primary_output_root", "secondary_output_root"]],
            "all_other_pairs": "DISJOINT_OR_EXACTLY_DECLARED_ANCESTRY"},
        "live_identity_grammar": GRAMMARS["LIVE_ID"],
        "strict_types": {"per_field": "artifact_schemas.*.identity_types", "integers": "type(value) is int; booleans rejected", "unknown_keys": "REJECT", "missing_keys": "REJECT", "null_required_fields": "REJECT"},
        "validation_boundary": {"checkpoint_opens": 0, "checkpoint_hash_reads": 0, "checkpoint_mmaps": 0, "tensor_reads": 0, "state_roots_created": 0, "numerical_operations": 0},
        "lifecycle": {"attempts": 1, "retries": 0, "resume": False, "both_candidate_reports_before_install": True, "both_installed_reports_before_state_or_checkpoint_access": True},
        "historical_master": {"terminal": 175, "delta": 0},
        "authority_semantics": {"candidate_is_live_authority": False, "installed_authority_requires": ["canonical_install_path", "candidate_install_byte_identity", "installation_receipt", "operator_approval_binding", "unused_roots", "both_consumer_candidate_validation_reports"], "target_consumers_require_installation_receipt": True, "candidate_validation_permits_noncanonical_private_path": True},
        "package_attempt_canonical_source": "$.package_attempt_id", "package_grant_references_canonical_top_level_id": True,
        "shared_parser_scope": "STRICT_NON_NUMERICAL_ROLE_INDEPENDENT_PARSE; CONSUMERS ADD DISJOINT ROLE_ASSERTION_SETS",
        "coverage_registry": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-identity-registry-v1.json",
        "coverage_matrix": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-binding-matrix-v1.json"}

def accounting() -> dict:
    return {"schema": "pulsarmlx.f017.corrected-oracle-event-accounting/4.0.0", "authorization_mint_delta": 0,
        "package_attempt_delta_on_durable_start": 1, "primary_event_delta_on_primary_durable_start": 1,
        "secondary_event_delta_on_secondary_durable_start": 1, "unstarted_consumer_delta": 0,
        "reservation_is_not_execution": True, "event_counts_derived_from_durable_start_receipts": True,
        "required_ledger_bindings": ["authorization_id", "package_attempt_id", "event_id", "durable_start_sha256", "event_class", "sequence", "prior_entry", "result"],
        "historical_master_terminal": 175, "historical_master_delta": 0,
        "event_02_disposition": "V2_PACKAGE_RESERVATION_OF_TWO_AUTHORIZED_CONSUMER_SLOTS; NO HISTORICAL REINTERPRETATION",
        "event_03_disposition": "NO_CANDIDATE_NO_AUTHORIZATION_NO_PACKAGE_NO_LEDGER_DELTA"}

def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def main() -> int:
    dump(CONTRACTS / "f017-corrected-oracle-lifecycle-identity-registry-v1.json", registry())
    dump(CONTRACTS / "f017-corrected-oracle-lifecycle-binding-matrix-v1.json", matrix())
    dump(CONTRACTS / "f017-corrected-oracle-authorization-consumer-interface-v4.json", interface())
    dump(CONTRACTS / "f017-corrected-oracle-event-accounting-v4.json", accounting())
    return 0

if __name__ == "__main__": raise SystemExit(main())
