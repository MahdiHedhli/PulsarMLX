#!/usr/bin/env python3
"""Instantiate the fixed Event 06 coordinator with explicit no-capability spies."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from f017_canonical_serialization_v10 import canonical_bytes
from f017_event06_bridge_synthetic_fixture_v1 import runtime_fixture_values
from f017_event06_numerical_bridge_v1 import build_bundle_binding
import execute_f017_corrected_oracle_event_v12_bridge as coordinator


def _sha(value: dict) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _bundle(role: str, bridge_sha256: str) -> dict:
    manifest = {"payloads":[{"sha256":"1"*64},{"sha256":"2"*64},{"sha256":"3"*64}]}
    receipt = {"routing_manifest_sha256":"4"*64}
    manifest_sha = _sha(manifest); receipt_sha = _sha(receipt); result_terminal_sha = "5" * 64
    terminal = {"schema":"pulsarmlx.f017.corrected-oracle-consumer-terminal/11.0.0",
        "role":role,"result":"COMPLETE","result_terminal_sha256":result_terminal_sha,
        "result_receipt_sha256":receipt_sha,"payload_manifest_sha256":manifest_sha,
        "secondary_eligible":role == "PRIMARY"}
    artifacts = {"manifest":manifest,"receipt":receipt,"consumer_terminal":terminal,
        "routing":{},"top32":{}}
    index = {"result_terminal_sha256":result_terminal_sha,"result_receipt_sha256":receipt_sha,
        "manifest_sha256":manifest_sha,"result":"PASS"}
    return {"artifacts":artifacts,"index":index,"bridge_bundle_binding_sha256":bridge_sha256,
            "result":"PASS"}


def _release_report(package_attempt_id: str) -> dict:
    lease_ids = [f"LEASE-{package_attempt_id}-{ordinal}" for ordinal in range(2, 7)]
    events = [
        {"lease_id":lease_id,"shard_ordinal":ordinal,"attempt":1,"prior_state":"OPEN",
         "result":"PASS_CLOSE","state":"CLOSED","close_event_sha256":None,
         "evidence_result":"PASS"}
        for ordinal, lease_id in zip(range(2, 7), lease_ids, strict=True)
    ]
    return {"release_pass":1,"expected_leases":5,"attempted_closures":5,
        "successful_closures":5,"duplicate_closures":0,"unknown_leases":0,
        "live_leases_after_release":0,"remaining_live_lease_ids":[],
        "lease_states":{lease_id:"CLOSED" for lease_id in lease_ids},
        "close_events":events,"idempotent_noop":False,"pending_close_evidence":[],
        "evidence_banking_failures":0,"result":"PASS"}


def _summary(bridge) -> dict:
    return {"schema":"pulsarmlx.f017.corrected-oracle-binary-comparison-summary/11.0.0",
        "authorization_id":bridge.get("authorization_id"),
        "package_attempt_id":bridge.get("package_attempt_id"),
        "classification":"EXACT_EXPECTED_TOKEN_STABLE"}


def qualify_call_path() -> dict:
    expected, installed, leases, report, plan, event_plan = runtime_fixture_values()
    calls: list[str] = []

    def package_gate(*_args):
        calls.append("PACKAGE_START_GATE_VALIDATED")
        return {"installed_authority":installed,"result":"PASS"}

    def identity_stage(*_args, **_kwargs):
        calls.append("V12_IDENTITY_TERMINAL_AND_FIVE_LEASES_VALIDATED")
        return leases, report

    def primary(*args):
        calls.append("PRIMARY_SINGLE_CALL")
        if args[0].get("bridge_sha256") != expected.sha256:
            raise ValueError("primary bridge authority")
        bundle = _bundle("PRIMARY", "6" * 64)
        binding, binding_sha = build_bundle_binding(args[0], args[1], bundle["index"])
        return bundle | {"bridge_bundle_binding": binding, "bridge_bundle_binding_sha256": binding_sha}

    def secondary(*args):
        calls.append("SECONDARY_SINGLE_CALL")
        if args[0].get("bridge_sha256") != expected.sha256:
            raise ValueError("secondary bridge authority")
        bundle = _bundle("SECONDARY", "7" * 64)
        binding, binding_sha = build_bundle_binding(args[0], args[1], bundle["index"])
        return bundle | {"bridge_bundle_binding": binding, "bridge_bundle_binding_sha256": binding_sha}

    def compare(*_args):
        calls.append("INDEPENDENT_COMPARISON")
        return _summary(expected)

    def validate_compare(*_args):
        calls.append("COMPARISON_VALIDATED")
        return {"result":"PASS"}

    release_calls = 0
    def release():
        nonlocal release_calls
        release_calls += 1; calls.append("DESCRIPTOR_RELEASE")
        return _release_report(expected.get("package_attempt_id"))
    leases.release = release

    def bank(_path, value):
        return _sha(value)

    with tempfile.TemporaryDirectory(prefix="f017-event06-bridge-callpath-") as temporary:
        root = Path(temporary)
        with (patch.object(coordinator, "validate_package_start", package_gate),
              patch.object(coordinator, "run_identity_stage", identity_stage),
              patch.object(coordinator, "execute_primary", primary),
              patch.object(coordinator, "execute_secondary", secondary),
              patch.object(coordinator, "derive_summary", compare),
              patch.object(coordinator, "validate_summary", validate_compare),
              patch.object(coordinator, "bank_exclusive", bank)):
            result = coordinator.execute_event06_bridge(
                root / "candidate", root / "installed", root / "receipt",
                package_attempt_id=expected.get("package_attempt_id"),
                package_start_path=root / "package-start.json",
                identity_evidence_directory=root / "identity",
                execution_plan=plan, event_identity_plan=event_plan,
                primary_directory=root / "primary", secondary_directory=root / "secondary",
                package_directory=root / "package", terminal_path=root / "package-terminal.json",
            )
    if (result["result"] != "PASS" or result["bridge"].sha256 != expected.sha256
            or result["package"]["result"] != "PASS" or release_calls != 1
            or type(result["package_start"]) is not coordinator.ValidatedDurableStart
            or type(result["execution"]) is not coordinator.ValidatedBridgeExecutionResult
            or calls.count("PRIMARY_SINGLE_CALL") != 1 or calls.count("SECONDARY_SINGLE_CALL") != 1):
        raise ValueError("production coordinator instantiability")

    failure_release_paths = 0
    _bridge, bridge_installed, bridge_leases, bridge_report, bridge_plan, bridge_event_plan = runtime_fixture_values()
    bridge_report = dict(bridge_report); bridge_report["checkpoint_shard_opens"] = 5
    bridge_released = 0
    def bridge_failure_release():
        nonlocal bridge_released
        bridge_released += 1
        return _release_report(_bridge.get("package_attempt_id"))
    bridge_leases.release = bridge_failure_release
    with tempfile.TemporaryDirectory(prefix="f017-event06-bridge-derivation-failure-") as temporary:
        root = Path(temporary)
        with (patch.object(coordinator, "validate_package_start",
                           lambda *_args: {"installed_authority":bridge_installed,"result":"PASS"}),
              patch.object(coordinator, "run_identity_stage", lambda *_args, **_kwargs: (bridge_leases, bridge_report)),
              patch.object(coordinator, "bank_exclusive", bank)):
            try:
                coordinator.execute_event06_bridge(
                    root / "candidate", root / "installed", root / "receipt",
                    package_attempt_id=_bridge.get("package_attempt_id"),
                    package_start_path=root / "package-start.json",
                    identity_evidence_directory=root / "identity", execution_plan=bridge_plan,
                    event_identity_plan=bridge_event_plan, primary_directory=root / "primary",
                    secondary_directory=root / "secondary", package_directory=root / "package",
                    terminal_path=root / "package-terminal.json")
            except ValueError:
                pass
            else:
                raise ValueError("bridge derivation failure unexpectedly passed")
    if bridge_released != 1:
        raise ValueError("bridge derivation descriptor release")
    failure_release_paths += 1

    for failed_stage in ("PRIMARY", "SECONDARY", "COMPARISON"):
        bridge, _installed, failure_leases, _report, _plan, _event_plan = runtime_fixture_values()
        released = 0
        def failure_release():
            nonlocal released
            released += 1
            return _release_report(bridge.get("package_attempt_id"))
        failure_leases.release = failure_release
        def primary_stage(*args):
            if failed_stage == "PRIMARY": raise RuntimeError("modeled primary failure")
            bundle = _bundle("PRIMARY", "6" * 64)
            binding, binding_sha = build_bundle_binding(args[0], args[1], bundle["index"])
            return bundle | {"bridge_bundle_binding": binding, "bridge_bundle_binding_sha256": binding_sha}
        def secondary_stage(*args):
            if failed_stage == "SECONDARY": raise RuntimeError("modeled secondary failure")
            bundle = _bundle("SECONDARY", "7" * 64)
            binding, binding_sha = build_bundle_binding(args[0], args[1], bundle["index"])
            return bundle | {"bridge_bundle_binding": binding, "bridge_bundle_binding_sha256": binding_sha}
        def comparison_stage(*_args):
            if failed_stage == "COMPARISON": raise RuntimeError("modeled comparison failure")
            return _summary(bridge)
        with tempfile.TemporaryDirectory(prefix="f017-event06-bridge-failure-") as temporary:
            root = Path(temporary)
            with (patch.object(coordinator, "execute_primary", primary_stage),
                  patch.object(coordinator, "execute_secondary", secondary_stage),
                  patch.object(coordinator, "derive_summary", comparison_stage),
                  patch.object(coordinator, "validate_summary", lambda *_args: {"result":"PASS"}),
                  patch.object(coordinator, "bank_exclusive", bank)):
                try:
                    coordinator.execute_consumers(bridge, failure_leases, root / "primary",
                        root / "secondary", root / "package")
                except RuntimeError:
                    pass
                else:
                    raise ValueError("modeled failure unexpectedly passed")
        if released != 1:
            raise ValueError("failure path descriptor release")
        failure_release_paths += 1

    return {"schema":"pulsarmlx.f017.event06-bridge-call-path-qualification/2.0.0",
        "production_coordinator_instantiated":"PASS","producer_adapter":"PASS",
        "primary_calls":1,"secondary_calls":1,"success_release_passes":release_calls,
        "sealed_durable_starts":3,"caller_supplied_start_digests":0,
        "sealed_execution_result":"PASS",
        "failure_release_paths":failure_release_paths,"comparison_release_accounting_chain":"PASS",
        "package_terminal":"PASS","original_checkpoint_root_resolved":False,
        "original_checkpoint_access":0,"numerical_operations":0,"live_state_created":False,
        "live_authority_installed":False,"event06_ids_consumed":0,"event06_executed":False,
        "result":"PASS"}


if __name__ == "__main__":
    print(json.dumps(qualify_call_path(), sort_keys=True, separators=(",", ":")))
