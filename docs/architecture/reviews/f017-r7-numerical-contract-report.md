# PulsarMLX F017 R7 Numerical Contract Report

## Result

The R7 exact semantic boundary and production Tier-B boundary are resolved,
and checkpoint-free R8 passed. The exact scaffold remains the permanent
semantic/debugging reference; production MLX remains the actual runtime path.
R9 is next and was not started in this sprint.

## Source

- Starting SHA: `d90e1c04f582e67599a499b3ed5d6e34681302ef`
- Branch: `feat/017-real-checkpoint-runner`
- R8 execution SHA: `88a46e813f47c4047644d736c82a926ea2f1abd8`
- No checkpoint access and no M1 model time

## Original frozen mismatch

The independent oracle is `427908.5` (`0x48d0f090`); production MLX was
`427909.0` (`0x48d0f0a0`). Absolute delta is `0.5`; relative delta is
`1.1684741013557804e-6`. The original exact contract correctly rejected it.

## Qualification scaffold and exact parity

The qualification-only Rust matvec uses strict increasing-column order,
separate rounded f32 multiply/add, frozen f32 SwiGLU semantics, no allocation,
no MLX, and no fallback. Gate, up, hidden, down, and complete-expert outputs
match the independent oracle bit-for-bit over 10 repeats.

## Production attribution

Decode, materialization, gate, up, and activation are excluded for the frozen
fixture. The first production difference is the MLX down matmul. The exact
internal reduction tree remains unknown and is not inferred from residuals.

## Tier-B and stress result

The theoretical, condition-aware contract was frozen before additional
candidate outputs. Nine independent stress cases then passed bit-identically.
Production R7 passed the unchanged contract with max absolute error `1.375`,
RMSE `0.693598660294626`, cosine `0.9999999999999881`, 10 deterministic
repeats, zero fallback, and reconciled ownership.

## R8

R8 passed with exact top-8 IDs, frozen-bounded router weights, exact
gate/up/activation, Tier-B-qualified down outputs for eight routed and one
shared expert, and bounded aggregation. The final aggregate max absolute error
was `3.175311913713813`, RMSE `1.5592101279929471`; lifecycle reconciled and
fallback count was zero.

## Evidence schema and modes

Runner evidence schema `1.1.0` records explicit numerical mode, oracle and
scaffold identities, backend/contract versions, mismatches, error metrics,
deterministic repeats, first divergence, and classification. The runner
requires one of `exact-qualification-scaffold` or `production-mlx-tier-b`;
production cannot silently fall back to the scaffold.

## CI and validation

The R8/report head Apple workflow
[`31491623025`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31491623025)
passed at `e58d3f1f`: the workspace job completed in 1m38s and the native MLX
job completed in 7m31s. The native job explicitly executed the exact scaffold,
R7 attribution, independent Tier-B stress, production R7, and R8 gates without
checkpoint access.

## Next gate

R9 is the exact next checkpoint-free gate: representative MLA/dense semantics
and the smallest missing production-adapter operations. R8 does not authorize
R9 execution inside this sprint, a real checkpoint, a P1 command, or M1 model
time.
