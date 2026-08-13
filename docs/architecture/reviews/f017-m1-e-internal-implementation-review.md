# F017 M1-E Internal Implementation Review

**Reviewer role:** INTERNAL IMPLEMENTATION

**Verdict: GO FOR ONE M1-E REAL EXPERT**

## Reviewed binding

- runtime implementation: `466770362e3066fa5fd9827ec1f454e03afe3006`
- tooling/test qualification: `3387bb6d4508eb04e672dc6194da2855ba72f072`
- reviewed package head: `f3a7ba8f3a7eb52dbf48c6929e23835e5c18eeea`
- handoff SHA-256: `2325f9b2964b5c1120864fbaa4d3fda875f8d263154d783bf02b6ad47e78e531`
- immutable execution-config SHA-256: `7f69550bfd7ccd5e820f23d2bcce7f0e287d2c2bfc5f1ae2adb59ec5467b0a1b`
- accepted M1-D evidence: `dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c`
- final package qualification: CI `31656082515`, exact reviewed package head, both Apple jobs green

## Implementation findings

The implementation is safe for one separately authorized expert attempt.

- `Glm52TensorMap` metadata fixes layer 3/expert 15 and the exact gate, up,
  and down ranges. Wildcards, adjacent experts, router/shared-expert tensors,
  and a fourth payload fail closed.
- The candidate composes three production MLX matvec boundaries with exact
  CPU-side SwiGLU orchestration. The CPU operation is explicitly classified;
  it cannot masquerade as fallback or reference dispatch.
- Independent IQ2_XXS and IQ3_XXS Python/NumPy decoders and strict sequential
  f32 arithmetic construct the oracle without Rust candidate, MLX, FFI, or
  candidate output. The finalized package is validated before candidate start.
- The expert Tier-B contract composes the two 6144-wide projection bounds,
  the frozen SiLU/product bound, and the 2048-wide down-projection bound. The
  zero-up edge retains the upstream SiLU term, and no threshold is fitted to
  candidate output.
- Ten complete repeats capture gate, up, activated-hidden, and final hashes.
  All four stages must be identical, while 30 native dispatches reconcile to
  one conceptual expert.
- Managed/derived arrays, callbacks, streams, singleton state, registrations,
  generations, owner tokens, and in-flight work are reconciled before PASS.
  Terminal failures remain bankable without weakening the PASS path.
- The production launcher accepts only the hash-bound execution config. The
  preflight is repeatable, accesses no payload, creates no attempt state, and
  returns exactly `READY_TO_EXECUTE_M1_E`.

## Validation evidence

CI `31656082515` ran the pinned native MLX environment with no relevant skip:

- Python activation/oracle package suite: 6 passed;
- execution-config, isolation, and failure gates: 5 passed;
- frozen expert numerical contract: 3 passed;
- native real-shaped expert integration: 4 passed;
- canonical synthetic expert: PASS, one expert, ten repeats, 30 native
  dispatches;
- intermediate repeat divergence with matching final output: rejected;
- stale oracle and candidate-before-completion: rejected;
- accepted M1-D path/config/repeat/oracle regressions: passed.

No real M1-E payload was read and no real expert was executed during review.
M1-F and P1 remain blocked.
