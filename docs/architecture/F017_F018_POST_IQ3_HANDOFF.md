# F017 / F018 Post-IQ3 Integration Handoff

## Review binding

- Feature 017 reviewed revision: `c2021e304f146afb9e1ccde86c252f341ab8ef78`
- Feature 018 profiling line began at:
  `6db38f1c937b9ad48321586be85cc558fb48e815`
- No code was merged or cherry-picked during this review.
- IQ2_XXS and IQ3_XXS shader/layout code remains Feature 018-owned.

## Existing generic pieces that fit

Feature 017 already has stable page-aligned slabs, slot generations, a modeled
Apple lifecycle, no-copy registration, checked memory admission, explicit
validation classifications, expert `NativeReadyHot`, broad telemetry buckets,
and a direct-versus-reference parity disposition. Those are the right
foundations.

## Missing format-neutral interfaces

### 1. Typed kernel capability

`BackendCapabilityReport` currently exposes global supported operation and
quantization lists. F018 needs an immutable capability entry keyed by:

- backend and kernel ABI/version;
- quantization and tensor role;
- supported shape/layout and tail rules;
- input/output dtype and accumulation contract;
- alignment/range requirements;
- supported validation modes and qualification evidence version.

Matching must reject an unknown role, shape, layout, or qualification version.
The type must not contain IQ2 or IQ3 bit-layout details.

### 2. Identity-bound native request

Add a request that carries checkpoint set identity, shard/tensor name, checked
byte range, logical shape, quantization, role, native slot ID plus occupancy
generation, activation/output handles, validation policy, fallback policy, and
cancellation token. Interior ranges must be validated against the registered
allocation before dispatch.

### 3. Four explicit dispatch dispositions

The two-state `ProjectionDispatch` is insufficient for F018 telemetry. The
generic result needs distinct states:

- `qualified_direct`;
- `explicit_reference(reason_code)` for intentionally unsupported work;
- `fallback(reason_code)` for a selected capability that could not execute;
- `error(reason_code)` when no result is consumable.

Validation mode must reject fallback/error. Production fallback remains an
explicit caller policy. An intentional reference dispatch is never relabeled
as fallback.

### 4. In-flight completion lease

The current synchronous checksum bridge uses Rust borrow lifetimes, while the
lifecycle state machine is separate. A generic submitted operation needs one
completion lease that retains:

- the Rust allocation owner;
- the Metal registration;
- immutable slot contents and occupancy generation;
- pipeline/command resources required through completion.

Drop, mutation, registration destruction, slot reuse, and generation advance
must fail or wait until completion/cancellation teardown is acknowledged. This
is the reusable form of the F018 completion-handler retention invariant.

### 5. Native-ready trunk residency

F017 models `NativeReadyHot` for experts but trunk `ResidencyClass` has only
compressed, decoded, and transient classes. Add a generic tensor residency key
bound to checkpoint/tensor/range/representation/backend qualification. It must
support one bounded native-ready output-head entry without importing expert
IDs or expert eviction rules.

The first policy consumer should be explicit output-head-only admission. Do not
generalize this into decoded-all trunk residency.

### 6. Stage and scope telemetry

The current five aggregate buckets cannot reproduce F018 evidence. Extend the
format-neutral span/event shape to separate:

- storage;
- decode and materialization;
- registration/import;
- library compile and pipeline creation;
- dispatch preparation;
- kernel execution;
- synchronization/completion;
- residency hit/miss/admission/eviction;
- cancellation/teardown.

Scope should carry layer/expert when present, tensor role, quantization,
capability/qualification version, bytes, requests, and the four-way dispatch
disposition. Aggregates can be derived from these events.

### 7. Bounded multi-operation dispatch

One context currently hosts qualified IQ2 gate/up and IQ3 down pipelines. A
generic request batch should allow a bounded ordered list with a per-operation
capability decision and result while sharing one cancellation/completion
domain. It must not encode gate/up/down as fixed Rust fields.

## ColPanicM2 test request

No full-model or private-checkpoint run is required. Please cover:

1. exact capability match plus role/shape/layout/version rejection;
2. intentional-reference versus fallback/error classification;
3. validation fail-closed and explicit production fallback policy;
4. stale slot/generation and interior-range rejection;
5. submit/wait/destroy, early destroy, early mutation/reuse, and repeated use;
6. cancellation before submit, queued cancellation, completion error, and
   teardown drain;
7. native-ready trunk hit/miss/admission/eviction and output-head-only budget;
8. stage/scope telemetry completeness and checked-counter overflow;
9. bounded multi-operation partial-failure behavior with no consumable partial
   output;
10. a fake/checksum native backend proving ownership and telemetry without
    importing IQ2/IQ3 code.

## Ownership boundary

Feature 017 owns these interfaces, resource policies, and lifecycle mechanics.
Feature 018 retains packed layouts, Metal shader sources, format parameters,
format-specific capability population, IQ2/IQ3 numerical contracts, and real
checkpoint qualification evidence.
