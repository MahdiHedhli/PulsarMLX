# Feature Specification: Qwen3MoE Layer-0 Router Parity

**Feature Branch**: `main` (separately numbered feature on the protected
incremental branch)

**Created**: 2026-08-05

**Status**: Implementation in progress. The model-free research methodology
and generated complete-router reference seam are implemented and validated
locally. External-checkpoint admission, genuine hidden-state capture, and any
real-router result remain unimplemented or unverified at their explicit task
gates.

**Input**: Define and verify the next bounded real-checkpoint slice after
Feature 001: complete layer-0 router projection, deterministic top-8 expert
selection, architecture-correct weighting, independent CPU parity, and
publication-quality correctness and timing evidence.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Verify Real Router Decisions (Priority: P1)

An inference-runtime engineer can apply one or more frozen real layer-0 router
inputs captured by a pinned independent CPU implementation from the already
admitted Qwen3MoE checkpoint and determine which eight experts the architecture
selects, in what order, and with what normalized weights.

**Why this priority**: Expert selection is the required real-checkpoint boundary
between the verified projection prefix and every later selected-expert or
routed-MoE feature. Incorrect IDs, ordering, or weights invalidate all deeper
work.

**Independent Test**: Use the immutable checkpoint identity and a frozen
single-row hidden-state fixture to produce complete router logits and
full-softmax probabilities, selected expert IDs, selected pre-normalization
probabilities, and normalized weights. Compare them with an independently
generated CPU oracle fixed before the Apple result.

**Acceptance Scenarios**:

1. **Given** the exact admitted checkpoint, complete layer-0 router tensor, and
   a frozen single-row hidden state, **when** the bounded Apple router path is
   evaluated, **then** all eight expert IDs and their ordering exactly match the
   frozen independent oracle and every weight is within its predeclared
   tolerance.
2. **Given** a frozen bounded multi-row batch, **when** every row is routed,
   **then** each row independently satisfies the same ID, ordering, weight, and
   no-fallback requirements.
3. **Given** identical immutable inputs, **when** the router experiment is
   repeated at least ten times, **then** expert IDs remain exact and router
   values remain within the deterministic repeatability policy on every run.

---

### User Story 2 - Reject Ambiguous or Unsafe Router Inputs (Priority: P2)

An implementer receives bounded, actionable failures before evaluation when a
router tensor or hidden state is truncated, malformed, dimensionally
incompatible, non-finite, or inconsistent with the admitted checkpoint.

**Why this priority**: A plausible router result from misoriented or incomplete
bytes is more dangerous than an explicit failure because later expert work
could appear correct while following the wrong route.

**Independent Test**: Exercise malformed tensor lengths, incompatible hidden
dimensions, invalid batch shapes, non-finite inputs, and altered checkpoint or
tensor identities without scheduling the accepted Apple execution.

**Acceptance Scenarios**:

1. **Given** a truncated or overlong encoded tensor range, **when** admission is
   attempted, **then** the request fails with the expected-versus-actual byte
   counts and no router result is emitted.
2. **Given** an incompatible hidden dimension or invalid batch shape, **when**
   validation runs, **then** the request fails before evaluated execution.
3. **Given** NaN or infinity in the hidden state or oracle output, **when** the
   comparison is attempted, **then** the experiment fails under a predefined
   non-finite policy rather than silently accepting or normalizing it.
4. **Given** a synthetic exact-tie or near-tie case, **when** top-8 selection is
   evaluated, **then** ordering follows the documented deterministic tie rule;
   the result remains labeled synthetic and does not imply checkpoint routing.

---

### User Story 3 - Publish Reproducible Correctness Evidence (Priority: P3)

A reviewer can trace every public router-parity claim from a claims ledger to
machine-readable raw observations, immutable inputs, oracle construction,
environment facts, exact commands, comparison metrics, and explicit caveats.

**Why this priority**: Feature 002 is intended to be reusable research evidence,
not only a local demonstration. Claims must remain independently auditable and
must not imply a complete MoE block or model.

**Independent Test**: Starting from a clean checkout and an authorized external
checkpoint with the recorded hash, follow the committed reproduction guide,
validate the evidence schema, and regenerate all published router tables from
raw observations without editing reported numbers.

**Acceptance Scenarios**:

1. **Given** a published verified claim, **when** a reviewer follows its ledger
   links, **then** the evidence identifies the clean commit, immutable model and
   tensor, input and oracle hashes, exact command, environment, all raw
   observations, summary statistics, result, and unsupported interpretations.
2. **Given** the committed raw observations, **when** the table-generation
   command runs, **then** it recreates the published values without hard-coded
   measurements or access to model weights.
3. **Given** an unsuccessful or aborted experiment, **when** evidence is
   reviewed, **then** the run remains distinguishable from passing measurements
   and is not silently removed.

---

### User Story 4 - Measure the Bounded Router Honestly (Priority: P4)

A performance researcher can distinguish first-process OS-cache-uncontrolled
and warm loading,
decode/dequantization, projection, top-k, normalization, and total evaluated
router costs where those phases can be observed without materially changing
semantics.

**Why this priority**: Bounded measurements can guide the next expert-path
feature, but only after correctness is established and without extrapolating to
layer or token throughput.

**Independent Test**: Run the frozen benchmark order after the correctness gate,
retain every sample, and verify that the report contains the required warm-up,
measurement, synchronization, statistics, environment, load, and caveat data.

**Acceptance Scenarios**:

1. **Given** a passing router correctness case, **when** its timing protocol is
   executed, **then** at least five warm-ups and at least ten measured costly
   real-checkpoint repetitions are retained for each admitted warm case.
2. **Given** a first-process OS-cache-uncontrolled case and a warm repeated
   case, **when** results are reported, **then** they remain separate and
   include all individual samples plus median, mean, standard deviation,
   minimum, maximum, p5, p25, p75, p95, and coefficient of variation.
3. **Given** system interference or an aborted run, **when** the protocol gate
   detects it, **then** measurement is postponed or labeled with the observed
   interference and never merged silently with clean results.

### Edge Cases

- The checkpoint file exists but its size, checksum, architecture metadata, or
  immutable source revision differs from Feature 001.
- The router tensor name is absent, duplicated, split unexpectedly, has an
  unsupported quantization, or its range crosses an invalid boundary.
- The apparent tensor dimensions permit more than one orientation; execution
  must stop until one orientation is proven by metadata and oracle parity.
- The first 16 router-output rows or another requested validation range is not
  meaningful for the actual tensor shape; the record must explain the
  architecture-correct substitute rather than inventing a case.
- `top_k` differs from eight, exceeds the expert count, or yields equal F32
  probabilities at the selection boundary.
- Selected values underflow, overflow, or produce a non-finite normalization
  denominator.
- A multi-row batch contains repeated or identical rows, exact ties, or rows
  selecting the same experts in different orders.
- The external model is available but memory pressure, disk headroom, thermal
  state, or concurrent workload violates the precommitted admission policy.
- A timing phase cannot be isolated without synchronizing differently or
  materially perturbing the operation; only the minimally instrumented total
  may be promoted in that case.
- A clean-checkout reproduction cannot resolve the exact oracle or model input;
  the claim remains provisional or blocked.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The feature MUST use exactly the immutable Qwen3MoE checkpoint
  admitted by Feature 001 and MUST reject any mismatch in repository, revision,
  file name, byte size, or SHA-256 before execution.
- **FR-002**: The feature MUST identify the complete layer-0 router tensor by
  exact name, offset, encoded length, logical dimensions, orientation, data
  type, quantization, and source-file identity.
- **FR-003**: The feature MUST define one or more frozen real layer-0 router
  input fixtures captured from the same checkpoint by a pinned independent
  CPU-only implementation. Each fixture MUST record its exact graph boundary,
  direct token IDs `[0,1]`, positions `[0,1]`, no-tokenizer input adapter,
  context/batch/ubatch/thread parameters, selected rows, shape, data type, byte
  order, capture procedure, full hash, and the deeper graph behavior it does
  not establish for PulsarMLX. Token IDs MUST be proven inside the observed
  vocabulary and the two captured rows MUST differ; otherwise capture stops.
- **FR-004**: The feature MUST freeze an independent CPU oracle before
  inspecting the corresponding Apple outputs. The oracle MUST NOT call the
  implementation under test and MUST record its tool identity and immutable
  inputs and outputs.
- **FR-005**: The feature MUST compute complete router logits and complete
  full-softmax probabilities for every admitted hidden-state row, retain each
  raw array or its stable full-output hash plus sufficient bounded values for
  review, and numerically compare both outputs with the independent oracle.
- **FR-006**: The feature MUST select exactly eight experts per real-checkpoint
  row using the architecture's documented ordering and tie behavior.
- **FR-007**: The feature MUST retain selected expert IDs, selected
  full-softmax probabilities before selected-sum renormalization, and normalized
  routing weights for every row.
- **FR-008**: The feature MUST apply the exact architecture-correct router
  normalization and weighting semantics proven from checkpoint metadata and an
  independent implementation.
- **FR-009**: Expert IDs and ordering MUST match the independent oracle exactly;
  logits, complete and selected full-softmax probabilities, and normalized
  weights MUST use absolute and relative tolerances fixed before Apple
  execution.
- **FR-010**: Correctness evidence MUST report compared counts, mismatch count,
  first mismatch location, maximum and mean absolute error, RMSE, and maximum
  relative error where meaningful.
- **FR-011**: Every admitted real case MUST run at least ten identical evaluated
  repetitions and record deterministic expert IDs plus per-run numerical
  summaries.
- **FR-012**: The Apple path MUST select the intended GPU explicitly, force
  evaluation and synchronization before readback or timing completion, and
  reject any CPU fallback.
- **FR-013**: Required real cases MUST include a single row and a bounded
  multi-row batch, and every route decision MUST use all 128 router outputs.
  Evidence MUST highlight rows 0 through 15 and at least one additional
  non-overlapping router-output range as spot checks while retaining the full
  output. The Feature 001 16-row expert-gate prefix MUST be declared
  inapplicable because it belongs to a different tensor.
- **FR-014**: A separate synthetic tie or near-tie case MUST verify deterministic
  selection at the top-8 boundary without being presented as real-checkpoint
  evidence.
- **FR-015**: Malformed, truncated, overlong, dimension-mismatched, orientation-
  ambiguous, invalid-`top_k`, and non-finite cases MUST fail with bounded
  structured errors before an accepted result is published.
- **FR-016**: The feature MUST preserve the completed Feature 001 source of truth
  and all inherited Linux/CUDA selection and runtime behavior.
- **FR-017**: Before measurements, the repository MUST contain a frozen
  experiment protocol, versioned evidence schema, reproducibility guide,
  results and limitations structure, claims ledger, and raw/table/figure
  conventions.
- **FR-018**: Every experiment record MUST contain all non-sensitive environment,
  source, model, tensor, command, input, oracle, timing, correctness, resource,
  result, and caveat fields required by the publishable evidence standard.
- **FR-019**: Public evidence MUST omit usernames, absolute home paths, machine
  identifiers, credentials, tokens, and model bytes while retaining reproducible
  immutable identities.
- **FR-020**: Timing MUST use a monotonic high-resolution source, synchronize
  evaluated work, separate observable phases, retain first-process
  OS-cache-uncontrolled and warm runs, and preserve every raw observation under
  the frozen exclusion policy. A run MAY be called controlled-cold only when
  cache control is independently proved and recorded.
- **FR-021**: Admitted timing cases MUST use at least five warm-ups and at least
  ten measured real-checkpoint repetitions; inexpensive synthetic
  microbenchmarks MUST use at least thirty measured repetitions.
- **FR-022**: Summary output MUST include median, arithmetic mean, standard
  deviation, minimum, maximum, p5, p25, p75, p95, and coefficient of variation
  computed from retained raw samples.
- **FR-023**: Loading, decode/dequantization, projection, top-k, normalization,
  and total evaluated execution MUST be measured separately only when the
  instrumentation preserves semantics; otherwise the evidence MUST explain the
  unavailable phase and retain a minimally instrumented total.
- **FR-024**: The protocol MUST record system load, power mode when observable,
  thermal state before and after when observable, benchmark order, and any
  interference; incompatible conditions MUST not be merged silently.
- **FR-025**: The minimally instrumented single-row real router case and the
  minimally instrumented two-row real router case are the two major benchmarks.
  At least one complete clean-process replication MUST be retained for each,
  and a second experiment batch MUST be collected later when feasible or
  explicitly marked unavailable. Stage-instrumented series are diagnostic and
  are not additional major benchmarks.
- **FR-026**: Checked-in validators MUST reject incomplete evidence, invalid
  statistics, missing raw observations, capability overclaims, and unsupported
  promotion from router evidence to expert, layer, model, generation, serving,
  or token-throughput claims.
- **FR-027**: Checked-in generators MUST recreate every published Feature 002
  table and any figure solely from committed machine-readable raw evidence and
  MUST NOT hard-code reported measurements.
- **FR-028**: The claims ledger MUST contain one row per public claim with linked
  evidence, clean commit, exact scope, status, and caveat. Only clean-checkout
  reproduced claims may be marked verified.
- **FR-029**: External-checkpoint execution MUST remain an explicit local-only
  command. CI MUST cover all schema, oracle-contract, malformed-input, synthetic,
  and generated-output checks that do not require the checkpoint.
- **FR-030**: The operator MUST be notified on NTFY topic `Mahdi-Dev` immediately
  before external model access and after Feature 002 completes or blocks.
- **FR-031**: Model weights, extracted tensors, private data, secrets, local
  caches, and large generated outputs MUST remain outside Git; precommit review
  MUST verify the boundary.
- **FR-032**: The exact router evidence MUST explicitly exclude expert MLP
  execution, routed-MoE aggregation, a complete transformer layer,
  language-model-head or model-output logits, generation, serving, custom
  Metal, full or giant model inference, projected tokens per second, and
  Linux/CUDA runtime parity.

### Key Entities

- **Checkpoint Identity**: Immutable repository, revision, file, size, SHA-256,
  license/provenance, architecture, and quantization identity reused from
  Feature 001.
- **Router Tensor Contract**: Exact layer-0 tensor name, file range, encoded
  layout, logical shape, orientation, data type, quantization, and expert count.
- **Hidden-State Fixture**: Frozen single-row or bounded batch input with an
  independent construction procedure, semantic scope, shape, bytes, and hash.
- **Router Oracle Result**: Frozen CPU logits, full-softmax probabilities,
  selected IDs, selected probabilities, normalized weights, hashes, and
  comparison policy generated independently of the Apple path.
- **Router Execution Result**: Evaluated-device identity, no-fallback state,
  output hashes and bounded values, per-run comparisons, and deterministic
  repeatability outcome.
- **Experiment Record**: Versioned, sanitized environment and command metadata,
  raw correctness/timing/resource observations, statistics, result, warnings,
  and exclusions for one immutable experiment.
- **Claim Ledger Entry**: One bounded public statement mapped to evidence,
  commit, scope, status, and caveat without implication to deeper capabilities.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every admitted single-row and multi-row real case has exact top-8
  expert ID and ordering parity with the frozen independent oracle.
- **SC-002**: Every compared router logit, complete and selected full-softmax
  probability, and normalized routing weight is within its predeclared absolute
  and relative tolerance, with zero mismatches outside tolerance and all
  required error metrics reported.
- **SC-003**: At least ten identical evaluated repetitions per real case retain
  identical expert IDs and satisfy the numeric repeatability policy on every
  run.
- **SC-004**: Every accepted Apple result identifies the intended device,
  records evaluated synchronization, and reports no fallback.
- **SC-005**: The required single-row, bounded batch, two non-overlapping output
  ranges, synthetic tie/near-tie, malformed tensor, dimension mismatch,
  invalid-`top_k`, and non-finite cases all produce their predefined results.
- **SC-006**: All published experiments validate against the versioned evidence
  schema and retain every required raw observation, environment field,
  immutable identity, command, oracle, result, warning, and exclusion without
  private data.
- **SC-007**: Each admitted real timing case retains at least five warm-ups and
  ten measured repetitions, while admitted inexpensive synthetic cases retain
  at least thirty measurements; all required statistics reproduce from raw
  samples.
- **SC-008**: First-process OS-cache-uncontrolled and warm results remain
  separately identifiable, at least one clean-process replication exists for
  each of the two declared major benchmarks, and no sample is removed outside
  the frozen exclusion rule.
- **SC-009**: A clean checkout plus the authorized model file and exact recorded
  command reproduces every claim marked verified and regenerates all published
  tables from committed raw evidence.
- **SC-010**: Exact workspace check and test gates remain green on macOS, and
  fixture-only CI passes without accessing an external checkpoint.
- **SC-011**: Staged review finds no model weights, extracted tensors, secrets,
  private paths, private machine identifiers, caches, binaries, or unintended
  Linux/CUDA selection changes.
- **SC-012**: No Feature 002 document or result presents router parity as expert
  execution, routed-MoE or layer parity, model inference, generation, serving,
  performance beyond the bounded router, custom Metal, tokens per second,
  giant-model execution, or Linux/CUDA runtime validation.

## Scope Boundaries and Stop Conditions

Feature 002's PulsarMLX/Apple path stops after complete router logits, top-8 IDs,
and normalized weights for the admitted bounded fixtures. It does not execute
expert MLPs or any deeper model graph. The independent CPU fixture-capture
helper evaluates the pinned upstream graph only through `ffn_norm-0` to produce
the real input; that establishes fixture provenance, not PulsarMLX attention,
residual, or normalization parity. Expert execution remains forbidden in both
paths. Stop, preserve failing evidence, and do not weaken the acceptance
criteria when:

- checkpoint provenance, license, revision, size, checksum, architecture, or
  router tensor identity cannot be proven;
- hidden-state semantics, tensor orientation, normalization, or tie behavior
  remains ambiguous after bounded source and oracle investigation;
- the independent oracle cannot be frozen without sharing the implementation
  under test;
- any expert ID differs, a numeric result exceeds its frozen tolerance, an
  evaluated result falls back, or ten-run repeatability fails;
- disk, memory, thermal, or concurrent-load admission fails;
- instrumentation materially changes semantics and no minimally instrumented
  total can be retained;
- progress would require changing inherited Linux/CUDA behavior, committing
  model data or secrets, custom Metal, or a destructive action; or
- clean-checkout reproduction or evidence validation cannot be achieved without
  inventing, deleting, or relabeling results.

## Assumptions

- The exact external Qwen3MoE Q8_0 file admitted by Feature 001 remains legally
  accessible locally and will not be downloaded again.
- A real router-input fixture can be captured from a pinned independent CPU-only
  execution of the same GGUF without downloading another checkpoint. If that
  capture cannot be achieved and independently hashed, deterministic
  model-shaped inputs remain synthetic and Feature 002 stops rather than
  relabeling them as real.
- The architecture's expert count and top-8 policy can be proven from immutable
  checkpoint metadata plus an independent implementation before Apple output.
- Router correctness in the PulsarMLX/Apple path can be validated without
  executing an expert, attention, residual path, language-model head, or
  generation loop. The separate pinned CPU fixture-capture path necessarily
  executes embedding, layer-0 attention, residual, and FFN RMS normalization
  only through `ffn_norm-0`, without establishing parity for those operations.
- The current Apple host can admit the complete router tensor and bounded batch
  while preserving the documented unified-memory reserve; admission will be
  rechecked immediately before model access.
- Public raw evidence may contain bounded numerical router outputs and hashes
  when licensing permits, but never checkpoint tensor bytes or extracted
  weights.
- Hosted CI cannot access the external checkpoint and therefore validates only
  committed fixtures, schemas, generators, contracts, and claim boundaries.
- Feature 001 remains closed; any demonstrable factual correction would be a
  separate documentation change rather than a reopened task.
