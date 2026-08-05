# Implementation Plan: Qwen3MoE Layer-0 Router Parity

**Branch**: `main` | **Date**: 2026-08-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from
`specs/002-qwen-router-parity/spec.md`

**Status**: Design complete; the foundational methodology and generated
model-free router seam are implemented and validated locally. No external
checkpoint has been accessed for Feature 002 and no real router result exists.

## Summary

Extend the bounded Apple reference path from Feature 001's expert-gate prefix
to the complete real layer-0 router boundary without reopening Feature 001 or
executing an expert. A pinned CPU-only llama.cpp callback first captures a real
post-attention, post-FFN-RMSNorm layer-0 router input from the same immutable
GGUF. A second independent `gguf-py`/scalar-F32 oracle reads the complete F32
router tensor, calculates all 128 logits, performs architecture-correct full
softmax, top-8 selection, and selected-probability renormalization,
cross-checks with NumPy F32, and freezes its outputs before Apple execution. A
separate versioned research-evidence package
and tested statistical method land in a clean commit before the model is
accessed or timing begins. The Apple path then reads only the admitted router
range, evaluates the same boundary through MLX with no fallback, verifies exact
IDs and bounded numerics over repeated single-row and batch cases, and publishes
raw first-process OS-cache-uncontrolled and warm observations without implying
expert, layer, or model inference.

## Technical Context

**Language/Version**: Rust 2021 with rustc 1.97.1; native arm64 CPython 3.12.13
for the locked worker and research scripts; POSIX shell for clean-checkout
orchestration

**Primary Dependencies**: Existing workspace crates; `serde`, `serde_json`,
`sha2`, and `libc` already used by `mlx-backend`; pinned `mlx==0.32.0`; Python
standard library for schema, statistics, tables, and deterministic SVG output;
pinned independent `ggml-org/llama.cpp` revision
`b06aa774c03dbbb624e726664b714a57d1f49815` for CPU capture and `gguf-py`

**Storage**: One authorized external immutable GGUF; exact positional reads for
the approximately 1 MiB router tensor; committed small JSON raw observations,
bounded numerical fixtures, Markdown/CSV tables, deterministic SVG figures,
and SHA-256 manifests; no weights or extracted tensor bytes in Git

**Testing**: Rust unit/integration tests, Python `unittest`, JSON/schema and
semantic mutation tests, deterministic generator tests, fixture-only MLX tests,
exact workspace Cargo gates, and explicit local-only real-checkpoint commands

**Target Platform**: Native arm64 Apple Silicon on macOS 14 or newer; audited
host is macOS 26.0 on Apple M1 Ultra with MLX GPU. Fixture-only CI uses the
standard GitHub `macos-15` arm64 runner. Supported Linux/CUDA runtime validation
is unavailable and must remain unverified.

**Project Type**: Multi-crate Rust runtime, persistent local Python MLX worker,
command-line validation tools, and a versioned research-evidence package

**Performance Goals**: No speed target and no optimization. Collect direct
router-only first-process OS-cache-uncontrolled and warm measurements after
correctness: at least five warm-ups plus ten costly external-operation samples,
at least five warm-ups plus thirty inexpensive warm compute samples, a complete
clean-process replication for each declared major benchmark, and a later second
batch when feasible. The two major benchmarks are the minimally instrumented
single-row and two-row real router cases; stage-instrumented series are
diagnostic only.

**Constraints**: Exact top-8 IDs/order; predeclared logit tolerance
`atol=5e-4, rtol=5e-4`; predeclared complete/selected-probability and
normalized-weight tolerance `atol=1e-6, rtol=1e-6`; canonical float32
little-endian hashes;
identical output hashes across ten repeated Apple executions; explicit GPU,
evaluation, synchronization, and no fallback; full 128-row routing only; no
model data, secrets, private paths, or machine identifiers committed; no custom
Metal; no Linux/CUDA behavior change; protocol frozen before results

**Scale/Scope**: One checkpoint, one layer, one F32 router tensor expected as
GGUF dimensions `[2048,128]` / reader shape `[128,2048]`, 128 logits per hidden
row, top-8 routing, one real single-row fixture, one bounded real multi-row
fixture, one synthetic tie fixture, and required malformed cases. Exact type,
offset, length, and tensor hash remain an admission fact to record before
execution, not a reason to broaden the design.

## Constitution Check

*GATE: Passed before Phase 0 research; re-evaluated after Phase 1 design below.*

| Principle | Feature 002 design evidence | Gate |
| --- | --- | --- |
| I. Correctness Before Optimization | CPU capture and independent scalar/NumPy oracle precede Apple output; tolerances and ten-run determinism are frozen before timing | PASS |
| II. Preserve Linux/CUDA Behavior | Feature is additive under `mlx-backend`, worker, scripts, schemas, fixtures, and docs; inherited selectors and CUDA runtime remain untouched and unclaimed | PASS |
| III. Verified Claims Only | Distinct evidence states, raw attempts, claims ledger, clean commit, exact commands, and explicit unsupported interpretations are mandatory | PASS |
| IV. Apple Silicon First Class | Explicit MLX GPU selection, evaluated synchronization, native environment/resource observations, and no fallback are acceptance gates | PASS |
| V. Portable Interfaces Without Flattening | Shared contracts describe router tensors, outputs, evidence, and errors; MLX process/timing mechanisms remain backend-private | PASS |
| VI. MLX Before Custom Metal | Only the inspectable MLX reference is admitted; custom Metal is an explicit exclusion | PASS |
| VII. Reproducible Benchmarks | Frozen protocol, raw samples, monotonic timing, first-process/warm separation, statistics, replication, load observations, and exact commands are designed before measurement | PASS |
| VIII. Explicit Compatibility | One exact architecture/checkpoint/tensor/dtype/execution depth is admitted; partial expert-gate evidence cannot imply router support | PASS |
| IX. Licensing and Attribution | Same recorded Apache-2.0 Qwen artifact and MIT project attribution are retained; pinned llama.cpp source stays external with its license recorded | PASS |
| X. Incremental Test-Backed Commits | Methodology, contracts, oracle capture, Apple execution, evidence, and CI are separate test-backed milestones | PASS |
| XI. No Secrets or Weights | Model and extracted tensor bytes remain external; evidence is sanitized, bounded, scanned, and append-only | PASS |
| XII. Documentation Is Implementation | Spec Kit artifacts, protocol, raw evidence, tables, figures, claims, reviewer index, limitations, and session log change with their slice | PASS |

No constitutional exception is required. The independent CPU capture may run
the same model graph outside PulsarMLX solely to freeze a real router input and
trusted comparison; it is an oracle, not a second production backend. A model-
shaped synthetic vector is not an acceptable substitute for the real fixture.

## Project Structure

### Documentation (this feature)

```text
specs/002-qwen-router-parity/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/
│   └── requirements.md
├── contracts/
│   ├── router-parity-v1.md
│   ├── research-evidence-v1.md
│   └── commands-v1.md
└── tasks.md
```

### Source Code and Publication Package

```text
crates/mlx-backend/
├── src/
│   ├── router.rs                 # router admission, comparison, evidence
│   └── bin/pulsar-mlx.rs         # additive inspect/validate commands
└── tests/
    ├── router_contract.rs
    └── research_evidence.rs

python/pulsar_mlx_worker/
├── router.py                     # bounded evaluated MLX router operation
└── tests/
    └── test_router.py

fixtures/research/router-v1/
├── README.md
├── manifest.json
├── golden/
├── evidence/
├── expected/
├── real/
├── synthetic-tie.json
└── malformed/

schemas/research/v1/
├── experiment.schema.json
└── router-parity.schema.json

scripts/research/
├── setup.sh
├── prepare_model.sh
├── check_staged.sh
├── capture_router_oracle.sh
├── llama_capture/
│   └── router_capture.cpp       # pinned CPU-only ffn_norm-0 observer source
├── router_oracle.py             # independent scalar/NumPy F32 router oracle
├── environment.py               # public-safe host/resource observations
├── publish_evidence.py          # append-only sanitized raw installation
├── validate_evidence.py
├── statistics.py
├── generate_tables.py
├── generate_figures.py
└── verify_package.py

scripts/research/tests/
├── test_router_oracle.py
├── test_feature002_records.py
├── test_validate_evidence.py
├── test_statistics.py
├── test_generators.py
├── test_timing_policy.py
└── test_verify_package.py

docs/research/
├── EXPERIMENT_PROTOCOL.md
├── REPRODUCIBILITY.md
├── RESULTS.md
├── LIMITATIONS.md
├── CLAIMS_LEDGER.md
├── REVIEWER_INDEX.md
├── MODEL_MANIFEST.json
├── ARTIFACT_MANIFEST.json
├── raw/002-router-parity/
├── tables/
└── figures/
```

**Structure Decision**: Keep Feature 001's `ModelSlice` contract frozen. Add a
separate router module and worker request because the new operation has a
different tensor, output set, repeatability policy, and timing envelope. Keep
generic evidence/statistics/generation scripts feature-neutral so later expert
and layer features can reuse the schema without pretending old Feature 001
records conform to it. Use pure-standard-library table and SVG generation to
avoid adding a plotting stack to the MLX worker environment.

## Phase 0: Research Decisions

Research is recorded in [research.md](research.md). The controlling decisions
are:

1. Admit only `blk.0.ffn_gate_inp.weight`; expected F32 shape is
   `[2048,128]` in GGUF order and `[128,2048]` for execution. Re-inventory the
   exact occurrence, type, offset, length, and tensor hash before execution.
2. Freeze architecture semantics as bias-free F32 projection, full 128-way
   float32 softmax, top-8 selection, selected-probability renormalization, and
   scale 1.0. Lower expert ID wins exact ties only as an explicit PulsarMLX
   deterministic rule; a real cutoff tie is a stop condition for cross-runtime
   parity.
3. Capture only a genuine `ffn_norm-0` router input via a CPU-only pinned
   scheduler callback using direct token IDs `[0,1]`, positions `[0,1]`, a
   two-token context/batch/ubatch, one thread, and no tokenizer selection.
   Freeze row 0 as `qwen3moe-layer0-router-token0-row0-v1` and rows 0–1 as
   `qwen3moe-layer0-router-token0-token1-batch-v1`; stop unless both IDs are in
   vocabulary and the captured rows differ. Prove cancellation before router or
   expert execution. Then independently compute the router with pinned
   `gguf-py` and standalone scalar F32 code, with NumPy only as a cross-check.
   Never relabel Feature 001's prompt-derived activation as real.
4. Introduce `pulsarmlx.research.experiment` and
   `pulsarmlx.research.router-parity` version `1.0.0`; do not retrofit the 14
   heterogeneous Feature 001 JSON records.
5. Freeze Type-7 percentiles, sample standard deviation, and explicit CV rules.
   Keep minimally instrumented totals separate from stage-instrumented timings;
   label first-process reads OS-cache-uncontrolled rather than filesystem-cold.
6. Commit and push methodology, schema, validators, and tests before any model
   access or measurement. Notify `Mahdi-Dev` immediately before that later
   access and when Feature 002 completes or blocks.

## Phase 1: Design Outputs

- [data-model.md](data-model.md) defines immutable model/tensor/input/oracle
  identities, research experiment state, raw observations, statistics,
  correctness, claims, and artifact-manifest relationships.
- [router-parity-v1.md](contracts/router-parity-v1.md) defines the complete
  projection, architecture order, deterministic tie policy, repeated-result,
  malformed-input, and comparison contract.
- [research-evidence-v1.md](contracts/research-evidence-v1.md) defines the
  versioned envelope, raw timing and correctness observations, privacy,
  append-only publication, statistics, and claim admission rules.
- [commands-v1.md](contracts/commands-v1.md) defines planned safe inspection,
  independent oracle capture, local Apple validation, schema validation,
  generation, and package-verification commands and their exit behavior.
- [quickstart.md](quickstart.md) gives the dependency-ordered validation and
  stop sequence. It labels commands as planned until implemented and reserves
  external model access for the post-methodology milestone.

## Delivery Sequence

1. Freeze research protocol, schemas, statistics, privacy rules, generators,
   valid/mutated fixtures, and offline tests; commit, push, and confirm CI.
2. Implement the separate router admission, worker, client, CLI, and oracle
   source seams test-first against generated F32 fixtures while preserving
   Feature 001 types and worker operations; commit, push, and confirm CI.
3. Complete malformed-input, evidence-publication, and timing-instrumentation
   coverage against fixture-only data; commit, push, and confirm CI without
   resolving or opening the checkpoint.
4. Verify the clean offline gate, notify `Mahdi-Dev`, inventory the external
   F32 router tensor, and commit its bounded admission result without Apple
   execution.
5. Build the pinned CPU-only llama.cpp capture helper outside Git, produce two
   identical `ffn_norm-0` captures with cancellation proved before router and
   expert execution, then compute the router independently with `gguf-py` and
   scalar F32 code cross-checked by NumPy. Freeze, commit, and CI-validate only
   legal bounded fixture/oracle values before any Apple output.
6. Run the clean committed local Apple correctness experiment. Stop on any ID,
   ordering, tolerance, identity, cutoff-tie, fallback, or determinism failure.
7. Only after correctness passes, run the frozen first-process-uncontrolled,
   warm, stage-instrumented, minimally instrumented, and replication timing
   batches.
8. Validate, sanitize, and append-only install raw evidence; commit and push
   that raw-data publication first. From that committed raw SHA, regenerate
   tables/figures and update the ledger and reviewer index in a second commit.
   Repeat exact workspace gates, scan staged content, push, confirm fixture-only
   CI, send completion NTFY, and close Feature 002.

Before every commit or push, run the standardized staged safety scan. After
each substantive push, record the actual CI run URL and conclusion in the next
focused task-state/documentation commit. The terminal documentation attestation
and any documentation-only attestation needed to restore a clean/equal branch
before model capture or Apple execution report their own CI conclusions out of
tree rather than creating recursive log-only commits.

## Requirement-to-Design Traceability

| Design boundary | Requirements | Success criteria | Authority |
| --- | --- | --- | --- |
| Immutable checkpoint/router admission | FR-001–FR-003, FR-013, FR-016 | SC-005, SC-010–SC-012 | Router contract and model manifest |
| Independent real input and CPU oracle | FR-003–FR-010 | SC-001–SC-003, SC-005 | Research and router contracts |
| Evaluated Apple execution/repeatability | FR-005–FR-015 | SC-001–SC-005 | Router contract and local command |
| Publication schema/privacy/raw evidence | FR-017–FR-019, FR-026–FR-028, FR-031–FR-032 | SC-006, SC-009, SC-011–SC-012 | Evidence contract, schemas, ledger, reviewer index |
| Timing/statistics/resource protocol | FR-020–FR-025 | SC-007–SC-008 | Experiment protocol and evidence contract |
| CI/local split and notifications | FR-029–FR-030 | SC-009–SC-010 | Commands contract and quickstart |

## Post-Design Constitution Recheck

All twelve gates remain PASS. The design adds no general engine abstraction,
does not touch inherited Linux/CUDA selection, admits no custom Metal or
optimization, keeps model data external, and prevents router measurements from
supporting expert/layer/model/token claims. The two-process reference boundary
is justified by an independent CPU oracle and the existing MLX package/runtime
boundary, with exact version and failure controls. No complexity exception is
required.

## Complexity Tracking

No constitution violation requires an exception.
