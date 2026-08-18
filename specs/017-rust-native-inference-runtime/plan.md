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
