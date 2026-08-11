# PulsarMLX Feature 017 final Claude verification request

This is verification-only. Do not reopen the accepted architecture. Review
the final feature SHA and answer only whether the remaining blockers are
closed and exactly one bounded M1 Ultra P1 is admitted.

## Reviewed and remediated boundaries

- Prior reviewed SHA: `0e59d9786b96ce0aaad513bae71702a57ef23b6f`.
- Branch: `feat/017-rust-native-inference-runtime`.
- Verified implementation SHA:
  `47575474b52b68f6f1a8ab7f4d373c598024212a`.
- Required native CI run: `31449698582` (success).
- Historical run `31437864529` targeted
  `b7585de3cd431f448c39eeb0a46df5d1a87acc6a` and passed, but native MLX tests
  skipped; it is not final-gate evidence.

## B1: default-stream ownership

- Official MLX C v0.6.0 examples construct a default stream with
  `mlx_default_cpu_stream_new()` and release it with `mlx_stream_free()`.
- Fix `4d80c85` separates stream origin from handle ownership. Handles from
  `mlx_default_cpu_stream_new`, `mlx_default_gpu_stream_new`, and
  `mlx_stream_new_device` are freed exactly once.
- Six process counters cover default CPU, default GPU, and owned stream
  creation/free. Local 1,000-context tests for each mode reconcile exactly,
  including partial-construction failure and singleton reacquisition.

## B2/B3/B4 and shape guard

- The source-first/derived-later regression performs no evaluation or
  synchronization between source destruction and derived destruction. The
  refcounted payload survives, the callback fires exactly once, and managed
  and derived counters reconcile.
- Managed and derived arrays share lifetime state but are accounted separately.
- Process-global MLX state is guarded by one fail-closed singleton context;
  partial failure releases the guard and full teardown permits recreation.
- `pulsar_mlx_array_create_managed` rejects zero and logical counts above
  `INT_MAX` before allocation or shape conversion; the `INT_MAX + 1` test does
  not allocate the requested payload.

## Independent fixture provenance

- Generator: `scripts/research/generate_f017_independent_oracle.py`.
- Generator SHA: `a9779097de029f26be1cb9fde3543cc517ff153e`.
- Environment: CPython 3.13.13, NumPy 2.4.5, deterministic seed 17017.
- Oracle artifact SHA-256:
  `16ca1e412dbf98d59e19b685b86549567de043ea7e728b254a952540aa783960`.
- Projection, router, complete expert, top-8/shared, MLA/dense, complete layer,
  and final norm/logits/top-k are all classified `INDEPENDENT`.
- The generator calls no Rust, FFI, MLX, checkpoint, or Rust `reference_*`
  code. Historical v1 fixtures are marked non-independent and excluded from
  the validated manifest set.
- Synthetic fixtures cover selected extremes but not real-checkpoint
  distribution tails. P1 remains the first real-checkpoint integration gate.

## P1 admission

The handoff records exact branch/SHA, clean state, checkpoint hashes,
OS/MLX/Metal/Xcode/compiler identity, stream origin and handle ownership,
singleton state, a 16 GiB absolute free-memory floor, no competing inference,
fail-closed validation, token 9703, expected token 21615, fresh evidence, and
exactly one P1 followed by a mandatory stop. It explicitly reconciles every
managed/derived/callback counter, all six stream counters, context singleton,
registrations/teardowns, in-flight work, and native-ready generations.

## Final CI evidence

- Run: `31449698582`, success, head
  `47575474b52b68f6f1a8ab7f4d373c598024212a`.
- URL: <https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31449698582>.
- `Apple MLX small-fixture validation` job `93651317894`: success.
- `Apple Silicon workspace baseline` job `93651317916`: success.
- The native job built official MLX v0.31.2 and MLX C v0.6.0 source commits
  plus the hash-verified upstream patch set from Homebrew `0.6.0_2`.
- The native log states
  `PULSAR_REQUIRE_NATIVE_MLX=1; executing native adapter tests (no skip permitted)`.
- Native adapter result: `9 passed; 0 failed; 0 ignored`.
- Independent-oracle results: Python `Ran 2 tests ... OK`; Rust
  `3 passed; 0 failed; 0 ignored`.
- The dedicated native job did not skip native tests. The separate workspace
  baseline intentionally compiles without MLX C and reports its existing skip;
  that skip is not used as native qualification evidence.

## Decision requested

Answer exactly one:

- `GO`: all remaining blockers are closed; exactly one bounded M1 Ultra F017
  P1 is admitted.
- `NO-GO`: list only concrete blockers remaining before that P1.

Do not authorize P2 or golden-eight.
