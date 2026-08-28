#!/usr/bin/env python3
"""Complete V12 bridge coordinator surface; repair qualification is no-access only."""
from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

from f017_binary_comparison_authority_v11 import derive_summary, validate_summary
from f017_canonical_serialization_v10 import bank_exclusive, canonical_bytes
from f017_corrected_oracle_primary_wrapper_v12 import execute_bridge_and_bank as execute_primary
from f017_corrected_oracle_secondary_wrapper_v12 import execute_bridge_and_bank as execute_secondary
from f017_descriptor_lease_manager_v10 import LeaseSet
from f017_event06_numerical_bridge_v1 import (
    PHASES, ValidatedIdentityStage, ValidatedNumericalBridge,
    accounting_view, build_package_terminal, build_transition_binding,
    comparison_view, derive_bridge, numerical_view, package_terminal_view,
    primary_terminal_binding, release_view, result_bundle_view,
    validate_package_terminal, validate_transition_chain,
)
from f017_event06_execution_plan_v1 import ValidatedExecutionPlan
from f017_result_artifacts_v11 import closure_root
from execute_f017_corrected_oracle_event_v12 import run_identity_stage, validate_package_start

PRODUCTION_CALL_PATH = (
    "VALIDATED_READINESS", "V12_CANDIDATE_TRIPLE_VALIDATED",
    "V12_INSTALLED_AUTHORITY_AND_RECEIPT_VALIDATED", "PACKAGE_START_GATE_VALIDATED",
    "DURABLE_PACKAGE_START", "V12_IDENTITY_TERMINAL_AND_FIVE_LEASES_VALIDATED",
    "EXECUTION_PLAN_VALIDATED", "BRIDGE_DERIVED_AND_VALIDATED",
    "PRIMARY_DURABLE_START", "PRIMARY_SINGLE_CALL", "PRIMARY_RESULT_TERMINAL",
    "SECONDARY_DURABLE_START", "SECONDARY_SINGLE_CALL", "SECONDARY_RESULT_TERMINAL",
    "INDEPENDENT_COMPARISON", "DESCRIPTOR_RELEASE", "ACCOUNTING_CLOSURE", "PACKAGE_TERMINAL",
)


def validate_transition_order(trace: object) -> dict:
    if type(trace) is not list or tuple(trace) != PRODUCTION_CALL_PATH:
        raise ValueError("Event 06 bridge transition order")
    if trace.count("PRIMARY_SINGLE_CALL") != 1 or trace.count("SECONDARY_SINGLE_CALL") != 1:
        raise ValueError("Event 06 bridge one-shot calls")
    return {"result":"PASS","transition_count":len(trace),"primary_calls":1,"secondary_calls":1}


def _bind(function, *args, **kwargs) -> None:
    inspect.signature(function).bind(*args, **kwargs)


def validate_no_access_call_path() -> dict:
    """Bind every real consumer signature without invoking any capability."""
    token = object(); path = Path("synthetic-validation-only")
    _bind(validate_package_start, path, path, path)
    _bind(run_identity_stage, token, package_attempt_id="P", package_durable_start=True,
          evidence_directory=path)
    _bind(derive_bridge, token, token, token, {})
    _bind(execute_primary, token, token, [1,2,3,4,5], path)
    _bind(execute_secondary, token, token, [1,2,3,4,5], path)
    _bind(derive_summary, path, {}, path, {}, {}, {}, {}, {}, {}, {}, {}, {}, "A")
    _bind(validate_summary, {}, path, {}, path, {}, {}, {}, {}, {}, {}, {}, {}, {}, "A")
    _bind(LeaseSet.release, token)
    _bind(closure_root, {}, {}, {}, {}, {}, {}, *("0" * 64 for _ in range(10)))
    _bind(build_package_terminal, token)
    validate_transition_order(list(PRODUCTION_CALL_PATH))
    return {
        "result":"PASS", "real_signatures_bound":10,
        "transition_count":len(PRODUCTION_CALL_PATH),
        "checkpoint_root_resolved":False,"checkpoint_opens":0,"checkpoint_hash_reads":0,
        "checkpoint_payload_reads":0,"checkpoint_mmaps":0,"tensor_reads":0,
        "numerical_operations":0,"durable_live_state_created":False,
        "live_authority_installed":False,"event06_ids_consumed":0,"event06_executed":False,
    }


def _sha(value: dict) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def execute_consumers(bridge: ValidatedNumericalBridge, leases: LeaseSet,
                      primary_directory: Path, secondary_directory: Path,
                      primary_start_sha256: str, secondary_start_sha256: str) -> dict:
    """Future live path: exactly one primary and one secondary invocation."""
    if type(bridge) is not ValidatedNumericalBridge or type(leases) is not LeaseSet:
        raise TypeError("validated bridge and lease set required")
    primary_numerical = numerical_view(bridge, "PRIMARY")
    primary_result = result_bundle_view(bridge, "PRIMARY", primary_start_sha256)
    primary = execute_primary(primary_numerical, primary_result, leases.inherited_fds(), primary_directory)
    primary_binding = primary_terminal_binding(
        primary, bridge.sha256, primary["bridge_bundle_binding_sha256"]
    )
    secondary_numerical = numerical_view(bridge, "SECONDARY", primary_binding=primary_binding)
    secondary_result = result_bundle_view(bridge, "SECONDARY", secondary_start_sha256)
    secondary = execute_secondary(secondary_numerical, secondary_result,
                                  leases.inherited_fds(), secondary_directory)
    compare_authority = comparison_view(
        bridge, primary["bridge_bundle_binding_sha256"],
        secondary["bridge_bundle_binding_sha256"],
    )
    pa, sa = primary["artifacts"], secondary["artifacts"]
    comparison = derive_summary(
        primary_directory, pa["manifest"]["payloads"][2],
        secondary_directory, sa["manifest"]["payloads"][2],
        pa["routing"], sa["routing"], pa["manifest"], sa["manifest"],
        pa["top32"], sa["top32"], pa["receipt"], sa["receipt"],
        compare_authority.get("authorization_id"),
    )
    validate_summary(
        comparison, primary_directory, pa["manifest"]["payloads"][2],
        secondary_directory, sa["manifest"]["payloads"][2],
        pa["routing"], sa["routing"], pa["manifest"], sa["manifest"],
        pa["top32"], sa["top32"], pa["receipt"], sa["receipt"],
        compare_authority.get("authorization_id"),
    )
    return {"bridge_sha256":bridge.sha256,"primary":primary,"secondary":secondary,
            "comparison":comparison,"comparison_view":compare_authority,"result":"PASS"}


def bank_bridge_transition_chain(directory: Path, bridge: ValidatedNumericalBridge,
                                 subjects: list[tuple[str, str]]) -> tuple[list[dict], str]:
    """Bank ten adjacent V12 bindings around unchanged V11 artifacts."""
    if type(subjects) is not list or len(subjects) != len(PHASES):
        raise ValueError("bridge transition subjects")
    directory.mkdir(parents=True, exist_ok=True)
    predecessor = "0" * 64; records = []
    for phase, (kind, digest) in zip(PHASES, subjects, strict=True):
        record, record_sha = build_transition_binding(bridge, phase, kind, digest, predecessor)
        observed = bank_exclusive(directory / f"bridge-transition-{len(records)+1:02d}.json", record)
        if observed != record_sha:
            raise ValueError("bridge transition banking")
        records.append(record); predecessor = record_sha
    if validate_transition_chain(bridge, records) != predecessor:
        raise ValueError("bridge transition reconstruction")
    return records, predecessor


def close_bridge_package(bridge: ValidatedNumericalBridge, chain_head_sha256: str,
                         v11_closure: dict, accounting_binding_sha256: str,
                         terminal_path: Path) -> dict:
    view = package_terminal_view(
        bridge, chain_head_sha256, _sha(v11_closure), accounting_binding_sha256
    )
    terminal = build_package_terminal(view)
    terminal_sha = validate_package_terminal(terminal, bridge)
    if bank_exclusive(terminal_path, terminal) != terminal_sha:
        raise ValueError("bridge package terminal banking")
    return {"terminal":terminal,"terminal_sha256":terminal_sha,"result":"PASS"}
