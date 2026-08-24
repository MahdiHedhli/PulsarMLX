#!/usr/bin/env python3
"""Generate the non-authoritative V6 authorization template."""
from __future__ import annotations

from pathlib import Path

from f017_corrected_oracle_authorization_v6 import ROOT, canonical_bytes, sha256_path, strict_bytes

INTERFACE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-authorization-consumer-interface-v6.json"
SCIENTIFIC = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v6.json"
OUTPUT = ROOT / "specs/017-rust-native-inference-runtime/fixtures/f017-corrected-full-checkpoint-oracle-inert-authorization-v6.json"
ZERO = "0" * 64


def _grant(role: str, prefix: str, producer: str, target: str, numerical: str, decoder: str) -> dict:
    return {
        "event_id": f"F017-INERT-{prefix}-EVENT-V6",
        "durable_start_id": f"F017-INERT-{prefix}-START-V6",
        "ledger_entry_id": f"F017-INERT-{prefix}-LEDGER-V6",
        "ledger_index_id": f"F017-INERT-{prefix}-INDEX-V6",
        "receipt_id": f"F017-INERT-{prefix}-RECEIPT-V6",
        "terminal_id": f"F017-INERT-{prefix}-TERMINAL-V6",
        "role": role,
        "producer_path": producer,
        "producer_sha256": sha256_path(ROOT / producer),
        "capability_path": f"specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-{prefix.lower()}-capability-v6.json",
        "capability_sha256": sha256_path(ROOT / f"specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-{prefix.lower()}-capability-v6.json"),
        "target_source_path": target,
        "target_source_sha256": sha256_path(ROOT / target),
        "numerical_path": numerical,
        "numerical_sha256": sha256_path(ROOT / numerical),
        "decoder_path": decoder,
        "decoder_sha256": sha256_path(ROOT / decoder),
        "state_root": f"INERT-NO-{prefix}-STATE-ROOT",
        "output_root": f"INERT-NO-{prefix}-OUTPUT-ROOT",
        "attempts": 1,
        "retries": 0,
        "resume": False,
        "accounting_class": f"CORRECTED_ORACLE_{prefix}_EVENT_LEDGER",
        "receipt_schema": "pulsarmlx.f017.corrected-oracle-consumer-receipt/6.0.0",
        "terminal_schema": "pulsarmlx.f017.corrected-oracle-consumer-terminal/6.0.0",
    }


def generate() -> dict:
    interface = strict_bytes(INTERFACE.read_bytes())
    scientific = strict_bytes(SCIENTIFIC.read_bytes())
    document = {
        "schema": interface["authorization_schema"], "authority_generation": 6,
        "state": "INERT_FIXTURE", "live": False, "authority_scope": "PRODUCTION",
        "authorization_id": "F017-INERT-AUTHORIZATION-V6", "operator_approval_id": "F017-INERT-APPROVAL-V6",
        "operator_approval_sha256": ZERO, "package_attempt_id": "F017-INERT-PACKAGE-ATTEMPT-V6",
        "primary_event_id": "F017-INERT-PRIMARY-EVENT-V6", "secondary_event_id": "F017-INERT-SECONDARY-EVENT-V6",
        "preflight_report_id": "F017-INERT-PREFLIGHT-V6", "primary_candidate_validation_report_id": "F017-INERT-PCV-V6",
        "secondary_candidate_validation_report_id": "F017-INERT-SCV-V6", "installation_receipt_id": "F017-INERT-INSTALL-V6",
        "primary_installed_validation_report_id": "F017-INERT-PIV-V6", "secondary_installed_validation_report_id": "F017-INERT-SIV-V6",
        "coordinator_handshake_id": "F017-INERT-HANDSHAKE-V6", "comparison_receipt_id": "F017-INERT-COMPARISON-RECEIPT-V6",
        "comparison_terminal_id": "F017-INERT-COMPARISON-TERMINAL-V6", "branch": scientific["branch"],
        "implementation_measurement_head": ZERO[:40], "implementation_measurement_manifest_sha256": ZERO,
        "authorization_interface_sha256": sha256_path(INTERFACE), "scientific_access_contract_sha256": sha256_path(SCIENTIFIC),
        "event_accounting_contract_sha256": scientific["bindings"]["accounting"]["sha256"],
        "path_timing_contract_sha256": scientific["bindings"]["path_timing"]["sha256"],
        "canonical_serialization_contract_sha256": scientific["bindings"]["serialization"]["sha256"],
        "lifecycle_semantic_model_sha256": scientific["bindings"]["lifecycle_model"]["sha256"],
        "numerical_contract_sha256": scientific["bindings"]["numerical_contract"]["sha256"],
        "numerical_capability_policy_sha256": "5ca6576781e269c18671b834b5d115494ec95462a17a59045e930eb256ce4d13",
        "numerical_requalification_sha256": "5a0257803d7af03f091c0dfc438be0727dc567b465c82a8dfcdf83f847e80c49",
        "numerical_methodology_sha256": "7c22507f15c79713a0f81dcf14ea3472aafef3cf43c09d388a6c021b3f1069c4",
        "checkpoint_manifest_sha256": "34b65d586c86d24ee10f3a2ed55491fb3a5a6b9ddbaf893bf9e0ab962c96cf8f",
        "checkpoint_catalog_sha256": "135500cc46b65a877027b597bf20e0c7bb613802e5137c48204e7ab6e7a7ff19",
        "checkpoint_set_sha256": scientific["production_checkpoint"]["checkpoint_set_sha256"],
        "historical_ledger_sha256": "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e",
        "historical_ledger_terminal": 175, "historical_ledger_delta": 0, "memory_preflight_sha256": ZERO,
        "memory_observed_at_unix_ns": 0, "memory_sample_max_age_ns": 300000000000,
        "checkpoint_catalog_path": "docs/research/glm52/raw/f016-c01-catalog-0001.json",
        "geometry_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-geometry-v1.json",
        "geometry_sha256": "a9037a42a476092bdc0f870a7e0b6162a1df0abbe5b0663218e82f931676846a",
        "shards": scientific["production_checkpoint"]["shards"], "checkpoint_root": "INERT-NO-CHECKPOINT-ROOT",
        "canonical_install_path": "INERT-NO-INSTALL-PATH",
        "package": {"claim_id": "F017-INERT-PACKAGE-CLAIM-V6", "durable_start_id": "F017-INERT-PACKAGE-START-V6",
                    "ledger_entry_id": "F017-INERT-PACKAGE-LEDGER-V6", "ledger_index_id": "F017-INERT-PACKAGE-INDEX-V6",
                    "receipt_id": "F017-INERT-PACKAGE-RECEIPT-V6", "terminal_id": "F017-INERT-PACKAGE-TERMINAL-V6",
                    "state_root": "INERT-NO-PACKAGE-STATE-ROOT", "output_root": "INERT-NO-PACKAGE-OUTPUT-ROOT",
                    "attempts": 1, "retries": 0, "resume": False, "accounting_class": "CORRECTED_ORACLE_PACKAGE_ATTEMPT_LEDGER",
                    "receipt_schema": "pulsarmlx.f017.corrected-oracle-package-receipt/6.0.0",
                    "terminal_schema": "pulsarmlx.f017.corrected-oracle-package-terminal/6.0.0"},
        "primary": _grant("INDEPENDENT_CPU_REFERENCE", "PRIMARY", "scripts/research/f017_corrected_oracle_primary_v6.py",
                          "scripts/research/f017_corrected_oracle_primary_target_source_v6.py", "scripts/research/f017_corrected_oracle_primary_numerics_v2.py",
                          "scripts/research/f017_oracle_primary_decoders.py"),
        "secondary": _grant("INDEPENDENT_ACCELERATED_CROSS_CHECK", "SECONDARY", "scripts/research/f017_corrected_oracle_secondary_v6.py",
                            "scripts/research/f017_corrected_oracle_secondary_target_source_v6.py", "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py",
                            "scripts/research/qualify_f017_quantization_matrix_v1.py"),
        "context": interface["pinned_context"], "limits": interface["pinned_limits"],
    }
    if set(document) != set(interface["top_level_keys"]):
        raise ValueError("inert authorization census")
    return document


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(canonical_bytes(generate()))
    print(sha256_path(OUTPUT))
