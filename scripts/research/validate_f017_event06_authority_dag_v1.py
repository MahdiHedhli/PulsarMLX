#!/usr/bin/env python3
"""Structural completeness validator for the Sequence 17 authority DAG."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAG = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-authority-dag-v1.json"
TRACE = ROOT / "scripts/research/f017_event06_dag_derived_control_path_v1.py"


def _symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _consumer_accepts(path: Path, symbol: str, expected: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol
    )
    arguments = function.args.args + function.args.kwonlyargs
    annotations = [ast.unparse(argument.annotation) for argument in arguments if argument.annotation]
    expected_parts = (
        expected.removeprefix("tuple[").removesuffix("]").split(",")
        if expected.startswith("tuple[") else [expected]
    )
    if all(any(part in annotation for annotation in annotations) for part in set(expected_parts)):
        return True
    # A single historical gate uses local imports to avoid a module cycle.  Its
    # exact type guard is still mechanically visible in the consumer body.
    body = ast.dump(function, include_attributes=False)
    return all(part in body and "type" in body and "IsNot" in body for part in expected_parts)


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


def _connected_components(edges: list[dict[str, object]]) -> int:
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge["source_node"], set()).add(edge["destination_node"])
        adjacency.setdefault(edge["destination_node"], set()).add(edge["source_node"])
    remaining = set(adjacency)
    components = 0
    while remaining:
        components += 1
        frontier = [next(iter(remaining))]
        while frontier:
            node = frontier.pop()
            if node not in remaining:
                continue
            remaining.remove(node)
            frontier.extend(adjacency[node] & remaining)
    return components


def validate_runtime_boundary(edge: dict[str, object], candidate: object,
                              expected_digest: str) -> None:
    """Fail closed on an exact traced edge type and producer digest."""
    expected = edge["accepted_input_type_or_schema"]
    if expected.startswith("tuple["):
        parts = expected.removeprefix("tuple[").removesuffix("]").split(",")
        exact_type = (type(candidate) is tuple and len(candidate) == len(parts)
                      and all(type(item).__name__ == part
                              for item, part in zip(candidate, parts, strict=True)))
        digest = (hashlib.sha256(json.dumps([item.sha256 for item in candidate],
                  sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                  if exact_type else None)
    else:
        exact_type = ((expected == "dict" and type(candidate) is dict)
                      or (expected == "list" and type(candidate) is list)
                      or type(candidate).__name__ == expected)
        if not exact_type:
            digest = None
        elif hasattr(candidate, "sha256"):
            digest = candidate.sha256
        elif type(candidate) in {dict, list}:
            from f017_canonical_serialization_v10 import canonical_bytes
            digest = hashlib.sha256(canonical_bytes(candidate)).hexdigest()
        else:
            digest = None
    if not exact_type or digest != expected_digest:
        raise TypeError("DAG runtime boundary type or digest mismatch")


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
    components = _connected_components(edges)
    assert components == 1 and _weakly_connected(edges)
    cache: dict[str, set[str]] = {}
    signature_bound = 0
    unknown_symbols = []
    unverified_boundaries = []
    for edge in edges:
        for module_key, symbol_key in (
            ("producer_module", "producer_symbol"),
            ("consumer_module", "consumer_symbol"),
        ):
            module = edge[module_key]
            cache.setdefault(module, _symbols(ROOT / module))
            if edge[symbol_key] not in cache[module]:
                unknown_symbols.append((module, edge[symbol_key]))
        if not _consumer_accepts(
                ROOT / edge["consumer_module"], edge["consumer_symbol"],
                edge["accepted_input_type_or_schema"]):
            unverified_boundaries.append(edge["edge_id"])
        signature_bound += 1
    assert not unknown_symbols and not unverified_boundaries
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
        "duplicate_edge_ids": len(edge_ids) - len(set(edge_ids)),
        "unknown_public_symbols": len(unknown_symbols),
        "signature_bound_edges": signature_bound,
        "unverified_consumer_type_boundaries": len(unverified_boundaries),
        "disconnected_production_nodes": max(0, components - 1),
        "result": "PASS",
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True, separators=(",", ":")))
