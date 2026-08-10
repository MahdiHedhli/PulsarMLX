# PulsarMLX Feature 017 M1 Ultra P1 handoff

Status: prepared, not executed on ColPanicM2.

## Preconditions

- Reconcile `feat/017-rust-native-inference-runtime` against origin and record
  the exact final SHA before starting.
- Verify checkpoint identity, immutable revision, and fixture/evidence hashes.
- Use the M1 Ultra under normal memory pressure with no competing inference,
  conversion, or unrelated GPU workload.
- Qualify the production Rust/Objective-C++ MLX adapter on the M1 Ultra first.
  Require initialized MLX output handles, explicit submission-stream
  synchronization, owner-last teardown, and exactly-once callbacks.
- Keep validation fail-closed. Unexpected backend errors or fallback are a
  failed P1, not a reference success.
- Require at least `17179869184` bytes (16 GiB) of free memory immediately
  before P1 admission. Record the measurement and reject the run below this
  absolute floor; normal-pressure labels alone are insufficient.
- Record macOS build, MLX C/native version, Metal version/driver context, and
  Xcode/compiler versions where available.
- Record the adapter stream mode as `borrowed_default` or `owned` and assert it
  matches the selected path.
- Assert exactly one MLX-using F017 context exists in the process.
- Assert pre-run managed/derived/callback counters are zero and post-run
  managed callbacks, managed array lifecycle, and derived lifecycle reconcile
  exactly. Derived arrays must be reported separately from managed callbacks.

## Single bounded run

- Run exactly one Feature 017 P1.
- Use prompt token `9703`.
- Expected first generated token: `21615`.
- Use a fresh evidence directory bound to branch SHA, checkpoint identity,
  fixture version, host, OS, MLX version, and adapter build.
- Stop after P1 and report before any P2 or golden-eight decision.

## Required evidence

Record separately and with timestamps:

- cold stack/logits boundary;
- first generated token and validation classification;
- terminal warm stack boundary;
- backend, direct, and explicit-reference dispatch counts;
- storage, decode, materialization, backend import/build, compute, and
  orchestration telemetry;
- compressed, decoded-hot, native-ready-hot, transient, and protected-shared
  residency state;
- memory admission, RSS/pressure, slot reuse, registrations, generations,
  teardowns, and every fallback or error reason.

## Stop rules

- Stop immediately on numerical mismatch, unexpected fallback, memory admission
  failure, adapter lifecycle failure, callback imbalance, stale generation, or
  unexplained error.
- Do not run P2, golden-eight, or any broader inference claim without a separate
  admission decision after the P1 report.
