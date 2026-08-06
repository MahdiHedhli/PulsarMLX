# Feature Specification: Top-8 Routed Aggregation

**Feature Branch**: `004-top8-aggregation`  
**Created**: 2026-08-06  
**Status**: Draft  
**Input**: Execute every Feature 002 routed expert for one input row, aggregate
weighted contributions, prove CPU oracle parity, and retain cold/warm I/O
gauges. No generation.

## Baseline

- Feature 002: router top-8 + normalized weights for row-0.  
- Feature 003: single expert 114 full MLP weighted parity verified.

## User Stories

### US1 - Multi-expert CPU oracle (P1)

Freeze independent CPU aggregation of all eight selected experts’ weighted
MLP outputs for the frozen `ffn_norm-0` row-0 input.

### US2 - Apple top-8 execution + aggregation (P1)

Run all eight experts on MLX GPU, sum weighted outputs, compare to oracle.

### US3 - I/O gauges (P2)

Record bytes read, cold vs warm re-read timings for expert tensor ranges
(public-safe, no tokens/sec claim).

### US4 - Publication (P2)

Publish raw evidence and claim F004-C01 for routed top-8 aggregation parity.

## Requirements

- **FR-001**: Use Feature 002 frozen top-8 IDs and weights for row-0.  
- **FR-002**: Execute full MLP for each of the eight experts (reuse F003 math).  
- **FR-003**: Aggregate `sum_i weight_i * expert_i_down`.  
- **FR-004**: Independent CPU oracle without MLX imports.  
- **FR-005**: MLX GPU eval/sync, no fallback, frozen tolerances.  
- **FR-006**: Retain cold/warm read gauges and bytes read.  
- **FR-007**: Publish append-only raw evidence under `raw/004-top8-moe/`.  
- **FR-008**: No layer/logits/generation claims.

## Success Criteria

- **SC-001**: Aggregated 2048-vector matches CPU oracle with 0 mismatches.  
- **SC-002**: All eight expert identities and routing weights recorded.  
- **SC-003**: At least one warm re-run shows reduced or recorded I/O gauges.  
- **SC-004**: Public claim F004-C01 only asserts top-8 aggregation depth.

## Out of Scope

Complete MoE block residuals/norms, attention, multi-layer, generation.
