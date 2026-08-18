#!/usr/bin/env python3
"""Synthetic-only F017 complete-layer aggregate acceptance v2 theorem.

The module has no filesystem, checkpoint, private-package, or production
evidence loader. It composes the fixed residual and shared-expert authority
with the already-frozen routed-aggregate perturbation using the production
addition order and a directed-outward final-f32 transport enclosure.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import struct
from typing import Sequence

from scripts.research import f017_routing_contract_v31 as v31


COMPLETE_LAYER_DIMENSION = 6144
MAX_ABSOLUTE_BUDGET = 0.0625
RMSE_BUDGET = 0.03125
COSINE_MINIMUM = 0.999
ENGINEERING_HEADROOM = 2.0


class CompleteLayerTheoremError(ValueError):
    """Fail-closed rejection outside the theorem domain."""


def _finite(value: float, label: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise CompleteLayerTheoremError(f"{label} must be finite")
    return value


def _point(value: float, label: str) -> v31.Interval:
    value = _finite(value, label)
    return v31.Interval(value, value)


def f32(value: float) -> float:
    """Round one finite Python float to canonical IEEE binary32."""
    value = _finite(value, "binary32 input")
    try:
        result = struct.unpack("<f", struct.pack("<f", value))[0]
    except OverflowError as exc:
        raise CompleteLayerTheoremError("binary32 overflow") from exc
    if not math.isfinite(result):
        raise CompleteLayerTheoremError("binary32 result is non-finite")
    return result


def _f32_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", f32(value)))[0]


def _f32_from_bits(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits))[0]


def _next_f32(value: float, upward: bool) -> float:
    value = f32(value)
    bits = _f32_bits(value)
    if value == 0.0:
        return _f32_from_bits(1 if upward else 0x80000001)
    bits += 1 if (upward == (value > 0.0)) else -1
    result = _f32_from_bits(bits)
    if not math.isfinite(result):
        raise CompleteLayerTheoremError("binary32 outward step overflow")
    return result


def _cast_interval_f32(value: v31.Interval) -> v31.Interval:
    """Soundly enclose monotone round-to-nearest binary32 materialization."""
    lower = f32(value.lower)
    upper = f32(value.upper)
    if lower > value.lower:
        lower = _next_f32(lower, False)
    if upper < value.upper:
        upper = _next_f32(upper, True)
    return v31.Interval(lower, upper)


def _sum_intervals(values: Sequence[v31.Interval]) -> v31.Interval:
    if not values:
        raise CompleteLayerTheoremError("empty interval reduction")
    total = v31.Interval(0.0, 0.0)
    for value in values:
        total = v31.interval_add(total, value)
    return total


def _factor(budget: float, bound: float) -> float:
    if bound < 0.0 or not math.isfinite(bound):
        raise CompleteLayerTheoremError("invalid acceptance bound")
    if bound == 0.0:
        return math.inf
    quotient = budget / bound
    return math.inf if math.isinf(quotient) else v31.round_down(quotient)


@dataclass(frozen=True)
class CompleteLayerQualification:
    nominal: tuple[float, ...]
    perturbations: tuple[v31.Interval, ...]
    max_absolute_bound: float
    rmse_bound: float
    perturbation_l2_bound: float
    nominal_l2_lower: float
    cosine_lower_bound: float | None
    max_absolute_factor: float
    rmse_factor: float
    cosine_factor: float | None
    aggregate_safety_factor: float
    mathematically_qualified: bool
    engineering_h2: bool
    shared_uncertainty_mode: str


def qualify_complete_layer(
    residual: Sequence[float],
    shared_nominal: Sequence[float],
    routed_nominal: Sequence[float],
    routed_perturbations: Sequence[v31.Interval],
    *,
    shared_intervals: Sequence[v31.Interval] | None = None,
) -> CompleteLayerQualification:
    """Enclose ``f32(f64(R) + (M + f64(S)))`` over routed uncertainty.

    An exact-class shared artifact is a point authority for this routing-only
    ambiguity proof, so ``delta_S=0``. A bounded-class shared artifact must
    supply explicit component intervals and cannot silently use the point rule.
    """
    dimension = len(residual)
    if dimension == 0 or any(
        len(values) != dimension
        for values in (shared_nominal, routed_nominal, routed_perturbations)
    ):
        raise CompleteLayerTheoremError("complete-layer dimensions must align")
    if shared_intervals is not None and len(shared_intervals) != dimension:
        raise CompleteLayerTheoremError("shared interval dimensions must align")

    nominal: list[float] = []
    perturbations: list[v31.Interval] = []
    radii: list[float] = []
    for index in range(dimension):
        r = f32(residual[index])
        s = f32(shared_nominal[index])
        m = _finite(routed_nominal[index], "routed nominal")
        routed_delta = routed_perturbations[index]
        shared = _point(s, "shared nominal") if shared_intervals is None else shared_intervals[index]
        if not shared.contains(s):
            raise CompleteLayerTheoremError("shared interval excludes nominal")

        nominal_value = f32(float(r) + (m + float(s)))
        exact_point = (
            routed_delta.lower == 0.0
            and routed_delta.upper == 0.0
            and shared.lower == s
            and shared.upper == s
        )
        if exact_point:
            delta = v31.Interval(0.0, 0.0)
        else:
            routed = v31.interval_add(_point(m, "routed nominal"), routed_delta)
            combined = v31.interval_add(routed, shared)
            complete = _cast_interval_f32(
                v31.interval_add(_point(r, "residual"), combined)
            )
            delta = v31.interval_sub(
                complete,
                _point(nominal_value, "nominal complete layer"),
            )
        radius = (
            0.0
            if delta.lower == 0.0 and delta.upper == 0.0
            else v31.round_up(max(abs(delta.lower), abs(delta.upper)))
        )
        nominal.append(nominal_value)
        perturbations.append(delta)
        radii.append(radius)

    max_bound = max(radii)
    if all(radius == 0.0 for radius in radii):
        l2_bound = 0.0
        rmse_bound = 0.0
    else:
        radius_squared = _sum_intervals(
            tuple(v31.square_interval(_point(radius, "component radius")) for radius in radii)
        )
        l2_bound = v31.interval_sqrt(
            v31.Interval(max(0.0, radius_squared.lower), radius_squared.upper)
        ).upper
        rmse_bound = v31.round_up(l2_bound / math.sqrt(dimension))

    nominal_squared = _sum_intervals(
        tuple(v31.square_interval(_point(value, "nominal complete layer")) for value in nominal)
    )
    nominal_norm = v31.interval_sqrt(
        v31.Interval(max(0.0, nominal_squared.lower), nominal_squared.upper)
    )
    cosine_lower: float | None = 1.0 if l2_bound == 0.0 and nominal_norm.lower > 0.0 else None
    if l2_bound > 0.0 and nominal_norm.lower > 0.0 and l2_bound < nominal_norm.lower:
        ratio_upper = v31.round_up(l2_bound / nominal_norm.lower)
        ratio_squared_upper = v31.round_up(ratio_upper * ratio_upper)
        tangent_squared_lower = v31.round_down(1.0 - ratio_squared_upper)
        if tangent_squared_lower > 0.0:
            cosine_lower = max(
                -1.0,
                min(1.0, v31.round_down(math.sqrt(tangent_squared_lower))),
            )

    max_factor = _factor(MAX_ABSOLUTE_BUDGET, max_bound)
    rmse_factor = _factor(RMSE_BUDGET, rmse_bound)
    cosine_factor: float | None = None
    if cosine_lower is not None:
        if cosine_lower == 1.0:
            cosine_factor = math.inf
        else:
            cosine_loss = v31.round_up(1.0 - cosine_lower)
            cosine_factor = v31.round_down((1.0 - COSINE_MINIMUM) / cosine_loss)
    factors = [max_factor, rmse_factor]
    if cosine_factor is not None:
        factors.append(cosine_factor)
    safety_factor = min(factors)
    mathematically_qualified = (
        max_bound <= MAX_ABSOLUTE_BUDGET
        and rmse_bound <= RMSE_BUDGET
        and cosine_lower is not None
        and cosine_lower >= COSINE_MINIMUM
    )
    return CompleteLayerQualification(
        nominal=tuple(nominal),
        perturbations=tuple(perturbations),
        max_absolute_bound=max_bound,
        rmse_bound=rmse_bound,
        perturbation_l2_bound=l2_bound,
        nominal_l2_lower=nominal_norm.lower,
        cosine_lower_bound=cosine_lower,
        max_absolute_factor=max_factor,
        rmse_factor=rmse_factor,
        cosine_factor=cosine_factor,
        aggregate_safety_factor=safety_factor,
        mathematically_qualified=mathematically_qualified,
        engineering_h2=mathematically_qualified and safety_factor >= ENGINEERING_HEADROOM,
        shared_uncertainty_mode=(
            "EXACT_CLASS_POINT_DELTA_S_ZERO"
            if shared_intervals is None
            else "BOUNDED_SHARED_INTERVALS_INCLUDED"
        ),
    )


def qualify_f017_production_complete_layer(
    *args: object, **kwargs: object
) -> CompleteLayerQualification:
    result = qualify_complete_layer(*args, **kwargs)
    if len(result.nominal) != COMPLETE_LAYER_DIMENSION:
        raise CompleteLayerTheoremError("F017 production complete layer requires 6144 components")
    return result
