#!/usr/bin/env python3
"""Source-derived, no-access qualification for the Event 06 minimum path.

The qualification invokes the sole public execution entry under the sealed,
context-local seams owned by ``f017_event06_minimum_gate_path_v1`` and censuses
the separate non-executing closeout entry.  It never selects a live root,
resolves an original checkpoint root, or supplies an authority/effect
dependency through the public API.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import re
from types import SimpleNamespace
import sys
import tempfile
import threading
from typing import Callable
from unittest.mock import patch

import f017_event06_minimum_gate_contract_v1 as contract
import f017_event06_minimum_gate_path_v1 as path


_ROOT = Path(__file__).resolve().parents[2]
_RESEARCH_ROOT = _ROOT / "scripts/research"
_PATH_SOURCE = _ROOT / "scripts/research/f017_event06_minimum_gate_path_v1.py"
_PUBLIC_EXECUTION_ENTRY = "execute_event06_minimum_gate_path"
_PUBLIC_CLOSEOUT_ENTRY = "closeout_interrupted_event06_minimum_gate_path"
_PUBLIC_EXPORTS = (_PUBLIC_EXECUTION_ENTRY, _PUBLIC_CLOSEOUT_ENTRY)
_SEQUENCE42_CHANGED_BOUNDARY_SOURCES = (
    "scripts/research/f017_checkpoint_identity_lifecycle_v12.py",
    "scripts/research/f017_checkpoint_identity_producer_v12.py",
    "scripts/research/f017_event06_minimum_gate_contract_v1.py",
    "scripts/research/f017_event06_minimum_gate_path_v1.py",
)
_SEQUENCE42_SCHEMA_VERSION = re.compile(
    r"pulsarmlx\.f017\..+/(?:12\.1\.0|1\.1\.0)"
)
_SEQUENCE40_CONSUMED_DECISION_SHA256 = (
    "25b1312d26a436e103f26f1645f2d83e3147cbabc6522c91e5fa92d89ee73bdd"
)
_SUPERSEDED_SURFACE_SOURCES = (
    "scripts/research/f017_checkpoint_identity_producer_v12.py",
    "scripts/research/f017_corrected_oracle_primary_wrapper_v11.py",
    "scripts/research/f017_corrected_oracle_secondary_wrapper_v11.py",
    "scripts/research/f017_corrected_oracle_primary_wrapper_v12.py",
    "scripts/research/f017_corrected_oracle_secondary_wrapper_v12.py",
    "scripts/research/f017_corrected_oracle_primary_wrapper_v12_bridge_v2.py",
    "scripts/research/f017_corrected_oracle_secondary_wrapper_v12_bridge_v2.py",
    "scripts/research/f017_result_bundle_builder_v11.py",
    "scripts/research/execute_f017_corrected_oracle_event_v12_bridge.py",
    "scripts/research/execute_f017_corrected_oracle_event_v12_bridge_v2.py",
    "scripts/research/f017_corrected_oracle_authorization_v12_v3.py",
    "scripts/research/f017_event06_collapsed_go_path_v1.py",
    "scripts/research/f017_event06_collapsed_live_installation_v2.py",
    "scripts/research/f017_event06_dag_derived_control_path_v1.py",
    "scripts/research/f017_event06_package_attempt_registry_v1.py",
    "scripts/research/f017_event06_package_attempt_registry_v2.py",
    "scripts/research/f017_event06_production_installation_v1.py",
    "scripts/research/f017_event06_production_installation_v2.py",
    "scripts/research/f017_event06_production_installation_v3.py",
)
_FORBIDDEN_PUBLIC_PARAMETER_TOKENS = (
    "identity_plan",
    "checkpoint",
    "storage",
    "root",
    "registry",
    "receipt",
    "ledger",
    "resolver",
    "provider",
    "callback",
    "dependency",
    "authority_sink",
    "kwargs",
)
_EFFECTFUL_NAME_TOKENS = (
    "begin",
    "execute",
    "install",
    "reserve",
    "claim",
    "commit",
    "bank",
    "start",
    "terminal",
)
_IRREVERSIBLE_EFFECT_CALLEES = frozenset(
    {
        "bank_exclusive",
        "write_bytes",
        "write_text",
        "mkdir",
        "replace",
        "rename",
        "symlink_to",
        "link",
        "_commit_bound",
        "_bank_checked",
        "_bank_package_start",
        "_execute_consumers",
        "_bank_reservation",
        "_bank_terminal",
        "commit_synthetic",
    }
)

_SUPERSEDED_EFFECTFUL_ENTRYPOINTS: dict[str, dict[str, str]] = {
    "scripts/research/f017_checkpoint_identity_producer_v12.py": {
        "produce": "_minimum_gate_produce",
    },
    "scripts/research/f017_corrected_oracle_primary_wrapper_v11.py": {
        "execute_and_bank": "_minimum_gate_execute_and_bank",
        "execute_target_and_bank": "_minimum_gate_execute_target_and_bank",
    },
    "scripts/research/f017_corrected_oracle_secondary_wrapper_v11.py": {
        "execute_and_bank": "_minimum_gate_execute_and_bank",
        "execute_target_and_bank": "_minimum_gate_execute_target_and_bank",
    },
    "scripts/research/f017_corrected_oracle_primary_wrapper_v12.py": {
        "execute_bridge_and_bank": "_qualification_execute_bridge_and_bank",
    },
    "scripts/research/f017_corrected_oracle_secondary_wrapper_v12.py": {
        "execute_bridge_and_bank": "_qualification_execute_bridge_and_bank",
    },
    "scripts/research/f017_corrected_oracle_primary_wrapper_v12_bridge_v2.py": {
        "execute_bridge_and_bank": "_qualification_execute_bridge_and_bank",
    },
    "scripts/research/f017_corrected_oracle_secondary_wrapper_v12_bridge_v2.py": {
        "execute_bridge_and_bank": "_qualification_execute_bridge_and_bank",
    },
    "scripts/research/f017_result_bundle_builder_v11.py": {
        "bank_output_bundle": "_minimum_gate_bank_output_bundle",
    },
    "scripts/research/execute_f017_corrected_oracle_event_v12_bridge.py": {
        "bank_live_package_start": "_qualification_bank_live_package_start",
        "bank_package_start": "_bank_package_start",
        "execute_event06_bridge": "_qualification_execute_event06_bridge",
        "close_bridge_package": "_qualification_close_bridge_package",
    },
    "scripts/research/execute_f017_corrected_oracle_event_v12_bridge_v2.py": {
        "execute_event06_bridge": "_qualification_execute_event06_bridge",
    },
    "scripts/research/f017_event06_collapsed_go_path_v1.py": {
        "begin_live_one_shot_composition": (
            "_qualification_begin_live_one_shot_composition"
        ),
    },
    "scripts/research/f017_event06_collapsed_live_installation_v2.py": {
        "begin_live_collapsed_installation": (
            "_qualification_begin_live_collapsed_installation"
        ),
        "commit_collapsed_live_installation": (
            "_qualification_commit_collapsed_live_installation"
        ),
    },
    "scripts/research/f017_event06_dag_derived_control_path_v1.py": {
        "run_full_call_path": "_qualification_run_full_call_path",
    },
    "scripts/research/f017_event06_package_attempt_registry_v2.py": {
        "reserve_live_package_attempt": "_qualification_reserve_live_package_attempt",
        "load_live_package_attempt": "_qualification_load_live_package_attempt",
        "claim_live_terminal_sinks": "_qualification_claim_live_terminal_sinks",
        "bank_live_terminal": "_qualification_bank_live_terminal",
    },
    "scripts/research/f017_event06_production_installation_v2.py": {
        "produce_future_go_capability": (
            "_qualification_produce_future_go_capability"
        ),
        "commit_production_installation_v2": (
            "_qualification_commit_production_installation_v2"
        ),
    },
    "scripts/research/f017_event06_production_installation_v3.py": {
        "produce_future_go_capability_v3": (
            "_qualification_produce_future_go_capability_v3"
        ),
        "commit_production_installation_v3": (
            "_qualification_commit_production_installation_v3"
        ),
    },
}

_INTRINSICALLY_FAIL_CLOSED_ENTRYPOINTS: dict[str, tuple[str, ...]] = {
    "scripts/research/f017_event06_package_attempt_registry_v1.py": (
        "reserve_package_attempt",
        "claim_terminal_sinks",
        "claim_qualification_terminal_sinks",
        "bank_terminal",
    ),
    "scripts/research/f017_event06_production_installation_v1.py": (
        "commit_production_installation",
    ),
}

# The accepted Sequence 38 classification is expressed here as semantic
# equivalence probes, not as a search for the historical symbol spelling.  A
# dependency is resolved only when the source-derived public closure contains
# no independent predicate/call surface for it.  Retained semantics that used
# to be duplicated by a dependency are named explicitly.
_DEPENDENCY_EQUIVALENCE_PROBES: dict[str, dict[str, object]] = {
    "M018": {
        "semantic": "eighty_six_field_readiness_acceptance_census",
        "resolution": "ABSENT_FROM_MANDATORY_PATH",
        "retained_by": (),
        "forbidden_component_terms": ("readiness_authority", "readiness_declaration"),
        "forbidden_source_terms": ("required_readiness_fields", "86_field"),
    },
    "M019": {
        "semantic": "twenty_one_role_readiness_manifest_closure",
        "resolution": "ABSENT_FROM_MANDATORY_PATH",
        "retained_by": (),
        "forbidden_component_terms": ("readiness_manifest",),
        "forbidden_source_terms": ("21_role", "authority_manifest_roles"),
    },
    "M020": {
        "semantic": "separate_schema_type_and_key_ratification",
        "resolution": "UTILITY_SUBSUMED_BY_FAIL_CLOSED_PREFLIGHT",
        "retained_by": ("M003",),
        "forbidden_component_terms": ("ratify_schema", "ratify_type", "ratify_key"),
        "forbidden_source_terms": ("schema_ratification", "type_ratification", "key_ratification"),
    },
    "M021": {
        "semantic": "implementation_head_tree_measurement_binding",
        "resolution": "ABSENT_FROM_MANDATORY_PATH",
        "retained_by": (),
        "forbidden_component_terms": ("implementation_measurement",),
        "forbidden_source_terms": ("implementation_head", "implementation_tree"),
    },
    "M022": {
        "semantic": "historical_readiness_supersession_chain",
        "resolution": "ABSENT_FROM_MANDATORY_PATH",
        "retained_by": (),
        "forbidden_component_terms": ("readiness_supersession",),
        "forbidden_source_terms": ("superseded_readiness", "readiness_predecessor"),
    },
    "M023": {
        "semantic": "pre_observation_qualification_corpus",
        "resolution": "OPTIONAL_AND_ABSENT_FROM_RUNTIME_PREDICATE",
        "retained_by": (),
        "forbidden_component_terms": ("qualification_corpus",),
        "forbidden_source_terms": ("qualification_corpus_sha256",),
    },
    "M024": {
        "semantic": "exact_head_full_native_ci_gate",
        "resolution": "OPTIONAL_AND_ABSENT_FROM_RUNTIME_PREDICATE",
        "retained_by": (),
        "forbidden_component_terms": ("full_native",),
        "forbidden_source_terms": ("required_native_skips", "full_native_run"),
    },
    "M025": {
        "semantic": "pre_event_independent_review_transport_gate",
        "resolution": "OPTIONAL_AND_ABSENT_FROM_RUNTIME_PREDICATE",
        "retained_by": (),
        "forbidden_component_terms": ("review_transport", "reviewer_admission"),
        "forbidden_source_terms": ("gemini_verdict", "opus_verdict", "review_provenance"),
    },
    "M026": {
        "semantic": "multi_document_human_authenticity_planner_chain",
        "resolution": "COLLAPSED_INTO_EXACT_HUMAN_PACKAGE_AUTHORITY",
        "retained_by": ("M012",),
        "forbidden_component_terms": ("planner_acceptance", "human_authenticity"),
        "forbidden_source_terms": ("sanitized_human_decision", "planner_acceptance_sha256"),
    },
    "M027": {
        "semantic": "separate_go_nonce_and_validity_window_gate",
        "resolution": "COLLAPSED_INTO_EXACT_HUMAN_PACKAGE_AUTHORITY",
        "retained_by": ("M012",),
        "forbidden_component_terms": ("validate_go_window", "validate_go_nonce"),
        "forbidden_source_terms": ("go_window_receipt", "go_nonce_receipt"),
    },
    "M028": {
        "semantic": "separate_derived_four_event_identity_plan",
        "resolution": "INTERNALLY_DERIVED_ONCE_WITHOUT_PLAN_AUTHORITY",
        "retained_by": ("M001", "M012"),
        "forbidden_component_terms": ("execution_plan", "identity_plan_validator"),
        "forbidden_source_terms": ("four_event_identity_plan", "identity_plan_path"),
    },
    "M029": {
        "semantic": "multi_adapter_sealed_exact_type_ceremony",
        "resolution": "INTERNAL_TYPES_ONLY_NOT_AN_INDEPENDENT_GATE",
        "retained_by": ("M003", "M012", "M014"),
        "forbidden_component_terms": ("preparation_adapter", "candidate_bundle_adapter"),
        "forbidden_source_terms": ("prepared_installation", "adapter_chain"),
    },
    "M030": {
        "semantic": "three_file_installation_transaction_and_readback",
        "resolution": "ABSENT_FROM_MANDATORY_PATH",
        "retained_by": (),
        "forbidden_component_terms": ("installation_transaction", "installed_triple"),
        "forbidden_source_terms": ("candidate_install_readback", "installed_triple"),
    },
    "M031": {
        "semantic": "separately_ratified_fixed_storage_layout",
        "resolution": "INTERNAL_NON_GATING_STORAGE_CHOICE",
        "retained_by": ("M001", "M016"),
        "forbidden_component_terms": ("storage_authority", "storage_primitives"),
        "forbidden_source_terms": ("storage_layout_ratification",),
    },
    "M032": {
        "semantic": "reservation_terminal_sink_claim_bank_split",
        "resolution": "COLLAPSED_INTO_ONE_SHOT_AND_SOLE_TERMINAL",
        "retained_by": ("M001", "M004", "M016"),
        "forbidden_component_terms": ("package_attempt_registry", "terminal_sink_claim"),
        "forbidden_source_terms": ("claim_terminal_sink", "bank_claimed_terminal"),
    },
    "M035": {
        "semantic": "zero_finding_label_gate",
        "resolution": "OPTIONAL_AND_ABSENT_FROM_RUNTIME_PREDICATE",
        "retained_by": (),
        "forbidden_component_terms": ("zero_findings",),
        "forbidden_source_terms": ("blocking_findings", "unresolved_findings"),
    },
}


def _literal_all(tree: ast.Module) -> tuple[str, ...]:
    for node in tree.body:
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if (
            isinstance(target, ast.Name)
            and target.id == "__all__"
            and value is not None
        ):
            resolved = ast.literal_eval(value)
            if type(resolved) not in {tuple, list} or any(
                type(item) is not str for item in resolved
            ):
                raise AssertionError("__all__ must be a static string census")
            return tuple(resolved)
    raise AssertionError("explicit __all__ required")


def _declared_or_implicit_exports(tree: ast.Module) -> tuple[str, ...]:
    try:
        return _literal_all(tree)
    except AssertionError:
        return tuple(
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and not node.name.startswith("_")
        )


def _local_call_graph(
    tree: ast.Module,
) -> tuple[dict[str, ast.FunctionDef | ast.AsyncFunctionDef], dict[str, set[str]]]:
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    graph: dict[str, set[str]] = {}
    for name, node in functions.items():
        called = {
            call.func.id
            for call in ast.walk(node)
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
        }
        graph[name] = called & functions.keys()
    return functions, graph


def _reachable(graph: dict[str, set[str]], root: str) -> set[str]:
    pending = [root]
    reached: set[str] = set()
    while pending:
        symbol = pending.pop()
        if symbol in reached:
            continue
        reached.add(symbol)
        pending.extend(sorted(graph.get(symbol, ()), reverse=True))
    return reached


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _module_path(module_name: str) -> Path | None:
    """Resolve only a repository-local, single-file research module."""
    leaf = module_name.rsplit(".", 1)[-1]
    if not leaf or not leaf.replace("_", "a").isalnum():
        return None
    candidate = _RESEARCH_ROOT / f"{leaf}.py"
    if candidate.is_file() and not candidate.is_symlink():
        return candidate
    return None


def _local_imports(tree: ast.Module) -> dict[str, dict[str, str]]:
    """Return alias -> local source binding without importing any module."""
    result: dict[str, dict[str, str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            target = _module_path(node.module)
            if target is None:
                continue
            for item in node.names:
                alias = item.asname or item.name
                result[alias] = {
                    "module": target.stem,
                    "symbol": item.name,
                    "path": target.relative_to(_ROOT).as_posix(),
                }
        elif isinstance(node, ast.Import):
            for item in node.names:
                target = _module_path(item.name)
                if target is None:
                    continue
                alias = item.asname or item.name.rsplit(".", 1)[-1]
                result[alias] = {
                    "module": target.stem,
                    "symbol": "*",
                    "path": target.relative_to(_ROOT).as_posix(),
                }
    return result


def _module_assignment(tree: ast.Module, name: str) -> ast.expr:
    """Return one exact module-level assignment expression."""
    values: list[ast.expr] = []
    for node in tree.body:
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if (
            isinstance(target, ast.Name)
            and target.id == name
            and value is not None
        ):
            values.append(value)
    if len(values) != 1:
        raise AssertionError(f"one module assignment required: {name}")
    return values[0]


def _identity_success_leaf_census(tree: ast.Module) -> dict[str, object]:
    """Derive the exact identity success inventory from producer source only."""
    imports = _local_imports(tree)
    binding = imports.get("_identity_success_evidence_leaves")
    if binding != {
        "module": "f017_checkpoint_identity_producer_v12",
        "symbol": "identity_success_evidence_leaves",
        "path": "scripts/research/f017_checkpoint_identity_producer_v12.py",
    }:
        raise AssertionError("identity success-leaf source binding")

    composer_value = _module_assignment(
        tree, "_SUCCESS_PHYSICAL_IDENTITY_FILES"
    )
    if not (
        isinstance(composer_value, ast.Call)
        and isinstance(composer_value.func, ast.Name)
        and composer_value.func.id == "frozenset"
        and len(composer_value.args) == 1
        and not composer_value.keywords
        and isinstance(composer_value.args[0], ast.Call)
        and isinstance(composer_value.args[0].func, ast.Name)
        and composer_value.args[0].func.id == "_identity_success_evidence_leaves"
        and not composer_value.args[0].args
        and not composer_value.args[0].keywords
    ):
        raise AssertionError("composer identity inventory must use producer export")

    producer_path = _ROOT / str(binding["path"])
    producer_raw = producer_path.read_bytes()
    producer_tree = ast.parse(producer_raw, filename=str(producer_path))
    if "identity_success_evidence_leaves" not in _literal_all(producer_tree):
        raise AssertionError("identity success-leaf producer export")

    base_expression = _module_assignment(producer_tree, "_IDENTITY_BASE_LEAVES")
    if not (
        isinstance(base_expression, ast.Call)
        and isinstance(base_expression.func, ast.Name)
        and base_expression.func.id == "frozenset"
        and len(base_expression.args) == 1
        and not base_expression.keywords
    ):
        raise AssertionError("identity base-leaf source expression")
    base_value = ast.literal_eval(base_expression.args[0])
    if type(base_value) is not set or any(
        type(item) is not str for item in base_value
    ):
        raise AssertionError("identity base-leaf literal census")

    function = _named_node(producer_tree, "identity_success_evidence_leaves")
    if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise AssertionError("identity success-leaf function source")
    prefix_values = [
        node.value
        for node in function.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "prefix"
    ]
    if len(prefix_values) != 1 or not isinstance(prefix_values[0], ast.SetComp):
        raise AssertionError("identity access-prefix source comprehension")
    comprehension = prefix_values[0]
    if (
        len(comprehension.generators) != 1
        or comprehension.generators[0].ifs
        or comprehension.generators[0].is_async
        or not isinstance(comprehension.generators[0].target, ast.Name)
        or comprehension.generators[0].target.id != "sequence"
        or not isinstance(comprehension.generators[0].iter, ast.Call)
        or not isinstance(comprehension.generators[0].iter.func, ast.Name)
        or comprehension.generators[0].iter.func.id != "range"
        or [
            item.value
            for item in comprehension.generators[0].iter.args
            if isinstance(item, ast.Constant) and type(item.value) is int
        ]
        != [1, 25]
        or comprehension.generators[0].iter.keywords
        or ast.unparse(comprehension.elt)
        not in {
            "f'access-prefix-{sequence:02d}.json'",
            'f"access-prefix-{sequence:02d}.json"',
        }
    ):
        raise AssertionError("identity access-prefix exact source range")

    returns = [node for node in function.body if isinstance(node, ast.Return)]
    if len(returns) != 1 or returns[0].value is None:
        raise AssertionError("identity success-leaf return source")
    return_source = ast.unparse(returns[0].value)
    if return_source != "tuple(sorted(set(_IDENTITY_BASE_LEAVES) | prefix))":
        raise AssertionError("identity success-leaf union source")

    prefix = {f"access-prefix-{sequence:02d}.json" for sequence in range(1, 25)}
    leaves = tuple(sorted(set(base_value) | prefix))
    if len(base_value) != 7 or len(prefix) != 24 or len(leaves) != 31:
        raise AssertionError("exact 31-leaf identity success inventory")
    return {
        "derivation": "AST_PRODUCER_EXPORT_AND_LITERAL_RANGE",
        "producer_module": str(binding["module"]),
        "producer_path": str(binding["path"]),
        "producer_source_sha256": _sha256(producer_raw),
        "producer_export": str(binding["symbol"]),
        "composer_uses_producer_export": True,
        "base_leaf_count": len(base_value),
        "access_prefix_leaf_count": len(prefix),
        "leaf_count": len(leaves),
        "leaves": list(leaves),
        "result": "PASS",
    }


def _recursive_local_import_inventory() -> dict[str, object]:
    """Recursively inventory local modules imported by the production module.

    This parses source only.  It neither imports additional code nor resolves
    any repository path mentioned by a contract or authority document.
    """
    pending = [_PATH_SOURCE]
    visited: set[Path] = set()
    records: list[dict[str, object]] = []
    edges: set[tuple[str, str, str]] = set()
    while pending:
        source_path = pending.pop()
        source_path = source_path.resolve(strict=True)
        if source_path in visited:
            continue
        visited.add(source_path)
        raw = source_path.read_bytes()
        tree = ast.parse(raw, filename=str(source_path))
        imports = _local_imports(tree)
        source_name = source_path.stem
        imported_modules: set[str] = set()
        for binding in imports.values():
            imported = str(binding["module"])
            imported_modules.add(imported)
            edges.add((source_name, imported, str(binding["symbol"])))
            target = _module_path(imported)
            if target is not None and target.resolve() not in visited:
                pending.append(target)
        records.append(
            {
                "module": source_name,
                "path": source_path.relative_to(_ROOT).as_posix(),
                "sha256": _sha256(raw),
                "local_imports": sorted(imported_modules),
            }
        )
    records.sort(key=lambda item: str(item["module"]))
    return {
        "entry_module": _PATH_SOURCE.stem,
        "module_count": len(records),
        "modules": records,
        "edges": [
            {"consumer": consumer, "producer": producer, "symbol": symbol}
            for consumer, producer, symbol in sorted(edges)
        ],
        "source_only": True,
    }


def _qualified_function_nodes(
    tree: ast.Module,
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Return module functions and one-level class methods by qualified name."""
    result: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result[node.name] = node
        elif isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result[f"{node.name}.{member.name}"] = member
    return result


def _alias_reference_sites(tree: ast.Module, alias: str) -> list[str]:
    """Source-derive every executable or module binding that uses an import."""
    sites = {
        name
        for name, node in _qualified_function_nodes(tree).items()
        if any(
            isinstance(item, ast.Name) and item.id == alias
            for item in ast.walk(node)
        )
    }
    module_statements = [
        node
        for node in tree.body
        if not isinstance(
            node,
            (
                ast.Import,
                ast.ImportFrom,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        )
    ]
    if any(
        isinstance(item, ast.Name) and item.id == alias
        for statement in module_statements
        for item in ast.walk(statement)
    ):
        sites.add("<module>")
    return sorted(sites)


def _schema_assignment_values(tree: ast.Module) -> dict[str, str]:
    """Resolve exact module constants holding Sequence 42 schema versions."""
    result: dict[str, str] = {}
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        if not (
            isinstance(value, ast.Constant)
            and type(value.value) is str
            and _SEQUENCE42_SCHEMA_VERSION.fullmatch(value.value) is not None
        ):
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                result[target.id] = value.value
    return result


def _schema_references(
    node: ast.AST, assignments: dict[str, str]
) -> set[str]:
    result: set[str] = set()
    for item in ast.walk(node):
        if (
            isinstance(item, ast.Constant)
            and type(item.value) is str
            and _SEQUENCE42_SCHEMA_VERSION.fullmatch(item.value) is not None
        ):
            result.add(item.value)
        elif isinstance(item, ast.Name) and item.id in assignments:
            result.add(assignments[item.id])
    return result


def _schema_writer_references(
    node: ast.AST, assignments: dict[str, str]
) -> set[str]:
    result: set[str] = set()
    for item in (candidate for candidate in ast.walk(node) if isinstance(candidate, ast.Dict)):
        for key, value in zip(item.keys, item.values, strict=True):
            if not (
                isinstance(key, ast.Constant)
                and key.value == "schema"
            ):
                continue
            if (
                isinstance(value, ast.Constant)
                and type(value.value) is str
                and _SEQUENCE42_SCHEMA_VERSION.fullmatch(value.value) is not None
            ):
                result.add(value.value)
            elif isinstance(value, ast.Name) and value.id in assignments:
                result.add(assignments[value.id])
    return result


def _changed_typed_boundary_census() -> dict[str, object]:
    """Derive and compose every Sequence 42 public or evidence boundary.

    The expected set comes from four independent final-source properties:
    cross-module lifecycle type imports, producer ``__all__``, minimum-path
    ``__all__``, and version-forward evidence schema literals.  The two raw
    document validators and their sealed callers are discovered from the
    minimum path's imports plus the contract's local call graph.  Coverage is
    then derived separately from source reference sites and schema
    writer-to-validator composition; no observed runtime trace supplies the
    denominator.
    """
    sources: dict[str, dict[str, object]] = {}
    for relative in _SEQUENCE42_CHANGED_BOUNDARY_SOURCES:
        source_path = _ROOT / relative
        raw = source_path.read_bytes()
        tree = ast.parse(raw, filename=str(source_path))
        sources[source_path.stem] = {
            "path": relative,
            "sha256": _sha256(raw),
            "tree": tree,
            "imports": _local_imports(tree),
        }

    lifecycle_module = "f017_checkpoint_identity_lifecycle_v12"
    producer_module = "f017_checkpoint_identity_producer_v12"
    contract_module = "f017_event06_minimum_gate_contract_v1"
    path_module = "f017_event06_minimum_gate_path_v1"

    lifecycle_symbols = sorted({
        str(binding["symbol"])
        for consumer in (producer_module, path_module)
        for binding in sources[consumer]["imports"].values()
        if binding["module"] == lifecycle_module
        and not str(binding["symbol"]).startswith("_")
    })
    producer_tree = sources[producer_module]["tree"]
    path_tree = sources[path_module]["tree"]
    contract_tree = sources[contract_module]["tree"]
    if not isinstance(producer_tree, ast.Module) or not isinstance(
        path_tree, ast.Module
    ) or not isinstance(contract_tree, ast.Module):
        raise AssertionError("changed boundary source trees")
    producer_symbols = sorted(_literal_all(producer_tree))
    path_symbols = sorted(_literal_all(path_tree))

    path_contract_imports = {
        str(binding["symbol"])
        for binding in sources[path_module]["imports"].values()
        if binding["module"] == contract_module
    }
    raw_document_validators = {
        symbol
        for symbol in path_contract_imports
        if symbol.startswith("_validate_") and symbol.endswith("_document")
    }
    contract_functions, contract_graph = _local_call_graph(contract_tree)
    sealed_validator_callers = {
        caller
        for caller, callees in contract_graph.items()
        if caller in path_contract_imports
        and caller.startswith("_validate_")
        and callees & raw_document_validators
    }
    contract_symbols = sorted(
        raw_document_validators | sealed_validator_callers
    )

    callable_groups = (
        (
            lifecycle_module,
            lifecycle_symbols,
            "CROSS_MODULE_TYPED_CARRIER_OR_FACTORY",
        ),
        (
            producer_module,
            producer_symbols,
            "EXPORTED_IDENTITY_PRODUCER_CONSUMER_INTERFACE",
        ),
        (
            contract_module,
            contract_symbols,
            "RAW_AND_SEALED_DOCUMENT_VALIDATOR_INTERFACE",
        ),
        (
            path_module,
            path_symbols,
            "PUBLIC_MINIMUM_PATH_INTERFACE",
        ),
    )
    callable_rows: list[dict[str, object]] = []
    callable_coverage: set[str] = set()
    for module, symbols, kind in callable_groups:
        producer = sources[module]
        producer_tree = producer["tree"]
        if not isinstance(producer_tree, ast.Module):
            raise AssertionError("changed callable producer tree")
        producer_nodes = {
            node.name: node
            for node in producer_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        for symbol in symbols:
            if symbol not in producer_nodes:
                raise AssertionError(f"changed callable source symbol: {module}.{symbol}")
            consumer_sites: set[str] = set()
            for consumer_module, consumer in sources.items():
                imports = consumer["imports"]
                consumer_tree = consumer["tree"]
                if not isinstance(consumer_tree, ast.Module):
                    raise AssertionError("changed callable consumer tree")
                for alias, binding in imports.items():
                    if (
                        binding["module"] == module
                        and binding["symbol"] == symbol
                    ):
                        consumer_sites.update(
                            f"{consumer_module}.{site}"
                            for site in _alias_reference_sites(
                                consumer_tree, alias
                            )
                        )
            if module == path_module:
                _, path_graph = _local_call_graph(producer_tree)
                consumer_sites.update(
                    f"{path_module}.{caller}"
                    for caller, callees in path_graph.items()
                    if symbol in callees
                )
            component = f"{module}.{symbol}"
            covered = bool(consumer_sites)
            if covered:
                callable_coverage.add(component)
            callable_rows.append(
                {
                    "boundary": component,
                    "boundary_kind": kind,
                    "producer_path": producer["path"],
                    "producer_source_sha256": producer["sha256"],
                    "consumer_reference_sites": sorted(consumer_sites),
                    "composition_tested": covered,
                }
            )

    schema_values: set[str] = set()
    schema_direct_references: dict[str, set[str]] = {}
    schema_writers: dict[str, set[str]] = {}
    schema_validators: dict[str, set[str]] = {}
    for module, source in sources.items():
        tree = source["tree"]
        if not isinstance(tree, ast.Module):
            raise AssertionError("changed schema source tree")
        assignments = _schema_assignment_values(tree)
        schema_values.update(assignments.values())
        schema_values.update(
            item.value
            for item in ast.walk(tree)
            if isinstance(item, ast.Constant)
            and type(item.value) is str
            and _SEQUENCE42_SCHEMA_VERSION.fullmatch(item.value) is not None
        )
        qualified_nodes = _qualified_function_nodes(tree)
        function_nodes = {
            name: node
            for name, node in qualified_nodes.items()
            if "." not in name
        }
        local_graph = {
            name: {
                call.func.id
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id in function_nodes
            }
            for name, node in function_nodes.items()
        }
        direct_by_function: dict[str, set[str]] = {}
        for name, node in qualified_nodes.items():
            referenced = _schema_references(node, assignments)
            direct_by_function[name] = referenced
            for schema in referenced:
                schema_direct_references.setdefault(schema, set()).add(
                    f"{module}.{name}"
                )
            for schema in _schema_writer_references(node, assignments):
                schema_writers.setdefault(schema, set()).add(f"{module}.{name}")
        for name in function_nodes:
            if "validate" not in name:
                continue
            reached = _reachable(local_graph, name)
            for schema in set().union(
                *(direct_by_function[callee] for callee in reached)
            ):
                schema_validators.setdefault(schema, set()).add(
                    f"{module}.{name}"
                )
        for name, referenced in direct_by_function.items():
            if "." in name and "validate" in name:
                for schema in referenced:
                    schema_validators.setdefault(schema, set()).add(
                        f"{module}.{name}"
                    )

    schema_rows: list[dict[str, object]] = []
    schema_coverage: set[str] = set()
    for schema in sorted(schema_values):
        writers = sorted(schema_writers.get(schema, ()))
        validators = sorted(schema_validators.get(schema, ()))
        covered = bool(writers and validators)
        if covered:
            schema_coverage.add(schema)
        schema_rows.append(
            {
                "boundary": schema,
                "boundary_kind": (
                    "VERSION_FORWARD_PERSISTED_OR_TRANSITIVELY_BOUND_SCHEMA"
                ),
                "direct_source_references": sorted(
                    schema_direct_references.get(schema, ())
                ),
                "writer_sites": writers,
                "validator_sites": validators,
                "composition_tested": covered,
            }
        )

    callable_expected = {
        str(row["boundary"]) for row in callable_rows
    }
    schema_expected = {str(row["boundary"]) for row in schema_rows}
    expected = callable_expected | schema_expected
    covered = callable_coverage | schema_coverage
    uncovered = sorted(expected - covered)
    extraneous = sorted(covered - expected)
    if (
        len(callable_rows) != 17
        or len(schema_rows) != 13
        or len(expected) != 30
        or uncovered
        or extraneous
    ):
        raise AssertionError(
            "changed typed boundary composition: "
            f"callable={len(callable_rows)}, schema={len(schema_rows)}, "
            f"uncovered={uncovered!r}, extraneous={extraneous!r}"
        )
    return {
        "derivation": (
            "FINAL_SOURCE_EXPORTS_CROSS_MODULE_TYPES_DOCUMENT_VALIDATORS_"
            "AND_VERSION_FORWARD_SCHEMAS"
        ),
        "denominator_independent_of_runtime_trace": True,
        "source_paths": [
            {
                "module": module,
                "path": source["path"],
                "sha256": source["sha256"],
            }
            for module, source in sorted(sources.items())
        ],
        "changed_callable_or_carrier_boundaries": callable_rows,
        "changed_callable_or_carrier_boundary_count": len(callable_rows),
        "version_forward_schema_boundaries": schema_rows,
        "version_forward_schema_boundary_count": len(schema_rows),
        "changed_typed_boundaries_total": len(expected),
        "changed_typed_boundaries_with_composition_tests": len(covered),
        "uncovered_changed_boundary_count": len(uncovered),
        "uncovered_changed_boundaries": uncovered,
        "extraneous_changed_boundary_count": len(extraneous),
        "extraneous_changed_boundaries": extraneous,
        "result": "PASS",
    }


def _named_node(
    tree: ast.Module, name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == name:
                return node
    raise AssertionError(f"source symbol not found: {name}")


def _class_method(tree: ast.Module, class_name: str, method: str) -> ast.FunctionDef:
    class_node = _named_node(tree, class_name)
    if not isinstance(class_node, ast.ClassDef):
        raise AssertionError(f"not a class: {class_name}")
    for node in class_node.body:
        if isinstance(node, ast.FunctionDef) and node.name == method:
            return node
    raise AssertionError(f"source method not found: {class_name}.{method}")


def _retained_gate_schema_type_mapping(
    tree: ast.Module,
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
) -> list[dict[str, object]]:
    """Map each retained ID to its final source function, types, and schemas."""
    rows: list[dict[str, object]] = []
    for mechanism_id in contract.REQUIRED_MECHANISM_IDS:
        prefix = f"_gate_{mechanism_id.lower()}_"
        matches = [name for name in functions if name.startswith(prefix)]
        if len(matches) != 1:
            raise AssertionError(f"one source gate required for {mechanism_id}")
        name = matches[0]
        node = functions[name]
        source = ast.unparse(node)
        schemas = sorted(
            {
                value.value
                for value in ast.walk(node)
                if isinstance(value, ast.Constant)
                and type(value.value) is str
                and value.value.startswith("pulsarmlx.")
            }
        )
        type_bindings = sorted(
            {
                value.id
                for value in ast.walk(node)
                if isinstance(value, ast.Name)
                and value.id.startswith(
                    ("_Validated", "_Identity", "_Stop", "_Runtime", "Mapping")
                )
            }
        )
        calls = sorted(
            {
                ast.unparse(value.func)
                for value in ast.walk(node)
                if isinstance(value, ast.Call)
            }
        )
        rows.append(
            {
                "mechanism_id": mechanism_id,
                "gate_symbol": name,
                "source_sha256": _sha256(source.encode("utf-8")),
                "schema_literals": schemas,
                "type_bindings": type_bindings,
                "called_validators_or_producers": calls,
            }
        )
    return rows


def _package_start_consumed_gate_relation(tree: ast.Module) -> dict[str, object]:
    """Derive the package-start-to-first-effect relation from AST order."""
    executor = _named_node(tree, "_execute_minimum_gate_path")
    gate = _named_node(tree, "_gate_m001_one_shot_claim")
    production_run = _class_method(tree, "_ProductionCheckpointEffect", "run")
    synthetic_run = _class_method(tree, "_SyntheticCheckpointProvider", "run")
    if not isinstance(executor, (ast.FunctionDef, ast.AsyncFunctionDef)) or not isinstance(
        gate, (ast.FunctionDef, ast.AsyncFunctionDef)
    ):
        raise AssertionError("package-start source functions")

    consumed_assignment_lines: list[int] = []
    fixture_build_lines: list[int] = []
    checkpoint_call_lines: list[int] = []
    for node in ast.walk(executor):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            value = node.value
            names = {
                item.id
                for item in ast.walk(target)
                if isinstance(item, ast.Name)
            }
            if "consumed_gate" in names and isinstance(value, ast.Call):
                if ast.unparse(value.func) == "_gate_m001_one_shot_claim":
                    consumed_assignment_lines.append(node.lineno)
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith(
            "checkpoint_effect.run"
        ):
            if not node.args or ast.unparse(node.args[0]) != "consumed_gate":
                raise AssertionError("checkpoint effect does not consume gate")
            checkpoint_call_lines.append(node.lineno)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == (
            "_build_installed_authority"
        ):
            fixture_build_lines.append(node.lineno)
    if (
        len(fixture_build_lines) != 1
        or len(consumed_assignment_lines) != 1
        or len(checkpoint_call_lines) != 1
    ):
        raise AssertionError("package-start/identity call census")

    calls_in_gate = [
        (node.lineno, ast.unparse(node.func), [ast.unparse(arg) for arg in node.args])
        for node in ast.walk(gate)
        if isinstance(node, ast.Call)
    ]
    consume_lines = [line for line, name, _args in calls_in_gate if name == "_consume_package_start_gate"]
    bank_lines = [
        line
        for line, name, args in calls_in_gate
        if name.endswith("storage.bank_package_start")
        and args[:2] == ["receipt", "stop"]
    ]
    state_lines = [
        line for line, name, _args in calls_in_gate if name.endswith("consume_package_start")
    ]
    if not (
        len(consume_lines) == len(bank_lines) == len(state_lines) == 1
        and consume_lines[0] < bank_lines[0] < state_lines[0]
        and fixture_build_lines[0]
        < consumed_assignment_lines[0]
        < checkpoint_call_lines[0]
    ):
        raise AssertionError(
            "durable start must select the winner before process state and identity"
        )

    effect_guards: list[dict[str, object]] = []
    for owner, method in (
        ("_ProductionCheckpointEffect", production_run),
        ("_SyntheticCheckpointProvider", synthetic_run),
    ):
        ordered_calls = sorted(
            (
                node.lineno,
                ast.unparse(node.func),
                [ast.unparse(arg) for arg in node.args],
            )
            for node in ast.walk(method)
            if isinstance(node, ast.Call)
        )
        guard_lines = [
            line
            for line, name, args in ordered_calls
            if name == "_require_consumed_gate"
            and args[:2] == ["consumed_gate", "authority"]
        ]
        effect_lines = [
            line
            for line, name, _args in ordered_calls
            if name
            in {
                "_run_identity_stage",
                "_ProductionCheckpointEffect().run",
                "self._qualification_interceptor.intercept_physical_call",
                "storage.bank",
                "_bind_identity_stage",
            }
        ]
        if len(guard_lines) != 1 or not effect_lines or guard_lines[0] >= min(effect_lines):
            raise AssertionError(f"consumed-gate guard order: {owner}")
        effect_guards.append(
            {
                "consumer": f"{owner}.run",
                "guard_line": guard_lines[0],
                "first_effect_line": min(effect_lines),
                "consumed_gate_is_first_argument": True,
            }
        )
    return {
        "gate_consumer": "_gate_m001_one_shot_claim",
        "consume_line": consume_lines[0],
        "durable_start_bank_line": bank_lines[0],
        "one_shot_state_consume_line": state_lines[0],
        "synthetic_fixture_build_line": fixture_build_lines[0],
        "executor_consumed_assignment_line": consumed_assignment_lines[0],
        "executor_first_identity_effect_line": checkpoint_call_lines[0],
        "synthetic_fixture_precedes_package_start": True,
        "effect_guards": effect_guards,
        "package_start_without_consumed_gate": 0,
        "result": "PASS",
    }


def _identity_key_census(tree: ast.Module) -> dict[str, object]:
    node = _named_node(tree, "_identities")
    authority = _named_node(tree, "_identity_installed_document")
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise AssertionError("identity derivation function")
    if not isinstance(authority, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise AssertionError("minimum identity authority function")
    expected = (
        "authorization_id",
        "package_attempt_id",
        "primary_event_id",
        "secondary_event_id",
    )
    identity_dicts = [
        value
        for value in ast.walk(node)
        if isinstance(value, ast.Dict)
        and all(isinstance(key, ast.Constant) and type(key.value) is str for key in value.keys)
    ]
    if len(identity_dicts) != 1:
        raise AssertionError("one identity mapping required")
    keys = tuple(str(key.value) for key in identity_dicts[0].keys)
    counts = Counter(keys)
    if set(keys) != set(expected) or any(counts[key] != 1 for key in expected):
        raise AssertionError("canonical package identity key census")
    authority_dicts = [
        value
        for value in ast.walk(authority)
        if isinstance(value, ast.Dict)
        and any(isinstance(key, ast.Constant) and key.value == "schema" for key in value.keys)
    ]
    if len(authority_dicts) != 1:
        raise AssertionError("one minimum identity authority document")
    authority_keys = {
        str(key.value)
        for key in authority_dicts[0].keys
        if isinstance(key, ast.Constant) and type(key.value) is str
    }
    removed_aliases = {
        "event_identity_plan_sha256",
        "producer_capability_path",
        "producer_capability_sha256",
        "primary_candidate_validator_path",
        "primary_candidate_validator_sha256",
        "secondary_candidate_validator_path",
        "secondary_candidate_validator_sha256",
        "identity_candidate_validator_path",
        "identity_candidate_validator_sha256",
        "installed_authorization_sha256",
        "installation_receipt_sha256",
    }
    if authority_keys & removed_aliases:
        raise AssertionError("removed identity ceremony remains normative")
    if not {
        "measured_producer_path",
        "measured_producer_sha256",
        "measured_validator_path",
        "measured_validator_sha256",
    } <= authority_keys:
        raise AssertionError("minimum identity implementation measurements")
    return {
        "identity_derivation_symbol": "_identities",
        "identity_authority_symbol": "_identity_installed_document",
        "canonical_identity_keys": list(keys),
        "key_occurrences": dict(sorted(counts.items())),
        "distinct_identity_key_count": len(counts),
        "package_identity_keys_per_identity": 1,
        "alias_keys": [],
        "identity_authority_field_count": len(authority_keys),
        "identity_plan_compatibility_field": None,
        "identity_plan_compatibility_value": None,
        "identity_plan_is_separately_supplied": False,
        "identity_plan_is_separately_validated": False,
        "removed_identity_ceremony_fields": sorted(removed_aliases),
        "result": "PASS",
    }


def _stage_receipt_binding_census(tree: ast.Module) -> dict[str, object]:
    """Prove stage progress is bound to rederived authority, not a subject SHA."""
    writer = _named_node(tree, "_bank_stage_receipt")
    reader = _named_node(tree, "_derive_durable_stage_progress")
    if not isinstance(writer, (ast.FunctionDef, ast.AsyncFunctionDef)) or not isinstance(
        reader, (ast.FunctionDef, ast.AsyncFunctionDef)
    ):
        raise AssertionError("stage receipt writer/reader source")

    def assigned_value(function: ast.AST, name: str) -> ast.expr:
        values = [
            node.value
            for node in ast.walk(function)
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ]
        if len(values) != 1:
            raise AssertionError(f"one stage receipt assignment: {name}")
        return values[0]

    authority_value = assigned_value(writer, "stage_authority")
    expected_value = assigned_value(reader, "expected_keys")
    if not isinstance(authority_value, ast.Dict):
        raise AssertionError("stage authority source document")
    authority_keys = [
        str(key.value)
        for key in authority_value.keys
        if isinstance(key, ast.Constant) and type(key.value) is str
    ]
    expected_keys = ast.literal_eval(expected_value)
    receipt_keys = {
        "schema",
        *authority_keys,
        "stage_authority_sha256",
        "result",
    }
    if authority_keys != [
        "stage",
        "authorization_id",
        "package_attempt_id",
        "stage_event_id",
        "package_start_sha256",
    ] or expected_keys != receipt_keys:
        raise AssertionError("stage authority exact key census")

    writer_source = ast.unparse(writer)
    reader_source = ast.unparse(reader)
    if (
        "_contract_sha256(stage_authority)" not in writer_source
        or "value.get('stage_authority_sha256')" not in reader_source
        or "_contract_sha256({" not in reader_source
        or "subject_sha256" in writer_source
        or "subject_sha256" in reader_source
    ):
        raise AssertionError("stage authority digest rederivation")
    return {
        "writer": "_bank_stage_receipt",
        "reader": "_derive_durable_stage_progress",
        "authority_keys": authority_keys,
        "receipt_keys": sorted(receipt_keys),
        "digest_field": "stage_authority_sha256",
        "digest_rederived_on_read": True,
        "unvalidated_subject_sha256_present": False,
        "result": "PASS",
    }


def _predicate_ownership_census(
    tree: ast.Module,
) -> dict[str, object]:
    """Derive and own every check on the production path before package start.

    This deliberately uses two different derivations.  A call-graph walk first
    computes the expected production component closure.  A check-site walk then
    inventories guards, raises, assertions, and validator calls in those
    components.  The ownership policy applies to the discovered closure; it is
    not a list of predicates expected to occur.
    """
    function_nodes: dict[str, ast.AST | None] = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    class_nodes = {
        node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
    }
    class_bases = {
        name: tuple(
            base.id for base in node.bases if isinstance(base, ast.Name)
        )
        for name, node in class_nodes.items()
    }
    for class_name, class_node in class_nodes.items():
        function_nodes[f"{class_name}::<construct>"] = None
        for node in class_node.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_nodes[f"{class_name}.{node.name}"] = node

    imports = _local_imports(tree)
    imported_components = {
        alias: f"import:{binding['path']}:{binding['symbol']}"
        for alias, binding in imports.items()
    }
    entry = "execute_event06_minimum_gate_path"
    executor = "_execute_minimum_gate_path"
    executor_node = function_nodes.get(executor)
    if not isinstance(executor_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise AssertionError("minimum-path executor source")
    boundary_lines = [
        node.lineno
        for node in ast.walk(executor_node)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_gate_m001_one_shot_claim"
    ]
    if len(boundary_lines) != 1:
        raise AssertionError("one package-start boundary")
    package_start_line = boundary_lines[0]
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }

    unknown = object()

    def production_value(node: ast.AST) -> object:
        """Evaluate only selectors fixed by the public production entry."""
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return {
                "qualification": None,
                "go": "VALIDATED_COLLAPSED_GO",
                "synthetic": False,
            }.get(node.id, unknown)
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "runtime"
            and node.attr == "scope"
        ):
            return "PRODUCTION"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            value = production_value(node.operand)
            return unknown if value is unknown else not bool(value)
        if isinstance(node, ast.BoolOp):
            values = [production_value(item) for item in node.values]
            if any(value is unknown for value in values):
                return unknown
            return (
                all(bool(value) for value in values)
                if isinstance(node.op, ast.And)
                else any(bool(value) for value in values)
            )
        if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
            left = production_value(node.left)
            right = production_value(node.comparators[0])
            if left is unknown or right is unknown:
                return unknown
            operator = node.ops[0]
            if isinstance(operator, (ast.Eq, ast.Is)):
                return left == right
            if isinstance(operator, (ast.NotEq, ast.IsNot)):
                return left != right
        return unknown

    def active_nodes(symbol: str) -> list[ast.AST]:
        node = function_nodes.get(symbol)
        if node is None:
            return []
        cutoff = package_start_line if symbol == executor else None
        observed: list[ast.AST] = []

        def visit(current: ast.AST) -> None:
            line = getattr(current, "lineno", None)
            if cutoff is not None and line is not None and line >= cutoff:
                return
            observed.append(current)
            if isinstance(current, ast.If):
                visit(current.test)
                selected = production_value(current.test)
                branches = (
                    current.body if selected is True
                    else current.orelse if selected is False
                    else [*current.body, *current.orelse]
                )
                for child in branches:
                    visit(child)
                return
            if isinstance(current, ast.IfExp):
                visit(current.test)
                selected = production_value(current.test)
                if selected is True:
                    visit(current.body)
                elif selected is False:
                    visit(current.orelse)
                else:
                    visit(current.body)
                    visit(current.orelse)
                return
            for child in ast.iter_child_nodes(current):
                visit(child)

        visit(node)
        return observed

    def inherited_method(class_name: str, method_name: str) -> str | None:
        pending = [class_name]
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            symbol = f"{current}.{method_name}"
            if symbol in function_nodes:
                return symbol
            pending.extend(class_bases.get(current, ()))
        return None

    unique_methods: dict[str, str] = {}
    method_counts = Counter(
        symbol.rsplit(".", 1)[1]
        for symbol in function_nodes
        if "." in symbol and "::<construct>" not in symbol
    )
    for symbol in function_nodes:
        if "." not in symbol or "::<construct>" in symbol:
            continue
        method = symbol.rsplit(".", 1)[1]
        if method_counts[method] == 1:
            unique_methods[method] = symbol

    def call_targets(caller: str, call: ast.Call) -> tuple[str, ...]:
        function = call.func
        if isinstance(function, ast.Name):
            name = function.id
            if name in function_nodes and "." not in name:
                return (name,)
            if name in class_nodes:
                targets = [f"{name}::<construct>"]
                for method in ("__new__", "__init__"):
                    resolved = inherited_method(name, method)
                    if resolved is not None:
                        targets.append(resolved)
                return tuple(targets)
            if name in imported_components:
                return (imported_components[name],)
            return ()
        if not isinstance(function, ast.Attribute):
            return ()
        if isinstance(function.value, ast.Name) and function.value.id == "self":
            class_name = caller.split(".", 1)[0] if "." in caller else ""
            resolved = inherited_method(class_name, function.attr)
            return () if resolved is None else (resolved,)
        # Resolve only an unambiguous local method.  Common Mapping/path/effect
        # methods are intentionally not guessed from attribute spelling.
        if function.attr in {
            "get", "items", "keys", "values", "as_dict", "bank", "prepare",
            "run", "primary", "secondary", "record", "fail", "release",
            "read_bytes", "is_file", "is_symlink", "mkdir", "resolve",
        }:
            return ()
        if not isinstance(function.value, ast.Name) or function.value.id in {
            "ast", "hashlib", "inspect", "json", "object", "os", "path",
            "re", "stat", "sys", "threading", "time",
        }:
            return ()
        resolved = unique_methods.get(function.attr)
        return () if resolved is None else (resolved,)

    graph: dict[str, set[str]] = {}
    call_sites: dict[tuple[str, str], list[int]] = {}
    for symbol in function_nodes:
        graph[symbol] = set()
        if symbol.endswith("::<construct>"):
            class_name = symbol.split("::", 1)[0]
            for method in ("__new__", "__init__"):
                resolved = inherited_method(class_name, method)
                if resolved is not None:
                    graph[symbol].add(resolved)
            continue
        for node in active_nodes(symbol):
            if not isinstance(node, ast.Call):
                continue
            for target in call_targets(symbol, node):
                graph[symbol].add(target)
                call_sites.setdefault((symbol, target), []).append(node.lineno)

    expected: set[str] = set()
    pending = [entry]
    while pending:
        symbol = pending.pop()
        if symbol in expected:
            continue
        expected.add(symbol)
        pending.extend(sorted(graph.get(symbol, ()), reverse=True))
    forbidden_production_components = sorted(
        symbol
        for symbol in expected
        if symbol.startswith("_qualification")
        or symbol.startswith("_Synthetic")
        or "._qualification" in symbol
    )

    accepted_owners = frozenset(contract.REQUIRED_MECHANISM_IDS)

    def gate_owner(symbol: str) -> str | None:
        match = re.fullmatch(r"_gate_m(\d{3})_.+", symbol)
        if match is None:
            return None
        mechanism_id = f"M{match.group(1)}"
        return mechanism_id if mechanism_id in accepted_owners else None

    def direct_owner(caller: str, target: str) -> str | None:
        owner = gate_owner(target)
        if owner is not None:
            return owner
        if caller == entry:
            if target == executor:
                return None
            if target == "_production_runtime":
                return "M001"
            if target == "_close_storage_after_outcome":
                return "M004"
            if target in {"_sha", "_authority_profile"}:
                return "M003"
        if caller == executor:
            if target.startswith("_StopBoundary::"):
                return "M004"
            if target == "_validate_fresh_integration_state":
                return "M001"
            if target == "_build_installed_authority":
                return "M013"
            if target == "_package_gate":
                return "M012"
            if target == "_sha":
                return "M003"
        return None

    component_owners: dict[str, set[str]] = {symbol: set() for symbol in expected}
    component_owners[entry].add("M003")
    for caller in (entry, executor):
        for target in sorted(graph.get(caller, ())):
            owner = direct_owner(caller, target)
            if owner is not None:
                component_owners.setdefault(target, set()).add(owner)
    # Gate symbols are self-identifying ownership roots even when the caller is
    # rearranged; this also makes a newly introduced M018-style gate invalid.
    for symbol in expected:
        owner = gate_owner(symbol)
        if owner is not None:
            component_owners[symbol].add(owner)

    changed = True
    while changed:
        changed = False
        for caller in sorted(expected):
            # The two coordinator containers have per-call ownership roots;
            # propagating their inline owner would incorrectly label all work.
            if caller in {entry, executor}:
                continue
            for target in graph.get(caller, ()):
                inherited = component_owners[caller] - component_owners[target]
                if inherited:
                    component_owners[target].update(inherited)
                    changed = True

    # Inline coordinator checks have distinct semantic owners.  The ownership
    # is derived from the identifiers used by each discovered expression.
    def inline_owners(symbol: str, node: ast.AST) -> set[str]:
        if isinstance(node, ast.Call):
            called_owners = {
                owner
                for target in call_targets(symbol, node)
                for owner in (
                    direct_owner(symbol, target),
                    *component_owners.get(target, ()),
                )
                if owner is not None
            }
            if called_owners:
                return called_owners
        if isinstance(node, ast.Raise):
            parent = parents.get(node)
            while parent is not None:
                if isinstance(parent, (ast.If, ast.While)):
                    return inline_owners(symbol, parent.test)
                parent = parents.get(parent)
        if symbol == entry:
            names = {
                item.id for item in ast.walk(node) if isinstance(item, ast.Name)
            }
            if names & {
                "collapsed_go_bytes", "qualification", "_QualificationInvocation",
                "_QUALIFICATION_INVOCATION_SEAL",
            }:
                return {"M003"}
            return set()
        if symbol != executor:
            return set(component_owners.get(symbol, ()))
        names = {
            item.id for item in ast.walk(node) if isinstance(item, ast.Name)
        }
        attrs = {
            item.attr for item in ast.walk(node) if isinstance(item, ast.Attribute)
        }
        if {"package_claim_sha256", "human_decision_sha256"} & (names | attrs):
            return {"M012"}
        if names & {"go", "raw", "_ValidatedCollapsedGo", "_sha"}:
            return {"M003"}
        return set()

    def check_kind(node: ast.AST) -> str | None:
        if isinstance(node, (ast.If, ast.While)):
            return "GUARD_PREDICATE"
        if isinstance(node, ast.Assert):
            return "ASSERTION"
        if isinstance(node, ast.Raise):
            return "EXPLICIT_REJECTION"
        if not isinstance(node, ast.Call):
            return None
        targets = call_targets("", node)
        names = [
            target.rsplit(":", 1)[-1].rsplit(".", 1)[-1]
            for target in targets
        ]
        if any(
            name.startswith(("validate_", "_validate_", "require_", "_require_"))
            or name in {"parse_artifact_bytes", "_parse_artifact_bytes"}
            for name in names
        ):
            return "VALIDATOR_CALL"
        return None

    rows: list[dict[str, object]] = []
    expected_check_sites: set[tuple[str, int, int, str]] = set()
    independently_observed_components: set[str] = set()
    for symbol in sorted(expected):
        if symbol.startswith("import:") or symbol.endswith("::<construct>"):
            independently_observed_components.add(symbol)
            continue
        nodes = active_nodes(symbol)
        independently_observed_components.add(symbol)
        for node in nodes:
            expected_kind: str | None = None
            if isinstance(node, (ast.If, ast.While)):
                expected_kind = "GUARD_PREDICATE"
            elif isinstance(node, ast.Assert):
                expected_kind = "ASSERTION"
            elif isinstance(node, ast.Raise):
                expected_kind = "EXPLICIT_REJECTION"
            elif isinstance(node, ast.Call):
                called_name = ast.unparse(node.func).rsplit(".", 1)[-1]
                if (
                    called_name.startswith(
                        ("validate_", "_validate_", "require_", "_require_")
                    )
                    or called_name in {
                        "parse_artifact_bytes", "_parse_artifact_bytes"
                    }
                ):
                    expected_kind = "VALIDATOR_CALL"
            if expected_kind is not None:
                expected_check_sites.add(
                    (symbol, node.lineno, node.col_offset, expected_kind)
                )
            kind = check_kind(node)
            if kind is None:
                continue
            owners = inline_owners(symbol, node)
            expression_node: ast.AST = node
            if isinstance(node, (ast.If, ast.While, ast.Assert)):
                expression_node = node.test
            elif isinstance(node, ast.Raise) and node.exc is not None:
                expression_node = node.exc
            expression = ast.unparse(expression_node)
            rows.append(
                {
                    "component": symbol,
                    "line": node.lineno,
                    "column": node.col_offset,
                    "check_kind": kind,
                    "source_sha256": _sha256(expression.encode("utf-8")),
                    "owner_mechanisms": sorted(owners),
                }
            )

    observed_check_sites = {
        (
            str(row["component"]), int(row["line"]), int(row["column"]),
            str(row["check_kind"]),
        )
        for row in rows
    }
    missing_check_sites = sorted(expected_check_sites - observed_check_sites)
    extra_check_sites = sorted(observed_check_sites - expected_check_sites)

    # Imported leaves and constructor dispatch nodes are observed separately
    # from their caller edges, so the coverage comparison is not a restatement
    # of the expected call-graph set.
    for caller in sorted(expected):
        for target in graph.get(caller, ()):
            if target in expected and (caller, target) in call_sites:
                independently_observed_components.add(target)

    coordinator_components = {entry, executor}
    unowned_components = sorted(
        symbol
        for symbol in expected - coordinator_components
        if not component_owners.get(symbol)
    )
    unowned_rows = [row for row in rows if not row["owner_mechanisms"]]
    invalid_owner_rows = [
        row
        for row in rows
        if not set(row["owner_mechanisms"]).issubset(accepted_owners)
    ]
    missing_components = sorted(expected - independently_observed_components)
    extra_components = sorted(independently_observed_components - expected)
    unowned_units = {
        *unowned_components,
        *(
            f"{row['component']}:{row['line']}:{row['column']}"
            for row in unowned_rows
        ),
    }
    owner_ids = sorted(
        {
            owner
            for owners in component_owners.values()
            for owner in owners
        }
    )
    result = "PASS" if not (
        forbidden_production_components
        or missing_components
        or extra_components
        or missing_check_sites
        or extra_check_sites
        or unowned_units
        or invalid_owner_rows
    ) else "FAIL"
    return {
        "phase": "PRODUCTION_ENTRY_THROUGH_PRE_PACKAGE_START",
        "production_entry": entry,
        "package_start_boundary_symbol": "_gate_m001_one_shot_claim",
        "package_start_boundary_line": package_start_line,
        "synthetic_or_qualification_components_in_production_closure": (
            forbidden_production_components
        ),
        "expected_component_count": len(expected),
        "expected_components": sorted(expected),
        "observed_component_count": len(independently_observed_components),
        "observed_components": sorted(independently_observed_components),
        "missing_component_count": len(missing_components),
        "missing_components": missing_components,
        "extra_component_count": len(extra_components),
        "extra_components": extra_components,
        "component_ownership": [
            {
                "component": symbol,
                "owner_mechanisms": sorted(component_owners.get(symbol, ())),
                "caller_edges": [
                    {
                        "caller": caller,
                        "source_lines": sorted(call_sites[(caller, symbol)]),
                    }
                    for caller in sorted(expected)
                    if (caller, symbol) in call_sites
                ],
            }
            for symbol in sorted(expected)
        ],
        "accepted_retained_owner_mechanisms": list(contract.REQUIRED_MECHANISM_IDS),
        "observed_owner_mechanisms": owner_ids,
        "expected_predicate_count": len(expected_check_sites),
        "observed_predicate_count": len(observed_check_sites),
        "missing_predicate_count": len(missing_check_sites),
        "missing_predicates": [
            {
                "component": symbol, "line": line, "column": column,
                "check_kind": kind,
            }
            for symbol, line, column, kind in missing_check_sites
        ],
        "extra_predicate_count": len(extra_check_sites),
        "extra_predicates": [
            {
                "component": symbol, "line": line, "column": column,
                "check_kind": kind,
            }
            for symbol, line, column, kind in extra_check_sites
        ],
        "owned_predicate_rows": rows,
        "owned_predicate_count": len(rows) - len(unowned_rows),
        "unowned_predicate_count": len(unowned_rows),
        "unowned_predicates": unowned_rows,
        "unowned_component_count": len(unowned_components),
        "unowned_components": unowned_components,
        "invalid_owner_row_count": len(invalid_owner_rows),
        "new_independently_enforceable_mechanisms": len(unowned_units),
        "no_eighteenth_required_gate": not unowned_units,
        "result": result,
    }


def _synthetic_seam_census(tree: ast.Module, public_exports: tuple[str, ...]) -> dict[str, object]:
    seam_classes = sorted(
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name.startswith("_Synthetic")
    )
    expected = [
        "_SyntheticCheckpointProvider",
        "_SyntheticNumericalProvider",
        "_SyntheticStorageBinding",
    ]
    if seam_classes != expected:
        raise AssertionError("exactly three synthetic seams required")
    seam_rows: list[dict[str, object]] = []
    for class_name in seam_classes:
        new = _class_method(tree, class_name, "__new__")
        source = ast.unparse(new)
        sealed = "seal is not _SYNTHETIC_" in source
        if not sealed or class_name in public_exports:
            raise AssertionError(f"private sealed seam: {class_name}")
        seam_rows.append(
            {
                "class": class_name,
                "private": class_name.startswith("_") and class_name not in public_exports,
                "seal_guarded_constructor": sealed,
            }
        )
    carrier = _named_node(tree, "_QualificationInvocation")
    if not isinstance(carrier, ast.ClassDef):
        raise AssertionError("qualification carrier")
    fields = [
        node.target.id
        for node in carrier.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    ]
    context_bindings = [
        target.id
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and isinstance(node.value, ast.Call)
        and ast.unparse(node.value.func) == "ContextVar"
        for target in [node.target]
    ]
    if fields != ["seal", "runtime", "now_unix_ns", "collapsed_go_sha256"]:
        raise AssertionError("qualification carrier field census")
    if context_bindings != ["_QUALIFICATION_INVOCATION"]:
        raise AssertionError("qualification ContextVar census")
    signature = inspect.signature(path.execute_event06_minimum_gate_path)
    return {
        "seam_count": len(seam_rows),
        "seams": seam_rows,
        "all_seams_private": all(row["private"] for row in seam_rows),
        "all_seams_seal_guarded": all(
            row["seal_guarded_constructor"] for row in seam_rows
        ),
        "contextvar_bindings": context_bindings,
        "contextvar_carrier_type": "_QualificationInvocation",
        "contextvar_carrier_fields": fields,
        "contextvar_is_public_export": "_QUALIFICATION_INVOCATION" in public_exports,
        "contextvar_is_public_parameter": any(
            parameter.name in {"runtime", "storage", "checkpoint_effect", "numerical_effect"}
            for parameter in signature.parameters.values()
        ),
        "contextvar_classification": "SEALED_CARRIER_FOR_EXACTLY_THREE_PRIVATE_SEAMS_NOT_A_FOURTH_SEAM",
        "public_effect_injection_inputs": 0,
        "result": "PASS",
    }


def _dependency_resolution_mapping(
    reachable_source: str,
    reachable_symbols: set[str],
    active_components: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Prove that all 16 historical hard dependencies are non-gating.

    Component terms are checked against dynamically observed producer/consumer
    callables when available.  Source terms are checked against the normalized
    AST for the mandatory entry closure, which detects renamed or nested
    equivalents rather than relying only on the old function names.
    """
    normalized_source = " ".join(reachable_source.lower().split())
    component_names = [
        str(item["component"]).lower() for item in (active_components or [])
    ]
    rows: list[dict[str, object]] = []
    unresolved: list[str] = []
    for mechanism_id in contract.IMPLEMENTATION_DEPENDENCY_MECHANISM_IDS:
        definition = _DEPENDENCY_EQUIVALENCE_PROBES.get(mechanism_id)
        if definition is None:
            raise AssertionError(f"missing dependency equivalence probe: {mechanism_id}")
        gate_symbols = sorted(
            symbol
            for symbol in reachable_symbols
            if symbol.startswith(f"_gate_{mechanism_id.lower()}_")
        )
        source_matches = sorted(
            term
            for term in definition["forbidden_source_terms"]
            if str(term).lower() in normalized_source
        )
        component_matches = sorted(
            term
            for term in definition["forbidden_component_terms"]
            if any(str(term).lower() in name for name in component_names)
        )
        separate_predicate = bool(gate_symbols or source_matches or component_matches)
        if separate_predicate:
            unresolved.append(mechanism_id)
        rows.append(
            {
                "mechanism_id": mechanism_id,
                "semantic_equivalence_class": definition["semantic"],
                "resolution": definition["resolution"],
                "retained_by": list(definition["retained_by"]),
                "independent_gate_symbols": gate_symbols,
                "normalized_source_equivalent_matches": source_matches,
                "active_indirect_component_matches": component_matches,
                "separate_normative_dependency_present": separate_predicate,
                "resolved": not separate_predicate,
            }
        )
    if [row["mechanism_id"] for row in rows] != list(
        contract.IMPLEMENTATION_DEPENDENCY_MECHANISM_IDS
    ):
        raise AssertionError("implementation dependency order")
    return {
        "mapped": len(rows),
        "expected": len(contract.IMPLEMENTATION_DEPENDENCY_MECHANISM_IDS),
        "rows": rows,
        "remaining": len(unresolved),
        "remaining_ids": unresolved,
        "renamed_nested_indirect_equivalents_checked": True,
        "result": "PASS" if not unresolved else "FAIL",
    }


def _source_derived_public_path_expectation() -> dict[str, object]:
    """Derive the profiled-path denominator without observing an execution.

    The denominator deliberately covers the public/coordinator roots, every
    retained gate reached from that root, and repository-local producer or
    consumer functions imported directly by the reachable composition.  The
    three effect seams remain outside this production-component denominator.
    The real V12 identity producer and evidence validator reached behind the
    checkpoint seam, and the real result-bundle producer reached behind the
    numerical seam, are included because they are production authorities rather
    than fixture implementations.
    """
    source_raw = _PATH_SOURCE.read_bytes()
    source = source_raw.decode("utf-8")
    tree = ast.parse(source, filename=str(_PATH_SOURCE))
    functions, graph = _local_call_graph(tree)
    exports = _literal_all(tree)
    if exports != _PUBLIC_EXPORTS:
        raise AssertionError("exact execution and closeout public exports")
    entry = _PUBLIC_EXECUTION_ENTRY
    reached = _reachable(graph, entry)
    executors = sorted(
        target
        for target in graph.get(entry, ())
        if target.startswith("_execute_") and target.endswith("minimum_gate_path")
    )
    if executors != ["_execute_minimum_gate_path"]:
        raise AssertionError("one source-derived public-path coordinator")
    executor = executors[0]
    gates = sorted(
        symbol
        for symbol in reached
        if re.fullmatch(r"_gate_m\d{3}_.+", symbol) is not None
    )
    if [f"M{int(symbol[7:10]):03d}" for symbol in gates] != list(
        contract.REQUIRED_MECHANISM_IDS
    ):
        raise AssertionError("profiled-path retained-gate source closure")

    expected: dict[str, dict[str, object]] = {}

    def add_local(symbol: str, kind: str) -> None:
        node = functions.get(symbol)
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raise AssertionError(f"profiled local component: {symbol}")
        component = f"{_PATH_SOURCE.stem}.{symbol}"
        expected[component] = {
            "component": component,
            "kind": kind,
            "module": _PATH_SOURCE.stem,
            "path": _PATH_SOURCE.relative_to(_ROOT).as_posix(),
            "first_line": node.lineno,
            "source_sha256": _sha256(source_raw),
        }

    add_local(entry, "PUBLIC_ENTRY")
    add_local(executor, "ROOT_COORDINATOR")
    for gate in gates:
        add_local(gate, "RETAINED_GATE")

    class_nodes = {
        node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
    }
    checkpoint_effect = class_nodes.get("_ProductionCheckpointEffect")
    if not isinstance(checkpoint_effect, ast.ClassDef):
        raise AssertionError("production checkpoint effect source")
    checkpoint_run = next(
        (
            node
            for node in checkpoint_effect.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "run"
        ),
        None,
    )
    if not isinstance(checkpoint_run, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise AssertionError("production checkpoint pre-open boundary")
    checkpoint_component = (
        f"{_PATH_SOURCE.stem}._ProductionCheckpointEffect.run"
    )
    expected[checkpoint_component] = {
        "component": checkpoint_component,
        "kind": "PHYSICAL_PREOPEN_BOUNDARY",
        "module": _PATH_SOURCE.stem,
        "path": _PATH_SOURCE.relative_to(_ROOT).as_posix(),
        "first_line": checkpoint_run.lineno,
        "source_sha256": _sha256(source_raw),
    }

    imports = _local_imports(tree)
    # Source nodes whose direct imported function calls form the exercised
    # producer/consumer boundary set.  This is an AST reachability result, not
    # a copy of the dynamic trace.
    boundary_nodes: list[ast.AST] = [functions[name] for name in sorted(reached)]
    boundary_nodes.append(checkpoint_run)
    for class_name, class_node in sorted(class_nodes.items()):
        if class_name.startswith(("_Qualification", "_Synthetic")):
            continue
        if class_name in {"_ProductionCheckpointEffect", "_ProductionNumericalEffect"}:
            # These are interposed effect boundaries.  The checkpoint run method
            # is represented explicitly above because its physical identity
            # producer now executes on graph-owned synthetic files; the real
            # numerical targets remain interposed.
            continue
        boundary_nodes.extend(
            node
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        )

    # The numerical seam still banks through the real V11 result-bundle
    # producer.  Discover that imported producer call from source while
    # excluding the synthetic class itself from the denominator.
    synthetic_numerical = class_nodes.get("_SyntheticNumericalProvider")
    if isinstance(synthetic_numerical, ast.ClassDef):
        boundary_nodes.extend(
            node
            for node in synthetic_numerical.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_bank"
        )

    profiled_direct_aliases = {
        call.func.id
        for node in boundary_nodes
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id in imports
    }
    closeout_reached = _reachable(graph, _PUBLIC_CLOSEOUT_ENTRY)
    closeout_direct_aliases = {
        call.func.id
        for name in closeout_reached
        for call in ast.walk(functions[name])
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id in imports
    }
    nonprofiled_closeout_aliases = (
        closeout_direct_aliases - profiled_direct_aliases
    )

    production_only_aliases: set[str] = set()
    for class_name in ("_ProductionNumericalEffect",):
        class_node = class_nodes.get(class_name)
        if not isinstance(class_node, ast.ClassDef):
            continue
        for call in (
            node for node in ast.walk(class_node) if isinstance(node, ast.Call)
        ):
            if isinstance(call.func, ast.Name) and call.func.id in imports:
                production_only_aliases.add(call.func.id)
    expected_external: set[str] = set()
    tracked_external_universe: set[str] = set()
    external_metadata: dict[str, dict[str, object]] = {}
    external_metadata_by_component: dict[str, dict[str, object]] = {}
    external_graphs: dict[str, dict[str, set[str]]] = {}
    for alias, binding in sorted(imports.items()):
        if alias in nonprofiled_closeout_aliases:
            continue
        symbol = str(binding["symbol"])
        if symbol == "*":
            continue
        target_path = _ROOT / str(binding["path"])
        target_raw = target_path.read_bytes()
        target_tree = ast.parse(target_raw, filename=str(target_path))
        _, target_graph = _local_call_graph(target_tree)
        external_graphs[str(binding["module"])] = target_graph
        target_node = next(
            (
                node
                for node in target_tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == symbol
            ),
            None,
        )
        if target_node is None:
            # Imported classes and constants are implementation support rather
            # than direct producer/consumer function boundaries.
            continue
        component = f"{binding['module']}.{symbol}"
        tracked_external_universe.add(component)
        metadata = {
            "component": component,
            "kind": "IMPORTED_PRODUCER_CONSUMER_BOUNDARY",
            "module": str(binding["module"]),
            "source_symbol": symbol,
            "path": str(binding["path"]),
            "first_line": target_node.lineno,
            "source_sha256": _sha256(target_raw),
        }
        external_metadata[alias] = metadata
        external_metadata_by_component[component] = metadata

    for node in boundary_nodes:
        for call in (item for item in ast.walk(node) if isinstance(item, ast.Call)):
            if not isinstance(call.func, ast.Name):
                continue
            alias = call.func.id
            if alias in production_only_aliases or alias not in external_metadata:
                continue
            metadata = external_metadata[alias]
            component = str(metadata["component"])
            expected_external.add(component)
            expected[component] = dict(metadata)

    # Imported producer/consumer functions are typed composition boundaries,
    # not isolated trace labels.  Derive the closure between those boundaries
    # from each imported module's own call graph.  This catches a validator
    # delegating to another imported validator without copying the observed
    # runtime trace into a handwritten expected census.  Restricting the walk
    # to functions explicitly imported by the production composer keeps
    # implementation-private helpers outside this boundary denominator.
    direct_external = set(expected_external)
    composition_edges: set[tuple[str, str]] = set()
    pending_external = sorted(direct_external, reverse=True)
    while pending_external:
        caller_component = pending_external.pop()
        caller_metadata = external_metadata_by_component.get(caller_component)
        if caller_metadata is None:
            raise AssertionError("imported boundary source metadata")
        module = str(caller_metadata["module"])
        symbol = str(caller_metadata["source_symbol"])
        graph_for_module = external_graphs.get(module)
        if graph_for_module is None or symbol not in graph_for_module:
            raise AssertionError("imported boundary source graph")
        for callee_symbol in sorted(graph_for_module[symbol]):
            callee_component = f"{module}.{callee_symbol}"
            if callee_component not in tracked_external_universe:
                continue
            composition_edges.add((caller_component, callee_component))
            if callee_component in expected_external:
                continue
            callee_metadata = external_metadata_by_component.get(callee_component)
            if callee_metadata is None:
                raise AssertionError("composed boundary source metadata")
            expected_external.add(callee_component)
            expected[callee_component] = dict(callee_metadata)
            pending_external.append(callee_component)

    transitive_external = expected_external - direct_external

    tracked_local_universe = {
        f"{_PATH_SOURCE.stem}.{name}"
        for name in functions
        if name in {entry, executor}
        or re.fullmatch(r"_gate_m\d{3}_.+", name) is not None
    }
    tracked_local_universe.add(checkpoint_component)
    expectation_rows = sorted(
        expected.values(), key=lambda item: str(item["component"])
    )
    return {
        "derivation": "AST_PUBLIC_ROOT_REACHABILITY_AND_DIRECT_LOCAL_IMPORT_CALLS",
        "source_path": _PATH_SOURCE.relative_to(_ROOT).as_posix(),
        "source_sha256": _sha256(source_raw),
        "expected_components": expectation_rows,
        "expected_component_names": sorted(expected),
        "expected_external_boundary_names": sorted(expected_external),
        "direct_external_boundary_names": sorted(direct_external),
        "transitive_external_boundary_names": sorted(transitive_external),
        "transitive_external_boundary_count": len(transitive_external),
        "source_derived_composition_edges": [
            {"caller": caller, "callee": callee}
            for caller, callee in sorted(composition_edges)
        ],
        "composition_derivation": (
            "DIRECT_IMPORT_CALLS_PLUS_IMPORTED_FUNCTION_LOCAL_CALL_GRAPH"
        ),
        "tracked_component_universe": sorted(
            tracked_local_universe | tracked_external_universe
        ),
        "interposed_physical_boundary_aliases": sorted(production_only_aliases),
        "excluded_nonprofiled_closeout_aliases": sorted(
            nonprofiled_closeout_aliases
        ),
    }


def _profiled_public_path(
    operation: Callable[[], dict[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    """Compare one dry-run trace with an independently source-derived set."""
    expectation = _source_derived_public_path_expectation()
    previous = sys.getprofile()
    called: dict[tuple[str, str, int], dict[str, object]] = {}
    source_cache: dict[str, Path | None] = {}
    qualification_source = Path(__file__).resolve(strict=True)

    def profiler(frame: object, event: str, _argument: object) -> None:
        if event != "call":
            return
        code = frame.f_code
        filename = str(code.co_filename)
        if filename not in source_cache:
            try:
                source_cache[filename] = Path(filename).resolve(strict=True)
            except (FileNotFoundError, OSError):
                source_cache[filename] = None
        source_path = source_cache[filename]
        if source_path is None:
            return
        if source_path.parent != _RESEARCH_ROOT or source_path == qualification_source:
            return
        qualname = str(getattr(code, "co_qualname", code.co_name))
        if "<" in qualname:
            return
        module = source_path.stem
        key = (module, qualname, int(code.co_firstlineno))
        called[key] = {
            "component": f"{module}.{qualname}",
            "module": module,
            "path": source_path.relative_to(_ROOT).as_posix(),
            "first_line": int(code.co_firstlineno),
        }

    sys.setprofile(profiler)
    try:
        result = operation()
    finally:
        sys.setprofile(previous)

    all_components = sorted(called.values(), key=lambda item: str(item["component"]))
    qualification_support_prefixes = (
        "f017_event06_minimum_gate_path_v1._qualification",
        "f017_event06_minimum_gate_path_v1._invoke_public_qualification",
        "f017_event06_minimum_gate_path_v1._run_no_access_qualification",
        "f017_event06_minimum_gate_path_v1._run_preopen_intercept",
    )
    qualification_carrier_components = {
        "f017_checkpoint_identity_producer_v12._bind_qualification_root_descriptor",
        "f017_checkpoint_identity_producer_v12._reset_qualification_root_descriptor",
    }
    seam_qualnames = {
        "_SyntheticStorageBinding",
        "_SyntheticCheckpointProvider",
        "_SyntheticNumericalProvider",
    }
    production: list[dict[str, object]] = []
    qualification_support: list[dict[str, object]] = []
    synthetic_seam_calls: list[dict[str, object]] = []
    for item in all_components:
        component = str(item["component"])
        qualname = component.split(".", 1)[1] if "." in component else component
        owner = qualname.split(".", 1)[0]
        module = str(item["module"])
        if (
            component.startswith(qualification_support_prefixes)
            or owner.startswith("_Qualification")
        ):
            qualification_support.append(item)
        elif (
            owner in seam_qualnames
            or component in qualification_carrier_components
            or "fixture" in module.lower()
            or module.startswith("qualify_")
        ):
            synthetic_seam_calls.append(item)
        else:
            production.append(item)
    expected_names = set(expectation["expected_component_names"])
    tracked_universe = set(expectation["tracked_component_universe"])
    observed_names = {str(item["component"]) for item in production}
    exercised_names = sorted(expected_names & observed_names)
    missing_names = sorted(expected_names - observed_names)
    unexpected_names = sorted((observed_names & tracked_universe) - expected_names)
    transitive_boundary_names = set(
        expectation["transitive_external_boundary_names"]
    )
    transitive_boundary_exercised = sorted(
        transitive_boundary_names & observed_names
    )
    transitive_boundary_uncovered = sorted(
        transitive_boundary_names - observed_names
    )
    active_modules: dict[str, list[str]] = {}
    for item in production:
        active_modules.setdefault(str(item["module"]), []).append(
            str(item["component"])
        )
    trace = {
        "production_component_count": len(production),
        "production_components_exercised": production,
        "source_derived_expectation": expectation,
        "source_derived_expected_component_count": len(expected_names),
        "source_derived_exercised_component_count": len(exercised_names),
        "source_derived_exercised_components": exercised_names,
        "source_derived_missing_component_count": len(missing_names),
        "source_derived_missing_components": missing_names,
        "source_derived_unexpected_component_count": len(unexpected_names),
        "source_derived_unexpected_components": unexpected_names,
        "source_derived_transitive_boundary_count": len(
            transitive_boundary_names
        ),
        "source_derived_transitive_boundaries_exercised": (
            transitive_boundary_exercised
        ),
        "source_derived_transitive_boundaries_uncovered": (
            transitive_boundary_uncovered
        ),
        "source_derived_transitive_boundary_composition": (
            f"{len(transitive_boundary_exercised)}/"
            f"{len(transitive_boundary_names)}"
        ),
        "production_components_exercised_ratio": (
            f"{len(exercised_names)}/{len(expected_names)}"
        ),
        "active_imported_producer_consumer_module_count": len(active_modules),
        "active_imported_producer_consumer_modules": [
            {"module": module, "called_components": sorted(components)}
            for module, components in sorted(active_modules.items())
        ],
        "qualification_support_components": qualification_support,
        "synthetic_seam_calls": synthetic_seam_calls,
        "actual_call_trace_not_handwritten_census": True,
        "expected_denominator_independent_of_observed_profile": True,
        "result": (
            "PASS"
            if not missing_names
            and not unexpected_names
            and not transitive_boundary_uncovered
            else "FAIL"
        ),
    }
    if missing_names or unexpected_names or transitive_boundary_uncovered:
        raise AssertionError(
            "source-derived public path mismatch: "
            f"missing={missing_names!r}, unexpected={unexpected_names!r}"
        )
    if not production or not any(
        item["component"]
        == "f017_event06_minimum_gate_path_v1.execute_event06_minimum_gate_path"
        for item in production
    ):
        raise AssertionError("public production entry absent from component trace")
    return result, trace


def _superseded_surface_census() -> dict[str, object]:
    exports_by_path: dict[str, list[str]] = {}
    bypasses: list[str] = []
    rows: list[dict[str, object]] = []
    source_discovered_effectful_roots: list[dict[str, object]] = []
    for relative in _SUPERSEDED_SURFACE_SOURCES:
        tree = ast.parse((_ROOT / relative).read_text(encoding="utf-8"))
        exports = _declared_or_implicit_exports(tree)
        exports_by_path[relative] = list(exports)

        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        local_graph = {
            name: {
                call.func.id
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id in functions
            }
            for name, node in functions.items()
        }
        direct_effects: dict[str, set[str]] = {}
        for name, node in functions.items():
            effects: set[str] = set()
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                callee = ast.unparse(call.func)
                leaf = (
                    call.func.attr
                    if isinstance(call.func, ast.Attribute)
                    else call.func.id
                    if isinstance(call.func, ast.Name)
                    else callee
                )
                if leaf in _IRREVERSIBLE_EFFECT_CALLEES:
                    effects.add(callee)
            direct_effects[name] = effects

        for name in sorted(functions):
            if name.startswith("_") or "qualification" in name.lower():
                continue
            reachable = _reachable(local_graph, name)
            effects = sorted(
                {
                    effect
                    for symbol in reachable
                    for effect in direct_effects.get(symbol, set())
                }
            )
            if effects:
                source_discovered_effectful_roots.append(
                    {
                        "path": relative,
                        "symbol": name,
                        "reachable_irreversible_effect_calls": effects,
                    }
                )
        module = importlib.import_module(Path(relative).stem)
        for symbol, private_symbol in _SUPERSEDED_EFFECTFUL_ENTRYPOINTS.get(
            relative, {}
        ).items():
            public_node = _named_node(tree, symbol)
            if not isinstance(public_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                raise AssertionError(f"superseded function shape: {relative}:{symbol}")
            body = list(public_node.body)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and type(body[0].value.value) is str
            ):
                body.pop(0)
            while body and isinstance(body[0], (ast.Delete, ast.Pass)):
                body.pop(0)
            first_effect_is_raise = bool(body and isinstance(body[0], ast.Raise))
            private_node_present = any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == private_symbol
                for node in tree.body
            )
            public_callable = getattr(module, symbol)
            signature = inspect.signature(public_callable)
            args: list[object] = []
            kwargs: dict[str, object] = {}
            for parameter in signature.parameters.values():
                if parameter.kind in {
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                }:
                    args.append(object())
                elif parameter.kind is inspect.Parameter.KEYWORD_ONLY:
                    kwargs[parameter.name] = object()
                elif parameter.kind not in {
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                }:
                    raise AssertionError(
                        f"generic superseded entrypoint: {relative}:{symbol}"
                    )
            runtime_fail_closed = False
            try:
                public_callable(*args, **kwargs)
            except RuntimeError as exc:
                runtime_fail_closed = str(exc).startswith(
                    "superseded by F017 Sequence 39"
                )
            row = {
                "path": relative,
                "symbol": symbol,
                "closure_class": "SEQUENCE39_EXPLICIT_TOMBSTONE",
                "exported": symbol in exports,
                "first_effect_is_raise": first_effect_is_raise,
                "runtime_fail_closed_before_effect": runtime_fail_closed,
                "private_qualification_symbol": private_symbol,
                "private_qualification_symbol_present": private_node_present,
                "private_qualification_symbol_exported": private_symbol in exports,
            }
            rows.append(row)
            if not (
                not row["exported"]
                and first_effect_is_raise
                and runtime_fail_closed
                and private_node_present
                and not row["private_qualification_symbol_exported"]
            ):
                bypasses.append(f"{relative}:{symbol}")
        for symbol in _INTRINSICALLY_FAIL_CLOSED_ENTRYPOINTS.get(relative, ()):
            public_node = _named_node(tree, symbol)
            if not isinstance(public_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                raise AssertionError(f"intrinsic fail-closed shape: {relative}:{symbol}")
            effect_calls = sorted(
                {
                    ast.unparse(call.func)
                    for call in ast.walk(public_node)
                    if isinstance(call, ast.Call)
                    and any(
                        token in ast.unparse(call.func).lower()
                        for token in (
                            "os.open",
                            "openat",
                            "write_bytes",
                            "write_text",
                            "_commit_bound",
                            "commit_synthetic",
                        )
                    )
                }
            )
            public_callable = getattr(module, symbol)
            signature = inspect.signature(public_callable)
            args: list[object] = []
            kwargs: dict[str, object] = {}
            for parameter in signature.parameters.values():
                if parameter.kind in {
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                }:
                    args.append(object())
                elif parameter.kind is inspect.Parameter.KEYWORD_ONLY:
                    kwargs[parameter.name] = object()
            runtime_fail_closed = False
            try:
                public_callable(*args, **kwargs)
            except Exception:
                runtime_fail_closed = True
            row = {
                "path": relative,
                "symbol": symbol,
                "closure_class": "HISTORICAL_INTRINSIC_FAIL_CLOSED",
                "exported": symbol in exports,
                "first_effect_is_raise": not effect_calls,
                "runtime_fail_closed_before_effect": runtime_fail_closed,
                "private_qualification_symbol": None,
                "private_qualification_symbol_present": None,
                "private_qualification_symbol_exported": None,
                "effect_calls": effect_calls,
            }
            rows.append(row)
            if effect_calls or not runtime_fail_closed:
                bypasses.append(f"{relative}:{symbol}")
    uncovered_effectful_roots = [
        row
        for row in source_discovered_effectful_roots
        if row["symbol"]
        not in _SUPERSEDED_EFFECTFUL_ENTRYPOINTS.get(str(row["path"]), {})
        and row["symbol"]
        not in _INTRINSICALLY_FAIL_CLOSED_ENTRYPOINTS.get(str(row["path"]), ())
    ]
    if uncovered_effectful_roots:
        bypasses.extend(
            f"{row['path']}:{row['symbol']}"
            for row in uncovered_effectful_roots
        )
    return {
        "sources": list(_SUPERSEDED_SURFACE_SOURCES),
        "exports_by_source": exports_by_path,
        "effectful_entrypoint_rows": rows,
        "effectful_entrypoints_checked": len(rows),
        "sequence39_explicit_tombstones": sum(
            row["closure_class"] == "SEQUENCE39_EXPLICIT_TOMBSTONE"
            for row in rows
        ),
        "historical_intrinsic_fail_closed": sum(
            row["closure_class"] == "HISTORICAL_INTRINSIC_FAIL_CLOSED"
            for row in rows
        ),
        "source_discovered_effectful_public_roots": (
            source_discovered_effectful_roots
        ),
        "source_discovered_effectful_public_root_count": len(
            source_discovered_effectful_roots
        ),
        "uncensused_effectful_public_roots": uncovered_effectful_roots,
        "uncensused_effectful_public_root_count": len(
            uncovered_effectful_roots
        ),
        "irreversible_effect_callee_vocabulary": sorted(
            _IRREVERSIBLE_EFFECT_CALLEES
        ),
        "callable_legacy_or_superseded_bypasses": len(bypasses),
        "bypasses": bypasses,
    }


def source_derived_closure(
    active_components: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Derive the mandatory gate and public-surface census from final source."""
    source = _PATH_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions, graph = _local_call_graph(tree)
    public_exports = _literal_all(tree)
    if public_exports != _PUBLIC_EXPORTS:
        raise AssertionError("minimum path must expose execution and closeout")
    public = _PUBLIC_EXECUTION_ENTRY
    reached = _reachable(graph, public)
    gate_symbols = sorted(
        symbol
        for symbol in reached
        if (
            symbol.startswith("_gate_m")
            and len(symbol) > 10
            and symbol[7:10].isdigit()
            and symbol[10] == "_"
        )
    )
    gate_ids = [f"M{int(symbol[7:10]):03d}" for symbol in gate_symbols]
    required = list(contract.REQUIRED_MECHANISM_IDS)
    extra = sorted(set(gate_ids) - set(required))
    uncovered = sorted(set(required) - set(gate_ids))

    reachable_source = "\n".join(ast.unparse(functions[name]) for name in sorted(reached))
    removed_still_gating = [
        mechanism_id
        for mechanism_id in contract.REMOVED_MECHANISM_IDS
        if mechanism_id in reachable_source.upper()
        or f"_gate_{mechanism_id.lower()}" in reachable_source
    ]
    dependency_mapping = _dependency_resolution_mapping(
        reachable_source, reached, active_components
    )
    optional_mandatory = [
        mechanism_id
        for mechanism_id in contract.OPTIONAL_NON_GATING_MECHANISM_IDS
        if f"_gate_{mechanism_id.lower()}" in reachable_source
    ]

    signature = inspect.signature(path.execute_event06_minimum_gate_path)
    parameters = tuple(signature.parameters.values())
    closeout_signature = inspect.signature(
        path.closeout_interrupted_event06_minimum_gate_path
    )
    closeout_parameters = tuple(closeout_signature.parameters.values())
    prohibited_parameters = [
        parameter.name
        for parameter in parameters
        if parameter.kind
        in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
        or any(
            token in parameter.name.lower()
            for token in _FORBIDDEN_PUBLIC_PARAMETER_TOKENS
        )
    ]
    prohibited_closeout_parameters = [
        parameter.name
        for parameter in closeout_parameters
        if parameter.kind
        in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
        or any(
            token in parameter.name.lower()
            for token in _FORBIDDEN_PUBLIC_PARAMETER_TOKENS
        )
    ]
    if tuple(parameter.name for parameter in parameters) != ("collapsed_go_bytes",):
        raise AssertionError("public production signature")
    if tuple(parameter.name for parameter in closeout_parameters) != (
        "collapsed_go_bytes",
    ):
        raise AssertionError("public nonexecuting closeout signature")

    closeout_reached = _reachable(graph, _PUBLIC_CLOSEOUT_ENTRY)
    closeout_calls = sorted({
        ast.unparse(call.func)
        for symbol in closeout_reached
        for call in ast.walk(functions[symbol])
        if isinstance(call, ast.Call)
    })
    forbidden_closeout_calls = sorted({
        call
        for call in closeout_calls
        if call
        in {
            "_execute_minimum_gate_path",
            "_run_identity_stage",
            "_execute_primary_target",
            "_execute_secondary_target",
            "_bank_output_bundle",
        }
        or call.endswith(
            (
                ".checkpoint_effect.run",
                ".numerical_effect.primary",
                ".numerical_effect.secondary",
            )
        )
    })
    closeout_gate_symbols = sorted(
        symbol
        for symbol in closeout_reached
        if re.fullmatch(r"_gate_m\d{3}_.+", symbol) is not None
    )
    identity_success_leaves = _identity_success_leaf_census(tree)

    superseded = _superseded_surface_census()
    import_inventory = _recursive_local_import_inventory()
    package_start_relation = _package_start_consumed_gate_relation(tree)
    identity_keys = _identity_key_census(tree)
    stage_receipt_binding = _stage_receipt_binding_census(tree)
    changed_typed_boundaries = _changed_typed_boundary_census()
    predicate_ownership = _predicate_ownership_census(tree)
    seams = _synthetic_seam_census(tree, public_exports)
    gate_schema_types = _retained_gate_schema_type_mapping(tree, functions)
    report = {
        "source_path": _PATH_SOURCE.relative_to(_ROOT).as_posix(),
        "public_production_exports": list(public_exports),
        "public_execution_exports": [_PUBLIC_EXECUTION_ENTRY],
        "public_nonexecuting_closeout_exports": [_PUBLIC_CLOSEOUT_ENTRY],
        "public_signature_parameters": [parameter.name for parameter in parameters],
        "public_closeout_signature_parameters": [
            parameter.name for parameter in closeout_parameters
        ],
        "public_raw_identity_inputs": 0,
        "public_storage_location_inputs": 0,
        "prohibited_public_parameters": prohibited_parameters,
        "prohibited_public_closeout_parameters": (
            prohibited_closeout_parameters
        ),
        "closeout_reachable_symbol_count": len(closeout_reached),
        "closeout_reachable_symbols": sorted(closeout_reached),
        "closeout_execution_entry_reachable": (
            _PUBLIC_EXECUTION_ENTRY in closeout_reached
        ),
        "closeout_gate_symbols": closeout_gate_symbols,
        "closeout_effectful_execution_calls": forbidden_closeout_calls,
        "closeout_is_nonexecuting": (
            _PUBLIC_EXECUTION_ENTRY not in closeout_reached
            and not closeout_gate_symbols
            and not forbidden_closeout_calls
        ),
        "reachable_symbol_count": len(reached),
        "reachable_symbols": sorted(reached),
        "local_call_edges": [
            {"caller": caller, "callee": callee}
            for caller in sorted(reached)
            for callee in sorted(graph.get(caller, set()) & reached)
        ],
        "required_gate_symbols": gate_symbols,
        "required_gate_ids": gate_ids,
        "required_gates_enforced": f"{len(gate_ids)}/17",
        "extra_required_gates": len(extra),
        "extra_gate_ids": extra,
        "uncovered_required_gates": len(uncovered),
        "uncovered_gate_ids": uncovered,
        "removed_mechanisms_still_gating": len(removed_still_gating),
        "removed_mechanism_ids_still_gating": removed_still_gating,
        "implementation_dependency_resolution": dependency_mapping,
        "implementation_dependencies_remaining": dependency_mapping["remaining"],
        "implementation_dependency_ids_remaining": dependency_mapping[
            "remaining_ids"
        ],
        "optional_diagnostics_mandatory": len(optional_mandatory),
        "optional_diagnostic_ids_mandatory": optional_mandatory,
        "superseded_surface": superseded,
        "recursive_imported_producer_consumer_inventory": import_inventory,
        "retained_gate_schema_type_mapping": gate_schema_types,
        "synthetic_interposition_seams": seams,
        "package_start_consumed_gate_relation": package_start_relation,
        "package_start_without_consumed_gate": package_start_relation[
            "package_start_without_consumed_gate"
        ],
        "package_identity_key_census": identity_keys,
        "package_identity_keys_per_identity": identity_keys[
            "package_identity_keys_per_identity"
        ],
        "identity_success_leaf_census": identity_success_leaves,
        "stage_receipt_binding_census": stage_receipt_binding,
        "changed_typed_boundary_census": changed_typed_boundaries,
        "predicate_ownership": predicate_ownership,
        "result": "PASS",
    }
    if (
        gate_ids != required
        or extra
        or uncovered
        or removed_still_gating
        or dependency_mapping["remaining"]
        or optional_mandatory
        or prohibited_parameters
        or prohibited_closeout_parameters
        or _PUBLIC_EXECUTION_ENTRY in closeout_reached
        or closeout_gate_symbols
        or forbidden_closeout_calls
        or identity_success_leaves["leaf_count"] != 31
        or stage_receipt_binding["result"] != "PASS"
        or changed_typed_boundaries["result"] != "PASS"
        or changed_typed_boundaries["uncovered_changed_boundary_count"] != 0
        or changed_typed_boundaries["extraneous_changed_boundary_count"] != 0
        or superseded["callable_legacy_or_superseded_bypasses"] != 0
        or predicate_ownership["unowned_predicate_count"] != 0
        or predicate_ownership["new_independently_enforceable_mechanisms"] != 0
        or seams["seam_count"] != 3
        or seams["public_effect_injection_inputs"] != 0
    ):
        raise AssertionError("source-derived minimum-path closure")
    return report


def _expect_rejection(
    mechanism_id: str, operation: Callable[[], object]
) -> dict[str, object]:
    protected_effect_attempts = 0

    def protected_effect() -> None:
        nonlocal protected_effect_attempts
        protected_effect_attempts += 1

    try:
        operation()
        protected_effect()
    except Exception as exc:
        return {
            "mechanism_id": mechanism_id,
            "rejected": True,
            "exception_type": type(exc).__name__,
            "protected_effect_attempts": protected_effect_attempts,
            "protected_effect_reached": protected_effect_attempts != 0,
        }
    raise AssertionError(f"{mechanism_id} mutation unexpectedly passed")


def retained_gate_mutations(root: Path) -> dict[str, object]:
    """Reject one stable, effect-free negative mutation for every retained gate."""

    class _Gettable:
        sha256 = "0" * 64

        def __init__(self, values: dict[str, object]):
            self.values = values

        def get(self, name: str) -> object:
            return self.values.get(name)

    mutation_profile = path._authority_profile(synthetic=True)
    mutation_now = 39_000_000_000
    mutation_seed = path._graph_owned_qualification_seed(
        root, "RETAINED-GATE-MUTATION"
    )
    mutation_raw = path._qualification_go(
        mutation_profile, mutation_seed, now_unix_ns=mutation_now
    )
    mutation_go = path._gate_m003_fail_closed_preflight(
        mutation_raw, mutation_profile, now_unix_ns=mutation_now
    )
    mutated_release = dict(mutation_profile.release_authority)
    mutated_runtime_closure = [
        dict(item) for item in mutated_release["runtime_source_closure"]
    ]
    mutated_runtime_closure[0]["sha256"] = "f" * 64
    mutated_release["runtime_source_closure"] = mutated_runtime_closure
    mutated_release_profile = SimpleNamespace(
        release_authority_sha256=mutation_profile.release_authority_sha256,
        release_authority=mutated_release,
    )
    bad_identity = SimpleNamespace(
        report={}, leases=SimpleNamespace(descriptors=[]), read_receipts=()
    )
    bad_bundle = {
        "result": "FAIL",
        "artifacts": {"manifest": {"role": "PRIMARY", "payloads": []}},
    }
    bad_terminal_bundle = {
        "artifacts": {"consumer_terminal": {"result": "FAIL"}}
    }
    m005_arguments = {
        name: None
        for name in inspect.signature(
            path._gate_m005_receipt_derived_ledger
        ).parameters
    }

    cases: list[tuple[str, Callable[[], object]]] = [
        (
            "M001",
            lambda: path._gate_m001_one_shot_claim(object(), None, None),
        ),
        ("M002", lambda: path._gate_m002_per_read_receipts(bad_identity)),
        (
            "M003",
            lambda: path._gate_m003_fail_closed_preflight(
                b"{}\n", path._authority_profile(synthetic=True), now_unix_ns=1
            ),
        ),
        (
            "M004",
            lambda: path._gate_m004_stop_boundary(
                path._StopBoundary(None), "NOT_A_STAGE", None
            ),
        ),
        (
            "M005",
            lambda: path._gate_m005_receipt_derived_ledger(**m005_arguments),
        ),
        (
            "M006",
            lambda: path._gate_m006_no_retry_or_resume(
                {"attempts": 2, "retries": 1, "resume": True}
            ),
        ),
        ("M007", lambda: path._gate_m007_numeric_acceptance(bad_bundle, "PRIMARY")),
        ("M008", lambda: path._gate_m008_comparison_rules({"thresholds": {}})),
        (
            "M009",
            path._gate_m009_stage_vocabulary,
        ),
        (
            "M010",
            lambda: path._gate_m010_accounting_units(
                {"authorization_delta": 1, "package_delta": 0}
            ),
        ),
        (
            "M011",
            lambda: path._gate_m011_historical_master_ledger(
                {
                    "historical_master_ledger_before": 174,
                    "historical_master_ledger_after": 175,
                }
            ),
        ),
        (
            "M012",
            lambda: path._gate_m012_fresh_human_package_authority(
                mutation_go,
                _Gettable({"collapsed_go_sha256": mutation_go.sha256}),
                mutated_release_profile,
            ),
        ),
        (
            "M013",
            lambda: path._gate_m013_checkpoint_identity_stability(
                bad_identity, mutation_profile, None
            ),
        ),
        (
            "M014",
            lambda: path._gate_m014_causal_prerequisite_order(bad_terminal_bundle),
        ),
        (
            "M015",
            lambda: path._gate_m015_independent_primary_secondary(
                bad_bundle, bad_bundle
            ),
        ),
        (
            "M016",
            lambda: path._gate_m016_immutable_result_closure(
                {}, {}, {}, "f" * 64, bad_identity, None, None
            ),
        ),
        (
            "M017",
            lambda: path._gate_m017_release_before_package_terminal(
                {
                    "result": "PASS",
                    "attempted_closures": 5,
                    "successful_closures": 4,
                    "duplicate_closures": 0,
                    "unknown_leases": 0,
                    "live_leases_after_release": 1,
                }
            ),
        ),
    ]
    results: list[dict[str, object]] = []
    for mechanism_id, operation in cases:
        if mechanism_id == "M009":
            with patch.object(path, "_STAGES", ()):
                results.append(
                    _expect_rejection(
                        mechanism_id, path._gate_m009_stage_vocabulary
                    )
                )
        else:
            results.append(_expect_rejection(mechanism_id, operation))
    passed_ids = [item["mechanism_id"] for item in results if item["rejected"]]
    expected = list(contract.REQUIRED_MECHANISM_IDS)
    if passed_ids != expected:
        raise AssertionError("retained-gate mutation census")
    return {
        "passed": len(passed_ids),
        "total": len(expected),
        "unexpected_passes": len(expected) - len(passed_ids),
        "cases": results,
        "synthetic_human_decision_sha256s": [path._sha(mutation_seed)],
        "result": "PASS",
    }


def _optional_omission_campaign(root: Path) -> dict[str, object]:
    cases: list[dict[str, object]] = []
    optional = tuple(contract.OPTIONAL_NON_GATING_MECHANISM_IDS)
    omissions = [(item,) for item in optional] + [optional]
    for index, omitted in enumerate(omissions):
        case_root = root / f"case-{index:02d}"
        case_root.mkdir()
        result = path._run_no_access_qualification(
            case_root, omit_optional=omitted
        )
        if (
            result["result"] != "PASS"
            or result["optional_non_gating_omitted"] != list(omitted)
            or result["optional_omission_changed_required_path"] is not False
        ):
            raise AssertionError("optional diagnostics became a runtime gate")
        cases.append(
            {
                "omitted": list(omitted),
                "synthetic_identities_instantiated": result[
                    "synthetic_identities_instantiated"
                ],
                "synthetic_identities_consumed": result[
                    "synthetic_identities_consumed"
                ],
                "synthetic_human_decision_sha256s": result[
                    "synthetic_human_decision_sha256s"
                ],
                "result": "PASS",
            }
        )
    return {
        "independent_cases": len(optional),
        "combined_cases": 1,
        "cases": cases,
        "synthetic_identities_instantiated": sum(
            int(item["synthetic_identities_instantiated"]) for item in cases
        ),
        "synthetic_identities_consumed": sum(
            int(item["synthetic_identities_consumed"]) for item in cases
        ),
        "synthetic_human_decision_sha256s": [
            digest
            for item in cases
            for digest in item["synthetic_human_decision_sha256s"]
        ],
        "result": "PASS",
    }


def _one_shot_campaign(root: Path) -> dict[str, object]:
    now = 4_000_000_000_000_000_000
    profile = path._authority_profile(synthetic=True)
    human_seed = path._graph_owned_qualification_seed(root, "CONTENTION")
    human_decision_sha256 = path._sha(human_seed)
    raw = path._qualification_go(profile, human_seed, now_unix_ns=now)
    # Each contender has a fresh integration object, producer set, and storage
    # binding.  They share only the exact GO/package leaf so the winner is
    # selected by the durable O_EXCL package-start write, never by shared
    # process-local state.
    runtimes = [
        path._qualification_runtime(
            root,
            human_decision_sha256,
            intercept=False,
            checkpoint_leaf=f"synthetic-checkpoint-contender-{index}",
        )
        for index in range(2)
    ]
    if (
        runtimes[0] is runtimes[1]
        or runtimes[0].integration_state is runtimes[1].integration_state
        or runtimes[0].storage is runtimes[1].storage
        or runtimes[0].storage.package_directory
        != runtimes[1].storage.package_directory
    ):
        raise AssertionError("contenders require independent runtimes and one leaf")

    original_bank = path._StorageBinding.bank_package_start
    barrier = threading.Barrier(2)

    def synchronized_bank(
        storage: object, value: dict[str, object], stop: object
    ) -> str:
        barrier.wait(timeout=30)
        return original_bank(storage, value, stop)

    def contender(runtime: object) -> dict[str, object]:
        return path._invoke_public_qualification(raw, runtime, now_unix_ns=now)

    outcomes: list[tuple[object, object]] = []
    with patch.object(
        path._StorageBinding, "bank_package_start", synchronized_bank
    ):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(contender, runtime) for runtime in runtimes]
            for runtime, future in zip(runtimes, futures, strict=True):
                try:
                    outcomes.append((runtime, future.result(timeout=90)))
                except Exception as exc:
                    outcomes.append((runtime, exc))
    winners = [(runtime, item) for runtime, item in outcomes if type(item) is dict]
    losers = [
        (runtime, item) for runtime, item in outcomes if isinstance(item, Exception)
    ]
    if len(winners) != 1 or len(losers) != 1:
        raise AssertionError("one-shot contention must have one winner")
    loser_runtime, loser_error = losers[0]
    if type(loser_error) is not FileExistsError:
        raise AssertionError("contention loser must fail at O_EXCL package start")
    loser_provider = loser_runtime.checkpoint_effect
    if (
        type(loser_provider) is not path._SyntheticCheckpointProvider
        or dict(loser_runtime.integration_state.snapshot())
        != {"package_starts": 0}
        or loser_runtime.observed_effects["checkpoint_root_resolutions"] != 0
        or loser_runtime.observed_effects["checkpoint_opens"] != 0
        or loser_runtime.observed_effects["numerical_executions"] != 0
        or loser_provider.physical_identity_producer_calls != 0
        or loser_provider.producer_checkpoint_binding_checks != 0
        or loser_provider.producer_checkpoint_shard_opens != 0
        or loser_provider.producer_checkpoint_identity_hash_reads != 0
    ):
        raise AssertionError("contention loser crossed package-start boundary")

    winner_runtime, _winner_result = winners[0]
    package_directory = winner_runtime.storage.package_directory
    start_path = package_directory / "package-start.json"
    terminal_path = package_directory / "package-terminal.json"
    before = (start_path.read_bytes(), terminal_path.read_bytes())

    # A third, freshly constructed runtime proves replay fails on the durable
    # package-start leaf even without any shared in-memory consumed flag.
    replay_now = now + 1_000
    replay_raw = path._qualification_go(
        profile, human_seed, now_unix_ns=replay_now
    )
    if replay_raw == raw or path._sha(replay_raw) == path._sha(raw):
        raise AssertionError("replay proof requires different canonical GO bytes")
    third_runtime = path._qualification_runtime(
        root,
        human_decision_sha256,
        intercept=False,
        checkpoint_leaf="synthetic-checkpoint-replay",
    )
    if (
        third_runtime.integration_state is winner_runtime.integration_state
        or third_runtime.storage is winner_runtime.storage
        or third_runtime.storage.package_directory != package_directory
    ):
        raise AssertionError("third attempt must be fresh and target exact package")
    second_exception: Exception | None = None
    try:
        path._invoke_public_qualification(
            replay_raw, third_runtime, now_unix_ns=replay_now
        )
    except Exception as second_error:
        second_exception = second_error
        second_rejected = True
        second_error_type = type(second_error).__name__
    else:
        raise AssertionError("second package attempt unexpectedly passed")
    if type(second_exception) is not FileExistsError:
        raise AssertionError("second attempt must fail at durable O_EXCL start")
    replay_provider = third_runtime.checkpoint_effect
    if (
        type(replay_provider) is not path._SyntheticCheckpointProvider
        or dict(third_runtime.integration_state.snapshot())
        != {"package_starts": 0}
        or third_runtime.observed_effects["checkpoint_root_resolutions"] != 0
        or third_runtime.observed_effects["checkpoint_opens"] != 0
        or third_runtime.observed_effects["numerical_executions"] != 0
        or replay_provider.physical_identity_producer_calls != 0
        or replay_provider.producer_checkpoint_binding_checks != 0
        or replay_provider.producer_checkpoint_shard_opens != 0
        or replay_provider.producer_checkpoint_identity_hash_reads != 0
    ):
        raise AssertionError("second attempt crossed package-start boundary")
    after = (start_path.read_bytes(), terminal_path.read_bytes())
    if before != after:
        raise AssertionError("loser or second attempt mutated winning package")

    winner_runtime.storage.prepare()
    try:
        try:
            winner_runtime.storage.bank(
                "package-terminal.json",
                {"schema": "COMPETING_TERMINAL", "result": "PASS"},
            )
        except FileExistsError:
            competing_terminal_rejected = True
        else:
            raise AssertionError("competing package terminal unexpectedly passed")
    finally:
        winner_runtime.storage.close()

    return {
        "contenders": 2,
        "independent_contender_runtimes": 2,
        "shared_process_local_one_shot_state": False,
        "shared_exact_package_leaf": package_directory.name,
        "shared_exact_package_leaf_sha256": path._sha(
            package_directory.name.encode("utf-8")
        ),
        "winner_selected_by": "O_EXCL_PACKAGE_TERMINAL_RESERVATION",
        "winners": len(winners),
        "losers_before_package_start": len(losers),
        "loser_error_type": type(loser_error).__name__,
        "loser_checkpoint_root_resolutions": 0,
        "loser_checkpoint_opens": 0,
        "loser_physical_identity_producer_calls": (
            loser_provider.physical_identity_producer_calls
        ),
        "replay_physical_identity_producer_calls": (
            replay_provider.physical_identity_producer_calls
        ),
        "loser_numerical_operations": 0,
        "terminal_winners_per_package": 1,
        "second_attempt_rejected": second_rejected,
        "second_attempt_uses_third_fresh_runtime": True,
        "second_attempt_uses_distinct_canonical_go_bytes": True,
        "second_attempt_preserves_human_decision_sha256": True,
        "first_go_sha256": path._sha(raw),
        "replay_go_sha256": path._sha(replay_raw),
        "package_claim_sha256": human_decision_sha256,
        "synthetic_human_decision_sha256s": [human_decision_sha256],
        "second_attempt_error_type": second_error_type,
        "second_attempts_reaching_package_start": 0,
        "competing_terminal_rejected": competing_terminal_rejected,
        "synthetic_identities_instantiated": sum(
            runtime.observed_effects["synthetic_identities_instantiated"]
            for runtime in [*runtimes, third_runtime]
        ),
        "synthetic_identities_consumed": sum(
            runtime.integration_state.snapshot().get("package_starts")
            for runtime in [*runtimes, third_runtime]
        ),
        "result": "PASS",
    }


def _stage_failure_campaign(root: Path) -> dict[str, object]:
    cases: list[dict[str, object]] = []
    durable_failed_stage = {
        "IDENTITY_TERMINAL": "PACKAGE_START",
        "PRIMARY_RESULT_TERMINAL": "IDENTITY_TERMINAL",
        "SECONDARY_RESULT_TERMINAL": "PRIMARY_RESULT_TERMINAL",
        "COMPARISON_TERMINAL": "SECONDARY_RESULT_TERMINAL",
        "RELEASE_TERMINAL": "COMPARISON_TERMINAL",
        "ACCOUNTING_CLOSURE": "RELEASE_TERMINAL",
        "PACKAGE_TERMINAL": "RELEASE_TERMINAL",
    }
    started_stages = {
        "IDENTITY_TERMINAL",
        "PRIMARY_RESULT_TERMINAL",
        "SECONDARY_RESULT_TERMINAL",
        "COMPARISON_TERMINAL",
        "RELEASE_TERMINAL",
        "ACCOUNTING_CLOSURE",
        "PACKAGE_TERMINAL",
    }
    for index, stage in enumerate(contract.STAGE_VOCABULARY):
        case_root = root / f"case-{index:02d}-{stage.lower()}"
        case_root.mkdir()
        result = path._run_no_access_qualification(case_root, fail_stage=stage)
        if result["fault_stop_observed"] is not True:
            raise AssertionError(f"stage did not stop: {stage}")
        package_directories = sorted(
            (case_root / f"fault-{stage.lower()}").glob("minimum-gate-*")
        )
        should_start = stage in started_stages
        if (
            result["package_started"] is not should_start
            or result["package_terminal_banked"] is not should_start
        ):
            raise AssertionError("fault-stage durable boundary census")
        if should_start:
            if len(package_directories) != 1:
                raise AssertionError("started-stage package directory census")
            package = package_directories[0]
            accounting_path = package / "failure-accounting.json"
            terminal_path = package / "package-terminal.json"
            accounting = json.loads(accounting_path.read_text(encoding="utf-8"))
            terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
            expected_failed_stage = durable_failed_stage[stage]
            if (
                accounting["failed_stage"] != expected_failed_stage
                or accounting["fabricated_successor_receipts"] != 0
                or accounting["historical_master_ledger_before"] != 175
                or accounting["historical_master_ledger_after"] != 175
                or terminal["state"] != "TERMINAL_FAILURE"
                or terminal["failed_stage"] != expected_failed_stage
                or terminal["fabricated_successor_receipts"] != 0
            ):
                raise AssertionError("truthful failure accounting")
            expected_primary_delta = int(
                stage
                in {
                    "SECONDARY_RESULT_TERMINAL",
                    "COMPARISON_TERMINAL",
                    "RELEASE_TERMINAL",
                    "ACCOUNTING_CLOSURE",
                    "PACKAGE_TERMINAL",
                }
            )
            expected_secondary_delta = int(
                stage
                in {
                    "COMPARISON_TERMINAL",
                    "RELEASE_TERMINAL",
                    "ACCOUNTING_CLOSURE",
                    "PACKAGE_TERMINAL",
                }
            )
            if (
                accounting["authorization_delta"] != 0
                or accounting["package_delta"] != 1
                or accounting["primary_delta"] != expected_primary_delta
                or accounting["secondary_delta"] != expected_secondary_delta
            ):
                raise AssertionError("receipt-derived failure deltas")
            durable_receipts = len(accounting["durable_receipts"])
        else:
            if package_directories:
                package = package_directories[0]
                if (
                    (package / "failure-accounting.json").exists()
                    or (package / "package-terminal.json").exists()
                ):
                    raise AssertionError("pre-start failure fabricated closure")
            durable_receipts = 0
        cases.append(
            {
                "stage": stage,
                "furthest_durable_stage": (
                    durable_failed_stage.get(stage) if should_start else None
                ),
                "package_started": should_start,
                "durable_receipts": durable_receipts,
                "fabricated_successor_receipts": 0,
                "synthetic_identities_instantiated": result[
                    "synthetic_identities_instantiated"
                ],
                "synthetic_identities_consumed": result[
                    "synthetic_identities_consumed"
                ],
                "synthetic_human_decision_sha256s": result[
                    "synthetic_human_decision_sha256s"
                ],
                "result": "PASS",
            }
        )
    return {
        "passed": len(cases),
        "total": len(contract.STAGE_VOCABULARY),
        "cases": cases,
        "synthetic_identities_instantiated": sum(
            int(item["synthetic_identities_instantiated"]) for item in cases
        ),
        "synthetic_identities_consumed": sum(
            int(item["synthetic_identities_consumed"]) for item in cases
        ),
        "synthetic_human_decision_sha256s": [
            digest
            for item in cases
            for digest in item["synthetic_human_decision_sha256s"]
        ],
        "result": "PASS",
    }


def _missing_required_public_path_rehearsals(root: Path) -> dict[str, object]:
    """Omit each required synthetic leaf and prove a terminal pre-open stop."""
    profile = path._authority_profile(synthetic=True)
    forbidden_successors = {
        "primary",
        "secondary",
        "primary-start-receipt.json",
        "secondary-start-receipt.json",
        "comparison-summary.json",
        "comparison-receipt.json",
        "comparison-terminal.json",
        "release-start-receipt.json",
        "release-report.json",
        "release-receipt.json",
        "release-terminal.json",
        "receipt-derived-accounting.json",
        "package-receipt.json",
        "v11-result-closure.json",
    }
    cases: list[dict[str, object]] = []
    for ordinal in range(1, 7):
        case_root = root / f"missing-required-{ordinal}"
        case_root.mkdir()
        now = 39_387_000_000 + ordinal
        seed = path._graph_owned_qualification_seed(
            case_root, f"MISSING-REQUIRED-{ordinal}"
        )
        raw = path._qualification_go(profile, seed, now_unix_ns=now)
        validated = path._validate_go_bytes(raw, profile, now_unix_ns=now)
        runtime = path._qualification_runtime(
            case_root,
            str(validated.get("human_decision_sha256")),
            intercept=False,
            missing_required_ordinal=ordinal,
        )
        failure: BaseException | None = None
        try:
            path._invoke_public_qualification(raw, runtime, now_unix_ns=now)
        except BaseException as exc:
            failure = exc
        if failure is None:
            raise AssertionError("missing required shard unexpectedly passed")

        provider = runtime.checkpoint_effect
        if type(provider) is not path._SyntheticCheckpointProvider:
            raise AssertionError("missing-required checkpoint provider")
        evidence = getattr(failure, "evidence", None)
        access_census = (
            evidence.get("access_census") if type(evidence) is dict else None
        )
        detail = getattr(failure, "detail", None)
        package = runtime.storage.package_directory
        terminal = json.loads(
            (package / "package-terminal.json").read_text(encoding="utf-8")
        )
        accounting = json.loads(
            (package / "failure-accounting.json").read_text(encoding="utf-8")
        )
        observed_package = set(item.name for item in package.iterdir())
        extra_name = path._SYNTHETIC_CHECKPOINT_BENIGN_EXTRA_LEAVES[0]
        if (
            type(evidence) is not dict
            or evidence.get("checkpoint_access") != "RECEIPT_DERIVED"
            or type(access_census) is not dict
            or access_census.get("receipt_count") != 0
            or access_census.get("checkpoint_shard_opens_lower_bound") != 0
            or access_census.get("checkpoint_shard_opens_upper_bound") != 0
            or access_census.get(
                "checkpoint_identity_hash_reads_lower_bound"
            )
            != 0
            or access_census.get(
                "checkpoint_identity_hash_reads_upper_bound"
            )
            != 0
            or access_census.get("exact") is not True
            or type(detail) is not str
            or detail
            != "checkpoint root leaf census: required=6 present=5 missing=1"
            or extra_name in detail
            or observed_package & forbidden_successors
            or terminal.get("state") != "TERMINAL_FAILURE"
            or terminal.get("failed_stage") != "PACKAGE_START"
            or accounting.get("package_delta") != 1
            or accounting.get("primary_delta") != 0
            or accounting.get("secondary_delta") != 0
            or accounting.get("original_checkpoint_opens_lower_bound") != 0
            or accounting.get("original_checkpoint_opens_upper_bound") != 0
            or accounting.get(
                "original_checkpoint_identity_hash_reads_lower_bound"
            )
            != 0
            or accounting.get(
                "original_checkpoint_identity_hash_reads_upper_bound"
            )
            != 0
            or accounting.get(
                "real_numerical_executions_observed_in_process"
            )
            != 0
            or provider.physical_identity_producer_calls != 1
            or provider.producer_checkpoint_binding_checks != 1
            or provider.producer_checkpoint_shard_opens != 0
            or provider.producer_checkpoint_identity_hash_reads != 0
            or runtime.observed_effects["synthetic_fixture_required_leaves"] != 5
            or runtime.observed_effects["synthetic_fixture_benign_extra_leaves"]
            != 1
            or runtime.observed_effects["synthetic_fixture_leaf_creation_opens"]
            != 6
            or runtime.observed_effects["numerical_executions"] != 0
        ):
            raise AssertionError("missing-required public-path pre-open closure")
        cases.append(
            {
                "missing_ordinal": ordinal,
                "checkpoint_shard_opens": 0,
                "checkpoint_identity_hash_reads": 0,
                "primary_successor_effects": 0,
                "secondary_successor_effects": 0,
                "comparison_successor_effects": 0,
                "release_successor_effects": 0,
                "terminal_failure_banked": True,
                "failure_accounting_banked": True,
                "synthetic_identities_instantiated": runtime.observed_effects[
                    "synthetic_identities_instantiated"
                ],
                "synthetic_identities_consumed": runtime.integration_state.snapshot().get(
                    "package_starts"
                ),
                "synthetic_human_decision_sha256s": [path._sha(seed)],
                "result": "PASS",
            }
        )
    return {
        "cases": cases,
        "missing_required_shard_preopen_failures": f"{len(cases)}/6",
        "checkpoint_shard_opens": 0,
        "checkpoint_identity_hash_reads": 0,
        "successor_effects": "0/0/0/0",
        "terminal_failures_banked": len(cases),
        "synthetic_identities_instantiated": sum(
            int(item["synthetic_identities_instantiated"]) for item in cases
        ),
        "synthetic_identities_consumed": sum(
            int(item["synthetic_identities_consumed"]) for item in cases
        ),
        "synthetic_human_decision_sha256s": [
            digest
            for item in cases
            for digest in item["synthetic_human_decision_sha256s"]
        ],
        "result": "PASS",
    }


def _synthetic_scope_boundary(root: Path) -> dict[str, object]:
    """Prove one graph-owned synthetic decision cannot enter production."""
    now = 39_388_000_000
    seed = path._graph_owned_qualification_seed(root, "SCOPE-BOUNDARY")
    synthetic = path._authority_profile(synthetic=True)
    production = path._authority_profile(synthetic=False)
    synthetic_shards = tuple(
        (item["size_bytes"], item["sha256"]) for item in synthetic.shards
    )
    production_shards = tuple(
        (item["size_bytes"], item["sha256"]) for item in production.shards
    )
    if (
        synthetic.checkpoint_set_sha256 == production.checkpoint_set_sha256
        or len(synthetic_shards) != 6
        or len(production_shards) != 6
        or any(
            synthetic_item == production_item
            for synthetic_item, production_item in zip(
                synthetic_shards, production_shards, strict=True
            )
        )
    ):
        raise AssertionError("synthetic/production checkpoint authority separation")
    raw = path._qualification_go(synthetic, seed, now_unix_ns=now)
    try:
        path._gate_m003_fail_closed_preflight(raw, production, now_unix_ns=now)
    except ValueError as exc:
        if "collapsed GO release authority" not in str(exc):
            raise
    else:
        raise AssertionError("synthetic authority crossed production preflight")
    return {
        "synthetic_authority_production_consumable": False,
        "checkpoint_set_sha256_unequal": True,
        "all_shard_size_digest_pairs_unequal": True,
        "synthetic_human_decision_sha256s": [path._sha(seed)],
        "protected_production_effects": 0,
        "result": "PASS",
    }


def qualify() -> dict[str, object]:
    """Run the complete deterministic Sequence 39 no-access campaign."""
    graph_temp_parent = Path(tempfile.gettempdir()).resolve(strict=True)
    temporary = tempfile.TemporaryDirectory(
        prefix="f017-sequence41-", dir=graph_temp_parent
    )
    root = path._qualification_root(Path(temporary.name))
    try:
        # First prove the static closure, then enrich it with the actual
        # producer/consumer component trace from the complete public dry run.
        source_derived_closure()
        mutation_root = root / "retained-gate-mutations"
        mutation_root.mkdir()
        mutations = retained_gate_mutations(mutation_root)

        full_root = root / "full-call-path"
        full_root.mkdir()
        full_path, component_trace = _profiled_public_path(
            lambda: path._run_no_access_qualification(full_root)
        )
        active_components = component_trace[
            "production_components_exercised"
        ]
        if not isinstance(active_components, list):
            raise AssertionError("production component trace")
        physical_counters = {
            "physical_v12_identity_producer_calls": 1,
            "synthetic_checkpoint_binding_checks": 1,
            "synthetic_checkpoint_shard_opens": 6,
            "synthetic_checkpoint_identity_hash_reads": 6,
            "synthetic_checkpoint_payload_bytes_read": 0,
            "synthetic_checkpoint_mmaps": 0,
            "graph_owned_synthetic_checkpoint_required_leaves": 6,
            "graph_owned_synthetic_checkpoint_benign_extra_leaves": 1,
            "graph_owned_fixture_leaf_creation_opens": 7,
            "graph_owned_fixture_benign_extra_creation_opens": 1,
            "identity_producer_extra_leaf_open_follow_stat_hash": "0/0/0/0",
        }
        if any(full_path.get(key) != value for key, value in physical_counters.items()):
            raise AssertionError("physical synthetic checkpoint counters")
        physical_components = {
            "f017_checkpoint_identity_producer_v12._minimum_gate_produce",
            "f017_checkpoint_identity_producer_v12.validate_banked_identity_evidence",
        }
        if not physical_components.issubset(
            set(component_trace["source_derived_exercised_components"])
        ):
            raise AssertionError("physical V12 identity component trace")
        closure = source_derived_closure(active_components)

        missing_root = root / "missing-required-public-path"
        missing_root.mkdir()
        missing_required = _missing_required_public_path_rehearsals(missing_root)

        scope_root = root / "synthetic-scope-boundary"
        scope_root.mkdir()
        scope_boundary = _synthetic_scope_boundary(scope_root)

        optional_root = root / "optional-omissions"
        optional_root.mkdir()
        optional = _optional_omission_campaign(optional_root)

        contention_root = root / "one-shot-contention"
        contention_root.mkdir()
        one_shot = _one_shot_campaign(contention_root)

        failures_root = root / "retained-stage-failures"
        failures_root.mkdir()
        stage_failures = _stage_failure_campaign(failures_root)

        decision_sha256s = [
            digest
            for source in (
                mutations,
                full_path,
                missing_required,
                scope_boundary,
                optional,
                one_shot,
                stage_failures,
            )
            for digest in source["synthetic_human_decision_sha256s"]
        ]
        if (
            not decision_sha256s
            or any(re.fullmatch(r"[0-9a-f]{64}", digest) is None for digest in decision_sha256s)
            or _SEQUENCE40_CONSUMED_DECISION_SHA256 in decision_sha256s
        ):
            raise AssertionError("synthetic decision authority separation")

        synthetic_identity_sources = {
            "full_call_path": {
                "instantiated": full_path["synthetic_identities_instantiated"],
                "consumed": full_path["synthetic_identities_consumed"],
            },
            "optional_omission_campaign": {
                "instantiated": optional["synthetic_identities_instantiated"],
                "consumed": optional["synthetic_identities_consumed"],
            },
            "one_shot_campaign": {
                "instantiated": one_shot["synthetic_identities_instantiated"],
                "consumed": one_shot["synthetic_identities_consumed"],
            },
            "stage_failure_campaign": {
                "instantiated": stage_failures[
                    "synthetic_identities_instantiated"
                ],
                "consumed": stage_failures["synthetic_identities_consumed"],
            },
            "missing_required_public_path_rehearsals": {
                "instantiated": missing_required[
                    "synthetic_identities_instantiated"
                ],
                "consumed": missing_required["synthetic_identities_consumed"],
            },
        }
        synthetic_instantiated = sum(
            int(item["instantiated"])
            for item in synthetic_identity_sources.values()
        )
        synthetic_consumed = sum(
            int(item["consumed"])
            for item in synthetic_identity_sources.values()
        )

        result = {
            "schema": (
                "pulsarmlx.f017.event06-v12-minimum-gate-path-qualification/1.0.0"
            ),
            "source_derived_closure": closure,
            "changed_typed_boundaries_total": closure[
                "changed_typed_boundary_census"
            ]["changed_typed_boundaries_total"],
            "changed_typed_boundaries_with_composition_tests": closure[
                "changed_typed_boundary_census"
            ]["changed_typed_boundaries_with_composition_tests"],
            "uncovered_or_extraneous_changed_boundaries": "0/0",
            "current_required_gate_count_reproduced": 35,
            "minimum_gate_set_accepted": 17,
            "required_gates_enforced": closure["required_gates_enforced"],
            "extra_required_gates": closure["extra_required_gates"],
            "optional_non_gating_mechanisms": len(
                contract.OPTIONAL_NON_GATING_MECHANISM_IDS
            ),
            "removed_mechanisms": f"{len(contract.REMOVED_MECHANISM_IDS)}/13",
            "removed_mechanisms_still_gating": closure[
                "removed_mechanisms_still_gating"
            ],
            "implementation_dependencies_resolved": (
                f"{len(contract.IMPLEMENTATION_DEPENDENCY_MECHANISM_IDS) - int(closure['implementation_dependencies_remaining'])}/"
                f"{len(contract.IMPLEMENTATION_DEPENDENCY_MECHANISM_IDS)}"
            ),
            "implementation_dependencies_remaining": closure[
                "implementation_dependencies_remaining"
            ],
            "callable_legacy_or_superseded_bypasses": closure[
                "superseded_surface"
            ]["callable_legacy_or_superseded_bypasses"],
            "production_public_raw_identity_inputs": closure[
                "public_raw_identity_inputs"
            ],
            "production_public_storage_location_inputs": closure[
                "public_storage_location_inputs"
            ],
            "package_start_without_consumed_gate": closure[
                "package_start_without_consumed_gate"
            ],
            "package_identity_keys_per_identity": closure[
                "package_identity_keys_per_identity"
            ],
            "terminal_winners_per_package": one_shot[
                "terminal_winners_per_package"
            ],
            "second_attempts_reaching_package_start": one_shot[
                "second_attempts_reaching_package_start"
            ],
            "full_call_path": full_path,
            "production_component_trace": component_trace,
            "root_census_policy": "REQUIRED_SUBSET_EXTRAS_IGNORED",
            "required_shard_names": 6,
            "required_shards_present_with_extra_leaves": "PASS",
            "exact_required_shard_open_names": "6/6",
            "retained_gate_mutations": mutations,
            "optional_diagnostic_omission": optional,
            "one_shot_contention": one_shot,
            "retained_stage_failures": stage_failures,
            "missing_required_public_path_rehearsals": missing_required,
            "synthetic_scope_boundary": scope_boundary,
            "missing_required_shard_preopen_failures": missing_required[
                "missing_required_shard_preopen_failures"
            ],
            "full_call_path_dry_run_with_synthetic_authority": "PASS",
            "physical_v12_identity_producer_on_graph_owned_synthetic_checkpoint": (
                "PASS"
            ),
            "physical_v12_identity_producer_calls": full_path[
                "physical_v12_identity_producer_calls"
            ],
            "synthetic_checkpoint_binding_checks": full_path[
                "synthetic_checkpoint_binding_checks"
            ],
            "synthetic_checkpoint_opens_identity_hash_reads_payload_bytes_mmaps": (
                f"{full_path['synthetic_checkpoint_shard_opens']}/"
                f"{full_path['synthetic_checkpoint_identity_hash_reads']}/"
                f"{full_path['synthetic_checkpoint_payload_bytes_read']}/"
                f"{full_path['synthetic_checkpoint_mmaps']}"
            ),
            "graph_owned_synthetic_checkpoint_required_leaves": full_path[
                "graph_owned_synthetic_checkpoint_required_leaves"
            ],
            "graph_owned_synthetic_checkpoint_benign_extra_leaves": full_path[
                "graph_owned_synthetic_checkpoint_benign_extra_leaves"
            ],
            "graph_owned_fixture_leaf_creation_opens": full_path[
                "graph_owned_fixture_leaf_creation_opens"
            ],
            "graph_owned_fixture_benign_extra_creation_opens": full_path[
                "graph_owned_fixture_benign_extra_creation_opens"
            ],
            "identity_producer_extra_leaf_open_follow_stat_hash": full_path[
                "identity_producer_extra_leaf_open_follow_stat_hash"
            ],
            "identity_producer_extra_leaf_interaction_proof": (
                "SOURCE_DERIVED_AND_FOCUSED_RUNTIME_INSTRUMENTED"
            ),
            "production_path_components_exercised": component_trace[
                "production_components_exercised_ratio"
            ],
            "original_checkpoint_root_resolutions": 0,
            "original_checkpoint_opens_hashes_payload_reads_mmaps": "0/0/0/0",
            "primary_secondary_real_executions": "0/0",
            "full_model_inference": "NONE",
            "real_registry_ledger_or_terminal_writes": 0,
            "real_event06_identities_instantiated_or_consumed": "0/0",
            "synthetic_identity_accounting": {
                "sources": synthetic_identity_sources,
                "instantiated": synthetic_instantiated,
                "consumed": synthetic_consumed,
                "all_consumptions_receipt_bound": True,
                "result": "PASS",
            },
            "synthetic_identities_instantiated_or_consumed": (
                f"{synthetic_instantiated}/{synthetic_consumed}"
            ),
            "synthetic_decision_authority_source": "GRAPH_OWNED_TEMPORARY_BYTES",
            "synthetic_decision_count": len(decision_sha256s),
            "synthetic_decision_digest_equals_consumed_go": False,
            "synthetic_authority_production_consumable": False,
            "historical_master_ledger": 175,
            "event06_executed": False,
            "new_human_go_created_requested_or_reused": False,
            "result": "PASS",
        }
        return result
    finally:
        temporary.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    qualified = qualify()
    rendered = json.dumps(qualified, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        print(rendered, end="")
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
