#!/usr/bin/env python3
"""Synthetic-only prompt-bound bridge fixtures; never resolve checkpoint paths."""
from __future__ import annotations

import hashlib
import stat

from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import ValidatedIdentityAuthority
from f017_descriptor_lease_manager_v10 import LeaseRecord, LeaseSet
from f017_event06_execution_plan_v1 import validate_execution_plan
from f017_event06_numerical_bridge_v1 import bind_identity_stage
from f017_event06_numerical_bridge_v2 import produce_identity_bridge_input, derive_bridge
from f017_event06_production_installation_v3 import seal_prompt_bound_event_identity_plan

PROMPT_BYTES = b"SYNTHETIC NON-AUTHORITY SEQUENCE 12 PROMPT\n"
PROMPT_COMMIT = "1" * 40
PROMPT_PATH = "Prompts/F017/SYNTHETIC-NON-AUTHORITY-SEQUENCE-12.md"


def runtime_fixture_values():
    fixed = "a" * 64
    authorization_id = "F017-NONAUTH-BRIDGE-AUTH-12"
    package_attempt_id = "F017-NONAUTH-BRIDGE-PACKAGE-12"
    primary_event_id = "F017-NONAUTH-BRIDGE-PRIMARY-12"
    secondary_event_id = "F017-NONAUTH-BRIDGE-SECONDARY-12"
    shards = [{
        "filename": f"synthetic-shard-{ordinal}.bin",
        "size_bytes": 0 if ordinal == 1 else ordinal,
        "sha256": hashlib.sha256(f"synthetic-shard-{ordinal}".encode()).hexdigest(),
        "role": "IDENTITY_ONLY" if ordinal == 1 else "GRAPH_PAYLOAD",
    } for ordinal in range(1, 7)]
    descriptors = [{
        "device": 1, "inode": ordinal, "mode": stat.S_IFREG | 0o600,
        "size": ordinal, "mtime_ns": ordinal, "ctime_ns": ordinal,
        "shard_ordinal": ordinal, "role": "GRAPH_PAYLOAD",
        "lease_id": f"LEASE-{package_attempt_id}-{ordinal}",
    } for ordinal in range(2, 7)]
    plan_value = {
        "schema": "pulsarmlx.f017.event06-v12-execution-plan/1.0.0",
        "package_attempt_id": package_attempt_id, "primary_event_id": primary_event_id,
        "secondary_event_id": secondary_event_id, "source_head": "2" * 40,
        "source_tree": "3" * 40, "implementation_measurement_sha256": "4" * 64,
        "tensor_catalog_path": "specs/017-rust-native-inference-runtime/contracts/f017-synthetic-descriptor-catalog-v9.json",
        "tensor_catalog_sha256": "5" * 64, "primary_numerical_sha256": "6" * 64,
        "secondary_numerical_sha256": "7" * 64,
        "numerical_contract_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json",
        "numerical_contract_sha256": "8" * 64,
        "result_authority_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-result-authority-v11-v2.json",
        "result_authority_sha256": "9" * 64, "result_bundle_builder_sha256": "a" * 64,
        "comparison_authority_sha256": "b" * 64, "release_authority_sha256": "c" * 64,
        "accounting_authority_sha256": "d" * 64, "primary_target_source_sha256": "e" * 64,
        "secondary_target_source_sha256": "f" * 64, "shards": shards,
        "attempts": 1, "retries": 0, "resume": False,
    }
    plan = validate_execution_plan(plan_value)
    identity_value = {
        "schema": "pulsarmlx.f017.event06-v12-prompt-bound-event-identity-plan/2.0.0",
        "authorization_id": authorization_id, "package_attempt_id": package_attempt_id,
        "primary_event_id": primary_event_id, "secondary_event_id": secondary_event_id,
        "execution_plan_sha256": plan.sha256, "prompt_repository_commit": PROMPT_COMMIT,
        "prompt_repository_path": PROMPT_PATH,
        "prompt_sha256": hashlib.sha256(PROMPT_BYTES).hexdigest(),
    }
    identity_raw = canonical_bytes(identity_value)
    event_identity = seal_prompt_bound_event_identity_plan(
        identity_raw, prompt_bytes=PROMPT_BYTES,
        prompt_repository_commit=PROMPT_COMMIT, prompt_repository_path=PROMPT_PATH,
    )
    installed_value = {
        "schema": "pulsarmlx.f017.corrected-oracle-checkpoint-identity-installed-authority/12.1.0",
        "generation": "V12", "authorization_id": authorization_id,
        "package_attempt_id": package_attempt_id, "checkpoint_set_sha256": fixed,
        "event_identity_plan_sha256": event_identity.source_sha256,
        "installation_receipt_sha256": "b" * 64,
    }
    installed = ValidatedIdentityAuthority(
        tuple(sorted(installed_value.items())),
        hashlib.sha256(canonical_bytes(installed_value)).hexdigest(), "INSTALLED",
    )
    leases = LeaseSet(
        [LeaseRecord(item, 2000 + item["shard_ordinal"]) for item in descriptors],
        hashlib.sha256(b"synthetic-identity-only").hexdigest(),
        [item["sha256"] for item in shards[1:]],
    )
    report = {
        "result": "PASS", "authority_scope": "SYNTHETIC_NON_AUTHORITY",
        "operation_class": "IDENTITY_ONLY", "generation": "V12",
        "ordered_shard_digests": [item["sha256"] for item in shards],
        "checkpoint_shard_opens": 6, "checkpoint_identity_hash_reads": 6,
        "retained_lease_count": 5, "identity_only_retained_count": 0,
        "descriptor_identities": descriptors, "path_reopen_count": 0,
        "evidence": {
            "access_journal_sha256": "1" * 64, "shard_receipts_sha256": "2" * 64,
            "lease_manifest_sha256": "3" * 64, "deterministic_core_sha256": "4" * 64,
            "identity_manifest_sha256": "5" * 64, "identity_receipt_sha256": "6" * 64,
            "identity_terminal_sha256": "7" * 64, "identity_terminal_state": "COMPLETE",
        },
    }
    identity_stage = bind_identity_stage(installed, leases, report)
    bridge_input = produce_identity_bridge_input(event_identity, installed, plan)
    bridge = derive_bridge(bridge_input, installed, identity_stage, plan)
    return bridge, bridge_input, event_identity, installed, leases, report, identity_stage, plan


if __name__ == "__main__":
    bridge, bridge_input, event_identity, *_ = runtime_fixture_values()
    print(bridge.sha256, bridge_input.sha256, event_identity.source_sha256)
