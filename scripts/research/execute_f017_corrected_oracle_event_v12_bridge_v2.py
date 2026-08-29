#!/usr/bin/env python3
"""Fixed Event 06 coordinator with prompt-bound identity continuity.

This module is a version-forward composition layer.  It leaves the accepted
package, identity, numerical, comparison, release, and accounting mechanics in
the historical coordinator unchanged and adds the missing sealed identity
edge plus prompt-bound downstream closure.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from f017_binary_comparison_authority_v11 import derive_summary, validate_summary
from f017_canonical_serialization_v10 import bank_exclusive, canonical_bytes
from f017_checkpoint_identity_authority_v12 import ValidatedIdentityAuthority
from f017_corrected_oracle_primary_wrapper_v12_bridge_v2 import execute_bridge_and_bank as execute_primary
from f017_corrected_oracle_secondary_wrapper_v12_bridge_v2 import execute_bridge_and_bank as execute_secondary
from f017_descriptor_lease_manager_v10 import LeaseSet
from f017_event06_execution_plan_v1 import ValidatedExecutionPlan
from f017_event06_numerical_bridge_v2 import (
    PromptBoundIdentityBridgeInputV2, ValidatedNumericalBridgeV2,
    build_accounting_closure, build_package_terminal, consumer_view,
    derive_bridge,
)
import f017_event06_numerical_bridge_v1 as legacy_bridge
import execute_f017_corrected_oracle_event_v12_bridge as legacy_coordinator
from f017_result_artifacts_v11 import closure_root

SUCCESSOR_CALL_PATH = (
    "INSTALLED_V12_AUTHORITY", "SEALED_PROMPT_BOUND_BRIDGE_INPUT",
    "SUCCESSOR_FIXED_EVENT06_COORDINATOR", "PACKAGE_START",
    "V12_IDENTITY_AND_LEASES", "SUCCESSOR_NUMERICAL_BRIDGE",
    "PRIMARY_AND_SECONDARY_WRAPPERS", "COMPARISON", "RELEASE",
    "ACCOUNTING", "PACKAGE_TERMINAL",
)


def _sha(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _bank(path: Path, value: dict[str, object], expected: str) -> None:
    if bank_exclusive(path, value) != expected:
        raise ValueError("prompt-bound bridge banking")


def validate_pre_package_bridge_input(
    bridge_input: PromptBoundIdentityBridgeInputV2,
    installed: ValidatedIdentityAuthority,
    execution_plan: ValidatedExecutionPlan,
) -> None:
    if type(bridge_input) is not PromptBoundIdentityBridgeInputV2:
        raise TypeError("exact sealed prompt-bound bridge input required")
    if type(installed) is not ValidatedIdentityAuthority or installed.posture != "INSTALLED":
        raise TypeError("exact installed V12 authority required")
    if type(execution_plan) is not ValidatedExecutionPlan:
        raise TypeError("exact sealed execution plan required")
    authority = installed.as_dict()
    checks = (
        (bridge_input.get("installed_authority_sha256"), installed.source_sha256),
        (bridge_input.get("installation_receipt_sha256"), authority["installation_receipt_sha256"]),
        (bridge_input.get("event_identity_plan_sha256"), authority["event_identity_plan_sha256"]),
        (bridge_input.get("authorization_id"), authority["authorization_id"]),
        (bridge_input.get("package_attempt_id"), authority["package_attempt_id"]),
        (bridge_input.get("execution_plan_sha256"), execution_plan.sha256),
        (bridge_input.get("package_attempt_id"), execution_plan.get("package_attempt_id")),
        (bridge_input.get("primary_event_id"), execution_plan.get("primary_event_id")),
        (bridge_input.get("secondary_event_id"), execution_plan.get("secondary_event_id")),
    )
    if any(observed != expected for observed, expected in checks):
        raise ValueError("pre-package prompt-bound bridge continuity")


def execute_consumers(
    bridge: ValidatedNumericalBridgeV2,
    leases: LeaseSet,
    primary_directory: Path,
    secondary_directory: Path,
    package_directory: Path,
) -> legacy_coordinator.ValidatedBridgeExecutionResult:
    """Run unchanged consumers through prompt-bound views exactly once per role."""
    if type(bridge) is not ValidatedNumericalBridgeV2 or type(leases) is not LeaseSet:
        raise TypeError("validated successor bridge and lease set required")
    historical = bridge.legacy_bridge
    package_directory.mkdir(parents=True, exist_ok=True)
    completed_phase = "IDENTITY_TERMINAL"
    try:
        primary_start = legacy_coordinator.bank_consumer_start(
            historical, "PRIMARY", package_directory / "bridge-primary-durable-start.json"
        )
        primary_numerical = consumer_view(
            bridge, "PRIMARY_NUMERICAL", legacy_bridge.numerical_view(historical, "PRIMARY")
        )
        primary_result = consumer_view(
            bridge, "PRIMARY_RESULT",
            legacy_bridge.result_bundle_view(historical, "PRIMARY", primary_start.sha256),
        )
        primary = execute_primary(
            primary_numerical, primary_result, leases.inherited_fds(), primary_directory
        )
        completed_phase = "PRIMARY_RESULT_TERMINAL"
        primary_binding = legacy_bridge.primary_terminal_binding(
            primary, historical, primary["bridge_bundle_binding"]
        )
        secondary_start = legacy_coordinator.bank_consumer_start(
            historical, "SECONDARY", package_directory / "bridge-secondary-durable-start.json",
            primary_terminal_binding_sha256=primary_binding.sha256,
        )
        secondary_numerical = consumer_view(
            bridge, "SECONDARY_NUMERICAL",
            legacy_bridge.numerical_view(historical, "SECONDARY", primary_binding=primary_binding),
        )
        secondary_result = consumer_view(
            bridge, "SECONDARY_RESULT",
            legacy_bridge.result_bundle_view(historical, "SECONDARY", secondary_start.sha256),
        )
        secondary = execute_secondary(
            secondary_numerical, secondary_result, leases.inherited_fds(), secondary_directory
        )
        completed_phase = "SECONDARY_RESULT_TERMINAL"
        comparison_historical = legacy_bridge.comparison_view(
            historical, primary["bridge_bundle_binding"],
            secondary["bridge_bundle_binding"],
        )
        comparison_authority = consumer_view(bridge, "COMPARISON", comparison_historical)
        pa, sa = primary["artifacts"], secondary["artifacts"]
        comparison = derive_summary(
            primary_directory, pa["manifest"]["payloads"][2],
            secondary_directory, sa["manifest"]["payloads"][2],
            pa["routing"], sa["routing"], pa["manifest"], sa["manifest"],
            pa["top32"], sa["top32"], pa["receipt"], sa["receipt"],
            comparison_historical.get("authorization_id"),
        )
        validate_summary(
            comparison, primary_directory, pa["manifest"]["payloads"][2],
            secondary_directory, sa["manifest"]["payloads"][2],
            pa["routing"], sa["routing"], pa["manifest"], sa["manifest"],
            pa["top32"], sa["top32"], pa["receipt"], sa["receipt"],
            comparison_historical.get("authorization_id"),
        )
        comparison_binding, comparison_binding_sha = legacy_bridge.build_comparison_binding(
            comparison_historical, comparison
        )
        _bank(package_directory / "bridge-comparison-binding.json", comparison_binding.as_dict(), comparison_binding_sha)
    except Exception:
        release_report = leases.release()
        failure = {
            "schema": "pulsarmlx.f017.event06-v12-prompt-bound-consumer-failure/2.0.0",
            "bridge_sha256": bridge.sha256,
            "event_identity_plan_sha256": bridge.get("event_identity_plan_sha256"),
            "package_attempt_id": bridge.get("package_attempt_id"),
            "completed_phase": completed_phase, "release_report": release_report,
            "result": "TERMINAL_FAILURE",
        }
        _bank(package_directory / "prompt-bound-consumer-failure.json", failure, _sha(failure))
        raise

    release_historical = legacy_bridge.release_view(historical, comparison_binding)
    release_authority = consumer_view(bridge, "RELEASE", release_historical)
    release_report = leases.release()
    release_binding, release_binding_sha = legacy_bridge.build_release_binding(
        release_historical, release_report
    )
    _bank(package_directory / "bridge-release-report.json", release_report, _sha(release_report))
    _bank(package_directory / "bridge-release-binding.json", release_binding.as_dict(), release_binding_sha)
    accounting_historical = legacy_bridge.accounting_view(historical, release_binding)
    accounting_authority = consumer_view(bridge, "ACCOUNTING", accounting_historical)
    accounting_binding, accounting_binding_sha = legacy_bridge.build_accounting_binding(
        accounting_historical, release_binding
    )
    _bank(package_directory / "bridge-accounting-binding.json", accounting_binding.as_dict(), accounting_binding_sha)

    comparison_receipt = {
        "schema": "pulsarmlx.f017.event06-bridge-comparison-receipt/1.0.0",
        "bridge_sha256": historical.sha256,
        "comparison_binding_sha256": comparison_binding_sha,
        "comparison_summary_sha256": _sha(comparison), "result": "PASS",
    }
    comparison_terminal = {
        "schema": "pulsarmlx.f017.event06-bridge-comparison-terminal/1.0.0",
        "bridge_sha256": historical.sha256,
        "comparison_receipt_sha256": _sha(comparison_receipt), "result": "COMPLETE",
    }
    release_start = {
        "schema": "pulsarmlx.f017.event06-bridge-release-start/1.0.0",
        "bridge_sha256": historical.sha256, "release_view_sha256": release_historical.sha256,
        "expected_leases": 5,
    }
    release_receipt = {
        "schema": "pulsarmlx.f017.event06-bridge-release-receipt/1.0.0",
        "bridge_sha256": historical.sha256, "release_binding_sha256": release_binding_sha,
        "release_report_sha256": _sha(release_report), "result": "PASS",
    }
    release_terminal = {
        "schema": "pulsarmlx.f017.event06-bridge-release-terminal/1.0.0",
        "bridge_sha256": historical.sha256, "release_receipt_sha256": _sha(release_receipt),
        "live_leases": 0, "result": "COMPLETE",
    }
    package_receipt = {
        "schema": "pulsarmlx.f017.event06-bridge-package-receipt/1.0.0",
        "bridge_sha256": historical.sha256,
        "accounting_binding_sha256": accounting_binding_sha,
        "comparison_terminal_sha256": _sha(comparison_terminal),
        "release_terminal_sha256": _sha(release_terminal), "result": "PASS",
    }
    for name, value in (
        ("comparison-receipt", comparison_receipt), ("comparison-terminal", comparison_terminal),
        ("release-start", release_start), ("release-receipt", release_receipt),
        ("release-terminal", release_terminal), ("package-receipt", package_receipt),
    ):
        _bank(package_directory / f"bridge-{name}.json", value, _sha(value))
    v11_closure = closure_root(
        pa["manifest"], pa["receipt"], pa["consumer_terminal"],
        sa["manifest"], sa["receipt"], sa["consumer_terminal"],
        primary["index"]["result_terminal_sha256"], secondary["index"]["result_terminal_sha256"],
        _sha(comparison), _sha(comparison_receipt), _sha(comparison_terminal),
        _sha(release_start), _sha(release_report), _sha(release_receipt),
        _sha(release_terminal), _sha(package_receipt),
    )
    v11_closure_binding = legacy_bridge.bind_v11_closure(
        historical, v11_closure, accounting_binding
    )
    _bank(
        package_directory / "bridge-v11-closure-binding.json",
        v11_closure_binding.as_dict(), v11_closure_binding.sha256,
    )
    views = {
        "PRIMARY_NUMERICAL": primary_numerical, "PRIMARY_RESULT": primary_result,
        "SECONDARY_NUMERICAL": secondary_numerical, "SECONDARY_RESULT": secondary_result,
        "COMPARISON": comparison_authority, "RELEASE": release_authority,
        "ACCOUNTING": accounting_authority,
    }
    value = {
        "bridge_sha256": historical.sha256, "prompt_bound_bridge_sha256": bridge.sha256,
        "primary": primary, "secondary": secondary,
        "primary_start_sha256": primary_start.sha256,
        "secondary_start_sha256": secondary_start.sha256,
        "comparison": comparison, "comparison_view": comparison_historical,
        "comparison_binding": comparison_binding,
        "comparison_binding_sha256": comparison_binding_sha,
        "comparison_terminal": comparison_terminal, "release_report": release_report,
        "release_binding": release_binding, "release_binding_sha256": release_binding_sha,
        "release_terminal": release_terminal, "accounting_binding": accounting_binding,
        "accounting_binding_sha256": accounting_binding_sha, "v11_closure": v11_closure,
        "v11_closure_binding": v11_closure_binding,
        "v11_closure_sha256": _sha(v11_closure), "consumer_views": views, "result": "PASS",
    }
    return legacy_coordinator.ValidatedBridgeExecutionResult(
        legacy_coordinator._EXECUTION_RESULT_SEAL, value
    )


def execute_event06_bridge(
    candidate_path: Path,
    installed_path: Path,
    receipt_path: Path,
    *,
    package_attempt_id: str,
    package_start_path: Path,
    identity_evidence_directory: Path,
    execution_plan: ValidatedExecutionPlan,
    bridge_input: PromptBoundIdentityBridgeInputV2,
    primary_directory: Path,
    secondary_directory: Path,
    package_directory: Path,
    terminal_path: Path,
) -> dict[str, object]:
    """One fixed production entrypoint; accepts no identity mapping or adapter."""
    gate = legacy_coordinator.validate_package_start(candidate_path, installed_path, receipt_path)
    installed = gate["installed_authority"]
    validate_pre_package_bridge_input(bridge_input, installed, execution_plan)
    package_start = legacy_coordinator.bank_package_start(installed, package_start_path)
    leases, identity_report = legacy_coordinator.run_identity_stage(
        installed, package_attempt_id=package_attempt_id, package_durable_start=True,
        evidence_directory=identity_evidence_directory,
    )
    try:
        identity = legacy_bridge.bind_identity_stage(installed, leases, identity_report)
        bridge = derive_bridge(bridge_input, installed, identity, execution_plan)
    except Exception:
        package_directory.mkdir(parents=True, exist_ok=True)
        release_report = leases.release()
        failure = {
            "schema": "pulsarmlx.f017.event06-v12-prompt-bound-bridge-failure/2.0.0",
            "identity_bridge_input_sha256": bridge_input.sha256,
            "event_identity_plan_sha256": bridge_input.get("event_identity_plan_sha256"),
            "package_attempt_id": package_attempt_id, "completed_phase": "IDENTITY_TERMINAL",
            "release_report": release_report, "result": "TERMINAL_FAILURE",
        }
        _bank(package_directory / "prompt-bound-bridge-failure.json", failure, _sha(failure))
        raise
    execution = execute_consumers(
        bridge, leases, primary_directory, secondary_directory, package_directory
    )
    views = execution["consumer_views"]
    accounting, accounting_sha = build_accounting_closure(
        bridge, views["ACCOUNTING"], execution["accounting_binding"]
    )
    _bank(package_directory / "prompt-bound-accounting-closure.json", accounting.as_dict(), accounting_sha)
    legacy_package = legacy_coordinator.close_bridge_package(
        bridge.legacy_bridge, package_start, execution, terminal_path
    )
    historical_package_view = legacy_bridge.package_terminal_view(
        bridge.legacy_bridge, legacy_package["transition_chain"],
        execution["v11_closure_binding"], execution["accounting_binding"],
    )
    package_view = consumer_view(bridge, "PACKAGE_TERMINAL", historical_package_view)
    views["PACKAGE_TERMINAL"] = package_view
    terminal, terminal_sha = build_package_terminal(
        bridge, package_view, legacy_package["terminal"], accounting,
        package_directory / "prompt-bound-package-terminal.json",
    )
    for role, view in views.items():
        value = view.as_dict()
        _bank(package_directory / f"prompt-bound-{role.lower().replace('_', '-')}-view.json", value, view.sha256)
    return {
        "bridge_input": bridge_input, "bridge": bridge, "package_start": package_start,
        "identity_report": identity_report, "execution": execution,
        "legacy_package": legacy_package, "consumer_views": views,
        "accounting_closure": accounting, "accounting_closure_sha256": accounting_sha,
        "terminal": terminal, "terminal_sha256": terminal_sha, "result": "PASS",
    }
