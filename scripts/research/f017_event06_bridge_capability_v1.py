#!/usr/bin/env python3
"""Static capability gate for the pure Event 06 bridge and execution plan."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PURE = [ROOT / "scripts/research/f017_event06_execution_plan_v1.py",
        ROOT / "scripts/research/f017_event06_numerical_bridge_v1.py"]
PROHIBITED_IMPORTS = {"os","subprocess","socket","mmap","importlib","ctypes","multiprocessing"}
PROHIBITED_CALLS = {"open","eval","exec","compile","getattr","setattr","globals","locals","vars","__import__"}


def validate_capability() -> dict:
    violations = []
    for path in PURE:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in PROHIBITED_IMPORTS:
                        violations.append(f"{path.name}:import:{alias.name}")
            elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in PROHIBITED_IMPORTS:
                violations.append(f"{path.name}:import:{node.module}")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in PROHIBITED_CALLS:
                violations.append(f"{path.name}:call:{node.func.id}")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names = [item.arg for item in node.args.args + node.args.kwonlyargs]
                if any("callback" in name or name.startswith("on_") for name in names):
                    violations.append(f"{path.name}:callback:{node.name}")
                if node.args.vararg is not None or node.args.kwarg is not None:
                    violations.append(f"{path.name}:variadic:{node.name}")
    if violations:
        raise ValueError("bridge capability drift: " + ",".join(violations))
    return {"result":"PASS","pure_modules":len(PURE),"violations":0,
        "checkpoint_capability":0,"file_io_capability":0,"subprocess_capability":0,
        "reflection_capability":0,"callback_capability":0,"ambient_policy_capability":0}


if __name__ == "__main__":
    import json
    print(json.dumps(validate_capability(), sort_keys=True, separators=(",",":")))
