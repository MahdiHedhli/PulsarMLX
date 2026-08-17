#!/usr/bin/env python3
"""F017 routing-contract v3.1 synthetic state-box propagation theorem.

This module is deliberately value-agnostic.  It implements reusable binary64
interval arithmetic and the frozen GLM-5.2 routing map, but has no private
package loader, checkpoint reader, or production evaluation entry point.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping, Sequence


RMS_EPSILON = float.fromhex("0x1.4f8b580000000p-17")  # f32(1e-5)
EXPERT_COUNT = 256
TOP_K = 8
ROUTING_WEIGHT_SCALE = 2.5
DENOMINATOR_FLOOR = 2.0**-14


class TheoremDomainError(ValueError):
    """Fail-closed rejection of an input outside the v3.1 theorem domain."""


def _finite(value: float, label: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise TheoremDomainError(f"{label} must be finite")
    return value


def round_down(value: float) -> float:
    value = _finite(value, "outward-rounding input")
    return math.nextafter(value, -math.inf)


def round_up(value: float) -> float:
    value = _finite(value, "outward-rounding input")
    return math.nextafter(value, math.inf)


@dataclass(frozen=True)
class Interval:
    lower: float
    upper: float

    def __post_init__(self) -> None:
        lower = _finite(self.lower, "interval lower")
        upper = _finite(self.upper, "interval upper")
        if lower > upper:
            raise TheoremDomainError("interval lower exceeds upper")
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)

    def contains(self, value: float) -> bool:
        value = _finite(value, "contained value")
        return self.lower <= value <= self.upper


def interval_add(left: Interval, right: Interval) -> Interval:
    return Interval(round_down(left.lower + right.lower), round_up(left.upper + right.upper))


def interval_sub(left: Interval, right: Interval) -> Interval:
    return Interval(round_down(left.lower - right.upper), round_up(left.upper - right.lower))


def interval_mul(left: Interval, right: Interval) -> Interval:
    products = (
        left.lower * right.lower,
        left.lower * right.upper,
        left.upper * right.lower,
        left.upper * right.upper,
    )
    if not all(math.isfinite(value) for value in products):
        raise TheoremDomainError("interval multiplication overflow")
    return Interval(round_down(min(products)), round_up(max(products)))


def interval_div(left: Interval, right: Interval) -> Interval:
    if right.lower <= 0.0 <= right.upper:
        raise TheoremDomainError("interval division denominator crosses zero")
    quotients = (
        left.lower / right.lower,
        left.lower / right.upper,
        left.upper / right.lower,
        left.upper / right.upper,
    )
    if not all(math.isfinite(value) for value in quotients):
        raise TheoremDomainError("interval division overflow")
    return Interval(round_down(min(quotients)), round_up(max(quotients)))


def interval_sqrt(value: Interval) -> Interval:
    if value.lower < 0.0:
        raise TheoremDomainError("sqrt interval has a negative lower endpoint")
    lower = 0.0 if value.lower == 0.0 else max(0.0, round_down(math.sqrt(value.lower)))
    upper = round_up(math.sqrt(value.upper))
    return Interval(lower, upper)


def symmetric_interval(center: float, radius: float) -> Interval:
    center = _finite(center, "box center")
    radius = _finite(radius, "box radius")
    if radius < 0.0:
        raise TheoremDomainError("box radius must be non-negative")
    return Interval(round_down(center - radius), round_up(center + radius))


def square_interval(value: Interval) -> Interval:
    if value.lower <= 0.0 <= value.upper:
        lower = 0.0
    else:
        lower = max(0.0, round_down(min(value.lower * value.lower, value.upper * value.upper)))
    upper_raw = max(value.lower * value.lower, value.upper * value.upper)
    if not math.isfinite(upper_raw):
        raise TheoremDomainError("squared-coordinate overflow")
    return Interval(lower, round_up(upper_raw))


def _outward_sum(values: Iterable[Interval]) -> Interval:
    total = Interval(0.0, 0.0)
    seen = False
    for value in values:
        total = interval_add(total, value)
        seen = True
    if not seen:
        raise TheoremDomainError("empty interval reduction")
    return total


@dataclass(frozen=True)
class RmsNormEnclosure:
    coordinates: tuple[Interval, ...]
    squared_coordinates: tuple[Interval, ...]
    mean_square: Interval
    rms: Interval
    normalized: tuple[Interval, ...]
    gamma_scaled: tuple[Interval, ...]


def propagate_rmsnorm(
    x0: Sequence[float],
    dx: Sequence[float],
    gamma: Sequence[float],
    *,
    epsilon: float = RMS_EPSILON,
) -> RmsNormEnclosure:
    """Enclose ``gamma*x/sqrt(mean(x*x)+epsilon)`` for the whole input box."""

    if not x0 or len(x0) != len(dx) or len(x0) != len(gamma):
        raise TheoremDomainError("RMSNorm vectors must be non-empty and shape-aligned")
    epsilon = _finite(epsilon, "RMSNorm epsilon")
    if epsilon <= 0.0:
        raise TheoremDomainError("RMSNorm epsilon must be positive")
    coordinates = tuple(symmetric_interval(center, radius) for center, radius in zip(x0, dx, strict=True))
    squared = tuple(square_interval(value) for value in coordinates)
    summed = _outward_sum(squared)
    count = Interval(float(len(x0)), float(len(x0)))
    divided_mean = interval_div(summed, count)
    # The algebraic range of a mean of squares is non-negative.  Preserve
    # that exact domain fact after generic addition/division rounding.
    mean_square = Interval(max(0.0, divided_mean.lower), divided_mean.upper)
    radicand = interval_add(mean_square, Interval(epsilon, epsilon))
    rms = interval_sqrt(radicand)
    if rms.lower <= 0.0:
        raise TheoremDomainError("RMSNorm denominator lower bound is not positive")
    normalized = tuple(interval_div(value, rms) for value in coordinates)
    gamma_scaled = tuple(
        interval_mul(Interval(_finite(weight, "gamma"), _finite(weight, "gamma")), value)
        for weight, value in zip(gamma, normalized, strict=True)
    )
    return RmsNormEnclosure(coordinates, squared, mean_square, rms, normalized, gamma_scaled)


def _checked_guards(guards: Sequence[float] | None, rows: int, label: str) -> tuple[float, ...]:
    if guards is None or len(guards) != rows:
        raise TheoremDomainError(f"{label} must be explicit and row-aligned")
    checked = tuple(_finite(value, label) for value in guards)
    if any(value < 0.0 for value in checked):
        raise TheoremDomainError(f"{label} must be non-negative")
    return checked


def propagate_router_logits(
    normalized: Sequence[Interval],
    router_rows: Sequence[Sequence[float]],
    *,
    logit_bias: Sequence[float] | None,
    reduction_guards: Sequence[float] | None,
    import_guards: Sequence[float] | None,
    bias_guards: Sequence[float] | None,
) -> tuple[Interval, ...]:
    """Enclose every row of ``W @ y + logit_bias`` independently."""

    if not normalized or not router_rows or len(router_rows) > EXPERT_COUNT:
        raise TheoremDomainError("router matrix dimensions are invalid")
    rows = len(router_rows)
    reduction = _checked_guards(reduction_guards, rows, "reduction guards")
    imported = _checked_guards(import_guards, rows, "import guards")
    bias_error = _checked_guards(bias_guards, rows, "bias guards")
    if logit_bias is None:
        biases = (0.0,) * rows
    elif len(logit_bias) == rows:
        biases = tuple(_finite(value, "logit bias") for value in logit_bias)
    else:
        raise TheoremDomainError("logit bias must be row-aligned")

    outputs: list[Interval] = []
    for row_index, row in enumerate(router_rows):
        if len(row) != len(normalized):
            raise TheoremDomainError("router row width does not match normalized state")
        terms = (
            interval_mul(Interval(_finite(weight, "router weight"), float(weight)), value)
            for weight, value in zip(row, normalized, strict=True)
        )
        dot = _outward_sum(terms)
        bias_interval = symmetric_interval(biases[row_index], bias_error[row_index])
        guarded = interval_add(dot, bias_interval)
        total_guard = round_up(reduction[row_index] + imported[row_index])
        outputs.append(interval_add(guarded, Interval(-total_guard, total_guard)))
    return tuple(outputs)


def sigmoid(value: float) -> float:
    value = _finite(value, "sigmoid input")
    if value >= 0.0:
        exponential = math.exp(-value)
        return 1.0 / (1.0 + exponential)
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def sigmoid_interval(value: Interval) -> Interval:
    lower = max(0.0, round_down(sigmoid(value.lower)))
    upper = min(1.0, round_up(sigmoid(value.upper)))
    return Interval(lower, upper)


@dataclass(frozen=True)
class ScoreEnclosure:
    probabilities: tuple[Interval, ...]
    selection_scores: tuple[Interval, ...]


def propagate_scores(
    logits: Sequence[Interval],
    correction_bias: Sequence[float],
    *,
    score_bias_guards: Sequence[float] | None,
) -> ScoreEnclosure:
    """Apply sigmoid, then the GLM selection-only correction bias."""

    if not logits or len(logits) != len(correction_bias):
        raise TheoremDomainError("score inputs must be non-empty and row-aligned")
    guards = _checked_guards(score_bias_guards, len(logits), "score bias guards")
    probabilities = tuple(sigmoid_interval(value) for value in logits)
    scores = tuple(
        interval_add(probability, symmetric_interval(_finite(bias, "correction bias"), guard))
        for probability, bias, guard in zip(probabilities, correction_bias, guards, strict=True)
    )
    return ScoreEnclosure(probabilities, scores)


def selected_challenger_difference(selected: Interval, challenger: Interval) -> Interval:
    return interval_sub(selected, challenger)


@dataclass(frozen=True)
class PairSafety:
    selected_id: int
    challenger_id: int
    difference: Interval
    nominal_margin: float
    ambiguity_allowance: float
    factor: float | None
    membership_invariant: bool
    mathematical_factor_pass: bool
    engineering_h2_pass: bool


def pair_safety(
    selected_id: int,
    challenger_id: int,
    selected_score: Interval,
    challenger_score: Interval,
    nominal_selected_score: float,
    nominal_challenger_score: float,
) -> PairSafety:
    if selected_id == challenger_id or min(selected_id, challenger_id) < 0:
        raise TheoremDomainError("pair expert IDs must be distinct and non-negative")
    difference = selected_challenger_difference(selected_score, challenger_score)
    nominal_margin = round_down(
        _finite(nominal_selected_score, "nominal selected score")
        - _finite(nominal_challenger_score, "nominal challenger score")
    )
    if nominal_margin <= 0.0:
        allowance = round_up(max(0.0, nominal_margin - difference.lower))
        factor: float | None = 0.0
    else:
        allowance = round_up(max(0.0, nominal_margin - difference.lower))
        factor = None if allowance == 0.0 else max(0.0, round_down(nominal_margin / allowance))
    membership = difference.lower > 0.0
    factor_pass = factor is None or factor >= 1.0
    engineering = membership and (factor is None or factor >= 2.0)
    return PairSafety(
        selected_id,
        challenger_id,
        difference,
        nominal_margin,
        allowance,
        factor,
        membership,
        membership and factor_pass,
        engineering,
    )


def summarize_pair_safety(pairs: Sequence[PairSafety]) -> dict[str, object]:
    if not pairs:
        raise TheoremDomainError("pair-safety summary is empty")
    finite_factors = sorted(pair.factor for pair in pairs if pair.factor is not None)
    worst = min(
        pairs,
        key=lambda pair: (math.inf if pair.factor is None else pair.factor, pair.selected_id, pair.challenger_id),
    )
    median = None
    if finite_factors:
        middle = len(finite_factors) // 2
        median = (
            finite_factors[middle]
            if len(finite_factors) % 2
            else (finite_factors[middle - 1] + finite_factors[middle]) / 2.0
        )
    return {
        "minimum_safety_factor": "INFINITE" if worst.factor is None else worst.factor,
        "worst_pair": [worst.selected_id, worst.challenger_id],
        "count_below_1": sum(not pair.mathematical_factor_pass for pair in pairs),
        "count_below_2": sum(not pair.engineering_h2_pass for pair in pairs),
        "median_finite_safety_factor": median,
        "all_membership_invariant": all(pair.membership_invariant for pair in pairs),
    }


def selected_weight_intervals(
    selected_ids: Sequence[int],
    probabilities: Mapping[int, Interval],
    *,
    scale: float = ROUTING_WEIGHT_SCALE,
    denominator_floor: float = DENOMINATOR_FLOOR,
) -> dict[int, Interval]:
    """Enclose GLM ID-keyed weights after a fixed set is independently proven."""

    if len(selected_ids) != TOP_K or len(set(selected_ids)) != TOP_K:
        raise TheoremDomainError("selected expert IDs must contain eight unique IDs")
    scale = _finite(scale, "routing weight scale")
    floor = _finite(denominator_floor, "denominator floor")
    if scale <= 0.0 or floor <= 0.0:
        raise TheoremDomainError("weight scale and denominator floor must be positive")
    selected: dict[int, Interval] = {}
    for expert_id in selected_ids:
        if type(expert_id) is not int or not 0 <= expert_id < EXPERT_COUNT:
            raise TheoremDomainError("selected expert ID is outside [0,255]")
        try:
            value = probabilities[expert_id]
        except KeyError as error:
            raise TheoremDomainError("missing selected probability interval") from error
        if value.lower < 0.0 or value.upper > 1.0:
            raise TheoremDomainError("probability interval lies outside [0,1]")
        selected[expert_id] = value

    result: dict[int, Interval] = {}
    scale_interval = Interval(scale, scale)
    for expert_id, numerator in selected.items():
        other_intervals = [value for other_id, value in selected.items() if other_id != expert_id]
        other_sum = _outward_sum(other_intervals)
        denominator_for_lower = max(floor, round_up(numerator.lower + other_sum.upper))
        denominator_for_upper = max(floor, round_down(numerator.upper + other_sum.lower))
        if denominator_for_upper <= 0.0:
            raise TheoremDomainError("selected-weight denominator is not positive")
        lower = max(0.0, round_down(numerator.lower / denominator_for_lower))
        upper = round_up(numerator.upper / denominator_for_upper)
        result[expert_id] = interval_mul(Interval(lower, upper), scale_interval)
    return result


def select_top_k_diagnostic(scores: Sequence[float], *, top_k: int = TOP_K) -> tuple[int, ...]:
    """Nominal diagnostic ordering; v3.1 PASS depends on set membership, not rank."""

    if len(scores) > EXPERT_COUNT or not 0 < top_k <= len(scores):
        raise TheoremDomainError("top-k dimensions are invalid")
    checked = tuple(_finite(value, "selection score") for value in scores)
    return tuple(sorted(range(len(checked)), key=lambda expert_id: (-checked[expert_id], expert_id))[:top_k])
