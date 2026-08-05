"""Frozen, dependency-free statistics for PulsarMLX research evidence.

The evidence format stores durations as positive integer nanoseconds.  This
module keeps those values as integers until a statistic necessarily produces a
floating-point result and implements the Feature 002 percentile convention
directly instead of relying on a library-specific default.
"""

from __future__ import annotations

from fractions import Fraction
import math
from typing import Iterable, Mapping, TypeAlias


NanosecondSummary: TypeAlias = dict[str, int | float | str | None]
CompatibilityKey: TypeAlias = tuple[object, ...]

# Changing any of these fields can change what was measured.  Observations
# with different values therefore must never contribute to the same summary.
COMPATIBILITY_FIELDS = (
    "case_id",
    "condition",
    "instrumentation_mode",
    "source_commit",
    "batch_id",
)

_REQUIRED_PERCENTILES = (
    ("p5_ns", Fraction(5, 100)),
    ("p25_ns", Fraction(25, 100)),
    ("median_ns", Fraction(50, 100)),
    ("p75_ns", Fraction(75, 100)),
    ("p95_ns", Fraction(95, 100)),
)


def _validated_nanoseconds(samples: Iterable[int]) -> tuple[int, ...]:
    """Materialize and validate a nonempty sequence of duration samples."""

    try:
        values = tuple(samples)
    except TypeError as error:
        raise TypeError("nanosecond samples must be an iterable") from error

    if not values:
        raise ValueError("at least one nanosecond sample is required")

    for index, value in enumerate(values):
        # ``bool`` is an ``int`` subclass, so an isinstance check would admit
        # it and silently turn True into a one-nanosecond observation.
        if type(value) is not int:
            raise TypeError(
                f"nanosecond sample at index {index} must be a plain integer"
            )
        if value <= 0:
            raise ValueError(
                f"nanosecond sample at index {index} must be positive"
            )

    return values


def _type_7_percentile(
    ordered_values: tuple[int, ...], probability: Fraction
) -> float:
    """Return a Hyndman-Fan Type-7 percentile for sorted integer values."""

    if not 0 <= probability <= 1:
        raise ValueError("percentile probability must be between zero and one")

    position = (len(ordered_values) - 1) * probability
    lower_index = position.numerator // position.denominator
    fraction = position - lower_index
    upper_index = min(lower_index + 1, len(ordered_values) - 1)

    lower = ordered_values[lower_index]
    upper = ordered_values[upper_index]
    interpolated = Fraction(lower) + fraction * (upper - lower)
    return float(interpolated)


def coefficient_of_variation(
    *,
    mean: float | int | None,
    sample_standard_deviation: float | int | None,
) -> tuple[float | None, str | None]:
    """Return sample-SD/mean or an explicit, stable unavailable reason."""

    if sample_standard_deviation is None:
        return None, "sample_standard_deviation_unavailable"
    if mean is None:
        return None, "mean_unavailable"

    for name, value in (
        ("mean", mean),
        ("sample_standard_deviation", sample_standard_deviation),
    ):
        if type(value) not in (int, float):
            raise TypeError(f"{name} must be a plain integer or float")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{name} must be finite")

    if sample_standard_deviation < 0:
        raise ValueError("sample_standard_deviation must be nonnegative")
    if mean == 0:
        return None, "zero_mean"

    return float(sample_standard_deviation / mean), None


def summarize_nanoseconds(samples: Iterable[int]) -> NanosecondSummary:
    """Summarize positive integer nanoseconds using the frozen v1 rules."""

    values = _validated_nanoseconds(samples)
    ordered = tuple(sorted(values))
    sample_count = len(values)
    total = sum(values)
    mean = total / sample_count

    if sample_count < 2:
        sample_standard_deviation = None
        sample_standard_deviation_reason = "requires_at_least_two_samples"
    else:
        # This algebraically equivalent form keeps the variance numerator
        # exact for integer durations and avoids catastrophic cancellation for
        # large nanosecond counters whose spread is small.
        squared_sum = sum(value * value for value in values)
        variance_numerator = sample_count * squared_sum - total * total
        variance_denominator = sample_count * (sample_count - 1)
        sample_standard_deviation = math.sqrt(
            variance_numerator / variance_denominator
        )
        sample_standard_deviation_reason = None

    variation, variation_reason = coefficient_of_variation(
        mean=mean,
        sample_standard_deviation=sample_standard_deviation,
    )

    summary: NanosecondSummary = {
        "sample_count": sample_count,
        "minimum_ns": ordered[0],
        "maximum_ns": ordered[-1],
        "mean_ns": mean,
        "sample_standard_deviation_ns": sample_standard_deviation,
        "sample_standard_deviation_reason": sample_standard_deviation_reason,
        "coefficient_of_variation": variation,
        "coefficient_of_variation_reason": variation_reason,
    }
    summary.update(
        {
            name: _type_7_percentile(ordered, probability)
            for name, probability in _REQUIRED_PERCENTILES
        }
    )
    return summary


def group_raw_observations(
    observations: Iterable[Mapping[str, object]],
) -> dict[CompatibilityKey, list[Mapping[str, object]]]:
    """Group observations without pooling different compatibility fields."""

    groups: dict[CompatibilityKey, list[Mapping[str, object]]] = {}
    for index, observation in enumerate(observations):
        if not isinstance(observation, Mapping):
            raise TypeError(f"observation at index {index} must be a mapping")

        key_values: list[object] = []
        for field in COMPATIBILITY_FIELDS:
            if field not in observation:
                raise KeyError(f"observation at index {index} is missing {field}")
            value = observation[field]
            try:
                hash(value)
            except TypeError as error:
                raise ValueError(
                    f"observation field {field} must be hashable"
                ) from error
            key_values.append(value)

        key = tuple(key_values)
        groups.setdefault(key, []).append(observation)

    return groups
