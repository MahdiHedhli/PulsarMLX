# F017/F018 native kernel boundary v1

Feature 017 supplies runtime ownership and qualification contracts. Feature
018 supplies direct quantized kernels. The boundary is intentionally narrow so
Feature 018 can advance without moving model lifecycle or memory policy into a
kernel implementation.

## Capability discovery

The runtime asks a backend for a capability record containing:

- architecture and backend ID;
- tensor role and quantization format;
- supported dimensions/layouts and alignment requirements;
- kernel ABI and qualification version;
- supported validation modes;
- whether the path is direct/native or reference/fallback.

Unknown capability versions fail closed. Capability discovery must not select a
kernel from a benchmark name or from an unqualified format string alone.

## Dispatch and ownership

Rust resolves the tensor catalog entry, residency tier, memory admission, and
stable slot. It passes an opaque native-buffer registration plus a checked
interior range only after the registration lifetime is established. Feature
018 must not retain a raw pointer after the dispatch completion fence.

The native adapter returns an explicit completion or error. Rust releases or
reuses the slot only after completion. Protected shared-expert slots remain
under Rust residency policy; a kernel cannot evict them.

## Qualified versus reference path

Every dispatch records one of:

- `qualified_direct`: capability and exact/numerical validation gates passed;
- `reference_fallback`: direct capability unavailable, rejected, cancelled, or
  not yet qualified.

Fallback is deterministic and visible in telemetry. A direct path must never
silently become a Python subprocess path in the shipping runtime.

## Validation and telemetry

Dispatch accepts the mode-aware validation policy:

- `golden_strict` stops on the first greedy mismatch;
- `teacher_forced_validation` continues on frozen reference tokens and records
  numerical deltas.

Each dispatch records layer/expert scope and separate storage, decode,
materialization, backend-import/build, and compute attribution. It also
records request count, bytes, kernel ABI/qualification version, and fallback
reason when applicable.

## Error and cancellation rules

Malformed ranges, unsupported layouts, insufficient admission, stale slot
registrations, unavailable devices, cancellation, and completion failures are
explicit errors. No partial output is consumable after an error. The runtime
must release transient resources in a defined order and preserve the Rust
owner until the native completion fence has resolved.

## Scope boundary

This contract does not select a Feature 018 kernel target, define a fused MoE
algorithm, or claim direct-kernel performance. It only defines how a future
qualified capability can be discovered, invoked, measured, and rejected safely.
