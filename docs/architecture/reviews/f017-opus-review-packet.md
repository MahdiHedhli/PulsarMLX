# PulsarMLX Feature 017 final independent review packet

## Scope

Verification of the last Feature 017 admission gates only: MLX stream
ownership, late callback safety, independent checkpoint-free provenance,
non-skipping native CI, and the single bounded M1 Ultra P1 contract. No
full-model run or Feature 018 kernel work occurred on ColPanicM2.

## Native ownership boundary

- Rust retains the host slab owner through MLX array and dependent stream work.
- The Objective-C++ adapter synchronizes the submission stream before host
  reuse or free.
- Stream origin (`default_cpu`, `default_gpu`, `owned_device`) is separate from
  handle ownership. Every admitted `_new` handle is freed exactly once.
- Per-context ownership state is refcounted across managed source, derived
  arrays, callback payload, and context accounting.
- A process-wide singleton rejects concurrent MLX contexts for the P1-era
  runtime and releases on every complete or partial teardown path.
- The shape boundary rejects zero and `INT_MAX + 1` before allocation.

## Falsifying regressions

- 1,000 default-CPU, 1,000 default-GPU, and 1,000 explicitly owned GPU context
  lifecycles reconcile all six stream counters.
- Source managed array destroyed first, derived `add_self` array destroyed
  later, with no intervening eval/sync: no UAF, exactly one callback, and
  managed/derived accounting reconciled.
- Partial construction after stream creation releases the stream and singleton;
  context recreation succeeds.

## Independent parity evidence

- Python/NumPy generator SHA:
  `a9779097de029f26be1cb9fde3543cc517ff153e`.
- CPython 3.13.13, NumPy 2.4.5, seed 17017.
- Oracle artifact SHA-256:
  `16ca1e412dbf98d59e19b685b86549567de043ea7e728b254a952540aa783960`.
- All seven ordered boundaries are `INDEPENDENT`; no Rust, FFI, MLX,
  checkpoint, or Rust `reference_*` code generated expected values.
- Historical Rust-reference fixtures remain for history but are explicitly
  non-independent and excluded from the validated set.
- Edge cases cover f16 Q8 scales, denormal-adjacent values, grid/sign extremes,
  zero/near-zero, cancellation, ties/near-ties, and top-k ordering. This is
  still synthetic evidence; real-checkpoint tails remain a P1 risk.

## F017/F018 boundary

F017 owns generic native-ready ownership, stream/fence lifetime, import and
registration lifecycle, capability/version metadata, fail-closed dispatch,
cancellation/teardown, and attributed telemetry. IQ2/IQ3 kernel semantics stay
in F018. The separately qualified Metal `newBufferWithBytesNoCopy` path is not
generalized into an MLX zero-copy claim.

## P1 and CI

The P1 handoff requires exact environment/checkpoint identity, one context,
stream origin/ownership, 16 GiB free memory, no competing inference, complete
pre/post accounting, prompt token 9703, expected token 21615, exactly one run,
and a mandatory stop. Final CI evidence is populated after official pinned
MLX/MLX C source builds execute the native adapter matrix without skip.

## Verification questions

1. Are any B1-B4 ownership, callback, singleton, or shape blockers still open?
2. Is the seven-boundary Python/NumPy evidence independent from the Rust
   candidate under test?
3. Does final native CI prove the MLX adapter tests executed rather than
   skipped?
4. Is exactly one bounded M1 Ultra P1 admitted?
