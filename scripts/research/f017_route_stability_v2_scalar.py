#!/usr/bin/env python3
"""Independent scalar transcription of the F017 v2 candidate bound."""

from __future__ import annotations

import math
from typing import Mapping, Sequence

U64 = 2.0 ** -53


def _up(value: float) -> float:
    if value < 0.0 or not math.isfinite(value):
        raise ValueError("bound")
    return math.nextafter(value, math.inf)


def _sigmoid(x: float) -> float:
    if x < 0.0:
        e = math.exp(x)
        return e / (1.0 + e)
    e = math.exp(-x)
    return 1.0 / (1.0 + e)


def _derivative_range(center: float, radius: float) -> tuple[float, float]:
    lo, hi = center - radius, center + radius
    def derivative(x: float) -> float:
        p = _sigmoid(x)
        return p * (1.0 - p)
    low = min(derivative(lo), derivative(hi))
    high = 0.25 if lo <= 0.0 <= hi else max(derivative(lo), derivative(hi))
    return max(0.0, math.nextafter(low, -math.inf)), _up(high)


def calculate(data: Mapping[str, object]) -> float:
    li, lj = float(data["logit_i"]), float(data["logit_j"])
    wi = tuple(float(x) for x in data["row_i"])  # type: ignore[arg-type]
    wj = tuple(float(x) for x in data["row_j"])  # type: ignore[arg-type]
    rb = tuple(float(x) for x in data["residual_bounds"])  # type: ignore[arg-type]
    lam = float(data["lambda_bound"])
    ri, rj = float(data["reduction_i"]), float(data["reduction_j"])
    ii, ij = float(data.get("import_i", 0.0)), float(data.get("import_j", 0.0))
    bi, bj = float(data.get("bias_i", 0.0)), float(data.get("bias_j", 0.0))
    if len(wi) != len(wj) or len(wi) != len(rb):
        raise ValueError("shape")
    if not all(math.isfinite(x) for x in (li, lj, lam, ri, rj, ii, ij, bi, bj, *wi, *wj, *rb)):
        raise ValueError("finite")
    if any(x < 0.0 for x in (lam, ri, rj, ii, ij, *rb)):
        raise ValueError("negative")
    ei = _up(abs(li) * lam + math.fsum(abs(wi[k]) * rb[k] for k in range(len(wi))) + ri + ii)
    ej = _up(abs(lj) * lam + math.fsum(abs(wj[k]) * rb[k] for k in range(len(wj))) + rj + ij)
    di, dj = _derivative_range(li, ei), _derivative_range(lj, ej)
    radial = _up(lam * max(abs(a * li - b * lj) for a in di for b in dj))
    nonradial = 0.0
    for k in range(len(wi)):
        coefficient = max(abs(a * wi[k] - b * wj[k]) for a in di for b in dj)
        nonradial = _up(nonradial + rb[k] * coefficient)
    reduction = _up(di[1] * ri + dj[1] * rj)
    imported = _up(di[1] * ii + dj[1] * ij)
    def addition_guard(center: float, radius: float, bias: float) -> float:
        low_score = _sigmoid(center - radius) + bias
        high_score = _sigmoid(center + radius) + bias
        if not math.isfinite(low_score) or not math.isfinite(high_score):
            raise ValueError("score interval")
        return _up(max(math.ulp(low_score), math.ulp(high_score), math.ulp(0.0)))
    addition_rounding = _up(2.0 * addition_guard(li, ei, bi) + 2.0 * addition_guard(lj, ej, bj))
    accumulation_rounding = _up(8.0 * U64 * (
        abs(_sigmoid(li)) + abs(_sigmoid(lj))
        + radial + nonradial + reduction + imported
    ))
    total = 0.0
    for term in (radial, nonradial, reduction, imported, addition_rounding, accumulation_rounding):
        total = _up(total + term)
    return total
