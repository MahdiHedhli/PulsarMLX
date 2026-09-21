#!/usr/bin/env python3
"""Independent checker for the generated Sequence 12 identity bridge contract."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQ = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-identity-to-numerical-bridge-requirements-v1.json"
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-identity-to-numerical-bridge-v2.json"
MODULE = ROOT / "scripts/research/f017_event06_identity_bridge_contract_v2.py"


def _assignments() -> dict[str, object]:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    result: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            result[node.targets[0].id] = ast.literal_eval(node.value)
    return result


def _acyclic(nodes: list[str], edges: list[str]) -> bool:
    incoming = {node: 0 for node in nodes}
    outgoing = {node: [] for node in nodes}
    for edge in edges:
        left, right = edge.split("->")
        if left not in incoming or right not in incoming or left == right:
            return False
        incoming[right] += 1
        outgoing[left].append(right)
    frontier = [node for node, count in incoming.items() if count == 0]
    visited = 0
    while frontier:
        node = frontier.pop()
        visited += 1
        for target in outgoing[node]:
            incoming[target] -= 1
            if incoming[target] == 0:
                frontier.append(target)
    return visited == len(nodes)


def validate() -> dict[str, object]:
    requirements = json.loads(REQ.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    generated = _assignments()
    pairs = (
        ("identity_input", "IDENTITY_INPUT"),
        ("numerical_bridge", "BRIDGE"),
        ("consumer_view", "CONSUMER_VIEW"),
        ("accounting_closure", "ACCOUNTING"),
        ("package_terminal", "PACKAGE_TERMINAL"),
    )
    for key, prefix in pairs:
        assert contract[key] == requirements[key]
        assert generated[f"{prefix}_SCHEMA"] == requirements[key]["schema"]
        assert generated[f"{prefix}_FIELDS"] == tuple(requirements[key]["fields"])
        assert generated[f"{prefix}_TYPES"] == requirements[key]["types"]
        assert len(requirements[key]["fields"]) == len(set(requirements[key]["fields"]))
        assert set(requirements[key]["fields"]) == set(requirements[key]["types"])
    nodes = requirements["signature_graph_nodes"]
    edges = requirements["signature_graph_edges"]
    assert generated["SIGNATURE_GRAPH_NODES"] == tuple(nodes)
    assert generated["SIGNATURE_GRAPH_EDGES"] == tuple(edges)
    assert len(nodes) == 18 and len(edges) == 17 and _acyclic(nodes, edges)
    assert generated["DIGEST_EDGES"] == tuple(requirements["digest_edges"])
    assert contract["legacy_projection_permitted"] is False
    assert contract["caller_created_mapping_permitted"] is False
    assert contract["unknown_fields_permitted"] is False
    return {
        "schema": "pulsarmlx.f017.event06-v12-identity-bridge-contract-validation/1.0.0",
        "identity_input_fields": len(requirements["identity_input"]["fields"]),
        "bridge_fields": len(requirements["numerical_bridge"]["fields"]),
        "consumer_view_fields": len(requirements["consumer_view"]["fields"]),
        "accounting_fields": len(requirements["accounting_closure"]["fields"]),
        "package_terminal_fields": len(requirements["package_terminal"]["fields"]),
        "signature_graph_nodes": len(nodes),
        "signature_graph_edges": len(edges),
        "digest_edges": len(requirements["digest_edges"]),
        "acyclic": True,
        "legacy_projection_permitted": False,
        "checkpoint_access": 0,
        "numerical_operations": 0,
        "result": "PASS",
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True, separators=(",", ":")))
