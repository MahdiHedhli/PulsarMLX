#!/usr/bin/env python3
"""Complete V12 bridge coordinator surface; repair qualification is no-access only."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from types import MappingProxyType

from f017_binary_comparison_authority_v11 import derive_summary, validate_summary
from f017_canonical_serialization_v10 import bank_exclusive, canonical_bytes
from f017_corrected_oracle_primary_wrapper_v12 import execute_bridge_and_bank as execute_primary
from f017_corrected_oracle_secondary_wrapper_v12 import execute_bridge_and_bank as execute_secondary
from f017_descriptor_lease_manager_v10 import LeaseSet
from f017_checkpoint_identity_authority_v12 import ValidatedIdentityAuthority
from f017_event06_numerical_bridge_v1 import (
    PHASES, ValidatedIdentityStage, ValidatedNumericalBridge,
    accounting_view, bind_identity_stage, bind_v11_closure, build_accounting_binding,
    build_comparison_binding, build_package_terminal, build_release_binding,
    build_transition_binding, comparison_view, derive_bridge, numerical_view, package_terminal_view,
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
_EXECUTION_RESULT_SEAL = object()
_START_SEAL = object()


class ValidatedDurableStart:
    """Coordinator-created durable start bound to the installed authority."""
    __slots__ = ("_value", "sha256")

    def __new__(cls, seal=None, value=None):
        if seal is not _START_SEAL:
            raise TypeError("durable starts are coordinator-created")
        return super().__new__(cls)

    def __init__(self, seal, value):
        object.__setattr__(self, "_value", MappingProxyType(dict(value)))
        object.__setattr__(self, "sha256", _sha(value))

    def __setattr__(self, name, value):
        del name, value
        raise TypeError("durable starts are immutable")

    def __delattr__(self, name):
        del name
        raise TypeError("durable starts are immutable")

    def get(self, key, default=None):
        return self._value.get(key, default)


class ValidatedBridgeExecutionResult:
    """Coordinator-created result closure; callers cannot supply digest mappings."""
    __slots__ = ("_value",)

    def __new__(cls, seal=None, value=None):
        if seal is not _EXECUTION_RESULT_SEAL:
            raise TypeError("bridge execution results are coordinator-created")
        return super().__new__(cls)

    def __init__(self, seal, value):
        object.__setattr__(self, "_value", MappingProxyType(dict(value)))

    def __setattr__(self, name, value):
        del name, value
        raise TypeError("bridge execution results are immutable")

    def __delattr__(self, name):
        del name
        raise TypeError("bridge execution results are immutable")

    def get(self, key, default=None):
        return self._value.get(key, default)

    def __getitem__(self, key):
        return self._value[key]


def validate_transition_order(trace: object) -> dict:
    if type(trace) is not list or tuple(trace) != PRODUCTION_CALL_PATH:
        raise ValueError("Event 06 bridge transition order")
    if trace.count("PRIMARY_SINGLE_CALL") != 1 or trace.count("SECONDARY_SINGLE_CALL") != 1:
        raise ValueError("Event 06 bridge one-shot calls")
    return {"result":"PASS","transition_count":len(trace),"primary_calls":1,"secondary_calls":1}


def validate_no_access_call_path() -> dict:
    """Run the canonical complete synthetic authority path without capabilities."""
    from f017_event06_dag_derived_control_path_v1 import run_full_call_path
    with tempfile.TemporaryDirectory(prefix="f017-event06-no-access-") as directory:
        full = run_full_call_path(Path(directory))
    counters = full["live_counters"]
    if full["result"] != "PASS" or any(counters.values()):
        raise ValueError("Event 06 bridge authority chain")
    order = validate_transition_order(list(PRODUCTION_CALL_PATH))
    return {
        "result":"PASS", "producer_adapter":"PASS", "authority_chain":"PASS",
        "release_binding_sha256":full["release_binding_sha256"],
        "accounting_binding_sha256":full["legacy_accounting_binding_sha256"],
        "real_signatures_bound":0, "transition_count":order["transition_count"],
        "checkpoint_root_resolved":False,"checkpoint_opens":0,"checkpoint_hash_reads":0,
        "checkpoint_payload_reads":0,"checkpoint_mmaps":0,"tensor_reads":0,
        "numerical_operations":0,"durable_live_state_created":False,
        "live_authority_installed":False,"event06_ids_consumed":0,"event06_executed":False,
    }


def _sha(value: dict) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _bank_checked(path: Path, value: dict, expected_sha256: str) -> None:
    if bank_exclusive(path, value) != expected_sha256:
        raise ValueError("Event 06 bridge artifact banking")


def bank_package_start(installed: ValidatedIdentityAuthority,
                       path: Path) -> ValidatedDurableStart:
    if type(installed) is not ValidatedIdentityAuthority or installed.posture != "INSTALLED":
        raise TypeError("validated installed authority required")
    authority = installed.as_dict()
    value = {
        "schema":"pulsarmlx.f017.event06-v12-bridge-package-durable-start/1.0.0",
        "authorization_id":authority["authorization_id"],
        "package_attempt_id":authority["package_attempt_id"],
        "installed_authority_sha256":installed.source_sha256,
        "installation_receipt_sha256":authority["installation_receipt_sha256"],
        "attempts":1,"retries":0,"resume":False,"state":"DURABLE_START",
    }
    start = ValidatedDurableStart(_START_SEAL, value)
    _bank_checked(path, value, start.sha256)
    return start


def bank_consumer_start(bridge: ValidatedNumericalBridge, role: str, path: Path, *,
                        primary_terminal_binding_sha256: str | None = None) -> ValidatedDurableStart:
    if type(bridge) is not ValidatedNumericalBridge or role not in {"PRIMARY", "SECONDARY"}:
        raise TypeError("validated bridge and consumer role required")
    value = {
        "schema":"pulsarmlx.f017.event06-v12-bridge-consumer-durable-start/1.0.0",
        "role":role,"bridge_sha256":bridge.sha256,
        "authorization_id":bridge.get("authorization_id"),
        "package_attempt_id":bridge.get("package_attempt_id"),
        "consumer_event_id":bridge.get(f"{role.lower()}_event_id"),
        "attempts":1,"retries":0,"resume":False,"state":"DURABLE_START",
    }
    if role == "PRIMARY":
        if primary_terminal_binding_sha256 is not None:
            raise ValueError("primary start cannot bind a prior consumer terminal")
    else:
        if type(primary_terminal_binding_sha256) is not str:
            raise ValueError("secondary start requires primary terminal binding")
        value["primary_terminal_binding_sha256"] = primary_terminal_binding_sha256
    start = ValidatedDurableStart(_START_SEAL, value)
    _bank_checked(path, value, start.sha256)
    return start


def execute_consumers(bridge: ValidatedNumericalBridge, leases: LeaseSet,
                      primary_directory: Path, secondary_directory: Path,
                      package_directory: Path) -> ValidatedBridgeExecutionResult:
    """Future live path: exactly one primary and one secondary invocation."""
    if type(bridge) is not ValidatedNumericalBridge or type(leases) is not LeaseSet:
        raise TypeError("validated bridge and lease set required")
    if not isinstance(package_directory, Path):
        raise TypeError("package evidence directory required")
    package_directory.mkdir(parents=True, exist_ok=True)
    completed_phase = "IDENTITY_TERMINAL"
    try:
        primary_start = bank_consumer_start(
            bridge, "PRIMARY", package_directory / "bridge-primary-durable-start.json"
        )
        primary_numerical = numerical_view(bridge, "PRIMARY")
        primary_result = result_bundle_view(bridge, "PRIMARY", primary_start.sha256)
        primary = execute_primary(primary_numerical, primary_result, leases.inherited_fds(), primary_directory)
        completed_phase = "PRIMARY_RESULT_TERMINAL"
        primary_binding = primary_terminal_binding(
            primary, bridge, primary["bridge_bundle_binding"]
        )
        secondary_start = bank_consumer_start(
            bridge, "SECONDARY", package_directory / "bridge-secondary-durable-start.json",
            primary_terminal_binding_sha256=primary_binding.sha256,
        )
        secondary_numerical = numerical_view(bridge, "SECONDARY", primary_binding=primary_binding)
        secondary_result = result_bundle_view(bridge, "SECONDARY", secondary_start.sha256)
        secondary = execute_secondary(secondary_numerical, secondary_result,
                                      leases.inherited_fds(), secondary_directory)
        completed_phase = "SECONDARY_RESULT_TERMINAL"
        compare_authority = comparison_view(
            bridge, primary["bridge_bundle_binding"],
            secondary["bridge_bundle_binding"],
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
        comparison_binding, comparison_binding_sha = build_comparison_binding(compare_authority, comparison)
        _bank_checked(package_directory / "bridge-comparison-binding.json", comparison_binding.as_dict(),
                      comparison_binding_sha)
    except Exception:
        release_report = leases.release()
        failure_release = {"schema":"pulsarmlx.f017.event06-bridge-failure-release/1.0.0",
            "bridge_sha256":bridge.sha256,"package_attempt_id":bridge.get("package_attempt_id"),
            "completed_phase":completed_phase,"release_report":release_report,
            "result":"TERMINAL_FAILURE"}
        _bank_checked(package_directory / "bridge-failure-release.json", failure_release,
                      _sha(failure_release))
        raise

    release_authority = release_view(bridge, comparison_binding)
    release_report = leases.release()
    release_binding, release_binding_sha = build_release_binding(release_authority, release_report)
    _bank_checked(package_directory / "bridge-release-report.json", release_report, _sha(release_report))
    _bank_checked(package_directory / "bridge-release-binding.json", release_binding.as_dict(), release_binding_sha)
    accounting_authority = accounting_view(bridge, release_binding)
    accounting_binding, accounting_binding_sha = build_accounting_binding(accounting_authority, release_binding)
    _bank_checked(package_directory / "bridge-accounting-binding.json", accounting_binding.as_dict(),
                  accounting_binding_sha)

    comparison_receipt = {"schema":"pulsarmlx.f017.event06-bridge-comparison-receipt/1.0.0",
        "bridge_sha256":bridge.sha256,"comparison_binding_sha256":comparison_binding_sha,
        "comparison_summary_sha256":_sha(comparison),"result":"PASS"}
    comparison_terminal = {"schema":"pulsarmlx.f017.event06-bridge-comparison-terminal/1.0.0",
        "bridge_sha256":bridge.sha256,"comparison_receipt_sha256":_sha(comparison_receipt),
        "result":"COMPLETE"}
    release_start = {"schema":"pulsarmlx.f017.event06-bridge-release-start/1.0.0",
        "bridge_sha256":bridge.sha256,"release_view_sha256":release_authority.sha256,
        "expected_leases":5}
    release_receipt = {"schema":"pulsarmlx.f017.event06-bridge-release-receipt/1.0.0",
        "bridge_sha256":bridge.sha256,"release_binding_sha256":release_binding_sha,
        "release_report_sha256":_sha(release_report),"result":"PASS"}
    release_terminal = {"schema":"pulsarmlx.f017.event06-bridge-release-terminal/1.0.0",
        "bridge_sha256":bridge.sha256,"release_receipt_sha256":_sha(release_receipt),
        "live_leases":0,"result":"COMPLETE"}
    package_receipt = {"schema":"pulsarmlx.f017.event06-bridge-package-receipt/1.0.0",
        "bridge_sha256":bridge.sha256,"accounting_binding_sha256":accounting_binding_sha,
        "comparison_terminal_sha256":_sha(comparison_terminal),
        "release_terminal_sha256":_sha(release_terminal),"result":"PASS"}
    for name, value in (("comparison-receipt", comparison_receipt),
                        ("comparison-terminal", comparison_terminal),
                        ("release-start", release_start), ("release-receipt", release_receipt),
                        ("release-terminal", release_terminal), ("package-receipt", package_receipt)):
        _bank_checked(package_directory / f"bridge-{name}.json", value, _sha(value))
    v11_closure = closure_root(
        pa["manifest"], pa["receipt"], pa["consumer_terminal"],
        sa["manifest"], sa["receipt"], sa["consumer_terminal"],
        primary["index"]["result_terminal_sha256"], secondary["index"]["result_terminal_sha256"],
        _sha(comparison), _sha(comparison_receipt), _sha(comparison_terminal),
        _sha(release_start), _sha(release_report), _sha(release_receipt),
        _sha(release_terminal), _sha(package_receipt),
    )
    v11_closure_binding = bind_v11_closure(bridge, v11_closure, accounting_binding)
    value = {"bridge_sha256":bridge.sha256,"primary":primary,"secondary":secondary,
            "primary_start_sha256":primary_start.sha256,"secondary_start_sha256":secondary_start.sha256,
            "comparison":comparison,"comparison_view":compare_authority,
            "comparison_binding":comparison_binding,"comparison_binding_sha256":comparison_binding_sha,
            "comparison_terminal":comparison_terminal,"release_report":release_report,
            "release_binding":release_binding,"release_binding_sha256":release_binding_sha,
            "release_terminal":release_terminal,"accounting_binding":accounting_binding,
            "accounting_binding_sha256":accounting_binding_sha,"v11_closure":v11_closure,
            "v11_closure_binding":v11_closure_binding,
            "v11_closure_sha256":_sha(v11_closure),"result":"PASS"}
    return ValidatedBridgeExecutionResult(_EXECUTION_RESULT_SEAL, value)


def derive_bridge_from_identity_output(installed_authority, leases: LeaseSet,
                                       identity_report: dict,
                                       execution_plan: ValidatedExecutionPlan,
                                       event_identity_plan: dict) -> ValidatedNumericalBridge:
    """Production adapter from the real V12 identity producer into the bridge."""
    identity = bind_identity_stage(installed_authority, leases, identity_report)
    return derive_bridge(installed_authority, identity, execution_plan, event_identity_plan)


def execute_event06_bridge(candidate_path: Path, installed_path: Path, receipt_path: Path, *,
                           package_attempt_id: str, package_start_path: Path,
                           identity_evidence_directory: Path,
                           execution_plan: ValidatedExecutionPlan, event_identity_plan: dict,
                           primary_directory: Path, secondary_directory: Path,
                           package_directory: Path, terminal_path: Path) -> dict:
    """Single fixed production call path from V12 package gate through terminal."""
    gate = validate_package_start(candidate_path, installed_path, receipt_path)
    installed = gate["installed_authority"]
    package_start = bank_package_start(installed, package_start_path)
    leases, identity_report = run_identity_stage(
        installed, package_attempt_id=package_attempt_id, package_durable_start=True,
        evidence_directory=identity_evidence_directory,
    )
    try:
        bridge = derive_bridge_from_identity_output(
            installed, leases, identity_report, execution_plan, event_identity_plan
        )
    except Exception:
        package_directory.mkdir(parents=True, exist_ok=True)
        release_report = leases.release()
        failure_release = {"schema":"pulsarmlx.f017.event06-bridge-failure-release/1.0.0",
            "package_attempt_id":package_attempt_id,"completed_phase":"IDENTITY_TERMINAL",
            "release_report":release_report,"result":"TERMINAL_FAILURE"}
        _bank_checked(package_directory / "bridge-failure-release.json", failure_release,
                      _sha(failure_release))
        raise
    result = execute_consumers(
        bridge, leases, primary_directory, secondary_directory, package_directory,
    )
    closure = close_bridge_package(bridge, package_start, result, terminal_path)
    return {"bridge":bridge,"package_start":package_start,
            "identity_report":identity_report,"execution":result,
            "package":closure,"result":"PASS"}


def bank_bridge_transition_chain(directory: Path, bridge: ValidatedNumericalBridge,
                                 subjects: list[tuple[str, str]]):
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
    chain = validate_transition_chain(bridge, records)
    if chain.get("chain_head_sha256") != predecessor:
        raise ValueError("bridge transition reconstruction")
    return records, chain


def close_bridge_package(bridge: ValidatedNumericalBridge, package_start: ValidatedDurableStart,
                         execution_result: ValidatedBridgeExecutionResult,
                         terminal_path: Path) -> dict:
    """Derive terminal inputs from the validated execution result; accept no digest strings."""
    if (type(bridge) is not ValidatedNumericalBridge
            or type(package_start) is not ValidatedDurableStart
            or type(execution_result) is not ValidatedBridgeExecutionResult
            or execution_result.get("result") != "PASS"
            or execution_result.get("bridge_sha256") != bridge.sha256):
        raise ValueError("bridge execution result")
    for start_value, bridge_value, name in (
        (package_start.get("authorization_id"), bridge.get("authorization_id"), "authorization"),
        (package_start.get("package_attempt_id"), bridge.get("package_attempt_id"), "package"),
        (package_start.get("installed_authority_sha256"), bridge.get("installed_authority_sha256"),
         "installed authority"),
        (package_start.get("installation_receipt_sha256"),
         bridge.get("installation_receipt_sha256"), "installation receipt"),
    ):
        if start_value != bridge_value:
            raise ValueError(f"package start/bridge {name}")
    _sha256 = lambda value: hashlib.sha256(canonical_bytes(value)).hexdigest()
    primary = execution_result["primary"]
    secondary = execution_result["secondary"]
    subjects = [
        ("PACKAGE_DURABLE_START", package_start.sha256),
        ("IDENTITY_TERMINAL", bridge.get("identity_terminal_sha256")),
        ("PRIMARY_DURABLE_START", execution_result["primary_start_sha256"]),
        ("PRIMARY_RESULT_TERMINAL", primary["index"]["result_terminal_sha256"]),
        ("SECONDARY_DURABLE_START", execution_result["secondary_start_sha256"]),
        ("SECONDARY_RESULT_TERMINAL", secondary["index"]["result_terminal_sha256"]),
        ("COMPARISON_TERMINAL", _sha256(execution_result["comparison_terminal"])),
        ("RELEASE_TERMINAL", _sha256(execution_result["release_terminal"])),
        ("ACCOUNTING_BINDING", execution_result["accounting_binding_sha256"]),
        ("V11_PACKAGE_CLOSURE", execution_result["v11_closure_sha256"]),
    ]
    records, transition_chain = bank_bridge_transition_chain(
        terminal_path.parent / "bridge-transition-chain", bridge, subjects
    )
    view = package_terminal_view(
        bridge, transition_chain, execution_result["v11_closure_binding"],
        execution_result["accounting_binding"]
    )
    terminal = build_package_terminal(view)
    terminal_sha = validate_package_terminal(terminal, bridge)
    if bank_exclusive(terminal_path, terminal) != terminal_sha:
        raise ValueError("bridge package terminal banking")
    return {"transition_records":records,
            "transition_chain":transition_chain,
            "chain_head_sha256":transition_chain.get("chain_head_sha256"),
            "terminal":terminal,"terminal_sha256":terminal_sha,"result":"PASS"}
