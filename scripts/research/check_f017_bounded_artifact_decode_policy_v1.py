#!/usr/bin/env python3
"""Independent AST policy for active F017 runtime JSON decode surfaces."""
from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "scripts/research"
ENTRY_PATHS = {
    "scripts/research/validate_f017_corrected_oracle_access_v10.py",
    "scripts/research/execute_f017_corrected_oracle_event_v10.py",
    "scripts/research/f017_corrected_oracle_primary_v10.py",
    "scripts/research/f017_corrected_oracle_secondary_v10.py",
}
CANONICAL_PARSER = "scripts/research/f017_bounded_artifact_decode_v1.py"
OFFLINE_ONLY_ALLOWANCE = {
    ("scripts/research/qualify_f017_quantization_matrix_v1.py", "invoke"),
}


def _closure() -> set[str]:
    pending = list(ENTRY_PATHS)
    closure: set[str] = set()
    while pending:
        relative = pending.pop()
        if relative in closure:
            continue
        path = ROOT / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        closure.add(relative)
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [item.name.split(".", 1)[0] for item in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module.split(".", 1)[0]]
            for module in modules:
                dependency = RESEARCH / f"{module}.py"
                if dependency.is_file():
                    pending.append(f"scripts/research/{module}.py")
    return closure


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def _containing_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str | None:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
    return None


def validate() -> dict:
    closure = _closure()
    violations: list[dict] = []
    direct_decode_sites: list[dict] = []
    for relative in sorted(closure):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"), filename=relative)
        parents = _parents(tree)
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "json"
                and node.func.attr in {"load", "loads"}
            ):
                continue
            function = _containing_function(node, parents)
            site = {"path": relative, "function": function, "line": node.lineno, "member": node.func.attr}
            direct_decode_sites.append(site)
            if relative == CANONICAL_PARSER:
                continue
            if (relative, function) in OFFLINE_ONLY_ALLOWANCE:
                continue
            violations.append(site)
    if violations:
        raise ValueError(f"direct active-runtime JSON parser surface: {violations}")
    accounting = (RESEARCH / "f017_corrected_oracle_event_accounting_v10.py").read_text(encoding="utf-8")
    coordinator = (RESEARCH / "execute_f017_corrected_oracle_event_v10.py").read_text(encoding="utf-8")
    if "read_artifact(path)" not in accounting or "accounting_authority.accounting_lower_bound()" not in coordinator:
        raise ValueError("load-bearing bounded-decode integration absent")
    return {
        "schema": "pulsarmlx.f017.bounded-artifact-decode-source-policy-result/1.0.0",
        "result": "PASS",
        "runtime_import_closure_count": len(closure),
        "direct_decode_sites": direct_decode_sites,
        "violations": [],
        "canonical_parser": CANONICAL_PARSER,
        "offline_only_allowances": [list(item) for item in sorted(OFFLINE_ONLY_ALLOWANCE)],
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True, separators=(",", ":")))
