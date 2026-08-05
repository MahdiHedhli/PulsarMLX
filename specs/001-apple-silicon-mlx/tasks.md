# Tasks: Apple Silicon MLX Backend Bring-Up

**Input**: Design documents from `specs/001-apple-silicon-mlx/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/`, and `quickstart.md`

**Tests**: The feature specification requires independent fixtures, contract
tests, malformed-input tests, scalar/trusted oracles, exact workspace gates,
and evidence for every completed slice. In each story, write the listed tests
and observe their relevant failure before implementing the behavior.

**Organization**: Setup and foundational work establish shared contracts. Each
subsequent phase is a user-story increment with an independent checkpoint.
Model files, credentials, local caches, and private machine identifiers remain
outside Git throughout.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it changes different files and does not
  depend on another incomplete task in the same phase.
- **[US#]**: Maps the task to a user story from `spec.md`.
- Every task names the exact file or files it creates or changes.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Reconfirm the inherited baseline, establish the two additive Rust
crate roots, and pin the local Python worker environment without touching the
Linux/CUDA defaults.

- [X] T001 Record a fresh clean-checkout status, remotes, tool versions, exact `cargo check --workspace --all-targets`, and exact `cargo test --workspace --no-fail-fast` actual result in `docs/validation/implementation-baseline.json`; stop setup if the verified macOS baseline regresses
- [X] T002 [P] Create the backend-neutral crate manifest and empty compiling library target in `crates/backend/Cargo.toml` and `crates/backend/src/lib.rs`
- [X] T003 [P] Create the Apple worker-client crate manifest, empty compiling library target, and CLI target in `crates/mlx-backend/Cargo.toml`, `crates/mlx-backend/src/lib.rs`, and `crates/mlx-backend/src/bin/pulsar-mlx.rs`
- [X] T004 Add `crates/backend` and `crates/mlx-backend` as additive workspace members without changing inherited members, features, or defaults in `Cargo.toml`
- [X] T005 [P] Define the native CPython package and exact `mlx==0.32.0` Darwin arm64 dependency policy in `pyproject.toml` and create the package marker in `python/pulsar_mlx_worker/__init__.py`
- [X] T006 Resolve and commit the reproducible worker dependency graph with a matching prebuilt arm64 MLX wheel in `uv.lock`; stop if resolution requires an unpinned version, source build, unsupported Python, or non-arm64 artifact

**Checkpoint**: Both new crates compile as empty additive members, `uv sync
--frozen` is resolvable on the supported host, the inherited baseline remains
recorded, and no Apple backend capability is claimed yet.

---

## Phase 2: Foundational Contracts (Blocking Prerequisites)

**Purpose**: Implement backend-neutral state, tensor, compatibility, and
evidence types that every story uses. This phase blocks all user-story work.

### Tests for foundational contracts

- [X] T007 [P] Write failing tests for explicit backend selection, `allow_fallback=false`, capability-state transitions, and rejection of an unevaluated success claim in `crates/backend/tests/capability_contract.rs`
- [X] T008 [P] Write failing tests for checked tensor shapes, storage orientation, exact byte counts, dtype/layout admission, synchronization metadata, and bounded comparison policies in `crates/backend/tests/tensor_contract.rs`
- [X] T009 [P] Write failing tests for validation, quantization, model-compatibility, benchmark, and evidence-status invariants in `crates/backend/tests/evidence_contract.rs`

### Implementation for foundational contracts

- [X] T010 Implement bounded common error categories without backend-specific objects or private path disclosure in `crates/backend/src/error.rs`
- [X] T011 Implement `BackendSelection`, `BackendCapabilityReport`, device states, explicit exclusions, and legal immutable transitions in `crates/backend/src/capability.rs`
- [X] T012 Implement checked `TensorContract`, comparison policy/result, shape-product, layout, dtype, byte-count, and synchronization validation in `crates/backend/src/tensor.rs`
- [X] T013 Implement quantization/model compatibility records, validation cases, evidence states, independent memory gauges, and correctness-gated benchmark records in `crates/backend/src/evidence.rs`
- [X] T014 Export the foundational API and pass all foundational tests without exposing CUDA, Python, or MLX implementation types in `crates/backend/src/lib.rs`

**Checkpoint**: `cargo test -p backend` passes, every invalid foundational
state is rejected, and the common contract remains semantic rather than a
lowest-common-denominator device API.

---

## Phase 3: User Story 1 - Establish a Trustworthy Apple Baseline (Priority: P1) 🎯 MVP

**Goal**: Start one bounded persistent worker, negotiate protocol v1, and prove
an explicitly selected MLX GPU operation was evaluated, synchronized, and
numerically correct without CPU fallback.

**Independent Test**: On a supported native Apple Silicon host, run the fake
worker contract suite and the real `device-smoke` command. The evidence reports
`evaluated` only after the exact MLX version, Metal/GPU identity, explicit GPU
matmul, evaluation, synchronization, and independent numeric comparison pass.

### Tests for User Story 1 (write and observe failure first)

- [X] T015 [P] [US1] Write failing Python protocol tests for fragmentation, size/depth/list limits, invalid UTF-8/JSON/envelopes, request IDs, protocol/version mismatch, stdout purity, and shutdown in `python/pulsar_mlx_worker/tests/test_protocol.py`
- [X] T016 [P] [US1] Write failing Rust fake-worker contract tests for hello negotiation, timeout, EOF, crash, nonzero exit, stdout contamination, request ordering, structured errors, and forced-cleanup reporting in `crates/mlx-backend/tests/worker_contract.rs`
- [X] T017 [P] [US1] Write a failing Apple-only device test that rejects non-arm64, wrong MLX version, unavailable Metal/GPU, CPU fallback, unevaluated work, and numerical mismatch in `crates/mlx-backend/tests/device_smoke.rs`

### Implementation for User Story 1

- [X] T018 [P] [US1] Implement bounded UTF-8 NDJSON v1 framing, envelopes, stable error codes, request validation, and protocol-only stdout in `python/pulsar_mlx_worker/protocol.py`
- [X] T019 [P] [US1] Implement sanitized host/runtime discovery, explicit GPU selection, Metal availability checks, evaluated nonsymmetric matmul, synchronization, comparison, and independent memory gauges in `python/pulsar_mlx_worker/runtime.py`
- [X] T020 [US1] Implement the persistent hello/health/tensor_probe/shutdown loop with diagnostics only on stderr and bounded graceful cleanup in `python/pulsar_mlx_worker/__main__.py`
- [X] T021 [P] [US1] Implement Rust protocol-v1 envelopes, limits, response-ID matching, error decoding, and capability negotiation in `crates/mlx-backend/src/protocol.rs`
- [X] T022 [US1] Implement one-worker-per-context spawn, pipe ownership, deadlines, lifecycle state machine, crash handling, and controlled shutdown in `crates/mlx-backend/src/client.rs`
- [X] T023 [US1] Implement explicit `apple-mlx` construction and the `device-smoke` CLI without inherited-backend auto-selection in `crates/mlx-backend/src/lib.rs` and `crates/mlx-backend/src/bin/pulsar-mlx.rs`
- [X] T024 [US1] Run the exact fake-worker, Python, and real Apple device commands and commit the sanitized actual capability/comparison result, warnings, and exclusions in `docs/validation/mlx-device-smoke.json`
- [X] T025 [US1] Update the runnable device command, stop conditions, actual capability boundary, and remaining exclusions in `specs/001-apple-silicon-mlx/quickstart.md`, `docs/apple-silicon/SESSION_LOG.md`, and `docs/apple-silicon/KNOWN_LIMITATIONS.md`
- [X] T026 [US1] Re-run the exact workspace check/test gates and record their actual result alongside the US1 evidence in `docs/validation/mlx-device-smoke.json`

**Checkpoint**: US1 is complete only when worker contract tests pass and the
real evidence says either `passed` with an evaluated GPU proof or a truthful
`blocked` result. Import success, allocation, queued work, or CPU execution is
never an MVP pass.

---

## Phase 4: User Story 2 - Prove Tensor and Quantized Operations (Priority: P2)

**Goal**: Prove every primitive needed by the first slice with deterministic
shape/layout/dtype contracts, predeclared tolerances, a strict scalar Q8_0
oracle, evaluated MLX parity, and malformed-input rejection.

**Independent Test**: Run the backend, strict Q8_0, Python worker, and Rust
integration suites plus `validate-fixtures`; all valid fixtures match their
independent oracle and all malformed cases fail before MLX execution.

### Tests for User Story 2 (write and observe failure first)

- [X] T027 [US2] Freeze nonsymmetric inputs, expected values, tensor orientation, dtypes, synchronization rules, and pre-result tolerances for elementwise, matmul, embedding, RMS norm, residual, routing, and Q8_0 cases in `fixtures/mlx/manifest.json`
- [X] T028 [P] [US2] Write failing strict Q8_0 decode/matvec tests for hand-built blocks, signed extrema, two scales, exact byte counts, divisibility, overflow, destination size, and non-finite rejection in `crates/quant/tests/q8_0_reference.rs`
- [X] T029 [P] [US2] Write failing Python fixture-operation tests that use independent expected values and prove malformed descriptors are rejected before MLX scheduling in `python/pulsar_mlx_worker/tests/test_tensor_ops.py`
- [X] T030 [P] [US2] Write failing Rust integration tests for bounded tensor requests, orientation-visible outputs, evaluated readback, error metrics, and request/result schema enforcement in `crates/mlx-backend/tests/tensor_contract.rs`

### Implementation for User Story 2

- [X] T031 [P] [US2] Implement panic-free strict Q8_0 row decode and scalar matvec with checked 32-element/34-byte block arithmetic in `crates/quant/src/q8_0_ref.rs` and export only the reviewed entry points from `crates/quant/src/lib.rs`
- [X] T032 [P] [US2] Implement explicit-device fixture tensor operations, forced evaluation/synchronization, bounded readback, and comparison summaries in `python/pulsar_mlx_worker/tensor_ops.py`
- [X] T033 [US2] Add the version-compatible fixture operation schemas and Rust client methods without allowing numeric-list or base64 weight transfer in `python/pulsar_mlx_worker/protocol.py`, `crates/mlx-backend/src/protocol.rs`, and `crates/mlx-backend/src/client.rs`
- [X] T034 [US2] Implement `validate-fixtures` with exact manifest identity, result cardinality, maximum errors, and first bounded mismatch in `crates/mlx-backend/src/bin/pulsar-mlx.rs`
- [X] T035 [US2] Execute the complete fixture suite and commit exact commands, actual results, oracle identities, tolerances, warnings, exclusions, and independent memory gauges in `docs/validation/mlx-tensor-fixtures.json`
- [X] T036 [US2] Record Q8_0 support separately by tensor role and by scalar/MLX evidence level in `docs/apple-silicon/COMPATIBILITY.md` and update actual US2 boundaries in `docs/apple-silicon/SESSION_LOG.md`
- [X] T037 [US2] Re-run the exact workspace gates after the shared quant change and append actual macOS results plus an explicit pending Linux/CUDA evidence status in `docs/validation/mlx-tensor-fixtures.json`

**Checkpoint**: US2 is independently complete when every admitted operation
has a passing oracle and evaluated MLX case, all malformed fixtures are
rejected, and Q8_0 support is scoped to proven tensor roles. No tolerance may
be tuned after observing the Apple result.

---

## Phase 5: User Story 3 - Validate Portable Expert Routing and Storage (Priority: P3)

**Goal**: Add an exact owned positional source without replacing the inherited
Linux fetcher, then prove deterministic routing and weighted expert aggregation
through a small generated split-shard fixture.

**Independent Test**: Run positional-source, inherited-path selection,
routing-oracle, worker, and synthetic-MoE integration suites. Exact valid bytes,
every specified invalid range, tie order, repeated experts, normalized weights,
and final output must match their independent contracts.

### Tests for User Story 3 (write and observe failure first)

- [X] T038 [US3] Define a deterministic reviewable multi-expert split-shard fixture, generation recipe, expected logical ranges, routes, tie order, weights, output, and license/provenance in `fixtures/mlx/routed-moe-v1.json`
- [X] T039 [P] [US3] Write failing portable-source contract tests for layouts, checked ranges, exact boundaries, injected partial/Interrupted/zero reads, truncation, batch ordering/all-or-error, and owned-payload lifetime in `crates/stream/tests/positional_source.rs`
- [X] T040 [P] [US3] Write Linux-only regression tests that keep the existing `io_uring` API, selection, aligned payload mapping, and short-payload failure semantics explicit in `crates/stream/tests/linux_uring_preservation.rs`
- [X] T041 [P] [US3] Write failing scalar and worker tests for finite scores, top-k bounds, score-descending/expert-ID-ascending ties, repeated experts, normalized weights, and weighted aggregation in `crates/backend/tests/routing_contract.rs` and `python/pulsar_mlx_worker/tests/test_routed_moe.py`
- [X] T042 [P] [US3] Write a failing end-to-end contract test for exact expert payloads and the synthetic routed output in `crates/mlx-backend/tests/synthetic_moe.rs`

### Implementation for User Story 3

- [X] T043 [P] [US3] Implement validated single/split shard layouts, exact positional-read loops, structured errors, non-cloneable owned payloads, and ordered all-or-error batches in `crates/stream/src/positional.rs` and export the additive surface from `crates/stream/src/lib.rs`
- [X] T044 [P] [US3] Implement deterministic backend-neutral top-k selection, tie-breaking, normalization, request planning, and scalar aggregation oracle in `crates/backend/src/routing.rs` and export it from `crates/backend/src/lib.rs`
- [X] T045 [P] [US3] Implement the evaluated MLX routed-expert fixture graph and bounded result/memory summary in `python/pulsar_mlx_worker/moe.py`
- [X] T046 [US3] Add bounded synthetic-MoE protocol/client operations and `validate-synthetic-moe` CLI wiring in `python/pulsar_mlx_worker/protocol.py`, `crates/mlx-backend/src/client.rs`, and `crates/mlx-backend/src/bin/pulsar-mlx.rs`
- [X] T047 [P] [US3] Execute the portable source suite and commit exact byte/range/error/ownership results in `docs/validation/portable-expert-source.json`
- [X] T048 [P] [US3] Execute the synthetic routed-MoE command and commit expert IDs, weights, output parity, memory gauges, actual result, warnings, and synthetic-only exclusions in `docs/validation/synthetic-moe-v1.json`
- [X] T049 [US3] Re-run the exact macOS workspace gates after shared storage/routing changes and append actual results to `docs/validation/portable-expert-source.json`
- [X] T050 [US3] Run the named Linux-only tests and applicable inherited CUDA checks on supported hardware/CI, or record the exact unavailable/not-run boundary; preserve selection/default behavior and prohibit a cross-platform-safe claim unless executed evidence passes in `docs/validation/linux-cuda-shared-boundary.json`

**Checkpoint**: US3 is independently complete on Apple when exact source and
synthetic oracle cases pass. Shared changes are described as Linux/CUDA-safe
only if `docs/validation/linux-cuda-shared-boundary.json` contains an actual
pass; unavailable hardware remains explicit unverified evidence, while any
observed inherited-path regression stops the feature.

---

## Phase 6: User Story 4 - Execute the First Compatible Real-Model Slice (Priority: P4)

**Goal**: Admit one immutable, legally accessible Qwen3-30B-A3B Q8_0 artifact
through explicit oracle, provenance, compatibility, disk, memory, and shared
regression gates, then execute only the bounded named graph depth that can be
compared correctly.

**Independent Test**: Before any model execution, inspect the four admission
records below. After an explicitly authorized external download, run the
trusted reference and Apple slice commands against the same immutable artifact
and deterministic prompt; the named output must satisfy its predeclared rule.

### Mandatory pre-execution admission gates

- [X] T051 [P] [US4] Select and freeze the trusted reference runtime, immutable version/revision, exact reproducible command, deterministic prompt, named comparison tensor/output, dtype, shape, tolerance, and mismatch policy in `docs/validation/models/qwen3-30b-a3b-q8_0-oracle.json`; stop US4 if no independent oracle can be fixed before viewing Apple output
- [X] T052 [P] [US4] Record the official source, immutable repository revision, exact filename, license source, published size, `qwen3moe` architecture, planned tensor/quantization roles, and bounded execution depth in `docs/validation/models/qwen3-30b-a3b-q8_0-compatibility.json`; stop before download on unresolved provenance or unsupported metadata
- [X] T053 [P] [US4] Create a conservative non-overlapping disk/unified-memory admission budget covering file bytes, owned compressed bytes, decoded arrays, temporaries, MLX active/cache/peak gauges, process footprint, cache budgets, and mandatory system headroom in `docs/validation/models/qwen3-30b-a3b-q8_0-memory-budget.json`; stop before download if the bounded slice does not fit
- [X] T054 [US4] Review all shared parsing/tokenization/storage/quantization/model-semantics changes against `docs/validation/linux-cuda-shared-boundary.json`, record unchanged inherited selection/defaults and any actual Linux/CUDA result, stop on an observed regression, and keep cross-platform safety explicitly unverified when suitable execution evidence is unavailable
- [X] T055 [US4] After explicit operator authorization, acquire the artifact outside the repository, verify actual byte size and SHA-256, inventory every tensor role/type needed by the slice, and update `docs/validation/models/qwen3-30b-a3b-q8_0-compatibility.json`; stop without executing if identity, license, inventory, or checksum is incomplete

### Tests for User Story 4 (write and observe failure before implementation)

- [X] T056 [P] [US4] Write failing Rust contract tests for immutable identity, metadata/quantization admission, missing-role rejection, budget rejection, unsupported execution depth, and absence of automatic downloads in `crates/mlx-backend/tests/real_model_contract.rs`
- [X] T057 [P] [US4] Write failing worker tests using bounded stand-ins for tensor-name/orientation checks, deterministic slice construction, unsupported-operation rejection, and oracle-shaped output in `python/pulsar_mlx_worker/tests/test_model_slice.py`

### Implementation for User Story 4

- [X] T058 [P] [US4] Implement checked external model identity, GGUF metadata/tensor inventory admission, exact supported-role matching, and memory-budget enforcement in `crates/mlx-backend/src/model.rs`
- [X] T059 [P] [US4] Implement only the admitted named Qwen3MoE worker slice with explicit tensor orientation, Q8_0 parity prerequisites, evaluated synchronization, bounded output, and memory gauges in `python/pulsar_mlx_worker/model_slice.py`
- [X] T060 [US4] Implement explicit external-path `inspect-model` and `validate-model-slice` commands with no downloader, token handling, full-output dump, or depth promotion in `crates/mlx-backend/src/bin/pulsar-mlx.rs` and `crates/mlx-backend/src/client.rs`
- [X] T061 [US4] Execute the preselected trusted-reference command and commit its sanitized immutable identity and bounded actual comparison output in `docs/validation/models/qwen3-30b-a3b-q8_0-reference-result.json`; stop if the oracle is not reproducible
- [X] T062 [US4] Execute the Apple slice against the same external artifact and prompt, compare only the preselected named output, and commit exact commands, actual errors/result, memory gauges, warnings, and execution-depth exclusions in `docs/validation/qwen3-30b-a3b-q8_0-slice.json`
- [X] T063 [US4] Update real-model versus giant-model support boundaries and exact post-slice workspace results in `docs/apple-silicon/COMPATIBILITY.md`, `docs/apple-silicon/SESSION_LOG.md`, `docs/apple-silicon/KNOWN_LIMITATIONS.md`, and `docs/validation/qwen3-30b-a3b-q8_0-slice.json`

**Checkpoint**: US4 passes only when every admission record is complete, the
artifact remains outside Git, the trusted oracle was chosen first, and the
bounded Apple output passes. A blocked gate remains a valid documented result
but is not real-model verification; an intermediate does not imply logits,
tokens, generation, giant-model inference, or serving.

---

## Phase 7: User Story 5 - Publish Reproducible Evidence and Boundaries (Priority: P5)

**Goal**: Make all verified, planned, unsupported, blocked, synthetic,
real-model, and giant-model states traceable and reject incomplete correctness
or benchmark claims.

**Independent Test**: Validate every committed evidence record, then reproduce
one selected case from its exact command. A reviewer can map each public claim
to immutable inputs, actual results, comparison rules, warnings, and
exclusions.

### Tests for User Story 5 (write and observe failure first)

- [X] T064 [P] [US5] Write failing schema/state tests that reject missing actual results, dirty/unknown commits, absent oracle fields, overlapping summed memory gauges, premature verified states, and benchmarks without passed correctness prerequisites in `crates/backend/tests/validation_records.rs`
- [X] T065 [P] [US5] Write failing claim-matrix tests that prevent synthetic, bounded real-model, giant-model, and production-serving evidence from implying one another in `crates/backend/tests/compatibility_matrix.rs`

### Implementation for User Story 5

- [X] T066 [US5] Implement reusable validation-record, compatibility-matrix, and benchmark-record validation with bounded diagnostics in `crates/backend/src/evidence.rs`
- [X] T067 [P] [US5] Populate the architecture/quantization/evidence-level matrix using only linked actual records in `docs/apple-silicon/COMPATIBILITY.md`
- [X] T068 [P] [US5] Create a reviewer index mapping case IDs to exact commands, immutable inputs, oracles, results, warnings, exclusions, and artifacts in `docs/validation/README.md`
- [X] T069 [US5] Record one post-correctness bounded benchmark with every constitution field, or an explicit `not_run` record with no performance claim, in `docs/validation/benchmark-initial.json`
- [X] T070 [US5] Independently replay one committed validation command and record the reproducer environment, actual result, differences, and exclusions in `docs/validation/reproduction-check.json`
- [X] T071 [US5] Reconcile verified/planned/unsupported language and executable commands across `README.md`, `specs/001-apple-silicon-mlx/quickstart.md`, `docs/apple-silicon/SESSION_LOG.md`, and `docs/apple-silicon/KNOWN_LIMITATIONS.md`
- [X] T072 [US5] Re-run the exact workspace gates and evidence validators, then record actual final story results without converting unavailable Linux/CUDA, model, or benchmark evidence into success in `docs/validation/reproduction-check.json`

**Checkpoint**: US5 is complete when every public claim resolves to a valid
record, a reviewer can replay one case, and incomplete or not-run benchmarks
cannot be presented as performance evidence.

---

## Phase 8: Polish and Cross-Cutting Validation

**Purpose**: Exercise supported automation, reconcile all documents, and leave
a scoped implementation handoff. This phase does not authorize custom Metal,
repository-wide debt cleanup, or broader model support.

- [X] T073 [P] Add a lockfile-backed, small-fixture-only Apple MLX job after local US1-US3 evidence exists, keep the exact Cargo baseline job intact, assert `arm64`, and exclude external models in `.github/workflows/macos.yml`
- [X] T074 Run the pushed macOS workflow, record the exact run identity, runner architecture, commands, actual results, and resource/model exclusions in `docs/validation/ci-mlx-smoke.json`
- [X] T075 [P] Run `cargo fmt --all -- --check` and `cargo clippy --workspace --all-targets -- -D warnings` as diagnostics, separate new failures from recorded upstream debt, and append actual results without broad cleanup in `docs/apple-silicon/SESSION_LOG.md`
- [X] T076 Run all focused tests plus exact workspace gates and `git diff --check`, inspect the staged diff for secrets, weights, private IDs, caches, generated binaries, and unintended Linux/CUDA selection changes, and record the sanitized review in `docs/apple-silicon/SESSION_LOG.md`
- [ ] T077 Execute every currently supported command in `specs/001-apple-silicon-mlx/quickstart.md`, replace planned wording only where actual committed evidence exists, and retain explicit stop instructions for unexecuted stages
- [ ] T078 Reconcile completed task status, requirement traceability, constitutional gates, evidence links, capability boundaries, and next bounded milestone in `specs/001-apple-silicon-mlx/tasks.md`, `specs/001-apple-silicon-mlx/spec.md`, `specs/001-apple-silicon-mlx/plan.md`, and `docs/apple-silicon/SESSION_LOG.md`

**Checkpoint**: The branch is buildable, evidence and docs agree, CI outcomes
are actual, the Linux/CUDA boundary is explicit, no forbidden files are staged,
and the next session cannot mistake planned work for implemented capability.

---

## Dependencies and Execution Order

### Phase dependencies

```text
Phase 1 Setup
    -> Phase 2 Foundational Contracts
        -> US1 Apple Baseline (MVP)
            -> US2 Tensor + Q8_0
                -> US3 Storage + Synthetic MoE
                    -> US4 admission gates -> US4 Real-Model Slice
                        -> US5 Evidence + Boundaries
                            -> Phase 8 Polish
```

- **Setup** has no feature dependency; T004 depends on T002-T003, and T006
  depends on T005.
- **Foundational** depends on Setup and blocks all stories. T010-T013 follow
  their failing tests; T014 follows T010-T013.
- **US1** depends on Foundational and is the MVP. T020 depends on T018-T019;
  T022 depends on T021; T023 depends on T020-T022; evidence follows execution.
- **US2** depends on the evaluated US1 worker contract. T028-T030 depend on the
  frozen T027 fixture contract; T033-T034 follow the reference implementations.
- **US3** depends on US2 tensor/Q8_0 parity. T043-T046 follow their respective
  failing tests; evidence T047-T050 follows implementation.
- **US4** depends on US3. T051-T054 are admission decisions, T055 requires
  their pass plus explicit download authorization, and no execution may begin
  before T051-T055. T061 precedes T062 so Apple output cannot influence the
  trusted oracle. T054/T050 bound Linux/CUDA claims even when hardware is
  unavailable.
- **US5** consumes actual evidence from the completed or blocked earlier
  stories; it never upgrades a blocked/not-run record to verified.
- **Polish** follows the highest desired completed story and keeps any skipped
  later story visibly incomplete.

### User-story dependency graph

| Story | Direct dependency | Independently testable result |
| --- | --- | --- |
| US1 | Foundational contracts | Explicit evaluated MLX device proof or bounded unsupported result |
| US2 | US1 worker/device contract | Deterministic tensor and Q8_0 fixture parity |
| US3 | US2 admitted operations | Exact portable expert reads and synthetic routed-MoE parity |
| US4 | US3 plus admission gates | One provenance-recorded bounded real-model output comparison |
| US5 | Actual records from desired stories | Validated claims, compatibility matrix, and reproducible evidence |

US1 is useful without later stories. US2 and US3 are separate validated
increments. US4 must not be parallelized ahead of its gates. US5 can begin its
schema/test work after Foundational, but final records depend on the actual
story outcomes.

## Parallel Execution Examples

### Setup and Foundational

```text
After T001: run T002, T003, and T005 in parallel.
After Phase 1: run T007, T008, and T009 in parallel.
After those tests fail as intended: implement T011, T012, and T013 in parallel,
then integrate with T014.
```

### User Story 1

```text
Run T015, T016, and T017 in parallel.
Then implement Python protocol/runtime (T018-T019) alongside Rust protocol
(T021); converge at worker/client integration T020-T023.
```

### User Story 2

```text
After T027, run T028, T029, and T030 in parallel.
Then implement the scalar Q8_0 reference (T031) alongside MLX tensor operations
(T032); integrate both through T033-T034.
```

### User Story 3

```text
After T038, run T039, T040, T041, and T042 in parallel.
Implement positional storage (T043), scalar routing (T044), and MLX routing
(T045) in parallel; converge at T046, then collect T047-T050 evidence.
```

### User Story 4

```text
Run the oracle, provenance, and memory admission work T051-T053 in parallel;
then complete T054-T055 before writing or running the model slice.
After the gates pass, T056 and T057 can run in parallel, followed by T058 and
T059 in parallel; converge at T060-T063. Never run T061 and T062 in parallel.
```

### User Story 5

```text
Run T064 and T065 in parallel.
After T066 passes, populate the compatibility matrix (T067) and validation
index (T068) in parallel, then complete benchmark/reproduction/docs work.
```

## Implementation Strategy

### MVP first: User Story 1 only

1. Complete Setup and Foundational contracts.
2. Complete T015-T026 in test-first order.
3. Stop and review `docs/validation/mlx-device-smoke.json`.
4. Proceed only if the result truthfully proves an evaluated MLX GPU operation;
   otherwise retain the bounded blocker and do not start tensor work.

### Incremental delivery

1. **MVP**: US1 proves environment, process contract, device, and no fallback.
2. **Reference primitives**: US2 proves tensor semantics and strict Q8_0.
3. **Core MoE proof**: US3 proves exact storage and synthetic routing.
4. **Reality bridge**: US4 passes all gates and proves one bounded external
   real-model slice without expanding the claim.
5. **Evidence release**: US5 makes claims and benchmark boundaries reviewable.
6. At every checkpoint, land a focused test-backed commit with its Spec Kit,
   session log, compatibility, validation, and limitation updates.

### Stop discipline

- Stop at any mandatory device, correctness, layout, provenance, compatibility,
  memory, regression, secret, or weight condition from `spec.md`.
- Do not silently fall back, loosen a tolerance after results, auto-download a
  checkpoint, sum overlapping memory gauges, or promote evidence depth.
- Do not start custom Metal, broad engine refactoring, full giant-model
  inference, production serving, or upstream formatting/Clippy cleanup under
  this task list.

## Notes

- `[P]` is deliberately conservative; tasks touching shared files or dependent
  evidence are serialized.
- Tests precede implementation in every behavior phase and remain as durable
  oracles after the story passes.
- Model paths, access credentials, and raw weights never appear in committed
  commands or evidence.
- Unavailable Linux/CUDA hardware permits only an explicit unverified boundary,
  never a cross-platform-safe claim; an observed regression is a stop.
- Complete one user-story checkpoint before expanding the capability claim.
