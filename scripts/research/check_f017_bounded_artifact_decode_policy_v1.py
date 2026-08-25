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
SYS_ALLOWED_DIRECT_MEMBERS = {"executable", "stderr"}
CAPABILITY_EXPORT_NAMES = {"builtins", "importlib", "json", "os", "sys"}
DYNAMIC_CAPABILITY_ATTRIBUTES = {
    "__bases__", "__builtins__", "__class__", "__dict__", "__getattribute__",
    "__globals__", "__mro__", "__subclasses__", "modules", "sys",
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


def _name_agnostic_decode_sites(relative: str, tree: ast.AST, parents: dict[ast.AST, ast.AST]) -> list[dict]:
    """Census direct load/loads calls without trusting receiver provenance."""
    sites: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or node.attr not in {"load", "loads"}:
            continue
        parent = parents.get(node)
        if isinstance(parent, ast.Call) and parent.func is node:
            sites.append({
                "path": relative,
                "function": _containing_function(node, parents),
                "line": node.lineno,
                "member": node.attr,
            })
    return sites


def inspect_source(relative: str, source: str) -> tuple[list[dict], list[dict]]:
    """Reject parser capabilities by semantic import/use shape, not spelling alone."""
    tree = ast.parse(source, filename=relative)
    parents = _parents(tree)
    violations: list[dict] = []
    direct_decode_sites: list[dict] = []
    semantic_modules: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name in {"json", "sys", "builtins"}:
                    semantic_modules[item.asname or item.name] = item.name
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name == "json" and item.asname is not None:
                    violations.append({"path": relative, "line": node.lineno, "reason": "JSON_MODULE_ALIAS"})
                if item.name == "importlib" or item.name.startswith("importlib."):
                    violations.append({"path": relative, "line": node.lineno, "reason": "DYNAMIC_IMPORT_MODULE"})
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0:
                violations.append({"path": relative, "line": node.lineno, "reason": "RELATIVE_IMPORT_PROHIBITED"})
            for item in node.names:
                if item.name in CAPABILITY_EXPORT_NAMES:
                    violations.append({
                        "path": relative,
                        "line": node.lineno,
                        "reason": "CAPABILITY_REEXPORT_IMPORT",
                        "member": item.name,
                    })
                    if item.name in {"json", "sys", "builtins"}:
                        semantic_modules[item.asname or item.name] = item.name
            if node.module in {"json", "sys", "builtins"}:
                violations.append({"path": relative, "line": node.lineno, "reason": "CAPABILITY_MEMBER_IMPORT", "module": node.module})
            if node.module == "importlib" or (node.module or "").startswith("importlib."):
                violations.append({"path": relative, "line": node.lineno, "reason": "DYNAMIC_IMPORT_MODULE"})
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"compile", "eval", "exec", "globals", "locals", "vars", "__import__"}:
                violations.append({"path": relative, "line": node.lineno, "reason": "DYNAMIC_GLOBAL_RESOLUTION"})
            elif node.func.id in {"getattr", "setattr"}:
                member = node.args[1].value if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) else None
                if type(member) is not str or member in DYNAMIC_CAPABILITY_ATTRIBUTES:
                    violations.append({"path": relative, "line": node.lineno, "reason": "DYNAMIC_ATTRIBUTE_RESOLUTION"})
        if isinstance(node, ast.Attribute) and node.attr in DYNAMIC_CAPABILITY_ATTRIBUTES:
            semantic_sys_direct = (
                node.attr in SYS_ALLOWED_DIRECT_MEMBERS
                and isinstance(node.value, ast.Name)
                and semantic_modules.get(node.value.id) == "sys"
            )
            if not semantic_sys_direct:
                violations.append({
                    "path": relative,
                    "line": node.lineno,
                    "reason": "DYNAMIC_CAPABILITY_TRAVERSAL",
                    "member": node.attr,
                })
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "modules"
            and isinstance(node.value, ast.Name)
            and node.value.id == "sys"
        ):
            violations.append({"path": relative, "line": node.lineno, "reason": "MODULE_REGISTRY_RESOLUTION"})
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "__import__"
            and isinstance(node.value, ast.Name)
            and node.value.id in {"builtins", "__builtins__"}
        ):
            violations.append({"path": relative, "line": node.lineno, "reason": "DYNAMIC_IMPORT_BUILTIN"})
        if isinstance(node, ast.Name) and node.id == "__builtins__":
            violations.append({"path": relative, "line": node.lineno, "reason": "BUILTINS_CAPABILITY_ESCAPE"})
        if not isinstance(node, ast.Name) or node.id not in semantic_modules:
            continue
        semantic_module = semantic_modules[node.id]
        parent = parents.get(node)
        if semantic_module == "builtins":
            violations.append({"path": relative, "line": node.lineno, "reason": "BUILTINS_MODULE_CAPABILITY"})
            continue
        if semantic_module == "sys":
            if not isinstance(parent, ast.Attribute) or parent.value is not node:
                violations.append({"path": relative, "line": node.lineno, "reason": "SYS_MODULE_ESCAPE"})
                continue
            if parent.attr not in SYS_ALLOWED_DIRECT_MEMBERS:
                violations.append({"path": relative, "line": node.lineno, "reason": "UNAUTHORIZED_SYS_CAPABILITY", "member": parent.attr})
            continue
        if not isinstance(parent, ast.Attribute) or parent.value is not node:
            violations.append({"path": relative, "line": node.lineno, "reason": "JSON_MODULE_ESCAPE"})
            continue
        member = parent.attr
        grandparent = parents.get(parent)
        direct_call = isinstance(grandparent, ast.Call) and grandparent.func is parent
        if member == "dumps" and direct_call:
            continue
        if member == "JSONDecodeError" and relative == CANONICAL_PARSER:
            continue
        if member in {"load", "loads"} and direct_call:
            function = _containing_function(parent, parents)
            site = {"path": relative, "function": function, "line": parent.lineno, "member": member}
            direct_decode_sites.append(site)
            if member == "loads" and (
                relative == CANONICAL_PARSER or (relative, function) in OFFLINE_ONLY_ALLOWANCE
            ):
                continue
        violations.append({"path": relative, "line": node.lineno, "reason": "UNAUTHORIZED_JSON_CAPABILITY", "member": member})
    return violations, direct_decode_sites


def validate() -> dict:
    closure = _closure()
    violations: list[dict] = []
    direct_decode_sites: list[dict] = []
    for relative in sorted(closure):
        source = (ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
        parents = _parents(tree)
        found, _ = inspect_source(relative, source)
        violations.extend(found)
        sites = _name_agnostic_decode_sites(relative, tree, parents)
        direct_decode_sites.extend(sites)
        for site in sites:
            if site["member"] == "loads" and (
                relative == CANONICAL_PARSER or (relative, site["function"]) in OFFLINE_ONLY_ALLOWANCE
            ):
                continue
            violations.append({
                "path": relative,
                "line": site["line"],
                "reason": "NAME_AGNOSTIC_DIRECT_DECODE_SITE",
                "member": site["member"],
            })
    if violations:
        raise ValueError(f"direct active-runtime JSON parser surface: {violations}")
    accounting = (RESEARCH / "f017_corrected_oracle_event_accounting_v10.py").read_text(encoding="utf-8")
    coordinator = (RESEARCH / "execute_f017_corrected_oracle_event_v10.py").read_text(encoding="utf-8")
    if "read_artifact_at(directory_fd, leaf)" not in accounting or "accounting_authority.accounting_lower_bound()" not in coordinator:
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
