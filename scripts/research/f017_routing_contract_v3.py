#!/usr/bin/env python3
"""Checkpoint-free semantic and numerical research for F017 routing v3.

The module intentionally separates the model-semantic routing object
(`expert_id`, `routing_weight`) from the rank-ordered transport used by the
current kernels.  It never opens a checkpoint.  The retained v2 private
antecedents are read only to derive pre-observation, ID-keyed weight intervals.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

from scripts.research.f017_route_stability_v2 import derivative_interval, outward, sigmoid

RAW_RECOVERY_SHA256 = "f9422287cb98322d1412a6dd2397bb0f4a0d6538778aa587dddff7c5154acf2a"
V2_CONTRACT_SHA256 = "36adbdcffeeb361638ec80258b912711b17a671276d68cf0129826e1ae042ac7"
ROUTE_SHA256 = "980b6a78ae04b816e1f9e563790f5a2d123723292dd0432a0218972d0f80593e"
LEDGER = 57
TOP_K = 8
EXPERT_COUNT = 256
WEIGHT_SCALE = 2.5
F32_UNIT_ROUNDOFF = 2.0 ** -24
F32_MIN_SUBNORMAL = float(np.nextafter(np.float32(0.0), np.float32(1.0)))
R10_ROUTING_WEIGHT_ATOL = 1.0e-5
R10_INTERMEDIATE_ATOL = 0.015625
ENGINEERING_HEADROOM = 2.0


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_json_no_duplicates(path: Path) -> dict:
    def pairs(items: list[tuple[str, object]]) -> dict:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key {key!r} in {path}")
            result[key] = value
        return result

    value = json.loads(path.read_text(), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError(f"expected object in {path}")
    return value


@dataclass(frozen=True, slots=True)
class RoutingPair:
    expert_id: int
    routing_weight: float

    def validate(self) -> None:
        if not 0 <= self.expert_id < EXPERT_COUNT:
            raise ValueError("expert ID outside the GLM routing domain")
        if not math.isfinite(self.routing_weight) or self.routing_weight <= 0.0:
            raise ValueError("routing weight must be finite and strictly positive")
        if self.routing_weight == 0.0 and math.copysign(1.0, self.routing_weight) < 0.0:
            raise ValueError("negative zero routing weight")


def atomic_pairs(ids: Sequence[int], weights: Sequence[float]) -> tuple[RoutingPair, ...]:
    if len(ids) != TOP_K or len(weights) != TOP_K:
        raise ValueError("exactly eight routing pairs required")
    pairs = tuple(RoutingPair(int(expert_id), float(weight)) for expert_id, weight in zip(ids, weights, strict=True))
    for item in pairs:
        item.validate()
    if len({item.expert_id for item in pairs}) != len(pairs):
        raise ValueError("duplicate selected expert")
    return pairs


def canonical_semantic_pairs(pairs: Sequence[RoutingPair]) -> tuple[RoutingPair, ...]:
    validated = atomic_pairs(
        [item.expert_id for item in pairs],
        [item.routing_weight for item in pairs],
    )
    return tuple(sorted(validated, key=lambda item: item.expert_id))


def canonical_semantic_bytes(pairs: Sequence[RoutingPair]) -> bytes:
    """Eight ID-sorted atomic records: little-endian u16 then f64."""
    return b"".join(
        struct.pack("<Hd", item.expert_id, item.routing_weight)
        for item in canonical_semantic_pairs(pairs)
    )


def canonical_semantic_sha256(pairs: Sequence[RoutingPair]) -> str:
    return sha256_bytes(canonical_semantic_bytes(pairs))


def rank_diagnostic_bytes(pairs: Sequence[RoutingPair]) -> bytes:
    validated = atomic_pairs(
        [item.expert_id for item in pairs],
        [item.routing_weight for item in pairs],
    )
    return b"".join(struct.pack("<Hd", item.expert_id, item.routing_weight) for item in validated)


def mathematical_moe_sum(
    pairs: Sequence[RoutingPair], expert_outputs: Mapping[int, Sequence[float]]
) -> tuple[float, ...]:
    pairs = atomic_pairs(
        [item.expert_id for item in pairs],
        [item.routing_weight for item in pairs],
    )
    widths = {len(expert_outputs[item.expert_id]) for item in pairs}
    if len(widths) != 1 or not widths or next(iter(widths)) == 0:
        raise ValueError("expert output shape")
    width = next(iter(widths))
    if any(
        not math.isfinite(float(value))
        for item in pairs
        for value in expert_outputs[item.expert_id]
    ):
        raise ValueError("non-finite expert output")
    return tuple(
        math.fsum(
            item.routing_weight * float(expert_outputs[item.expert_id][column])
            for item in pairs
        )
        for column in range(width)
    )


def f32(value: float) -> float:
    with np.errstate(over="ignore", invalid="ignore"):
        result = float(np.float32(value))
    if not math.isfinite(result):
        raise ValueError("non-finite f32 operation")
    return result


def f32_atomic_terms(
    pairs: Sequence[RoutingPair], expert_outputs: Mapping[int, Sequence[float]]
) -> dict[int, tuple[float, ...]]:
    validated = atomic_pairs(
        [item.expert_id for item in pairs],
        [item.routing_weight for item in pairs],
    )
    widths = {len(expert_outputs[item.expert_id]) for item in validated}
    if len(widths) != 1 or not widths or next(iter(widths)) == 0:
        raise ValueError("expert output shape")
    return {
        item.expert_id: tuple(
            f32(item.routing_weight * float(value))
            for value in expert_outputs[item.expert_id]
        )
        for item in validated
    }


def accumulate_f32(order: Sequence[int], terms: Mapping[int, Sequence[float]]) -> tuple[float, ...]:
    if len(order) != TOP_K or len(set(order)) != TOP_K or set(order) != set(terms):
        raise ValueError("accumulation order is not an exact expert permutation")
    widths = {len(terms[item]) for item in order}
    if len(widths) != 1:
        raise ValueError("term shape")
    result = [0.0] * next(iter(widths))
    for expert_id in order:
        for index, value in enumerate(terms[expert_id]):
            result[index] = f32(result[index] + float(value))
    return tuple(result)


def gamma(count: int, unit_roundoff: float = F32_UNIT_ROUNDOFF) -> float:
    product = count * unit_roundoff
    if count < 0 or product >= 1.0:
        raise ValueError("invalid gamma")
    return product / (1.0 - product)


def accumulation_order_bound(terms: Mapping[int, Sequence[float]]) -> tuple[float, ...]:
    """Conservative difference between any two serial f32 reductions.

    Atomic products are already rounded to f32.  Each serial sum has absolute
    error at most gamma_7 * sum(abs(term)); comparing two orders doubles that
    envelope.  The subnormal guard covers seven additions in both reductions.
    """
    if len(terms) != TOP_K:
        raise ValueError("exactly eight atomic term vectors required")
    widths = {len(value) for value in terms.values()}
    if len(widths) != 1:
        raise ValueError("term shape")
    width = next(iter(widths))
    factor = 2.0 * gamma(TOP_K - 1)
    subnormal = 2.0 * (TOP_K - 1) * F32_MIN_SUBNORMAL
    return tuple(
        math.nextafter(
            factor * math.fsum(abs(float(value[column])) for value in terms.values())
            + subnormal,
            math.inf,
        )
        for column in range(width)
    )


def qualify_accumulation_orders(
    pairs: Sequence[RoutingPair],
    expert_outputs: Mapping[int, Sequence[float]],
    candidate_order: Sequence[int],
) -> dict[str, object]:
    terms = f32_atomic_terms(pairs, expert_outputs)
    oracle_order = [item.expert_id for item in pairs]
    id_order = sorted(oracle_order)
    rank_sum = accumulate_f32(oracle_order, terms)
    id_sum = accumulate_f32(id_order, terms)
    candidate_sum = accumulate_f32(candidate_order, terms)
    bound = accumulation_order_bound(terms)
    differences = {
        "rank_vs_id": [abs(a - b) for a, b in zip(rank_sum, id_sum, strict=True)],
        "rank_vs_candidate": [abs(a - b) for a, b in zip(rank_sum, candidate_sum, strict=True)],
    }
    if any(
        difference > limit
        for values in differences.values()
        for difference, limit in zip(values, bound, strict=True)
    ):
        raise AssertionError("accumulation-order bound under-bound")
    maximum_bound = max(bound, default=0.0)
    return {
        "mathematical_equivalence": True,
        "bitwise_equivalence": rank_sum == id_sum == candidate_sum,
        "maximum_observed_difference": max((max(values, default=0.0) for values in differences.values()), default=0.0),
        "maximum_bound": maximum_bound,
        "covered_by_r10_intermediate_tier_b": maximum_bound <= R10_INTERMEDIATE_ATOL,
        "oracle_runtime_policy": "rank_order_serial_f32",
        "semantic_evidence_policy": "expert_id_sorted_atomic_pairs",
        "runtime_change": False,
    }


def qualify_candidate_pairs(
    oracle: Sequence[RoutingPair],
    candidate: Sequence[RoutingPair],
    permitted_intervals: Mapping[int, tuple[float, float]],
) -> dict[str, object]:
    oracle_atomic = canonical_semantic_pairs(oracle)
    candidate_atomic = canonical_semantic_pairs(candidate)
    if [item.expert_id for item in oracle_atomic] != [item.expert_id for item in candidate_atomic]:
        raise ValueError("selected expert membership mismatch")
    failures = []
    engineering_failures = []
    for item in candidate_atomic:
        if item.expert_id not in permitted_intervals:
            raise ValueError("missing ID-keyed weight interval")
        low, high = permitted_intervals[item.expert_id]
        if not (math.isfinite(low) and math.isfinite(high) and 0.0 < low <= high):
            raise ValueError("invalid ID-keyed weight interval")
        oracle_weight = next(
            oracle_item.routing_weight
            for oracle_item in oracle_atomic
            if oracle_item.expert_id == item.expert_id
        )
        absolute_error = abs(item.routing_weight - oracle_weight)
        if not low <= item.routing_weight <= high or absolute_error > R10_ROUTING_WEIGHT_ATOL:
            failures.append(item.expert_id)
        engineering_low = oracle_weight - (oracle_weight - low) / ENGINEERING_HEADROOM
        engineering_high = oracle_weight + (high - oracle_weight) / ENGINEERING_HEADROOM
        if (
            not engineering_low <= item.routing_weight <= engineering_high
            or absolute_error > R10_ROUTING_WEIGHT_ATOL / ENGINEERING_HEADROOM
        ):
            engineering_failures.append(item.expert_id)
    return {
        "semantic_pass": not failures,
        "engineering_headroom_pass": not engineering_failures,
        "failed_weight_experts": failures,
        "failed_engineering_weight_experts": engineering_failures,
        "rank_equal": rank_diagnostic_bytes(oracle) == rank_diagnostic_bytes(candidate),
        "semantic_hash_equal": canonical_semantic_sha256(oracle) == canonical_semantic_sha256(candidate),
    }


def _read_f32(path: Path, shape: tuple[int, ...]) -> np.ndarray:
    value = np.fromfile(path, dtype="<f4")
    if value.size != math.prod(shape):
        raise ValueError(f"private f32 shape mismatch: {path}")
    return value.reshape(shape)


def _read_f64(path: Path, shape: tuple[int, ...]) -> np.ndarray:
    value = np.fromfile(path, dtype="<f8")
    if value.size != math.prod(shape):
        raise ValueError(f"private f64 shape mismatch: {path}")
    return value.reshape(shape)


def _load_private_antecedents(root: Path, raw: dict) -> dict[str, object]:
    package = root / "target/f017-v2-antecedent-recovery-event-1/recovery-package/antecedents"
    expected = raw["antecedent_retention"]["private_artifacts"]
    names = {
        "router_matrix": ((EXPERT_COUNT, 6144), _read_f32),
        "non_radial_component_bounds": ((6144,), _read_f64),
        "router_reduction_bounds": ((EXPERT_COUNT,), _read_f64),
        "router_import_materialization_bounds": ((EXPERT_COUNT,), _read_f64),
    }
    result: dict[str, object] = {}
    for name, (shape, loader) in names.items():
        path = package / f"{name}.bin"
        relative = f"antecedents/{name}.bin"
        if not path.is_file() or sha256_path(path) != expected[relative]:
            raise ValueError(f"private antecedent identity mismatch: {name}")
        result[name] = loader(path, shape)
    decomposition_path = package / "rmsnorm_decomposition_inputs.bin"
    if sha256_path(decomposition_path) != expected["antecedents/rmsnorm_decomposition_inputs.bin"]:
        raise ValueError("RMSNorm decomposition identity mismatch")
    result["rmsnorm_decomposition_inputs"] = json.loads(decomposition_path.read_bytes())
    return result


def individual_probability_intervals(root: Path) -> dict[int, dict[str, float]]:
    raw_path = root / "docs/architecture/reviews/evidence/f017-v2-antecedent-recovery-result-v1.json"
    if sha256_path(raw_path) != RAW_RECOVERY_SHA256:
        raise ValueError("raw recovery evidence identity mismatch")
    raw = parse_json_no_duplicates(raw_path)
    private = _load_private_antecedents(root, raw)
    logits = [float(value) for value in raw["antecedent_retention"]["router_logits"]]
    probabilities = [float(value) for value in raw["antecedent_retention"]["router_probabilities"]]
    selected = [int(value) for value in raw["antecedent_retention"]["pairwise_surface"]["selected_ids_ordered"]]
    rows = private["router_matrix"]
    residual = private["non_radial_component_bounds"]
    reduction = private["router_reduction_bounds"]
    imported = private["router_import_materialization_bounds"]
    decomposition = private["rmsnorm_decomposition_inputs"]
    if not isinstance(rows, np.ndarray) or not isinstance(residual, np.ndarray):
        raise TypeError("private antecedent type")
    lambda_bound = float(decomposition["lambda_bound"])
    intervals: dict[int, dict[str, float]] = {}
    for expert_id in selected:
        logit_error = outward(
            abs(logits[expert_id]) * lambda_bound
            + math.fsum(
                abs(float(weight)) * float(bound)
                for weight, bound in zip(rows[expert_id], residual, strict=True)
            )
            + float(reduction[expert_id])
            + float(imported[expert_id])
        )
        derivative = derivative_interval(
            math.nextafter(logits[expert_id] - logit_error, -math.inf),
            math.nextafter(logits[expert_id] + logit_error, math.inf),
        )
        probability_error = outward(derivative[1] * logit_error + 4.0 * math.ulp(probabilities[expert_id]))
        low = max(math.nextafter(probabilities[expert_id] - probability_error, -math.inf), math.ulp(0.0))
        high = min(math.nextafter(probabilities[expert_id] + probability_error, math.inf), 1.0)
        if not 0.0 < low <= probabilities[expert_id] <= high < 1.0:
            raise ValueError("invalid probability interval")
        intervals[expert_id] = {
            "oracle_logit": logits[expert_id],
            "oracle_probability": probabilities[expert_id],
            "logit_error_bound": logit_error,
            "probability_error_bound": probability_error,
            "probability_low": low,
            "probability_high": high,
        }
    return intervals


def normalized_weight_intervals(
    probability_intervals: Mapping[int, Mapping[str, float]],
    oracle_pairs: Sequence[RoutingPair],
) -> dict[int, dict[str, float | bool]]:
    pairs = canonical_semantic_pairs(oracle_pairs)
    selected = [item.expert_id for item in pairs]
    if set(selected) != set(probability_intervals):
        raise ValueError("probability interval membership")
    result: dict[int, dict[str, float | bool]] = {}
    for item in pairs:
        current = probability_intervals[item.expert_id]
        other_ids = [expert_id for expert_id in selected if expert_id != item.expert_id]
        denominator_for_low = float(current["probability_low"]) + math.fsum(
            float(probability_intervals[expert_id]["probability_high"])
            for expert_id in other_ids
        )
        denominator_for_high = float(current["probability_high"]) + math.fsum(
            float(probability_intervals[expert_id]["probability_low"])
            for expert_id in other_ids
        )
        low = math.nextafter(
            WEIGHT_SCALE * float(current["probability_low"]) / denominator_for_low,
            -math.inf,
        )
        high = math.nextafter(
            WEIGHT_SCALE * float(current["probability_high"]) / denominator_for_high,
            math.inf,
        )
        # Future production materializes the normalized weight as f32.  One
        # full f32 ULP on either endpoint is an explicit transport guard.
        f32_guard = max(
            abs(float(np.spacing(np.float32(low)))),
            abs(float(np.spacing(np.float32(high)))),
        )
        low = max(math.nextafter(low - f32_guard, -math.inf), math.ulp(0.0))
        high = math.nextafter(high + f32_guard, math.inf)
        error_bound = max(item.routing_weight - low, high - item.routing_weight)
        if not low <= item.routing_weight <= high:
            raise ValueError("oracle weight outside derived interval")
        result[item.expert_id] = {
            **current,
            "oracle_routing_weight": item.routing_weight,
            "routing_weight_low": low,
            "routing_weight_high": high,
            "routing_weight_error_bound": error_bound,
            "routing_weight_engineering_low": math.nextafter(
                item.routing_weight - (item.routing_weight - low) / ENGINEERING_HEADROOM,
                math.inf,
            ),
            "routing_weight_engineering_high": math.nextafter(
                item.routing_weight + (high - item.routing_weight) / ENGINEERING_HEADROOM,
                -math.inf,
            ),
            "oracle_self_consistent": True,
            "inherited_r10_candidate_atol": R10_ROUTING_WEIGHT_ATOL,
            "future_candidate_rule": "ID-keyed candidate weight must satisfy both this propagated interval and inherited R10 max-absolute error",
            "positivity_safety_factor": item.routing_weight / error_bound if error_bound else math.inf,
        }
    return result


def accumulation_stress(sample_count: int = 20_000, seed: int = 170_189_003) -> dict[str, object]:
    rng = np.random.Generator(np.random.PCG64(seed))
    under_bounds = 0
    bitwise_equal = 0
    maximum_ratio = 0.0
    maximum_difference = 0.0
    maximum_bound = 0.0
    ids = tuple(range(TOP_K))
    for iteration in range(sample_count):
        mode = iteration % 6
        if mode == 0:
            values = rng.normal(0.0, 1.0, size=TOP_K)
        elif mode == 1:
            values = np.asarray([(-1.0) ** index * (1.0 + index * 2.0 ** -20) for index in ids])
        elif mode == 2:
            values = rng.choice([-1.0, 1.0], size=TOP_K) * np.geomspace(2.0 ** -120, 2.0 ** 120, TOP_K)
        elif mode == 3:
            values = np.asarray([0.0, -0.0, F32_MIN_SUBNORMAL, -F32_MIN_SUBNORMAL, 1e-30, -1e-30, 1.0, -1.0])
        elif mode == 4:
            values = rng.uniform(-1e30, 1e30, size=TOP_K)
        else:
            base = float(rng.uniform(-1e5, 1e5))
            values = np.asarray([base, -base, base, -base, 1e-4, -1e-4, 3e-4, -3e-4])
        terms = {expert_id: (f32(float(values[expert_id])),) for expert_id in ids}
        left = accumulate_f32(ids, terms)[0]
        permutation = tuple(int(value) for value in rng.permutation(ids))
        right = accumulate_f32(permutation, terms)[0]
        bound = accumulation_order_bound(terms)[0]
        difference = abs(left - right)
        if difference > bound:
            under_bounds += 1
        if left == right:
            bitwise_equal += 1
        maximum_ratio = max(maximum_ratio, difference / bound if bound else 0.0)
        maximum_difference = max(maximum_difference, difference)
        maximum_bound = max(maximum_bound, bound)
    return {
        "sample_count": sample_count,
        "seed": seed,
        "under_bound_count": under_bounds,
        "bitwise_equal_count": bitwise_equal,
        "maximum_observed_actual_to_bound_ratio": maximum_ratio,
        "maximum_observed_difference": maximum_difference,
        "maximum_bound": maximum_bound,
    }


def source_identities(root: Path) -> list[dict[str, object]]:
    classifications = {
        "crates/kernels/cuda/pulsar_kernels.cu": "NUMERICALLY_OBSERVABLE_RUNTIME_POLICY",
        "crates/engine/src/lib.rs": "NUMERICALLY_OBSERVABLE_RUNTIME_POLICY",
        "crates/backend/src/routing.rs": "NUMERICALLY_OBSERVABLE_RUNTIME_POLICY",
        "crates/f017-runner/src/layer_qualification.rs": "REFERENCE_MODEL_SEMANTICS",
        "scripts/research/generate_f017_r10_oracle.py": "REFERENCE_MODEL_SEMANTICS",
        "scripts/research/layer_stack_parity.py": "REFERENCE_MODEL_SEMANTICS",
    }
    return [
        {
            "path": path,
            "sha256": sha256_path(root / path),
            "classification": classification,
        }
        for path, classification in classifications.items()
    ]


def build_source_trace(root: Path) -> dict[str, object]:
    return {
        "schema": "pulsarmlx.f017.routing-v3-source-trace",
        "schema_version": "1.0.0",
        "checkpoint_access": 0,
        "classification": "ORDER_IS_NUMERICALLY_OBSERVABLE_NOT_MODEL_SEMANTIC",
        "source_identities": source_identities(root),
        "trace": [
            {"stage": "top_k", "behavior": "score descending; lower expert ID wins exact ties", "rank_class": "MODEL_SEMANTIC_SELECTION_PROCEDURE"},
            {"stage": "pair_transport", "behavior": "selected IDs, weights, and expert pointers share token/selected-slot indexing", "rank_class": "MODEL_SEMANTIC_ATOMIC_ASSOCIATION"},
            {"stage": "weight_construction", "behavior": "selected pre-bias sigmoid probabilities are sum-normalized, floored at 2^-14, and scaled by 2.5", "rank_class": "MODEL_SEMANTIC_BY_EXPERT"},
            {"stage": "weight_scaling", "behavior": "no rank-indexed scale; scale is common to all selected experts", "rank_class": "MODEL_SEMANTIC_BY_EXPERT"},
            {"stage": "storage_resolve", "behavior": "selected IDs are sorted/deduplicated only for storage and cache requests", "rank_class": "NUMERICALLY_INERT_RUNTIME_POLICY"},
            {"stage": "expert_execution", "behavior": "same-slot weight multiplies the same-slot expert activation; independent ID/weight permutation is forbidden", "rank_class": "MODEL_SEMANTIC_ATOMIC_ASSOCIATION"},
            {"stage": "routed_accumulation", "behavior": "current plain and grouped kernels reduce selected slots in slot/rank order", "rank_class": "NUMERICALLY_OBSERVABLE_RUNTIME_POLICY"},
            {"stage": "completion_and_tiers", "behavior": "device/CPU/tier partial joins can change f32 reduction grouping but not pair membership", "rank_class": "NUMERICALLY_OBSERVABLE_RUNTIME_POLICY"},
            {"stage": "shared_expert", "behavior": "computed independently from normalized input and added after routed accumulation", "rank_class": "MODEL_SEMANTIC_RANK_INDEPENDENT"},
            {"stage": "residual", "behavior": "attention residual is added after routed and shared branches", "rank_class": "MODEL_SEMANTIC_RANK_INDEPENDENT"},
            {"stage": "prefetch_and_cache", "behavior": "uses selected-ID membership and deduplicated IDs; rank is not a cache/capacity semantic", "rank_class": "NUMERICALLY_INERT_RUNTIME_POLICY"},
            {"stage": "evidence", "behavior": "rank-ordered IDs and weights remain retained diagnostics", "rank_class": "EVIDENCE_ONLY"},
        ],
        "unresolved_rank_dependence": [],
        "permutation_equivalence": "The exact mathematical contribution is invariant under any joint permutation of distinct atomic (expert_id, weight) pairs; f32 serial reductions may differ by order.",
        "forbidden_operation": "independent permutation of expert IDs or routing weights",
        "runtime_semantics_changed": False,
    }


def validate_source_trace(root: Path, trace: Mapping[str, object]) -> None:
    expected_patterns = {
        "crates/kernels/cuda/pulsar_kernels.cu": [
            "w[k] = best_prob", "mid[mid_off] = pulsar_glu", "for (uint32_t slot = 0; slot < n_used; slot++)",
        ],
        "crates/engine/src/lib.rs": [
            "distinct.sort_unstable();", "st.router_weights", "kernels::moe_down(",
        ],
        "crates/f017-runner/src/layer_qualification.rs": [
            "routing_weights[route]", "routed_experts[route]", "python_fsum",
        ],
    }
    for path, patterns in expected_patterns.items():
        text = (root / path).read_text()
        for pattern in patterns:
            if pattern not in text:
                raise ValueError(f"routing source trace drift: {path}: {pattern}")
    if trace.get("classification") != "ORDER_IS_NUMERICALLY_OBSERVABLE_NOT_MODEL_SEMANTIC":
        raise ValueError("unexpected semantic classification")
    if trace.get("unresolved_rank_dependence") != []:
        raise ValueError("unresolved rank dependence")


def _cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-trace", action="store_true")
    parser.add_argument("--stress", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    if args.source_trace:
        result: object = build_source_trace(root)
        validate_source_trace(root, result)
    elif args.stress:
        result = accumulation_stress(args.stress)
        if result["under_bound_count"] != 0:
            raise SystemExit("accumulation under-bound")
    else:
        raise SystemExit("choose --source-trace or --stress")
    payload = canonical_json_bytes(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
    else:
        print(payload.decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
