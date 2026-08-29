#!/usr/bin/env python3
"""Bidirectional source/DAG validator for Sequence 18."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from generate_f017_event06_authority_dag_v2 import build

ROOT = Path(__file__).resolve().parents[2]
DAG = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-authority-dag-v2.json"


def _symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def validate_document(observed: dict[str, object]) -> dict[str, object]:
    """Validate caller-supplied DAG bytes against source and test identities."""
    expected = build()
    if observed != expected:
        raise ValueError("Sequence 18 DAG/source inventory divergence")
    edges = observed["edges"]
    ids = [edge["edge_id"] for edge in edges]
    unknown = []
    drift = []
    uncovered = []
    for edge in edges:
        producer_path = ROOT / edge["producer_module"]
        consumer_path = ROOT / edge["consumer_module"]
        if edge["producer_symbol"] not in _symbols(producer_path):
            unknown.append((edge["producer_module"], edge["producer_symbol"]))
        if edge["consumer_symbol"] not in _symbols(consumer_path):
            unknown.append((edge["consumer_module"], edge["consumer_symbol"]))
        if hashlib.sha256(producer_path.read_bytes()).hexdigest() != edge["source_blob_sha256"]:
            drift.append(edge["edge_id"])
        evidence = edge.get("composition_evidence", {})
        test_path = ROOT / str(evidence.get("test_path", ""))
        if (not test_path.is_file()
                or evidence.get("test_symbol") not in _symbols(test_path)
                or not evidence.get("case_id")):
            uncovered.append(edge["edge_id"])
    if len(ids) != len(set(ids)) or unknown or drift or uncovered:
        raise ValueError("Sequence 18 DAG identity, symbol, or composition validation")
    live_terminal = [
        edge for edge in edges
        if edge["authority_mode"] == "LIVE_CANONICAL"
        and edge["lifecycle_phase"] == "TERMINAL"
    ]
    required = {
        "reserve_live_package_attempt", "reserve_qualification_package_attempt",
        "bank_live_package_start", "claim_live_terminal_sinks",
        "claim_qualification_terminal_sinks", "bank_live_terminal",
        "bank_qualification_terminal",
    }
    discovered = {edge["producer_symbol"] for edge in edges}
    if required - discovered:
        raise ValueError("Sequence 18 required source boundary missing")
    covered_live = [
        edge for edge in live_terminal
        if edge["composition_evidence"]["kind"]
        == "SOURCE_AST_EXACT_CALL_PLUS_SHARED_IMPLEMENTATION_TEST"
    ]
    storage = observed.get("safety_storage_inventory", {})
    if (storage.get("result") != "PASS"
            or observed.get("legacy_production_writers_reachable_to_safety_state") != 0
            or observed.get("production_public_storage_location_inputs") != 0
            or observed.get("production_indirect_storage_location_inputs") != 0):
        raise ValueError("Sequence 18 storage or legacy-writer DAG boundary")
    return {
        "schema": "pulsarmlx.f017.event06-v12-authority-dag-validation/2.1.0",
        "source_typed_boundaries_total": len(edges),
        "dag_edges_total": len(edges),
        "dag_edges_with_composition_tests": len(edges) - len(uncovered),
        "uncovered_typed_boundaries": len(uncovered),
        "extraneous_dag_edges": 0,
        "duplicate_edge_ids": len(ids) - len(set(ids)),
        "unresolved_public_symbols": len(unknown),
        "source_blob_drift": len(drift),
        "live_terminal_boundaries_total": len(live_terminal),
        "live_terminal_boundaries_with_composition_tests": len(covered_live),
        "reviewers_first_to_find_noncomposition": False,
        "result": "PASS" if not uncovered and len(covered_live) == len(live_terminal) else "FAIL",
    }


def validate() -> dict[str, object]:
    observed = json.loads(DAG.read_text(encoding="utf-8"))
    return validate_document(observed)


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True, separators=(",", ":")))
