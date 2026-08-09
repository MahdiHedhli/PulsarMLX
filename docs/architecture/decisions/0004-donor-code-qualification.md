# ADR 0004: Qualify donor code before adoption

- **Status**: Accepted
- **Date**: 2026-08-09

## Decision

Pulsar is inherited project lineage. ssd-llm and Colibri are design references.
No donor runtime becomes a PulsarMLX dependency, and no implementation is
copied or adapted, without explicit source and license review, attribution,
independent tests, compatibility analysis, and measured benefit.

## Consequences

Ideas may guide clean reimplementation behind PulsarMLX interfaces. Any future
adaptation must record provenance and satisfy the donor license. Donor benchmark
results are never promoted as PulsarMLX evidence, and no endorsement is implied.
