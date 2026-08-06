# Tasks: Qwen3MoE Layer-0 Router Parity

**Input**: Design documents from `specs/002-qwen-router-parity/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`quickstart.md`, and `contracts/`

**Tests**: This feature explicitly requires test-first implementation,
mutation tests, fixture-only CI, real-checkpoint parity, and publication
validation.

**Organization**: Tasks are grouped by user story. The gated real-checkpoint
phase integrates the independently prepared stories under one notified
hardware window.

## Pre-Implementation Review Gate

The live `$speckit-analyze` gate ran after task generation, mapped all 44
requirements, and identified no orphaned task. Its blocking findings must be
remediated and the read-only analysis rerun before T001 begins. T093 is the
required final repeat analysis, not the first analysis.

## Hard Safety Boundary

Tasks T001 through T072 MUST NOT resolve, stat, hash, open, or execute the
external checkpoint. T073 sends and confirms the required NTFY notification.
T074 is the first task permitted to access external model data.

After T073 succeeds, any stop condition before Feature 002 completion MUST
preserve safe raw attempts outside Git, sanitize and commit only bounded legal
evidence, send a blocker notification to NTFY topic `Mahdi-Dev` stating that
local inference may resume, update the session/results/limitations documents,
and stop without weakening tolerances, changing the oracle, relabeling a
synthetic input, or continuing into a deeper graph.

T097 is a terminal exception to ordinary numeric ordering: it becomes eligible
immediately after any documented Feature 002 stop condition in any phase, or
after T096 passes for normal completion. If no pre-access notification was sent,
the blocker message says model access never began and local inference was never
paused.

Every task that creates a commit or pushes MUST run the standardized staged
secret/private-path/model-byte/binary/cache/large-file and Linux/CUDA-selection
scan immediately before the commit. CI outcomes learned after a push are
appended immediately to `docs/apple-silicon/SESSION_LOG.md` and included in the
next focused documentation/task-state commit; a milestone is not described as
clean while such a log update is pending. Before a later gate that requires a
clean/equal branch, the pending log update is committed and pushed as a scanned
documentation-only CI attestation, and that attestation's own CI result is
reported out of tree rather than recursively logged. The same non-recursive
exception applies to T096: T097 reports its CI result in the terminal message
and final report without changing the clean branch.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it changes independent files.
- **[Story]**: Maps the task to a specification user story.
- Every implementation phase is test-first.
- Every coherent milestone ends with validation, task/log updates, a focused
  commit, push, and CI confirmation.

## Phase 1: Setup and Safe Baseline

**Purpose**: Re-establish the completed Feature 001 baseline and create the
Feature 002 research structure without model access.

- [X] T001 Run Spec Kit health, Git status, Cargo workspace, and Python worker baseline commands and append exact actual results to `docs/apple-silicon/SESSION_LOG.md`
- [X] T002 Create the no-network research tooling skeleton and idempotent entrypoint in `scripts/research/setup.sh`
- [X] T003 [P] Add explicit local research-work, candidate-output, oracle-build, model, cache, log, and secret exclusions without ignoring publishable evidence in `.gitignore`
- [X] T004 [P] Create status-only skeletons in `docs/research/EXPERIMENT_PROTOCOL.md`, `docs/research/REPRODUCIBILITY.md`, `docs/research/RESULTS.md`, `docs/research/LIMITATIONS.md`, `docs/research/CLAIMS_LEDGER.md`, and `docs/research/REVIEWER_INDEX.md`

**Checkpoint**: Baseline results are recorded and every new document says that
implementation and real-router results do not yet exist.

---

## Phase 2: Foundational Research Methodology

**Purpose**: Freeze and push the schema, statistics, privacy, generation, and
publication method before any model access.

**Critical**: T022 and its CI run must pass before any external-checkpoint
task.

### Tests First

- [X] T005 [P] Write and run failing known-vector tests for Type-7 percentiles, mean, sample standard deviation, coefficient of variation, null reasons, and raw-observation grouping in `scripts/research/tests/test_statistics.py`
- [X] T006 [P] Write and run failing structural, semantic, privacy, non-finite, repetition, append-only, and incompatible-condition mutation tests in `scripts/research/tests/test_validate_evidence.py`
- [X] T007 [P] Write and run failing deterministic Markdown, CSV, SVG, and provenance-sidecar regeneration tests in `scripts/research/tests/test_generators.py`
- [X] T008 [P] Write and run failing package-verification, overwrite-refusal, candidate-sanitization, and atomic-publication tests in `scripts/research/tests/test_verify_package.py`

### Implementation

- [X] T009 Create closed version-1 schemas and small positive/mutated fixtures in `schemas/research/v1/experiment.schema.json`, `schemas/research/v1/router-parity.schema.json`, and `fixtures/research/router-v1/evidence/`
- [X] T010 Implement the frozen statistics rules using raw integer nanoseconds and no plotting dependency in `scripts/research/statistics.py`
- [X] T011 Implement fail-closed schema, semantic, privacy, capability-boundary, repetition, correctness, and statistics validation in `scripts/research/validate_evidence.py`
- [X] T012 Run the T005 statistics and T006 validator contracts to red-then-green completion, confirm the intentionally later T007–T008 generator/publication contracts remain at their recorded red boundary until T014–T015, and record exact counts and exclusions in `docs/apple-silicon/SESSION_LOG.md`
- [X] T013 Stage only the schema/statistics/validator slice, scan for secrets, private paths, model bytes, binaries, and large files, then commit, push, and record actual CI in `docs/apple-silicon/SESSION_LOG.md`
- [X] T014 [P] Implement deterministic table and SVG generation with source hashes and no embedded measurements in `scripts/research/generate_tables.py` and `scripts/research/generate_figures.py`
- [X] T015 Implement candidate validation, byte-for-byte regeneration, ledger/index checking, atomic append-only installation, and overwrite refusal in `scripts/research/verify_package.py` and `scripts/research/publish_evidence.py`
- [X] T016 Complete idempotent no-model safe setup, explicit-path preparation, standardized staged scanning, and shell tests in `scripts/research/setup.sh`, `scripts/research/prepare_model.sh`, and `scripts/research/check_staged.sh`
- [X] T017 Freeze tolerances, exact direct token IDs `[0,1]`, positions `[0,1]`, context/batch/ubatch/thread parameters, case IDs, row selection, two-row/16,384-byte maximum fixture, major benchmark matrix, timing boundaries, sample counts, ordering, interference, exclusion, amendment, retention, and stop rules in `docs/research/EXPERIMENT_PROTOCOL.md`
- [X] T018 [P] Complete the clean-checkout guide, empty result/limitation structures, claims table, reviewer index, and manifest placeholders in `docs/research/REPRODUCIBILITY.md`, `docs/research/RESULTS.md`, `docs/research/LIMITATIONS.md`, `docs/research/CLAIMS_LEDGER.md`, `docs/research/REVIEWER_INDEX.md`, `docs/research/MODEL_MANIFEST.json`, and `docs/research/ARTIFACT_MANIFEST.json`
- [X] T019 Run safe setup, all research unit tests, positive evidence-fixture validation, and fixture-only package verification exactly as documented in `specs/002-qwen-router-parity/quickstart.md`
- [X] T020 Add fixture-only schema, mutation, statistics, generation, privacy, and package checks with an explicitly empty model variable to `.github/workflows/macos.yml`
- [X] T021 Run the CI-equivalent fixture suite, exact Cargo workspace gates, Python worker suite, `git diff --check`, and staged safety scans, then update `docs/apple-silicon/SESSION_LOG.md` and `specs/002-qwen-router-parity/tasks.md`
- [X] T022 Commit the complete frozen methodology, push `main` without force, wait for every `.github/workflows/macos.yml` job, and record the commit/run identity in `docs/apple-silicon/SESSION_LOG.md`

**Checkpoint**: Methodology, schemas, validators, generators, fixtures,
documentation, and fixture-only CI are committed and green. No external model
has been accessed.

---

## Phase 3: User Story 1 - Verify Router Decisions (Priority: P1) 🎯 MVP

**Goal**: Implement the bounded complete-router reference operation and
independent oracle workflow using redistributable fixtures first.

**Independent Test**: A generated `[N,2048] × [2048,128]` case produces all
128 logits and probabilities, exact ordered top-8 IDs, selected probabilities,
normalized weights, hashes, comparisons, explicit GPU identity,
synchronization, and no fallback. Real-checkpoint acceptance completes at
T084.

### Tests First

- [X] T023 [P] [US1] Write and run failing Rust tests for tensor admission, complete logits/probabilities, top-8 IDs/order, selected probabilities, normalized weights, canonical hashes, comparisons, and ten-repeat identity in `crates/mlx-backend/tests/router_contract.rs`
- [X] T024 [P] [US1] Write and run failing worker tests for single-row and bounded-batch evaluated MLX router execution, explicit GPU, synchronization, complete outputs, and no fallback in `python/pulsar_mlx_worker/tests/test_router.py`
- [X] T025 [P] [US1] Write and run failing stub tests for pinned-source verification, two identical captures, cancellation proof, scalar F32 accumulation, NumPy cross-checking, oracle independence, and no model auto-download in `scripts/research/tests/test_router_oracle.py`

### Implementation

- [X] T026 [US1] Create the generated 128-expert/top-8 fixture README, manifest, finite hidden rows, F32 weight fixture recipe, independent expected results, and canonical hashes in `fixtures/research/router-v1/README.md`, `fixtures/research/router-v1/manifest.json`, and `fixtures/research/router-v1/golden/`
- [X] T027 [US1] Implement immutable router identity, positional-read admission, canonical F32 hashing, full-output comparison metrics, and bounded evidence types in `crates/mlx-backend/src/router.rs`
- [X] T028 [US1] Add the control-only router request/result, strict frame bounds, complete response validation, and stable error parsing in `crates/mlx-backend/src/protocol.rs`
- [X] T029 [US1] Add the supervised router request method without changing Feature 001 methods or descriptor inheritance in `crates/mlx-backend/src/client.rs`
- [X] T030 [US1] Implement evaluated MLX F32 projection, full 128-way softmax, deterministic top-8, selected-probability renormalization, evaluation, synchronization, and memory gauges in `python/pulsar_mlx_worker/router.py`
- [X] T031 [US1] Register the additive router operation without changing existing operations or startup semantics in `python/pulsar_mlx_worker/protocol.py`, `python/pulsar_mlx_worker/runtime.py`, and `python/pulsar_mlx_worker/__main__.py`
- [X] T032 [US1] Add strict parsers and safe planned commands for `inspect-router`, `validate-router-fixtures`, and `validate-router` in `crates/mlx-backend/src/bin/pulsar-mlx.rs`
- [X] T033 [US1] Export only the additive Feature 002 router API and retain Feature 001 exports unchanged in `crates/mlx-backend/src/lib.rs`
- [X] T034 [US1] Implement the pinned llama.cpp capture source, shell orchestration, standalone scalar oracle, and no-MLX import guard in `scripts/research/llama_capture/router_capture.cpp`, `scripts/research/capture_router_oracle.sh`, and `scripts/research/router_oracle.py`
- [X] T035 [US1] Run focused Rust, worker, generated-fixture MLX, oracle-stub, schema, and package tests and confirm all T023 through T025 failures now pass without checkpoint access using `specs/002-qwen-router-parity/quickstart.md`
- [X] T036 [US1] Document the offline router seam, explicit compatibility level, oracle boundary, unverified real-checkpoint status, exact commands, and unsupported depths in `docs/apple-silicon/COMPATIBILITY.md`, `docs/apple-silicon/BACKEND_DESIGN.md`, `docs/apple-silicon/KNOWN_LIMITATIONS.md`, `docs/apple-silicon/SESSION_LOG.md`, and `specs/002-qwen-router-parity/tasks.md`
- [X] T037 [US1] Run exact workspace gates, Python discovery, research validation, `git diff --check`, Feature 001 preservation review, and staged safety scans over `crates/mlx-backend/`, `python/pulsar_mlx_worker/`, `scripts/research/`, and `fixtures/research/router-v1/`
- [X] T038 [US1] Create focused router-core and oracle-tooling commits, push `main`, wait for every fixture-only/workspace CI job, and record actual results in `docs/apple-silicon/SESSION_LOG.md`

**Checkpoint**: Offline router and oracle contracts pass. No real-router
capability is claimed and no external model has been accessed.

---

## Phase 4: User Story 2 - Reject Unsafe Router Inputs (Priority: P2)

**Goal**: Prove malformed or ambiguous inputs fail before accepted MLX
execution.

**Independent Test**: Every malformed, non-finite, identity, shape, range,
orientation, top-k, tie, fallback, and mutation case produces its stable error,
and pre-execution failures never call the router runner or construct/schedule
router MLX arrays. Existing startup runtime discovery remains unchanged.

### Tests First

- [X] T039 [P] [US2] Write and run failing Rust tests for truncated/overlong ranges, duplicate/missing tensors, changed identity, wrong F32 type/dimensions/orientation, invalid top-k, non-finite data, aliases, and runner-not-called behavior in `crates/mlx-backend/tests/router_contract.rs`
- [X] T040 [P] [US2] Write and run failing Python tests proving malformed fields, invalid shapes/dtypes, non-finite values, fallback requests, invalid case IDs, and byte-count failures occur before router MLX array construction, scheduling, or runner access in `python/pulsar_mlx_worker/tests/test_router.py`
- [X] T041 [US2] Add bounded malformed, truncated, overlong, orientation, invalid-top-k, non-finite, exact-tie, and near-tie fixtures in `fixtures/research/router-v1/malformed/` and `fixtures/research/router-v1/synthetic-tie.json`

### Implementation

- [X] T042 [US2] Implement exact host-side identity, range, shape, F32 type, count, finite-value, alias, mutation, and resource failure codes in `crates/mlx-backend/src/router.rs`
- [X] T043 [US2] Implement pre-router-array worker validation, bounded failures, and router-runner-not-called enforcement while preserving startup discovery in `python/pulsar_mlx_worker/router.py` and `python/pulsar_mlx_worker/protocol.py`
- [X] T044 [US2] Implement probability-descending/expert-ID-ascending synthetic tie behavior while preserving any real rank-8/rank-9 tie as a stop condition in `python/pulsar_mlx_worker/router.py` and `crates/mlx-backend/src/router.rs`
- [X] T045 [US2] Complete `validate-router-fixtures` failure retention and synthetic-versus-real evidence labeling in `crates/mlx-backend/src/bin/pulsar-mlx.rs`
- [X] T046 [US2] Run all focused negative tests, backend-neutral routing regression tests, worker tests, and generated MLX fixture validation from `fixtures/research/router-v1/manifest.json`
- [X] T047 [US2] Run schema/package validation, exact Cargo workspace gates, Python discovery, and Feature 001 regression tests, then record actual results in `docs/apple-silicon/SESSION_LOG.md`
- [X] T048 [US2] Update failure coverage and exclusions, mark task state, and perform staged safety/Linux-CUDA selection review in `docs/apple-silicon/KNOWN_LIMITATIONS.md`, `docs/apple-silicon/SESSION_LOG.md`, and `specs/002-qwen-router-parity/tasks.md`
- [X] T049 [US2] Commit the fail-closed safety slice, push `main`, and wait for every `.github/workflows/macos.yml` job before allowing external-model access

**Checkpoint**: Unsafe cases fail before accepted execution. Synthetic tie
behavior is verified but is not checkpoint evidence.

---

## Phase 5: User Story 3 - Publish Reproducible Evidence (Priority: P3)

**Goal**: Make every router claim traceable and regenerable from committed
machine-readable fixture evidence.

**Independent Test**: A clean fixture-only checkout validates positive, failed,
and aborted records; regenerates every artifact byte-for-byte; and rejects
privacy or scope violations.

### Tests First

- [X] T050 [P] [US3] Write and run failing Feature 002 tests for immutable identities, raw attempts, failed/aborted retention, correctness metrics, unsupported interpretations, and clean-commit promotion in `scripts/research/tests/test_feature002_records.py`
- [X] T051 [P] [US3] Write and run failing tests for claim links, reviewer-index completeness, sidecars, append-only install, duplicate IDs, overclaims, and private-value rejection in `scripts/research/tests/test_generators.py` and `scripts/research/tests/test_verify_package.py`

### Implementation

- [X] T052 [US3] Add small schema-valid passing, failed, aborted, excluded, and mutation evidence fixtures with no real measurements in `fixtures/research/router-v1/evidence/`
- [X] T053 [US3] Implement Feature 002 identity, correctness, repetition, artifact-link, unsupported-depth, and claim-promotion checks in `scripts/research/validate_evidence.py`
- [X] T054 [US3] Implement exclusive append-only publication, stable experiment IDs, path sanitization, legal bounded-copy rules, and atomic failure in `scripts/research/publish_evidence.py`
- [X] T055 [US3] Implement deterministic correctness/timing tables, bounded SVGs, source sidecars, ledger verification, and reviewer-index verification in `scripts/research/generate_tables.py`, `scripts/research/generate_figures.py`, and `scripts/research/verify_package.py`
- [X] T056 [US3] Generate and commit only fixture-derived expected publication outputs under `fixtures/research/router-v1/expected/`
- [X] T057 [US3] Reproduce the fixture package from a temporary clean checkout and compare every generated byte and hash using `specs/002-qwen-router-parity/quickstart.md`
- [X] T058 [US3] Document fixture-only publication, append-only rules, claim states, clean-checkout reproduction, and non-model scope in `docs/research/REPRODUCIBILITY.md`, `docs/research/RESULTS.md`, `docs/research/LIMITATIONS.md`, `docs/research/CLAIMS_LEDGER.md`, and `docs/research/REVIEWER_INDEX.md`
- [X] T059 [US3] Run every safe research command, package verification, Cargo workspace gate, Python discovery, `git diff --check`, and deterministic regeneration comparison using `specs/002-qwen-router-parity/quickstart.md`
- [X] T060 [US3] Update task/session state, scan the staged package, commit evidence tooling, push `main`, and wait for every `.github/workflows/macos.yml` job using `docs/apple-silicon/SESSION_LOG.md` and `specs/002-qwen-router-parity/tasks.md`

**Checkpoint**: Publication tooling is reproducible for fixtures. No
real-checkpoint claim exists.

---

## Phase 6: User Story 4 - Measure the Bounded Router Honestly (Priority: P4)

**Goal**: Instrument the bounded router without confusing lazy scheduling,
stage instrumentation, process state, or cache state.

**Independent Test**: A generated fixture retains all attempts, separates
minimal and stage-instrumented modes, synchronizes each evaluated interval,
enforces 5/10 and 5/30 policies, and reproduces every statistic.

### Tests First

- [X] T061 [P] [US4] Write and run failing worker tests for monotonic nanosecond timing, evaluated barriers, minimally instrumented totals, synchronization, F32 dequantization `not_applicable`, warmup retention, and all-attempt retention in `python/pulsar_mlx_worker/tests/test_router.py`
- [X] T062 [P] [US4] Write and run failing Rust tests for timing payloads, fixed sample policies, exact single-row and two-row minimally instrumented major benchmarks, per-major-benchmark clean-process replication, process/condition labels, output hashes, and response bounds in `crates/mlx-backend/tests/research_evidence.rs`
- [X] T063 [P] [US4] Write and run failing tests for incompatible grouping, interference labels, unfiltered/filtered summaries, sample counts, unavailable phases, and second-batch reasons in `scripts/research/tests/test_timing_policy.py`

### Implementation

- [ ] T064 [US4] Implement monotonic raw timing, explicit synchronization, minimally instrumented totals, stage diagnostics, and all-attempt retention in `python/pulsar_mlx_worker/router.py`
- [ ] T065 [US4] Implement timing observation/result types, sample validation, process/condition/instrumentation separation, and response bounds in `crates/mlx-backend/src/router.rs` and `crates/mlx-backend/src/protocol.rs`
- [ ] T066 [US4] Implement correctness-gated orchestration for the single-row and two-row minimally instrumented major benchmarks, one clean-process replication per major benchmark, and later-batch/unavailable recording in `crates/mlx-backend/src/bin/pulsar-mlx.rs`
- [ ] T067 [US4] Implement public-safe environment, load, storage, pressure, power, thermal, and resource observations with unavailable reasons in `scripts/research/environment.py`
- [ ] T068 [US4] Run the inexpensive generated router microbenchmark with five retained warmups and thirty measurements and keep its candidate outside Git until validated through `fixtures/research/router-v1/manifest.json`
- [ ] T069 [US4] Validate the generated timing candidate, reproduce statistics/grouping, verify no stage-sum claim, and run focused Rust/Python/research tests using `specs/002-qwen-router-parity/quickstart.md`
- [ ] T070 [US4] Update timing methods, fixture behavior, unavailable observations, task state, and staged review in `docs/research/EXPERIMENT_PROTOCOL.md`, `docs/research/RESULTS.md`, `docs/research/LIMITATIONS.md`, `docs/apple-silicon/SESSION_LOG.md`, and `specs/002-qwen-router-parity/tasks.md`
- [ ] T071 [US4] Run exact workspace/package gates and the standardized staged safety scan, commit timing instrumentation, push `main`, and wait for every `.github/workflows/macos.yml` job

**Checkpoint**: Timing mechanics are fixture-verified. No real router latency
has been measured or claimed.

---

## Phase 7: Gated Real-Checkpoint Integration

**Purpose**: Notify the operator, admit the exact model, freeze a real CPU
oracle, run bounded Apple correctness, and only then retain timing evidence.

**Dependencies**: T022, T038, T049, T060, and T071 must be pushed with green
CI.

- [ ] T072 Append the actual T071 CI result, create and push a scanned non-recursive documentation-only CI attestation, wait for it, then verify clean `main`, `HEAD == origin/main`, green CI, methodology ancestry, exact workspace/Python/research gates, normal resource admission, and external candidate directories outside Git using `specs/002-qwen-router-parity/quickstart.md`
- [ ] T073 Send the pre-access NTFY to `https://ntfy.sh/Mahdi-Dev`, require an acknowledged success response, and stop before model access if it fails as specified in `specs/002-qwen-router-parity/contracts/commands-v1.md`
- [ ] T074 [US1] Only after T073, verify exact external filename, size, SHA-256, immutable identity, and run read-only `inspect-router` into an external candidate according to `specs/002-qwen-router-parity/quickstart.md`
- [ ] T075 [US1] Validate the inspection and stop on unresolved occurrence, F32 type, dimensions, offset, range, hash, orientation, top-k, scale, bias, license, memory, disk, pressure, thermal, or workload facts before updating `docs/research/MODEL_MANIFEST.json`
- [ ] T076 [US1] Record that inspection performed no MLX/router execution, update task/session state, scan the staged inventory, commit/push immutable admission, and wait for CI using `docs/apple-silicon/SESSION_LOG.md` and `specs/002-qwen-router-parity/tasks.md`
- [ ] T077 [US1] First append the actual T076 CI result and complete a scanned non-recursive documentation-only CI attestation so the source tree is clean/equal; then run two independently started CPU-only `ffn_norm-0` captures using only precommitted direct token IDs `[0,1]`, positions `[0,1]`, two-token context/batch/ubatch, one thread, no tokenizer selection, and the pinned source via `scripts/research/capture_router_oracle.sh`
- [ ] T078 [US1] Prove one CPU scheduler split, complete synchronized capture, CPU abort guard, identical hashes, and no router/expert callback node after `ffn_norm-0`, or retain a minimal reproduction and trigger the stop protocol in `docs/research/EXPERIMENT_PROTOCOL.md`
- [ ] T079 [US1] Run the standalone scalar F32 router oracle and NumPy cross-check without importing MLX or worker code using `scripts/research/router_oracle.py`
- [ ] T080 [US1] Validate the external oracle candidate's complete tensor/input/output hashes, all 128 logits/probabilities, exact top-8, frozen tolerances, distinct real rows, no rank-8/rank-9 tie, and redistribution scope without writing committed fixture/raw paths using `scripts/research/verify_package.py`
- [ ] T081 [US1] After all oracle/schema/privacy/model-byte/path/workspace/package checks pass, atomically publish bounded fixture/oracle values to `fixtures/research/router-v1/real/` and `docs/research/raw/002-router-parity/`, run the staged scan, update task/session state, commit/push before Apple output, and wait for CI using `docs/apple-silicon/SESSION_LOG.md` and `specs/002-qwen-router-parity/tasks.md`
- [ ] T082 [US1] Append the actual T081 CI result, complete a scanned non-recursive documentation-only CI attestation, then reconfirm clean/equal `main`, green CI, unchanged model/router, intended GPU, normal pressure/thermal/load, and continued operator pause using `specs/002-qwen-router-parity/quickstart.md`
- [ ] T083 [US1] Run the exact local `validate-router` command into an external candidate and require its internal correctness gate before timing as defined in `specs/002-qwen-router-parity/contracts/commands-v1.md`
- [ ] T084 [US1] Evaluate all real stop conditions: exact single-row/batch IDs and order, complete 128-output metrics, ranges `0..16` and `64..80`, frozen tolerances, finite values, ten identical hashes, GPU/sync/no-fallback, immutable identity, and no expert execution in the external candidate
- [ ] T085 [US4] After T084 passes, verify every warmup/measurement, first-process/warm condition, minimal/stage mode, F32 `not_applicable` dequantization, one clean-process replication for each single-row and two-row minimally instrumented major benchmark, later-batch reason, interference policy, and statistic in the external candidate
- [ ] T086 [US3] Validate and sanitize the real candidate, preserve failed/aborted attempts, assign append-only IDs, and stage only bounded legal raw records under `docs/research/raw/002-router-parity/`
- [ ] T087 [US3] Run raw-package/privacy/model-byte checks, commit and push the append-only raw evidence before generation, wait for CI, and record the committed raw SHA in `docs/apple-silicon/SESSION_LOG.md`
- [ ] T088 [US3] Generate tables, figures, sidecars, results, limitations, ledger, and reviewer index only from the committed raw SHA, verify deterministic output, scan staged content for secrets/private paths/model bytes/binaries/large files, commit/push, and wait for CI under `docs/research/`
- [ ] T089 [US3] From a temporary clean checkout at the recorded source commit, rerun the exact authorized model reproduction command, compare identities/outputs, and retain a new external candidate instead of overwriting evidence according to `docs/research/REPRODUCIBILITY.md`

**Checkpoint**: The deepest valid real boundary is frozen. A failure after T073
is a documented stop condition, not permission to continue.

---

## Phase 8: Final Reconciliation and Closeout

**Purpose**: Promote only cleanly reproduced claims, complete final audits,
push a clean branch, and release the operator's hardware.

- [ ] T090 Validate and sanitize the clean-checkout reproduction candidate without altering committed raw evidence using `scripts/research/validate_evidence.py` and `scripts/research/verify_package.py`
- [ ] T091 Append-only publish the reproduction record, scan it, commit/push the raw-only change, wait for CI, and record its raw SHA in `docs/apple-silicon/SESSION_LOG.md`
- [ ] T092 Regenerate publication artifacts from the committed reproduction SHA and update only observed capability/claim status in `README.md`, `docs/apple-silicon/COMPATIBILITY.md`, `docs/apple-silicon/BACKEND_DESIGN.md`, `docs/apple-silicon/KNOWN_LIMITATIONS.md`, `docs/research/RESULTS.md`, `docs/research/LIMITATIONS.md`, `docs/research/CLAIMS_LEDGER.md`, and `docs/research/REVIEWER_INDEX.md`
- [ ] T093 Repeat Spec Kit consistency analysis, requirements/constitution traceability, capability-claim audit, local-link validation, shell-block syntax checks, and schema/manifest inventory checks over `specs/002-qwen-router-parity/` and `.specify/memory/constitution.md`
- [ ] T094 Run research tests, package verification, Python discovery, focused router tests, `cargo check --workspace --all-targets`, `cargo test --workspace --no-fail-fast`, and `git diff --check`, then record actual counts in `docs/apple-silicon/SESSION_LOG.md`
- [ ] T095 Mark final Spec Kit task state, record commits/CI/commands/limitations, and perform staged scans for secrets, private paths, identifiers, model/tensor bytes, caches, binaries, large files, and Linux/CUDA changes in `specs/002-qwen-router-parity/tasks.md` and `docs/apple-silicon/SESSION_LOG.md`
- [ ] T096 Commit final reconciliation, push `main` without force, wait for every `.github/workflows/macos.yml` job, and verify a clean worktree with `HEAD == origin/main` using `docs/apple-silicon/SESSION_LOG.md`
- [ ] T097 After T096 is green OR immediately after any documented Feature 002 stop condition in any phase, send the completion or exact-blocker NTFY to `https://ntfy.sh/Mahdi-Dev`, state whether model access began and that local inference may continue/resume, require an acknowledged response, and leave the clean branch unchanged as specified in `specs/002-qwen-router-parity/contracts/commands-v1.md`

---

## Dependencies and Execution Order

### Phase Dependencies

- **Setup**: Starts from the completed Feature 001 baseline.
- **Foundational**: Depends on Setup and blocks every user story.
- **User Story 1**: Depends on Foundational.
- **User Story 2**: Depends on User Story 1 request/result and worker seams.
- **User Story 3**: Depends on Foundational; real promotion also depends on
  User Stories 1 and 2.
- **User Story 4**: Depends on User Story 1's evaluated operation; real timing
  also depends on passing real correctness.
- **Gated integration**: Depends on all four story phases, pushed commits, and
  green CI.
- **Closeout**: Depends on the deepest valid gated result.

### Model-Access Dependency

```text
T022 methodology green
  -> T038 router core green
  -> T049 safety green
  -> T060 publication green
  -> T071 timing green
  -> T072 clean pre-access gate
  -> T073 acknowledged NTFY
  -> T074 first permitted checkpoint access
```

### Real Execution Dependency

```text
T074 exact model/tensor admission
  -> T075/T076 validated admission commit and CI
  -> T077/T078 genuine capture and cancellation proof
  -> T079/T080 independent oracle freeze
  -> T081 oracle commit and CI
  -> T082 clean/equal Apple preflight
  -> T083 Apple command
  -> T084 correctness
  -> T085 timing
  -> T086/T087 raw publication commit
  -> T088 generated publication commit
  -> T089 clean-checkout reproduction
  -> T090/T091 reproduction raw commit
  -> T092 verified-claim promotion
```

## Parallel Opportunities

- T005 through T008 can run in parallel in separate research test files.
- T014 and T018 can run in parallel after schemas/statistics stabilize.
- T023 through T025 can run in parallel across Rust, Python, and oracle tests.
- T039 and T040 can run in parallel.
- T050 and T051 can run in parallel.
- T061 through T063 can run in parallel.
- T074 through T092 remain serialized under one notified hardware window.

## Parallel Example: User Story 1

```text
Task: T023 - Rust router contract tests
Task: T024 - Python evaluated-router tests
Task: T025 - Independent oracle workflow tests
```

After all three expected failures are recorded, proceed serially through shared
implementation files T027 through T034.

## Parallel Example: User Story 4

```text
Task: T061 - Worker timing tests
Task: T062 - Rust timing-payload tests
Task: T063 - Statistical grouping and interference tests
```

## Implementation Strategy

### Offline MVP

1. Complete Setup and Foundational.
2. Complete User Story 1 through T038.
3. Complete the User Story 2 safety gate through T049.
4. Validate the fixture-only router path independently.

This proves only the implementation contract and generated execution, not real
Qwen routing.

### Real Correctness MVP

The smallest real-checkpoint acceptance slice additionally requires T072
through T084. It ends at exact router correctness and implies neither timing,
expert execution, nor a complete layer.

### Full Feature 002

Complete T001 through T097. Timing and verified publication are required to
declare the current specification complete.

## Focused Commit Boundaries

- T013: `test(research): freeze evidence schema and statistics`
- T022: `docs(research): freeze router publication methodology`
- T038: `feat(mlx): add bounded router reference path`
- T049: `test(mlx): reject unsafe router inputs`
- T060: `docs(research): add reproducible router evidence tooling`
- T071: `perf(research): instrument bounded router timings`
- T076: `docs(research): admit immutable router tensor`
- T081: `docs(research): freeze independent router oracle`
- T087: `docs(research): publish raw router parity evidence`
- T088: `docs(research): generate router parity artifacts`
- T091: `docs(research): publish router reproduction evidence`
- T096: `docs: reconcile Feature 002 results`

Each commit is pushed without force and followed by its actual CI result before
the next dependency-sensitive milestone.

## Notes

- Every `[P]` task changes a different file or independent test surface.
- Tests are written and observed failing before their implementation task.
- Feature 001's task list remains closed and unchanged.
- External model data, derived tensor bytes, private paths, caches, binaries,
  and secrets remain outside Git.
- Stop conditions produce retained failed evidence, not weakened acceptance.
