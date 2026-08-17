#!/usr/bin/env python3
"""Synthetic-only F017 weighted-MoE aggregate perturbation theorem.

The module deliberately has no filesystem, package, checkpoint, or production
evidence loader.  It encloses the f64 routed aggregate
``M = sum_i(q_i * e_i)`` for eight fixed expert IDs using binary64 directed-
outward interval arithmetic.  Real expert outputs are inputs to a later,
separately authorized evaluation, never to this theorem freeze.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Mapping, Sequence

from scripts.research import f017_routing_contract_v31 as v31


SELECTED_EXPERT_COUNT = 8
ROUTED_AGGREGATE_DIMENSION = 6144
R10_INTERMEDIATE_MAX_ABSOLUTE_ERROR = 0.015625
R10_INTERMEDIATE_RMSE = 0.0078125
R10_INTERMEDIATE_COSINE_MINIMUM = 0.9999
ENGINEERING_HEADROOM = 2.0


class AggregateTheoremError(ValueError):
    """Fail-closed rejection outside the theorem's declared domain."""


def _finite(value: float, label: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise AggregateTheoremError(f"{label} must be finite")
    return value


def _point(value: float, label: str = "point") -> v31.Interval:
    value = _finite(value, label)
    return v31.Interval(value, value)


def _sum_intervals(values: Sequence[v31.Interval]) -> v31.Interval:
    if not values:
        raise AggregateTheoremError("empty interval reduction")
    total = v31.Interval(0.0, 0.0)
    for value in values:
        total = v31.interval_add(total, value)
    return total


def _intersect(left: v31.Interval, right: v31.Interval) -> v31.Interval:
    lower = max(left.lower, right.lower)
    upper = min(left.upper, right.upper)
    if lower > upper:
        raise AggregateTheoremError("independent sound enclosures do not intersect")
    return v31.Interval(lower, upper)


def _square(value: v31.Interval) -> v31.Interval:
    return v31.square_interval(value)


def _radius(value: v31.Interval) -> float:
    return v31.round_up(max(abs(value.lower), abs(value.upper)))


def _ratio_factor(budget: float, bound: float) -> float:
    budget = _finite(budget, "budget")
    bound = _finite(bound, "bound")
    if budget <= 0.0 or bound < 0.0:
        raise AggregateTheoremError("safety-factor inputs are outside domain")
    if bound == 0.0:
        return math.inf
    quotient = budget / bound
    return math.inf if math.isinf(quotient) else v31.round_down(quotient)


@dataclass(frozen=True)
class AggregateInterval:
    lower: float
    upper: float

    @property
    def width(self) -> float:
        return self.upper - self.lower

    def contains(self, value: float) -> bool:
        value = _finite(value, "contained value")
        return self.lower <= value <= self.upper


def _public_interval(value: v31.Interval) -> AggregateInterval:
    return AggregateInterval(value.lower, value.upper)


@dataclass(frozen=True)
class ComponentEnclosure:
    index: int
    nominal: float
    direct: AggregateInterval
    centered: AggregateInterval
    enclosure: AggregateInterval
    radius: float
    reference: float
    centered_deviation_radius: float
    centered_common_mode_radius: float
    nominal_output_uncertainty_radius: float


@dataclass(frozen=True)
class AggregateQualification:
    expert_ids: tuple[int, ...]
    expert_count: int
    dimension: int
    component_bounds: tuple[ComponentEnclosure, ...]
    max_absolute_bound: float
    rmse_bound: float
    cosine_lower_bound: float | None
    max_absolute_factor: float
    rmse_factor: float
    cosine_factor: float | None
    aggregate_safety_factor: float
    mathematically_qualified: bool
    engineering_h2: bool
    joint_weight_sum_interval: AggregateInterval
    output_uncertainty_mode: str


def _validate_ids(expert_ids: Sequence[int]) -> tuple[int, ...]:
    ids = tuple(expert_ids)
    if len(ids) != SELECTED_EXPERT_COUNT or len(set(ids)) != SELECTED_EXPERT_COUNT:
        raise AggregateTheoremError("exactly eight unique selected expert IDs are required")
    if any(not isinstance(expert_id, int) or expert_id < 0 for expert_id in ids):
        raise AggregateTheoremError("expert IDs must be non-negative integers")
    return ids


def _keys_exact(mapping: Mapping[int, object], ids: tuple[int, ...], label: str) -> None:
    if set(mapping) != set(ids):
        raise AggregateTheoremError(f"{label} must be exactly ID-keyed to the selected set")


def _cosine_lower(
    nominal: Sequence[float],
    delta: Sequence[v31.Interval],
) -> float | None:
    aggregate = tuple(
        v31.interval_add(_point(value, "nominal aggregate"), perturbation)
        for value, perturbation in zip(nominal, delta, strict=True)
    )
    nominal_norm_squared = _sum_intervals(
        tuple(_square(_point(value, "nominal aggregate")) for value in nominal)
    )
    aggregate_norm_squared = _sum_intervals(tuple(_square(value) for value in aggregate))
    nominal_norm = v31.interval_sqrt(
        v31.Interval(max(0.0, nominal_norm_squared.lower), nominal_norm_squared.upper)
    )
    aggregate_norm = v31.interval_sqrt(
        v31.Interval(max(0.0, aggregate_norm_squared.lower), aggregate_norm_squared.upper)
    )
    if nominal_norm.lower <= 0.0 or aggregate_norm.lower <= 0.0:
        return None
    dot = _sum_intervals(
        tuple(
            v31.interval_mul(_point(value, "nominal aggregate"), admissible)
            for value, admissible in zip(nominal, aggregate, strict=True)
        )
    )
    denominator = v31.round_up(nominal_norm.upper * aggregate_norm.upper)
    if denominator <= 0.0 or not math.isfinite(denominator):
        return None
    lower = v31.round_down(dot.lower / denominator)
    return max(-1.0, min(1.0, lower))


def qualify_weighted_aggregate(
    expert_ids: Sequence[int],
    nominal_weights: Mapping[int, float],
    weight_intervals: Mapping[int, v31.Interval],
    nominal_outputs: Mapping[int, Sequence[float]],
    *,
    output_intervals: Mapping[int, Sequence[v31.Interval]] | None = None,
    joint_weight_sum_interval: v31.Interval | None = None,
) -> AggregateQualification:
    """Enclose weight-only or joint weight/output aggregate perturbation.

    Two independently sound enclosures are formed for every coordinate:

    * direct: ``sum(q_i*e_i) - sum(q0_i*e0_i)``;
    * normalization-centered, for a deterministic mid-hull reference ``c``:
      ``sum(dq_i*(e_i-c)) + sum(q0_i*(e_i-e0_i)) + c*sum(dq_i)``.

    Their intersection is sound and exploits the supplied joint shared-
    denominator sum enclosure without assuming endpoint cancellation.
    """

    ids = _validate_ids(expert_ids)
    for mapping, label in (
        (nominal_weights, "nominal weights"),
        (weight_intervals, "weight intervals"),
        (nominal_outputs, "nominal outputs"),
    ):
        _keys_exact(mapping, ids, label)
    if joint_weight_sum_interval is None:
        raise AggregateTheoremError("joint selected-weight sum enclosure is required")
    if output_intervals is not None:
        _keys_exact(output_intervals, ids, "expert-output intervals")

    checked_weights: dict[int, float] = {}
    checked_weight_intervals: dict[int, v31.Interval] = {}
    checked_outputs: dict[int, tuple[float, ...]] = {}
    checked_output_intervals: dict[int, tuple[v31.Interval, ...]] = {}
    dimension: int | None = None
    for expert_id in ids:
        q0 = _finite(nominal_weights[expert_id], "nominal routing weight")
        q_interval = weight_intervals[expert_id]
        if q0 <= 0.0 or q_interval.lower <= 0.0 or not q_interval.contains(q0):
            raise AggregateTheoremError("routing-weight interval must be positive and contain nominal")
        row = tuple(_finite(value, "nominal expert output") for value in nominal_outputs[expert_id])
        if not row:
            raise AggregateTheoremError("expert-output vectors must be non-empty")
        if dimension is None:
            dimension = len(row)
        elif len(row) != dimension:
            raise AggregateTheoremError("expert-output vector dimensions must align")
        if output_intervals is None:
            row_intervals = tuple(_point(value, "nominal expert output") for value in row)
        else:
            supplied = tuple(output_intervals[expert_id])
            if len(supplied) != len(row):
                raise AggregateTheoremError("expert-output interval dimensions must align")
            if any(not interval.contains(value) for value, interval in zip(row, supplied, strict=True)):
                raise AggregateTheoremError("expert-output interval must contain nominal output")
            row_intervals = supplied
        checked_weights[expert_id] = q0
        checked_weight_intervals[expert_id] = q_interval
        checked_outputs[expert_id] = row
        checked_output_intervals[expert_id] = row_intervals

    assert dimension is not None
    nominal_weight_sum = math.fsum(checked_weights.values())
    if not joint_weight_sum_interval.contains(nominal_weight_sum):
        raise AggregateTheoremError("joint selected-weight sum does not contain nominal sum")
    joint_delta_sum = v31.interval_sub(
        joint_weight_sum_interval,
        _point(nominal_weight_sum, "nominal selected-weight sum"),
    )
    zero_uncertainty = (
        joint_weight_sum_interval.lower == nominal_weight_sum
        and joint_weight_sum_interval.upper == nominal_weight_sum
        and all(
            checked_weight_intervals[expert_id].lower == checked_weights[expert_id]
            and checked_weight_intervals[expert_id].upper == checked_weights[expert_id]
            and all(
                interval.lower == nominal and interval.upper == nominal
                for interval, nominal in zip(
                    checked_output_intervals[expert_id],
                    checked_outputs[expert_id],
                    strict=True,
                )
            )
            for expert_id in ids
        )
    )

    components: list[ComponentEnclosure] = []
    internal_enclosures: list[v31.Interval] = []
    nominal_aggregate: list[float] = []
    for column in range(dimension):
        nominal = math.fsum(
            checked_weights[expert_id] * checked_outputs[expert_id][column]
            for expert_id in ids
        )
        nominal = _finite(nominal, "nominal routed aggregate")
        nominal_aggregate.append(nominal)

        direct_total = _sum_intervals(
            tuple(
                v31.interval_mul(
                    checked_weight_intervals[expert_id],
                    checked_output_intervals[expert_id][column],
                )
                for expert_id in ids
            )
        )
        direct = v31.interval_sub(direct_total, _point(nominal, "nominal aggregate"))

        hull_lower = min(checked_output_intervals[expert_id][column].lower for expert_id in ids)
        hull_upper = max(checked_output_intervals[expert_id][column].upper for expert_id in ids)
        reference = _finite((hull_lower + hull_upper) / 2.0, "centering reference")
        if zero_uncertainty:
            exact_zero = v31.Interval(0.0, 0.0)
            internal_enclosures.append(exact_zero)
            components.append(
                ComponentEnclosure(
                    index=column,
                    nominal=nominal,
                    direct=_public_interval(exact_zero),
                    centered=_public_interval(exact_zero),
                    enclosure=_public_interval(exact_zero),
                    radius=0.0,
                    reference=reference,
                    centered_deviation_radius=0.0,
                    centered_common_mode_radius=0.0,
                    nominal_output_uncertainty_radius=0.0,
                )
            )
            continue
        deviation_terms: list[v31.Interval] = []
        nominal_output_terms: list[v31.Interval] = []
        for expert_id in ids:
            delta_weight = v31.interval_sub(
                checked_weight_intervals[expert_id],
                _point(checked_weights[expert_id], "nominal routing weight"),
            )
            centered_output = v31.interval_sub(
                checked_output_intervals[expert_id][column],
                _point(reference, "centering reference"),
            )
            output_delta = v31.interval_sub(
                checked_output_intervals[expert_id][column],
                _point(checked_outputs[expert_id][column], "nominal expert output"),
            )
            deviation_terms.append(v31.interval_mul(delta_weight, centered_output))
            nominal_output_terms.append(
                v31.interval_mul(_point(checked_weights[expert_id], "nominal routing weight"), output_delta)
            )
        deviation = _sum_intervals(tuple(deviation_terms))
        nominal_output_uncertainty = _sum_intervals(tuple(nominal_output_terms))
        common_mode = v31.interval_mul(_point(reference, "centering reference"), joint_delta_sum)
        centered = v31.interval_add(
            v31.interval_add(deviation, nominal_output_uncertainty),
            common_mode,
        )
        enclosure = _intersect(direct, centered)
        internal_enclosures.append(enclosure)
        components.append(
            ComponentEnclosure(
                index=column,
                nominal=nominal,
                direct=_public_interval(direct),
                centered=_public_interval(centered),
                enclosure=_public_interval(enclosure),
                radius=_radius(enclosure),
                reference=reference,
                centered_deviation_radius=_radius(deviation),
                centered_common_mode_radius=_radius(common_mode),
                nominal_output_uncertainty_radius=_radius(nominal_output_uncertainty),
            )
        )

    if zero_uncertainty:
        max_absolute = 0.0
        rmse = 0.0
    else:
        max_absolute = v31.round_up(max(component.radius for component in components))
        squared_radii = tuple(_square(_point(component.radius, "component radius")) for component in components)
        mean_squared_raw = v31.interval_div(
            _sum_intervals(squared_radii),
            _point(float(dimension), "aggregate dimension"),
        )
        mean_squared = v31.Interval(max(0.0, mean_squared_raw.lower), mean_squared_raw.upper)
        rmse = v31.interval_sqrt(mean_squared).upper
    cosine_lower = (
        1.0
        if zero_uncertainty and any(value != 0.0 for value in nominal_aggregate)
        else _cosine_lower(nominal_aggregate, internal_enclosures)
    )

    max_factor = _ratio_factor(R10_INTERMEDIATE_MAX_ABSOLUTE_ERROR, max_absolute)
    rmse_factor = _ratio_factor(R10_INTERMEDIATE_RMSE, rmse)
    if cosine_lower is None:
        cosine_factor = None
        aggregate_factor = min(max_factor, rmse_factor)
        mathematical = False
    else:
        cosine_loss = 0.0 if cosine_lower == 1.0 else max(0.0, v31.round_up(1.0 - cosine_lower))
        cosine_factor = _ratio_factor(1.0 - R10_INTERMEDIATE_COSINE_MINIMUM, cosine_loss)
        aggregate_factor = min(max_factor, rmse_factor, cosine_factor)
        mathematical = aggregate_factor >= 1.0
    engineering = mathematical and aggregate_factor >= ENGINEERING_HEADROOM

    return AggregateQualification(
        expert_ids=ids,
        expert_count=len(ids),
        dimension=dimension,
        component_bounds=tuple(components),
        max_absolute_bound=max_absolute,
        rmse_bound=rmse,
        cosine_lower_bound=cosine_lower,
        max_absolute_factor=max_factor,
        rmse_factor=rmse_factor,
        cosine_factor=cosine_factor,
        aggregate_safety_factor=aggregate_factor,
        mathematically_qualified=mathematical,
        engineering_h2=engineering,
        joint_weight_sum_interval=_public_interval(joint_weight_sum_interval),
        output_uncertainty_mode="WEIGHT_ONLY" if output_intervals is None else "JOINT_WEIGHT_AND_OUTPUT",
    )


def qualify_f017_production_aggregate(
    expert_ids: Sequence[int],
    nominal_weights: Mapping[int, float],
    weight_intervals: Mapping[int, v31.Interval],
    nominal_outputs: Mapping[int, Sequence[float]],
    *,
    selected_set_invariant: bool,
    output_intervals: Mapping[int, Sequence[v31.Interval]] | None = None,
    joint_weight_sum_interval: v31.Interval | None = None,
) -> AggregateQualification:
    """Apply the generic theorem with F017 production shape/authority gates."""

    if selected_set_invariant is not True:
        raise AggregateTheoremError("selected-set invariance is a production precondition")
    result = qualify_weighted_aggregate(
        expert_ids,
        nominal_weights,
        weight_intervals,
        nominal_outputs,
        output_intervals=output_intervals,
        joint_weight_sum_interval=joint_weight_sum_interval,
    )
    if result.dimension != ROUTED_AGGREGATE_DIMENSION:
        raise AggregateTheoremError("F017 routed-aggregate dimension must be 6144")
    return result


def result_to_dict(result: AggregateQualification) -> dict[str, object]:
    def interval(value: AggregateInterval) -> dict[str, float]:
        return {"lower": value.lower, "upper": value.upper}

    def factor(value: float | None) -> float | str | None:
        if value is None:
            return None
        return "INFINITY" if math.isinf(value) else value

    return {
        "expert_ids": list(result.expert_ids),
        "expert_count": result.expert_count,
        "dimension": result.dimension,
        "component_bounds": [
            {
                "index": item.index,
                "nominal": item.nominal,
                "direct": interval(item.direct),
                "centered": interval(item.centered),
                "enclosure": interval(item.enclosure),
                "radius": item.radius,
                "reference": item.reference,
                "centered_deviation_radius": item.centered_deviation_radius,
                "centered_common_mode_radius": item.centered_common_mode_radius,
                "nominal_output_uncertainty_radius": item.nominal_output_uncertainty_radius,
            }
            for item in result.component_bounds
        ],
        "max_absolute_bound": result.max_absolute_bound,
        "rmse_bound": result.rmse_bound,
        "cosine_lower_bound": result.cosine_lower_bound,
        "max_absolute_factor": factor(result.max_absolute_factor),
        "rmse_factor": factor(result.rmse_factor),
        "cosine_factor": factor(result.cosine_factor),
        "aggregate_safety_factor": factor(result.aggregate_safety_factor),
        "mathematically_qualified": result.mathematically_qualified,
        "engineering_h2": result.engineering_h2,
        "joint_weight_sum_interval": interval(result.joint_weight_sum_interval),
        "output_uncertainty_mode": result.output_uncertainty_mode,
    }


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
