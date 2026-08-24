#!/usr/bin/env python3
"""Independent structural corroboration for F017 numerical capabilities.

This checker intentionally imports neither the value-flow analyzer nor any of
its helpers.  It provides a smaller second implementation of the direct-use
and reflection bans.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


def semantic_import(module: str, identities: dict[str, str]) -> str | None:
    matches = [
        name
        for name in identities
        if module == name or module.startswith(name + ".") or name.startswith(module + ".")
    ]
    if not matches:
        return None
    return identities[max(matches, key=len)]


def check(path: Path, policy: dict) -> dict:
    tree = ast.parse(path.read_text(), filename=str(path))
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                semantic = semantic_import(alias.name, policy["module_identities"])
                if semantic:
                    canonical_modules = {
                        module
                        for module, identity in policy["module_identities"].items()
                        if identity == semantic
                    }
                    if alias.name not in canonical_modules:
                        raise ValueError(f"independent checker: capability submodule {alias.name}")
                    aliases[alias.asname or alias.name.split(".")[0]] = semantic
        if isinstance(node, ast.ImportFrom):
            if node.level > 0:
                raise ValueError("independent checker: relative import")
            if node.module and semantic_import(node.module, policy["module_identities"]):
                raise ValueError("independent checker: import-from capability")
    uses = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in policy["prohibited_dynamic_names"]:
            raise ValueError(f"independent checker: dynamic name {node.id}")
        if isinstance(node, ast.Attribute) and node.attr in policy["prohibited_meta_attributes"]:
            raise ValueError(f"independent checker: meta attribute {node.attr}")
        if not isinstance(node, ast.Name) or node.id not in aliases:
            continue
        parent = parents.get(node)
        if not isinstance(parent, ast.Attribute) or parent.value is not node:
            raise ValueError(f"independent checker: bare module {node.id}")
        if isinstance(parents.get(parent), ast.Attribute):
            raise ValueError("independent checker: attribute chain")
        semantic = aliases[node.id]
        module = policy["semantic_modules"][semantic]
        allowed = set(module["direct_callable_members"]) | set(module["type_dtype_members"])
        if parent.attr not in allowed:
            raise ValueError(f"independent checker: member {parent.attr}")
        grandparent = parents.get(parent)
        if isinstance(grandparent, (ast.Assign, ast.AnnAssign, ast.NamedExpr, ast.Return, ast.Yield, ast.YieldFrom)):
            raise ValueError("independent checker: member escape")
        if isinstance(grandparent, (ast.List, ast.Tuple, ast.Set, ast.Dict, ast.Lambda)):
            raise ValueError("independent checker: member container/capture")
        uses += 1
    return {"result": "PASS", "path": str(path), "semantic_aliases": aliases, "approved_use_count": uses}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text())
    print(json.dumps(check(args.source, policy), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
