# F020 ClampedSwiGLU activation qualification

Updated 2026-10-03. This records synthetic activation qualification at
`60a2436886fb6803d62a28d28c0cfb717d93e206`. It is an additive result receipt,
separate from the unchanged prospective package and historical attempts.

The active research driver is
`scripts/research/f020_fused_swiglu_qualification_v2_5.py`.
Its method was independently accepted by Grok 4.7 and Agy/Gemini 3.8 Flash
Medium at that exact commit. The subsequent admitted Studio run completed
`PASS`; required [CI 37133162964](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/37133162964)
also completed successfully.

## Observed result and numerical boundary

The retained successful attempt enumerated 2,197,815,298 F32 gate inputs in
[-16, 16], including signed zeros and subnormals, across 2,098 bounded batches.
It recorded 2,098 native SiLU materializations, 6,295 CPU arithmetic guard checks
and zero anomalies. This is exhaustive gate coverage; the bounded up operand
is covered by the reviewed product theorem, not a Cartesian exhaustive sweep.

Both acceptance gates passed: the inherited `delta + beta_B <= E_N` gate and
the exact full-up propagation gate. `beta_B = 5201/4194304` and
`E_N = E_act = 1/128` are unchanged. The resulting full-up bound was approximately
0.00185411144, below 0.0078125. Independent R1 corroboration passed for the
42 fixed and 500 extended controls plus the worst-error witness.

The unchanged regressions passed with exact manifest case IDs: 363 native
primitive cases and 32 expert-plane composition cases. Required CI additionally
passed its same-run baseline/candidate canonical-report comparison.

The graph preserves the asymmetric gate clamp, symmetric up clamp, and explicit
materialization of the native SiLU buffer before the final up-dependent product.
The claim is tied to the recorded native artifacts, source pins, OS/Metal runtime
and M1 Ultra qualification environment. It is not a universal intrinsic error
bound or qualification of a new physically fused expert kernel.

## Attempts and reproduction

The first attempt completed its native sweep and controls, then stopped while
formatting an exact R1 fraction under Python's default 4,300-digit conversion
limit. Its evidence is retained. The successful second attempt used
process-local `PYTHONINTMAXSTRDIGITS=0` for exact-rational report serialization;
source bytes, arithmetic, domains, coefficients and budgets did not change.

The [sanitized qualification summary](../../specs/020-mlx-safetensors-affine/qualification/fused-swiglu-v2-5-studio-summary-v1.json)
binds the successful full report by SHA-256 and records source/package, runtime,
counts, bounds, regression and CI identities. The full 24.4 MB report and raw
attempts remain in the owner's private evidence archive.

The frozen driver's execution authority requires the retained
`feat/020-synthetic-expert-mlp-20260925` branch, clean requested HEAD and exact
origin parity. It deliberately refuses execution from `main`. Integration
does not modify those gates or enable automatic candidate execution.

## Next boundary

Complete synthetic expert-MLP composition is still unqualified. Its additive
contract, independently computed end-to-end R1, deterministic fixture population,
source bindings and implementation must be frozen and independently reviewed
before candidate observations. Preserve packed U32 weights into gate/up/down QMM,
the qualified activation ordering, and the unchanged down-input predicates.

Real checkpoint payloads, production shapes, routing/aggregation, a complete
model, streaming, serving, physical kernel fusion and performance qualification
remain separate gates. No activation benchmark or implementation-selection
speedup is claimed by this receipt.
