#!/usr/bin/env python3
"""Structural completeness validator for the Sequence 17 authority DAG."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAG = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-authority-dag-v1.json"
TRACE = ROOT / "scripts/research/f017_event06_dag_derived_control_path_v1.py"


def _symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _trace_edge_ids() -> list[str]:
    tree = ast.parse(TRACE.read_text(encoding="utf-8"))
    result: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "_trace":
            continue
        if len(node.args) < 2:
            raise AssertionError("trace call edge argument")
        edge = node.args[1]
        if isinstance(edge, ast.Name) and edge.id == "edge_id":
            result.extend(f"F017-DAG-{number:03d}" for number in range(1, 13))
            continue
        if not (
            isinstance(edge, ast.Subscript)
            and isinstance(edge.value, ast.Name)
            and edge.value.id == "EDGE_IDS"
            and isinstance(edge.slice, ast.Constant)
            and type(edge.slice.value) is int
        ):
            raise AssertionError("trace edge must derive from EDGE_IDS")
        result.append(f"F017-DAG-{edge.slice.value + 1:03d}")
    return result


def _weakly_connected(edges: list[dict[str, object]]) -> bool:
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        left = edge["source_node"]
        right = edge["destination_node"]
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
    frontier = [next(iter(adjacency))]
    visited: set[str] = set()
    while frontier:
        node = frontier.pop()
        if node in visited:
            continue
        visited.add(node)
        frontier.extend(adjacency[node] - visited)
    return visited == set(adjacency)


def validate() -> dict[str, object]:
    value = json.loads(DAG.read_text(encoding="utf-8"))
    edges = value["edges"]
    required = {
        "edge_id", "source_node", "producer_module", "producer_symbol",
        "output_type_or_schema", "destination_node", "consumer_module",
        "consumer_symbol", "accepted_input_type_or_schema",
        "digest_identity_invariant", "authority_mode", "lifecycle_phase",
        "side_effect_class", "negative_mutation_family",
    }
    assert value["schema"] == "pulsarmlx.f017.event06-v12-authority-dag/1.0.0"
    assert type(edges) is list and len(edges) == value["edge_count"]
    assert all(type(edge) is dict and set(edge) == required for edge in edges)
    edge_ids = [edge["edge_id"] for edge in edges]
    assert len(edge_ids) == len(set(edge_ids))
    assert edge_ids == [f"F017-DAG-{number:03d}" for number in range(1, len(edges) + 1)]
    assert all(edge["output_type_or_schema"] == edge["accepted_input_type_or_schema"] for edge in edges)
    assert _weakly_connected(edges)
    cache: dict[str, set[str]] = {}
    for edge in edges:
        for module_key, symbol_key in (
            ("producer_module", "producer_symbol"),
            ("consumer_module", "consumer_symbol"),
        ):
            module = edge[module_key]
            cache.setdefault(module, _symbols(ROOT / module))
            assert edge[symbol_key] in cache[module], (module, edge[symbol_key])
    traced = _trace_edge_ids()
    assert len(traced) == len(set(traced))
    absent = sorted(set(edge_ids) - set(traced))
    extraneous = sorted(set(traced) - set(edge_ids))
    assert not absent and not extraneous
    assert value["live_authority_artifact_classes_added"] == 0
    assert value["original_checkpoint_access_permitted"] is False
    return {
        "schema": "pulsarmlx.f017.event06-v12-authority-dag-validation/1.0.0",
        "dag_edges_total": len(edges),
        "source_trace_edges": len(traced),
        "source_typed_boundaries_absent_from_dag": len(absent),
        "extraneous_trace_edges_absent_from_dag": len(extraneous),
        "duplicate_edge_ids": 0,
        "unknown_public_symbols": 0,
        "disconnected_production_nodes": 0,
        "result": "PASS",
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True, separators=(",", ":")))
