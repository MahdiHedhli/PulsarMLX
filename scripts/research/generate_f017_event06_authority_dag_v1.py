#!/usr/bin/env python3
"""Generate the canonical typed authority-DAG edge inventory for Sequence 17."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-authority-dag-v1.json"


ROWS = (
    ("READINESS", "validate_event06_readiness_declaration_v3", "ValidatedEvent06ReadinessV3", "DECISION", "produce_bound_sanitized_human_decision", "PREPARATION"),
    ("DECISION", "produce_bound_sanitized_human_decision", "BoundSanitizedHumanDecisionV2", "COLLAPSED_GO", "seal_bound_collapsed_one_shot_go", "PREPARATION"),
    ("COLLAPSED_GO", "seal_bound_collapsed_one_shot_go", "CollapsedOneShotGoV1", "EXECUTION_PLAN", "derive_production_event_identities", "PREPARATION"),
    ("EXECUTION_PLAN", "validate_execution_plan", "ValidatedExecutionPlan", "APPROVAL", "produce_collapsed_live_approval", "PREPARATION"),
    ("APPROVAL", "produce_collapsed_live_approval", "CollapsedLiveApprovalV2", "PREPARATION", "seal_collapsed_live_preparation", "PREPARATION"),
    ("PREPARATION", "seal_collapsed_live_preparation", "CollapsedLivePreparationV2", "PROMPT_IDENTITY", "produce_collapsed_live_prompt_identity", "PREPARATION"),
    ("PROMPT_IDENTITY", "produce_collapsed_live_prompt_identity", "CollapsedLivePromptIdentityV2", "CANDIDATE_BUNDLE", "produce_checkpoint_bound_candidate_bundle", "CANDIDATE"),
    ("CANDIDATE_BUNDLE", "produce_checkpoint_bound_candidate_bundle", "CheckpointBoundCandidateBundleV2", "PREPARED_INSTALLATION", "prepare_collapsed_production_installation", "INSTALLATION"),
    ("PREPARED_INSTALLATION", "prepare_collapsed_production_installation", "PreparedCollapsedInstallationV2", "INSTALL_CAPABILITY", "produce_qualification_installation_capability", "INSTALLATION"),
    ("INSTALL_CAPABILITY", "produce_qualification_installation_capability", "QualificationInstallationCapabilityV2", "DURABLE_TRANSACTION", "commit_qualification_collapsed_installation", "INSTALLATION"),
    ("DURABLE_TRANSACTION", "commit_qualification_collapsed_installation", "DurableTransactionResult", "INSTALLED_TRIPLE", "validate_collapsed_installed_triple", "INSTALLATION"),
    ("INSTALLED_TRIPLE", "validate_collapsed_installed_triple", "CollapsedInstalledTripleV2", "PACKAGE_GATE", "validate_collapsed_installed_package_gate", "PACKAGE_GATE"),
    ("INSTALLED_AUTHORITY", "validate_collapsed_installed_triple", "ValidatedIdentityAuthority", "IDENTITY_STAGE", "bind_identity_stage", "IDENTITY_INTERPOSE"),
    ("SYNTHETIC_LEASES", "_synthetic_identity_stage", "LeaseSet", "IDENTITY_STAGE", "bind_identity_stage", "IDENTITY_INTERPOSE"),
    ("PROMPT_IDENTITY", "produce_collapsed_live_prompt_identity", "CollapsedLivePromptIdentityV2", "BRIDGE_INPUT", "produce_identity_bridge_input", "BRIDGE"),
    ("INSTALLED_AUTHORITY", "validate_collapsed_installed_triple", "ValidatedIdentityAuthority", "BRIDGE_INPUT", "produce_identity_bridge_input", "BRIDGE"),
    ("EXECUTION_PLAN", "validate_execution_plan", "ValidatedExecutionPlan", "BRIDGE_INPUT", "produce_identity_bridge_input", "BRIDGE"),
    ("BRIDGE_INPUT", "produce_identity_bridge_input", "PromptBoundIdentityBridgeInputV2", "NUMERICAL_BRIDGE", "derive_bridge", "BRIDGE"),
    ("IDENTITY_STAGE", "bind_identity_stage", "ValidatedIdentityStage", "NUMERICAL_BRIDGE", "derive_bridge", "BRIDGE"),
    ("NUMERICAL_BRIDGE", "historical_bridge", "ValidatedNumericalBridge", "PRIMARY_NUMERICAL", "numerical_view", "PRIMARY"),
    ("PRIMARY_LEGACY_VIEW", "numerical_view", "ValidatedConsumerView", "PRIMARY_NUMERICAL", "consumer_view", "PRIMARY"),
    ("NUMERICAL_BRIDGE", "historical_bridge", "ValidatedNumericalBridge", "PRIMARY_RESULT", "result_bundle_view", "PRIMARY"),
    ("PRIMARY_RESULT_LEGACY", "result_bundle_view", "ValidatedConsumerView", "PRIMARY_RESULT", "consumer_view", "PRIMARY"),
    ("PRIMARY_RESULT", "_synthetic_bundle", "dict", "PRIMARY_TERMINAL", "primary_terminal_binding", "PRIMARY"),
    ("PRIMARY_TERMINAL", "primary_terminal_binding", "ValidatedConsumerView", "SECONDARY_NUMERICAL", "numerical_view", "SECONDARY"),
    ("SECONDARY_LEGACY_VIEW", "numerical_view", "ValidatedConsumerView", "SECONDARY_NUMERICAL", "consumer_view", "SECONDARY"),
    ("SECONDARY_NUMERICAL", "result_bundle_view", "ValidatedConsumerView", "SECONDARY_RESULT", "consumer_view", "SECONDARY"),
    ("SECONDARY_RESULT", "build_bundle_binding", "tuple[ValidatedBundleBinding,ValidatedBundleBinding]", "COMPARISON", "comparison_view", "COMPARISON"),
    ("COMPARISON_LEGACY_VIEW", "comparison_view", "ValidatedConsumerView", "COMPARISON", "consumer_view", "COMPARISON"),
    ("COMPARISON", "build_comparison_binding", "ValidatedComparisonBinding", "RELEASE", "release_view", "RELEASE"),
    ("RELEASE", "release", "dict", "RELEASE_BINDING", "build_release_binding", "RELEASE"),
    ("RELEASE_BINDING", "build_release_binding", "ValidatedReleaseBinding", "ACCOUNTING", "accounting_view", "ACCOUNTING"),
    ("ACCOUNTING_LEGACY_VIEW", "accounting_view", "ValidatedConsumerView", "ACCOUNTING", "consumer_view", "ACCOUNTING"),
    ("ACCOUNTING", "build_accounting_binding", "ValidatedAccountingBinding", "PACKAGE_TERMINAL", "package_terminal_view", "TERMINAL"),
    ("PACKAGE_TERMINAL_LEGACY", "package_terminal_view", "ValidatedConsumerView", "PACKAGE_TERMINAL", "consumer_view", "TERMINAL"),
    ("PACKAGE_TERMINAL_VIEW", "consumer_view", "PromptBoundConsumerViewV2", "PACKAGE_TERMINAL", "build_package_terminal", "TERMINAL"),
    ("ACCOUNTING_CLOSURE", "build_accounting_closure", "ValidatedAccountingClosureV2", "PACKAGE_TERMINAL", "build_package_terminal", "TERMINAL"),
)

MODULES = {
    "validate_event06_readiness_declaration_v3": "scripts/research/f017_event06_readiness_authority_v3.py",
    "produce_bound_sanitized_human_decision": "scripts/research/f017_event06_collapsed_live_installation_v2.py",
    "seal_bound_collapsed_one_shot_go": "scripts/research/f017_event06_collapsed_live_installation_v2.py",
    "derive_production_event_identities": "scripts/research/f017_event06_collapsed_live_installation_v2.py",
    "validate_execution_plan": "scripts/research/f017_event06_execution_plan_v1.py",
    "produce_collapsed_live_approval": "scripts/research/f017_event06_collapsed_live_installation_v2.py",
    "seal_collapsed_live_preparation": "scripts/research/f017_event06_collapsed_live_installation_v2.py",
    "produce_collapsed_live_prompt_identity": "scripts/research/f017_event06_collapsed_live_installation_v2.py",
    "produce_checkpoint_bound_candidate_bundle": "scripts/research/f017_event06_collapsed_live_installation_v2.py",
    "prepare_collapsed_production_installation": "scripts/research/f017_event06_collapsed_live_installation_v2.py",
    "produce_qualification_installation_capability": "scripts/research/f017_event06_collapsed_live_installation_v2.py",
    "commit_qualification_collapsed_installation": "scripts/research/f017_event06_collapsed_live_installation_v2.py",
    "validate_collapsed_installed_triple": "scripts/research/f017_event06_collapsed_live_installation_v2.py",
    "validate_collapsed_installed_package_gate": "scripts/research/execute_f017_corrected_oracle_event_v12.py",
    "bind_identity_stage": "scripts/research/f017_event06_numerical_bridge_v1.py",
    "_synthetic_identity_stage": "scripts/research/f017_event06_dag_derived_control_path_v1.py",
    "produce_identity_bridge_input": "scripts/research/f017_event06_numerical_bridge_v2.py",
    "derive_bridge": "scripts/research/f017_event06_numerical_bridge_v2.py",
    "historical_bridge": "scripts/research/f017_event06_numerical_bridge_v2.py",
    "numerical_view": "scripts/research/f017_event06_numerical_bridge_v1.py",
    "consumer_view": "scripts/research/f017_event06_numerical_bridge_v2.py",
    "result_bundle_view": "scripts/research/f017_event06_numerical_bridge_v1.py",
    "_synthetic_bundle": "scripts/research/f017_event06_dag_derived_control_path_v1.py",
    "primary_terminal_binding": "scripts/research/f017_event06_numerical_bridge_v1.py",
    "build_bundle_binding": "scripts/research/f017_event06_numerical_bridge_v1.py",
    "comparison_view": "scripts/research/f017_event06_numerical_bridge_v1.py",
    "build_comparison_binding": "scripts/research/f017_event06_numerical_bridge_v1.py",
    "release_view": "scripts/research/f017_event06_numerical_bridge_v1.py",
    "release": "scripts/research/f017_descriptor_lease_manager_v10.py",
    "build_release_binding": "scripts/research/f017_event06_numerical_bridge_v1.py",
    "accounting_view": "scripts/research/f017_event06_numerical_bridge_v1.py",
    "build_accounting_binding": "scripts/research/f017_event06_numerical_bridge_v1.py",
    "build_accounting_closure": "scripts/research/f017_event06_numerical_bridge_v2.py",
    "package_terminal_view": "scripts/research/f017_event06_numerical_bridge_v1.py",
    "build_package_terminal": "scripts/research/f017_event06_numerical_bridge_v2.py",
}


def build() -> dict[str, object]:
    edges = []
    for number, row in enumerate(ROWS, 1):
        source, producer, output_type, destination, consumer, phase = row
        edges.append({
            "edge_id": f"F017-DAG-{number:03d}",
            "source_node": source,
            "producer_module": MODULES[producer],
            "producer_symbol": producer,
            "output_type_or_schema": output_type,
            "destination_node": destination,
            "consumer_module": MODULES[consumer],
            "consumer_symbol": consumer,
            "accepted_input_type_or_schema": output_type,
            "digest_identity_invariant": "EXACT_PRODUCER_OBJECT_AND_BOUND_DIGEST_CONTINUITY",
            "authority_mode": "QUALIFICATION_ONLY_NO_LIVE_AUTHORITY",
            "lifecycle_phase": phase,
            "side_effect_class": "DISPOSABLE_SYNTHETIC_ONLY",
            "negative_mutation_family": [
                "mapping_or_deserialized_lookalike", "wrong_exact_type",
                "digest_or_identity_substitution", "replay_or_cross_role_reuse",
            ],
        })
    return {
        "schema": "pulsarmlx.f017.event06-v12-authority-dag/1.0.0",
        "generation": "V12",
        "numerical_authority": "V4",
        "result_authority": "V11",
        "edges": edges,
        "edge_count": len(edges),
        "coverage_count_source": "DERIVED_FROM_EDGES_ARRAY",
        "production_trace_module": "scripts/research/f017_event06_dag_derived_control_path_v1.py",
        "allowlisted_nonproduction_exclusions": [
            "synthetic identity receipt creation at irreversible checkpoint boundary",
            "synthetic primary and secondary receipts at real numerical kernels",
        ],
        "live_authority_artifact_classes_added": 0,
        "original_checkpoint_access_permitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raw = (json.dumps(build(), indent=2, sort_keys=True) + "\n").encode()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_bytes() != raw:
            raise SystemExit("generated Event 06 authority DAG is stale")
        return 0
    OUTPUT.write_bytes(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
