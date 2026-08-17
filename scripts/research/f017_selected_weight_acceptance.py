#!/usr/bin/env python3
"""Synthetic-only selected-routing-weight interval acceptance for F017.

This module freezes how a v3.1 ID-keyed weight enclosure is judged.  It has no
file loader, no production evidence parser, and no checkpoint or model entry
point.  The inherited R10 coefficient error budget is applied to the whole
enclosure, not merely to one observed candidate value.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Mapping, Sequence

from scripts.research import f017_routing_contract_v31 as v31


TOP_K = v31.TOP_K
EXPERT_COUNT = v31.EXPERT_COUNT
ROUTING_WEIGHT_SCALE = v31.ROUTING_WEIGHT_SCALE
DENOMINATOR_FLOOR = v31.DENOMINATOR_FLOOR
R10_ROUTING_WEIGHT_MAX_ABSOLUTE_ERROR = 1.0e-5
ENGINEERING_HEADROOM = 2.0
ENGINEERING_ROUTING_WEIGHT_MAX_ABSOLUTE_ERROR = (
    R10_ROUTING_WEIGHT_MAX_ABSOLUTE_ERROR / ENGINEERING_HEADROOM
)


class WeightQualificationError(ValueError):
    """Fail-closed rejection outside the frozen weight-acceptance domain."""


@dataclass(frozen=True, slots=True)
class PerExpertQualification:
    expert_id: int
    nominal_weight: float
    interval: v31.Interval
    outward_absolute_radius: float
    relative_radius: float
    mathematically_qualified: bool
    engineering_h2: bool


@dataclass(frozen=True, slots=True)
class SelectedWeightQualification:
    by_expert_id: dict[int, PerExpertQualification]
    probability_sum_interval: v31.Interval
    nominal_probability_sum: float
    joint_weight_sum_interval: v31.Interval
    nominal_weight_sum: float
    denominator_floor_status: str
    joint_normalization_valid: bool
    mathematically_qualified: bool
    engineering_h2: bool
    failed_mathematical_ids: tuple[int, ...]
    failed_engineering_ids: tuple[int, ...]


def _finite(value: float, label: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise WeightQualificationError(f"{label} must be finite")
    return value


def _selected_ids(selected_ids: Sequence[int]) -> tuple[int, ...]:
    result = tuple(selected_ids)
    if len(result) != TOP_K or len(set(result)) != TOP_K:
        raise WeightQualificationError("selected set must contain eight unique expert IDs")
    if any(type(expert_id) is not int or not 0 <= expert_id < EXPERT_COUNT for expert_id in result):
        raise WeightQualificationError("selected expert ID outside [0,255]")
    return result


def _exact_mapping_keys(values: Mapping[int, object], selected_ids: Sequence[int], label: str) -> None:
    if set(values) != set(selected_ids):
        raise WeightQualificationError(f"{label} must be keyed by exactly the selected expert IDs")


def _probability_sum_interval(probabilities: Mapping[int, v31.Interval], selected_ids: Sequence[int]) -> v31.Interval:
    total = v31.Interval(0.0, 0.0)
    for expert_id in selected_ids:
        total = v31.interval_add(total, probabilities[expert_id])
    return v31.Interval(max(0.0, total.lower), total.upper)


def _scaled_normalization_sum(value: float, *, upward: bool) -> float:
    value = _finite(value, "selected probability sum")
    if value < 0.0:
        raise WeightQualificationError("selected probability sum must be non-negative")
    if value == 0.0:
        return 0.0
    raw = ROUTING_WEIGHT_SCALE * value / max(value, DENOMINATOR_FLOOR)
    return v31.round_up(raw) if upward else max(0.0, v31.round_down(raw))


def joint_weight_sum_enclosure(probability_sum: v31.Interval) -> tuple[v31.Interval, str]:
    """Dependency-aware enclosure of ``2.5*P/max(P,2^-14)``.

    This avoids summing eight independently extremized weight intervals.  The
    shared selected-probability denominator makes the semantic sum a monotone
    scalar function of the common probability sum ``P``.
    """

    if probability_sum.lower < 0.0:
        raise WeightQualificationError("probability sum interval is negative")
    if probability_sum.upper < DENOMINATOR_FLOOR:
        status = "ACTIVE_FOR_ENTIRE_BOX"
    elif probability_sum.lower > DENOMINATOR_FLOOR:
        status = "INACTIVE_FOR_ENTIRE_BOX"
    else:
        status = "TRANSITION_WITHIN_BOX"
    if status == "INACTIVE_FOR_ENTIRE_BOX":
        # Algebraically, the common probability sum cancels exactly.  Retain
        # one outward representable neighbor for transport of the scalar sum.
        return (
            v31.Interval(
                v31.round_down(ROUTING_WEIGHT_SCALE),
                v31.round_up(ROUTING_WEIGHT_SCALE),
            ),
            status,
        )
    return (
        v31.Interval(
            _scaled_normalization_sum(probability_sum.lower, upward=False),
            _scaled_normalization_sum(probability_sum.upper, upward=True),
        ),
        status,
    )


def qualify_weight_enclosures(
    selected_ids: Sequence[int],
    nominal_weights: Mapping[int, float],
    intervals: Mapping[int, v31.Interval],
    *,
    nominal_probability_sum: float,
    probability_sum_interval: v31.Interval,
    selected_set_invariant: bool,
) -> SelectedWeightQualification:
    """Apply the frozen acceptance rule to already-derived v3.1 enclosures.

    Production evidence must additionally bind these enclosures to the frozen
    v3.1 derivation.  This pure function exists so the acceptance rule can be
    tested without any production values.
    """

    ids = _selected_ids(selected_ids)
    if selected_set_invariant is not True:
        raise WeightQualificationError("selected-set invariance must be independently proven")
    _exact_mapping_keys(nominal_weights, ids, "nominal weights")
    _exact_mapping_keys(intervals, ids, "weight intervals")
    nominal_probability_sum = _finite(nominal_probability_sum, "nominal probability sum")
    if nominal_probability_sum < 0.0 or not probability_sum_interval.contains(nominal_probability_sum):
        raise WeightQualificationError("nominal probability sum is outside its enclosure")

    by_id: dict[int, PerExpertQualification] = {}
    for expert_id in sorted(ids):
        nominal = _finite(nominal_weights[expert_id], "nominal routing weight")
        interval = intervals[expert_id]
        if not isinstance(interval, v31.Interval):
            raise WeightQualificationError("weight enclosure must use the frozen v3.1 interval type")
        if nominal <= 0.0 or interval.lower <= 0.0:
            raise WeightQualificationError("selected routing weights must remain strictly positive")
        if not interval.contains(nominal):
            raise WeightQualificationError("weight enclosure does not contain its nominal ID-keyed weight")
        radius = v31.round_up(max(nominal - interval.lower, interval.upper - nominal))
        relative = v31.round_up(radius / abs(nominal))
        mathematical = radius <= R10_ROUTING_WEIGHT_MAX_ABSOLUTE_ERROR
        engineering = mathematical and radius <= ENGINEERING_ROUTING_WEIGHT_MAX_ABSOLUTE_ERROR
        by_id[expert_id] = PerExpertQualification(
            expert_id,
            nominal,
            interval,
            radius,
            relative,
            mathematical,
            engineering,
        )

    joint_sum, floor_status = joint_weight_sum_enclosure(probability_sum_interval)
    nominal_weight_sum = math.fsum(item.nominal_weight for item in by_id.values())
    if not math.isfinite(nominal_weight_sum):
        raise WeightQualificationError("nominal selected-weight sum is non-finite")
    joint_valid = joint_sum.contains(nominal_weight_sum)
    if not joint_valid:
        raise WeightQualificationError("nominal selected-weight sum violates shared-denominator semantics")

    failed_mathematical = tuple(
        expert_id for expert_id, item in by_id.items() if not item.mathematically_qualified
    )
    failed_engineering = tuple(expert_id for expert_id, item in by_id.items() if not item.engineering_h2)
    mathematical = joint_valid and not failed_mathematical
    engineering = mathematical and not failed_engineering
    return SelectedWeightQualification(
        by_id,
        probability_sum_interval,
        nominal_probability_sum,
        joint_sum,
        nominal_weight_sum,
        floor_status,
        joint_valid,
        mathematical,
        engineering,
        failed_mathematical,
        failed_engineering,
    )


def qualify_probability_box(
    selected_ids: Sequence[int],
    nominal_probabilities: Mapping[int, float],
    probability_intervals: Mapping[int, v31.Interval],
    *,
    selected_set_invariant: bool,
) -> SelectedWeightQualification:
    """Derive v3.1 weights from a synthetic probability box and qualify them."""

    ids = _selected_ids(selected_ids)
    _exact_mapping_keys(nominal_probabilities, ids, "nominal probabilities")
    _exact_mapping_keys(probability_intervals, ids, "probability intervals")
    checked_nominal: dict[int, float] = {}
    for expert_id in ids:
        nominal = _finite(nominal_probabilities[expert_id], "nominal probability")
        interval = probability_intervals[expert_id]
        if not isinstance(interval, v31.Interval):
            raise WeightQualificationError("probability enclosure must use the frozen v3.1 interval type")
        if interval.lower < 0.0 or interval.upper > 1.0:
            raise WeightQualificationError("probability enclosure lies outside [0,1]")
        if not interval.contains(nominal):
            raise WeightQualificationError("probability enclosure does not contain its nominal value")
        checked_nominal[expert_id] = nominal

    nominal_probability_sum = math.fsum(checked_nominal[expert_id] for expert_id in ids)
    denominator = max(nominal_probability_sum, DENOMINATOR_FLOOR)
    if denominator <= 0.0 or not math.isfinite(denominator):
        raise WeightQualificationError("nominal routing denominator is invalid")
    nominal_weights = {
        expert_id: ROUTING_WEIGHT_SCALE * checked_nominal[expert_id] / denominator
        for expert_id in ids
    }
    derived = v31.selected_weight_intervals(ids, probability_intervals)
    probability_sum = _probability_sum_interval(probability_intervals, ids)
    return qualify_weight_enclosures(
        ids,
        nominal_weights,
        derived,
        nominal_probability_sum=nominal_probability_sum,
        probability_sum_interval=probability_sum,
        selected_set_invariant=selected_set_invariant,
    )


def result_to_dict(result: SelectedWeightQualification) -> dict[str, object]:
    return {
        "by_expert_id": {
            str(expert_id): {
                "expert_id": item.expert_id,
                "nominal_weight": item.nominal_weight,
                "interval": {"lower": item.interval.lower, "upper": item.interval.upper},
                "outward_absolute_radius": item.outward_absolute_radius,
                "relative_radius_diagnostic": item.relative_radius,
                "mathematically_qualified": item.mathematically_qualified,
                "engineering_h2": item.engineering_h2,
            }
            for expert_id, item in sorted(result.by_expert_id.items())
        },
        "probability_sum_interval": {
            "lower": result.probability_sum_interval.lower,
            "upper": result.probability_sum_interval.upper,
        },
        "nominal_probability_sum": result.nominal_probability_sum,
        "joint_weight_sum_interval": {
            "lower": result.joint_weight_sum_interval.lower,
            "upper": result.joint_weight_sum_interval.upper,
        },
        "nominal_weight_sum": result.nominal_weight_sum,
        "denominator_floor_status": result.denominator_floor_status,
        "joint_normalization_valid": result.joint_normalization_valid,
        "mathematically_qualified": result.mathematically_qualified,
        "engineering_h2": result.engineering_h2,
        "failed_mathematical_ids": list(result.failed_mathematical_ids),
        "failed_engineering_ids": list(result.failed_engineering_ids),
    }


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
