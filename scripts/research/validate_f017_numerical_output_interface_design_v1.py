#!/usr/bin/env python3
"""Mechanical validator for the preregistered F017 numerical output design."""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
OUTPUT = CONTRACTS / "f017-corrected-oracle-numerical-output-interface-v1.json"
FORMULAS = CONTRACTS / "f017-corrected-oracle-numerical-formula-manifest-v4.json"
SOURCE_MAP = CONTRACTS / "f017-corrected-oracle-numerical-v2-v3-source-map-v1.json"
PLAN = CONTRACTS / "f017-corrected-oracle-numerical-requalification-plan-v4.json"
PRIMARY_V2 = ROOT / "scripts/research/f017_corrected_oracle_primary_numerics_v2.py"
SECONDARY_V2 = ROOT / "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py"

PRIMARY_SHA = "657cdff9ee833cb2b3a0b3fa71b6cbc3dd1e0fbc71b74b9bbff9dca6b5b76767"
SECONDARY_SHA = "e3670b22ac71bad7523efe1e47b00f2345d1f103d2af8f7592e2f3f8c793a791"
REQUIRED_FIELDS = (
    "role", "dtype", "core_execution_count", "final_hidden_element_count",
    "final_normalized_element_count", "full_logits_element_count",
    "final_hidden_payload", "final_normalized_payload", "full_logits_payload",
    "final_hidden_sha256", "final_normalized_sha256", "full_logits_sha256",
    "layer_captures", "selected_token", "top_32", "top_1_margin", "tie_rule",
)
REQUIRED_PROHIBITIONS = {
    "FILE_IO", "CHECKPOINT_ACCESS", "LIFECYCLE_STATE", "AUTHORIZATION",
    "SUBPROCESS", "NEW_OR_UNREVIEWED_DYNAMIC_IMPORT", "REFLECTION",
    "FRAME_INSPECTION", "TRACING_HOOK", "DEBUGGER_HOOK",
    "CALLER_SUPPLIED_CAPTURE_CALLBACK",
}
FORMATS = ["F32", "F16", "Q4_0", "Q4_1", "Q5_0", "Q5_1", "Q8_0", "Q6_K", "IQ2_XXS", "IQ3_XXS", "BF16"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text())
    if type(value) is not dict:
        raise ValueError(f"object required: {path}")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


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
        result_assignment = isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "result"
            for target in statement.targets
        )
        if result_assignment or isinstance(statement, ast.Return):
            break
        body.append(statement)
    normalized = ast.FunctionDef(
        name="_execute_graph", args=function.args, body=body,
        decorator_list=[], returns=None, type_comment=None, type_params=[],
    )
    dumped = ast.dump(normalized, annotate_fields=True, include_attributes=False)
    return len(body), hashlib.sha256(dumped.encode()).hexdigest()


def validate_documents(output: dict, formulas: dict, source_map: dict, plan: dict) -> None:
    require(set(output) >= {
        "roles", "output_object", "qualification_geometry", "one_execution_rule",
        "legacy_compatibility", "hash_binding", "control_plane",
        "prohibited_capabilities", "accepted_historical_scoped_capabilities",
    }, "output contract key census")
    require(set(output["roles"]) == {"PRIMARY", "SECONDARY"}, "role census")
    expected_roles = {
        "PRIMARY": ("f64le", 8, [("final_hidden", 6144), ("final_normalized", 6144), ("full_logits", 154880)]),
        "SECONDARY": ("f32le", 4, [("final_hidden", 6144), ("final_normalized", 6144), ("full_logits", 154880)]),
    }
    for role, (dtype, itemsize, payloads) in expected_roles.items():
        record = output["roles"][role]
        require(record["dtype"] == dtype, f"dtype: {role}")
        require(record["geometry_scope"] == "PRODUCTION_V11_ENVELOPE", f"geometry scope: {role}")
        require(len(record["payloads"]) == 3, f"payload census: {role}")
        for actual, (kind, count) in zip(record["payloads"], payloads, strict=True):
            require(actual["kind"] == kind, f"payload kind: {role}/{kind}")
            require(actual["shape"] == [count], f"shape: {role}/{kind}")
            require(actual["element_count"] == count, f"elements: {role}/{kind}")
            require(actual["itemsize"] == itemsize, f"itemsize: {role}/{kind}")
            require(actual["expected_bytes"] == count * itemsize, f"bytes: {role}/{kind}")
    qgeometry = output["qualification_geometry"]
    require(qgeometry["primary_itemsize"] == 8 and qgeometry["secondary_itemsize"] == 4, "qualification itemsize")
    require(qgeometry["production_geometry_required_for_live_v11"] is True, "live production geometry")

    obj = output["output_object"]
    require(obj["frozen_dataclass"] is True, "frozen output")
    require(obj["deep_immutability"] == "REQUIRED", "deep immutability")
    require(obj["payload_representation"] == "IMMUTABLE_BYTES", "payload representation")
    require(obj["payload_endianness"] == "LITTLE", "payload endian")
    require(obj["writable_aliases"] == "PROHIBITED", "writable aliases")
    require(obj["cross_execution_reuse"] == "PROHIBITED", "cross execution reuse")
    require(obj["cross_role_buffer_sharing"] == "PROHIBITED", "cross role sharing")
    require(tuple(obj["fields"]) == REQUIRED_FIELDS, "output field census")
    field_types = obj["field_types"]
    require(field_types == {
        "payloads": "bytes",
        "layer_captures": "tuple[frozen_role_specific_layer_capture,...]",
        "top_32": "tuple[frozen_role_specific_top_record,...]",
        "scalar_metadata": "str|int|float",
        "mutable_list_or_dict_fields": "PROHIBITED",
    }, "output field types")

    one = output["one_execution_rule"]
    require(one["shared_internal_graph_path_per_role"] is True, "shared graph path")
    require(one["core_execution_count"] == 1, "one execution")
    for key in ("recompute_final_hidden", "recompute_final_normalized", "recompute_full_logits", "reconstruct_from_hash", "legacy_adapter_reruns_graph"):
        require(one[key] is False, key)
    require(one["capture_timing"] == {
        "final_hidden": "AFTER_FINAL_CONFIGURED_LAYER; production geometry completes 79 layers",
        "final_normalized": "AFTER_FINAL_RMS_NORMALIZATION",
        "full_logits": "AFTER_OUTPUT_PROJECTION",
    }, "capture timing")

    legacy = output["legacy_compatibility"]
    require(legacy["required"] == "EXACT", "legacy exact")
    require(legacy["runtime_scope"] == "PYTHON_SUCCESSOR_CORE_OFFLINE_REQUALIFICATION_AND_HISTORICAL_COMPATIBILITY_ONLY", "legacy scope")
    require(legacy["cross_language_json_equivalence_claimed"] is False, "cross language claim")
    require(legacy["active_v11_calls_legacy_api"] is False, "active legacy API")
    require(legacy["active_v11_serializes_legacy_result"] is False, "active legacy serialization")
    require(legacy["primary_canonical_json_bytes"] == "EXACT" and legacy["primary_result_sha256"] == "EXACT", "primary legacy")
    require(legacy["secondary_all_fields_and_values"] == "EXACT", "secondary legacy")
    require(legacy["source_read_census"] == "EXACT", "source reads")
    require(legacy["source_read_optimization_in_this_formula_preserving_scope"] == "PROHIBITED", "source optimization")

    control = output["control_plane"]
    require(control["output_object_is_control_json"] is False, "control object")
    require(control["full_payload_serialization"] == "PROHIBITED", "payload serialization")
    require(control["writable_array_serialization"] == "PROHIBITED", "writable serialization")
    require(control["v11_consumption"] == "DIRECT_BINARY_PAYLOAD_BANKING", "V11 consumption")
    require(control["legacy_full_logits_dictionary_allowed_only_in_offline_requalification"] is True, "offline legacy")
    require(control["legacy_full_logits_dictionary_rejected_by_active_control_serializer"] is True, "active serializer")
    require(set(output["prohibited_capabilities"]) == REQUIRED_PROHIBITIONS, "prohibited capability census")
    accepted = output["accepted_historical_scoped_capabilities"]
    require(accepted["capability_policy_sha256"] == "5ca6576781e269c18671b834b5d115494ec95462a17a59045e930eb256ce4d13", "capability policy")
    require("three existing function-scope mlx.core imports" in accepted["secondary_mlx_imports"], "scoped MLX imports")
    require("not output-capture callbacks" in accepted["source_store_rowmatrix_protocols"], "protocol scope")
    require(output["numerical_formulas_changed"] is False, "formula declaration")
    require(output["numerical_operation_order_changed"] is False, "operation order declaration")
    require(output["routing_semantics_changed"] is False and output["decoder_semantics_changed"] is False, "semantic declaration")

    require(sha(PRIMARY_V2) == PRIMARY_SHA and sha(SECONDARY_V2) == SECONDARY_SHA, "historical V2 byte authority")
    for role, path in (("primary", PRIMARY_V2), ("secondary", SECONDARY_V2)):
        observed = function_hashes(path)
        for symbol, expected in formulas[role]["formula_symbols"].items():
            require(observed.get(symbol) == expected, f"formula hash: {role}/{symbol}")
        statement_count, digest = graph_prefix(path)
        prefix = formulas[role]["graph_numerical_prefix"]
        require(statement_count == prefix["statement_count"] and digest == prefix["sha256"], f"graph prefix: {role}")
        require("terminal legacy return" in prefix["normalization"], f"prefix rule: {role}")
    require(formulas["primary_secondary_graph_consolidation"] == "PROHIBITED", "graph independence")
    require(formulas["shared_non_numerical_output_protocol"] == "PERMITTED", "output protocol")

    require(len(source_map["mappings"]) == 14, "source map census")
    require(source_map["numerical_expression_changes_allowed"] == 0, "numerical expression changes")
    for mapping in source_map["mappings"]:
        require(mapping["formula_status"] in {"MUST_BE_AST_EXACT", "NUMERICAL_PREFIX_EXACT_INTERFACE_SUFFIX_ONLY"}, "mapping status")
    require(plan["canonical_seeds"] == list(range(18101, 18113)), "canonical seeds")
    require(plan["expanded_seeds"] == list(range(17018, 17024)), "expanded seeds")
    require(plan["quantization_formats"] == FORMATS, "format corpus")
    require(plan["packed_decoder_cases"] == 44 and plan["numerical_localization_mutations"] == 16, "decoder corpus")
    require(all(value == 20 for value in plan["fresh_process_minimums"].values()), "fresh process corpus")
    require(plan["ownership_mutation_minimum"] == 50, "ownership mutations")
    require(plan["historical_observations_quarantined"] == [21615, 17351, 154820], "observation quarantine")


def set_path(document: dict, path: tuple[object, ...], value: object) -> None:
    target: object = document
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]


def mutation_suite(output: dict, formulas: dict, source_map: dict, plan: dict) -> tuple[list[str], list[str]]:
    mutations: list[tuple[str, Callable[[dict, dict, dict, dict], None]]] = []
    for role in ("PRIMARY", "SECONDARY"):
        for index, payload in enumerate(output["roles"][role]["payloads"]):
            base = ("roles", role, "payloads", index)
            mutations.extend([
                (f"{role}_{payload['kind']}_KIND", lambda o, f, s, p, b=base: set_path(o, b + ("kind",), "wrong")),
                (f"{role}_{payload['kind']}_SHAPE", lambda o, f, s, p, b=base: set_path(o, b + ("shape",), [1])),
                (f"{role}_{payload['kind']}_ELEMENTS", lambda o, f, s, p, b=base: set_path(o, b + ("element_count",), 1)),
                (f"{role}_{payload['kind']}_ITEMSIZE", lambda o, f, s, p, b=base: set_path(o, b + ("itemsize",), 1)),
                (f"{role}_{payload['kind']}_BYTES", lambda o, f, s, p, b=base: set_path(o, b + ("expected_bytes",), 1)),
            ])
    scalar_mutations = [
        (("output_object", "frozen_dataclass"), False),
        (("output_object", "deep_immutability"), "OPTIONAL"),
        (("output_object", "payload_representation"), "list"),
        (("output_object", "payload_endianness"), "BIG"),
        (("output_object", "writable_aliases"), "PERMITTED"),
        (("output_object", "cross_execution_reuse"), "PERMITTED"),
        (("output_object", "cross_role_buffer_sharing"), "PERMITTED"),
        (("one_execution_rule", "shared_internal_graph_path_per_role"), False),
        (("one_execution_rule", "core_execution_count"), 2),
        (("one_execution_rule", "recompute_final_hidden"), True),
        (("one_execution_rule", "recompute_final_normalized"), True),
        (("one_execution_rule", "recompute_full_logits"), True),
        (("one_execution_rule", "reconstruct_from_hash"), True),
        (("one_execution_rule", "legacy_adapter_reruns_graph"), True),
        (("legacy_compatibility", "required"), "APPROXIMATE"),
        (("legacy_compatibility", "cross_language_json_equivalence_claimed"), True),
        (("legacy_compatibility", "active_v11_calls_legacy_api"), True),
        (("legacy_compatibility", "active_v11_serializes_legacy_result"), True),
        (("legacy_compatibility", "source_read_census"), "CHANGED"),
        (("control_plane", "output_object_is_control_json"), True),
        (("control_plane", "full_payload_serialization"), "PERMITTED"),
        (("control_plane", "writable_array_serialization"), "PERMITTED"),
        (("control_plane", "v11_consumption"), "LEGACY_JSON"),
        (("qualification_geometry", "production_geometry_required_for_live_v11"), False),
        (("numerical_formulas_changed",), True),
        (("numerical_operation_order_changed",), True),
        (("routing_semantics_changed",), True),
        (("decoder_semantics_changed",), True),
    ]
    for index, (path, value) in enumerate(scalar_mutations):
        mutations.append((f"SCALAR_{index:02d}_{'_'.join(map(str, path))}", lambda o, f, s, p, q=path, v=value: set_path(o, q, v)))
    for field in REQUIRED_FIELDS:
        mutations.append((f"DROP_FIELD_{field}", lambda o, f, s, p, x=field: o["output_object"]["fields"].remove(x)))
    for capability in sorted(REQUIRED_PROHIBITIONS):
        mutations.append((f"DROP_PROHIBITION_{capability}", lambda o, f, s, p, x=capability: o["prohibited_capabilities"].remove(x)))
    for role in ("primary", "secondary"):
        for symbol in formulas[role]["formula_symbols"]:
            mutations.append((f"FORMULA_{role}_{symbol}", lambda o, f, s, p, r=role, x=symbol: set_path(f, (r, "formula_symbols", x), "0" * 64)))
        mutations.append((f"PREFIX_{role}_SHA", lambda o, f, s, p, r=role: set_path(f, (r, "graph_numerical_prefix", "sha256"), "0" * 64)))
        mutations.append((f"PREFIX_{role}_COUNT", lambda o, f, s, p, r=role: set_path(f, (r, "graph_numerical_prefix", "statement_count"), 999)))
    for index in range(len(source_map["mappings"])):
        mutations.append((f"SOURCE_MAP_{index:02d}", lambda o, f, s, p, i=index: set_path(s, ("mappings", i, "formula_status"), "")))
    for seed in plan["canonical_seeds"]:
        mutations.append((f"DROP_CANONICAL_{seed}", lambda o, f, s, p, x=seed: p["canonical_seeds"].remove(x)))
    for seed in plan["expanded_seeds"]:
        mutations.append((f"DROP_EXPANDED_{seed}", lambda o, f, s, p, x=seed: p["expanded_seeds"].remove(x)))
    for fmt in FORMATS:
        mutations.append((f"DROP_FORMAT_{fmt}", lambda o, f, s, p, x=fmt: p["quantization_formats"].remove(x)))

    rejected: list[str] = []
    unexpected: list[str] = []
    for mutation_id, mutate in mutations:
        documents = [copy.deepcopy(value) for value in (output, formulas, source_map, plan)]
        mutate(*documents)
        try:
            validate_documents(*documents)
        except ValueError:
            rejected.append(mutation_id)
        else:
            unexpected.append(mutation_id)
    return rejected, unexpected


def validate() -> dict:
    output, formulas, source_map, plan = map(load, (OUTPUT, FORMULAS, SOURCE_MAP, PLAN))
    validate_documents(output, formulas, source_map, plan)
    rejected, unexpected = mutation_suite(output, formulas, source_map, plan)
    require(len(rejected) >= 120 and not unexpected, "design mutation census")
    return {
        "schema": "pulsarmlx.f017.numerical-output-interface-design-validation/2.0.0",
        "historical_primary_sha256": sha(PRIMARY_V2),
        "historical_secondary_sha256": sha(SECONDARY_V2),
        "geometry_checks": 6,
        "formula_symbol_checks": sum(len(formulas[r]["formula_symbols"]) for r in ("primary", "secondary")),
        "graph_prefix_checks": 2,
        "source_mappings": len(source_map["mappings"]),
        "design_mutations": len(rejected) + len(unexpected),
        "design_mutations_rejected": len(rejected),
        "unexpected_passes": unexpected,
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
