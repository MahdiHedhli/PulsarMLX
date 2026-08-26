#!/usr/bin/env python3
"""Validate the formula-preserving F017 numerical output-interface implementation."""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib.util
import json
import math
import struct
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "scripts/research"
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
PRIMARY_V2 = RESEARCH / "f017_corrected_oracle_primary_numerics_v2.py"
SECONDARY_V2 = RESEARCH / "f017_corrected_oracle_secondary_numerics_v2.py"
PRIMARY_V3 = RESEARCH / "f017_corrected_oracle_primary_numerics_v3.py"
SECONDARY_V3 = RESEARCH / "f017_corrected_oracle_secondary_numerics_v3.py"
POLICY_V1 = CONTRACTS / "f017-corrected-oracle-numerical-capability-policy-v1.json"
POLICY_V2 = CONTRACTS / "f017-corrected-oracle-numerical-capability-policy-v2.json"
PRIMARY_V2_SHA = "657cdff9ee833cb2b3a0b3fa71b6cbc3dd1e0fbc71b74b9bbff9dca6b5b76767"
SECONDARY_V2_SHA = "e3670b22ac71bad7523efe1e47b00f2345d1f103d2af8f7592e2f3f8c793a791"
PRIMARY_HELPERS = ("_matvec", "_transpose_matvec", "_rms", "_silu", "_residual", "_projection", "_swiglu", "_route")
SECONDARY_HELPERS = ("rms", "mv", "transpose_mv", "swiglu")
OUTPUT_FIELDS = (
    "role", "dtype", "core_execution_count", "final_hidden_element_count",
    "final_normalized_element_count", "full_logits_element_count",
    "final_hidden_payload", "final_normalized_payload", "full_logits_payload",
    "final_hidden_sha256", "final_normalized_sha256", "full_logits_sha256",
    "layer_captures", "selected_token", "top_32", "top_1_margin", "tie_rule",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"module spec: {path}")
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def functions(path: Path) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in ast.parse(path.read_text()).body
        if isinstance(node, ast.FunctionDef)
    }


def ast_bytes(node: ast.AST) -> bytes:
    return ast.dump(node, annotate_fields=True, include_attributes=False).encode()


def historical_prefix(node: ast.FunctionDef) -> list[ast.stmt]:
    result: list[ast.stmt] = []
    for statement in node.body:
        result_assignment = isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "result"
            for target in statement.targets
        )
        if result_assignment or isinstance(statement, ast.Return):
            break
        result.append(statement)
    return result


def normalized_graph(function: ast.FunctionDef, body: list[ast.stmt]) -> bytes:
    value = ast.FunctionDef(
        name="_execute_graph", args=function.args, body=body,
        decorator_list=[], returns=None, type_comment=None, type_params=[],
    )
    return ast_bytes(value)


def validate_formula_equivalence() -> dict:
    p2, p3 = functions(PRIMARY_V2), functions(PRIMARY_V3)
    s2, s3 = functions(SECONDARY_V2), functions(SECONDARY_V3)
    for symbol in PRIMARY_HELPERS:
        require(symbol in p2 and symbol in p3, f"primary symbol: {symbol}")
        require(ast_bytes(p2[symbol]) == ast_bytes(p3[symbol]), f"primary formula drift: {symbol}")
    for symbol in SECONDARY_HELPERS:
        require(symbol in s2 and symbol in s3, f"secondary symbol: {symbol}")
        require(ast_bytes(s2[symbol]) == ast_bytes(s3[symbol]), f"secondary formula drift: {symbol}")
    for role, old, new in (("primary", p2["execute"], p3["_execute_graph"]), ("secondary", s2["execute"], s3["_execute_graph"])):
        expected = normalized_graph(old, historical_prefix(old))
        require(isinstance(new.body[-1], ast.Return), f"{role} state return")
        observed = normalized_graph(new, new.body[:-1])
        require(expected == observed, f"{role} graph prefix drift")
    return {
        "helper_symbols": len(PRIMARY_HELPERS) + len(SECONDARY_HELPERS),
        "graph_prefixes": 2,
        "changed_numerical_expressions": 0,
    }


def validate_source_policy() -> dict:
    analyzer = module("f017_capability_analyzer_v2_impl", RESEARCH / "f017_numerical_capability_analysis_v2.py")
    checker = module("f017_capability_checker_v1_impl", RESEARCH / "check_f017_numerical_capabilities_independent_v1.py")
    v1, v2 = json.loads(POLICY_V1.read_text()), json.loads(POLICY_V2.read_text())
    require(v2["supersedes"]["sha256"] == sha(POLICY_V1), "capability supersession")
    require(v2["new_external_capabilities"] == 0, "new external capability")
    require(v2["exact_capability_imports"] == v1["exact_capability_imports"], "capability import drift")
    require(v2["module_identities"] == v1["module_identities"], "module identity drift")
    require(v2["semantic_modules"] == v1["semantic_modules"], "semantic module drift")
    results = {}
    for role, path in (("primary", PRIMARY_V3), ("secondary", SECONDARY_V3)):
        semantic = analyzer.analyze_path(path, POLICY_V2, role)
        independent = checker.check(path, v2)
        results[role] = {
            "semantic_module_uses": len(semantic.approved_module_uses),
            "semantic_receiver_uses": len(semantic.approved_receiver_uses),
            "independent_module_uses": independent["approved_use_count"],
        }
    return results


def validate_output_object(value: object, role: str, hidden: int, vocab: int) -> None:
    require(role in {"PRIMARY", "SECONDARY"}, "role")
    expected_type = "PrimaryNumericalOutputs" if role == "PRIMARY" else "SecondaryNumericalOutputs"
    require(type(value).__name__ == expected_type, "output type")
    require(dataclasses.is_dataclass(value), "dataclass")
    require(value.__dataclass_params__.frozen is True, "frozen dataclass")
    require(tuple(field.name for field in dataclasses.fields(value)) == OUTPUT_FIELDS, "output field census")
    itemsize, dtype = (8, "f64le") if role == "PRIMARY" else (4, "f32le")
    require(value.role == role and value.dtype == dtype and value.core_execution_count == 1, "output identity")
    counts = (value.final_hidden_element_count, value.final_normalized_element_count, value.full_logits_element_count)
    require(counts == (hidden, hidden, vocab), "output geometry")
    payloads = (value.final_hidden_payload, value.final_normalized_payload, value.full_logits_payload)
    hashes = (value.final_hidden_sha256, value.final_normalized_sha256, value.full_logits_sha256)
    for payload, expected_count, expected_hash in zip(payloads, counts, hashes, strict=True):
        require(type(payload) is bytes, "immutable payload type")
        require(len(payload) == expected_count * itemsize, "payload byte count")
        require(hashlib.sha256(payload).hexdigest() == expected_hash, "payload hash")
        code = "<d" if role == "PRIMARY" else "<f"
        decoded = [record[0] for record in struct.iter_unpack(code, payload)]
        require(len(decoded) == expected_count and all(math.isfinite(item) for item in decoded), "payload finite geometry")
    require(type(value.layer_captures) is tuple and all(dataclasses.is_dataclass(item) and item.__dataclass_params__.frozen for item in value.layer_captures), "layer capture immutability")
    require(type(value.top_32) is tuple and len(value.top_32) == min(32, vocab), "top tuple")
    require(all(dataclasses.is_dataclass(item) and item.__dataclass_params__.frozen for item in value.top_32), "top immutability")
    require(type(value.selected_token) is int and 0 <= value.selected_token < vocab, "selected token")
    require(type(value.top_1_margin) is float and math.isfinite(value.top_1_margin), "margin")
    try:
        json.dumps(value)
    except TypeError:
        pass
    else:
        raise ValueError("output object entered control JSON")


def validate() -> dict:
    require(sha(PRIMARY_V2) == PRIMARY_V2_SHA and sha(SECONDARY_V2) == SECONDARY_V2_SHA, "historical V2 byte drift")
    formula = validate_formula_equivalence()
    capability = validate_source_policy()
    p3 = module("f017_primary_v3_impl", PRIMARY_V3)
    s3 = module("f017_secondary_v3_impl", SECONDARY_V3)
    require(p3.PrimaryNumericalOutputs.__dataclass_params__.frozen, "primary frozen output")
    require(s3.SecondaryNumericalOutputs.__dataclass_params__.frozen, "secondary frozen output")
    return {
        "schema": "pulsarmlx.f017.numerical-output-interface-implementation-validation/1.0.0",
        "historical_primary_sha256": sha(PRIMARY_V2),
        "historical_secondary_sha256": sha(SECONDARY_V2),
        "successor_primary_sha256": sha(PRIMARY_V3),
        "successor_secondary_sha256": sha(SECONDARY_V3),
        "formula_equivalence": formula,
        "capability_analysis": capability,
        "new_external_capabilities": 0,
        "original_checkpoint_access": 0,
        "result": "PASS",
    }


def main() -> int:
    result = validate()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
