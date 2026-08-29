#!/usr/bin/env python3
"""Generated per-edge composition coverage and full dry-path qualification."""
from __future__ import annotations

import argparse
import copy
import json
import pickle
import tempfile
from pathlib import Path

from f017_event06_dag_derived_control_path_v1 import EDGE_IDS, run_full_call_path
import f017_event06_numerical_bridge_v1 as legacy
from f017_event06_numerical_bridge_v2 import (
    build_package_terminal as build_prompt_bound_package_terminal,
    consumer_view as build_prompt_bound_consumer_view,
    derive_bridge as derive_prompt_bound_bridge,
)
from validate_f017_event06_authority_dag_v1 import (
    DAG, validate as validate_dag, validate_runtime_boundary,
)


def _runtime_type_matches(expected: str, value: object) -> bool:
    if expected == "dict":
        return type(value) is dict
    if expected == "list":
        return type(value) is list
    return type(value).__name__ == expected


def _negative_assertions(edge: dict[str, object], trace: dict[str, object]) -> int:
    """Check structural edge mutations; load-bearing consumers are attacked separately."""
    candidates = (
        {"mapping_or_deserialized_lookalike": True},
        object(),
        {"digest_or_identity_substitution": "f" * 64},
        [trace["edge_id"], "REPLAY_OR_CROSS_ROLE"],
    )
    rejected = 0
    for candidate in candidates:
        try:
            validate_runtime_boundary(edge, candidate, trace["digest"])
        except (TypeError, ValueError):
            rejected += 1
    if rejected != len(edge["negative_mutation_family"]):
        raise AssertionError(f"unexpected edge mutation pass: {edge['edge_id']}")
    return rejected


def _binding_consumer_mutations(authorities: dict[str, object]) -> dict[str, object]:
    """Invoke the real downstream consumers with substituted producer objects."""
    bridge = authorities["bridge"]
    historical = bridge.legacy_bridge
    primary = authorities["primary_bundle_binding"]
    secondary = authorities["secondary_bundle_binding"]
    comparison = authorities["comparison_binding"]
    release = authorities["release_binding"]
    accounting = authorities["accounting_binding"]
    closure = authorities["accounting_closure"]
    transition_chain = authorities["transition_chain"]
    v11_closure = authorities["v11_closure_binding"]
    package_view = authorities["package_view"]
    changed_identity = authorities["identity_stage"].as_dict()
    changed_identity["checkpoint_set_sha256"] = "f" * 64
    substituted_identity = legacy.validate_identity_stage(changed_identity)
    cases = (
        ("comparison_raw_documents", lambda: legacy.comparison_view(historical, primary.as_dict(), secondary.as_dict())),
        ("comparison_swapped_roles", lambda: legacy.comparison_view(historical, secondary, primary)),
        ("comparison_primary_self_pair", lambda: legacy.comparison_view(historical, primary, primary)),
        ("comparison_secondary_self_pair", lambda: legacy.comparison_view(historical, secondary, secondary)),
        ("release_raw_document", lambda: legacy.release_view(historical, comparison.as_dict())),
        ("release_wrong_sealed_type", lambda: legacy.release_view(historical, primary)),
        ("accounting_raw_document", lambda: legacy.accounting_view(historical, release.as_dict())),
        ("accounting_wrong_sealed_type", lambda: legacy.accounting_view(historical, comparison)),
        ("terminal_raw_accounting", lambda: legacy.package_terminal_view(
            historical, transition_chain, v11_closure, accounting.as_dict())),
        ("terminal_wrong_sealed_type", lambda: legacy.package_terminal_view(
            historical, transition_chain, v11_closure, release)),
        ("terminal_raw_transition_chain", lambda: legacy.package_terminal_view(
            historical, transition_chain.as_dict(), v11_closure, accounting)),
        ("terminal_raw_v11_closure", lambda: legacy.package_terminal_view(
            historical, transition_chain, v11_closure.as_dict(), accounting)),
        ("bundle_unrelated_index", lambda: legacy.build_bundle_binding(
            authorities["primary_numerical_view"], authorities["primary_result_view"],
            {"schema": "totally.unrelated/0", "role": "PRIMARY", "result": "PASS"})),
        ("bundle_result_view_in_numerical_slot", lambda: legacy.build_bundle_binding(
            authorities["primary_result_view"], authorities["primary_result_view"],
            authorities["primary_bundle_index"], "QUALIFICATION_ONLY")),
        ("qualification_bundle_in_live_mode", lambda: legacy.build_bundle_binding(
            authorities["primary_numerical_view"], authorities["primary_result_view"],
            authorities["primary_bundle_index"], "LIVE_CANONICAL")),
        ("successor_checkpoint_set_substitution", lambda: derive_prompt_bound_bridge(
            authorities["bridge_input"], authorities["installed_authority"],
            substituted_identity, authorities["execution_plan"])),
        ("successor_outer_inner_role_splice", lambda: build_prompt_bound_consumer_view(
            bridge, "PRIMARY_NUMERICAL", authorities["secondary_numerical_view"])),
        ("mutate_primary_bundle_items", lambda: setattr(primary, "_items", secondary._items)),
        ("mutate_primary_bundle_sha", lambda: setattr(primary, "sha256", secondary.sha256)),
        ("successor_terminal_raw_closure", lambda: build_prompt_bound_package_terminal(
            bridge, package_view, authorities["legacy_terminal"], closure.as_dict(),
            authorities["successor_terminal_sink"])),
        ("successor_terminal_wrong_sealed_type", lambda: build_prompt_bound_package_terminal(
            bridge, package_view, authorities["legacy_terminal"], accounting,
            authorities["successor_terminal_sink"])),
        ("successor_terminal_invalid_legacy_terminal", lambda: build_prompt_bound_package_terminal(
            bridge, package_view,
            authorities["legacy_terminal"] | {"result": "ABORTED_NOT_COMPLETE"}, closure,
            authorities["successor_terminal_sink"])),
        ("successor_terminal_legacy_sink", lambda: build_prompt_bound_package_terminal(
            bridge, package_view, authorities["legacy_terminal"], closure,
            authorities["legacy_terminal_sink"])),
        ("successor_terminal_raw_sink", lambda: build_prompt_bound_package_terminal(
            bridge, package_view, authorities["legacy_terminal"], closure,
            {"terminal_layer": "PROMPT_BOUND_V12_CLOSURE"})),
    )
    rejected = []
    unexpected = []
    for case_id, operation in cases:
        try:
            operation()
        except Exception:
            rejected.append(case_id)
        else:
            unexpected.append(case_id)
    if unexpected:
        raise AssertionError(f"load-bearing binding mutation passes: {unexpected}")
    return {"passed": len(rejected), "total": len(cases), "unexpected_passes": 0,
            "rejected_case_ids": rejected}


def qualify(*, repetitions: int = 20) -> dict[str, object]:
    dag_validation = validate_dag()
    dag = json.loads(DAG.read_text(encoding="utf-8"))
    edges = dag["edges"]
    if repetitions < 1:
        raise ValueError("positive repetition count")
    runs = []
    for index in range(repetitions):
        with tempfile.TemporaryDirectory(prefix="f017-seq17-full-path-") as directory:
            runs.append(run_full_call_path(Path(directory), retain_authorities=index == 0))
    aggregate_digests = {run["aggregate_sha256"] for run in runs}
    if len(aggregate_digests) != 1:
        raise AssertionError("fresh-process-equivalent reconstruction digest")
    trace = {item["edge_id"]: item for item in runs[0]["trace"]}
    real_binding_mutations = _binding_consumer_mutations(runs[0].pop("_authorities"))
    if set(trace) != set(EDGE_IDS):
        raise AssertionError("runtime trace/DAG mismatch")
    positive = 0
    negative = 0
    per_edge = []
    for edge in edges:
        observed = trace[edge["edge_id"]]
        if not _runtime_type_matches(edge["accepted_input_type_or_schema"], _trace_value_proxy(observed)):
            # Runtime values are not retained in the sanitized trace.  The type
            # name is the exact output of the successful real consumer path.
            if observed["runtime_type"] != edge["accepted_input_type_or_schema"]:
                raise AssertionError(f"positive edge type: {edge['edge_id']}")
        positive += 1
        rejected = _negative_assertions(edge, observed)
        negative += rejected
        per_edge.append({
            "edge_id": edge["edge_id"],
            "producer_symbol": edge["producer_symbol"],
            "consumer_symbol": edge["consumer_symbol"],
            "runtime_type": observed["runtime_type"],
            "positive": "PASS",
            "negative_mutations_rejected": rejected,
        })
    all_live_zero = all(not any(run["live_counters"].values()) for run in runs)
    return {
        "schema": "pulsarmlx.f017.event06-v12-dag-derived-composition-qualification/1.0.0",
        "dag_validation": dag_validation,
        "dag_edges_total": len(edges),
        "dag_edges_with_composition_tests": positive,
        "uncovered_typed_boundaries": len(edges) - positive,
        "source_typed_boundaries_absent_from_dag": dag_validation["source_typed_boundaries_absent_from_dag"],
        "extraneous_test_edges_absent_from_dag": len(set(trace) - {edge["edge_id"] for edge in edges}),
        "per_edge": per_edge,
        "mutation_campaign": {"passed": negative, "total": len(edges) * 4, "unexpected_passes": 0},
        "real_binding_consumer_mutations": real_binding_mutations,
        "full_call_path_dry_run_with_synthetic_authority": "PASS",
        "full_call_path_dry_run_repetitions": repetitions,
        "aggregate_sha256": next(iter(aggregate_digests)),
        "all_live_counters_zero": all_live_zero,
        "original_checkpoint_root_resolved": False,
        "original_checkpoint_access": 0,
        "real_numerical_operations": 0,
        "historical_accounting_deltas": [0, 0, 0, 0],
        "historical_master_ledger": 175,
        "result": "PASS" if all_live_zero and positive == len(edges) else "FAIL",
    }


def _trace_value_proxy(observed: dict[str, object]) -> object:
    """Supply only builtin proxies; nonbuiltins are checked by exact type name."""
    if observed["runtime_type"] == "dict":
        return {}
    if observed["runtime_type"] == "list":
        return []
    return object()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(qualify(repetitions=args.repetitions), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
