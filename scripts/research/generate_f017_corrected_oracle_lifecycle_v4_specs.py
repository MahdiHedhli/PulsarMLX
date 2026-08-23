#!/usr/bin/env python3
"""Generate the F017 corrected-oracle lifecycle v4 authority specifications."""
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

ALL = COLUMNS
AFTER_APPROVAL = COLUMNS[1:]
AFTER_INSTALL = COLUMNS[5:]
PACKAGE_FLOW = COLUMNS[7:10] + COLUMNS[18:]
PRIMARY_FLOW = COLUMNS[10:14] + COLUMNS[18:]
SECONDARY_FLOW = COLUMNS[14:18] + COLUMNS[18:]

IDENTITIES = {
    "operator_approval_id": ("LIVE_ID", "operator", "operator_approval", ALL, False, False),
    "operator_approval_sha256": ("SHA256", "banked approval bytes", "candidate_authorization", AFTER_APPROVAL, True, True),
    "authorization_id": ("LIVE_ID", "operator", "operator_approval", ALL, False, False),
    "authorization_schema": ("SCHEMA_ID", "interface v4", "candidate_authorization", AFTER_APPROVAL, False, True),
    "authorization_interface_sha256": ("SHA256", "committed interface v4", "operator_approval", ALL, False, True),
    "candidate_sha256": ("SHA256", "authorizer candidate bytes", "primary_candidate_validation_report", COLUMNS[2:], True, True),
    "installed_authorization_sha256": ("SHA256", "descriptor-relative installed bytes", "installation_receipt", AFTER_INSTALL, True, True),
    "installation_receipt_sha256": ("SHA256", "banked installation receipt", "coordinator_handshake", COLUMNS[6:], True, True),
    "package_attempt_id": ("LIVE_ID", "operator", "operator_approval", ALL, False, False),
    "package_state_root": ("ABSOLUTE_PATH", "operator", "operator_approval", COLUMNS[:10] + COLUMNS[18:], False, True),
    "package_output_root": ("ABSOLUTE_PATH", "operator", "operator_approval", COLUMNS[:10] + COLUMNS[18:], False, True),
    "package_claim_sha256": ("SHA256", "package claim readback", "package_durable_start", COLUMNS[8:10] + COLUMNS[18:], True, True),
    "package_durable_start_sha256": ("SHA256", "package durable start readback", "package_ledger_entry", COLUMNS[9:] , True, True),
    "package_ledger_entry_id": ("LIVE_ID", "operator-approved derivation rule", "operator_approval", COLUMNS[:2] + COLUMNS[7:10] + COLUMNS[18:], True, False),
    "package_ledger_entry_sha256": ("SHA256", "package ledger readback", "package_receipt", COLUMNS[18:], True, True),
    "package_receipt_id": ("LIVE_ID", "operator-approved derivation rule", "operator_approval", COLUMNS[:2] + COLUMNS[18:], True, False),
    "package_receipt_sha256": ("SHA256", "package receipt readback", "package_terminal", COLUMNS[19:], True, True),
    "package_terminal_id": ("LIVE_ID", "operator-approved derivation rule", "operator_approval", COLUMNS[:2] + COLUMNS[19:], True, False),
    "package_terminal_sha256": ("SHA256", "package terminal readback", "final_declaration", ["final_declaration"], True, True),
    "primary_event_id": ("LIVE_ID", "operator", "operator_approval", COLUMNS[:14] + COLUMNS[18:], False, False),
    "primary_consumer_role": ("ROLE", "interface v4", "operator_approval", COLUMNS[:14] + COLUMNS[18:], False, True),
    "primary_producer_sha256": ("SHA256", "committed primary wrapper", "operator_approval", COLUMNS[:14] + COLUMNS[18:], False, True),
    "primary_capability_sha256": ("SHA256", "committed primary capability", "operator_approval", COLUMNS[:14] + COLUMNS[18:], False, True),
    "primary_state_root": ("ABSOLUTE_PATH", "operator", "operator_approval", COLUMNS[:14] + COLUMNS[18:], False, True),
    "primary_output_root": ("ABSOLUTE_PATH", "operator", "operator_approval", COLUMNS[:14] + COLUMNS[18:], False, True),
    "primary_durable_start_sha256": ("SHA256", "primary durable start readback", "primary_ledger_entry", COLUMNS[11:14] + COLUMNS[18:], True, True),
    "primary_ledger_entry_id": ("LIVE_ID", "operator-approved derivation rule", "operator_approval", COLUMNS[:2] + COLUMNS[10:14] + COLUMNS[18:], True, False),
    "primary_ledger_entry_sha256": ("SHA256", "primary ledger readback", "primary_receipt", COLUMNS[12:14] + COLUMNS[18:], True, True),
    "primary_receipt_id": ("LIVE_ID", "operator-approved derivation rule", "operator_approval", COLUMNS[:2] + COLUMNS[12:14] + COLUMNS[18:], True, False),
    "primary_receipt_sha256": ("SHA256", "primary receipt readback", "primary_terminal", COLUMNS[13:] , True, True),
    "primary_terminal_id": ("LIVE_ID", "operator-approved derivation rule", "operator_approval", COLUMNS[:2] + COLUMNS[13:14] + COLUMNS[18:], True, False),
    "primary_terminal_sha256": ("SHA256", "primary terminal readback", "package_receipt", COLUMNS[18:], True, True),
    "secondary_event_id": ("LIVE_ID", "operator", "operator_approval", COLUMNS[:7] + COLUMNS[14:], False, False),
    "secondary_consumer_role": ("ROLE", "interface v4", "operator_approval", COLUMNS[:7] + COLUMNS[14:], False, True),
    "secondary_producer_sha256": ("SHA256", "committed secondary wrapper", "operator_approval", COLUMNS[:7] + COLUMNS[14:], False, True),
    "secondary_capability_sha256": ("SHA256", "committed secondary capability", "operator_approval", COLUMNS[:7] + COLUMNS[14:], False, True),
    "secondary_state_root": ("ABSOLUTE_PATH", "operator", "operator_approval", COLUMNS[:7] + COLUMNS[14:], False, True),
    "secondary_output_root": ("ABSOLUTE_PATH", "operator", "operator_approval", COLUMNS[:7] + COLUMNS[14:], False, True),
    "secondary_durable_start_sha256": ("SHA256", "secondary durable start readback", "secondary_ledger_entry", COLUMNS[15:], True, True),
    "secondary_ledger_entry_id": ("LIVE_ID", "operator-approved derivation rule", "operator_approval", COLUMNS[:2] + COLUMNS[14:], True, False),
    "secondary_ledger_entry_sha256": ("SHA256", "secondary ledger readback", "secondary_receipt", COLUMNS[16:], True, True),
    "secondary_receipt_id": ("LIVE_ID", "operator-approved derivation rule", "operator_approval", COLUMNS[:2] + COLUMNS[16:], True, False),
    "secondary_receipt_sha256": ("SHA256", "secondary receipt readback", "secondary_terminal", COLUMNS[17:], True, True),
    "secondary_terminal_id": ("LIVE_ID", "operator-approved derivation rule", "operator_approval", COLUMNS[:2] + COLUMNS[17:], True, False),
    "secondary_terminal_sha256": ("SHA256", "secondary terminal readback", "package_receipt", COLUMNS[18:], True, True),
    "branch": ("BRANCH", "committed contract", "operator_approval", ALL, False, True),
    "implementation_head": ("GIT_COMMIT", "committed contract", "operator_approval", ALL, False, True),
    "contract_sha256": ("SHA256", "committed scientific contract", "operator_approval", ALL, False, True),
    "coordinator_sha256": ("SHA256", "committed coordinator", "operator_approval", ALL, False, True),
    "authorizer_sha256": ("SHA256", "committed authorizer", "operator_approval", COLUMNS[:7] + COLUMNS[18:], False, True),
    "numerical_methodology_sha256": ("SHA256", "frozen numerical contract", "operator_approval", ALL, False, True),
    "checkpoint_manifest_sha256": ("SHA256", "committed manifest", "operator_approval", ALL, False, True),
    "catalog_sha256": ("SHA256", "committed catalog", "operator_approval", ALL, False, True),
    "checkpoint_set_sha256": ("SHA256", "committed checkpoint set", "operator_approval", ALL, False, True),
    "historical_ledger_sha256": ("SHA256", "historical branch authority", "operator_approval", ALL, False, True),
    "historical_ledger_terminal": ("INTEGER", "historical branch authority", "operator_approval", ALL, False, True),
    "package_accounting_class": ("ACCOUNTING_CLASS", "event accounting v4", "operator_approval", COLUMNS[:10] + COLUMNS[18:], False, True),
    "primary_accounting_class": ("ACCOUNTING_CLASS", "event accounting v4", "operator_approval", COLUMNS[:14] + COLUMNS[18:], False, True),
    "secondary_accounting_class": ("ACCOUNTING_CLASS", "event accounting v4", "operator_approval", COLUMNS[:7] + COLUMNS[14:], False, True),
}

GRAMMARS = {
    "LIVE_ID": "ASCII ^[A-Z0-9](?:[A-Z0-9-]{0,126}[A-Z0-9])?$; forbidden markers; globally unused in declared authority roots",
    "SHA256": "lowercase hexadecimal SHA-256, exactly 64 characters",
    "ABSOLUTE_PATH": "absolute canonical non-symlink path; no NUL or Unicode separators",
    "SCHEMA_ID": "exact committed schema identifier",
    "ROLE": "closed consumer-role enum",
    "BRANCH": "exact authoritative branch string",
    "GIT_COMMIT": "lowercase hexadecimal commit object ID, 40 characters",
    "INTEGER": "JSON integer, boolean prohibited",
    "ACCOUNTING_CLASS": "closed event-accounting class enum",
}

def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def registry() -> dict:
    rows = []
    for name, (kind, source, first, downstream, derivable, repeatable) in IDENTITIES.items():
        rows.append({
            "name": name, "type": kind, "grammar": GRAMMARS[kind],
            "uniqueness_scope": "GLOBAL_DECLARED_AUTHORITY_ROOTS" if kind == "LIVE_ID" else "CONTENT_OR_SEMANTIC_SCOPE",
            "authority_source": source, "first_introduction": first,
            "downstream_artifacts": downstream, "validators": ["validate_f017_corrected_oracle_lifecycle_v4.py", "artifact_schema_validator"],
            "derivation_permitted": derivable, "repetition_permitted": repeatable,
            "mismatch_behavior": "FAIL_CLOSED_BEFORE_NEXT_LIFECYCLE_TRANSITION",
            "terminal_failure_class": "LIFECYCLE_IDENTITY_BINDING_FAILURE",
        })
    return {"schema": "pulsarmlx.f017.corrected-oracle-lifecycle-identity-registry/1.0.0", "identity_count": len(rows), "identities": rows}

def matrix() -> dict:
    rows = []
    for name, (kind, source, _first, downstream, _derivable, _repeatable) in IDENTITIES.items():
        cells = {}
        for column in COLUMNS:
            required = column in downstream
            cells[column] = {
                "required": required,
                "json_path": f"$.{name}" if required else None,
                "type": kind if required else None,
                "source": source if required else None,
                "equality_rule": "EXACT_TYPED_EQUALITY_TO_FIRST_INTRODUCTION" if required else None,
                "validator": "validate_f017_corrected_oracle_lifecycle_v4.py" if required else None,
                "failure_classification": "LIFECYCLE_BINDING_COVERAGE_FAILURE" if required else None,
            }
        rows.append({"identity": name, "cells": cells})
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-lifecycle-binding-matrix/1.0.0",
        "status": "LIFECYCLE_BINDING_COVERAGE: COMPLETE", "columns": COLUMNS,
        "row_count": len(rows), "rows": rows,
    }

def interface() -> dict:
    top = [
        "schema", "state", "live", "authority_scope", "branch", "implementation_head",
        "authorization_id", "operator_approval_id", "operator_approval_sha256", "package_attempt_id",
        "authorization_interface_sha256", "authorizer_sha256", "coordinator_sha256", "contract_sha256",
        "numerical_methodology_sha256", "checkpoint_manifest_sha256", "checkpoint_catalog_path",
        "checkpoint_catalog_sha256", "checkpoint_set_sha256", "checkpoint_root", "historical_ledger_sha256",
        "historical_ledger_terminal", "historical_ledger_delta", "memory_observer_sha256",
        "memory_parser_contract_sha256", "memory_preflight_sha256", "memory_observed_at_unix_ns",
        "memory_available_bytes", "candidate_nonce", "canonical_install_path", "installation_receipt_schema",
        "geometry_sha256", "synthetic_qualification_sha256", "prompt_token", "position", "top_n", "p1_authority",
        "package", "primary", "secondary", "consumers", "event_accounting", "shards",
    ]
    package = [
        "attempt_id_json_path", "state_root", "output_root", "attempts", "retries", "resume",
        "accounting_class", "durable_start_schema", "receipt_schema", "terminal_schema",
    ]
    consumer = [
        "event_id", "role", "producer_path", "producer_sha256", "capability_sha256", "decoder_path",
        "decoder_sha256", "state_root", "output_root", "attempts", "retries", "resume",
        "accounting_class", "durable_start_schema", "receipt_schema", "terminal_schema",
    ]
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-authorization-consumer-interface/4.0.0",
        "authorization_schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/4.0.0",
        "supersedes_schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/3.0.0",
        "version_reason": "COMPLETE_TYPED_LIFECYCLE_IDENTITY_AND_INSTALLATION_RECEIPT_BINDING",
        "top_level_keys": top, "package_grant_keys": package,
        "primary_grant_keys": consumer, "secondary_grant_keys": consumer,
        "accounting_keys": ["authorization_mint_delta", "package_attempt_delta_on_durable_start", "primary_event_delta_on_durable_start", "secondary_event_delta_on_durable_start", "unstarted_consumer_delta"],
        "shard_keys": ["access_role", "filename", "sha256", "size_bytes"],
        "operator_approval_keys": [
            "schema", "operator_approval_id", "decision", "branch", "contract_sha256", "authorization_id",
            "package_attempt_id", "primary_event_id", "secondary_event_id", "canonical_authorization_path",
            "package_state_root", "package_output_root", "primary_state_root", "primary_output_root",
            "secondary_state_root", "secondary_output_root", "checkpoint_root", "attempts", "retries", "resume",
            "operator_identity", "approved_at_utc", "new_go", "prior_go_reused", "p1_attempt_2",
            "authorization_survives_bound_byte_change",
        ],
        "installation_receipt_keys": [
            "schema", "result", "operator_approval_id", "authorization_id", "package_attempt_id",
            "primary_event_id", "secondary_event_id", "candidate_sha256", "installed_authorization_sha256",
            "primary_validation_report_sha256", "secondary_validation_report_sha256", "operator_approval_sha256",
            "installation_path", "installed_at_unix_ns",
        ],
        "identity_uniqueness": {
            "all_four_live_ids_pairwise_distinct": True, "all_live_ids_previously_unused": True,
            "roots_nonoverlapping_except_package_parent_of_consumer_roots": True,
        },
        "live_identity_grammar": GRAMMARS["LIVE_ID"],
        "forbidden_live_id_markers": ["INERT", "FIXTURE", "TEST", "SYNTHETIC"],
        "strict_types": {"integers": "type(value) is int; booleans rejected", "unknown_keys": "REJECT", "missing_keys": "REJECT", "null_required_fields": "REJECT"},
        "authority_semantics": {
            "candidate_is_live_authority": False,
            "installed_authority_requires": ["canonical installed path", "candidate/install byte identity", "installation receipt", "operator approval binding", "unused roots", "both consumer candidate-validation reports"],
            "target_consumers_require_installation_receipt": True,
            "candidate_validation_permits_noncanonical_private_path": True,
        },
        "package_attempt_canonical_source": "$.package_attempt_id",
        "package_grant_reference": "$.package.attempt_id_json_path == '$.package_attempt_id'",
        "coverage_registry": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-identity-registry-v1.json",
        "coverage_matrix": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-binding-matrix-v1.json",
    }

def main() -> int:
    dump(CONTRACTS / "f017-corrected-oracle-lifecycle-identity-registry-v1.json", registry())
    dump(CONTRACTS / "f017-corrected-oracle-lifecycle-binding-matrix-v1.json", matrix())
    dump(CONTRACTS / "f017-corrected-oracle-authorization-consumer-interface-v4.json", interface())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
