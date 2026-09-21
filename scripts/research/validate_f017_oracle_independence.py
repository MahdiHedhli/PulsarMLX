#!/usr/bin/env python3
"""Conservative static independence policy for the F017 oracle generator."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ALLOWED_IMPORTS = {
    "argparse",
    "hashlib",
    "json",
    "math",
    "platform",
    "struct",
    "importlib.metadata",
    "pathlib",
    "typing",
    "numpy",
    "__future__",
}
PROHIBITED_TOKENS = {
    "subprocess",
    "ctypes",
    "cffi",
    "pulsarmlx",
    "pulsar_mlx",
    "mlx",
    "checkpoint",
    "reference_",
}
ALLOWED_READ_FUNCTIONS = {"_write_or_check", "main"}


class IndependencePolicyError(RuntimeError):
    pass


def validate(path: Path) -> None:
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                if name not in ALLOWED_IMPORTS:
                    raise IndependencePolicyError(f"unapproved import: {name}")
                lowered = name.lower()
                if any(token in lowered for token in PROHIBITED_TOKENS):
                    raise IndependencePolicyError(f"prohibited dependency: {name}")
        if isinstance(node, ast.Call):
            function_name = ""
            if isinstance(node.func, ast.Name):
                function_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                function_name = node.func.attr
            lowered = function_name.lower()
            if function_name in {"system", "popen", "run", "call", "check_call", "check_output"}:
                raise IndependencePolicyError(f"process execution is prohibited: {function_name}")
            if function_name in {"read_text", "read_bytes", "open"}:
                current: ast.AST | None = node
                owner = None
                while current in parents:
                    current = parents[current]
                    if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        owner = current.name
                        break
                if owner not in ALLOWED_READ_FUNCTIONS:
                    raise IndependencePolicyError(
                        f"file read outside declared output drift check: {owner or '<module>'}"
                    )


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) == 2 else Path(
        "scripts/research/generate_f017_independent_oracle.py"
    )
    validate(path)
    print(f"F017 oracle independence policy: PASS ({path})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IndependencePolicyError as exc:
        print(f"F017 oracle independence policy: REJECT: {exc}", file=sys.stderr)
        raise SystemExit(2)
