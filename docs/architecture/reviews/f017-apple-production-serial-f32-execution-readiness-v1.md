# F017 Apple production serial-f32 execution readiness v1

This package prepares one future human-gated representative Apple production
serial-f32 equivalence execution. It performs no representative arithmetic,
checkpoint access, comparison, determinism run, approval, or live GO issuance.

## Retained package

The fixed machine-local package contains exactly 40 byte-identical retained
tensors: canonical S0 (1), attention (9), router (3), routed experts (24), and
shared expert (3). Its canonical ordered-descriptor root is
`564a33aee801b4a44e23f3a9b370e1a2ce040dda521dadc4ac54dbfd29045be6`;
the total payload is 257,305,600 bytes. The consumer rehashes every actual file,
rejects missing or extra files, validates every source authority and descriptor,
and rederives the root before attempt creation. A manifest root claim is never
trusted by itself.

Assembly is limited to byte-for-byte copying. The package has no checkpoint
fallback, decoder/re-encoder, conversion, concatenation, or formula-regeneration
surface.

## Code and runtime authority

Execution code is frozen at the committed execution-code-head contract. The
source census includes the native capture runner, MLX projection dispatch,
serial binary32 helpers, capture/receipt/terminal mechanics, and all known
load-bearing quantization sources, including `iq_ref.rs` and
`cpu_dot_tables.rs`.

The future executor is an immutable single-link copy of the reviewed release
binary. Preflight rehashes it and verifies exact MLX-C/MLX linkage, dylib bytes,
Apple M1 Ultra hardware, macOS build, toolchain bindings, and five thread-limit
variables before durable attempt-start. Runtime drift is a pre-attempt failure.

## Comparison and routing

All 34 capture stages are bound to the accepted stage and capture manifests.
Each row is `NOT_EXECUTED` and carries its frozen intended relationship,
retained expectation where available, metrics, tolerances, and failure class.
Proof/reference f64 surfaces remain distinct from production serial-f32.

Routing comparison is ordered and fail-closed: expert membership, expert order,
tie behavior, routing weights, routed expert stages, then routed aggregate.
Numeric closeness cannot repair a structural routing failure.

## Determinism

The future qualification uses ten genuinely fresh processes with identical
package, executable, runtime, environment, authorization, and representative
input. Every one of 34 stage files must be byte-identical across all runs. Any
failure banks all hashes, reports the earliest divergent stage, and blocks an
equivalence claim. No averaging or tolerance can conceal nondeterminism.

## Single use and accounting

The future event is a retained-only real execution event with zero new payload
consumption: master ledger 175 to 175. It still requires an event result,
receipts, terminal state, and same-commit master-ledger validation. Counts are
derived from receipts; `terminal.json` is not sole accounting authority.

The approval and GO schemas bind the exact reviewed head, code, executable,
runtime, package, stage/capture/comparison/determinism contracts, wrapper,
terminalizer, ledger, attempt, output root, and human approval identity. Normal
validation cannot create a live token. A live token requires an explicit future
operator-only command and is single-use with no retry or resume.

RN1 requires exclusive attempt ownership, durable owned attempt and execution
starts before arithmetic, invocation-owned cleanup, receipt-derived accounting,
and fail-closed reconciliation. Wrapper v1 remains tombstoned.

## Operator boundary

After independent acceptance, the only remaining operator choice is whether to
authorize exactly one execution against the reviewed package and code. No
tolerance, tensor, model path, decoder, runtime, stage, comparison order, retry,
or ledger choice remains open. This document and its contracts do not authorize
or execute that event.
