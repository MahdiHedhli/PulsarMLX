# ADR 0001: Rust owns the shipping runtime

- **Status**: Accepted
- **Date**: 2026-08-09

## Decision

The installable PulsarMLX inference runtime will have no required Python
process. Rust owns product orchestration and performance-critical resource
management: checkpoint identity, storage, memory admission, residency,
routing, model state, generation, telemetry, cancellation, recovery, CLI, and
serving.

Native MLX and Metal functionality may use narrow C or Objective-C++ platform
bridges. “Rust-native” describes ownership and process architecture, not a rule
that every source file must be Rust.

## Consequences

The current Python/MLX research runtime is transitional, not the shipping
process boundary. Native work proceeds incrementally and must remain comparable
to the independent Python reference. A wholesale rewrite during Feature 016 is
out of scope.
