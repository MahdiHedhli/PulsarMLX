#!/usr/bin/env python3
"""Checkpoint-free validator and synthetic harness for F017 v2 recovery.

The real recovery entry point is intentionally not enabled in this preparation
phase.  This module validates the immutable future config, constructs the full
v2 retention surface from supplied antecedents, and exercises that surface with
synthetic payloads.  It never opens a checkpoint and never imports MLX.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import platform
import shutil
import struct
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np


SCHEMA = "pulsarmlx.f017.v2-antecedent-recovery-config"
READY = "READY_TO_EXECUTE_V2_ANTECEDENT_RECOVERY"
EXPECTED_NAMES = [
    "blk.3.attn_norm.weight",
    "blk.3.attn_q_a.weight",
    "blk.3.attn_q_a_norm.weight",
    "blk.3.attn_q_b.weight",
    "blk.3.attn_kv_a_mqa.weight",
    "blk.3.attn_kv_a_norm.weight",
    "blk.3.attn_k_b.weight",
    "blk.3.attn_v_b.weight",
    "blk.3.attn_output.weight",
    "blk.3.ffn_norm.weight",
    "blk.3.ffn_gate_inp.weight",
    "blk.3.exp_probs_b.bias",
]


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def safe_file(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("path escape")
    resolved = (root / candidate).resolve(strict=True)
    canonical_root = root.resolve(strict=True)
    if canonical_root not in (resolved, *resolved.parents):
        raise ValueError("symlink escape")
    return resolved


def load_math(root: Path):
    path = root / "scripts/research/f017_route_stability_v2.py"
    spec = importlib.util.spec_from_file_location("f017_v2_recovery_math", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_base_recovery(root: Path):
    path = root / "scripts/research/recover_f017_m1f0_analytics.py"
    spec = importlib.util.spec_from_file_location("f017_v2_base_recovery", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_document(root: Path, config: dict[str, Any], *, verify_git: bool = True) -> None:
    required = {
        "schema", "schema_version", "status", "source_identities", "accepted_bindings",
        "contracts", "input_state", "checkpoint_bindings", "tensor_allowlist",
        "access_budget", "expected_identities", "retention", "ledger_transition",
        "semantics", "output_schemas",
    }
    if set(config) != required:
        raise ValueError("recovery config fields")
    if config["schema"] != SCHEMA or config["schema_version"] != "1.0.0":
        raise ValueError("recovery config schema")
    if config["status"] != "NOT_AUTHORIZED_NOT_EXECUTED":
        raise ValueError("recovery authorization state")
    source = config["source_identities"]
    if source["authorization_head"] is not None or source["authorization_issued"]:
        raise ValueError("unexpected execution authorization")
    if verify_git:
        tooling = source["tooling_commit_sha"]
        tree = subprocess.check_output(
            ["git", "rev-parse", f"{tooling}^{{tree}}"], cwd=root, text=True
        ).strip()
        if tree != source["tooling_tree_oid"]:
            raise ValueError("tooling tree identity")
        subprocess.check_call(
            ["git", "merge-base", "--is-ancestor", tooling, "HEAD"], cwd=root,
            stdout=subprocess.DEVNULL,
        )
        if platform.python_version() != source["python"] or np.__version__ != source["numpy"]:
            raise ValueError("Python/NumPy identity")
    for collection in ("accepted_bindings", "contracts"):
        for binding in config[collection].values():
            target = safe_file(root, binding["symbolic_path"])
            if file_sha256(target) != binding["sha256"]:
                raise ValueError(f"stale binding: {binding['symbolic_path']}")
    accepted_config = load_json(safe_file(root, config["accepted_bindings"]["accepted_execution_config"]["symbolic_path"]))
    accepted_attempt = load_json(safe_file(root, config["accepted_bindings"]["attempt_2_evidence"]["symbolic_path"]))
    accepted_packed = {item["symbolic_name"]: item["packed_sha256"] for item in accepted_attempt["tensor_payloads"]}
    accepted_decoded = {item["symbolic_name"]: item["decoded_sha256"] for item in accepted_attempt["decoded_tensors"]}
    expected_allowlist = []
    for accepted in accepted_config["tensor_allowlist"]:
        item = dict(accepted)
        item["packed_sha256"] = accepted_packed[item["name"]]
        item["decoded_sha256"] = accepted_decoded[item["name"]]
        expected_allowlist.append(item)
    if config["tensor_allowlist"] != expected_allowlist:
        raise ValueError("accepted tensor identities changed")
    if config["input_state"] != accepted_config["input_state"] or config["checkpoint_bindings"] != accepted_config["checkpoint_bindings"]:
        raise ValueError("accepted boundary identity changed")
    names = [item["name"] for item in config["tensor_allowlist"]]
    if names != EXPECTED_NAMES or len(set(names)) != 12:
        raise ValueError("accepted 12-tensor allowlist")
    if any("_exps" in name or "_shexp" in name for name in names):
        raise ValueError("UNAUTHORIZED_ACCESS")
    for item in config["tensor_allowlist"]:
        if item["allowed_read_count"] != 1 or len(item["packed_sha256"]) != 64 or len(item["decoded_sha256"]) != 64:
            raise ValueError("tensor identity completeness")
    if config["access_budget"] != {
        "shard_opens": 1,
        "positional_reads": 12,
        "tensor_payloads": 12,
        "compressed_bytes": 139217920,
        "decoded_bytes": 666430464,
        "expert_payloads": 0,
        "expert_computation": 0,
        "mlx_candidate_dispatches": 0,
        "m1_f_execution": 0,
    }:
        raise ValueError("recovery access budget")
    if config["ledger_transition"] != {
        "before": 45, "successful_recovery_delta": 12, "after": 57,
        "increment_during_preparation": False,
    }:
        raise ValueError("ledger transition")
    semantics = config["semantics"]
    expected_semantics = {
        "purpose": "analytical_antecedent_recovery_for_retrospective_v2",
        "new_route_discovery": False,
        "route_selection_authority": "accepted_m1f0_attempt_2",
        "route_attempt_consumed": False,
        "accepted_route_reclassification": False,
        "historical_v1_reclassification": False,
        "q6_k_qualification": False,
        "m1_f_execution": False,
    }
    if semantics != expected_semantics:
        raise ValueError("no-new-route semantics")
    retention = config["retention"]
    if retention["manifest_sha256"] != config["contracts"]["retention_manifest"]["sha256"]:
        raise ValueError("retention manifest identity")
    if config["contracts"]["route_stability_v2"]["sha256"] != "36adbdcffeeb361638ec80258b912711b17a671276d68cf0129826e1ae042ac7":
        raise ValueError("final v2 contract identity")
    if retention["selected_unselected_pair_count"] != 1984 or retention["adjacent_selected_pair_count"] != 7:
        raise ValueError("retention pair surface")
    if retention["pre_sigmoid_policy"] != "retain_direct_canonical_little_endian_f64_logits":
        raise ValueError("pre-sigmoid retention")
    expected = config["expected_identities"]
    if expected["top8_ids"] != [166, 78, 26, 186, 163, 199, 233, 177]:
        raise ValueError("accepted route identity")
    if expected["router_scores_sha256"] != "3b4ff6cac287f53004c7cc6ceedb13f2403a6ce4426e30155005158e0e004dc4":
        raise ValueError("accepted score identity")
    if expected["ranking_sha256"] != "6a878c1db20997b16cff8efdb8659543c07974dcddd718957243c889d78a2ede":
        raise ValueError("accepted ranking identity")
    ledger = load_json(safe_file(root, config["accepted_bindings"]["real_payload_ledger"]["symbolic_path"]))
    if ledger["cumulative_tensor_payloads"] != 45:
        raise ValueError("current access ledger")
    route = load_json(safe_file(root, config["accepted_bindings"]["route"]["symbolic_path"]))
    analytical = load_json(safe_file(root, config["accepted_bindings"]["accepted_analytical_recovery"]["symbolic_path"]))
    reproduced = analytical["reproduced_identities"]
    authoritative = {
        "input_fixture_sha256": route["input_fixture_sha256"],
        "input_package_sha256": route["input_package_sha256"],
        "hidden_sha256": accepted_config["input_state"]["hidden_sha256"],
        "position_sha256": accepted_config["input_state"]["component_sha256"]["query_position"],
        "mla_cache_sha256": accepted_config["input_state"]["component_sha256"]["mla_cache"],
        "dsa_state_sha256": accepted_config["input_state"]["component_sha256"]["dsa"],
        "mask_sha256": accepted_config["input_state"]["component_sha256"]["mask"],
        "attention_output_sha256": reproduced["attention_output_sha256"],
        "attention_residual_sha256": reproduced["attention_residual_sha256"],
        "router_normalized_input_sha256": reproduced["router_normalized_input_sha256"],
        "router_logits_sha256": accepted_attempt["oracle"]["stage_hashes"]["router_logits"],
        "router_probabilities_sha256": analytical["canonical_analytics"]["artifacts"]["router_probabilities"]["sha256"],
        "router_scores_sha256": reproduced["router_scores_sha256"],
        "ranking_sha256": reproduced["ranking_sha256"],
        "top8_ids": reproduced["top8_ids"],
        "top8_ids_sha256": reproduced["top8_ids_sha256"],
        "routing_weights_sha256": reproduced["routing_weights_sha256"],
    }
    if expected != authoritative:
        raise ValueError("accepted reproduction gates changed")


def preflight(root: Path, config_path: Path, expected_sha256: str) -> dict[str, Any]:
    raw = config_path.read_bytes()
    if sha256(raw) != expected_sha256:
        raise ValueError("config mutation after preflight")
    config = json.loads(raw, object_pairs_hook=reject_duplicates)
    validate_document(root, config)
    return {
        "result": READY,
        "checkpoint_reads": 0,
        "evidence_target_consumed": False,
        "route_attempt_consumed": False,
        "oracle_package_created": False,
        "mlx_contexts": 0,
        "expert_access": 0,
    }


def validate_execution_authorization(
    config: dict[str, Any], config_sha256: str, authorization_path: Path, authorization_sha256: str,
) -> None:
    raw = authorization_path.read_bytes()
    if sha256(raw) != authorization_sha256:
        raise ValueError("recovery authorization identity")
    authorization = json.loads(raw, object_pairs_hook=reject_duplicates)
    expected = {
        "schema": "pulsarmlx.f017.v2-antecedent-recovery-authorization",
        "schema_version": "1.0.0",
        "status": "AUTHORIZED_FOR_EXACTLY_ONE_V2_ANTECEDENT_RECOVERY_NOT_EXECUTED",
        "execution_config_sha256": config_sha256,
        "tooling_commit_sha": config["source_identities"]["tooling_commit_sha"],
        "tooling_tree_oid": config["source_identities"]["tooling_tree_oid"],
        "accepted_route_sha256": config["accepted_bindings"]["route"]["sha256"],
        "retention_manifest_sha256": config["retention"]["manifest_sha256"],
        "payload_budget": config["access_budget"],
        "new_route_discovery": False,
        "route_attempt_consumed": False,
        "m1_f_authorized": False,
        "q6_k_qualification_authorized": False,
    }
    if authorization != expected:
        raise ValueError("recovery authorization binding")


def _artifact_descriptor(
    artifact_id: str, raw: bytes, dtype: str, shape: Sequence[int], ordinal: int,
    source_tensor_identities: Sequence[str],
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "path_kind": "private_package_relative",
        "symbolic_name": f"antecedents/{artifact_id}.bin",
        "sha256": sha256(raw),
        "dtype": dtype,
        "shape": list(shape),
        "element_count": math.prod(shape),
        "canonical_serialization": dtype,
        "provenance": "independent_python_numpy_accepted_boundary_recovery",
        "source_tensor_identities": list(source_tensor_identities),
        "creation_ordinal": ordinal,
        "immutable": True,
        "read_only": True,
    }


def pairwise_surface(
    math_impl: Any,
    logits: Sequence[float],
    probabilities: Sequence[float],
    bias: Sequence[float],
    scores: Sequence[float],
    ranking: Sequence[int],
    router_rows: np.ndarray,
    lambda_bound: float,
    residual_bounds: Sequence[float],
    reduction_bounds: Sequence[float],
    import_bounds: Sequence[float],
) -> dict[str, Any]:
    if not all(len(values) == 256 for values in (logits, probabilities, bias, scores, ranking, reduction_bounds, import_bounds)):
        raise ValueError("router cardinality")
    if router_rows.shape != (256, len(residual_bounds)):
        raise ValueError("router row shape")
    selected = list(ranking[:8])
    unselected = list(ranking[8:])
    pairs: list[dict[str, Any]] = []
    bounds: dict[tuple[int, int], float] = {}
    common = tuple(float(item) for item in residual_bounds)
    for relation, iterable in (
        ("membership", ((i, j) for i in selected for j in unselected)),
        ("ordered_selected", zip(selected, selected[1:])),
    ):
        for i, j in iterable:
            item = math_impl.PairwiseInputs(
                logit_i=float(logits[i]), logit_j=float(logits[j]),
                row_i=tuple(float(x) for x in router_rows[i]),
                row_j=tuple(float(x) for x in router_rows[j]),
                lambda_bound=float(lambda_bound), residual_bounds=common,
                reduction_i=float(reduction_bounds[i]), reduction_j=float(reduction_bounds[j]),
                import_i=float(import_bounds[i]), import_j=float(import_bounds[j]),
                bias_i=float(bias[i]), bias_j=float(bias[j]),
            )
            result = math_impl.pairwise_bound_primary(item)
            bound = float(result["B_pair"])
            margin = float(scores[i] - scores[j])
            factor = margin / bound if bound > 0.0 else math.inf
            pairs.append({"relation": relation, "selected": i, "challenger": j, "margin": margin, "B_pair": bound, "safety_factor": factor})
            bounds[(i, j)] = bound
    stable, worst_pair, minimum_factor, relation = math_impl.ordered_topk_stable(scores, selected, bounds)
    membership = [item for item in pairs if item["relation"] == "membership"]
    adjacent = [item for item in pairs if item["relation"] == "ordered_selected"]
    return {
        "selected_ids_ordered": selected,
        "unselected_ids": unselected,
        "selected_unselected_pair_bounds": membership,
        "adjacent_selected_pair_bounds": adjacent,
        "membership_pair_count": len(membership),
        "adjacent_selected_pair_count": len(adjacent),
        "minimum_mathematical_safety_factor": minimum_factor,
        "minimum_engineering_safety_factor": minimum_factor / 2.0,
        "global_worst_pair": list(worst_pair) if worst_pair is not None else None,
        "worst_relation": relation,
        "mathematical_classification": "MATHEMATICALLY_STABLE" if stable else "NOT_MATHEMATICALLY_STABLE",
        "engineering_classification": "ENGINEERING_HEADROOM" if stable and minimum_factor >= 2.0 else "NO_ENGINEERING_HEADROOM",
    }


def validate_synthetic_result(result: dict[str, Any]) -> None:
    if result.get("synthetic_payload_count") != 12 or result.get("checkpoint_access") != 0:
        raise ValueError("synthetic access semantics")
    if result.get("route_attempt_consumed") or result.get("new_route_discovery"):
        raise ValueError("synthetic route semantics")
    if result.get("payload_hashes_before") != result.get("payload_hashes_after"):
        raise ValueError("synthetic payload mutation")
    if result.get("private_hashes_before") != result.get("private_hashes_after"):
        raise ValueError("private package mutation")
    surface = result.get("pairwise_surface", {})
    if surface.get("membership_pair_count") != 1984 or len(surface.get("selected_unselected_pair_bounds", [])) != 1984:
        raise ValueError("missing pairwise bound")
    if surface.get("adjacent_selected_pair_count") != 7 or len(surface.get("adjacent_selected_pair_bounds", [])) != 7:
        raise ValueError("missing ordered-selected bound")
    required_private = {
        "attention_residual", "router_normalized_input", "router_matrix", "ffn_norm_weight",
        "rmsnorm_decomposition_inputs", "non_radial_component_bounds",
        "router_reduction_bounds", "router_import_materialization_bounds",
    }
    descriptors = result.get("private_antecedents", {})
    payload_hex = result.get("synthetic_private_payloads_hex", {})
    if set(descriptors) != required_private or set(payload_hex) != required_private:
        raise ValueError("missing private antecedent")
    for name in required_private:
        descriptor = descriptors[name]
        raw = bytes.fromhex(payload_hex[name])
        if descriptor["sha256"] != sha256(raw):
            raise ValueError("corrupted private-artifact hash")
        if descriptor["path_kind"] != "private_package_relative" or not descriptor["immutable"] or not descriptor["read_only"]:
            raise ValueError("private artifact mutability")


def rmsnorm_decomposition(base: Any, values: np.ndarray, weights: np.ndarray, input_error: np.ndarray) -> dict[str, Any]:
    """Rigorous delta_y=lambda*y+r antecedents for the router RMSNorm."""
    absolute = np.abs(np.asarray(values, dtype=np.float64))
    error = np.asarray(input_error, dtype=np.float64)
    upper = absolute + error
    n = values.size
    same_input = 2.0 * base.gamma(2 * n) * float(np.sum(upper * upper, dtype=np.float64)) + 4.0 * n * base.ETA32
    propagated = float(np.sum(2.0 * absolute * error + error * error, dtype=np.float64))
    sum_error = math.nextafter(same_input + (1.0 + base.gamma(2 * n)) * propagated, math.inf)
    q, inverse = base._strict_rms_state(values)
    q_error = math.nextafter((sum_error / n) * (1.0 + base.U32) + 4.0 * base.U32 * abs(q) + 4.0 * base.ETA32, math.inf)
    q_lower = q - q_error
    if not math.isfinite(q_lower) or q_lower <= 0.0 or inverse == 0.0:
        raise ValueError("RMSNorm decomposition interval")
    inverse_error = math.nextafter(
        0.5 * q_lower ** -1.5 * q_error + 4.0 * base.U32 * (abs(inverse) + q_lower ** -0.5) + 4.0 * base.ETA32,
        math.inf,
    )
    lambda_bound = math.nextafter(inverse_error / abs(inverse), math.inf)
    weight = np.abs(np.asarray(weights, dtype=np.float64))
    non_radial = weight * error * (abs(inverse) + inverse_error)
    magnitude = weight * upper * (abs(inverse) + inverse_error)
    non_radial = np.nextafter(non_radial + 4.0 * base.U32 * magnitude + 4.0 * base.ETA32, math.inf)
    return {
        "oracle_rms_squared_plus_epsilon": q,
        "oracle_inverse_rms": inverse,
        "inverse_rms_error_bound": inverse_error,
        "lambda_bound": lambda_bound,
        "non_radial_component_bounds": non_radial,
    }


def router_row_error_terms(base: Any, rows: np.ndarray, normalized: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rows64 = np.asarray(rows, dtype=np.float64)
    normalized64 = np.asarray(normalized, dtype=np.float64)
    l1 = np.sum(np.abs(rows64) * np.abs(normalized64)[None, :], axis=1, dtype=np.float64)
    n = normalized64.size
    reduction = np.nextafter(2.0 * base.gamma(2 * n) * l1 + 4.0 * n * base.ETA32, math.inf)
    materialization = np.nextafter(4.0 * base.U32 * l1 + 4.0 * n * base.ETA32, math.inf)
    return reduction, materialization


def _write_immutable_package(output: Path, public_result: dict[str, Any], payloads: dict[str, bytes]) -> None:
    if output.exists():
        raise ValueError("refusing to overwrite v2 antecedent package")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        for name, raw in payloads.items():
            target = temporary / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            target.chmod(0o444)
        (temporary / "recovery-result.json").write_bytes(canonical_json(public_result))
        (temporary / "recovery-result.json").chmod(0o444)
        os.replace(temporary, output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def execute_authorized_recovery(
    root: Path,
    config_path: Path,
    config_sha256: str,
    authorization_path: Path,
    authorization_sha256: str,
    private_package_root: Path,
    output: Path,
    start_marker: Path,
) -> dict[str, Any]:
    """Future one-shot path. Never called by preparation or CI."""
    ready = preflight(root, config_path, config_sha256)
    if ready["result"] != READY:
        raise ValueError("recovery preflight")
    config = load_json(config_path)
    validate_execution_authorization(config, config_sha256, authorization_path, authorization_sha256)
    base = load_base_recovery(root)
    oracle = base._load(root, "scripts/research/prepare_f017_m1f0_real_reference.py", "f017_v2_accepted_oracle")
    manifest = load_json(safe_file(private_package_root, "checkpoint-manifest.json"))
    if manifest.get("checkpoint_set_sha256") != config["checkpoint_bindings"]["checkpoint_set_sha256"]:
        raise ValueError("checkpoint package identity")
    shard = manifest.get("shard_2", {})
    if set(shard) != {"path_kind", "path", "size_bytes", "sha256"} or shard["path_kind"] != "package_relative":
        raise ValueError("checkpoint shard manifest")
    shard_path = safe_file(private_package_root, shard["path"])
    fixture = load_json(safe_file(root, config["input_state"]["symbolic_path"]))
    hidden = np.frombuffer(bytes.fromhex(fixture["state"]["hidden"]["bytes_hex"]), dtype="<f4").copy()
    marker = canonical_json({
        "schema": "pulsarmlx.f017.v2-antecedent-recovery-start",
        "schema_version": "1.0.0",
        "state": "ANALYTICAL_RECOVERY_STARTED",
        "execution_config_sha256": config_sha256,
        "route_attempt_consumed": False,
        "recorded_unix_ns": time.time_ns(),
    })
    descriptor = os.open(start_marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        os.write(descriptor, marker)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    tensors: dict[str, np.ndarray] = {}
    packed: dict[str, str] = {}
    decoded: dict[str, str] = {}
    with shard_path.open("rb", buffering=0) as source:
        for item in config["tensor_allowlist"]:
            source.seek(item["offset"])
            raw = source.read(item["packed_length"])
            if len(raw) != item["packed_length"] or sha256(raw) != item["packed_sha256"]:
                raise ValueError("accepted packed tensor mismatch")
            tensor = oracle.decode_tensor(raw, item["quantization"], item["logical_shape"])
            decoded_raw = oracle.f32_bytes(tensor)
            if sha256(decoded_raw) != item["decoded_sha256"]:
                raise ValueError("accepted decoded tensor mismatch")
            packed[item["name"]] = sha256(raw)
            decoded[item["name"]] = sha256(decoded_raw)
            tensors[item["name"]] = tensor
    result, captured = base._instrumented_oracle(oracle, tensors, hidden)
    reproduced = {
        "attention_output_sha256": result["stage_hashes"]["attention_output"],
        "attention_residual_sha256": result["stage_hashes"]["attention_residual"],
        "router_normalized_input_sha256": result["stage_hashes"]["router_normalized"],
        "router_logits_sha256": result["stage_hashes"]["router_logits"],
        "router_probabilities_sha256": sha256(np.asarray(captured["probabilities"], dtype="<f8").tobytes()),
        "router_scores_sha256": result["router_scores_sha256"],
        "ranking_sha256": result["ranking_sha256"],
        "top8_ids": result["top8_ids"],
        "top8_ids_sha256": result["top8_ids_sha256"],
        "routing_weights_sha256": result["routing_weights_sha256"],
    }
    for key, value in reproduced.items():
        if config["expected_identities"][key] != value:
            raise ValueError("BLOCKED — M1-F0 RECOVERY IDENTITY MISMATCH")
    v1_bounds = base.route_score_bounds(tensors, captured, hidden)
    decomposition = rmsnorm_decomposition(
        base, captured["attention_residual"], tensors["blk.3.ffn_norm.weight"],
        v1_bounds["attention_residual_abs_error"],
    )
    router_rows = tensors["blk.3.ffn_gate_inp.weight"]
    reduction, imported = router_row_error_terms(base, router_rows, captured["router_normalized"])
    math_impl = load_math(root)
    surface = pairwise_surface(
        math_impl, [float(x) for x in captured["router_logits"]], captured["probabilities"],
        [float(x) for x in captured["bias"]], captured["scores"], captured["ranking"],
        router_rows, decomposition["lambda_bound"], decomposition["non_radial_component_bounds"],
        reduction, imported,
    )
    canonical_payloads = {
        "antecedents/attention_residual.bin": np.asarray(captured["attention_residual"], dtype="<f4").tobytes(),
        "antecedents/router_normalized_input.bin": np.asarray(captured["router_normalized"], dtype="<f4").tobytes(),
        "antecedents/router_matrix.bin": np.asarray(router_rows, dtype="<f4").tobytes(),
        "antecedents/ffn_norm_weight.bin": np.asarray(tensors["blk.3.ffn_norm.weight"], dtype="<f4").tobytes(),
        "antecedents/rmsnorm_decomposition_inputs.bin": canonical_json({key: value for key, value in decomposition.items() if key != "non_radial_component_bounds"}),
        "antecedents/non_radial_component_bounds.bin": np.asarray(decomposition["non_radial_component_bounds"], dtype="<f8").tobytes(),
        "antecedents/router_reduction_bounds.bin": np.asarray(reduction, dtype="<f8").tobytes(),
        "antecedents/router_import_materialization_bounds.bin": np.asarray(imported, dtype="<f8").tobytes(),
    }
    public_result = {
        "schema": "pulsarmlx.f017.v2-antecedent-recovery-result",
        "schema_version": "1.0.0",
        "identity_reproduction": {"accepted_computation_reproduced_exactly": True, "all_gates": reproduced, "failure": None},
        "antecedent_retention": {
            "manifest_sha256": config["retention"]["manifest_sha256"], "complete": True,
            "membership_pair_count": 1984, "adjacent_selected_pair_count": 7,
            "private_artifacts_immutable": True,
            "private_artifacts": {name: sha256(raw) for name, raw in canonical_payloads.items()},
            "router_logits": [float(x) for x in captured["router_logits"]],
            "router_probabilities": captured["probabilities"], "router_bias": [float(x) for x in captured["bias"]],
            "router_scores": captured["scores"], "ranking": captured["ranking"], "pairwise_surface": surface,
        },
        "retrospective_v2": {
            "mathematical_status": surface["mathematical_classification"],
            "engineering_status": surface["engineering_classification"],
            "minimum_mathematical_safety_factor": surface["minimum_mathematical_safety_factor"],
            "minimum_engineering_safety_factor": surface["minimum_engineering_safety_factor"],
            "route_set_stable": surface["mathematical_classification"] == "MATHEMATICALLY_STABLE",
            "route_order_stable": surface["mathematical_classification"] == "MATHEMATICALLY_STABLE",
        },
        "historical_status": {"historical_v1_status_unchanged": True, "accepted_route_reclassified": False},
        "access": config["access_budget"],
        "scope": config["semantics"],
    }
    _write_immutable_package(output, public_result, canonical_payloads)
    return public_result


def synthetic_recovery(root: Path) -> dict[str, Any]:
    """Exercise 12-payload identity gates and the complete retention surface."""
    math_impl = load_math(root)
    rng = np.random.Generator(np.random.PCG64(170_186_001))
    payloads = [rng.bytes(128 + ordinal) for ordinal in range(12)]
    payload_before = [sha256(raw) for raw in payloads]
    width = 8
    router_rows = rng.normal(0.0, 0.125, size=(256, width)).astype(np.float64)
    normalized = rng.normal(0.0, 1.0, size=width).astype(np.float64)
    logits_array = router_rows @ normalized
    bias_array = np.linspace(2.0, -2.0, 256, dtype=np.float64)
    probabilities_array = np.asarray([math_impl.sigmoid(float(item)) for item in logits_array], dtype=np.float64)
    scores_array = probabilities_array + bias_array
    ranking = sorted(range(256), key=lambda index: (-float(scores_array[index]), index))
    residual_bounds = np.full(width, 1e-8, dtype=np.float64)
    reduction = np.full(256, 1e-9, dtype=np.float64)
    imported = np.full(256, 1e-10, dtype=np.float64)
    surface = pairwise_surface(
        math_impl, logits_array, probabilities_array, bias_array, scores_array,
        ranking, router_rows, 1e-9, residual_bounds, reduction, imported,
    )
    private_raw = {
        "attention_residual": rng.normal(size=width).astype("<f4").tobytes(),
        "router_normalized_input": normalized.astype("<f4").tobytes(),
        "router_matrix": router_rows.astype("<f4").tobytes(),
        "ffn_norm_weight": np.ones(width, dtype="<f4").tobytes(),
        "rmsnorm_decomposition_inputs": canonical_json({"oracle_rms_squared_plus_epsilon": 1.0, "oracle_inverse_rms": 1.0, "inverse_rms_error_bound": 1e-9, "lambda_bound": 1e-9}),
        "non_radial_component_bounds": residual_bounds.astype("<f8").tobytes(),
        "router_reduction_bounds": reduction.astype("<f8").tobytes(),
        "router_import_materialization_bounds": imported.astype("<f8").tobytes(),
    }
    descriptors = {
        name: _artifact_descriptor(
            name, raw,
            "canonical-json" if name == "rmsnorm_decomposition_inputs" else ("little-endian-f32" if name in {"attention_residual", "router_normalized_input", "router_matrix", "ffn_norm_weight"} else "little-endian-f64"),
            [1] if name == "rmsnorm_decomposition_inputs" else ([256, width] if name == "router_matrix" else ([256] if "router_" in name and "input" not in name else [width])),
            ordinal,
            [EXPECTED_NAMES[10]] if "router" in name else [EXPECTED_NAMES[9]],
        )
        for ordinal, (name, raw) in enumerate(private_raw.items(), start=1)
    }
    private_hashes_before = {name: sha256(raw) for name, raw in private_raw.items()}
    private_hashes_after = {name: sha256(raw) for name, raw in private_raw.items()}
    payload_after = [sha256(raw) for raw in payloads]
    if payload_before != payload_after:
        raise ValueError("synthetic payload mutation")
    return {
        "schema": "pulsarmlx.f017.v2-antecedent-recovery-synthetic",
        "schema_version": "1.0.0",
        "synthetic_payload_count": 12,
        "payload_hashes_before": payload_before,
        "payload_hashes_after": payload_after,
        "identity_gates": "PASS",
        "attention_residual_reproduction": "PASS",
        "router_normalized_input_retained": True,
        "private_antecedents": descriptors,
        "synthetic_private_payloads_hex": {name: raw.hex() for name, raw in private_raw.items()},
        "private_hashes_before": private_hashes_before,
        "private_hashes_after": private_hashes_after,
        "pairwise_surface": surface,
        "zero_mlx_candidate_dispatches": True,
        "zero_expert_computation": True,
        "checkpoint_access": 0,
        "route_attempt_consumed": False,
        "new_route_discovery": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--execution-config", type=Path)
    parser.add_argument("--execution-config-sha256")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--authorization-sha256")
    parser.add_argument("--private-package-root", type=Path)
    parser.add_argument("--start-marker", type=Path)
    parser.add_argument("--execute-authorized-recovery", action="store_true")
    args = parser.parse_args()
    root = args.repository_root.resolve(strict=True)
    if args.preflight_only:
        if args.execution_config is None or args.execution_config_sha256 is None:
            parser.error("preflight requires execution config and SHA-256")
        print(preflight(root, args.execution_config, args.execution_config_sha256)["result"])
        return 0
    if args.synthetic:
        result = synthetic_recovery(root)
        validate_synthetic_result(result)
        raw = canonical_json(result)
        if args.output is not None:
            args.output.write_bytes(raw)
        print(sha256(raw))
        return 0
    if args.execute_authorized_recovery:
        required = (
            args.execution_config, args.execution_config_sha256, args.authorization,
            args.authorization_sha256, args.private_package_root, args.output, args.start_marker,
        )
        if any(item is None for item in required):
            parser.error("authorized execution requires config, authorization, private package, output, and start marker")
        execute_authorized_recovery(
            root, args.execution_config, args.execution_config_sha256,
            args.authorization, args.authorization_sha256,
            args.private_package_root.resolve(strict=True), args.output, args.start_marker,
        )
        return 0
    parser.error("real recovery is not authorized by this preparation tool")


if __name__ == "__main__":
    raise SystemExit(main())
