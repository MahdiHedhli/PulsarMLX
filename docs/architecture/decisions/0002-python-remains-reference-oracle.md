# ADR 0002: Python remains the reference oracle

- **Status**: Accepted
- **Date**: 2026-08-09

## Decision

Python and NumPy remain an independently understandable architecture oracle,
fixture generator, boundary-inspection environment, reference decoder,
differential-testing path, and research evidence producer after native runtime
implementations land.

## Consequences

The reference path may be slower and is not deleted merely because Rust, MLX,
or Metal becomes faster. Native implementations must compare against it at
appropriate exact or numerical gates. Oracle code must not call the
implementation under test.
