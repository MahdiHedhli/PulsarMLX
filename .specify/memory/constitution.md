<!--
Sync Impact Report
- Version change: template -> 1.0.0
- Modified principles: none; initial ratification
- Added principles:
  - I. Correctness Before Optimization
  - II. Preserve Upstream Linux and CUDA Behavior
  - III. Verified Claims Only
  - IV. Apple Silicon Is a First-Class Backend
  - V. Portable Interfaces Without Lowest-Common-Denominator Design
  - VI. MLX Reference Before Custom Metal
  - VII. Reproducible Benchmarks
  - VIII. Explicit Model and Quantization Compatibility
  - IX. Clean Licensing and Upstream Attribution
  - X. Incremental, Test-Backed Commits
  - XI. No Secrets or Model Weights
  - XII. Documentation Is Part of the Implementation
- Added sections:
  - Platform and Compatibility Constraints
  - Specification-Driven Development Workflow
- Removed sections: none
- Follow-up TODOs: none
-->
# PulsarMLX Constitution

## Core Principles

### I. Correctness Before Optimization

Every backend operation MUST have a correctness oracle, an explicit tolerance
where floating-point comparison is involved, and a reproducible validation
case before performance work begins. Optimizations MUST preserve the validated
result and MUST be reversible in a focused change. Throughput, memory use, or
latency improvements do not justify an unmeasured correctness regression.

### II. Preserve Upstream Linux and CUDA Behavior

The inherited Linux/CUDA path MUST remain behaviorally unchanged unless a
separately specified upstream-compatible fix is required. Apple work MUST be
additive or selected through explicit backend capabilities. Changes touching
shared parsing, tokenization, storage, quantization, or model metadata MUST run
the portable macOS baseline and receive Linux/CUDA validation on supported
hardware or CI before being described as cross-platform-safe.

### III. Verified Claims Only

Documentation, commit messages, benchmark reports, and release notes MUST
distinguish observed results from expectations and plans. A capability MUST
NOT be described as working until its exact command, environment, input, and
result have been recorded. Excluded tests, unavailable hardware, warnings, and
failed checks MUST be reported with the successful evidence.

### IV. Apple Silicon Is a First-Class Backend

Apple Silicon MUST have explicit backend selection, capability reporting,
tests, memory-accounting rules, error messages, and documentation. It MUST NOT
be modeled as a CUDA-shaped compatibility shim. Unified memory, Metal-backed
MLX execution, macOS storage semantics, and arm64 CPU fallbacks MUST be treated
as native design inputs while shared model semantics remain portable.

### V. Portable Interfaces Without Lowest-Common-Denominator Design

Shared interfaces MUST express stable model and storage semantics rather than
CUDA streams, raw device pointers, MLX implementation details, or a forced
intersection of backend features. Backend-specific optimized operations MAY
exist behind explicit capability contracts. Unsupported operations MUST fail
clearly instead of silently choosing a lower-quality or numerically different
path.

### VI. MLX Reference Before Custom Metal

The first Apple execution path MUST use correct, inspectable MLX operations.
Custom Metal kernels, graph fusion, unsafe zero-copy aliasing, and comparable
low-level optimizations MUST NOT begin until the corresponding MLX reference
operation and parity test pass. Any later custom kernel MUST retain the MLX or
scalar reference as a test oracle.

### VII. Reproducible Benchmarks

Every published performance result MUST record the commit, machine and memory,
macOS and tool versions, model identity and checksum or immutable revision,
quantization, context shape, cache state, storage placement, warm-up policy,
sample count, and exact command. Comparisons MUST change one declared variable
at a time and MUST include correctness validation before timing.

### VIII. Explicit Model and Quantization Compatibility

Support MUST be recorded as a matrix of model architecture, checkpoint format,
tensor layout, quantization, execution phase, and backend. Synthetic coverage,
small real-model coverage, and giant-model coverage MUST be labeled
separately. Unknown tensor types, shapes, orientation, block tails, or model
metadata MUST produce bounded errors rather than implicit reinterpretation.

### IX. Clean Licensing and Upstream Attribution

The upstream MIT license, Git history, copyright notices, and Pulsar
attribution MUST remain intact. PulsarMLX documentation MUST identify its
modifications, link the upstream repository, avoid implying upstream
endorsement, and state that upstream maintainers are not responsible for fork
changes. Third-party code or data MUST include compatible licensing and
provenance before it is committed.

### X. Incremental, Test-Backed Commits

Work MUST proceed in the smallest independently reviewable vertical slices.
Each behavior-changing commit MUST include or cite a failing-then-passing test
or another explicit validation artifact. Commits MUST preserve a buildable
branch, avoid unrelated formatting churn, and keep implementation, generated
specification, and evidence changes coherent and reviewable.

### XI. No Secrets or Model Weights

Credentials, tokens, private keys, shell history, private configuration,
non-public personal data, sensitive machine identifiers such as serial numbers
and hardware UUIDs, and proprietary or large model weights MUST NOT enter Git
history. GGUF, safetensors, checkpoints, benchmark dumps, and local caches MUST
remain outside version control unless a tiny, licensed fixture is explicitly
reviewed for provenance and size. Staged content MUST receive a secret and
large-file review before every push.

### XII. Documentation Is Part of the Implementation

Feature specifications, plans, interface contracts, compatibility matrices,
validation commands, limitations, benchmark methods, and session handoff notes
MUST be updated in the same bounded change as the behavior they describe. A
feature is incomplete when another developer cannot reproduce its result or
understand its exclusions from committed documentation.

## Platform and Compatibility Constraints

- GitHub Spec Kit artifacts under `.specify/` and `specs/` are the source of
  truth for feature requirements and implementation planning.
- Existing Linux, CUDA, `io_uring`, GGUF, tokenizer, quantization, and API
  behavior are compatibility constraints, not automatic design templates for
  the Apple backend.
- The initial Apple sequence is: macOS build baseline, MLX device smoke test,
  tensor execution proof, expert-storage abstraction, quantized reference
  operations, synthetic routed-MoE validation, then the lowest-cost compatible
  real-model vertical slice.
- Real-model and performance claims require legally accessible inputs and
  recorded provenance. Model files stay outside Git.
- Custom Metal work and giant-model tuning are out of scope until the correct
  MLX reference path and bounded parity evidence exist.

## Specification-Driven Development Workflow

1. Begin each feature with `$speckit-specify` and complete its requirements
   checklist before planning.
2. Use `$speckit-plan` to record research decisions, data and state models,
   backend/storage contracts, constitution gates, and a runnable quickstart.
3. Use `$speckit-tasks` to produce dependency-ordered, story-aligned,
   test-backed increments. Run `$speckit-analyze` before implementation.
4. For Rust changes, run the narrowest relevant tests plus
   `cargo check --workspace --all-targets` and
   `cargo test --workspace --no-fail-fast` before handoff.
5. Treat repository-wide rustfmt and strict Clippy failures as recorded debt
   until a dedicated cleanup is specified; do not hide new failures in that
   debt.
6. Record exact commands, actual results, warnings, excluded coverage, and
   benchmark context in committed documentation.
7. Review the staged diff for scope, attribution, secrets, weights, generated
   binaries, and unintended upstream behavior before each focused commit.

## Governance

This constitution is the highest-authority project governance document.
Feature specifications, plans, tasks, reviews, and commits MUST include a
constitution-compliance check. A proposed exception MUST be documented in the
feature plan with its scope, evidence, risk, expiration or removal condition,
and reviewer approval; convenience alone is not justification.

Amendments require a dedicated documentation change that explains the
rationale and migration impact, updates the Sync Impact Report, and changes
the version according to semantic versioning:

- MAJOR for removing or incompatibly redefining a principle;
- MINOR for adding a principle or materially expanding governance; and
- PATCH for non-semantic clarification.

The ratification date remains fixed. The last-amended date changes whenever
normative content changes. Reviews MUST reject undocumented capability claims,
missing validation evidence, attribution regressions, secret/weight exposure,
or implementation that bypasses the active Spec Kit artifacts.

**Version**: 1.0.0 | **Ratified**: 2026-08-05 | **Last Amended**: 2026-08-05
