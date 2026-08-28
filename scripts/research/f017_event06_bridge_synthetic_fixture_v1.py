#!/usr/bin/env python3
"""Deterministic synthetic-only bridge fixture; never resolves a checkpoint root."""
from __future__ import annotations

import hashlib
import stat

from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import ValidatedIdentityAuthority
from f017_event06_execution_plan_v1 import validate_execution_plan
from f017_event06_numerical_bridge_v1 import derive_bridge, validate_identity_stage


def fixture_values():
    fixed = "a" * 64
    event_plan = {"schema":"pulsarmlx.f017.event06-event-identity-plan/1.0.0",
        "package_attempt_id":"F017-BRIDGE-PACKAGE-01","primary_event_id":"F017-BRIDGE-PRIMARY-01",
        "secondary_event_id":"F017-BRIDGE-SECONDARY-01"}
    event_sha = hashlib.sha256(canonical_bytes(event_plan)).hexdigest()
    shards = [{"filename":f"synthetic-shard-{ordinal}.bin","size_bytes":0 if ordinal == 1 else ordinal,
        "sha256":hashlib.sha256(f"shard-{ordinal}".encode()).hexdigest(),
        "role":"IDENTITY_ONLY" if ordinal == 1 else "GRAPH_PAYLOAD"} for ordinal in range(1,7)]
    descriptors = [{"device":1,"inode":ordinal,"mode":stat.S_IFREG | 0o600,
        "size":ordinal,"mtime_ns":ordinal,"ctime_ns":ordinal,"shard_ordinal":ordinal,
        "role":"GRAPH_PAYLOAD","lease_id":f"F017-BRIDGE-LEASE-{ordinal}"} for ordinal in range(2,7)]
    descriptor_sha = hashlib.sha256(canonical_bytes(descriptors)).hexdigest()
    installed_value = {"schema":"pulsarmlx.f017.corrected-oracle-checkpoint-identity-installed-authority/12.1.0",
        "generation":"V12","authorization_id":"F017-BRIDGE-AUTH-01",
        "package_attempt_id":event_plan["package_attempt_id"],"checkpoint_set_sha256":fixed,
        "event_identity_plan_sha256":event_sha,"installation_receipt_sha256":"b" * 64}
    installed = ValidatedIdentityAuthority(tuple(sorted(installed_value.items())),
        hashlib.sha256(canonical_bytes(installed_value)).hexdigest(), "INSTALLED")
    identity = validate_identity_stage({"schema":"pulsarmlx.f017.event06-v12-identity-stage-binding/1.0.0",
        "authorization_id":installed_value["authorization_id"],"package_attempt_id":event_plan["package_attempt_id"],
        "checkpoint_set_sha256":fixed,"identity_manifest_sha256":"c" * 64,"identity_terminal_sha256":"d" * 64,
        "access_census_sha256":"e" * 64,"descriptor_identity_sha256":descriptor_sha,
        "lease_owner":event_plan["package_attempt_id"],"graph_descriptors":descriptors,"result":"PASS"})
    plan_value = {"schema":"pulsarmlx.f017.event06-v12-execution-plan/1.0.0",
        "package_attempt_id":event_plan["package_attempt_id"],"primary_event_id":event_plan["primary_event_id"],
        "secondary_event_id":event_plan["secondary_event_id"],"event_identity_plan_sha256":event_sha,
        "source_head":"1" * 40,"source_tree":"2" * 40,"implementation_measurement_sha256":"3" * 64,
        "tensor_catalog_path":"specs/017-rust-native-inference-runtime/contracts/f017-synthetic-descriptor-catalog-v9.json",
        "tensor_catalog_sha256":"4" * 64,"primary_numerical_sha256":"5" * 64,
        "secondary_numerical_sha256":"6" * 64,
        "numerical_contract_path":"specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json",
        "numerical_contract_sha256":"7" * 64,
        "result_authority_path":"specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-result-authority-v11-v2.json",
        "result_authority_sha256":"8" * 64,"result_bundle_builder_sha256":"9" * 64,
        "comparison_authority_sha256":"a" * 64,"release_authority_sha256":"b" * 64,
        "accounting_authority_sha256":"c" * 64,"primary_target_source_sha256":"d" * 64,
        "secondary_target_source_sha256":"e" * 64,"shards":shards,"attempts":1,"retries":0,"resume":False}
    plan = validate_execution_plan(plan_value)
    return derive_bridge(installed, identity, plan, event_plan), installed, identity, plan, event_plan, plan_value
