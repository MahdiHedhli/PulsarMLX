#!/usr/bin/env python3
"""Bank and audit one completed F017 v2 antecedent recovery.

This is a checkpoint-free evidence banker. It never imports or invokes the
recovery executor, opens checkpoint files, or changes the immutable private
recovery package. It derives summaries only from the retained public pair
surface and validates every private artifact against its retained hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
from pathlib import Path
from typing import Any, Iterable


CONFIG_SHA = "649a53630be246af11270f1cad19bdb8a7ccabf06e928febfe6cbc282dd4c7e2"
FINAL_V2_SHA = "36adbdcffeeb361638ec80258b912711b17a671276d68cf0129826e1ae042ac7"
RETENTION_SHA = "bd3cc6c10faee0d8c8072000403bbef68354286515482a6b78869ab02be81e13"
EXPECTED_ROUTE = [166, 78, 26, 186, 163, 199, 233, 177]


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    return raw, json.loads(raw, object_pairs_hook=reject_duplicates)


def write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def packed(values: Iterable[int | float], code: str) -> bytes:
    values = list(values)
    return struct.pack(f"<{len(values)}{code}", *values)


def summarize_surface(surface: dict[str, Any]) -> dict[str, Any]:
    membership = surface["selected_unselected_pair_bounds"]
    ordered = surface["adjacent_selected_pair_bounds"]
    if len(membership) != 1984 or len(ordered) != 7:
        raise ValueError("pair surface cardinality")
    if surface["selected_ids_ordered"] != EXPECTED_ROUTE or len(surface["unselected_ids"]) != 248:
        raise ValueError("route surface identity")
    for item in (*membership, *ordered):
        if not all(math.isfinite(float(item[key])) for key in ("margin", "B_pair", "safety_factor")):
            raise ValueError("non-finite pair surface")
        if item["B_pair"] < 0.0:
            raise ValueError("negative pair bound")
    worst_membership = min(membership, key=lambda item: item["safety_factor"])
    worst_ordered = min(ordered, key=lambda item: item["safety_factor"])
    global_worst = min((worst_membership, worst_ordered), key=lambda item: item["safety_factor"])
    membership_stable = all(item["margin"] > item["B_pair"] for item in membership)
    ordered_stable = all(item["margin"] > item["B_pair"] for item in ordered)
    membership_headroom = all(item["margin"] >= 2.0 * item["B_pair"] for item in membership)
    ordered_headroom = all(item["margin"] >= 2.0 * item["B_pair"] for item in ordered)
    worst_per_selected = []
    for selected in EXPECTED_ROUTE:
        item = min(
            (candidate for candidate in membership if candidate["selected"] == selected),
            key=lambda candidate: candidate["safety_factor"],
        )
        worst_per_selected.append(item)
    minimum = float(global_worst["safety_factor"])
    return {
        "membership_pair_count": 1984,
        "ordered_selected_pair_count": 7,
        "membership_stable": membership_stable,
        "membership_engineering_headroom": membership_headroom,
        "ordered_selected_stable": ordered_stable,
        "ordered_selected_engineering_headroom": ordered_headroom,
        "exact_ordered_top8_mathematically_stable": membership_stable and ordered_stable,
        "exact_ordered_top8_engineering_headroom": membership_headroom and ordered_headroom,
        "minimum_mathematical_safety_factor": minimum,
        "minimum_engineering_safety_factor": minimum / 2.0,
        "worst_membership_pair": worst_membership,
        "worst_ordered_selected_pair": worst_ordered,
        "global_worst_pair": global_worst,
        "worst_challenger_per_selected": worst_per_selected,
        "mathematical_classification": (
            "MATHEMATICALLY_STABLE" if membership_stable and ordered_stable
            else "NOT_MATHEMATICALLY_STABLE"
        ),
        "engineering_classification": (
            "ENGINEERING_HEADROOM" if membership_headroom and ordered_headroom
            else "NO_ENGINEERING_HEADROOM"
        ),
    }


def descriptor(
    package: Path,
    symbolic_name: str,
    dtype: str,
    shape: list[int],
    element_count: int,
    ordinal: int,
    source_tensors: list[dict[str, str]],
) -> dict[str, Any]:
    path = package / symbolic_name
    raw = path.read_bytes()
    if path.stat().st_mode & 0o222:
        raise ValueError("private artifact is writable")
    return {
        "artifact_id": Path(symbolic_name).stem,
        "path_kind": "private_package_relative",
        "symbolic_name": symbolic_name,
        "sha256": sha256(raw),
        "dtype": dtype,
        "shape": shape,
        "element_count": element_count,
        "canonical_serialization": dtype,
        "provenance": "independent_python_numpy_accepted_boundary_recovery",
        "source_tensor_identities": source_tensors,
        "creation_ordinal": ordinal,
        "immutable": True,
        "read_only": True,
        "byte_length": len(raw),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--private-package", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--authorization-sha256", required=True)
    parser.add_argument("--start-marker", type=Path, required=True)
    parser.add_argument("--output-result", type=Path, required=True)
    parser.add_argument("--output-private-manifest", type=Path, required=True)
    parser.add_argument("--output-review", type=Path, required=True)
    args = parser.parse_args()

    root = args.repository_root.resolve(strict=True)
    package = args.private_package.resolve(strict=True)
    config_raw, config = read_json(root / "docs/architecture/reviews/evidence/f017-v2-antecedent-recovery-execution-config-v1.json")
    if sha256(config_raw) != CONFIG_SHA:
        raise ValueError("execution config identity")
    authorization_raw, authorization = read_json(args.authorization.resolve(strict=True))
    if sha256(authorization_raw) != args.authorization_sha256:
        raise ValueError("authorization identity")
    if authorization["execution_config_sha256"] != CONFIG_SHA:
        raise ValueError("authorization/config binding")
    marker_raw, marker = read_json(args.start_marker.resolve(strict=True))
    if marker["state"] != "ANALYTICAL_RECOVERY_STARTED" or marker["route_attempt_consumed"]:
        raise ValueError("execution start semantics")
    if marker["execution_config_sha256"] != CONFIG_SHA:
        raise ValueError("start/config binding")

    result_path = package / "recovery-result.json"
    result_raw, result = read_json(result_path)
    if result_raw != canonical_json(result):
        raise ValueError("noncanonical recovery result")
    if not result["identity_reproduction"]["accepted_computation_reproduced_exactly"]:
        raise ValueError("identity reproduction")
    if result["historical_status"] != {
        "historical_v1_status_unchanged": True,
        "accepted_route_reclassified": False,
    }:
        raise ValueError("historical status")
    if result["scope"] != config["semantics"] or result["access"] != config["access_budget"]:
        raise ValueError("scope/access identity")
    retention = result["antecedent_retention"]
    if retention["manifest_sha256"] != RETENTION_SHA or not retention["complete"]:
        raise ValueError("retention status")
    surface = retention["pairwise_surface"]
    summary = summarize_surface(surface)

    source = {
        item["name"]: {
            "name": item["name"],
            "packed_sha256": item["packed_sha256"],
            "decoded_sha256": item["decoded_sha256"],
        }
        for item in config["tensor_allowlist"]
    }
    attention_names = [item["name"] for item in config["tensor_allowlist"][:9]]
    norm_name = "blk.3.ffn_norm.weight"
    router_name = "blk.3.ffn_gate_inp.weight"
    definitions = [
        ("antecedents/attention_residual.bin", "little-endian-f32", [6144], 6144, attention_names),
        ("antecedents/router_normalized_input.bin", "little-endian-f32", [6144], 6144, [*attention_names, norm_name]),
        ("antecedents/router_matrix.bin", "little-endian-f32", [256, 6144], 256 * 6144, [router_name]),
        ("antecedents/ffn_norm_weight.bin", "little-endian-f32", [6144], 6144, [norm_name]),
        ("antecedents/rmsnorm_decomposition_inputs.bin", "canonical-json", [1], 1, [*attention_names, norm_name]),
        ("antecedents/non_radial_component_bounds.bin", "little-endian-f64", [6144], 6144, [*attention_names, norm_name]),
        ("antecedents/router_reduction_bounds.bin", "little-endian-f64", [256], 256, [router_name]),
        ("antecedents/router_import_materialization_bounds.bin", "little-endian-f64", [256], 256, [router_name]),
    ]
    descriptors = [
        descriptor(package, name, dtype, shape, count, ordinal, [source[item] for item in names])
        for ordinal, (name, dtype, shape, count, names) in enumerate(definitions, start=1)
    ]
    retained_hashes = retention["private_artifacts"]
    if {item["symbolic_name"]: item["sha256"] for item in descriptors} != retained_hashes:
        raise ValueError("private-artifact hash mismatch")
    rms = json.loads((package / "antecedents/rmsnorm_decomposition_inputs.bin").read_text(), object_pairs_hook=reject_duplicates)
    expected_rms = {
        "oracle_rms_squared_plus_epsilon", "oracle_inverse_rms",
        "inverse_rms_error_bound", "lambda_bound",
    }
    if set(rms) != expected_rms or not all(math.isfinite(float(value)) for value in rms.values()):
        raise ValueError("RMSNorm antecedent completeness")

    analytical = json.loads((root / "docs/architecture/reviews/evidence/f017-m1-f0-router-analytical-recovery-v1.json").read_text())
    routing_weights = analytical["canonical_analytics"]["artifacts"]["routing_weights"]
    objects = {
        "router_logits": (retention["router_logits"], "d"),
        "router_probabilities": (retention["router_probabilities"], "d"),
        "router_bias": (retention["router_bias"], "f"),
        "router_scores": (retention["router_scores"], "d"),
        "ranking": (retention["ranking"], "H"),
        "selected_ids_ordered": (surface["selected_ids_ordered"], "H"),
        "unselected_ids": (surface["unselected_ids"], "H"),
    }
    analytical_hashes = {
        name: {
            "element_count": len(values),
            "canonical_serialization": {"d": "little-endian-f64", "f": "little-endian-f32", "H": "little-endian-u16"}[code],
            "sha256": sha256(packed(values, code)),
        }
        for name, (values, code) in objects.items()
    }
    analytical_hashes["selected_unselected_pair_bounds"] = {
        "element_count": 1984,
        "canonical_serialization": "canonical-json",
        "sha256": sha256(canonical_json(surface["selected_unselected_pair_bounds"])),
    }
    analytical_hashes["adjacent_selected_pair_bounds"] = {
        "element_count": 7,
        "canonical_serialization": "canonical-json",
        "sha256": sha256(canonical_json(surface["adjacent_selected_pair_bounds"])),
    }
    analytical_hashes["routing_weights"] = routing_weights

    private_manifest = {
        "schema": "pulsarmlx.f017.v2-antecedent-recovery-private-manifest",
        "schema_version": "1.0.0",
        "retention_manifest_sha256": RETENTION_SHA,
        "recovery_result_sha256": sha256(result_raw),
        "artifact_count": 8,
        "artifacts": descriptors,
        "rmsnorm_decomposition_inputs": rms,
        "local_sigmoid_interval_policy": {
            "direct_logits_retained": True,
            "interval_inputs_reconstructable_from": [
                "router_logits", "router_matrix", "lambda_bound",
                "non_radial_component_bounds", "router_reduction_bounds",
                "router_import_materialization_bounds",
            ],
        },
        "machine_local_paths_published": False,
        "result": "PASS",
    }
    raw_summary = result["retrospective_v2"]
    review = {
        "schema": "pulsarmlx.f017.v2-antecedent-recovery-review",
        "schema_version": "1.0.0",
        "execution": {
            "reviewed_head": "493a087a4aafc28aee1e5933400ac77366521361",
            "tooling_commit": config["source_identities"]["tooling_commit_sha"],
            "tooling_tree": config["source_identities"]["tooling_tree_oid"],
            "execution_config_sha256": CONFIG_SHA,
            "authorization_sha256": args.authorization_sha256,
            "start_marker_sha256": sha256(marker_raw),
            "start_unix_ns": marker["recorded_unix_ns"],
            "completion_artifact_mtime_ns": result_path.stat().st_mtime_ns,
            "observed_duration_ns": result_path.stat().st_mtime_ns - marker["recorded_unix_ns"],
            "event_consumed": True,
            "route_attempt_consumed": False,
        },
        "contracts": {"final_v2_sha256": FINAL_V2_SHA, "retention_manifest_sha256": RETENTION_SHA},
        "identity_reproduction": result["identity_reproduction"],
        "analytical_objects": analytical_hashes,
        "pairwise_summary": summary,
        "immutable_raw_summary_audit": {
            "raw_recovery_result_sha256": sha256(result_raw),
            "raw_reported_minimum_mathematical_safety_factor": raw_summary["minimum_mathematical_safety_factor"],
            "raw_reported_minimum_engineering_safety_factor": raw_summary["minimum_engineering_safety_factor"],
            "finding": "executor returned the first failing ordered pair rather than the global minimum and reused exact-ordered stability as the route-set summary",
            "disposition": "raw result preserved; corrected summary derived from all retained pairs without checkpoint access",
            "overall_exact_ordered_classification_changed": False,
            "membership_subclassification_corrected": raw_summary["route_set_stable"] != summary["membership_stable"],
            "raw_reported_route_set_stable": raw_summary["route_set_stable"],
            "corrected_membership_stable": summary["membership_stable"],
        },
        "private_manifest_sha256": sha256(canonical_json(private_manifest)),
        "access": result["access"],
        "ledger_transition": {"before": 45, "delta": 12, "after": 57},
        "historical_status": result["historical_status"],
        "scope": result["scope"],
        "checkpoint_reads_during_banking": 0,
        "retry_performed": False,
        "result": "V2_ANTECEDENT_RECOVERY_ACCEPTED",
    }

    write_exclusive(args.output_result, result_raw)
    write_exclusive(args.output_private_manifest, canonical_json(private_manifest))
    write_exclusive(args.output_review, canonical_json(review))
    print(sha256(result_raw))
    print(sha256(canonical_json(private_manifest)))
    print(sha256(canonical_json(review)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
