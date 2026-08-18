#!/usr/bin/env python3
"""Checkpoint-free F017 routing-contract v3.1 production evaluation.

The public result contains only symbolic identities and derived analytical
values.  Private paths are CLI inputs and are never serialized.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
from typing import Any, Sequence

import numpy as np

import f017_routing_contract_v31 as theorem
import validate_f017_v2_antecedent_private_reuse as reuse


ROOT = Path(__file__).resolve().parents[2]
STARTING_HEAD = "b899d09b971912a4d8d256fb381558865319818a"
CONSUMER_ID = "F017-DPREFIX-ROUTE-AMBIGUITY-PROPAGATION-ANALYTICAL-1"
EXACT_SHA = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"
REAL2_SHA = "541d8dbcf459b49e9b5c69ae44f919a64c2eaaefa4f6daeb7e0d13443b521aff"
REAL3_SHA = "ad71c3b10531283f55117b8b72f3f754653dfa74f6fbe96faf520f728432ac1a"
ROUTER_BIAS_SHA = "eb6feeb8d7ab446e4e786aaac55c22cc7b98521dbd71cb0a57610d8da59b0491"
V31_CONTRACT_SHA = "084e496d44f2e3857e9f6da0c9e0b922fc11b805df8fda85e8aea86d2c22f455"
V31_IMPLEMENTATION_SHA = "a4ca7d39c76d5c5359e16bdf3f851f309e89c7e5f662713746bb456531597f38"
V31_SPECIFICATION_SHA = "06f432cc609a927b91e2671bcce8878b2a51ff61c88707aed5a68c6402f383dc"
V31_FREEZE_EVIDENCE_SHA = "c4fec4534647243c1a6d5bbda90553114e9fea93cbb2991e177d9661d7c53fcf"
PRIVATE_REUSE_AUTHORIZATION_SHA = "4a6d232366a976892e38fa4da2dbeaf4b77d0c6f6e5195e43672a4537c8f9a07"
PRIVATE_MANIFEST_SHA = "1007112a0642919321d0081e79bba12fe3809c456e79a22b9623d19689b78112"
RECOVERY_RESULT_SHA = "f9422287cb98322d1412a6dd2397bb0f4a0d6538778aa587dddff7c5154acf2a"
EVALUATION_SCHEMA_SHA = "de1749962b6954e962de9b758c0c18942dcc079368916171f7fda362e9eff34c"
CHECKPOINT_READS = 0
SHARD_OPENS = 0
REAL_PAYLOAD_LEDGER = 139

CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-routing-contract-v3.1-state-box.json"
V31_IMPLEMENTATION = ROOT / "scripts/research/f017_routing_contract_v31.py"
SPECIFICATION = ROOT / "docs/architecture/reviews/f017-routing-v3-1-state-box-theorem.md"
FREEZE_EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-routing-v3-1-theorem-freeze-v1.json"
REUSE_AUTHORIZATION = ROOT / "docs/architecture/reviews/evidence/f017-v2-antecedent-private-reuse-authorization-v1.json"
PRIVATE_MANIFEST = ROOT / "docs/architecture/reviews/evidence/f017-v2-antecedent-recovery-private-manifest-v1.json"
RECOVERY_RESULT = ROOT / "docs/architecture/reviews/evidence/f017-v2-antecedent-recovery-result-v1.json"
LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"


class EvaluationError(ValueError):
    """Fail-closed production-evaluation rejection."""


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _finite_vector(values: Sequence[float], label: str) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if not result or not all(math.isfinite(value) for value in result):
        raise EvaluationError(f"{label} must be non-empty and finite")
    return result


@dataclass(frozen=True)
class AmbiguityBox:
    center: tuple[float, ...]
    radius: tuple[float, ...]
    componentwise_radius_max: float
    l1_radius: float
    l2_radius: float


def build_ambiguity_box(
    center: Sequence[float], real2: Sequence[float], real3: Sequence[float]
) -> AmbiguityBox:
    center_values = _finite_vector(center, "ambiguity center")
    real2_values = _finite_vector(real2, "REAL-2 state")
    real3_values = _finite_vector(real3, "REAL-3 state")
    if len(center_values) != len(real2_values) or len(center_values) != len(real3_values):
        raise EvaluationError("ambiguity states must be shape-aligned")
    radius = tuple(
        math.nextafter(max(abs(left - nominal), abs(right - nominal)), math.inf)
        for nominal, left, right in zip(center_values, real2_values, real3_values, strict=True)
    )
    return AmbiguityBox(
        center_values,
        radius,
        max(radius),
        math.nextafter(math.fsum(radius), math.inf),
        math.nextafter(math.sqrt(math.fsum(value * value for value in radius)), math.inf),
    )


def _f64_sha(values: Sequence[float]) -> str:
    return sha256_bytes(struct.pack("<" + "d" * len(values), *values))


def _u16_sha(values: Sequence[int]) -> str:
    return sha256_bytes(struct.pack("<" + "H" * len(values), *values))


def _interval_json(value: theorem.Interval) -> dict[str, float]:
    return {"lower": value.lower, "upper": value.upper}


def _factor_json(value: float | None) -> float | str:
    return "INFINITE" if value is None else value


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        raise EvaluationError("empty percentile surface")
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def evaluate_vectors(
    *,
    center: Sequence[float],
    real2: Sequence[float],
    real3: Sequence[float],
    gamma: Sequence[float],
    router_rows: Sequence[Sequence[float]],
    correction_bias: Sequence[float],
    reduction_guards: Sequence[float],
    import_guards: Sequence[float],
) -> dict[str, Any]:
    """Evaluate the frozen theorem for already identity-validated values."""

    box = build_ambiguity_box(center, real2, real3)
    gamma_values = _finite_vector(gamma, "FFN norm gamma")
    bias_values = _finite_vector(correction_bias, "correction bias")
    if len(box.center) != len(gamma_values):
        raise EvaluationError("center and FFN norm gamma must be shape-aligned")
    if len(router_rows) != theorem.EXPERT_COUNT or len(bias_values) != theorem.EXPERT_COUNT:
        raise EvaluationError("production routing surface must have 256 experts")
    rows = tuple(_finite_vector(row, "router row") for row in router_rows)
    if any(len(row) != len(box.center) for row in rows):
        raise EvaluationError("router rows must match state width")
    reduction = _finite_vector(reduction_guards, "reduction guards")
    imported = _finite_vector(import_guards, "import guards")
    if len(reduction) != theorem.EXPERT_COUNT or len(imported) != theorem.EXPERT_COUNT:
        raise EvaluationError("router guards must be row-aligned")

    rms = theorem.propagate_rmsnorm(box.center, box.radius, gamma_values)
    logit_intervals = theorem.propagate_router_logits(
        rms.gamma_scaled,
        rows,
        logit_bias=None,
        reduction_guards=reduction,
        import_guards=imported,
        bias_guards=(0.0,) * theorem.EXPERT_COUNT,
    )
    score_enclosure = theorem.propagate_scores(
        logit_intervals,
        bias_values,
        score_bias_guards=(0.0,) * theorem.EXPERT_COUNT,
    )

    nominal_rms = math.sqrt(
        math.fsum(value * value for value in box.center) / len(box.center) + theorem.RMS_EPSILON
    )
    normalized = tuple(weight * value / nominal_rms for weight, value in zip(gamma_values, box.center, strict=True))
    logits = tuple(
        math.fsum(weight * value for weight, value in zip(row, normalized, strict=True))
        for row in rows
    )
    probabilities = tuple(theorem.sigmoid(value) for value in logits)
    scores = tuple(value + bias for value, bias in zip(probabilities, bias_values, strict=True))
    ranking = theorem.select_top_k_diagnostic(scores, top_k=theorem.EXPERT_COUNT)
    selected = ranking[: theorem.TOP_K]
    unselected = ranking[theorem.TOP_K :]
    pairs = tuple(
        theorem.pair_safety(
            selected_id,
            challenger_id,
            score_enclosure.selection_scores[selected_id],
            score_enclosure.selection_scores[challenger_id],
            scores[selected_id],
            scores[challenger_id],
        )
        for selected_id in selected
        for challenger_id in unselected
    )
    if len(pairs) != theorem.TOP_K * (theorem.EXPERT_COUNT - theorem.TOP_K):
        raise EvaluationError("membership pair cardinality")
    summary = theorem.summarize_pair_safety(pairs)
    finite_factors = [pair.factor for pair in pairs if pair.factor is not None]

    denominator = max(
        theorem.DENOMINATOR_FLOOR,
        math.fsum(probabilities[expert_id] for expert_id in selected),
    )
    exact_weights = {
        expert_id: theorem.ROUTING_WEIGHT_SCALE * probabilities[expert_id] / denominator
        for expert_id in selected
    }
    weight_intervals = theorem.selected_weight_intervals(
        selected,
        {expert_id: score_enclosure.probabilities[expert_id] for expert_id in selected},
    )
    all_contained = all(weight_intervals[expert_id].contains(exact_weights[expert_id]) for expert_id in selected)

    pair_records = [
        {
            "selected_expert_id": pair.selected_id,
            "challenger_expert_id": pair.challenger_id,
            "exact_selected_score": scores[pair.selected_id],
            "exact_challenger_score": scores[pair.challenger_id],
            "exact_positive_margin": pair.nominal_margin,
            "selected_score_interval": _interval_json(score_enclosure.selection_scores[pair.selected_id]),
            "challenger_score_interval": _interval_json(score_enclosure.selection_scores[pair.challenger_id]),
            "score_difference_interval": _interval_json(pair.difference),
            "difference_lower": pair.difference.lower,
            "ambiguity_allowance": pair.ambiguity_allowance,
            "mathematical_safety_factor": _factor_json(pair.factor),
            "mathematical_pass": pair.mathematical_factor_pass,
            "engineering_h2_pass": pair.engineering_h2_pass,
        }
        for pair in pairs
    ]
    expert_records = [
        {
            "expert_id": expert_id,
            "exact_logit": logits[expert_id],
            "logit_interval": _interval_json(logit_intervals[expert_id]),
            "exact_probability": probabilities[expert_id],
            "probability_interval": _interval_json(score_enclosure.probabilities[expert_id]),
            "correction_bias": bias_values[expert_id],
            "exact_score": scores[expert_id],
            "score_interval": _interval_json(score_enclosure.selection_scores[expert_id]),
        }
        for expert_id in range(theorem.EXPERT_COUNT)
    ]
    selected_weights = {
        str(expert_id): {
            "expert_id": expert_id,
            "exact_probability": probabilities[expert_id],
            "probability_interval": _interval_json(score_enclosure.probabilities[expert_id]),
            "exact_routing_weight": exact_weights[expert_id],
            "routing_weight_interval": _interval_json(weight_intervals[expert_id]),
            "exact_weight_contained": weight_intervals[expert_id].contains(exact_weights[expert_id]),
            "mathematical_qualification": "ENCLOSURE_VALID_ACCEPTANCE_RULE_UNFROZEN",
            "engineering_qualification": "ACCEPTANCE_RULE_UNFROZEN",
        }
        for expert_id in selected
    }
    all_membership = bool(summary["all_membership_invariant"])
    disposition = (
        "ROUTE SET INVARIANT / WEIGHTS REQUIRE QUALIFICATION"
        if all_membership and all_contained
        else "ROUTE NOT PROVEN INVARIANT"
    )
    return {
        "ambiguity_set": {
            "center": "DPREFIX-EXACT-1",
            "construction": "outward max(abs(REAL-2-exact),abs(REAL-3-exact)) per component",
            "component_count": len(box.center),
            "componentwise_radius_max": box.componentwise_radius_max,
            "l1_radius": box.l1_radius,
            "l2_radius": box.l2_radius,
        },
        "exact_route": {
            "policy": "ANALYTICAL_ROUTE_PLANNING_ONLY",
            "rms": nominal_rms,
            "normalized_state_sha256_lef64": _f64_sha(normalized),
            "logits_sha256_lef64": _f64_sha(logits),
            "probabilities_sha256_lef64": _f64_sha(probabilities),
            "scores_sha256_lef64": _f64_sha(scores),
            "ranking_sha256_leu16": _u16_sha(ranking),
            "ranking": list(ranking),
            "selected_top8": list(selected),
            "selected_set": sorted(selected),
        },
        "experts": expert_records,
        "membership": {
            "required": 1984,
            "evaluated": len(pairs),
            "mathematical_pass_count": sum(pair.mathematical_factor_pass for pair in pairs),
            "mathematical_fail_count": sum(not pair.mathematical_factor_pass for pair in pairs),
            "all_membership_invariant": all_membership,
            "minimum_mathematical_safety_factor": summary["minimum_safety_factor"],
            "worst_pair": summary["worst_pair"],
            "count_factor_below_1": summary["count_below_1"],
            "count_factor_below_2": summary["count_below_2"],
            "engineering_h2_pass_count": sum(pair.engineering_h2_pass for pair in pairs),
            "engineering_h2_fail_count": sum(not pair.engineering_h2_pass for pair in pairs),
            "median_finite_safety_factor": summary["median_finite_safety_factor"],
            "factor_percentiles": {
                "p05": _percentile(finite_factors, 0.05),
                "p25": _percentile(finite_factors, 0.25),
                "p75": _percentile(finite_factors, 0.75),
                "p95": _percentile(finite_factors, 0.95),
            },
            "minimum_positive_difference_lower": min(pair.difference.lower for pair in pairs if pair.difference.lower > 0.0),
            "exact_state_minimum_membership_margin": min(pair.nominal_margin for pair in pairs),
            "pairs": pair_records,
        },
        "selected_weights": {
            "precondition_selected_set_invariant": all_membership,
            "key_semantics": "expert_id",
            "by_expert_id": selected_weights,
            "all_exact_weights_contained": all_contained,
            "qualification": "REQUIRES_FROZEN_ACCEPTANCE_RULE",
            "reason": "v3.1 freezes sound ID-keyed intervals but no mathematical or engineering interval-width acceptance threshold",
        },
        "guards": {
            "reduction_guards": "AUTHORIZED_ROW_SPECIFIC_VALUES_APPLIED",
            "import_materialization_guards": "AUTHORIZED_ROW_SPECIFIC_VALUES_APPLIED",
            "linear_logit_bias": "ABSENT",
            "linear_bias_representation_guards": "EXACT_ZERO",
            "correction_bias_representation_guards": "EXACT_ZERO_AFTER_F32_IDENTITY_VALIDATION",
            "transport_rounding": "V3_1_DIRECTED_OUTWARD_NEXTAFTER",
            "legacy_v2_attention_and_non_radial_artifacts": "IDENTITY_VERIFIED_NOT_SUBSTITUTED_FOR_V3_1_DIRECT_STATE_BOX",
        },
        "route_insensitivity_disposition": disposition,
    }


def _read_f32(path: Path, expected_sha: str, count: int, label: str) -> list[float]:
    if path.is_symlink() or not path.is_file():
        raise EvaluationError(f"{label} must be a regular non-symlink file")
    metadata = path.stat()
    if metadata.st_mode & 0o222 or metadata.st_nlink != 1:
        raise EvaluationError(f"{label} must be read-only without a hard-link alias")
    raw = path.read_bytes()
    if sha256_bytes(raw) != expected_sha or len(raw) != count * 4:
        raise EvaluationError(f"{label} identity mismatch")
    return np.frombuffer(raw, dtype="<f4").astype(np.float64).tolist()


def _assert_public_identities() -> None:
    expected = {
        CONTRACT: V31_CONTRACT_SHA,
        V31_IMPLEMENTATION: V31_IMPLEMENTATION_SHA,
        SPECIFICATION: V31_SPECIFICATION_SHA,
        FREEZE_EVIDENCE: V31_FREEZE_EVIDENCE_SHA,
        REUSE_AUTHORIZATION: PRIVATE_REUSE_AUTHORIZATION_SHA,
        PRIVATE_MANIFEST: PRIVATE_MANIFEST_SHA,
        RECOVERY_RESULT: RECOVERY_RESULT_SHA,
    }
    for path, digest in expected.items():
        if sha256_path(path) != digest:
            raise EvaluationError(f"public authority identity mismatch: {path.name}")
    ledger = json.loads(LEDGER.read_text())
    real2 = [item for item in ledger.get("events", []) if item.get("attempt") == "DPREFIX-REAL-2"]
    if len(real2) != 1 or real2[0].get("cumulative_tensor_payloads_after_event") != REAL_PAYLOAD_LEDGER:
        raise EvaluationError("route-evaluation ledger boundary drift")
    if ledger.get("cumulative_tensor_payloads", 0) < REAL_PAYLOAD_LEDGER:
        raise EvaluationError("real-payload ledger predates route evaluation")


def evaluate_authorized_package(
    private_package_root: Path,
    exact_state: Path,
    real2_state: Path,
    real3_state: Path,
) -> dict[str, Any]:
    _assert_public_identities()
    reuse_document = reuse.load_json(REUSE_AUTHORIZATION)
    reuse.validate_authorization_document(reuse_document)
    inventory = reuse.expected_inventory(reuse.load_json(PRIVATE_MANIFEST))
    before = reuse.verify_private_artifacts(private_package_root, inventory)

    center = _read_f32(exact_state, EXACT_SHA, 6144, "DPREFIX-EXACT-1")
    real2 = _read_f32(real2_state, REAL2_SHA, 6144, "REAL-2 state")
    real3 = _read_f32(real3_state, REAL3_SHA, 6144, "REAL-3 state")
    antecedents = private_package_root / "antecedents"
    gamma = _read_f32(antecedents / "ffn_norm_weight.bin", before["antecedents/ffn_norm_weight.bin"], 6144, "FFN norm weight")
    router_flat = _read_f32(antecedents / "router_matrix.bin", before["antecedents/router_matrix.bin"], 256 * 6144, "router matrix")
    router_rows = [router_flat[index * 6144 : (index + 1) * 6144] for index in range(256)]
    reduction = np.frombuffer((antecedents / "router_reduction_bounds.bin").read_bytes(), dtype="<f8").tolist()
    imported = np.frombuffer((antecedents / "router_import_materialization_bounds.bin").read_bytes(), dtype="<f8").tolist()
    recovery = json.loads(RECOVERY_RESULT.read_text())
    correction_bias = recovery["antecedent_retention"]["router_bias"]
    if len(correction_bias) != 256 or sha256_bytes(struct.pack("<256f", *correction_bias)) != ROUTER_BIAS_SHA:
        raise EvaluationError("correction-bias identity mismatch")

    first = evaluate_vectors(
        center=center,
        real2=real2,
        real3=real3,
        gamma=gamma,
        router_rows=router_rows,
        correction_bias=correction_bias,
        reduction_guards=reduction,
        import_guards=imported,
    )
    second = evaluate_vectors(
        center=center,
        real2=real2,
        real3=real3,
        gamma=gamma,
        router_rows=router_rows,
        correction_bias=correction_bias,
        reduction_guards=reduction,
        import_guards=imported,
    )
    first_raw = canonical_json(first)
    second_raw = canonical_json(second)
    if first_raw != second_raw:
        raise EvaluationError("deterministic route replay mismatch")
    after = reuse.verify_private_artifacts(private_package_root, inventory)
    if before != after:
        raise EvaluationError("authorized private artifact mutation")

    return {
        "schema": "pulsarmlx.f017.dprefix-route-ambiguity-v3.1-evaluation",
        "schema_version": "1.0.0",
        "schema_contract": {
            "path": "specs/017-rust-native-inference-runtime/contracts/f017-dprefix-route-ambiguity-v31-evaluation-v1.schema.json",
            "sha256": EVALUATION_SCHEMA_SHA,
        },
        "starting_authoritative_head": STARTING_HEAD,
        "consumer_id": CONSUMER_ID,
        "scope": "ANALYTICAL_ROUTE_PLANNING_ONLY",
        "authority": {
            "DPREFIX_EXACT_1_sha256": EXACT_SHA,
            "REAL_2_state_sha256": REAL2_SHA,
            "REAL_3_state_sha256": REAL3_SHA,
            "routing_contract_v3_1_sha256": V31_CONTRACT_SHA,
            "routing_implementation_v3_1_sha256": V31_IMPLEMENTATION_SHA,
            "routing_specification_v3_1_sha256": V31_SPECIFICATION_SHA,
            "routing_freeze_evidence_sha256": V31_FREEZE_EVIDENCE_SHA,
            "private_reuse_authorization_sha256": PRIVATE_REUSE_AUTHORIZATION_SHA,
            "private_manifest_sha256": PRIVATE_MANIFEST_SHA,
            "recovery_result_sha256": RECOVERY_RESULT_SHA,
            "correction_bias_sha256": ROUTER_BIAS_SHA,
            "evaluation_tool": {
                "path": "scripts/research/f017_route_ambiguity_v31_evaluation.py",
                "sha256": sha256_path(Path(__file__)),
            },
        },
        "private_reuse": {
            "artifact_count": len(inventory),
            "authorized_symbolic_names": [item["symbolic_name"] for item in inventory],
            "before_sha256": before,
            "after_sha256": after,
            "unchanged": before == after,
            "machine_local_paths_published": False,
        },
        "evaluation": first,
        "deterministic_replay": {
            "run_count": 2,
            "run_1_sha256": sha256_bytes(first_raw),
            "run_2_sha256": sha256_bytes(second_raw),
            "identical": True,
        },
        "expectation_check": {
            "precommitted_score_ambiguity_order": "approximately 1e-6",
            "observed_max_score_interval_width": max(item["score_interval"]["upper"] - item["score_interval"]["lower"] for item in first["experts"]),
            "precommitted_margin_order": "approximately 1e-3",
            "observed_minimum_membership_margin": first["membership"]["exact_state_minimum_membership_margin"],
            "precommitted_safety_factor_order": "approximately 1e2 to 1e3",
            "observed_minimum_safety_factor": first["membership"]["minimum_mathematical_safety_factor"],
            "classification": "DIFFERS_MATERIALLY_RETAINED_ROW_GUARDS_DOMINATE_WORST_BOUND",
            "theorem_or_guard_modified_after_observation": False,
        },
        "historical_immutability": {
            "DPREFIX_REAL_1": "REJECTED_UNCHANGED",
            "DPREFIX_REAL_2": "REJECTED_UNCHANGED",
            "DPREFIX_REAL_3": "REJECTED_UNCHANGED",
            "DPREFIX_EXACT_1": "CANONICAL_UNCHANGED",
        },
        "isolation": {
            "checkpoint_reads": CHECKPOINT_READS,
            "shard_opens": SHARD_OPENS,
            "real_payload_ledger_before": REAL_PAYLOAD_LEDGER,
            "real_payload_ledger_after": REAL_PAYLOAD_LEDGER,
            "ledger_mutated": False,
            "candidate_or_model_dispatches": 0,
            "representative_m1f0_execution": False,
        },
        "result": first["route_insensitivity_disposition"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-package-root", type=Path, required=True)
    parser.add_argument("--exact-state", type=Path, required=True)
    parser.add_argument("--real2-state", type=Path, required=True)
    parser.add_argument("--real3-state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_authorized_package(
        args.private_package_root.resolve(strict=True),
        args.exact_state.resolve(strict=True),
        args.real2_state.resolve(strict=True),
        args.real3_state.resolve(strict=True),
    )
    raw = canonical_json(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    print(result["result"])
    print(f"EVALUATION_SHA256={sha256_bytes(raw)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
