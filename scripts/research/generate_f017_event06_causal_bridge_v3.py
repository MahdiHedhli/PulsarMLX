#!/usr/bin/env python3
"""Derive the liquid Sequence 13 causal bridge requirements and contract.

This is design-only tooling.  It does not import an Event 06 executor, resolve a
checkpoint path, construct live authority, or perform numerical work.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
REQUIREMENTS = CONTRACTS / "f017-corrected-oracle-event06-causal-identity-to-numerical-bridge-requirements-v2.json"
CONTRACT = CONTRACTS / "f017-corrected-oracle-event06-causal-identity-to-numerical-bridge-v3.json"

COMMON = {
    "schema": "str",
    "node_id": "enum",
}
CONTINUITY = {
    "authorization_id": "typed_id",
    "package_attempt_id": "typed_id",
    "event_identity_plan_sha256": "sha256",
    "prompt_repository_commit": "git_object",
    "prompt_repository_path": "repository_path",
    "prompt_sha256": "sha256",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _node(
    node_id: str,
    *,
    stage: str,
    producer: str,
    output_type: str,
    consumer: str,
    input_type: str,
    predecessors: tuple[str, ...],
    fields: dict[str, str],
    side_effects: tuple[str, ...],
    failure: str,
    after_package_start: bool,
    after_identity: bool,
) -> dict[str, object]:
    complete = dict(COMMON)
    complete.update(fields)
    for predecessor in predecessors:
        complete[f"{predecessor.lower()}_sha256"] = "sha256"
    return {
        "node_id": node_id,
        "stage": stage,
        "producer_api": producer,
        "sealed_output_type": output_type,
        "validator_or_consumer_api": consumer,
        "sealed_input_type": input_type,
        "direct_predecessors": list(predecessors),
        "required_fields": list(complete),
        "field_types": complete,
        "allowed_side_effects": list(side_effects),
        "failure_outcome": failure,
        "after_package_start": after_package_start,
        "after_identity": after_identity,
        "caller_mapping_permitted": False,
        "public_exact_type_required": True,
        "output_digest_is_external": True,
    }


def _nodes() -> list[dict[str, object]]:
    pre = False
    post = True
    return [
        _node(
            "RAW_FUTURE_HUMAN_GO", stage="PRE_PACKAGE_PRE_IDENTITY",
            producer="capture_future_human_go_evidence_v4",
            output_type="RawFutureHumanGoEvidenceV4",
            consumer="seal_live_go_envelope_v4", input_type="RawFutureHumanGoEvidenceV4",
            predecessors=(),
            fields={"raw_human_go_sha256": "sha256", "target_machine": "enum", "scope": "enum", "attempts": "non_boolean_integer", "retries": "non_boolean_integer", "resume": "bool", "generation": "enum"},
            side_effects=("BANK_RAW_GO_EVIDENCE",), failure="RAW_GO_REJECTED_NO_AUTHORITY", after_package_start=pre, after_identity=pre,
        ),
        _node(
            "SEALED_LIVE_GO_ENVELOPE", stage="PRE_PACKAGE_PRE_IDENTITY",
            producer="seal_live_go_envelope_v4", output_type="SealedLiveGoEnvelopeV4",
            consumer="produce_prompt_bound_event_identity_plan_v3", input_type="SealedLiveGoEnvelopeV4",
            predecessors=("RAW_FUTURE_HUMAN_GO",),
            fields={"raw_human_go_sha256": "sha256", "authorization_id": "typed_id", "package_attempt_id": "typed_id", "primary_event_id": "typed_id", "secondary_event_id": "typed_id", "prompt_repository_commit": "git_object", "prompt_repository_path": "repository_path", "prompt_sha256": "sha256", "generation": "enum"},
            side_effects=("BANK_SEALED_GO",), failure="LIVE_GO_SEAL_REJECTED_NO_AUTHORITY", after_package_start=pre, after_identity=pre,
        ),
        _node(
            "PROMPT_BOUND_EVENT_IDENTITY_PLAN", stage="PRE_PACKAGE_PRE_IDENTITY",
            producer="produce_prompt_bound_event_identity_plan_v3", output_type="PromptBoundEventIdentityPlanV3",
            consumer="produce_live_operator_approval_v4", input_type="PromptBoundEventIdentityPlanV3",
            predecessors=("SEALED_LIVE_GO_ENVELOPE",),
            fields={"authorization_id": "typed_id", "package_attempt_id": "typed_id", "primary_event_id": "typed_id", "secondary_event_id": "typed_id", "execution_plan_sha256": "sha256", "prompt_repository_commit": "git_object", "prompt_repository_path": "repository_path", "prompt_sha256": "sha256"},
            side_effects=("BANK_IDENTITY_PLAN",), failure="IDENTITY_PLAN_REJECTED_NO_AUTHORITY", after_package_start=pre, after_identity=pre,
        ),
        _node(
            "LIVE_OPERATOR_APPROVAL", stage="PRE_PACKAGE_PRE_IDENTITY",
            producer="produce_live_operator_approval_v4", output_type="LiveOperatorApprovalV4",
            consumer="prepare_production_installation_v4", input_type="LiveOperatorApprovalV4",
            predecessors=("SEALED_LIVE_GO_ENVELOPE", "PROMPT_BOUND_EVENT_IDENTITY_PLAN"),
            fields={**CONTINUITY, "candidate_sha256": "sha256", "execution_plan_sha256": "sha256", "live": "bool"},
            side_effects=("BANK_OPERATOR_APPROVAL",), failure="APPROVAL_REJECTED_NO_INSTALL", after_package_start=pre, after_identity=pre,
        ),
        _node(
            "PREPARED_PRODUCTION_INSTALLATION", stage="PRE_PACKAGE_PRE_IDENTITY",
            producer="prepare_production_installation_v4", output_type="PreparedProductionInstallationV4",
            consumer="produce_future_go_capability_v4", input_type="PreparedProductionInstallationV4",
            predecessors=("LIVE_OPERATOR_APPROVAL", "PROMPT_BOUND_EVENT_IDENTITY_PLAN"),
            fields={**CONTINUITY, "candidate_sha256": "sha256", "installation_receipt_sha256": "sha256", "installed_authority_candidate_sha256": "sha256", "live_authority": "bool"},
            side_effects=("BANK_PREPARED_INSTALLATION",), failure="PREPARATION_REJECTED_NO_INSTALL", after_package_start=pre, after_identity=pre,
        ),
        _node(
            "FUTURE_GO_CAPABILITY", stage="PRE_PACKAGE_PRE_IDENTITY",
            producer="produce_future_go_capability_v4", output_type="FutureGoCapabilityV4",
            consumer="commit_durable_installation_v4", input_type="FutureGoCapabilityV4",
            predecessors=("PREPARED_PRODUCTION_INSTALLATION",),
            fields={"authorization_id": "typed_id", "package_attempt_id": "typed_id", "nonce_sha256": "sha256", "expires_at_unix_ns": "non_boolean_integer", "single_use": "bool"},
            side_effects=("REGISTER_SINGLE_USE_CAPABILITY",), failure="CAPABILITY_REJECTED_NO_INSTALL", after_package_start=pre, after_identity=pre,
        ),
        _node(
            "DURABLE_INSTALLATION_TRANSACTION", stage="PRE_PACKAGE_PRE_IDENTITY",
            producer="commit_durable_installation_v4", output_type="DurableInstallationTransactionV4",
            consumer="validate_installed_v12_authority_v4", input_type="DurableInstallationTransactionV4",
            predecessors=("PREPARED_PRODUCTION_INSTALLATION", "FUTURE_GO_CAPABILITY"),
            fields={"authorization_id": "typed_id", "package_attempt_id": "typed_id", "candidate_sha256": "sha256", "installation_receipt_sha256": "sha256", "installed_authority_sha256": "sha256", "transaction_journal_sha256": "sha256", "capability_consumed": "bool"},
            side_effects=("EXCLUSIVE_INSTALL", "FSYNC_FILES", "FSYNC_DIRECTORY", "CONSUME_CAPABILITY"), failure="DURABLE_INSTALLATION_TERMINAL_FAILURE", after_package_start=pre, after_identity=pre,
        ),
        _node(
            "INSTALLED_V12_AUTHORITY", stage="PRE_PACKAGE_PRE_IDENTITY",
            producer="validate_installed_v12_authority_v4", output_type="InstalledV12AuthorityV4",
            consumer="produce_pre_package_execution_context_v1", input_type="InstalledV12AuthorityV4",
            predecessors=("DURABLE_INSTALLATION_TRANSACTION", "PROMPT_BOUND_EVENT_IDENTITY_PLAN"),
            fields={**CONTINUITY, "installed_authority_sha256": "sha256", "installation_receipt_sha256": "sha256", "execution_plan_sha256": "sha256", "state": "enum"},
            side_effects=("BANK_INSTALLED_AUTHORITY_VALIDATION",), failure="INSTALLED_AUTHORITY_REJECTED_NO_PACKAGE", after_package_start=pre, after_identity=pre,
        ),
        _node(
            "PRE_PACKAGE_EXECUTION_CONTEXT", stage="PRE_PACKAGE_PRE_IDENTITY",
            producer="produce_pre_package_execution_context_v1", output_type="PrePackageExecutionContextV1",
            consumer="start_event06_package_v12", input_type="PrePackageExecutionContextV1",
            predecessors=("INSTALLED_V12_AUTHORITY", "PROMPT_BOUND_EVENT_IDENTITY_PLAN"),
            fields={**CONTINUITY, "installed_authority_sha256": "sha256", "execution_plan_sha256": "sha256", "context_sha256": "sha256", "numerical_contract_sha256": "sha256", "result_authority_sha256": "sha256"},
            side_effects=("BANK_PRE_PACKAGE_CONTEXT",), failure="PRE_PACKAGE_CONTEXT_REJECTED_NO_PACKAGE", after_package_start=pre, after_identity=pre,
        ),
        _node(
            "PACKAGE_DURABLE_START", stage="POST_PACKAGE_START_PRE_IDENTITY",
            producer="start_event06_package_v12", output_type="PackageDurableStartV12",
            consumer="produce_v12_checkpoint_identity_stage", input_type="PackageDurableStartV12",
            predecessors=("PRE_PACKAGE_EXECUTION_CONTEXT", "INSTALLED_V12_AUTHORITY"),
            fields={**CONTINUITY, "installed_authority_sha256": "sha256", "package_claim_sha256": "sha256", "package_start_receipt_sha256": "sha256", "package_delta": "non_boolean_integer"},
            side_effects=("BANK_PACKAGE_CLAIM", "BANK_PACKAGE_START", "INCREMENT_PACKAGE_ACCOUNTING"), failure="PACKAGE_START_TERMINAL_FAILURE", after_package_start=post, after_identity=pre,
        ),
        _node(
            "V12_CHECKPOINT_IDENTITY_STAGE", stage="POST_PACKAGE_START_POST_IDENTITY",
            producer="produce_v12_checkpoint_identity_stage", output_type="V12CheckpointIdentityStage",
            consumer="produce_post_identity_numerical_bridge_v3", input_type="V12CheckpointIdentityStage",
            predecessors=("PACKAGE_DURABLE_START", "PRE_PACKAGE_EXECUTION_CONTEXT"),
            fields={**CONTINUITY, "checkpoint_set_sha256": "sha256", "identity_terminal_sha256": "sha256", "access_census_sha256": "sha256", "descriptor_identity_set_sha256": "sha256", "lease_manifest_sha256": "sha256", "lease_owner_id": "typed_id", "graph_descriptor_count": "non_boolean_integer"},
            side_effects=("OPEN_AND_HASH_SIX_SHARDS", "CLOSE_IDENTITY_ONLY_SHARD", "RETAIN_FIVE_GRAPH_LEASES", "BANK_IDENTITY_TERMINAL"), failure="IDENTITY_TERMINAL_FAILURE_RELEASE_LEASES", after_package_start=post, after_identity=post,
        ),
        _node(
            "POST_IDENTITY_NUMERICAL_BRIDGE", stage="POST_PACKAGE_START_POST_IDENTITY",
            producer="produce_post_identity_numerical_bridge_v3", output_type="PostIdentityNumericalBridgeV3",
            consumer="produce_primary_consumer_terminal_v12", input_type="PostIdentityNumericalBridgeV3",
            predecessors=("PRE_PACKAGE_EXECUTION_CONTEXT", "INSTALLED_V12_AUTHORITY", "V12_CHECKPOINT_IDENTITY_STAGE"),
            fields={**CONTINUITY, "installed_authority_sha256": "sha256", "execution_plan_sha256": "sha256", "checkpoint_set_sha256": "sha256", "identity_terminal_sha256": "sha256", "access_census_sha256": "sha256", "descriptor_identity_set_sha256": "sha256", "lease_manifest_sha256": "sha256", "lease_owner_id": "typed_id"},
            side_effects=("BANK_POST_IDENTITY_BRIDGE",), failure="POST_IDENTITY_BRIDGE_REJECTED_RELEASE_LEASES", after_package_start=post, after_identity=post,
        ),
        _node(
            "PRIMARY_CONSUMER_TERMINAL", stage="POST_PACKAGE_START_POST_IDENTITY",
            producer="produce_primary_consumer_terminal_v12", output_type="PrimaryConsumerTerminalV12",
            consumer="produce_secondary_consumer_terminal_v12", input_type="PrimaryConsumerTerminalV12",
            predecessors=("POST_IDENTITY_NUMERICAL_BRIDGE",),
            fields={**CONTINUITY, "consumer_event_id": "typed_id", "checkpoint_set_sha256": "sha256", "result_bundle_sha256": "sha256", "routing_manifest_sha256": "sha256", "consumer_terminal_sha256": "sha256", "core_execution_count": "non_boolean_integer"},
            side_effects=("ONE_PRIMARY_EXECUTION", "BANK_PRIMARY_RESULT_BUNDLE", "BANK_PRIMARY_TERMINAL"), failure="PRIMARY_TERMINAL_FAILURE_RELEASE_LEASES", after_package_start=post, after_identity=post,
        ),
        _node(
            "SECONDARY_CONSUMER_TERMINAL", stage="POST_PACKAGE_START_POST_IDENTITY",
            producer="produce_secondary_consumer_terminal_v12", output_type="SecondaryConsumerTerminalV12",
            consumer="produce_independent_comparison_terminal_v12", input_type="SecondaryConsumerTerminalV12",
            predecessors=("POST_IDENTITY_NUMERICAL_BRIDGE", "PRIMARY_CONSUMER_TERMINAL"),
            fields={**CONTINUITY, "consumer_event_id": "typed_id", "checkpoint_set_sha256": "sha256", "result_bundle_sha256": "sha256", "routing_manifest_sha256": "sha256", "consumer_terminal_sha256": "sha256", "core_execution_count": "non_boolean_integer"},
            side_effects=("ONE_SECONDARY_EXECUTION", "BANK_SECONDARY_RESULT_BUNDLE", "BANK_SECONDARY_TERMINAL"), failure="SECONDARY_TERMINAL_FAILURE_RELEASE_LEASES", after_package_start=post, after_identity=post,
        ),
        _node(
            "INDEPENDENT_COMPARISON_TERMINAL", stage="POST_PACKAGE_START_POST_IDENTITY",
            producer="produce_independent_comparison_terminal_v12", output_type="IndependentComparisonTerminalV12",
            consumer="produce_descriptor_release_terminal_v12", input_type="IndependentComparisonTerminalV12",
            predecessors=("POST_IDENTITY_NUMERICAL_BRIDGE", "PRIMARY_CONSUMER_TERMINAL", "SECONDARY_CONSUMER_TERMINAL"),
            fields={**CONTINUITY, "checkpoint_set_sha256": "sha256", "primary_result_bundle_sha256": "sha256", "secondary_result_bundle_sha256": "sha256", "comparison_summary_sha256": "sha256", "comparison_terminal_sha256": "sha256", "classification": "enum"},
            side_effects=("BANK_COMPARISON_SUMMARY", "BANK_COMPARISON_TERMINAL"), failure="COMPARISON_TERMINAL_FAILURE_RELEASE_LEASES", after_package_start=post, after_identity=post,
        ),
        _node(
            "DESCRIPTOR_RELEASE_TERMINAL", stage="POST_PACKAGE_START_POST_IDENTITY",
            producer="produce_descriptor_release_terminal_v12", output_type="DescriptorReleaseTerminalV12",
            consumer="produce_accounting_closure_v12", input_type="DescriptorReleaseTerminalV12",
            predecessors=("V12_CHECKPOINT_IDENTITY_STAGE", "INDEPENDENT_COMPARISON_TERMINAL"),
            fields={**CONTINUITY, "checkpoint_set_sha256": "sha256", "lease_manifest_sha256": "sha256", "release_report_sha256": "sha256", "release_terminal_sha256": "sha256", "attempted_closures": "non_boolean_integer", "successful_closures": "non_boolean_integer", "live_leases": "non_boolean_integer"},
            side_effects=("CLOSE_FIVE_GRAPH_DESCRIPTORS", "BANK_RELEASE_TERMINAL"), failure="RELEASE_TERMINAL_FAILURE", after_package_start=post, after_identity=post,
        ),
        _node(
            "ACCOUNTING_CLOSURE", stage="POST_PACKAGE_START_POST_IDENTITY",
            producer="produce_accounting_closure_v12", output_type="CoordinatorAccountingClosureV12",
            consumer="produce_package_terminal_v12", input_type="CoordinatorAccountingClosureV12",
            predecessors=("POST_IDENTITY_NUMERICAL_BRIDGE", "INDEPENDENT_COMPARISON_TERMINAL", "DESCRIPTOR_RELEASE_TERMINAL"),
            fields={**CONTINUITY, "checkpoint_set_sha256": "sha256", "authorization_delta": "non_boolean_integer", "package_delta": "non_boolean_integer", "primary_delta": "non_boolean_integer", "secondary_delta": "non_boolean_integer", "historical_master_ledger": "non_boolean_integer", "accounting_receipt_sha256": "sha256"},
            side_effects=("BANK_COORDINATOR_ACCOUNTING_CLOSURE",), failure="ACCOUNTING_TERMINAL_FAILURE", after_package_start=post, after_identity=post,
        ),
        _node(
            "PACKAGE_TERMINAL", stage="POST_PACKAGE_START_POST_IDENTITY",
            producer="produce_package_terminal_v12", output_type="CoordinatorPackageTerminalV12",
            consumer="validate_package_terminal_closure_v12", input_type="CoordinatorPackageTerminalV12",
            predecessors=("INDEPENDENT_COMPARISON_TERMINAL", "DESCRIPTOR_RELEASE_TERMINAL", "ACCOUNTING_CLOSURE"),
            fields={**CONTINUITY, "checkpoint_set_sha256": "sha256", "primary_consumer_terminal_sha256": "sha256", "secondary_consumer_terminal_sha256": "sha256", "comparison_terminal_sha256": "sha256", "release_terminal_sha256": "sha256", "accounting_closure_sha256": "sha256", "package_receipt_sha256": "sha256", "result": "enum"},
            side_effects=("BANK_PACKAGE_RECEIPT", "BANK_PACKAGE_TERMINAL"), failure="PACKAGE_TERMINAL_FAILURE", after_package_start=post, after_identity=post,
        ),
    ]


def derive_requirements() -> dict[str, object]:
    nodes = _nodes()
    edges = [f"{source}->{node['node_id']}" for node in nodes for source in node["direct_predecessors"]]
    # These are historical design bindings, not selectors for the current live
    # surface.  Pin the accepted bytes instead of silently rebinding the old
    # design when a Sequence 39 tombstone changes a former public module.
    historical = {
        "live_go_contract_v3": (
            "scripts/research/f017_event06_live_go_contract_v3.py",
            "df9777cd0e31adbcf4b0379a2cc3020988481d59bb8f24676ebed49e1e09aa87",
        ),
        "production_installation_v3": (
            "scripts/research/f017_event06_production_installation_v3.py",
            "ef2527b3b80a1e487bc145318f6ffaf8d830fa9d6492af68fc8a9b619d6494e9",
        ),
        "durable_installation_transaction_v1": (
            "scripts/research/f017_event06_durable_installation_transaction_v1.py",
            "ee8add19d81a1da5f15f98ac79836cf0228288f8eb6c087bcc61b768bb587c09",
        ),
        "execution_plan_v1": (
            "scripts/research/f017_event06_execution_plan_v1.py",
            "e6bc9020eb0262bca9ce9bc39b526337f1068da4e77edf854ebfbcf6cc1fd499",
        ),
        "checkpoint_identity_v12": (
            "scripts/research/f017_checkpoint_identity_producer_v12.py",
            "419a8f5395368b3a2066d2c3ef5b19d1f14ef2bf49cc4ca8a19e2031e7880dbe",
        ),
        "primary_numerical_v3": (
            "scripts/research/f017_corrected_oracle_primary_numerics_v3.py",
            "56f4179a58ff9558e143e79af73f9709e731ca74b6536f346b1a8e1b29e3f3a6",
        ),
        "secondary_numerical_v3": (
            "scripts/research/f017_corrected_oracle_secondary_numerics_v3.py",
            "c1b6b95cf2a597453aeecc43bf1d5c6df5b8488a6ac522bd01771af7b4d0e7d3",
        ),
        "result_authority_v11": (
            "scripts/research/f017_result_bundle_authority_v11.py",
            "f1388876fa24d4f93d6cd0732c6648584177b353c2bd1f37f6a02d3b3e948a3a",
        ),
        "comparison_authority_v11": (
            "scripts/research/f017_binary_comparison_authority_v11.py",
            "10235d8482aa66a318d7e97b7d3b9fbf27859a732cf67bf29d9cbcd19596e352",
        ),
    }
    superseded = (
        ("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-identity-to-numerical-bridge-requirements-v1.json", "1e7f3a1269127bf2c40cdd2eae69133f806dd094bc1fb777ad7beff4154aa5fd"),
        ("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-identity-to-numerical-bridge-v2.json", "fdf3485232a763da602bf15afe0514e4b39b012e28d88194aeb207dd1132fb0b"),
        ("docs/architecture/reviews/evidence/f017-event06-v12-sequence12-preobservation-freeze-v1.json", "4e9352a860ad828213a85dbe1b0cb95db05784d3190d9593a0cd9087ef858afe"),
    )
    return {
        "schema": "pulsarmlx.f017.event06-v12-causal-identity-to-numerical-bridge-requirements/2.0.0",
        "authority_posture": "PROSPECTIVE_LIQUID_CANDIDATE",
        "eligible_transition": "BANKED_PINNED_TEMPORALLY_FROZEN_NOT_OPERATIONALLY_RATIFIED_AFTER_DUAL_ACCEPTANCE",
        "generation": "V12",
        "numerical_authority": "V4_UNCHANGED",
        "result_authority": "V11_UNCHANGED",
        "historical_master_ledger": 175,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "historical_public_interfaces": [
            {"role": role, "path": path, "sha256": digest}
            for role, (path, digest) in historical.items()
        ],
        "superseded_future_authority": [
            {"path": path, "sha256": digest, "historical_bytes_preserved": True, "future_selection_permitted": False}
            for path, digest in superseded
        ],
        "canonical_event_identity_plan_fields": ["schema", "authorization_id", "package_attempt_id", "primary_event_id", "secondary_event_id", "execution_plan_sha256", "prompt_repository_commit", "prompt_repository_path", "prompt_sha256"],
        "pre_package_forbidden_fields": ["post_identity_numerical_bridge_sha256", "identity_terminal_sha256", "checkpoint_set_sha256", "access_census_sha256", "descriptor_identity_set_sha256", "lease_manifest_sha256", "lease_owner_id"],
        "post_identity_first_authorized_fields": ["identity_terminal_sha256", "checkpoint_set_sha256", "access_census_sha256", "descriptor_identity_set_sha256", "lease_manifest_sha256", "lease_owner_id"],
        "prohibitions": ["ALIASES", "COERCIONS", "OPTIONAL_AUTHORITY_FIELDS", "UNKNOWN_FIELDS", "SCHEMA_UNIONS", "CALLBACKS", "CALLER_PROVIDED_ADAPTERS", "FUTURE_REFERENCES", "SELF_DIGESTS", "CYCLES", "AMBIGUOUS_OWNERSHIP", "CHECKPOINT_SET_SUBSTITUTION", "PROMPT_SUBSTITUTION", "EVENT_ID_SUBSTITUTION", "ROLE_SUBSTITUTION", "CALLER_CREATED_ACCOUNTING", "CALLER_CREATED_TERMINAL", "PRIVATE_RESEAL", "LEGACY_PROJECTION", "SERIALIZATION_ROUND_TRIP_AUTHORITY"],
        "production_implementation_exists": False,
        "operationally_ratified": False,
        "checkpoint_access_permitted": False,
        "event06_execution_permitted": False,
    }


def derive_contract(requirements: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "pulsarmlx.f017.event06-v12-causal-identity-to-numerical-bridge-contract/3.0.0",
        "requirements_path": REQUIREMENTS.relative_to(ROOT).as_posix(),
        "requirements_sha256": hashlib.sha256(_canonical(requirements)).hexdigest(),
        "authority_posture": requirements["authority_posture"],
        "eligible_transition": requirements["eligible_transition"],
        "generation": requirements["generation"],
        "numerical_authority": requirements["numerical_authority"],
        "result_authority": requirements["result_authority"],
        "historical_master_ledger": requirements["historical_master_ledger"],
        "superseded_future_authority": requirements["superseded_future_authority"],
        "nodes": requirements["nodes"],
        "edges": requirements["edges"],
        "node_count": requirements["node_count"],
        "edge_count": requirements["edge_count"],
        "canonical_event_identity_plan_fields": requirements["canonical_event_identity_plan_fields"],
        "pre_package_forbidden_fields": requirements["pre_package_forbidden_fields"],
        "post_identity_first_authorized_fields": requirements["post_identity_first_authorized_fields"],
        "prohibitions": requirements["prohibitions"],
        "public_construction_api": "construct_design_candidate_v3",
        "public_validation_api": "validate_causal_bridge_candidate_v3",
        "production_implementation_exists": False,
        "operationally_ratified": False,
        "checkpoint_access_permitted": False,
        "event06_execution_permitted": False,
    }


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def candidate_bytes() -> tuple[bytes, bytes]:
    requirements = derive_requirements()
    return _canonical(requirements), _canonical(derive_contract(requirements))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = candidate_bytes()
    outputs = ((REQUIREMENTS, expected[0]), (CONTRACT, expected[1]))
    if args.check:
        if any(not path.exists() or path.read_bytes() != data for path, data in outputs):
            raise SystemExit("causal bridge design outputs are stale")
        return 0
    for path, data in outputs:
        path.write_bytes(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
