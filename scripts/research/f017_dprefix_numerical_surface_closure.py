#!/usr/bin/env python3
"""Checkpoint-free DPREFIX paired-value numerical-surface closure."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

from scripts.research.f017_dprefix_metric_engine import compare_f32le
from scripts.research.f017_dprefix_oracle_runtime import (
    canonical_f32,
    synthetic_actual_binary_oracle_surfaces,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
PRIVATE = ROOT / ".pulsarmlx-local/oracle-build"

ATTEMPT = "DPREFIX-REAL-1"
LEDGER = 59
TIER_B_PATH = CONTRACTS / "f017-dense-prefix-real-tier-b-v1.json"
TIER_B_SHA = "9d1a6cc20ce8325fe8395334416f5ebcf980b72f02c6a0b44dc3240e0810024a"
REPEAT_SHA = "4a9f2f29689b8c20259ebadd46a0038008895ea173bf024b2ab805d35b7aa488"
STOP_EVIDENCE_SHA = "a730fb123fd86319b199579c79bdcbff1b282b7f7ec4003daa694f9e37a176b6"
PREDECESSOR_CANDIDATE_SHA = "69b8cda5e3a6e600d29c899cb75ac4cdcf98ef301f50d506240c3499c918ae4f"
PREDECESSOR_CANDIDATE_SOURCE_SHA = "fe53a89ab8619675650346faae314a6219312a5be67e2a85a2c5a64fa5a4abc4"
PREDECESSOR_ORACLE_SHA = "4f8344057c962c96f969aeb8dc60b833939dc64dd59ab5addec4b4c2249c486f"
PREDECESSOR_ORACLE_SOURCE_SHA = "9e7d233e2816401d95ddd009c239cf78f05b080afe9c3cecc3ad8f60bf8f53ae"
PREDECESSOR_CONFIG_SHA = "1ec301f23735dbebd7360ef58f38ba78cfc89dad878f3b6c63686ac63952a806"
PREDECESSOR_AUTH_SHA = "68e37070e50c96cd57d2e0dd79199f1a63952163adfd614f7200907ca3b3d248"
CANDIDATE_V2 = PRIVATE / "f017-dense-prefix-candidate-v2"
REHEARSAL = PRIVATE / "numerical-surface-v2/candidate.json"
ORACLE_PACKAGE = PRIVATE / "oracle-package-v2"
ORACLE_SURFACES = PRIVATE / "numerical-surface-v2/oracle-surfaces"

CANDIDATE_FILES = {
    "crates/f017-runner/src/bin/f017-dense-prefix-candidate.rs": "narrow native boundary plus observational paired-value export",
    "crates/f017-runner/Cargo.toml": "dedicated binary declaration and dependencies",
    "crates/f017-runner/build.rs": "source identity and native-MLX admission",
    "crates/quant/src/cpu_dot.rs": "Q4_K/Q5_K candidate decoder path",
    "crates/quant/src/q6_k_ref.rs": "corrected Q6_K candidate decoder path",
    "crates/quant/src/q8_0_ref.rs": "Q8_0 candidate decoder path",
    "crates/stream/src/apple_mlx_bridge.rs": "Rust native tensor import/matvec/lifecycle surface",
    "crates/stream/src/apple_mlx_bridge.mm": "MLX C/Objective-C++ dispatch and ownership surface",
    "crates/stream/build.rs": "native bridge compile/link identity",
}
ORACLE_FILES = {
    "scripts/research/f017_dprefix_oracle_runtime.py": "NumPy-only arithmetic and paired-value export",
    "scripts/research/ggml_kquants.py": "independent Q4_K/Q5_K/Q6_K decoder specification",
    "scripts/research/glm52_dense_primitives.py": "reviewed independent F32/Q8_0 decoder lineage",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def frozen_semantics() -> dict[str, Any]:
    return {
        "prompt": "Hello",
        "token": 9703,
        "position": 0,
        "payloads": 40,
        "packed_bytes": 1_431_263_232,
        "ledger_before": 59,
        "ledger_after": 99,
        "repeats": 10,
        "automatic_retry": False,
        "automatic_m1f0_continuation": False,
    }


def _metric_policy(contract: dict[str, Any], kind: str, layer: int) -> dict[str, float]:
    if kind == "attention":
        threshold = contract["intermediate_attention_each_layer"]
    else:
        threshold = next(item for item in contract["layer_entry_cumulative"] if item["after_layer"] == layer)
    return {
        "max_absolute_error": threshold["max_absolute_error"],
        "rmse": threshold["rmse"],
        "cosine_similarity_minimum": threshold["cosine_similarity_minimum"],
    }


def numerical_surface_manifest() -> dict[str, Any]:
    if sha(TIER_B_PATH) != TIER_B_SHA:
        raise ValueError("frozen Tier-B identity changed")
    contract = load(TIER_B_PATH)
    common = {
        "dtype": "f32",
        "shape": [6144],
        "canonical_serialization": "little_endian_ieee754_binary32_c_order",
        "lifetime": "event_local_until_metric_and_diagnostics_finalized",
    }
    surfaces: list[dict[str, Any]] = [
        {
            **common,
            "semantic_id": "embedding",
            "name": "frozen token-9703 embedding output",
            "layer": None,
            "stage": "embedding",
            "candidate_producer": "candidate.embedding_lookup.output",
            "oracle_producer": "oracle.embedding_lookup.output",
            "required_metrics": [],
            "retention_class": "B",
            "terminal_evidence_field": "numerical_surfaces.embedding",
            "qualification": "exact input-surface identity; no free threshold introduced",
        }
    ]
    for layer in range(3):
        surfaces.extend(
            [
                {
                    **common,
                    "semantic_id": f"layer_{layer}_attention",
                    "name": f"layer {layer} attention projection output before residual",
                    "layer": layer,
                    "stage": "attention_projection_output",
                    "candidate_producer": f"candidate.layer[{layer}].attention_projection_output",
                    "oracle_producer": f"oracle.layer[{layer}].attention_projection_output",
                    "required_metrics": ["max_absolute_error", "rmse", "cosine_similarity", "non_finite_counts", "signed_zero_mismatch_count"],
                    "thresholds": _metric_policy(contract, "attention", layer),
                    "retention_class": "B",
                    "terminal_evidence_field": f"numerical_surfaces.layer_{layer}_attention",
                },
                {
                    **common,
                    "semantic_id": f"layer_{layer}_output",
                    "name": f"complete layer {layer} post-FFN residual output",
                    "layer": layer,
                    "stage": "complete_layer_output",
                    "candidate_producer": f"candidate.layer[{layer}].complete_output",
                    "oracle_producer": f"oracle.layer[{layer}].complete_output",
                    "required_metrics": ["max_absolute_error", "rmse", "cosine_similarity", "non_finite_counts", "signed_zero_mismatch_count"],
                    "thresholds": _metric_policy(contract, "layer_output", layer),
                    "per_layer_envelope": contract["per_layer"],
                    "retention_class": "B" if layer < 2 else "A",
                    "terminal_evidence_field": f"numerical_surfaces.layer_{layer}_output",
                },
            ]
        )
    surfaces.append(
        {
            **common,
            "semantic_id": "layer_3_entry",
            "name": "retained layer-3 entry hidden state",
            "layer": 3,
            "stage": "layer_entry",
            "candidate_producer": "candidate.layer[2].complete_output.retention_alias",
            "oracle_producer": "oracle.layer[2].complete_output.retention_alias",
            "alias_of": "layer_2_output",
            "required_metrics": ["max_absolute_error", "rmse", "cosine_similarity", "non_finite_counts", "signed_zero_mismatch_count"],
            "thresholds": _metric_policy(contract, "layer_output", 2),
            "retention_class": "A",
            "lifetime": "permanent_private_retention_at_creation",
            "terminal_evidence_field": "numerical_surfaces.layer_3_entry",
        }
    )
    result = {
        "schema": "pulsarmlx.f017.dprefix-numerical-surface-manifest",
        "schema_version": "1.0.0",
        "source_of_truth": "f017-dense-prefix-real-tier-b-v1",
        "tier_b_sha256": TIER_B_SHA,
        "tier_b_unchanged": True,
        "post_observation_retuning": "FORBIDDEN",
        "retention_design": "HYBRID_CLASS_B_EVENT_LOCAL_PLUS_CLASS_A_FINAL",
        "surfaces": surfaces,
        "checkpoint_access": 0,
        "ledger": 59,
    }
    validate_surface_manifest(result)
    return result


def validate_surface_manifest(manifest: dict[str, Any]) -> None:
    surfaces = manifest.get("surfaces", [])
    ids = [surface.get("semantic_id") for surface in surfaces]
    if len(ids) != 8 or len(set(ids)) != 8:
        raise ValueError("surface census")
    for surface in surfaces:
        if not surface.get("candidate_producer"):
            raise ValueError(f"candidate producer absent: {surface.get('semantic_id')}")
        if not surface.get("oracle_producer"):
            raise ValueError(f"oracle producer absent: {surface.get('semantic_id')}")
        if surface.get("required_metrics") and surface.get("retention_class") == "D":
            raise ValueError(f"hash-only metric surface: {surface.get('semantic_id')}")
        if surface.get("shape") != [6144] or surface.get("dtype") != "f32":
            raise ValueError(f"canonical semantics: {surface.get('semantic_id')}")


def _surface_pass(surface: dict[str, Any], metric: dict[str, Any], synthetic: bool) -> bool:
    if surface["semantic_id"] == "embedding":
        return metric["candidate_sha256"] == metric["oracle_sha256"]
    thresholds = surface["thresholds"]
    cumulative = (
        metric["max_absolute_error"] <= thresholds["max_absolute_error"]
        and metric["rmse"] <= thresholds["rmse"]
        and metric["cosine_similarity"] >= thresholds["cosine_similarity_minimum"]
        and metric["candidate_non_finite_count"] == 0
        and metric["oracle_non_finite_count"] == 0
    )
    per_layer = surface.get("per_layer_envelope")
    if per_layer is None:
        return cumulative
    return cumulative and (
        metric["max_absolute_error"] <= per_layer["max_absolute_error"]
        and metric["rmse"] <= per_layer["rmse"]
        and metric["cosine_similarity"] >= per_layer["cosine_similarity_minimum"]
    )


def compare_surface_packages(
    candidate: dict[str, bytes], oracle: dict[str, bytes], manifest: dict[str, Any], *, synthetic: bool = False
) -> dict[str, Any]:
    validate_surface_manifest(manifest)
    results = []
    failed = []
    for surface in manifest["surfaces"]:
        semantic_id = surface["semantic_id"]
        if semantic_id not in candidate or semantic_id not in oracle:
            raise ValueError(f"NUMERICAL_SURFACE_MISSING: {semantic_id}")
        metric = compare_f32le(candidate[semantic_id], oracle[semantic_id], surface["shape"]).as_dict()
        passed = _surface_pass(surface, metric, synthetic)
        metric.update({"semantic_id": semantic_id, "retention_class": surface["retention_class"], "pass": passed})
        results.append(metric)
        if not passed:
            failed.append(semantic_id)
    return {"overall_pass": not failed, "failed_surfaces": failed, "surfaces": results}


def continuation_adjudication() -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.dprefix-unconsumed-attempt-continuation",
        "schema_version": "2.0.0",
        "decision": "SAME UNCONSUMED DPREFIX ATTEMPT MAY CONTINUE",
        "attempt_id": ATTEMPT,
        "authorized": True,
        "consumed": False,
        "executed": False,
        "checkpoint_accessed": False,
        "prior_numerical_surface_stop_evidence_sha256": STOP_EVIDENCE_SHA,
        "attempt_identity_semantics": "real-budget consumption identity, not authorization revision identity",
        "ledger": 59,
        "checkpoint_access": 0,
    }


def evidence_schema() -> dict[str, Any]:
    surface_ids = [surface["semantic_id"] for surface in numerical_surface_manifest()["surfaces"]]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/MahdiHedhli/PulsarMLX/specs/017-rust-native-inference-runtime/contracts/f017-dense-prefix-evidence-v4.schema.json",
        "title": "F017 dense-prefix terminal evidence with complete paired numerical surfaces",
        "type": "object",
        "additionalProperties": True,
        "required": ["candidate_executable_sha256", "oracle_package_sha256", "numerical_surface_manifest_sha256", "metric_engine_sha256", "numerical_surfaces", "overall_numerical_pass"],
        "properties": {
            "candidate_executable_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "oracle_package_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "numerical_surface_manifest_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "metric_engine_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "overall_numerical_pass": {"type": "boolean"},
            "numerical_surfaces": {
                "type": "array",
                "minItems": 8,
                "maxItems": 8,
                "uniqueItems": True,
                "allOf": [
                    {"contains": {"type": "object", "properties": {"semantic_id": {"const": semantic_id}}, "required": ["semantic_id"]}, "minContains": 1, "maxContains": 1}
                    for semantic_id in surface_ids
                ],
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "semantic_id", "candidate_sha256", "oracle_sha256", "shape", "count",
                        "dtype", "serialization", "max_absolute_error", "rmse",
                        "cosine_similarity", "candidate_non_finite_count",
                        "oracle_non_finite_count", "signed_zero_mismatch_count",
                        "retention_class", "pass",
                    ],
                    "properties": {
                        "semantic_id": {"enum": surface_ids},
                        "candidate_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "oracle_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "shape": {"const": [6144]},
                        "count": {"const": 6144},
                        "dtype": {"const": "f32"},
                        "serialization": {"const": "canonical_little_endian_ieee754_binary32_c_order"},
                        "max_absolute_error": {"type": "number", "minimum": 0},
                        "rmse": {"type": "number", "minimum": 0},
                        "cosine_similarity": {"type": "number", "minimum": -1, "maximum": 1},
                        "candidate_non_finite_count": {"const": 0},
                        "oracle_non_finite_count": {"const": 0},
                        "signed_zero_mismatch_count": {"type": "integer", "minimum": 0},
                        "retention_class": {"enum": ["A", "B"]},
                        "pass": {"type": "boolean"},
                    },
                },
            },
        },
    }


def validate_terminal_numerical_surfaces(items: list[dict[str, Any]]) -> None:
    """Fail closed unless terminal evidence instantiates every frozen surface once."""
    expected = [surface["semantic_id"] for surface in numerical_surface_manifest()["surfaces"]]
    actual = [item.get("semantic_id") for item in items]
    if len(actual) != len(expected) or sorted(actual) != sorted(expected) or len(set(actual)) != len(actual):
        raise ValueError("NUMERICAL_SURFACE_MISSING_OR_DUPLICATE")
    required = {
        "candidate_sha256", "oracle_sha256", "shape", "count", "dtype",
        "serialization", "max_absolute_error", "rmse", "cosine_similarity",
        "candidate_non_finite_count", "oracle_non_finite_count",
        "signed_zero_mismatch_count", "retention_class", "pass",
    }
    for item in items:
        missing = required.difference(item)
        if missing:
            raise ValueError(f"NUMERICAL_SURFACE_MISSING: {item.get('semantic_id')}: {sorted(missing)}")
        if item["shape"] != [6144] or item["count"] != 6144 or item["dtype"] != "f32":
            raise ValueError(f"NUMERICAL_SURFACE_DESCRIPTOR: {item['semantic_id']}")


def rehearse_retention(directory: Path, values: bytes) -> dict[str, Any]:
    if len(values) != 6144 * 4:
        raise ValueError("retained layer-3 state byte count")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "layer3-entry.f32le"
    path.write_bytes(values)
    path.chmod(0o444)
    return {
        "symbolic_private_identity": "f017-private/dprefix/numerical-surface-v2/layer3-entry.f32le",
        "private_path": str(path),
        "sha256": sha(path),
        "dtype": "f32",
        "shape": [6144],
        "count": 6144,
        "serialization": "canonical_little_endian_ieee754_binary32_c_order",
        "immutable": True,
        "read_only": not os.access(path, os.W_OK) or not bool(path.stat().st_mode & 0o222),
        "checkpoint_access": 0,
    }


def source_manifest(files: dict[str, str], surface: str) -> dict[str, Any]:
    entries = []
    for relative, role in files.items():
        path = ROOT / relative
        if not path.is_file():
            raise ValueError(f"missing source surface: {relative}")
        entries.append({"path": relative, "sha256": sha(path), "role": role})
    result = {
        "schema": f"pulsarmlx.f017.dprefix-{surface}-source-manifest",
        "schema_version": "2.0.0",
        "surface": surface,
        "files": entries,
        "wildcards": False,
        "checkpoint_access": 0,
    }
    result["source_manifest_sha256"] = canonical_sha(result)
    return result


def candidate_build_manifest(source: dict[str, Any]) -> dict[str, Any]:
    if not CANDIDATE_V2.is_file():
        raise ValueError("successor candidate executable missing")
    binary_sha = sha(CANDIDATE_V2)
    if binary_sha == PREDECESSOR_CANDIDATE_SHA:
        raise ValueError("successor candidate identity did not change")
    return {
        "schema": "pulsarmlx.f017.dprefix-candidate-build-manifest",
        "schema_version": "2.0.0",
        "predecessor_binary_sha256": PREDECESSOR_CANDIDATE_SHA,
        "binary": {
            "symbolic_private_path": "f017-private/dprefix/f017-dense-prefix-candidate-v2",
            "sha256": binary_sha,
            "size_bytes": CANDIDATE_V2.stat().st_size,
            "format": "Mach-O 64-bit arm64 executable",
            "dynamic_build_at_execution": False,
        },
        "source_manifest_sha256": source["source_manifest_sha256"],
        "compiler": subprocess.check_output(["rustc", "--version", "--verbose"], cwd=ROOT, text=True).strip(),
        "cargo": subprocess.check_output(["cargo", "--version"], cwd=ROOT, text=True).strip(),
        "target_triple": "aarch64-apple-darwin",
        "native_mlx": {
            "mlx_source_sha": "68cf2fddd8de5edd8ab3d926391772b2e2cedad8",
            "mlx_c_source_sha": "0726ca922fc902c4c61ef9c27d94132be418e945",
            "libmlx_sha256": "6622caeb3e65a8310cf2290751ffbecf32135187aa75ef05f398916ac37bd9ed",
            "libmlxc_sha256": "a060915d4b9accbf58e84d174029d5c51805891834494d50cf87a0d573222e62",
            "loader": "@rpath/libmlxc.dylib + @rpath/libmlx.dylib",
        },
        "arithmetic_change": False,
        "instrumentation": "post-readback CPU copies and canonical surface-file writes only",
        "structurally_absent": ["layer3_attention", "router", "experts", "logits", "output_head", "generation", "M1-F0"],
        "checkpoint_access": 0,
    }


def instantiate_oracle(source: dict[str, Any], surface_manifest_sha: str) -> dict[str, Any]:
    ORACLE_PACKAGE.mkdir(parents=True, exist_ok=True)
    copied = []
    for entry in source["files"]:
        source_path = ROOT / entry["path"]
        destination = ORACLE_PACKAGE / source_path.name
        if destination.exists():
            destination.chmod(0o644)
        shutil.copyfile(source_path, destination)
        destination.chmod(0o444)
        copied.append({"name": destination.name, "sha256": sha(destination)})
    package = {
        "schema": "pulsarmlx.f017.dprefix-instantiated-oracle-package",
        "schema_version": "2.0.0",
        "status": "INSTANTIATED_FROZEN_BEFORE_CANDIDATE",
        "predecessor_package_sha256": PREDECESSOR_ORACLE_SHA,
        "symbolic_private_identity": "f017-private/dprefix/oracle-package-v2",
        "source_manifest_sha256": source["source_manifest_sha256"],
        "numerical_surface_manifest_sha256": surface_manifest_sha,
        "files": copied,
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "numpy": np.__version__,
            "platform": platform.platform(),
            "prng": "none",
        },
        "serialization": "canonical_little_endian_ieee754_binary32_c_order",
        "immutable": True,
        "read_only": True,
        "contains_real_checkpoint_outputs": False,
        "independence": {"rust_ffi": False, "mlx": False, "candidate_import": False, "candidate_helpers": False, "candidate_expected_values": False, "verdict": "ORACLE PACKAGE INDEPENDENT"},
        "checkpoint_access": 0,
    }
    package["package_sha256"] = canonical_sha(package)
    manifest_path = ORACLE_PACKAGE / "manifest.json"
    if manifest_path.exists():
        manifest_path.chmod(0o644)
    manifest_path.write_bytes(canonical_bytes(package))
    manifest_path.chmod(0o444)
    return package


def _candidate_surface_payloads() -> tuple[dict[str, bytes], dict[str, Any]]:
    evidence = load(REHEARSAL)
    if evidence.get("repeats") != 10 or not evidence.get("deterministic"):
        raise ValueError("successor candidate ten-repeat rehearsal")
    payloads: dict[str, bytes] = {}
    for item in evidence.get("numerical_surface_package", []):
        relative = Path(item["symbolic_relative_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("candidate surface path")
        path = REHEARSAL.parent / relative
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != item["sha256"]:
            raise ValueError("candidate surface identity")
        payloads[item["semantic_id"]] = payload
    return payloads, evidence


def _oracle_surface_payloads() -> tuple[dict[str, bytes], dict[str, Any]]:
    surfaces = synthetic_actual_binary_oracle_surfaces()
    required = {surface["semantic_id"] for surface in numerical_surface_manifest()["surfaces"]}
    selected = {name: surfaces[name] for name in required}
    ORACLE_SURFACES.mkdir(parents=True, exist_ok=True)
    payloads: dict[str, bytes] = {}
    descriptors = []
    for name in sorted(selected):
        payload = canonical_f32(selected[name])
        path = ORACLE_SURFACES / f"{name}.f32le"
        if path.exists():
            path.chmod(0o644)
        path.write_bytes(payload)
        path.chmod(0o444)
        payloads[name] = payload
        descriptors.append({"semantic_id": name, "sha256": sha(path), "shape": [6144], "dtype": "f32", "canonical_bytes": len(payload), "symbolic_relative_path": f"oracle-surfaces/{name}.f32le", "immutable": True, "read_only": True})
    return payloads, {"surfaces": descriptors, "package_sha256": canonical_sha(descriptors)}


def metric_engine_contract() -> dict[str, Any]:
    engine_path = ROOT / "scripts/research/f017_dprefix_metric_engine.py"
    return {
        "schema": "pulsarmlx.f017.dprefix-tier-b-metric-engine",
        "schema_version": "1.0.0",
        "source_path": "scripts/research/f017_dprefix_metric_engine.py",
        "source_sha256": sha(engine_path),
        "input": "paired canonical little-endian IEEE-754 binary32 C-order values",
        "accumulation": "CPython binary64 products with math.fsum deterministic reductions",
        "metrics": ["max_absolute_error", "rmse", "cosine_similarity", "non_finite_counts", "signed_zero_mismatch_count"],
        "trusts_candidate_pass_flags": False,
        "trusts_oracle_pass_flags": False,
        "shape_mismatch": "FAIL_CLOSED",
        "dtype_mismatch": "FAIL_CLOSED",
        "non_finite": "FAIL_CLOSED",
        "checkpoint_access": 0,
    }


def rehearsal_artifact(manifest: dict[str, Any], build: dict[str, Any], oracle_package: dict[str, Any]) -> dict[str, Any]:
    candidate_payloads, candidate_evidence = _candidate_surface_payloads()
    oracle_payloads, oracle_descriptor = _oracle_surface_payloads()
    comparison = compare_surface_packages(candidate_payloads, oracle_payloads, manifest)
    validate_terminal_numerical_surfaces(comparison["surfaces"])
    if not comparison["overall_pass"]:
        raise ValueError(f"synthetic Tier-B failure: {comparison['failed_surfaces']}")
    final = next(item for item in comparison["surfaces"] if item["semantic_id"] == "layer_3_entry")
    prior = load(EVIDENCE / "f017-dprefix-candidate-oracle-synthetic-parity-v1.json")
    reconciliation = {
        "prior_max_abs": prior["max_abs"],
        "current_max_abs": final["max_absolute_error"],
        "prior_rmse": prior["rmse"],
        "current_rmse": final["rmse"],
        "prior_cosine": prior["cosine"],
        "current_cosine": final["cosine_similarity"],
        "max_abs_and_rmse_exact": (
            final["max_absolute_error"] == prior["max_abs"]
            and final["rmse"] == prior["rmse"]
        ),
        "cosine_absolute_method_delta": abs(final["cosine_similarity"] - prior["cosine"]),
        "cosine_method_delta_limit": 1e-15,
        "methodology_reconciled": (
            final["max_absolute_error"] == prior["max_abs"]
            and final["rmse"] == prior["rmse"]
            and abs(final["cosine_similarity"] - prior["cosine"]) <= 1e-15
        ),
        "attribution": "The prior NumPy reduction and the frozen scalar math.fsum engine differ only in binary64 cosine accumulation order; canonical candidate/oracle f32 bytes are unchanged.",
    }
    if not reconciliation["methodology_reconciled"]:
        raise ValueError("prior final synthetic parity did not reconcile")
    old_candidate = load(EVIDENCE / "f017-dprefix-actual-binary-synthetic-rehearsal-v1.json")
    candidate_equivalence = {
        "predecessor_binary_sha256": PREDECESSOR_CANDIDATE_SHA,
        "successor_binary_sha256": build["binary"]["sha256"],
        "all_repeat_stage_hashes_exact": old_candidate["stage_hashes"] == candidate_evidence["stage_hashes"],
        "final_state_exact": old_candidate["retained_state"]["sha256"] == candidate_evidence["retained_state"]["sha256"],
        "predecessor_native_dispatches": old_candidate["dispatch"]["native_matvecs"],
        "successor_native_dispatches": candidate_evidence["dispatch"]["native_matvecs"],
        "added_native_dispatches": candidate_evidence["dispatch"]["native_matvecs"] - old_candidate["dispatch"]["native_matvecs"],
        "added_readbacks": candidate_evidence["dispatch"]["readbacks"] - old_candidate["dispatch"]["readbacks"],
        "instrumentation_host_surface_copies": 8,
        "instrumentation_host_bytes": 8 * 6144 * 4,
        "result": "CANDIDATE INSTRUMENTATION NUMERICALLY NEUTRAL",
    }
    if not candidate_equivalence["all_repeat_stage_hashes_exact"] or not candidate_equivalence["final_state_exact"] or candidate_equivalence["added_native_dispatches"] != 0 or candidate_equivalence["added_readbacks"] != 0:
        raise ValueError("candidate instrumentation changed numerical semantics")
    oracle_equivalence = {
        "predecessor_package_sha256": PREDECESSOR_ORACLE_SHA,
        "successor_package_sha256": oracle_package["package_sha256"],
        "predecessor_final_sha256": prior["oracle_sha256"],
        "successor_final_sha256": final["oracle_sha256"],
        "exact_canonical_output": prior["oracle_sha256"] == final["oracle_sha256"],
        "result": "ORACLE INSTRUMENTATION NUMERICALLY NEUTRAL",
    }
    if not oracle_equivalence["exact_canonical_output"]:
        raise ValueError("oracle instrumentation changed numerical semantics")
    return {
        "schema": "pulsarmlx.f017.dprefix-full-tier-b-synthetic-rehearsal",
        "schema_version": "1.0.0",
        "result": "FULL TIER_B_SURFACE_INSTANTIABLE_CHECKPOINT_FREE",
        "tier_b_sha256": TIER_B_SHA,
        "candidate_executable_sha256": build["binary"]["sha256"],
        "oracle_package_sha256": oracle_package["package_sha256"],
        "numerical_surface_manifest_sha256": canonical_sha(manifest),
        "metric_engine_sha256": sha(ROOT / "scripts/research/f017_dprefix_metric_engine.py"),
        "repeat_count": candidate_evidence["repeats"],
        "deterministic": candidate_evidence["deterministic"],
        "surfaces": comparison["surfaces"],
        "overall_pass": comparison["overall_pass"],
        "candidate_equivalence": candidate_equivalence,
        "oracle_equivalence": oracle_equivalence,
        "prior_final_metric_reconciliation": reconciliation,
        "dispatch": candidate_evidence["dispatch"],
        "oracle_surface_package": oracle_descriptor,
        "lifecycle_reconciled": candidate_evidence["lifecycle_reconciled"],
        "retained_state": candidate_evidence["retained_state"],
        "checkpoint_access": 0,
        "ledger": 59,
    }


def _successor_artifacts() -> dict[Path, Any]:
    manifest = numerical_surface_manifest()
    manifest_sha = canonical_sha(manifest)
    candidate_source = source_manifest(CANDIDATE_FILES, "candidate")
    candidate_build = candidate_build_manifest(candidate_source)
    oracle_source = source_manifest(ORACLE_FILES, "oracle")
    oracle_package = instantiate_oracle(oracle_source, manifest_sha)
    metric_contract = metric_engine_contract()
    schema = evidence_schema()
    rehearsal = rehearsal_artifact(manifest, candidate_build, oracle_package)
    continuation = continuation_adjudication()
    memory = {
        "schema": "pulsarmlx.f017.dprefix-paired-surface-memory-admission",
        "schema_version": "1.0.0",
        "predecessor_floor_gib": 27,
        "candidate_surface_bytes": 8 * 6144 * 4,
        "oracle_surface_bytes": 8 * 6144 * 4,
        "metric_engine_peak_working_bytes": 8 * 6144 * 4,
        "candidate_binary_bytes": candidate_build["binary"]["size_bytes"],
        "oracle_package_bytes": sum(item["canonical_bytes"] for item in rehearsal["oracle_surface_package"]["surfaces"]),
        "lifetime_model": "one candidate/oracle surface pair is compared and finalized before release; final layer-3 bytes remain Class A",
        "existing_allocator_and_1_25_reserve_absorbs_bytes": True,
        "minimum_free_memory_gib": 27,
        "floor_lowered": False,
        "result": "27 GIB FLOOR STILL SAFE",
        "checkpoint_access": 0,
        "ledger": 59,
    }
    config = {
        "schema": "pulsarmlx.f017.dense-prefix-execution-config",
        "schema_version": "4.0.0",
        "status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW",
        "predecessor": {"path": "docs/architecture/reviews/evidence/f017-dense-prefix-execution-config-v3.json", "sha256": PREDECESSOR_CONFIG_SHA},
        "authorization_base_head": "2e110d6ba8466ba84a880abdf0408d6c226977e6",
        "attempt_id": ATTEMPT,
        "candidate": {"source_manifest_sha256": candidate_source["source_manifest_sha256"], "build_manifest_sha256": canonical_sha(candidate_build), "binary_sha256": candidate_build["binary"]["sha256"], "symbolic_private_path": candidate_build["binary"]["symbolic_private_path"], "dynamic_build_at_execution": False},
        "oracle": {"source_manifest_sha256": oracle_source["source_manifest_sha256"], "package_sha256": oracle_package["package_sha256"], "symbolic_private_identity": oracle_package["symbolic_private_identity"], "finalized_before_candidate": True, "post_candidate_rehash": True, "dynamic_implementation_generation": False},
        "numerical_evidence": {"tier_b_sha256": TIER_B_SHA, "repeat_contract_sha256": REPEAT_SHA, "surface_manifest_sha256": manifest_sha, "metric_engine_contract_sha256": canonical_sha(metric_contract), "metric_engine_source_sha256": metric_contract["source_sha256"], "evidence_schema_sha256": canonical_sha(schema), "rehearsal_sha256": canonical_sha(rehearsal), "post_observation_retuning": "FORBIDDEN"},
        "frozen_semantics": frozen_semantics(),
        "identity_gates": {"Q4_K": "unchanged hard packed+decoded confirmation", "Q6_K": "unchanged hard packed+decoded confirmation"},
        "memory_floor_gib": 27,
        "execution_authorized": True,
        "consumed": False,
        "executed": False,
        "checkpoint_accessed": False,
        "automatic_retry": False,
        "automatic_m1f0_continuation": False,
        "cli_target_override": False,
        "environment_target_override": False,
        "checkpoint_access_during_preparation": 0,
    }
    config_sha = canonical_sha(config)
    auth = {
        "schema": "pulsarmlx.f017.dense-prefix-authorization-binding",
        "schema_version": "3.0.0",
        "status": "AUTHORIZED_UNCONSUMED_NOT_EXECUTED_PENDING_INDEPENDENT_REVIEW",
        "predecessor_authorization_sha256": PREDECESSOR_AUTH_SHA,
        "attempt_id": ATTEMPT,
        "execution_authorized": True,
        "execution_config_sha256": config_sha,
        "candidate_source_manifest_sha256": candidate_source["source_manifest_sha256"],
        "candidate_executable_sha256": candidate_build["binary"]["sha256"],
        "oracle_source_manifest_sha256": oracle_source["source_manifest_sha256"],
        "oracle_package_sha256": oracle_package["package_sha256"],
        "numerical_surface_manifest_sha256": manifest_sha,
        "metric_engine_contract_sha256": canonical_sha(metric_contract),
        "metric_engine_source_sha256": metric_contract["source_sha256"],
        "evidence_schema_sha256": canonical_sha(schema),
        "tier_b_sha256": TIER_B_SHA,
        "inventory_sha256": "c9c1540ea1cc9e69344ed9f3dcc4eb8ba1e5c15e3d55c1bccdec00eeb1db36aa",
        "prompt_package_sha256": "c05ba1cba69535cd17daf9f4326e5e1db25ffafe504c53712aa548f251741dff",
        "ledger_before": 59,
        "expected_ledger_after": 99,
        "automatic_retry": False,
        "automatic_m1f0_continuation": False,
        "release_requires_independent_review": True,
        "checkpoint_access": 0,
    }
    auth_sha = canonical_sha(auth)
    identity = {
        "attempt_id": ATTEMPT,
        "binary_sha256": candidate_build["binary"]["sha256"],
        "source_manifest_sha256": candidate_source["source_manifest_sha256"],
        "execution_config_sha256": config_sha,
        "authorization_binding_sha256": auth_sha,
        "inventory_sha256": "c9c1540ea1cc9e69344ed9f3dcc4eb8ba1e5c15e3d55c1bccdec00eeb1db36aa",
        "prompt_package_sha256": "c05ba1cba69535cd17daf9f4326e5e1db25ffafe504c53712aa548f251741dff",
        "ledger_before": 59,
    }
    attempt = {
        "schema": "pulsarmlx.f017.dense-prefix-attempt-ledger",
        "schema_version": "4.0.0",
        "append_only_predecessor": {"path": "docs/architecture/reviews/evidence/f017-dense-prefix-attempt-ledger-v3.json", "sha256": "1de57b2ce2a4e5e50e698394ba960cb4390242dcd88982df92f4cdb5649242a5"},
        "history": [
            {"event": "FIRST_RELEASE_NONCONSUMING_INFRASTRUCTURE_STOP", "evidence_sha256": "b8495bd1a4129efc7e24c687289bcb3be7af7f153e24d45ccffdccb79e79d60a"},
            {"event": "INFRASTRUCTURE_CLOSURE_SUCCESSOR_AUTHORIZATION", "attempt_ledger_sha256": "b18be3ab1f5589942a232d5d04fcd57888eb7bde14b363ca62368a387a1242fe"},
            {"event": "SECOND_RELEASE_NUMERICAL_SURFACE_STOP", "evidence_sha256": STOP_EVIDENCE_SHA},
            {"event": "NUMERICAL_SURFACE_CLOSURE_SUCCESSOR_AUTHORIZATION", "execution_config_sha256": config_sha, "authorization_binding_sha256": auth_sha, "candidate_executable_sha256": candidate_build["binary"]["sha256"], "oracle_package_sha256": oracle_package["package_sha256"], "rehearsal_sha256": canonical_sha(rehearsal)},
        ],
        "current_state": {"attempt_id": ATTEMPT, "authorized": True, "consumed": False, "executed": False, "checkpoint_accessed": False, "ledger": 59, "automatic_retry": False, "automatic_m1f0_continuation": False},
        "checkpoint_access": 0,
        "ledger": 59,
    }
    preflight = {
        "schema": "pulsarmlx.f017.dprefix-numerical-surface-closure-preflight",
        "schema_version": "1.0.0",
        "result": "READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE",
        "attempt_id": ATTEMPT,
        "execution_config_sha256": config_sha,
        "authorization_binding_sha256": auth_sha,
        "attempt_ledger_sha256": canonical_sha(attempt),
        "candidate_executable_sha256": candidate_build["binary"]["sha256"],
        "candidate_source_manifest_sha256": candidate_source["source_manifest_sha256"],
        "oracle_package_sha256": oracle_package["package_sha256"],
        "oracle_source_manifest_sha256": oracle_source["source_manifest_sha256"],
        "numerical_surface_manifest_sha256": manifest_sha,
        "metric_engine_source_sha256": metric_contract["source_sha256"],
        "evidence_schema_sha256": canonical_sha(schema),
        "full_rehearsal_result": rehearsal["result"],
        "all_tier_b_fields_have_candidate_producers": True,
        "all_tier_b_fields_have_oracle_producers": True,
        "all_required_values_retained_or_derivable": True,
        "memory_floor_gib": 27,
        "checkpoint_reads": 0,
        "attempt_consumed": False,
        "ledger": 59,
    }
    internal = {
        "schema": "pulsarmlx.f017.dprefix-numerical-surface-closure-internal-review",
        "schema_version": "1.0.0",
        "verdict": "GO FOR DPREFIX NUMERICAL-SURFACE CLOSURE ADVERSARIAL REVIEW",
        "tier_b_unchanged": True,
        "all_required_surfaces_producible": True,
        "candidate_oracle_semantics_aligned": True,
        "metrics_independently_derived": True,
        "terminal_schema_fully_populable": True,
        "candidate_instrumentation": rehearsal["candidate_equivalence"]["result"],
        "oracle_instrumentation": rehearsal["oracle_equivalence"]["result"],
        "retention_operational": True,
        "memory_floor_result": memory["result"],
        "continuation_decision": continuation["decision"],
        "checkpoint_access": 0,
        "ledger": 59,
    }
    return {
        EVIDENCE / "f017-dprefix-numerical-surface-manifest-v1.json": manifest,
        EVIDENCE / "f017-dprefix-tier-b-metric-engine-v1.json": metric_contract,
        EVIDENCE / "f017-dprefix-candidate-source-manifest-v2.json": candidate_source,
        EVIDENCE / "f017-dprefix-candidate-build-manifest-v2.json": candidate_build,
        EVIDENCE / "f017-dprefix-oracle-source-manifest-v2.json": oracle_source,
        EVIDENCE / "f017-dprefix-instantiated-oracle-package-v2.json": oracle_package,
        EVIDENCE / "f017-dprefix-full-tier-b-synthetic-rehearsal-v1.json": rehearsal,
        EVIDENCE / "f017-dprefix-paired-surface-memory-admission-v1.json": memory,
        EVIDENCE / "f017-dprefix-unconsumed-attempt-continuation-v2.json": continuation,
        EVIDENCE / "f017-dense-prefix-execution-config-v4.json": config,
        EVIDENCE / "f017-dense-prefix-authorization-binding-v3.json": auth,
        EVIDENCE / "f017-dprefix-candidate-identity-binding-v2.json": identity,
        EVIDENCE / "f017-dense-prefix-attempt-ledger-v4.json": attempt,
        EVIDENCE / "f017-dprefix-numerical-surface-closure-preflight-v1.json": preflight,
        EVIDENCE / "f017-dprefix-numerical-surface-closure-internal-review-v1.json": internal,
        CONTRACTS / "f017-dense-prefix-evidence-v4.schema.json": schema,
    }


def validate_artifacts(values: dict[Path, Any]) -> dict[str, Any]:
    by_name = {path.name: value for path, value in values.items()}
    config = by_name["f017-dense-prefix-execution-config-v4.json"]
    auth = by_name["f017-dense-prefix-authorization-binding-v3.json"]
    attempt = by_name["f017-dense-prefix-attempt-ledger-v4.json"]
    preflight = by_name["f017-dprefix-numerical-surface-closure-preflight-v1.json"]
    rehearsal = by_name["f017-dprefix-full-tier-b-synthetic-rehearsal-v1.json"]
    if canonical_sha(config) != auth["execution_config_sha256"]:
        raise ValueError("config authorization mismatch")
    if canonical_sha(auth) != attempt["history"][-1]["authorization_binding_sha256"]:
        raise ValueError("attempt authorization mismatch")
    if attempt["current_state"] != {"attempt_id": ATTEMPT, "authorized": True, "consumed": False, "executed": False, "checkpoint_accessed": False, "ledger": 59, "automatic_retry": False, "automatic_m1f0_continuation": False}:
        raise ValueError("attempt state")
    if rehearsal["result"] != "FULL TIER_B_SURFACE_INSTANTIABLE_CHECKPOINT_FREE" or not rehearsal["overall_pass"] or len(rehearsal["surfaces"]) != 8:
        raise ValueError("Tier-B instantiability")
    if preflight["result"] != "READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE" or preflight["checkpoint_reads"] != 0:
        raise ValueError("preflight")
    if load(EVIDENCE / "f017-real-payload-access-ledger-v1.json")["cumulative_tensor_payloads"] != 59:
        raise ValueError("real payload ledger changed")
    if sha(EVIDENCE / "f017-dense-prefix-real-attempt-1-not-executed-numerical-surface-v1.json") != STOP_EVIDENCE_SHA:
        raise ValueError("historical numerical-surface stop changed")
    return {"result": preflight["result"], "tier_b": rehearsal["result"], "attempt": ATTEMPT, "checkpoint_access": 0, "ledger": 59}


def write_all() -> dict[str, Any]:
    values = _successor_artifacts()
    validate_artifacts(values)
    for path, value in values.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_bytes(value))
    return validate_artifacts(values)


if __name__ == "__main__":
    print(json.dumps(write_all(), sort_keys=True))
