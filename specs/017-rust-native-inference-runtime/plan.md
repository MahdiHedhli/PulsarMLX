# Implementation Plan: 017-rust-native-inference-runtime

**Branch**: `feat/017-rust-native-inference-runtime`
**Feature Spec**: `spec.md`
**Status**: Draft, bounded and inventory-driven

## Phase 0 — Reconciliation and repository lockstep

- Confirm branch state and `main` ancestry in `a948b68d9868a34b0cc9b00aacaa4ad2330b0f55`.
- Confirm Feature 016 evidence remains immutable.
- Ingest authoritative post-run and trunk inventory files as read-only inputs.

## Phase 1 — Spec and contracts (completed)

- `spec.md`, `plan.md`, `tasks.md`, `checklists/requirements.md`, and starter contracts are in place and aligned to authoritative metrics.

## Phase 2 — Portable differential fixture contract

- Add validator that reads fixture manifests and verifies:
  - source commit and checkpoint identity
  - tensor id, dimension, quantization, shard, and range
  - position/layer/offset metadata
  - payload hash and provenance
- Reuse previously generated public-safe samples when available; no private weight bytes in source.

Gate: manifest validation succeeds and rejects missing fields or unknown checksums.

## Phase 3 — Inventory-driven residency model

- Ingest `f016-gguf-trunk-inventory-0001.json` and derive slot classes from measured dimensions and use counts.
- Define slot-size classes from empirical trunk distributions and natural residency candidates.
- Model options A–F from Feature 016 derived table.

Gate: no hard-coded slot size constants are introduced without deriving from inventory.

## Phase 4 — Native slab allocator

- Design and implement allocator contract first; enforce bounded alignment, zeroing policy, and ownership.
- Add explicit failure modes and deterministic reuse behavior.
- Add occupancy, peak, request/allocate metrics.

Gate: deterministic stress tests confirm no UAF and safe pressure rejection.

## Phase 5 — Whole-matrix positional I/O

- Implement full-tensor/matrix positional read as the primary contract.
- Keep row reads as a test helper and compatibility mode.
- Add overflow checks, exact byte accounting, cancellation hooks, and request-count telemetry.

Gate: row-read amplification can be measured and improved with bounded whole-read path.

## Phase 6 — Telemetry split and attribution

- Add split telemetry fields for each of:
  - storage/read
  - decode
  - materialization
  - backend build/import
  - compute
- Ensure totals are traceable to boundary-level stages.

Gate: one-layer representative call produces non-overlapping attribution buckets.

## Phase 7 — Exact Rust decode qualification

- Qualify decoder boundary against existing Feature 016 anchors.
- Start with the required baseline formats and add malformed/truncated rejection tests.

Gate: at least one exact or numerically qualified format is committed with deterministic classification.

## Phase 8 — Residency + bridge implementation

- Build residency abstractions for compressed, decoded-hot, transient, and hybrid experiments.
- Add Objective-C++ bridge spike and command/teardown ordering.
- Demonstrate deterministic read/write ownership, registration, and destruction.

Gate: stable registration lifecycle with no silent fallback and explicit teardown order.

## Phase 9 — Native MLX boundary ADR

- Evaluate available options (C API, shim, ObjC++), and produce ADR for minimal-risk path.

Gate: recommendation published before adopting deeper MLX-native compute.

## Phase 10 — Runtime skeleton

- Add reusable runtime configuration, model identity, catalog, telemetry, cancellation, and execution traits.
- Keep GLM-specific math behind trait/plugin boundary.

Gate: rust-only initialization without requiring model execution service.

## Phase 11 — Checkpoint-free ladder with mode-aware validation

- Build ladder boundaries in order, with hard stop on any unsupported mismatch:
  1. byte-range tensor read
  2. one quant block decode
  3. complete matrix decode
  4. matrix/reference compare
  5. router boundary
  6. one expert projection
  7. complete expert
  8. top-8 + shared MoE
  9. representative MLA/dense
  10. representative layer
  11. final logits
- Apply `golden_strict` and `teacher_forced_validation` classes.

Gate: ladder advances only when previous boundary remains deterministic and bounded.

Current boundary: R6-R12 are composed checkpoint-free. The permanent exact-order
qualification scaffold is bit-identical to the independent R7, R9, R10, R11,
and R12 oracles. Production R7/R8 qualify under the frozen expert Tier-B contract; R9
MLA/DSA and R10 complete-layer execution qualify under separately frozen,
fail-closed composition contracts with ten deterministic repeats. The
adversarial review accepted the numerical evidence subject to the now-applied
classification/applicability remediation. R7 carries an explicit vocabulary
amendment; current R9/R10 evidence binds to reviewed v2 contracts that preserve
all thresholds while tightening internal-selection divergence to numerical
failure. R11 final logits/top-k and R12 two-layer canonical-binary execution
pass their frozen exact and production gates with exact greedy identity, zero
fallback, and reconciled lifecycle accounting. The next gate is internal plus
independent adversarial review; no real checkpoint or M1-C/P1 model time is
admitted.

Pre-M1 remediation status: production admission now uses measured host
telemetry and hard gates; the reviewed environment manifest and actually
loaded MLX libraries are verified; evidence output is exclusively acquired;
PASS is persisted only after teardown and dispatch reconciliation; identity
mode validates the complete production `Glm52TensorMap`; and R12 production no
longer invokes the qualification scaffold. Production stage modes now require
the `production_reviewed` environment before telemetry, adapter, or checkpoint
work, while an explicit fixture identity mode preserves checkpoint-free CI.
Apple-native CI explicitly executes both loaded-library match/mismatch tests.
T017-160 and T017-161 are closed by the internal and independent review GOs.
Exactly one M1-A production adapter preflight passed and its public-safe
evidence is banked. Exactly one separately authorized M1-B production identity
run also passed: all six shards, checkpoint/catalog/tokenizer identities, and
the 79-layer / 1,809-tensor production map validated with zero tensor decode or
compute dispatch. Exactly one separately authorized M1-C read then captured
and independently validated the local-only `output_norm.weight` F32 boundary
with zero tensor execution or compute. T017-140 is complete. M1-D is prepared
but not authorized; T017-141 and P1 remain blocked.

## Final phase

- No 018 kernels are selected inside this feature.
- M1 Ultra parity is not requested until the ladder, residency budget gates, and bridge ownership are green.

## Phase 12 — Canonical runner contract

- Freeze the dedicated binary name, strict CLI, exit classes, validation modes,
  public-safe evidence schema, and atomic progress rules.
- Bind the runner to the production F017 adapter; prohibit Python orchestration,
  Linux/CUDA engine substitution, Feature 018 kernels, and hidden fallback.

Gate: contract/schema tests reject unknown options, duplicate keys, invalid
mode combinations, and incomplete lifecycle evidence.

## Phase 13 — Runner identity and storage vertical slice

- Add an immutable multi-shard manifest with exact shard identities.
- Compose the existing GGUF parser and positional reader into one production
  catalog/store with overflow, short-read, duplicate-name, and path-sanitizing
  failures.
- Implement `--dry-run`, `--checkpoint-identity-only`, and a fake split-GGUF
  fixture without checkpoint downloads.

Gate: the actual binary reaches R4 and records exact read/hash evidence from a
tiny public-safe multi-shard fixture.

## Phase 14 — Production adapter execution surface

- Bind `--adapter-preflight-only` to the actual production adapter.
- Add only typed MLX C operations required by the next semantic boundary,
  starting with shaped f32 import, matvec, bounded result extraction, and
  explicit synchronization.
- Record capability, dispatch, setup, compute, synchronization, and ownership
  telemetry with no silent fallback.

Gate: R5 projection fixture passes against its independent oracle on the native
Apple job and every lifecycle counter reconciles.

## Phase 15 — GLM-5.2 runtime composition

- Validate the complete 79-layer `glm-dsa` tensor map before execution.
- Compose router, expert, MLA/DSA, layer, final-output, and generation state in
  R6 through R11 order.
- Run a tiny synthetic multi-layer model through the actual runner binary at
  R12; no unit-only bypass satisfies this gate.

Gate: the checkpoint-free end-to-end runner produces its expected token,
complete evidence, cancellation behavior, and zero lifecycle state.

## Phase 16 — Local-only and M1 ladder

- Consume hash-bound, non-redistributed R13 boundary fixtures on the M2/M1
  development machines.
- Review and bank M1-A through M1-G separately before documenting the literal
  M1-H command.
- M1-H requires a new independent review and a fresh one-P1 authorization.

Gate: do not claim P1 readiness before R0-R14 and M1-A through M1-G are green.

## Phase 17 — DPREFIX oracle reproducibility closure

- Preserve REAL-2 and REAL-3 as distinct BLAS-class persisted authorities.
- Characterize their byte delta from the immutable retained packed package.
- Produce DPREFIX-EXACT-1 through independently implemented, fixed-order,
  non-BLAS scalar scaffolds and require fresh-process bitwise identity.
- Require every successor identity gate to name an exact, bounded, or
  persisted-authority reproducibility mechanism.
- Propagate the exact/BLAS ambiguity through routing only when the retained
  layer-3 attention and router surface can support all 1,984 v3 membership
  inequalities and expert-ID keyed weight intervals.

Gate: no route-invariance claim, representative M1-F0 execution, dense-prefix
replay, or checkpoint access while the load-bearing route-propagation bytes or
a reviewed global propagation bound are absent.

## Phase 18 — Routing-contract v3.1 theorem freeze

- Bind the committed GLM-5.2 FFN RMSNorm, sigmoid-plus-correction-bias top-8,
  selected-probability normalization, scale, and atomic ID/weight semantics.
- Freeze a binary64 directed-outward componentwise theorem from an arbitrary
  finite layer-3 entry-state box through RMSNorm, row-specific router logits,
  selection scores, strict selected/unselected differences, safety factors,
  and ID-keyed selected-weight intervals.
- Validate the theorem only with synthetic, adversarial, mutation, and sampled
  property fixtures; no retained private numerical value is an input to the
  freeze.
- Keep ordered top-8 rank diagnostic, mathematical factor threshold 1 distinct
  from engineering H=2, and require selected-set invariance before weight
  qualification.

Gate: the public theorem package is hash-bound, its outward enclosures contain
all synthetic samples, historical DPREFIX evidence remains immutable, and the
real-payload ledger remains 139 before any real ambiguity-box evaluation.

## Phase 19 — Canonical selected-expert output recovery authorization

- Derive the exact gate/up/down positional slices for the eight invariant
  selected expert IDs from committed checkpoint metadata.
- Freeze one future shard-2 open, 24 reads, 90,439,680 packed bytes, durable
  partial-read accounting, and a 139-to-163 successful ledger transition.
- Bind the retained DPREFIX-EXACT-1 f32 state and FFN norm to strict f32
  RMSNorm, IQ2_XXS/IQ3_XXS decode, row-major projections, SwiGLU, and eight
  canonical f32 `[6144]` down outputs.
- Require packed retention at creation and two fresh-process fixed-order output
  reproductions without checkpoint rereads; keep aggregate evaluation and all
  downstream execution outside this event.

Gate: the metadata-only authorization package validates and is independently
reviewed before any checkpoint open or payload read; preparation leaves the
real-payload ledger at 139.

The execution release additionally requires a pre-execution amendment: every
retained IQ2_XXS/IQ3_XXS payload must be decoded by two independently bound
accepted implementations, compared by exact canonical f32 identity, and pass
before the next checkpoint read. A disagreement terminates without selecting a
decoder or granting output authority. This amendment itself performs zero
checkpoint access and requires renewed independent review.

## Phase 20 — Canonical selected-expert output reuse authorization

- Preserve the completed recovery event as terminal immutable history and
  authorize only its eight ID-keyed canonical f32 `[6144]` down outputs for a
  distinct checkpoint-free analytical consumer.
- Bind every output to its retained-object SHA, canonical DPREFIX-EXACT-1
  input, and expert-specific gate/up/down packed identities; require regular,
  read-only, single-link, non-symlink storage with equal before/after hashes.
- Restrict consumption to the frozen weighted-MoE aggregate perturbation
  theorem and its unchanged R10 intermediate budgets; aggregate arithmetic
  remains outside the authorization loop.
- Publish only package-relative symbolic names and public identities, never
  private bytes or machine-local paths.

Gate: the public authorization/schema and private verifier pass all identity,
provenance, mutation, privacy, ledger, and historical-immutability checks with
checkpoint reads and shard opens zero and the real-payload ledger fixed at 163.

## Phase 21 — Weighted-MoE aggregate safety evaluation

- Consume only the eight reuse-authorized canonical expert down outputs and
  already-banked ID-keyed routing-weight/joint-normalization evidence.
- Apply the unchanged frozen direct and normalization-centered enclosures,
  intersect them componentwise, and compare the resulting max-absolute, RMSE,
  and cosine bounds only with the unchanged R10 v2 intermediate budgets.
- Reproduce the complete public evaluation byte-identically twice, rehash the
  eight persisted-authority outputs before and after, and preserve membership,
  coefficient, and aggregate conclusions as three separate facts.

Gate: any failed aggregate budget keeps `ROUTE NOT PROVEN INVARIANT`; no theorem
or tolerance adjustment, checkpoint access, payload-ledger mutation, or M1-F0
authorization occurs in this phase.

## Phase 22 — Complete-layer aggregate acceptance v2 freeze

- Bind the production complete-layer value as the final binary32 cast of the
  canonical residual plus the binary64 routed/shared combination.
- Apply the immutable R10 final-output thresholds (`0.0625`, `0.03125`, and
  cosine `0.999`) while preserving routed-only v1 and its FAIL unchanged.
- Reuse the frozen v1 routed interval, include final-f32 transport, and freeze a
  value-agnostic Euclidean tangent-ball cosine theorem with separate H=2.
- Treat a future exact-class shared output as a point only within the frozen
  routing-weight ambiguity proof and derive its exact three-payload recovery
  inventory from committed catalog metadata.

Gate: synthetic/adversarial/property and public validation pass before any real
shared output is observed; checkpoint reads and shard opens remain zero and the
real-payload ledger remains 163 pending a separately reviewed recovery event.

## Phase 23 — Canonical shared-expert output reuse authorization

- Preserve the completed shared-expert recovery event as terminal immutable
  history and authorize only its canonical little-endian f32 `[6144]` output
  for a distinct checkpoint-free complete-layer-v2 analytical consumer.
- Classify the retained object as `PERSISTED_AUTHORITY` produced by the reviewed
  exact-class strict-f32, fixed-order, no-BLAS computation and require equal
  expected/before/after SHA identities plus regular, read-only, single-link,
  non-symlink storage.
- Permit `delta_S=0` only for the frozen routing-weight ambiguity proof with
  this exact canonical point artifact; do not generalize the point rule.
- Bind the immutable routed-output reuse authorization, exact weights,
  intervals, routed nominal aggregate, and routed sound enclosure without
  recomputation or complete-layer metric evaluation.

Gate: the public schema/authorization and private verifier pass provenance,
identity, mutation, privacy, routed-compatibility, ledger, and historical-
immutability checks with checkpoint reads and shard opens zero and the real-
payload ledger fixed at 166.

## Phase 24 — Representative M1-F0 semantic boundary v2 freeze

- Freeze the exact production layer-3 graph from the canonical pre-attention
  entry through attention, the post-attention residual, FFN RMSNorm, routing,
  routed/shared FFN work, and the final residual-added output.
- Correct the direct-DPREFIX v3.1, recovered expert/shared outputs, routed-v1,
  and e942 lineage append-only as valid evidence on a direct-DPREFIX FFN/MoE
  analytical surface, not as representative post-attention M1-F0/M1-F truth.
- Preserve the historical accepted M1-F0 attempt unchanged while freezing a
  new representative boundary from DPREFIX-EXACT-1 through layer-3 attention
  and routing only; expert, shared-expert, complete-layer, and candidate work
  remain outside M1-F0.
- Derive the nine hash-only attention payload descriptors and require separate
  cross-event authorization for the three retained router authorities before a
  future independently reviewed one-open CPU fixed-order recovery event.
- Bind future NTFY progress points and prohibit GPU/LM Studio disturbance for
  the CPU-only execution class.

Gate: the semantic graph, append-only correction index, boundary contract,
inventory arithmetic, identity-gate rules, and mutation tests validate with no
execution authorization, checkpoint reads, shard opens, GPU dispatch, or ledger
change; the real-payload ledger remains 166 and the future success shape is
separately reviewed as nine reads, 132,900,864 packed bytes, and ledger 175.

## Phase 25 — Representative M1-F0 RMSNorm epsilon adjudication

- Rank committed model configuration, production runtime plumbing, historical
  accepted M1-F0 execution, independent R9/dense-prefix oracles, and the later
  boundary freeze by semantic relevance and executable authority.
- Bind the single GLM-5.2 RMSNorm epsilon as `f32(1e-5)`, exact decimal
  `9.999999747378752e-6` and bits `0x3727c5ac`, at layer-3 attention input,
  query-rank, compressed-KV, and post-attention FFN normalization sites.
- Preserve the semantic graph v1, representative boundary v2, and their freeze
  as historical bytes while superseding their unsupported `1e-6` transcription
  with graph v2 and boundary v3.
- Reject synthetic and legacy `1e-6` helpers as production numerical authority,
  and add mutation tests that fail on epsilon, site, dtype, or authorization
  regression.

Gate: the corrected public package reconstructs the authority chain from
committed bytes, preserves historical accepted execution evidence, grants no
real-event authority, performs no checkpoint or shard access, and leaves the
real-payload ledger exactly 166.

## Phase 26 — Representative M1-F0 execution authorization preparation

- Bind the corrected boundary v3, semantic graph v2, epsilon adjudication, and
  canonical pre-attention DPREFIX input to one review-gated attention-to-router
  event that stops before all expert and M1-F execution.
- Re-derive the exact ordered nine-read inventory from committed catalog
  metadata and quant-block arithmetic, with one shard open, 132,900,864 packed
  bytes, no fallback reads, and durable partial accounting from ledger 166.
- Prepare a separate consumer-scoped reuse authority for the retained FFN norm,
  router matrix, and correction bias, requiring immutable before/after identity
  checks and forbidding checkpoint fallback or direct-DPREFIX output reuse.
- Freeze strict binary32 fixed-order attention/residual/FFN-normalization and
  mixed f32/f64 routing semantics, canonical output serialization, ten retained-
  material fresh-process repeats, and terminal no-retry behavior.
- Reject mutations to the head, semantic identities, epsilon or dtype,
  inventory order/ranges/totals, shard-open/read budget, ledger interval,
  partial-failure doctrine, router reuse, or stop boundary.

Gate: the authorization remains `PREPARED_REVIEW_REQUIRED`,
`real_event_authorized=false`, checkpoint reads and shard opens remain zero,
the ledger remains 166, and independent adversarial review is the only next
step.

## Phase 27 — Representative M1-F0 authorization executor repair

- Preserve rejected authorization v1 byte-for-byte and add a v2 review wrapper
  over a hash-bound full candidate rather than editing historical evidence.
- Instantiate the authorized shape with one narrow executor: nine allowlisted
  checkpoint payloads, three retained router authorities, one separately
  resolved DPREFIX-EXACT-1 S0 authority, and no expert or candidate path.
- Make exact-size consumption durably recoverable through attempt/start,
  per-read receipts, journal/ledger reconciliation, retain-before-decode, and
  terminal no-resume/no-retry banking.
- Emit a single canonical stage vocabulary directly, including
  `post_attention_residual`, `router_scores`, `ranking`, `selected_ids`, and
  `routing_weights`, while retaining only an explicit historical-name map.
- Rehearse the entire 132,900,864-byte geometry twice in fresh processes and
  exercise interrupt, short-read, hash, decoder, retained-input, ordering,
  open-count, retry, epsilon, vocabulary, direct-surface, and expert guards.
- Anchor packed and decoded identities to accepted attempt-2 evidence and
  enforce F32 packed/decoded equality, retained S0 manifest identity, exact
  executor/rehearsal bindings, and non-presence-only semantic validation.

Gate: v2 remains `PREPARED_REVIEW_REQUIRED` with
`real_event_authorized=false`; real checkpoint reads, shard opens, expert
computations, and representative real computations remain zero; the ledger
stays 166 and independent adversarial re-review is the only next action.

## Phase 28 — Representative M1-F0 review-2 repair and v3 rebind

- Preserve authorization v1/v2 and commit the consolidated independent REJECT
  verdict at the exact operator-supplied SHA before treating it as authority.
- Scope retained-router reuse to the exact representative event consumer and
  prohibit aliases, fallback, or implicit inheritance.
- Restore a ten-run reproduce-from-retention contract with 10/10 stage and
  route identity, at least two fresh processes, finite checks, before/after
  hashes, and zero checkpoint rereads or additional opens.
- Complete all locally checkable ledger, retained-authority, decoder,
  environment, storage, destination, and shard-object gates before attempt
  start or shard open; consume each retained object through the descriptor
  actually validated.
- Establish the crash invariant that a durable receipt implies a durable
  recoverable packed payload, and terminalize every interrupted attempt from
  validated receipts/retention without resume, reread, retry, or second
  attempt.
- Rehearse two successful fresh processes, ten retained-only reproductions,
  the production computation adapter at full real geometry, and exactly 29
  committed fail-closed mutation/crash paths.

Gate: authorization v3 is append-only and `PREPARED_REVIEW_REQUIRED`, all
R1/R2/R3 and N7-N11 validators pass, previous authorizations retain their exact
identities, real checkpoint reads and shard opens remain zero, the real ledger
remains 166, and independent adversarial re-review is the only next action.

## Phase 29 — Representative M1-F0 single-use execution release preparation

- Preserve accepted authorization v3 and its independent acceptance byte-for-
  byte while preparing a narrower one-shot control-plane release.
- Bind the reviewed execution code head, every accepted implementation and
  contract identity, canonical S0, exact ordered nine-read inventory, shard,
  pinned CPU environment, 3 GiB pre-open storage floor, and ledger 166-to-175.
- Define release consumption at the durable attempt-start boundary and keep it
  irrevocably consumed after every partial, crash, compute, reproduction, or
  evidence failure; only a failure before attempt start leaves it unconsumed.
- Require a separate committed independent approval and a later distinct
  operator invocation; preparation itself keeps all checkpoint, shard, and
  real-event gates false.
- Reject mutations to identities, inventory, head, environment, storage,
  ledger, stop boundary, one-shot semantics, or approval state.

Gate: the release remains `PREPARED_FOR_INDEPENDENT_APPROVAL`,
`real_event_authorized=false`, checkpoint reads and shard opens remain zero,
the real ledger remains 166, and separate independent release approval is the
only next action.

## Phase 30 — Representative M1-F0 pre-attempt ledger-binding repair

- Preserve authorization v3, release v1, its independent approval, and the
  accepted wrapper v1 byte-for-byte after the one authorized invocation failed
  before attempt start with zero reads and zero shard opens.
- Normalize the two exact committed ledger authorities through a versioned
  adapter that binds artifact hashes, schemas, versions, provenance fields,
  top-level field names, integer types, cross-source agreement, and ledger 166
  without legacy-field fallback.
- Bind an append-only wrapper v2 to that adapter and make preflight-only execute
  the real ledger reconstruction that wrapper v1 skipped.
- Regress the exact public-result `ledger_after` shape plus missing, malformed,
  stale, nested-substitution, schema-drift, wrong-value, and disagreement cases.
- Prepare release v2 against the repaired execution-code commit while keeping
  approval and real-event authority false and rejecting the release-v1 token.

Gate: the former `KeyError: ledger` case passes checkpoint-free through wrapper
v2, malformed authority fails before attempt start, no state root exists,
checkpoint reads and shard opens remain zero, the ledger remains 166, and a
fresh independent review and separate approval/token are required before any
real execution.

## Phase 31 — Representative route, expert authorization, and retained-only release

- Bank the successful representative attention-to-router execution at ledger
  175, then reconstruct and independently accept the concrete representative
  route from retained-only evidence without checkpoint rereads.
- Bind the representative `router_normalized` input, atomic expert ID/weight
  pairs, and the 24 position-independent retained expert-weight payloads into a
  checkpoint-free expert-output recovery authorization.
- Preserve a strict retained-only event class: ledger 175-to-175, zero
  checkpoint reads, zero shard opens, 90,439,680 retained packed bytes, and a
  stop after eight concrete individual expert outputs before any aggregate,
  shared expert, FFN completion, or S2 construction.
- Prepare a one-shot release wrapper with authoritative ledger reconstruction,
  pinned runtime checks, consume-what-you-validated inputs, fixed destinations,
  durable attempt-start, crash terminalization, two fresh-process output
  reproduction, separate independent approval, and a later operator token.
- Bank exact cycle-1 REJECT and cycle-2 ACCEPT reviewer artifacts; treat both
  blocking and non-blocking-required findings as release-blocking.

Gate: the release is independently accepted but remains
`PREPARED_FOR_INDEPENDENT_APPROVAL`, `real_event_authorized=false`, ledger 175,
checkpoint reads and shard opens zero, and no real representative expert
execution has occurred. The only next action is a separate independent release
approval; do not create a GO token or execute.

## Phase 32 — Retained-only representative expert-output recovery

- Execute the separately approved one-shot retained-only release exactly once
  from the canonical representative `router_normalized` input and the 24
  retained packed expert weights.
- Preserve ledger 175-to-175 with zero checkpoint reads, zero shard opens, and
  zero checkpoint bytes; require all retained inputs to hash identically before
  and after computation.
- Bank eight concrete little-endian f32 `[6144]` expert outputs in canonical
  representative ID order and require two fresh-process exact reproductions.
- Stop before weighted aggregation, shared-expert execution, FFN completion,
  or S2 construction.

Gate: terminal disposition is `COMPLETE`, eight finite output authorities are
banked, 2/2 retained-only reproduction passes, downstream execution counts are
zero, and ledger remains 175. The next action is checkpoint-free cross-event
reuse authorization for these outputs; do not aggregate yet.

## Phase 33 — Representative expert-output cross-event reuse

- Bind the eight concrete representative expert outputs atomically to their
  canonical post-attention route IDs and binary64 routing weights in exact rank
  order, preserving expert 62 before expert 73.
- Require open-once consume-what-you-validated retention with exact expected,
  before, consumed, and after SHA equality; regular, non-symlink, read-only,
  single-link files; exact f32 `[6144]` geometry; and finite values.
- Freeze the future analytical aggregate-input surface as exact f32-to-f64
  promotion, binary64 weight multiplication, and Python `math.fsum`-equivalent
  binary64 accumulation while keeping the production serial-f32 runtime policy
  separate and unauthorized.
- Prohibit historical direct-DPREFIX outputs, checkpoint/expert fallback,
  aggregate/shared/FFN/S2 execution, and preserve ledger 175 with zero reads,
  opens, expert executions, and aggregate executions.
- Bank the exact Fable 5 ACCEPT review and Extra High builder composition
  closeout, retaining justified defense-in-depth notes for the future consumer.

Gate: the reuse authority is independently accepted for future aggregate
authorization preparation only; the aggregate remains not evaluated, no GO
token or execution authority exists, and the next action is to prepare a
separate checkpoint-free routed-aggregate authorization.

## Phase 34 — Representative routed-aggregate authorization

- Classify the canonical F017 routed-aggregate arithmetic as a proof/reference
  surface intentionally distinct from the production serial-f32 runtime:
  promote each retained f32 expert output element exactly to binary64, multiply
  by its banked binary64 routing weight, and call CPython 3.14.6 `math.fsum`
  exactly once on the eight products in canonical representative order.
- Require open-once consume-what-you-validated handling for all eight retained
  representative expert outputs and reject historical direct-DPREFIX outputs,
  protected representative identities in synthetic mode, and every
  checkpoint, shard, expert, shared, FFN, residual, or S2 capability.
- Rehearse only synthetic real-geometry inputs, bind a deterministic
  little-endian f64 `[6144]` output contract, and preserve zero real aggregate
  executions during authorization preparation.
- Enforce a future separately approved one-shot release with fixed
  event/release/attempt identities, exclusive durable attempt-start before
  aggregate computation, no retry/resume/second attempt, and future
  release-stage pinning of the concrete state and output destinations.
- Bank the exact Fable 5 review chain and Extra High builder composition
  closeout, treating all blocking and non-blocking-required findings as gates.

Gate: the authorization is independently accepted for a future separately
released checkpoint-free routed aggregate only; the real aggregate remains not
computed, `real_event_authorized=false`, ledger remains 175, and the next action
is to prepare an independently reviewed single-use routed-aggregate release.

## Phase 35 — Representative routed-aggregate single-use release

- Bind the accepted proof/reference authorization, arithmetic, executor,
  rehearsal, reuse authority, and Fable review to one fixed event, release, and
  attempt identity at ledger 175-to-175 with zero checkpoint, shard, and expert
  budgets.
- Resolve retained inputs, attempt state, output directory/file, future
  approval, and future token from fixed home/repository expressions with no
  caller-selected path surface.
- Consume the release at an exclusive durable attempt-start; durably count the
  one aggregate execution independently of output publication; prohibit
  concurrent invocation, retry, resume, and a second attempt; and bind a
  read-only interruption terminalizer.
- Publish exactly one finite little-endian f64 `[6144]` output through
  descriptor-relative exclusive temporary creation, file fsync, no-replace
  hard-link publication, parent fsync, temporary unlink, and descriptor-based
  read-back; require a matching `COMPLETE` terminal for output authority.
- Preserve the accepted one-real-aggregate budget: no extra real reproduction
  runs are introduced; two-fresh-process exact determinism remains established
  by the frozen synthetic rehearsal.
- Bank three exact Fable 5 reviews and Extra High builder composition
  acceptance while leaving the release `PREPARED_FOR_INDEPENDENT_APPROVAL` and
  without creating a GO token.

Gate: the release is independently accepted for separate approval and operator
preparation only; the real aggregate remains not computed, state/output/token
remain absent, and the next action is a separate independent release approval.

## Phase 36 — Banked aggregate and shared-expert authority reconciliation

- Record the successful routed-aggregate event and its immutable f64 `[6144]`
  proof/reference output while keeping production serial-f32 explicitly
  separate.
- Bind the accepted routed-aggregate cross-event reuse authority with open-once
  consume-what-you-validated semantics and zero recomputation capability.
- Record the independently accepted representative shared-expert
  authorization, release, approval, and retained-only real execution result:
  one finite f32 `[6144]` output, 2/2 exact fresh-process reproduction, and
  unchanged retained input and parameter identities.
- Preserve ledger 175 with zero new checkpoint reads, shard opens, downstream
  FFN completions, and S2 constructions throughout reconciliation.

Gate: the routed aggregate and shared-expert output are independently banked
authorities on their distinct accepted numerical surfaces; neither routed-plus-
shared composition nor S2 has been performed.

## Phase 37 — Shared-output reuse and representative FFN composition

- Bind the banked representative shared-expert output through a private
  manifest and open-once same-descriptor resolver requiring exact expected,
  before, consumed, and after identity, finite f32 `[6144]` geometry, and
  immutable single-link read-only storage.
- Freeze routed-plus-shared arithmetic as the canonical F017 proof/reference
  FFN surface: preserve the routed f64 `[6144]` contribution, exactly promote
  each shared f32 element to binary64 with no scalar multiplier, add in fixed
  routed-then-shared order under IEEE-754 round-to-nearest-ties-to-even, and
  serialize a finite little-endian f64 `[6144]` result.
- Keep the proof/reference surface distinct from the unauthorized production
  serial-f32 path and prohibit historical direct-DPREFIX inputs, checkpoint or
  compute fallbacks, BLAS, GPU, parallel reduction, and S2 construction.
- Bind S1 as `LAYER3_POST_ATTENTION_RESIDUAL`, hash-retained and reproducible
  checkpoint-free but not byte-retained; require a separate future S1
  materialization/retention authority before S2 preparation.
- Rehearse only synthetic real-geometry inputs in two fresh processes against
  an exact rational oracle; expose real-input preflight but no real-execution
  CLI; validate committed producer/consumer schemas and load-bearing
  mutations; bank exact Fable 5 review bytes.

Gate: shared-output reuse and the future one-shot checkpoint-free FFN
composition authorization are independently accepted; no real FFN output or S2
is computed, no GO token exists, and ledger remains 175.

## Phase 38 — Representative FFN-composition single-use release

- Bind the accepted proof/reference FFN authorization, routed/shared reuse
  authorities, exact retained inputs, arithmetic, executor, synthetic
  rehearsal, and accepted review to an immutable execution-code head and one
  future event/release/attempt identity.
- Pin ledger 175-to-175 with zero checkpoint, shard, expert, shared-expert,
  S1-materialization, and S2 budgets; count exactly one FFN composition at a
  durable FFN-start record before arithmetic regardless of its outcome.
- Consume the release through exclusive durable attempt creation; prohibit
  concurrency, retry, resume, and second attempt; reconcile partial-start,
  interrupted, published-but-incomplete, terminal-failure, and COMPLETE states
  without rerunning computation.
- Publish one finite little-endian f64 `[6144]` output and its private manifest
  by descriptor-relative exclusive temporary files, fsync, no-replace hard
  links, parent fsync, and descriptor read-back; bind both through a durable
  execution receipt and require a matching COMPLETE terminal for authority.
- Expose no S1 input/materialization or S2 construction path, create no GO
  token, and bank exact Fable 5 request/review artifacts under the bounded
  autonomous review policy.

Gate: the release is independently accepted for a separate operator execution
decision only; it remains `PREPARED_FOR_INDEPENDENT_APPROVAL`, no approval or GO
token is created, no real FFN is computed, and ledger remains 175.

## Phase 39 — Representative FFN-composition release v2 authority repair

- Preserve release v1 and its independent technical review byte-for-byte while
  classifying v1 as superseded only for execution authority because its exact
  approval-key census cannot carry the release-review SHA and does not enforce
  `reviewed_head`.
- Add append-only release/wrapper v2 machinery with an acyclic authority chain:
  committed release bytes, committed independent review target, immutable
  Fable-5 review bytes, later independent approval binding the exact review SHA
  and reviewed head, and a later machine-local token binding the approval SHA.
- Enforcement-check every approval authority field, including review bytes,
  reviewer identity/model, reviewed Git commit, release bytes at that commit,
  authorization/arithmetic/code identities, accounting, and stop boundary.
- Preserve the accepted proof/reference FFN numerical surface and all v1
  durability, immutable-input, output-publication, terminalization, ledger,
  checkpoint, expert, S1, and S2 boundaries without running the real FFN.

Gate: release v2 is independently accepted and ready for a separate approval
phase; no approval or GO token exists, no real FFN is computed, and ledger
remains 175.

## Phase 40 — FFN release v2 approval and machine-local readiness

- Materialize the exact 28-field approval required by the v2 approval contract,
  binding the accepted release/review/code/authorization/arithmetic chain while
  remaining non-executable and distinct from the later machine-local token.
- Commit and independently review the approval bytes with Claude Fable 5 before
  any machine-local execution authority exists.
- Verify the retained routed/shared files and manifests, pinned runtime, fixed
  v2 state/output destinations, zero prior state, and preflight-only wrapper
  disposition without performing FFN arithmetic.
- Only after every gate passes, create one mode-0400, regular, non-symlink,
  single-link GO token whose exact eight fields bind the committed approval SHA;
  validate it without entering the wrapper execution path and stop unconsumed.

Gate: one valid machine-local v2 token exists unconsumed; approval/review bytes
are committed and accepted; ledger remains 175; checkpoint, attempt, FFN, S1,
and S2 counters remain zero.

## Phase 41 — Representative FFN execution banking and cross-event reuse

- Reconcile the consumed release-v2 attempt from its durable attempt-start,
  FFN-start, receipt, terminal, retained output, and private manifest, then bank
  an append-only public execution packet that distinguishes release authority,
  GO authority, release consumption, arithmetic execution, and output authority.
- Bind the retained proof/reference FFN output to a consumer-scoped reuse
  authorization and open-once resolver enforcing exact manifest, geometry,
  finiteness, and EXPECTED = BEFORE = CONSUMED = AFTER identity without an FFN,
  checkpoint, S1, or S2 capability.
- Adjudicate post-event reproduction explicitly against the accepted routed
  aggregate reuse precedent: the completed event did not authorize a second
  composition, so exact byte retention plus matching COMPLETE terminal,
  receipt, manifest, arithmetic, and input identities are reviewed as the
  reuse basis rather than retroactively expanding execution authority.
- Validate all authority, surface-isolation, retained-file, and downstream
  boundary mutations, then bank an exact Claude Fable 5 review of committed
  bytes and close out the bounded loop only on ACCEPT.

Gate: the representative proof/reference FFN output is independently accepted
for checkpoint-free cross-event reuse; release v2 remains consumed and is never
rerun; ledger remains 175; no new FFN, S1, or S2 work occurs.

## Phase 42 — Representative S1 materialization preparation

- Bind the canonical `LAYER3_POST_ATTENTION_RESIDUAL` identity to the accepted
  representative M1-F0 real-execution packet, stage vocabulary, retained-only
  reproduction contract, exact producer, canonical DPREFIX-EXACT-1 S0, and
  nine immutable retained attention payload authorities.
- Add an append-only extraction adapter that uses the same frozen
  `compose_oracle` numerical implementation as the accepted producer and emits
  only canonical little-endian f32 `[6144]` S1 bytes; provide no checkpoint,
  shard, router, expert, FFN, S1-consumer, or S2 interface.
- Gate one future materialization with exclusive durable attempt creation,
  durable materialization-start before reconstruction, no retry/resume/second
  attempt, descriptor-relative expected/produced/read-back verification, and
  durable no-replace output, private-manifest, receipt, and terminal banking.
- Rehearse only synthetic real-geometry inputs and release mechanics, validate
  stale/wrong authorities and arithmetic/boundary mutations, and bank exact
  Claude Fable 5 review bytes before describing the release as accepted.

Gate: S1 materialization machinery is independently accepted for a later
approval/execution decision; no real S1 bytes are materialized, no GO token is
created, ledger remains 175, and checkpoint, attention-event, FFN, and S2
counters remain zero.

## Phase 43 — S1 release-v2 approval and machine-local readiness

- Materialize the exact 18-field approval required and enforcement-checked by
  wrapper v2, binding the accepted release-v2 bytes and the accepted immutable
  Claude Fable 5 release-review head, path, SHA, model, and verdict while
  remaining non-executable and separate from the machine-local token.
- Commit and independently review the approval bytes and their transitive
  release -> review -> approval -> token authority chain before creating any
  local execution authority.
- Verify the canonical S0, its private manifest, all nine retained attention
  payloads, pinned runtime, fixed release-v2 state/output destinations, and
  zero prior materialization state without executing reconstruction arithmetic.
- Only after every gate passes, create one exact eight-field, mode-0400,
  regular, non-symlink, single-link GO token bound to the committed approval;
  validate it through the read-only authority gate and stop unconsumed.

Gate: one valid machine-local S1 release-v2 token exists unconsumed;
approval/review bytes are committed and accepted; ledger remains 175; and
checkpoint, attention-event, attempt, materialization, FFN, and S2 counters
remain zero.

## Phase 44 — Representative S1 execution banking and cross-event reuse

- Reconcile the consumed release-v2 event from its durable attempt-start,
  materialization-start, receipt, COMPLETE terminal, retained S1 output, and
  private manifest, then bank an append-only execution packet distinguishing
  historical attention authority, checkpoint-free reconstruction, release
  consumption, materialization accounting, and retained output authority.
- Bind the exact `LAYER3_POST_ATTENTION_RESIDUAL` bytes to a consumer-scoped
  reuse authorization and open-once resolver enforcing immutable manifest,
  geometry, finiteness, and EXPECTED = BEFORE = CONSUMED = AFTER identity on
  the same descriptor without reconstruction or downstream computation.
- Adjudicate reproduction against accepted F017 retained-output precedent: the
  precommitted expected S1 SHA, matching durable COMPLETE chain, immutable
  source identities, and accepted 10/10 retained-only attention reproduction
  lineage are the reuse basis; any new reproduction requires separate
  authority and is not executed here.
- Validate authority, retained-file, lineage, accounting, and downstream
  boundary mutations, then bank exact Claude Fable 5 review bytes and close
  only on ACCEPT.

Gate: the canonical representative S1 artifact is independently accepted for
checkpoint-free cross-event reuse; release v2 remains consumed and is never
rerun; ledger remains 175; no attention, S1, FFN, or S2 work occurs.

## Phase 45 — Representative S2 authorization and single-use release preparation

- Bind the independently accepted S1 and proof/reference FFN reuse authorities
  to a frozen scalar S2 arithmetic contract: exact binary32-to-binary64 S1
  widening, one ordered binary64 addition, and one ties-to-even binary64-to-
  binary32 cast per coordinate.
- Preserve the resulting surface as proof/reference-derived and explicitly not
  proven equivalent to production serial-f32 despite its final f32 storage.
- Gate one future checkpoint-free S2 construction with immutable open-once
  operands, exclusive durable attempt and S2 starts, no retry/resume/second
  attempt, descriptor-relative durable no-replace publication, manifest,
  receipt, terminalization, and truthful pre-arithmetic accounting.
- Rehearse only synthetic real-geometry operands, reject arithmetic, lineage,
  file-policy, fallback, race, and downstream-boundary mutations, then bank an
  exact Claude Fable 5 review of committed bytes before approval readiness.

Gate: arithmetic, authorization, and release are independently accepted for a
later separate approval and operator decision; no approval or GO token exists,
neither real operand is consumed, no S2 is constructed, and ledger remains 175
with zero checkpoint reads or shard opens.

## Phase 46 — S2 independent approval and machine-local readiness

- Bank the exact wrapper-enforced 28-field independent approval binding the
  release, arithmetic, authorization, execution-code head, accepted reviewed
  head, release-review bytes, and reviewer identity without itself executing or
  acting as a token.
- Independently review the committed approval and its acyclic release -> review
  -> approval -> machine-local token chain before any local capability exists.
- Verify the immutable S1 and FFN operands through their fixed manifests and
  open-once descriptor policy, the pinned runtime, empty fixed S2 execution
  state, and ledger 175 without entering the S2 arithmetic path.
- Only after every gate passes, create one exact eight-field mode-0400,
  single-link machine-local GO token, validate it through the non-executing
  authority gate, and stop unconsumed.

Gate: approval and approval-review bytes are committed and accepted; exactly
one valid S2 token exists unconsumed; attempt/S2 starts remain absent; neither
operand has been consumed by S2; ledger remains 175 with zero checkpoint reads.

## Phase 47 — S2 consumer/release v2 manifest compatibility repair

- Preserve release v1 and all historical review/approval bytes while marking
  only its execution authority superseded after the real readiness gate proved
  it cannot parse the exact retained S1 producer manifest.
- Add a schema-specific v2 consumer that validates the accepted singular S1
  `artifact` object and `LAYER3_POST_ATTENTION_RESIDUAL` producer vocabulary
  directly, derives any consumer alias only afterward, and keeps the distinct
  accepted FFN `artifacts` schema fail-closed.
- Reuse the frozen v1 scalar S2 arithmetic object unchanged and preserve all
  exclusive-attempt, durable-start, publication, terminalization, accounting,
  checkpoint, S1, FFN, and downstream boundaries under new v2 release paths.
- Require both synthetic real-geometry rehearsal and exact non-consuming real
  retained preflight to resolve `PRODUCTION_BINDINGS_RESOLVED` before committed
  Claude Fable 5 review; create no approval or GO token in this phase.

Gate: release v2 is independently accepted for a later separate approval and
readiness decision; exact S1/FFN retained bindings resolve without arithmetic,
attempt state, or execution consumption; ledger remains 175 with zero reads.
