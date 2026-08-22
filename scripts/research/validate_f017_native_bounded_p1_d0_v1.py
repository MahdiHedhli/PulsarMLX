#!/usr/bin/env python3
"""Strict validator for F017 D0 native numerical acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


class D0Error(ValueError):
    pass


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise D0Error(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data, object_pairs_hook=_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise D0Error(f"{label} is not strict JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise D0Error(f"{label} is not an object")
    return value


def _git(root: Path, *args: str) -> bytes:
    try:
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True).stdout
    except subprocess.CalledProcessError as exc:
        raise D0Error(f"git {' '.join(args)} failed") from exc


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate(contract_path: Path, root: Path) -> dict[str, Any]:
    raw = contract_path.read_bytes()
    contract = _json(raw, str(contract_path))
    if contract.get("schema") != "pulsarmlx.f017.native-bounded-p1-numeric-acceptance-contract" or contract.get("schema_version") != "1.0.0":
        raise D0Error("D0 schema mismatch")
    authority_path = root / contract["authority"]["authority_contract_path"]
    if _sha(authority_path.read_bytes()) != contract["authority"]["authority_contract_sha256"]:
        raise D0Error("D0 authority-root SHA mismatch")
    sources: dict[str, dict[str, Any]] = {}
    for binding in contract["bound_oracles"]:
        if set(binding) != {"branch", "commit", "path", "sha256", "role"}:
            raise D0Error("bound oracle field census mismatch")
        data = _git(root, "show", f"{binding['commit']}:{binding['path']}")
        if _sha(data) != binding["sha256"]:
            raise D0Error(f"bound oracle SHA mismatch: {binding['role']}")
        sources[binding["role"]] = _json(data, binding["role"])
    required_roles = {
        "INDEPENDENT_SYNTHETIC_SEVEN_BOUNDARY_ORACLE",
        "ACCEPTED_REDUCED_GEOMETRY_MLA_NUMERIC_CONTRACT",
        "ACCEPTED_OPERAND_CONDITIONED_QUANTIZED_MATVEC_BOUND",
        "ACCEPTED_COMPLETE_LAYER_PRODUCT_NUMERIC_CONTRACT",
        "ACCEPTED_CANONICAL_34_STAGE_VOCABULARY",
        "ACCEPTED_PROOF_REFERENCE_COMPARISON_VOCABULARY",
    }
    if set(sources) != required_roles:
        raise D0Error("D0 oracle role census mismatch")
    implementation_roles = {
        "INDEPENDENT_ORACLE_GENERATOR",
        "INDEPENDENCE_POLICY_VALIDATOR",
        "SEVEN_BOUNDARY_AND_EDGE_EXECUTABLE_ASSERTIONS",
        "CANDIDATE_BOUNDARY_IMPLEMENTATION",
    }
    seen_implementation: set[str] = set()
    for binding in contract["bound_oracle_implementation"]:
        if set(binding) != {"branch", "commit", "path", "sha256", "role"}:
            raise D0Error("oracle implementation field census mismatch")
        data = _git(root, "show", f"{binding['commit']}:{binding['path']}")
        if _sha(data) != binding["sha256"]:
            raise D0Error(f"oracle implementation SHA mismatch: {binding['role']}")
        seen_implementation.add(binding["role"])
    if seen_implementation != implementation_roles:
        raise D0Error("oracle implementation role census mismatch")
    independent = sources["INDEPENDENT_SYNTHETIC_SEVEN_BOUNDARY_ORACLE"]
    if set(independent["boundaries"]) != {
        "projection", "router", "complete_expert", "top8_shared",
        "mla_dense", "complete_layer", "final_norm_logits_topk",
    }:
        raise D0Error("independent seven-boundary oracle census mismatch")
    stage_source = sources["ACCEPTED_CANONICAL_34_STAGE_VOCABULARY"]
    expected_ids = [row["id"] for row in stage_source["stages"]]
    rows = contract["stage_rows"]
    if len(rows) != 34 or [row["ordinal"] for row in rows] != list(range(34)):
        raise D0Error("D0 stage ordinal census mismatch")
    if [row["id"] for row in rows] != expected_ids:
        raise D0Error("D0 stage vocabulary differs from accepted canonical bytes")
    classes = set(contract["classes"])
    allowed_metrics = set(contract["metric_profiles"])
    allowed_boundaries = {
        "projection", "router", "complete_expert", "top8_shared",
        "mla_dense", "complete_layer", "final_norm_logits_topk",
    }
    for row in rows:
        if set(row) != {"ordinal", "id", "backend", "class", "oracle", "metric", "boundary"}:
            raise D0Error(f"stage field census mismatch: {row.get('id')}")
        if row["class"] not in classes or row["class"] == "UNRESOLVED_NUMERIC_SEMANTICS":
            raise D0Error(f"unaccepted D0 class: {row['id']}")
        if row["metric"] not in allowed_metrics or row["boundary"] not in allowed_boundaries:
            raise D0Error(f"unresolved metric/oracle boundary: {row['id']}")
    expected_class_metric = {
        "input_hidden": ("BYTE_EXACT_REQUIRED", "exact_bytes"),
        "post_attention_residual": ("NUMERICALLY_BOUNDED_REQUIRED", "native_intermediate_tier_b"),
        "ranking": ("BYTE_EXACT_REQUIRED", "exact_bytes"),
        "selected_ids": ("BYTE_EXACT_REQUIRED", "exact_bytes"),
        "routing_weights": ("STRUCTURAL_EXACT_NUMERIC_BOUNDED", "routing_weight"),
        "routed_gate": ("NUMERICALLY_BOUNDED_REQUIRED", "operand_conditioned_matvec"),
        "routed_up": ("NUMERICALLY_BOUNDED_REQUIRED", "operand_conditioned_matvec"),
        "routed_down_outputs": ("NUMERICALLY_BOUNDED_REQUIRED", "operand_conditioned_matvec"),
        "routed_aggregate": ("INTENTIONALLY_DISTINCT", "native_intermediate_tier_b"),
        "shared_gate": ("NUMERICALLY_BOUNDED_REQUIRED", "operand_conditioned_matvec"),
        "shared_up": ("NUMERICALLY_BOUNDED_REQUIRED", "operand_conditioned_matvec"),
        "shared_expert_output": ("NUMERICALLY_BOUNDED_REQUIRED", "native_intermediate_tier_b"),
        "production_ffn": ("INTENTIONALLY_DISTINCT", "native_intermediate_tier_b"),
        "production_s2": ("INTENTIONALLY_DISTINCT", "native_final_tier_b"),
    }
    for row in rows:
        expected = expected_class_metric.get(
            row["id"],
            ("IMPLEMENTATION_SPECIFIC_REPRODUCIBILITY", "pinned_environment_reproduction"),
        )
        if (row["class"], row["metric"]) != expected:
            raise D0Error(f"stage class/metric binding changed: {row['id']}")
    route_ids = [
        "SELECTED_EXPERT_MEMBERSHIP_EXACT", "SELECTED_EXPERT_ORDER_EXACT",
        "TIE_BEHAVIOR_EXACT", "ROUTING_WEIGHT_NUMERIC_BOUNDS",
        "ROUTED_EXPERT_OUTPUT_GRADING", "ROUTED_AGGREGATE_GRADING",
    ]
    if contract["route_gate_order"] != route_ids:
        raise D0Error("routing structural gate order weakened")
    metrics = contract["metric_profiles"]
    expected_thresholds = {
        "native_intermediate_tier_b": (0.015625, 0.0078125, 0.9999),
        "native_final_tier_b": (0.0625, 0.03125, 0.999),
    }
    for name, values in expected_thresholds.items():
        actual = metrics[name]
        if (actual["max_absolute_error"], actual["rmse"], actual["cosine_similarity_minimum"]) != values:
            raise D0Error(f"frozen tolerance changed: {name}")
    r10 = sources["ACCEPTED_COMPLETE_LAYER_PRODUCT_NUMERIC_CONTRACT"]
    if (
        r10["intermediate"]["max_absolute_error"],
        r10["intermediate"]["rmse"],
        r10["intermediate"]["cosine_similarity_minimum"],
    ) != expected_thresholds["native_intermediate_tier_b"]:
        raise D0Error("R10 intermediate source no longer resolves to D0 values")
    if (
        r10["final"]["max_absolute_error"],
        r10["final"]["rmse"],
        r10["final"]["cosine_similarity_minimum"],
    ) != expected_thresholds["native_final_tier_b"]:
        raise D0Error("R10 final source no longer resolves to D0 values")
    expert = sources["ACCEPTED_OPERAND_CONDITIONED_QUANTIZED_MATVEC_BOUND"]
    if expert["per_element_absolute_bound"] != metrics["operand_conditioned_matvec"]["per_coordinate_cap"]:
        raise D0Error("operand-conditioned executable semantic binding mismatch")
    if metrics["routing_weight"]["max_absolute_error"] != 0.00001:
        raise D0Error("routing-weight tolerance changed")
    epistemics = contract["tolerance_epistemics"]
    required_epistemics = {
        "post_hoc_selection": False,
        "new_empirical_derivation_in_v1": False,
        "reused_contracts_were_frozen_before_target_results": True,
        "future_empirical_corpora": "SYNTHETIC_OR_PINNED_PUBLIC_SAFE_FIXTURE_ONLY",
        "retained_representative_bytes_may_set_thresholds": False,
        "d3_5_may_falsify_derivation": True,
        "d3_5_may_set_or_tune_value": False,
        "triggering_d3_5_output_quarantined_from_threshold_selection": True,
    }
    for key, expected in required_epistemics.items():
        if type(epistemics.get(key)) is not type(expected) or epistemics.get(key) != expected:
            raise D0Error(f"D0 epistemic rule weakened: {key}")
    policy = contract["execution_policy"]
    if policy["mlx_version"] != "0.31.2" or policy["mlx_c_version"] != "0.6.0":
        raise D0Error("native MLX runtime pin changed")
    if policy["device_brand"] != "Apple M1 Ultra" or policy["matvec_device"] != "GPU":
        raise D0Error("native device/backend policy changed")
    repeat = metrics["pinned_environment_reproduction"]
    if repeat["same_process_repetitions"] != 10 or repeat["fresh_process_repetitions"] != 10:
        raise D0Error("determinism repetition count changed")
    if repeat["numeric_tolerance_may_hide_repeat_failure"] is not False:
        raise D0Error("determinism failure may be hidden by tolerance")
    common = contract["common_acceptance"]
    if common["unresolved_stage_count"] != 0 or common["unexecuted_observed_results"] is not None:
        raise D0Error("D0 claims an observed result or unresolved stage")
    if contract["scope_limitations"]["full_forward_qualified_by_d3_5"] is not False:
        raise D0Error("D3.5 scope overclaimed")
    if contract["phase_invariants"] != {
        "real_m1_ultra_p1_executions": 0,
        "full_model_real_checkpoint_inference_executions": 0,
        "checkpoint_reads": 0,
        "live_p1_authorizations": 0,
    }:
        raise D0Error("D0 phase invariants changed")
    return {
        "result": "PASS",
        "sha256": _sha(raw),
        "stages": len(rows),
        "unresolved": 0,
        "post_hoc_tolerance": False,
        "retained_qualification_executed": False,
        "p1_executed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--contract", type=Path,
        default=Path("specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-numeric-acceptance-contract-v1.json"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    path = args.contract if args.contract.is_absolute() else root / args.contract
    print(json.dumps(validate(path, root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
