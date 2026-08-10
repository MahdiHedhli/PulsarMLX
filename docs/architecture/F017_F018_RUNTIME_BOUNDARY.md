# Feature 017 / Feature 018 Runtime Boundary

## Decision

Feature 017 owns reusable shipping-runtime plumbing. Feature 018 owns
format-specific direct-quantized Metal experiments and their qualification.
The branches remain independent; reviewed infrastructure crosses the boundary
only through focused commits or an explicit later integration change.

## Feature 017 shared runtime plumbing

- Stable, page-aligned compressed slabs and generation-protected slot reuse.
- No-copy Metal registration lifecycle and in-flight completion safety.
- Generic backend timing, dispatch, failure, and resource telemetry.
- Native-ready compressed residency representation and bounded admission.
- Generic direct/reference dispatch contract.
- Validation-mode fail-closed semantics: a selected direct operation that
  fails cannot recover to reference and produce a passing validation record.
- Explicit production fallback policy and telemetry, if the product later
  chooses to support it.

These mechanisms must not encode IQ2_XXS block layout, GLM tensor names, or a
specific shader geometry.

## Feature 018 format-specific ownership

- IQ2_XXS packed layout and lookup-table identities.
- The deterministic one-thread-per-row Metal qualification scaffold.
- IQ2_XXS parameter validation and packed GEMV dispatch.
- IQ2_XXS numerical qualification, evidence schema, and benchmark ladder.
- Any future IQ2 performance kernel and its separate Tier-B qualification.
- Any future IQ3 implementation after its own admission gate.

Feature 018 can consume the shared ownership and telemetry contracts but does
not become the permanent allocator, cache policy, scheduler, or generation
loop.

## Current integration state

The Feature 018 branch selectively carries reviewed stable-slab and no-copy
registration lineage. Its post-Opus hardening adds completion-handler retention
and native in-flight accounting that are candidates for a focused Feature 017
integration review. No wholesale branch merge has occurred.

The Python worker remains a bounded research bridge. A shipping runtime should
invoke the same generic native contract from Rust orchestration without a
required Python process. The current bridge result does not claim that Feature
017 integration is complete.

## Review gate

Before shared runtime code is moved between features:

1. review the focused diff and license lineage;
2. retain platform gating and Linux/CUDA behavior;
3. run native lifetime, malformed-input, and generation tests;
4. keep format-specific shader/layout code behind an explicit capability;
5. preserve the Python/NumPy oracle and deterministic Metal scaffold;
6. record the exact commits integrated rather than merging unrelated work.
