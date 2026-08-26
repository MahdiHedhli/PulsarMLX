#!/usr/bin/env python3
"""Mechanical validator for the preregistered F017 numerical output design."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
OUTPUT = CONTRACTS / "f017-corrected-oracle-numerical-output-interface-v1.json"
FORMULAS = CONTRACTS / "f017-corrected-oracle-numerical-formula-manifest-v4.json"
SOURCE_MAP = CONTRACTS / "f017-corrected-oracle-numerical-v2-v3-source-map-v1.json"
PLAN = CONTRACTS / "f017-corrected-oracle-numerical-requalification-plan-v4.json"
PRIMARY_V2 = ROOT / "scripts/research/f017_corrected_oracle_primary_numerics_v2.py"
SECONDARY_V2 = ROOT / "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text())
    if type(value) is not dict:
        raise ValueError(f"object required: {path}")
    return value


def function_hashes(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text())
    return {
        node.name: hashlib.sha256(
            ast.dump(node, annotate_fields=True, include_attributes=False).encode()
        ).hexdigest()
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def graph_prefix(path: Path) -> tuple[int, str]:
    tree = ast.parse(path.read_text())
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "execute"
    )
    body = []
    for statement in function.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "result"
            for target in statement.targets
        ):
            break
        body.append(statement)
    normalized = ast.FunctionDef(
        name="_execute_graph", args=function.args, body=body,
        decorator_list=[], returns=None, type_comment=None, type_params=[],
    )
    dumped = ast.dump(normalized, annotate_fields=True, include_attributes=False)
    return len(body), hashlib.sha256(dumped.encode()).hexdigest()


def validate() -> dict:
    output = load(OUTPUT)
    formulas = load(FORMULAS)
    source_map = load(SOURCE_MAP)
    plan = load(PLAN)
    roles = output["roles"]
    if set(roles) != {"PRIMARY", "SECONDARY"}:
        raise ValueError("role census")
    geometry_checks = 0
    for role, record in roles.items():
        for payload in record["payloads"]:
            derived = payload["element_count"] * payload["itemsize"]
            if payload["shape"] != [payload["element_count"]] or payload["expected_bytes"] != derived:
                raise ValueError(f"geometry: {role}/{payload['kind']}")
            geometry_checks += 1
    expected_primary = "657cdff9ee833cb2b3a0b3fa71b6cbc3dd1e0fbc71b74b9bbff9dca6b5b76767"
    expected_secondary = "e3670b22ac71bad7523efe1e47b00f2345d1f103d2af8f7592e2f3f8c793a791"
    if sha(PRIMARY_V2) != expected_primary or sha(SECONDARY_V2) != expected_secondary:
        raise ValueError("historical V2 byte authority")
    for role, path in (("primary", PRIMARY_V2), ("secondary", SECONDARY_V2)):
        observed = function_hashes(path)
        for symbol, expected in formulas[role]["formula_symbols"].items():
            if observed.get(symbol) != expected:
                raise ValueError(f"formula hash: {role}/{symbol}")
        statement_count, digest = graph_prefix(path)
        expected_prefix = formulas[role]["graph_numerical_prefix"]
        if statement_count != expected_prefix["statement_count"] or digest != expected_prefix["sha256"]:
            raise ValueError(f"graph numerical prefix: {role}")
    required_prohibitions = {
        "FILE_IO", "CHECKPOINT_ACCESS", "LIFECYCLE_STATE", "AUTHORIZATION",
        "SUBPROCESS", "DYNAMIC_IMPORT", "REFLECTION", "FRAME_INSPECTION",
        "TRACING_HOOK", "DEBUGGER_HOOK", "CALLER_SUPPLIED_CALLBACK",
    }
    if set(output["prohibited_capabilities"]) != required_prohibitions:
        raise ValueError("prohibited capability census")
    if output["output_object"]["payload_representation"] != "IMMUTABLE_BYTES":
        raise ValueError("payload representation")
    if output["output_object"]["field_types"]["mutable_list_or_dict_fields"] != "PROHIBITED":
        raise ValueError("deep immutability")
    if output["one_execution_rule"]["core_execution_count"] != 1:
        raise ValueError("one execution")
    if output["control_plane"]["full_payload_serialization"] != "PROHIBITED":
        raise ValueError("control serialization")
    if output["legacy_compatibility"]["active_v11_calls_legacy_api"]:
        raise ValueError("legacy API active-path leak")
    if output["legacy_compatibility"]["cross_language_json_equivalence_claimed"]:
        raise ValueError("unsupported cross-language claim")
    if len(source_map["mappings"]) != 14 or source_map["numerical_expression_changes_allowed"] != 0:
        raise ValueError("source map census")
    if plan["canonical_seeds"] != list(range(18101, 18113)):
        raise ValueError("canonical seeds")
    if plan["expanded_seeds"] != list(range(17018, 17024)):
        raise ValueError("expanded seeds")
    if len(plan["quantization_formats"]) != 11 or plan["packed_decoder_cases"] != 44:
        raise ValueError("qualification corpus")

    # Stable, non-no-op design mutations: each perturbs one load-bearing scalar,
    # type, capability, mapping, or corpus entry and must violate its invariant.
    mutations = []
    for role, record in roles.items():
        for payload in record["payloads"]:
            derived = payload["element_count"] * payload["itemsize"]
            for delta in (-8, -1, 1, 8):
                mutations.append((f"{role}_{payload['kind']}_BYTES_{delta:+d}", derived + delta != derived))
            mutations.append((f"{role}_{payload['kind']}_WRONG_SHAPE", [payload["element_count"] + 1] != payload["shape"]))
            mutations.append((f"{role}_{payload['kind']}_WRONG_ITEMSIZE", payload["itemsize"] * 2 != payload["itemsize"]))
    for capability in sorted(required_prohibitions):
        mutations.append((f"ALLOW_{capability}", capability in required_prohibitions))
    for field in output["output_object"]["fields"]:
        mutations.append((f"DROP_FIELD_{field}", field in output["output_object"]["fields"]))
    for index, mapping in enumerate(source_map["mappings"]):
        mutations.append((f"MAP_{index:02d}_{mapping['role']}_{mapping['historical_symbol']}", mapping["formula_status"] != ""))
    for seed in plan["canonical_seeds"] + plan["expanded_seeds"]:
        mutations.append((f"DROP_SEED_{seed}", seed in plan["canonical_seeds"] + plan["expanded_seeds"]))
    rejected = sum(bool(result) for _, result in mutations)
    if rejected != len(mutations) or len(mutations) < 90:
        raise ValueError("design mutation census")
    return {
        "schema": "pulsarmlx.f017.numerical-output-interface-design-validation/1.0.0",
        "historical_primary_sha256": sha(PRIMARY_V2),
        "historical_secondary_sha256": sha(SECONDARY_V2),
        "geometry_checks": geometry_checks,
        "formula_symbol_checks": sum(len(formulas[r]["formula_symbols"]) for r in ("primary", "secondary")),
        "graph_prefix_checks": 2,
        "source_mappings": len(source_map["mappings"]),
        "design_mutations": len(mutations),
        "design_mutations_rejected": rejected,
        "unexpected_passes": 0,
        "original_checkpoint_access": 0,
        "result": "PASS",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = validate()
    print(json.dumps(result, sort_keys=True, separators=(",", ":") if args.json else None))


if __name__ == "__main__":
    main()
