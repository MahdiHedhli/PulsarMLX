#!/usr/bin/env python3
"""Complete Event 06 control-path composition with irreversible work interposed.

This module is qualification-only.  It uses the real collapsed-GO producers,
durable qualification installer, V12/V11 bridge, consumer views, accounting,
release, and package-terminal builders.  The original-checkpoint identity
operation and numerical kernels are replaced by sealed deterministic receipts;
no live resolver or production installation capability is imported here.
"""
from __future__ import annotations

import hashlib
import stat
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
from f017_descriptor_lease_manager_v10 import LeaseRecord, LeaseSet
from f017_event06_sequence14_fixture_v1 import build_sequence14_qualification
from f017_event06_numerical_bridge_v2 import (
    build_accounting_closure,
    build_package_terminal as build_prompt_bound_package_terminal,
    consumer_view,
    derive_bridge,
    historical_bridge,
    produce_identity_bridge_input,
)
import f017_event06_numerical_bridge_v1 as legacy
from f017_event06_package_attempt_registry_v2 import (
    claim_qualification_terminal_sinks, reserve_qualification_package_attempt,
)


EDGE_IDS = tuple(f"F017-DAG-{number:03d}" for number in range(1, 46))


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _synthetic_identity_stage(package: dict[str, object]):
    """Return a sealed identity receipt without resolving or opening a root."""
    plan = package["plan"]
    installed = package["installed"].authority
    package_id = plan.get("package_attempt_id")
    shards = plan.get("shards")
    descriptors = [
        {
            "device": 17,
            "inode": ordinal,
            "mode": stat.S_IFREG | 0o600,
            "size": shards[ordinal - 1]["size_bytes"],
            "mtime_ns": ordinal,
            "ctime_ns": ordinal,
            "shard_ordinal": ordinal,
            "role": "GRAPH_PAYLOAD",
            "lease_id": f"LEASE-{package_id}-{ordinal}",
        }
        for ordinal in range(2, 7)
    ]
    leases = LeaseSet(
        [LeaseRecord(identity, 10_000 + identity["shard_ordinal"]) for identity in descriptors],
        shards[0]["sha256"],
        [item["sha256"] for item in shards[1:]],
    )
    report = {
        "result": "PASS",
        "authority_scope": "SYNTHETIC_NON_AUTHORITY",
        "operation_class": "QUALIFICATION_IDENTITY_BOUNDARY_INTERPOSE",
        "generation": "V12",
        "ordered_shard_digests": [item["sha256"] for item in shards],
        "checkpoint_shard_opens": 6,
        "checkpoint_identity_hash_reads": 6,
        "retained_lease_count": 5,
        "identity_only_retained_count": 0,
        "descriptor_identities": descriptors,
        "path_reopen_count": 0,
        "evidence": {
            "access_journal_sha256": _sha({"synthetic_access": "INTERPOSED"}),
            "shard_receipts_sha256": _sha({"synthetic_shards": 6}),
            "lease_manifest_sha256": _sha(descriptors),
            "deterministic_core_sha256": _sha({"kernel": "NOT_RUN"}),
            "identity_manifest_sha256": _sha({"identity": "QUALIFICATION_ONLY"}),
            "identity_receipt_sha256": _sha({"receipt": "QUALIFICATION_ONLY"}),
            "identity_terminal_sha256": _sha({"terminal": "QUALIFICATION_ONLY"}),
            "identity_terminal_state": "COMPLETE",
        },
    }
    return legacy.bind_identity_stage(installed, leases, report), leases, report


def _synthetic_bundle(role: str, bridge: legacy.ValidatedNumericalBridge) -> dict[str, object]:
    """Construct an in-memory, non-installable synthetic consumer terminal."""
    manifest_sha = _sha({"role": role, "payloads": "INTERPOSED_NOT_BANKED"})
    receipt_sha = _sha({"role": role, "receipt": "QUALIFICATION_ONLY"})
    terminal_sha = _sha({"role": role, "terminal": "QUALIFICATION_ONLY"})
    terminal = {
        "schema": "pulsarmlx.f017.corrected-oracle-consumer-terminal/11.0.0",
        "role": role,
        "result": "COMPLETE",
        "result_terminal_sha256": terminal_sha,
        "result_receipt_sha256": receipt_sha,
        "payload_manifest_sha256": manifest_sha,
        "secondary_eligible": role == "PRIMARY",
    }
    index = {
        "schema": "pulsarmlx.f017.event06-v12-qualification-bundle-index/1.0.0",
        "role": role,
        "bridge_sha256": bridge.sha256,
        "manifest_sha256": manifest_sha,
        "result_receipt_sha256": receipt_sha,
        "result_terminal_sha256": terminal_sha,
        "qualification_only": True,
        "result": "PASS",
    }
    return {"artifacts": {"consumer_terminal": terminal}, "index": index, "result": "PASS"}


def _trace(trace: list[dict[str, object]], edge_id: str, value: object) -> object:
    digest = getattr(value, "source_sha256", getattr(value, "sha256", None))
    runtime_type = type(value).__name__
    if type(value) is tuple and all(hasattr(item, "sha256") for item in value):
        runtime_type = "tuple[" + ",".join(type(item).__name__ for item in value) + "]"
        digest = _sha([item.sha256 for item in value])
    if digest is None and type(value) in {dict, list}:
        digest = _sha(value)
    trace.append({"edge_id": edge_id, "runtime_type": runtime_type, "digest": digest})
    return value


def run_full_call_path(root: Path, *, retain_authorities: bool = False) -> dict[str, object]:
    """Run one deterministic complete control path without irreversible work."""
    package = build_sequence14_qualification(
        root, now_unix_ns=4_000_000_000_000_000_000
    )
    trace: list[dict[str, object]] = []
    # The public Sequence 14 composition produced and consumed the first twelve
    # authorities.  Rebind their exact runtime outputs into the derived trace.
    for edge_id, name in zip(
        EDGE_IDS[:12],
        (
            "readiness", "decision", "go", "plan", "approval", "preparation",
            "identity", "bundle", "prepared", "capability", "transaction", "installed",
        ),
        strict=True,
    ):
        _trace(trace, edge_id, package[name])

    identity_stage, leases, identity_report = _synthetic_identity_stage(package)
    _trace(trace, EDGE_IDS[12], package["installed"].authority)
    _trace(trace, EDGE_IDS[13], leases)
    bridge_input = produce_identity_bridge_input(
        package["identity"], package["installed"].authority, package["plan"]
    )
    _trace(trace, EDGE_IDS[14], package["identity"])
    _trace(trace, EDGE_IDS[15], package["installed"].authority)
    _trace(trace, EDGE_IDS[16], package["plan"])
    bridge = derive_bridge(
        bridge_input, package["installed"].authority, identity_stage, package["plan"]
    )
    historical = historical_bridge(bridge)
    _trace(trace, EDGE_IDS[17], bridge_input)
    _trace(trace, EDGE_IDS[18], identity_stage)

    primary_numerical_legacy = legacy.numerical_view(historical, "PRIMARY")
    _trace(trace, EDGE_IDS[19], historical)
    primary_numerical = consumer_view(
        bridge, "PRIMARY_NUMERICAL", primary_numerical_legacy
    )
    _trace(trace, EDGE_IDS[20], primary_numerical_legacy)
    primary_result_legacy = legacy.result_bundle_view(
        historical, "PRIMARY", _sha({"primary": "DURABLE_SYNTHETIC_START"})
    )
    _trace(trace, EDGE_IDS[21], historical)
    primary_result = consumer_view(bridge, "PRIMARY_RESULT", primary_result_legacy)
    _trace(trace, EDGE_IDS[22], primary_result_legacy)
    primary_bundle = _synthetic_bundle("PRIMARY", historical)
    primary_bundle_binding, primary_bundle_binding_sha = legacy.build_bundle_binding(
        primary_numerical_legacy, primary_result_legacy, primary_bundle["index"],
        "QUALIFICATION_ONLY",
    )
    primary_terminal_binding = legacy.primary_terminal_binding(
        primary_bundle, historical, primary_bundle_binding
    )
    _trace(trace, EDGE_IDS[23], primary_bundle)

    secondary_numerical_legacy = legacy.numerical_view(
        historical, "SECONDARY", primary_binding=primary_terminal_binding
    )
    _trace(trace, EDGE_IDS[24], primary_terminal_binding)
    secondary_numerical = consumer_view(
        bridge, "SECONDARY_NUMERICAL", secondary_numerical_legacy
    )
    _trace(trace, EDGE_IDS[25], secondary_numerical_legacy)
    secondary_result_legacy = legacy.result_bundle_view(
        historical, "SECONDARY", _sha({"secondary": "DURABLE_SYNTHETIC_START"})
    )
    secondary_result = consumer_view(bridge, "SECONDARY_RESULT", secondary_result_legacy)
    _trace(trace, EDGE_IDS[26], secondary_result_legacy)
    secondary_bundle = _synthetic_bundle("SECONDARY", historical)
    secondary_bundle_binding, secondary_bundle_binding_sha = legacy.build_bundle_binding(
        secondary_numerical_legacy, secondary_result_legacy, secondary_bundle["index"],
        "QUALIFICATION_ONLY",
    )

    comparison_legacy = legacy.comparison_view(
        historical, primary_bundle_binding, secondary_bundle_binding
    )
    _trace(trace, EDGE_IDS[27], (primary_bundle_binding, secondary_bundle_binding))
    comparison = consumer_view(bridge, "COMPARISON", comparison_legacy)
    _trace(trace, EDGE_IDS[28], comparison_legacy)
    comparison_summary = {
        "schema": "pulsarmlx.f017.corrected-oracle-binary-comparison-summary/11.0.0",
        "authorization_id": bridge.get("authorization_id"),
        "package_attempt_id": bridge.get("package_attempt_id"),
        "classification": "NUMERICALLY_STABLE_TOP_K_ONLY",
        "qualification_only": True,
    }
    comparison_binding, comparison_binding_sha = legacy.build_comparison_binding(
        comparison_legacy, comparison_summary
    )
    release_legacy = legacy.release_view(historical, comparison_binding)
    _trace(trace, EDGE_IDS[29], comparison_binding)
    release = consumer_view(bridge, "RELEASE", release_legacy)
    close_event = lambda event: _sha({"qualification_close_event": event})
    release_report = leases.release(
        close_function=lambda _descriptor, _lease_id: None,
        event_function=close_event,
    )
    _trace(trace, EDGE_IDS[30], release_report)
    release_binding, release_binding_sha = legacy.build_release_binding(
        release_legacy, release_report
    )
    accounting_legacy = legacy.accounting_view(historical, release_binding)
    _trace(trace, EDGE_IDS[31], release_binding)
    accounting = consumer_view(bridge, "ACCOUNTING", accounting_legacy)
    legacy_accounting_binding, legacy_accounting_sha = legacy.build_accounting_binding(
        accounting_legacy, release_binding
    )
    _trace(trace, EDGE_IDS[32], accounting_legacy)
    accounting_closure, accounting_closure_sha = build_accounting_closure(
        bridge, accounting, legacy_accounting_binding
    )
    _trace(trace, EDGE_IDS[33], legacy_accounting_binding)

    predecessor = "0" * 64
    transitions: list[dict[str, object]] = []
    for phase in legacy.PHASES:
        transition, predecessor = legacy.build_transition_binding(
            historical,
            phase,
            "QUALIFICATION_ONLY_SYNTHETIC_RECEIPT",
            _sha({"phase": phase, "authority_mode": "QUALIFICATION_ONLY"}),
            predecessor,
        )
        transitions.append(transition)
    transition_chain = legacy.validate_transition_chain(historical, transitions)
    v11_closure = {
        "schema": "pulsarmlx.f017.corrected-oracle-package-result-closure/11.0.0",
        "primary": {
            "manifest_sha256": primary_bundle["index"]["manifest_sha256"],
            "receipt_sha256": primary_bundle["index"]["result_receipt_sha256"],
            "terminal_sha256": _sha(primary_bundle["artifacts"]["consumer_terminal"]),
            "result_terminal_sha256": primary_bundle["index"]["result_terminal_sha256"],
            "routing_manifest_sha256": _sha({"role": "PRIMARY", "routing": "INTERPOSED"}),
            "payload_sha256s": [_sha({"role": "PRIMARY", "payload": index}) for index in range(3)],
        },
        "secondary": {
            "manifest_sha256": secondary_bundle["index"]["manifest_sha256"],
            "receipt_sha256": secondary_bundle["index"]["result_receipt_sha256"],
            "terminal_sha256": _sha(secondary_bundle["artifacts"]["consumer_terminal"]),
            "result_terminal_sha256": secondary_bundle["index"]["result_terminal_sha256"],
            "routing_manifest_sha256": _sha({"role": "SECONDARY", "routing": "INTERPOSED"}),
            "payload_sha256s": [_sha({"role": "SECONDARY", "payload": index}) for index in range(3)],
        },
        "comparison": {
            "summary_sha256": comparison_binding.get("comparison_summary_sha256"),
            "receipt_sha256": _sha({"comparison": "QUALIFICATION_RECEIPT"}),
            "terminal_sha256": _sha({"comparison": "QUALIFICATION_TERMINAL"}),
        },
        "release": {
            "start_sha256": _sha({"release": "QUALIFICATION_START"}),
            "report_sha256": release_binding.get("release_report_sha256"),
            "receipt_sha256": _sha({"release": "QUALIFICATION_RECEIPT"}),
            "terminal_sha256": _sha({"release": "QUALIFICATION_TERMINAL"}),
        },
        "package_receipt_sha256": _sha({"package": "QUALIFICATION_RECEIPT"}),
        "payload_count": 6,
        "result": "COMPLETE",
    }
    v11_closure_binding = legacy.bind_v11_closure(
        historical, v11_closure, legacy_accounting_binding
    )
    package_legacy_view = legacy.package_terminal_view(
        historical, transition_chain, v11_closure_binding, legacy_accounting_binding,
    )
    _trace(trace, EDGE_IDS[34], package_legacy_view)
    package_view = consumer_view(bridge, "PACKAGE_TERMINAL", package_legacy_view)
    package_reservation = reserve_qualification_package_attempt(
        package["installed"], root / "package-attempt-registry",
    )
    _trace(trace, EDGE_IDS[35], package["installed"].authority)
    _trace(trace, EDGE_IDS[36], package_reservation)
    _trace(trace, EDGE_IDS[37], package_legacy_view)
    terminal_sinks = claim_qualification_terminal_sinks(
        package_reservation, historical, package_legacy_view
    )
    legacy_terminal_sink, successor_terminal_sink = terminal_sinks
    _trace(trace, EDGE_IDS[38], legacy_terminal_sink)
    _trace(trace, EDGE_IDS[39], successor_terminal_sink)
    legacy_terminal, legacy_terminal_sha = legacy.build_package_terminal(
        package_legacy_view, historical, legacy_terminal_sink
    )
    _trace(trace, EDGE_IDS[40], package_view)
    _trace(trace, EDGE_IDS[41], accounting_closure)
    _trace(trace, EDGE_IDS[42], primary_bundle_binding)
    _trace(trace, EDGE_IDS[43], transition_chain)
    _trace(trace, EDGE_IDS[44], v11_closure_binding)
    package_terminal, package_terminal_sha = build_prompt_bound_package_terminal(
        bridge, package_view, legacy_terminal, accounting_closure,
        successor_terminal_sink,
    )
    from execute_f017_corrected_oracle_event_v12_bridge import (
        ValidatedBridgeExecutionResult, _EXECUTION_RESULT_SEAL,
    )
    execution_result = ValidatedBridgeExecutionResult(
        _EXECUTION_RESULT_SEAL,
        {
            "bridge_sha256": historical.sha256,
            "primary": primary_bundle,
            "secondary": secondary_bundle,
            "primary_start_sha256": primary_result_legacy.get("durable_start_sha256"),
            "secondary_start_sha256": secondary_result_legacy.get("durable_start_sha256"),
            "comparison_terminal": {
                "schema": "pulsarmlx.f017.event06-v12-qualification-comparison-terminal/1.0.0",
                "result": "COMPLETE",
            },
            "release_terminal": {
                "schema": "pulsarmlx.f017.event06-v12-qualification-release-terminal/1.0.0",
                "result": "COMPLETE",
            },
            "accounting_binding": legacy_accounting_binding,
            "accounting_binding_sha256": legacy_accounting_sha,
            "v11_closure_binding": v11_closure_binding,
            "v11_closure_sha256": _sha(v11_closure),
            "result": "PASS",
        },
    )

    counters = package["state"].snapshot()
    live_zero = {
        name: counters[name]
        for name in (
            "canonical_live_reservations", "live_checkpoint_root_resolutions",
            "live_installation_commit_calls", "live_authorities_or_capabilities",
            "package_starts", "original_checkpoint_shard_opens",
            "original_checkpoint_identity_hash_reads",
            "original_checkpoint_payload_reads",
            "original_checkpoint_mmaps_or_tensor_reads", "numerical_operations",
            "event06_identities_instantiated", "event06_identities_consumed",
            "authorization_delta", "package_delta", "primary_delta",
            "secondary_delta", "p1_actions",
        )
    }
    result = {
        "schema": "pulsarmlx.f017.event06-v12-full-call-path-no-access/1.0.0",
        "authority_mode": "QUALIFICATION_ONLY",
        "dag_edges_traversed": [item["edge_id"] for item in trace],
        "trace": trace,
        "identity_report": identity_report,
        "primary_receipt": primary_bundle["index"],
        "secondary_receipt": secondary_bundle["index"],
        "comparison_receipt": comparison_binding.as_dict(),
        "comparison_binding_sha256": comparison_binding_sha,
        "release_receipt": release_binding.as_dict(),
        "release_binding_sha256": release_binding_sha,
        "accounting_receipt": accounting_closure.as_dict(),
        "legacy_accounting_binding_sha256": legacy_accounting_sha,
        "package_terminal": package_terminal,
        "package_terminal_sha256": package_terminal_sha,
        "legacy_package_terminal_sha256": legacy_terminal_sha,
        "synthetic_accounting": {"package": 1, "primary": 1, "secondary": 1},
        "live_accounting": {"authorization": 0, "package": 0, "primary": 0, "secondary": 0},
        "live_counters": live_zero,
        "historical_master_ledger": 175,
        "original_checkpoint_root_resolved": False,
        "full_model_inference": "NONE",
        "result": "PASS",
    }
    if len(trace) != len(EDGE_IDS) or set(result["dag_edges_traversed"]) != set(EDGE_IDS):
        raise AssertionError("complete DAG traversal")
    if any(live_zero.values()) or not leases.closed:
        raise AssertionError("no-access and release closure")
    result["aggregate_sha256"] = _sha({
        "authority_mode": result["authority_mode"],
        "dag_edges_traversed": result["dag_edges_traversed"],
        "runtime_types": [item["runtime_type"] for item in trace],
        "stable_preinstallation_edge_digests": [item["digest"] for item in trace[:7]],
        "authority_invariant_bindings": {
            "event_identity_plan_sha256": bridge.get("event_identity_plan_sha256"),
            "preparation_sha256": bridge.get("preparation_sha256"),
            "collapsed_go_sha256": bridge.get("collapsed_go_sha256"),
            "prompt_sha256": bridge.get("prompt_sha256"),
            "checkpoint_set_sha256": historical.get("checkpoint_set_sha256"),
            "execution_plan_sha256": historical.get("execution_plan_sha256"),
            "numerical_contract_sha256": historical.get("numerical_contract_sha256"),
            "result_authority_sha256": historical.get("result_authority_sha256"),
            "primary_bundle_role": primary_bundle_binding.get("role"),
            "secondary_bundle_role": secondary_bundle_binding.get("role"),
            "transition_phases": [record["phase"] for record in transitions],
            "accounting_result": legacy_accounting_binding.get("result"),
            "package_terminal_result": package_terminal["result"],
        },
        "synthetic_accounting": result["synthetic_accounting"],
        "live_accounting": result["live_accounting"],
        "live_counters": result["live_counters"],
        "historical_master_ledger": 175,
        "original_checkpoint_root_resolved": False,
        "full_model_inference": "NONE",
        "package_terminal_result": package_terminal["result"],
    })
    if retain_authorities:
        result["_authorities"] = {
            "bridge": bridge,
            "historical_bridge": historical,
            "bridge_input": bridge_input,
            "installed_authority": package["installed"].authority,
            "identity_stage": identity_stage,
            "execution_plan": package["plan"],
            "primary_numerical_view": primary_numerical_legacy,
            "primary_result_view": primary_result_legacy,
            "primary_bundle_index": primary_bundle["index"],
            "secondary_numerical_view": secondary_numerical_legacy,
            "secondary_result_view": secondary_result_legacy,
            "primary_bundle_binding": primary_bundle_binding,
            "secondary_bundle_binding": secondary_bundle_binding,
            "comparison_binding": comparison_binding,
            "release_binding": release_binding,
            "accounting_binding": legacy_accounting_binding,
            "accounting_closure": accounting_closure,
            "transition_chain": transition_chain,
            "v11_closure_binding": v11_closure_binding,
            "package_view": package_view,
            "legacy_terminal": legacy_terminal,
            "legacy_terminal_sink": legacy_terminal_sink,
            "successor_terminal_sink": successor_terminal_sink,
            "execution_result": execution_result,
        }
    return result


__all__ = ["EDGE_IDS", "run_full_call_path"]
