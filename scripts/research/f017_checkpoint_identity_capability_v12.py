#!/usr/bin/env python3
"""Measured capability policy for the generic V12 identity producer."""
from __future__ import annotations

import ast
from pathlib import Path

from f017_checkpoint_identity_lifecycle_v12 import failure

ROOT = Path(__file__).resolve().parents[2]
PRODUCER = ROOT / "scripts/research/f017_checkpoint_identity_producer_v12.py"
PROHIBITED_IMPORTS = {"subprocess", "socket", "requests", "urllib", "importlib", "inspect", "ctypes"}


def validate_capability() -> dict:
    try:
        tree = ast.parse(PRODUCER.read_text(encoding="utf-8"), filename=str(PRODUCER))
        imports: set[str] = set()
        event_branches = 0
        dynamic_callbacks = 0
        caller_callback_parameters = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.If):
                text = ast.unparse(node.test)
                event_branches += int(bool(__import__("re").search(r"EVENT[_-]?0?[0-9]", text)))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "getattr", "setattr"}:
                dynamic_callbacks += 1
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names = {argument.arg for argument in (*node.args.posonlyargs, *node.args.args,
                                                        *node.args.kwonlyargs)}
                caller_callback_parameters += len(names & {"callback", "progress"})
        prohibited = sorted(imports & PROHIBITED_IMPORTS)
        if prohibited or event_branches or dynamic_callbacks or caller_callback_parameters:
            raise failure("F017_V12_IDENTITY_CAPABILITY_DRIFT", "V12 identity producer capability")
        return {
            "result": "PASS", "prohibited_imports": prohibited,
            "event_number_capability_branches": event_branches,
            "reflection_or_dynamic_callbacks": dynamic_callbacks,
            "caller_callback_parameters": caller_callback_parameters,
            "checkpoint_access_during_validation": 0,
        }
    except Exception as exc:
        if hasattr(exc, "outcome_id"):
            raise
        raise failure("F017_V12_IDENTITY_CAPABILITY_DRIFT", type(exc).__name__) from exc
