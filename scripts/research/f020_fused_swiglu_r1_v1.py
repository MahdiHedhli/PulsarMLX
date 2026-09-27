#!/usr/bin/env python3
"""Independent exact-rational interval evaluator for F020 fused SwiGLU.

This module deliberately has no MLX, compiler, candidate, or fixture imports.
It is used as the expected-value authority by the qualification driver.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math


@dataclass(frozen=True)
class Interval:
    lo: Fraction
    hi: Fraction

    def __post_init__(self) -> None:
        if self.lo > self.hi:
            raise ValueError("inverted interval")

    @property
    def width(self) -> Fraction:
        return self.hi - self.lo


def add(a: Interval, b: Interval) -> Interval:
    return Interval(a.lo + b.lo, a.hi + b.hi)


def mul(a: Interval, b: Interval) -> Interval:
    p = (a.lo * b.lo, a.lo * b.hi, a.hi * b.lo, a.hi * b.hi)
    return Interval(min(p), max(p))


def scale(a: Interval, c: Fraction) -> Interval:
    return mul(a, Interval(c, c))


def reciprocal_positive(a: Interval) -> Interval:
    if a.lo <= 0:
        raise ValueError("reciprocal interval crosses zero")
    return Interval(Fraction(1, a.hi), Fraction(1, a.lo))


# Decimal rational enclosures of ln(2), deliberately wider than the known
# value. They are constants, not candidate observations.
LN2 = Interval(
    Fraction(6931471805599453094172321214581765680755001343602552541206800094933936, 10**70),
    Fraction(6931471805599453094172321214581765680755001343602552541206800094933940, 10**70),
)
ONE = Interval(Fraction(1), Fraction(1))


def exp_taylor(t: Fraction) -> Interval:
    """Degree-64 Taylor enclosure after exact rational range reduction."""
    # k is chosen from the host value only to select a nearby reduction; the
    # interval proof below still encloses k*ln(2).
    k = math.floor(float(t / LN2.lo) + 0.5)
    a = Interval(t, t)
    kln = scale(LN2, Fraction(k))
    r = Interval(a.lo - kln.hi, a.hi - kln.lo)
    if not (abs(r.lo) <= Fraction(1, 2) and abs(r.hi) <= Fraction(1, 2)):
        raise ValueError("range reduction outside contract")
    term = ONE
    total = ONE
    for n in range(1, 65):
        term = mul(term, r)
        term = scale(term, Fraction(1, n))
        total = add(total, term)
    # |r| <= 1/2, so the geometric tail after degree 64 is bounded by
    # (|r|^65/65!) / (1-|r|/66); use a simple strict rational upper bound.
    rho = max(abs(r.lo), abs(r.hi))
    tail = rho ** 65 / math.factorial(65)
    tail = tail * Fraction(66, 65)
    total = Interval(total.lo - tail, total.hi + tail)
    scale2 = Fraction(2 ** k) if k >= 0 else Fraction(1, 2 ** (-k))
    return scale(total, scale2)


def sigmoid(x: Fraction) -> Interval:
    if x >= 0:
        e = exp_taylor(-x)
        return reciprocal_positive(add(ONE, e))
    e = exp_taylor(x)
    return mul(e, reciprocal_positive(add(ONE, e)))


def evaluate(gate_f32: float, up_f32: float) -> Interval:
    if not (math.isfinite(gate_f32) and math.isfinite(up_f32)):
        raise ValueError("non-finite input")
    if not (-16.0 <= gate_f32 <= 16.0 and -16.0 <= up_f32 <= 16.0):
        raise ValueError("input outside frozen domain")
    g = min(Fraction.from_float(gate_f32), Fraction(10))
    up = min(max(Fraction.from_float(up_f32), Fraction(-10)), Fraction(10))
    s = sigmoid(g)
    return mul(mul(Interval(g, g), s), Interval(up, up))


def self_test() -> None:
    for x in (Fraction(-16), Fraction(-10), Fraction(0), Fraction(10), Fraction(16)):
        y = evaluate(float(x), Fraction(1).__float__())
        if y.width > Fraction(1, 2**160):
            raise AssertionError(f"R1 width too large at {x}: {y.width}")
        if not (y.lo <= y.hi):
            raise AssertionError("R1 interval ordering")


if __name__ == "__main__":
    self_test()
    print("R1_SELFTEST_PASS")
