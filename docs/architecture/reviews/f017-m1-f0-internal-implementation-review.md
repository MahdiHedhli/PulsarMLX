# F017 M1-F0 Internal Implementation Review

## Verdict

`GO FOR M1-F0 ADVERSARIAL REVIEW`

## Scope reviewed

This review covers only the checkpoint-free M1-F0 admission delta at tooling
head `3192b31e4fe3008f0182548a45f7117948d83afd`. It does not review or
authorize a real payload read.

## Findings

- The input is generated independently with PCG64 seed `17017006`; it does not
  reuse the historical Feature 016 residual.
- Layer 3, position 0 is self-contained: DSA is exact `range_fill([0])`, so no
  indexer tensor is needed.
- The allowlist is an ordered set of 12 exact catalog entries. It contains
  attention norms/projections, the attention output projection, router norm,
  router projection, and router bias only. Expert/shared-expert patterns and
  model output-head identities fail closed.
- The access budget is derived from GGUF block layouts and catalog shapes:
  one shard open, 12 positional reads, 139,217,920 packed bytes, and zero
  expert payloads.
- The independent preparer has no Rust, FFI, MLX, candidate-output, or
  Feature-018 dependency. Its Q5_K/Q8_0 scalar decoders match the existing
  Python decoder and Rust decoder on frozen exact-byte regressions.
- The shared orchestration computes the full position-zero query/KV path,
  attention score, exact single-visible-value softmax, attention residual,
  router normalization/projection, sigmoid+bias, stable top-8, and routing
  weights. It never calls an expert.
- The selection contract fixes lower-ID tie-breaking and canonical u16/f64
  serialization. Non-finite values are rejected.
- The numerical contract is operand-conditioned and frozen before any real
  observation. Exact route selection additionally requires an interval margin
  between ranks 8 and 9; tolerances cannot substitute a different route.
- The immutable config binds the input components, exact allowlist, contracts,
  source hashes, evidence lineage, budget, attempt semantics, and external
  authorization requirement. Preflight re-hashes each repository artifact and
  performs no payload read or attempt transition.
- The future real preparer requires a separately hash-bound authorization and
  a typed, contained private package before opening the single shard.
- Synthetic qualification passed 10/10 deterministic discoveries. Six stress
  families and the negative mutation suite passed. The time-bounded soak found
  no stage/route divergence.

## Failure-path review

Historical-route substitution, altered input, wrong layer, adjacent/expert
tensor, wildcard or missing tensor, wrong router-bias metadata, decoder
substitution, stale artifact hash, top-k order/weight mutation, access-budget
increase, attempt reuse, unissued authorization, path traversal, and symlink
escape all fail before real access.

## Boundary disposition

No real checkpoint was accessed. M1-F0 was not executed or authorized. M1-F
remains blocked. The package is suitable for a separate adversarial review.
