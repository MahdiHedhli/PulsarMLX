# ADR 0005: Keep the MLX boundary narrow and native

- **Status**: Accepted for Feature 017 infrastructure; official CPU/GPU managed import is qualified with initialized handles and explicit stream synchronization
- **Date**: 2026-08-10

## Decision

Rust owns the shipping runtime and exposes a small, versioned C ABI for the
Apple-specific MLX adapter. The adapter is implemented in Objective-C++ so it
can coordinate MLX, Metal, Objective-C ownership, and command-completion
fences without exposing C++ or Objective-C types to Rust.

The adapter may call an official supported MLX native C or C++ API when the
pinned deployment can prove all of the following:

- construction from a Rust-owned or Metal-visible buffer does not introduce an
  unreported copy;
- the buffer owner outlives every MLX operation and completion fence;
- synchronization and error propagation are explicit;
- teardown cannot destroy a buffer while an MLX or Metal command is in flight;
- the API is available under the project macOS deployment and build policy.

For unsupported versions or environments, the adapter exposes capability
discovery and fail-closed operation only. Existing Python/MLX functionality
remains the research/reference path, not a required shipping process.

## ColPanicM2 qualification evidence

The installed native environment on 2026-08-10 contains MLX C 0.6.0_2 and
MLX 0.31.2 under Homebrew, while the project Python reference path currently
pins MLX 0.32.0. The public-safe probe in
`scripts/research/f017_mlx_c_qualification.cpp` passed the following CPU
checks:

- `mlx_array_new_data_managed_payload` accepted a 4096-byte-aligned host buffer.
- `mlx_array_eval` followed by `mlx_synchronize` completed deterministically.
- `mlx_array_data_float32` returned the same host pointer for this CPU array.
- `mlx_array_free` invoked the ownership callback exactly once, followed by
  explicit stream teardown.

The standalone lifecycle matrix in
`docs/architecture/reviews/f017-mlx-gpu-teardown-forensics.md` also passed the
GPU managed-array path, including initialized `mlx_get_default_stream`, owned
streams, explicit synchronization, stream-first and array-first teardown,
same-process reuse, and copy-backed controls. Every variant passed its
30-repeat matrix; the copy-backed GPU control passed 100/100.

The earlier exit-134 result was caused by passing an uninitialized
`mlx_stream` output object to `mlx_get_default_stream`. The minimized child
stopped before array import at `libmlxc.dylib` `mlx_get_default_stream + 52`.
Initializing the output with `mlx_stream_new()` removes the failure. This is a
probe contract correction, not an upstream MLX managed-buffer defect.

The qualified MLX C contract is not a general MLX/Metal zero-copy claim. It
requires initialized handles, explicit `mlx_synchronize(stream)`, and retaining
the host owner through array and dependent stream teardown. Rust slab to Metal
`newBufferWithBytesNoCopy` remains a separate direct path.

The actual Rust/Objective-C++ adapter is implemented in
`crates/stream/src/apple_mlx_bridge.rs` and
`crates/stream/src/apple_mlx_bridge.mm`. Its native tests cover CPU and GPU
managed imports, borrowed/default and owned streams, explicit operations and
synchronization, pointer identity, exactly-once callbacks, 30 borrowed cycles,
100 owned cycles, and fail-closed invalid imports. Builds without the native
MLX C installation compile with an explicit adapter-test skip.

## Options considered

| Option | Decision | Reason |
| --- | --- | --- |
| Official MLX C API called directly from Rust | Not the primary boundary | C ownership may be usable, but Rust would still need an Apple-specific lifetime and synchronization layer. Direct binding also couples the runtime to the exact exposed API surface. |
| Narrow C ABI shim implemented in C++ | Retained as the ABI shape | Opaque handles, pointer/length validation, explicit release, and status/error codes are stable for Rust and testable without leaking C++ types. |
| Objective-C++ adapter | Selected implementation boundary | It can own MLX/Metal objects, bridge `newBufferWithBytesNoCopy`, and enforce completion-before-release ordering in one Apple-specific component. |
| Unofficial Rust MLX binding | Rejected for Feature 017 | It adds API and ownership risk without evidence that it supports native-buffer import, synchronization, deployment, and maintenance requirements. |
| Python worker process | Research-only | It violates the no-required-Python shipping target and hides process, copy, and teardown costs behind a subprocess protocol. |

## Ownership contract

Rust retains ownership of page-aligned slab storage and the residency slot ID.
The adapter may retain an opaque registration handle, but never the Rust
allocation independently. A registration release must occur before the Rust
slot is released or reused. Every asynchronous operation must return a
completion token or an explicit failure; dropping an in-flight handle is not a
valid cancellation protocol.

The existing Metal no-copy bridge is evidence for stable Rust-owned storage
registration, not evidence that MLX imports that storage without copying.
That MLX-specific copy boundary remains an explicit Feature 017 qualification
gate.

## Consequences

- Rust policy, memory admission, residency, telemetry, cancellation, and
  fallback remain backend-neutral.
- Objective-C++ is limited to native object construction, buffer registration,
  synchronization, and error translation.
- The same ABI can support a qualified direct Metal path later without making
  Feature 017 select a Feature 018 kernel.
- MLX version, macOS deployment, storage mode, copy behavior, and teardown
  evidence must be recorded with every qualified native fixture.
- A failed native import or unavailable API must fall back explicitly to the
  reference path; it must not silently spawn Python from the shipping runtime.

## Required qualification before production use

1. Construct a native array or equivalent MLX object from a registered
   Rust-owned buffer and record whether a copy occurred.
2. Submit a deterministic no-op or checksum operation, wait for completion,
   and compare the result with a CPU reference.
3. Reuse the same registration across multiple submissions without
   unregister/register churn.
4. Exercise cancellation and destruction while work is pending, failing
   closed if the API cannot make ordering explicit.
5. Record the macOS version, MLX version, compiler/toolchain, storage mode,
   pointer alignment, and ownership evidence.
