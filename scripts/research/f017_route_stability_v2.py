#!/usr/bin/env python3
"""Checkpoint-free reference math for the F017 pairwise route bound candidate."""

from __future__ import annotations

import math
import importlib.util
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Iterable, Sequence

import numpy as np

U64 = 2.0 ** -53


def outward(value: float) -> float:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError("finite non-negative bound required")
    return math.nextafter(value, math.inf)


def sigmoid(value: float) -> float:
    if value >= 0.0:
        term = math.exp(-value)
        return 1.0 / (1.0 + term)
    term = math.exp(value)
    return term / (1.0 + term)


def sigmoid_prime(value: float) -> float:
    probability = sigmoid(value)
    return probability * (1.0 - probability)


def derivative_interval(low: float, high: float) -> tuple[float, float]:
    if not math.isfinite(low) or not math.isfinite(high) or low > high:
        raise ValueError("invalid sigmoid interval")
    endpoints = (sigmoid_prime(low), sigmoid_prime(high))
    maximum = 0.25 if low <= 0.0 <= high else max(endpoints)
    minimum = min(endpoints)
    return (max(0.0, math.nextafter(minimum, -math.inf)), outward(maximum))


def corner_abs(a: float, b: float, left: tuple[float, float], right: tuple[float, float]) -> float:
    return max(abs(x * a - y * b) for x in left for y in right)


@dataclass(frozen=True)
class PairwiseInputs:
    logit_i: float
    logit_j: float
    row_i: tuple[float, ...]
    row_j: tuple[float, ...]
    lambda_bound: float
    residual_bounds: tuple[float, ...]
    reduction_i: float
    reduction_j: float
    import_i: float = 0.0
    import_j: float = 0.0
    bias_i: float = 0.0
    bias_j: float = 0.0

    def validate(self) -> None:
        values = (
            self.logit_i, self.logit_j, self.lambda_bound, self.reduction_i,
            self.reduction_j, self.import_i, self.import_j, self.bias_i,
            self.bias_j, *self.row_i,
            *self.row_j, *self.residual_bounds,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("non-finite pairwise input")
        if len(self.row_i) != len(self.row_j) or len(self.row_i) != len(self.residual_bounds):
            raise ValueError("pairwise shape")
        if any(value < 0.0 for value in (
            self.lambda_bound, self.reduction_i, self.reduction_j,
            self.import_i, self.import_j, *self.residual_bounds,
        )):
            raise ValueError("negative pairwise bound")


def individual_logit_bound(logit: float, row: Sequence[float], value: PairwiseInputs, which: str) -> float:
    residual = math.fsum(abs(weight) * bound for weight, bound in zip(row, value.residual_bounds, strict=True))
    reduction = value.reduction_i if which == "i" else value.reduction_j
    materialization = value.import_i if which == "i" else value.import_j
    return outward(abs(logit) * value.lambda_bound + residual + reduction + materialization)


def final_addition_rounding_guard(logit: float, logit_error: float, bias: float) -> float:
    """One-ULP outward guard for one fl(sigmoid(logit)+bias) operation.

    Binary64 round-to-nearest has at most half-ULP error.  The contract uses a
    full ULP at the largest-magnitude endpoint, then rounds the bound outward.
    This remains conservative at zero, across cancellation, and for subnormal
    results.  A candidate-vs-oracle row difference contains two such additions.
    """
    probability_low = sigmoid(logit - logit_error)
    probability_high = sigmoid(logit + logit_error)
    score_low = probability_low + bias
    score_high = probability_high + bias
    if not math.isfinite(score_low) or not math.isfinite(score_high):
        raise ValueError("non-finite score interval")
    guard = max(math.ulp(score_low), math.ulp(score_high), math.ulp(0.0))
    return outward(guard)


def pairwise_bound_primary(value: PairwiseInputs) -> dict[str, float | tuple[float, float]]:
    """Mean-value interval bound retaining shared radial/residual variables."""
    value.validate()
    error_i = individual_logit_bound(value.logit_i, value.row_i, value, "i")
    error_j = individual_logit_bound(value.logit_j, value.row_j, value, "j")
    derivative_i = derivative_interval(value.logit_i - error_i, value.logit_i + error_i)
    derivative_j = derivative_interval(value.logit_j - error_j, value.logit_j + error_j)
    radial = outward(value.lambda_bound * corner_abs(
        value.logit_i, value.logit_j, derivative_i, derivative_j
    ))
    residual = 0.0
    for weight_i, weight_j, bound in zip(value.row_i, value.row_j, value.residual_bounds, strict=True):
        residual = outward(residual + bound * corner_abs(weight_i, weight_j, derivative_i, derivative_j))
    reduction = outward(derivative_i[1] * value.reduction_i + derivative_j[1] * value.reduction_j)
    materialization = outward(derivative_i[1] * value.import_i + derivative_j[1] * value.import_j)
    addition_rounding = outward(
        2.0 * final_addition_rounding_guard(value.logit_i, error_i, value.bias_i)
        + 2.0 * final_addition_rounding_guard(value.logit_j, error_j, value.bias_j)
    )
    accumulation_rounding = outward(8.0 * U64 * (
        abs(sigmoid(value.logit_i)) + abs(sigmoid(value.logit_j))
        + radial + residual + reduction + materialization
    ))
    total = 0.0
    for term in (radial, residual, reduction, materialization, addition_rounding, accumulation_rounding):
        total = outward(total + term)
    return {
        "B_pair": total,
        "radial": radial,
        "non_radial": residual,
        "router_reduction": reduction,
        "import_materialization": materialization,
        "bias_operand_perturbation": 0.0,
        "final_addition_rounding": addition_rounding,
        "bound_accumulation_rounding": accumulation_rounding,
        "logit_error_i": error_i,
        "logit_error_j": error_j,
        "derivative_interval_i": derivative_i,
        "derivative_interval_j": derivative_j,
    }


def pairwise_bound_scalar(value: PairwiseInputs) -> float:
    """Independent scalar structure for exact f64 parity checks."""
    value.validate()
    ei = outward(abs(value.logit_i) * value.lambda_bound + math.fsum(
        abs(value.row_i[k]) * value.residual_bounds[k] for k in range(len(value.row_i))
    ) + value.reduction_i + value.import_i)
    ej = outward(abs(value.logit_j) * value.lambda_bound + math.fsum(
        abs(value.row_j[k]) * value.residual_bounds[k] for k in range(len(value.row_j))
    ) + value.reduction_j + value.import_j)
    di = derivative_interval(value.logit_i - ei, value.logit_i + ei)
    dj = derivative_interval(value.logit_j - ej, value.logit_j + ej)
    terms = [outward(value.lambda_bound * max(
        abs(a * value.logit_i - b * value.logit_j) for a in di for b in dj
    ))]
    non_radial = 0.0
    for k in range(len(value.row_i)):
        coefficient = max(abs(a * value.row_i[k] - b * value.row_j[k]) for a in di for b in dj)
        non_radial = outward(non_radial + value.residual_bounds[k] * coefficient)
    terms.append(non_radial)
    terms.append(outward(di[1] * value.reduction_i + dj[1] * value.reduction_j))
    terms.append(outward(di[1] * value.import_i + dj[1] * value.import_j))
    addition_rounding = outward(
        2.0 * final_addition_rounding_guard(value.logit_i, ei, value.bias_i)
        + 2.0 * final_addition_rounding_guard(value.logit_j, ej, value.bias_j)
    )
    terms.append(addition_rounding)
    terms.append(outward(8.0 * U64 * (
        abs(sigmoid(value.logit_i)) + abs(sigmoid(value.logit_j))
        + sum(terms[:-1])
    )))
    total = 0.0
    for term in terms:
        total = outward(total + term)
    return total


def exact_pair_delta(value: PairwiseInputs, lam: float, residual: Sequence[float], rho_i: float, rho_j: float) -> float:
    before = (sigmoid(value.logit_i) + value.bias_i) - (sigmoid(value.logit_j) + value.bias_j)
    delta_i = lam * value.logit_i + math.fsum(w * r for w, r in zip(value.row_i, residual, strict=True)) + rho_i
    delta_j = lam * value.logit_j + math.fsum(w * r for w, r in zip(value.row_j, residual, strict=True)) + rho_j
    after = (sigmoid(value.logit_i + delta_i) + value.bias_i) - (sigmoid(value.logit_j + delta_j) + value.bias_j)
    return abs(after - before)


def full_set_stable(scores: Sequence[float], selected: Iterable[int], pair_bounds: dict[tuple[int, int], float]) -> tuple[bool, tuple[int, int] | None, float]:
    selected_set = set(selected)
    unselected = set(range(len(scores))) - selected_set
    minimum_factor = math.inf
    minimum_pair = None
    for i in selected_set:
        for j in unselected:
            bound = pair_bounds[(i, j)]
            margin = scores[i] - scores[j]
            factor = margin / bound if bound > 0.0 else math.inf
            if factor < minimum_factor:
                minimum_factor, minimum_pair = factor, (i, j)
            if not margin > bound:
                return False, (i, j), minimum_factor
    return True, minimum_pair, minimum_factor


def ordered_topk_stable(
    scores: Sequence[float],
    ordered_selected: Sequence[int],
    pair_bounds: dict[tuple[int, int], float],
) -> tuple[bool, tuple[int, int] | None, float, str]:
    """Prove top-k membership and normative rank-ordered byte stability.

    All selected/unselected pairs protect membership.  Every adjacent selected
    pair protects the oracle order; preservation of the adjacent strict chain
    preserves every non-adjacent relation by transitivity.  Exact ties fail the
    strict perturbation proof even when the lower-ID tie rule fixes oracle order.
    """
    if len(set(ordered_selected)) != len(ordered_selected):
        raise ValueError("duplicate selected expert")
    expected = sorted(ordered_selected, key=lambda item: (-scores[item], item))
    if list(ordered_selected) != expected:
        raise ValueError("selected order is not canonical")
    selected_set = set(ordered_selected)
    unselected = set(range(len(scores))) - selected_set
    minimum_factor = math.inf
    minimum_pair = None
    for relation, pairs in (
        ("membership", ((i, j) for i in ordered_selected for j in unselected)),
        ("ordered_selected", zip(ordered_selected, ordered_selected[1:])),
    ):
        for i, j in pairs:
            if (i, j) not in pair_bounds:
                raise ValueError(f"missing pairwise bound {(i, j)}")
            bound = pair_bounds[(i, j)]
            if not math.isfinite(bound) or bound < 0.0:
                raise ValueError("invalid pairwise bound")
            margin = scores[i] - scores[j]
            factor = margin / bound if bound > 0.0 else (math.inf if margin > 0.0 else 0.0)
            if factor < minimum_factor:
                minimum_factor, minimum_pair = factor, (i, j)
            if not margin > bound:
                return False, (i, j), minimum_factor, relation
    return True, minimum_pair, minimum_factor, "complete"


def high_precision_sigmoid(value: float) -> Decimal:
    with localcontext() as context:
        context.prec = 80
        item = Decimal.from_float(value)
        return Decimal(1) / (Decimal(1) + (-item).exp())


def stress(sample_count: int = 100_000, seed: int = 170_185_001) -> dict[str, float | int]:
    scalar_path = __import__("pathlib").Path(__file__).with_name("f017_route_stability_v2_scalar.py")
    scalar_spec = importlib.util.spec_from_file_location("f017_route_stability_v2_scalar_stress", scalar_path)
    if scalar_spec is None or scalar_spec.loader is None:
        raise RuntimeError(scalar_path)
    scalar_module = importlib.util.module_from_spec(scalar_spec)
    scalar_spec.loader.exec_module(scalar_module)
    rng = np.random.Generator(np.random.PCG64(seed))
    under_bounds = 0
    parity_mismatches = 0
    maximum_ratio = 0.0
    maximum_final_addition_rounding = 0.0
    maximum_final_addition_fraction = 0.0
    for _ in range(sample_count):
        width = 8
        logit_i, logit_j = rng.uniform(-12.0, 12.0, size=2)
        row_i = tuple(float(x) for x in rng.normal(0.0, 1.0, size=width))
        mode = int(rng.integers(0, 4))
        if mode == 0:
            row_j = row_i
        elif mode == 1:
            row_j = tuple(-x for x in row_i)
        else:
            row_j = tuple(float(x) for x in rng.normal(0.0, 1.0, size=width))
        residual_bounds = tuple(float(x) for x in rng.uniform(0.0, 2e-3, size=width))
        value = PairwiseInputs(
            float(logit_i), float(logit_j), row_i, row_j,
            float(rng.uniform(0.0, 2e-3)), residual_bounds,
            float(rng.uniform(0.0, 2e-4)), float(rng.uniform(0.0, 2e-4)),
            float(rng.uniform(0.0, 1e-5)), float(rng.uniform(0.0, 1e-5)),
            float(rng.uniform(-64.0, 64.0)), float(rng.uniform(-64.0, 64.0)),
        )
        primary_result = pairwise_bound_primary(value)
        primary = float(primary_result["B_pair"])
        addition_rounding = float(primary_result["final_addition_rounding"])
        maximum_final_addition_rounding = max(maximum_final_addition_rounding, addition_rounding)
        maximum_final_addition_fraction = max(
            maximum_final_addition_fraction,
            addition_rounding / primary if primary else 0.0,
        )
        scalar = scalar_module.calculate(value.__dict__)
        if primary != scalar:
            parity_mismatches += 1
        lam = float(rng.uniform(-value.lambda_bound, value.lambda_bound))
        residual = [float(rng.uniform(-bound, bound)) for bound in residual_bounds]
        rho_i = float(rng.uniform(-(value.reduction_i + value.import_i), value.reduction_i + value.import_i))
        rho_j = float(rng.uniform(-(value.reduction_j + value.import_j), value.reduction_j + value.import_j))
        actual = exact_pair_delta(value, lam, residual, rho_i, rho_j)
        if actual > primary:
            under_bounds += 1
        maximum_ratio = max(maximum_ratio, actual / primary if primary else 0.0)
    return {
        "sample_count": sample_count,
        "seed": seed,
        "under_bound_count": under_bounds,
        "independent_implementation_mismatches": parity_mismatches,
        "maximum_observed_actual_to_bound_ratio": maximum_ratio,
        "maximum_final_addition_rounding": maximum_final_addition_rounding,
        "maximum_final_addition_fraction_of_bound": maximum_final_addition_fraction,
    }
