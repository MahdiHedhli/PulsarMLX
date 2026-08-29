#!/usr/bin/env python3
"""Source-derived legacy-writer and safety-storage census for Sequence 18."""
from __future__ import annotations

import ast
import hashlib
import inspect
from pathlib import Path

import execute_f017_corrected_oracle_event_v12_bridge as coordinator_v1
import execute_f017_corrected_oracle_event_v12_bridge_v2 as coordinator_v2
import f017_event06_package_attempt_registry_v1 as legacy
import f017_event06_package_attempt_registry_v2 as registry
from f017_event06_storage_authority_v1 import (
    FIXED_LIVE_REGISTRY_ROOT_CANONICAL_UTF8_LENGTH,
    FIXED_LIVE_REGISTRY_ROOT_CANONICAL_UTF8_SHA256,
    fixed_live_registry_root,
)


ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ENTRYPOINTS = (
    registry.reserve_live_package_attempt,
    registry.load_live_package_attempt,
    registry.claim_live_terminal_sinks,
    registry.bank_live_terminal,
    coordinator_v1.bank_live_package_start,
    coordinator_v1.execute_event06_bridge,
    coordinator_v2.execute_event06_bridge,
)
LEGACY_WRITERS = (
    legacy.reserve_package_attempt,
    legacy.claim_terminal_sinks,
    legacy.claim_qualification_terminal_sinks,
    legacy.bank_terminal,
    coordinator_v1.bank_package_start,
)
PRODUCTION_MODULES = (
    "scripts/research/f017_event06_storage_authority_v1.py",
    "scripts/research/f017_event06_storage_primitives_v1.py",
    "scripts/research/f017_event06_package_attempt_registry_v2.py",
    "scripts/research/execute_f017_corrected_oracle_event_v12_bridge.py",
    "scripts/research/execute_f017_corrected_oracle_event_v12_bridge_v2.py",
    "scripts/research/f017_event06_numerical_bridge_v1.py",
    "scripts/research/f017_event06_numerical_bridge_v2.py",
)
STORAGE_TOKENS = (
    "root", "path", "directory", "registry", "location", "storage", "provider",
    "resolver", "callback", "config", "option", "destination",
)
RECLAIM_TOKENS = ("reclaim", "expire", "unlock", "force", "truncate", "overwrite", "rotate")


def _tree(path: str) -> ast.Module:
    return ast.parse((ROOT / path).read_text(encoding="utf-8"))


def _first_effect_is_raise(function) -> bool:
    node = next(
        item for item in ast.walk(_tree(inspect.getsourcefile(function)))
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == function.__name__
    )
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body.pop(0)
    while body and isinstance(body[0], (ast.Delete, ast.Pass)):
        body.pop(0)
    return bool(body and isinstance(body[0], ast.Raise))


def _indirect_storage_selectors() -> list[dict[str, object]]:
    findings = []
    for path in PRODUCTION_MODULES:
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = ""
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                if name in {"getenv", "expanduser", "home"}:
                    findings.append({"path": path, "line": node.lineno, "symbol": name})
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
                if isinstance(node.value.value, ast.Name) and node.value.value.id == "os" and node.value.attr == "environ":
                    findings.append({"path": path, "line": node.lineno, "symbol": "os.environ"})
    return findings


def census() -> dict[str, object]:
    public = []
    for function in PRODUCTION_ENTRYPOINTS:
        for name, parameter in inspect.signature(function).parameters.items():
            if any(token in name.lower() for token in STORAGE_TOKENS):
                public.append({
                    "module": function.__module__, "symbol": function.__name__,
                    "parameter": name, "kind": parameter.kind.name,
                })
    source_path = ROOT / "scripts/research/f017_event06_storage_authority_v1.py"
    source_tree = ast.parse(source_path.read_text(encoding="utf-8"))
    source_line = next(
        node.lineno for node in source_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "fixed_live_registry_root"
    )
    reclaim = []
    for path in PRODUCTION_MODULES:
        for node in ast.walk(_tree(path)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                lowered = node.name.lower()
                if any(token in lowered for token in RECLAIM_TOKENS):
                    reclaim.append({"path": path, "line": node.lineno, "symbol": node.name})
    legacy_rows = [
        {
            "module": function.__module__,
            "symbol": function.__name__,
            "disposition": "FAIL_CLOSED_BEFORE_SIDE_EFFECT" if _first_effect_is_raise(function) else "REACHABLE",
        }
        for function in LEGACY_WRITERS
    ]
    fail_closed = sum(row["disposition"] == "FAIL_CLOSED_BEFORE_SIDE_EFFECT" for row in legacy_rows)
    result = {
        "schema": "pulsarmlx.f017.event06-v12-sequence18-storage-authority-census/1.0.0",
        "production_closure_modules": list(PRODUCTION_MODULES),
        "production_entrypoints": [f"{item.__module__}:{item.__name__}" for item in PRODUCTION_ENTRYPOINTS],
        "production_public_storage_location_inputs": len(public),
        "production_public_storage_location_findings": public,
        "production_indirect_storage_location_inputs": len(_indirect_storage_selectors()),
        "production_indirect_storage_location_findings": _indirect_storage_selectors(),
        "production_storage_authority_source": (
            f"scripts/research/f017_event06_storage_authority_v1.py:{source_line}:fixed_live_registry_root"
        ),
        "production_storage_authority_source_blob_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "fixed_live_registry_root_canonical_utf8_sha256": FIXED_LIVE_REGISTRY_ROOT_CANONICAL_UTF8_SHA256,
        "fixed_live_registry_root_canonical_utf8_length": FIXED_LIVE_REGISTRY_ROOT_CANONICAL_UTF8_LENGTH,
        "fixed_authority_runtime_digest_verified": (
            hashlib.sha256(str(fixed_live_registry_root()).encode()).hexdigest()
            == FIXED_LIVE_REGISTRY_ROOT_CANONICAL_UTF8_SHA256
        ),
        "reservation_reclaim_expire_unlock_or_override_symbols_reachable": len(reclaim),
        "reclaim_findings": reclaim,
        "legacy_production_writers_total": len(legacy_rows),
        "legacy_production_writers_removed": 0,
        "legacy_production_writers_fail_closed_proven": fail_closed,
        "legacy_production_writers_reachable_to_safety_state": len(legacy_rows) - fail_closed,
        "legacy_writer_rows": legacy_rows,
    }
    result["result"] = "PASS" if (
        result["production_public_storage_location_inputs"] == 0
        and result["production_indirect_storage_location_inputs"] == 0
        and result["reservation_reclaim_expire_unlock_or_override_symbols_reachable"] == 0
        and result["legacy_production_writers_total"]
        == result["legacy_production_writers_fail_closed_proven"]
    ) else "FAIL"
    return result


def validate_census_document(document: dict[str, object]) -> dict[str, object]:
    expected = census()
    if document != expected:
        raise ValueError("Sequence 18 storage census/source divergence")
    return expected


__all__ = ["census", "validate_census_document"]
