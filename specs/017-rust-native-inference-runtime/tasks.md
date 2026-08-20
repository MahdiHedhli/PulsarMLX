# Tasks: 017-rust-native-inference-runtime

## Pre-implementation

- [x] T017-01 Reconcile current branch/main hash at `a948b68d9868a34b0cc9b00aacaa4ad2330b0f55`.
- [x] T017-02 Confirm required Feature 016 authoritative files are present.
- [x] T017-03 Create feature directory and baseline spec artifacts.
- [x] T017-04 Authoritative fact ingestion checklist completed in spec.

## Phase 1 — Portable fixture contract and parser

- [x] T017-10 Define `portable-fixture-contract-v1` manifest schema:
  - source commit + checkpoint identity + tensor identity + shard + layer/position + quant + dtype + offsets + hashes.
- [x] T017-11 Add schema validators and fail-closed behavior for missing identities or hash mismatches.
- [x] T017-12 Add manifest fixture examples for public-safe synthetic artifacts and one local-only real manifest pointer.
- [x] T017-13 Add tests for malformed/unsigned/duplicate manifests.

## Phase 2 — Inventory-driven slot sizing and residency boundaries

- [x] T017-20 Ingest `f016-gguf-trunk-inventory-0001.json` and assert:
  - `tensor_count == 1353`
  - `excluded_expert_matrix_count == 456`
  - `total_compressed_bytes == 13_474_784_256`
  - `total_decoded_f32_bytes == 66_223_309_824`
- [x] T017-21 Assert trunk residency options A–F are represented by concrete names and budgets from authoritative table.
- [x] T017-22 Add allocator/slot-size generation from observed tensor-size distribution (no invented sizes).
- [x] T017-23 Add safe rejections for decoded-all-trunk and unsafe hybrid options on M2 Max safety gates.
- [x] T017-24 Add unit tests for compressed/decoded/hybrid residency state transitions.

## Phase 3 — Native slab allocator

- [x] T017-30 Implement page-aligned allocator contract with stable slot IDs and bounded max in-use limit.
- [x] T017-31 Add deterministic reuse policy and reuse counters.
- [x] T017-32 Add zeroing policy documentation + tests.
- [x] T017-33 Add telemetry for requested bytes, allocated bytes, alignment, slot-count, reuse-count, peak logical residency.

## Phase 4 — Positional I/O and read-path contract

- [x] T017-30 Implement page-aligned allocator contract with stable slot IDs and bounded max in-use limit.
- [x] T017-31 Add deterministic reuse policy and reuse counters.
- [x] T017-32 Add zeroing policy documentation + tests.
- [x] T017-33 Add telemetry for requested bytes, allocated bytes, alignment, slot-count, reuse-count, peak logical residency.
- [x] T017-40 Implement sync pread-like reads with shard identity and offset overflow guard.
- [x] T017-41 Add read exactness contract: short-read != requested bytes is an error.
- [x] T017-42 Add whole-matrix reader API and explicit tensor-size-guided chunking.
- [x] T017-43 Record read request count plus requested/actual bytes separately.
- [x] T017-44 Add synthetic and local fixture tests comparing bulk path to row reads.

## Phase 5 — Telemetry attribution

- [x] T017-50 Add separate timers/counters for:
  - storage/read
  - decode
  - buffer/materialization
  - backend build/import
  - compute
- [x] T017-51 Ensure layer-level aggregates and fixture events can attribute each bucket independently.
- [x] T017-52 Add fail-closed behavior if any bucket overflows uninitialized telemetry states.

## Phase 6 — Decoder and numerical boundary

- [x] T017-60 Qualify at least one required format lane with strict criteria.
- [x] T017-61 Add malformed and truncated input rejection coverage.
- [x] T017-62 Add bit-level comparison or documented epsilon contract where exactness is not yet possible.
- [x] T017-63 Record throughput and allocator impact for qualified formats.

## Phase 7 — Apple bridge spike and native registration

- [x] T017-70 Build native bridge registration spike with deterministic buffer ownership and teardown ordering.
- [x] T017-71 Demonstrate stable address behavior across command submission boundaries.
- [x] T017-72 Add no-copy or explicit `newBufferWithBytesNoCopy` qualification matrix.
- [x] T017-73 Add fail-closed teardown and cancellation path tests.

## Phase 8 — Runtime skeleton and mode-aware validation

- [x] T017-80 Add reusable runtime contracts and GLM plugin boundary stubs.
- [x] T017-81 Add `teacher_forced_validation` and `golden_strict` result classes.
- [x] T017-82 Add mismatch classification and deterministic stopping policy.

## Phase 9 — Checkpoint-free fixture ladder

- [x] T017-90 Implement boundaries 1→11 in strict order and stop on mismatch.
- [x] T017-91 Validate boundary 2 and 3 on M2 Max using hash-bound local fixtures.
- [x] T017-92 Capture residual telemetry and memory admission outcomes at every boundary.

## M2 Max safety gate (mandatory)

- [x] T017-99 Reject dec-trunk residency plans requiring swap-risky memory profiles unless allocator study is complete and green.

## Release-prep

- [x] T018-00 Send milestone NTFY update after authoritative input incorporation and milestone gates.

## Canonical real-checkpoint runner extension

- [x] T017-100 Reconcile reviewed F017 source and preserve immutable M1 and existing dirty worktrees.
- [x] T017-101 Create and push dedicated `feat/017-real-checkpoint-runner` from reviewed `a4b08e1`.
- [x] T017-102 Commit a source-backed real-checkpoint runner gap analysis.
- [x] T017-103 Freeze the canonical runner CLI, exit-class, evidence, and mode contract.
- [x] T017-104 Define versioned runner evidence schema and duplicate-key rule.
- [x] T017-110 Add dedicated `f017-glm52-runner` crate and strict CLI parser.
- [x] T017-111 Add atomic evidence/progress writer and deterministic validator.
- [x] T017-112 Add immutable fake multi-shard checkpoint manifest and identity parser.
- [x] T017-113 Compose GGUF catalog and positional tensor store with exact range/hash evidence.
- [x] T017-114 Add runner dry-run and checkpoint-identity-only vertical slices.
- [x] T017-120 Bind adapter-preflight-only to the production F017 adapter with zero-state/reconciliation evidence.
- [x] T017-121 Add the smallest typed MLX compute operation required by the real-shaped projection gate.
- [x] T017-122 Pass R5 production-adapter projection against the independent oracle.
- [x] T017-130 Add fully validated 79-layer `glm-dsa` tensor map.
- [x] T017-131A Freeze the original R7 mismatch, fixture identities, and exact failure classification without re-execution.
- [x] T017-131B Add an auditable strict-column-order f32 qualification matvec.
- [x] T017-131C Prove exact gate/up/down and complete-expert parity through the qualification scaffold.
- [x] T017-131D Attribute the original production MLX mismatch at every retained intermediate.
- [x] T017-131E Freeze an independently derived production expert Tier-B contract before additional production expert fixtures.
- [x] T017-131F Qualify the frozen Tier-B contract with independent stress fixtures.
- [x] T017-131G Requalify production R7 under the frozen Tier-B contract with fail-closed mode evidence.
- [x] T017-131I Make exact-scaffold and production-MLX numerical modes explicit in runner CLI, dispatch, and evidence.
- [x] T017-131H Admit and run only checkpoint-free R8 if every R7 gate passes.
- [x] T017-131 Compose router and complete expert runtime boundaries R6-R8.
- [x] T017-132 Compose MLA/DSA and complete layer runtime boundaries R9-R10.
- [x] T017-132R Add fail-closed greedy-applicability vocabulary and
  mechanically reconcile R7-R10 without changing numerical payloads.
- [x] T017-132V Preserve immutable R9/R10 v1 contracts, publish reviewed v2
  semantic tightening, record the R7 amendment, and rebind evidence without
  numerical reruns.
- [x] T017-133 Compose final norm/logits/top-k runtime boundary R11.
- [x] T017-134 Run a tiny synthetic multi-layer model end to end through the actual runner binary at R12.
- [x] T017-140 Add local-only real boundary fixture manifest/validator for R13.
  - [x] T017-140A Add the checkpoint-free manifest schema and fake-shard validator.
  - [x] T017-140I Bind the reviewed immutable six-shard checkpoint, catalog,
    tensor-map, and privacy identities without capturing tensor payload bytes.
  - [x] T017-140B Generate and validate a separately authorized real local boundary fixture.
- [ ] T017-141 Add literal canonical P1 command only after M1-A through M1-G review gates pass.
- [x] T017-150 Add checkpoint-free CI for CLI/schema/store/tensor-map/runner/cancellation/privacy gates.
- [x] T017-151 Require native Apple CI to execute adapter and projection tests without skips.
- [x] T017-160 Obtain internal implementation review of the runner composition.
- [x] T017-161 Obtain independent adversarial review of P1 meaningfulness and fail-closed behavior.
- [x] T017-162 Execute and bank exactly one accepted M1-A production adapter preflight.
- [x] T017-163 Execute M1-B only after separate review and explicit authorization.
  - [x] T017-163A Repair the stale runtime pin, provision the reviewed local-only
    production checkpoint manifest, and prepare a fresh authorization packet.
  - [x] T017-163B Execute exactly one separately authorized M1-B identity run.
- [x] T017-164 Capture all ten M1-D production outputs before buffer reuse and
  require finalized-oracle structural ordering before PASS.
- [x] T017-165 Separate M1-D activation/finalization/reference provenance,
  bind the handoff and execution contracts immutably, and reject stale or
  ambiguous authorization packets before real payload access.
- [x] T017-166 Execute the exactly-once authorized M1-D attempt, bank the
  fail-closed `m1d_contract_read` infrastructure rejection, and stop without
  retry or M1-E promotion.
- [x] T017-167 Reproduce the relocated-package `m1d_contract_read` failure,
  separate typed repository/package roots, hash-bind every artifact, qualify
  arbitrary-package-location/cwd independence through the canonical native
  projection loop, preserve attempt 1, and publish a distinct attempt-2
  authorization.
- [x] T017-168 Execute the separately authorized M1-D attempt 2, preserve the
  fail-closed `m1d_activation_fixture_read` pre-candidate rejection, and stop
  without checkpoint access, candidate execution, retry, or M1-E promotion.
- [x] T017-169 Replace manual M1-D command assembly with one hash-bound typed
  execution config, add non-consuming preflight and wrong-path/override
  regressions, and prepare a distinct unconsumed attempt-3 authorization.
- [x] T017-170 Publish final runner sprint report and exact M1-A through M1-H blockers.
- [x] T017-171 Execute exactly one separately authorized M1-D attempt 3 from
  the immutable execution config, bank its accepted real-projection evidence,
  and stop before M1-E execution.
- [x] T017-172 Prepare, freeze, checkpoint-free qualify, and independently
  review the complete layer-3/expert-15 M1-E admission package.
- [x] T017-173 Execute exactly one separately authorized M1-E real-expert
  attempt from the immutable execution config, then stop before M1-F.
- [x] T017-174 Reproduce and independently resolve the M1-E attempt-1
  `m1e_down_decoded` IQ3_XXS identity failure, publish the exact v2 decoder
  contract and regression fixture, preserve dependent historical evidence,
  and prepare a separately authorized M1-E attempt 2 without candidate
  compute.
- [x] T017-175 Separate embedded compiled-runtime, execution-tooling, and
  authorization-checkout identities; fail closed on non-ancestry, dirty
  state, stale binaries, or execution-relevant descendant drift; rebuild the
  still-unconsumed M1-E attempt-2 config under trusted-repository identity v2.
- [x] T017-176 Execute exactly one identity-v2-authorized M1-E attempt 2,
  preserve the fail-closed pre-checkpoint execution-config schema rejection,
  bank public-safe evidence, and stop without retry or M1-F preparation.
- [x] T017-177 Make the independent M1-E preparer consume execution-config
  schema 3.0.0 natively, reject downgrade/confusion inputs before payload
  access, preserve decoder/numerical identities, and prepare an unconsumed
  attempt-3 authorization after internal and adversarial GO reviews.
- [x] T017-178 Execute the M1-E closed loop: preserve the unconsumed attempt-3
  native-loader preflight blocker, bind the reviewed MLX loader environment,
  rebuild authorization, execute at most attempts 3-5, and bank acceptance or
  the terminal blocker without entering M1-F.
- [ ] T017-179 Prepare and checkpoint-free qualify the complete layer-3 M1-F
  admission package. **Blocked pending a representative v3/H=2 fixture:** the
  first accepted oracle route remains valid adversarial stress evidence and is
  semantically stable under v3, but its membership factor
  `1.2497550469932908` is below H=2. Both the original frozen random-normal
  ladder and a separately frozen correlated synthetic family are now
  checkpoint-free planning rejects; the next real-access decision is the
  separately reviewed dense-prefix layer-3 entry-state boundary. Expert-specific
  inventory and real Q6_K qualification remain paused.
- [x] T017-180 Prepare and checkpoint-free qualify the bounded layer-3 M1-F0
  oracle-only attention/router discovery package, freeze its 12-tensor
  expert-free access budget and exact route-selection contract, pass internal
  review, and stop with the adversarial packet pending external review.
- [x] T017-181 Close the M1-F0 adversarial tooling-provenance and real-byte
  Q5_K decoder findings, prove pinned input regeneration, strengthen route
  and first-real-quantization admission, rebuild the immutable config, pass
  internal review, and stop for a narrow external adversarial delta review.
- [x] T017-182 Execute the bounded M1-F0 closed loop, preserve rejected attempt
  1, remediate its evidence-wrapper failure, accept attempt 2 with exactly 12
  attention/router payloads and ten deterministic oracle repeats, bank the
  real route, and stop with M1-F prepared but unauthorized.
- [x] T017-183 Recover the accepted M1-F0 analytical values without changing
  route semantics, retain full score/ranking objects, and prove the first
  fixture is unsuitable for production route freezing under the pre-frozen
  stability contract.
- [x] T017-184 Reconstruct the complete real-payload ledger, precommit the
  eight-fixture checkpoint-free input family, extend analytical retention, and
  bank a one-million-sample planning estimate showing the proposed family is
  underpowered without performing new checkpoint access.
- [x] T017-185 Research and freeze a checkpoint-free pairwise route-stability
  v2 candidate, repair estimator/ladder and analytical-retention bindings,
  stress independent implementations without under-bounds, and fail closed
  because accepted M1-F0 evidence omitted the RMSNorm/router-row antecedents
  required to instantiate v2 without new real checkpoint access.
- [x] T017-186 Finalize route-stability v2 with explicit score-addition rounding
  and normative ordered-top-8 stability, qualify the final mathematics through
  independent implementations and directed/randomized stress, and prepare a
  non-consuming, identity-gated 12-payload antecedent-recovery package without
  checkpoint access or route reclassification.
- [x] T017-187 Execute exactly one authorized v2 antecedent recovery, reproduce
  the accepted M1-F0 identities with the frozen 12-payload boundary, retain the
  complete pairwise surface and immutable private antecedents, append the
  45-to-57 real-payload ledger event, and stop for independent evidence review.
- [x] T017-188 Close the checkpoint-free v2 recovery summary-integrity findings:
  derive global membership and ordered extrema from the complete retained
  detail surface, separate route-set from route-order status, reject summary
  mutations fail-closed, preserve immutable raw evidence, and audit adjacent
  F017 summarizers for historical false-PASS risk.
- [x] T017-189 Research and freeze the checkpoint-free M1-F routing-contract v3:
  trace production/reference rank semantics, make expert ID and weight atomic,
  qualify ID-keyed routing weights and f32 accumulation-order effects, preserve
  v1/v2 history, retrospectively falsify fixture 1 from retained antecedents,
  characterize representative/stress policy and the dense-prefix fallback, and
  stop for independent adversarial review with the real-payload ledger at 57.
- [x] T017-190 Adopt the independently reviewed routing-contract v3 semantics,
  land clarification-only denominator and routed-accumulation scope regressions,
  reject two underpowered synthetic representative families through pre-frozen
  million-sample H=2 planning, complete route-independent M1-F and downstream
  M1-G/P1 scaffolding, derive the exact metadata-only dense-prefix boundary,
  and stop before any new real access with the ledger at 57.
- [x] T017-191 Prepare the checkpoint-free M1-F(-1) real dense-prefix boundary:
  reconcile reviewed provenance, freeze the P-MIN/token-9703 input, independently
  derive the exact 40-tensor inventory and budgets, freeze mixed-policy decoded
  reuse, repair and regress the Q6_K decoder group ordering, prepare Q4_K/Q6_K
  real-byte gates, bound conservative double-residency admission, qualify the
  independent synthetic/oracle/config/evidence/retention scaffolds, and stop for
  adversarial review with zero real access and the ledger unchanged at 57.
- [x] T017-192 Complete the checkpoint-free dense-prefix/decoded-reuse/Colibrì
  comparative audit: freeze the seven-use-case separate-package reuse policy,
  pin and hash-audit Colibrì without copying source or adopting a dependency,
  land independent near-tie/dispatch/lifetime regressions, preserve the exact
  40-tensor dense-prefix and Q4_K/Q6_K packages, and stop for adversarial review
  with zero real access and the ledger unchanged at 57.
- [x] T017-193 Close the checkpoint-free Q6_K decoder-lineage defect with a
  minimized auditable fixture, pinned upstream provenance, three independent
  exact-byte implementations, historical-impact evidence and regressions;
  revalidate the staged Q6_K package, prepare the fail-closed one-payload Q4_K
  authorization handoff, preserve dense-prefix numerical semantics, and stop
  before real access with the ledger unchanged at 57.
- [x] T017-194 Reconcile the Q4K-REAL-1 execution instruction fail-closed,
  bank a checkpoint-free NOT_EXECUTED result after the reviewed attempt ledger
  remained empty and both control artifacts remained unauthorized, regress that
  operator text cannot bypass machine authorization, preserve the unconsumed
  attempt, and leave the real-payload ledger unchanged at 57.
- [x] T017-195 Amend only the Q4K-REAL-1 authorization state with versioned,
  hash-bound execution controls and one append-only authorized/unconsumed attempt
  record; preserve the prior NOT_EXECUTED evidence and all numerical semantics,
  prove the canonical preflight READY plus ten fail-closed mutations, and stop
  for narrow adversarial review with zero real access and ledger 57.
- [x] T017-196 Execute the single authorized Q4K-REAL-1 payload event, retain the
  first-observation packed identity, require exact canonical f32 equality across
  three independent decoders, bank fail-closed evidence and append-only attempt
  plus real-payload ledger transitions, and stop before Q6_K with ledger 58.
- [x] T017-197 Reconcile the committed Q4K-REAL-1 terminal evidence, attempt
  ledger, and real-payload ledger through a fail-closed triad validator; bank
  real-event packet and CI provenance rules; prepare Q6K-REAL-1 born authorized
  and unconsumed with direct corrected-decoder binding, one-payload isolation,
  and zero checkpoint access; stop for independent adversarial review at ledger 58.
- [x] T017-198 Execute exactly one independently released Q6K-REAL-1 payload,
  retain the first-observation packed identity, require exact canonical f32
  equality across the corrected grouped Python, independent index-driven
  Python, and independent Rust decoders, close the real-byte side of
  F017-Q6K-LANE-ORDER-001, reconcile execution-start/attempt/payload/terminal
  evidence, and stop before dense-prefix execution with ledger 59.
- [x] T017-199 Audit the DPREFIX-REAL-1 authorization package checkpoint-free,
  independently regenerate its 40-tensor inventory and exact 38-entry proposed
  read partition, and fail closed without creating an execution config,
  authorization binding, or attempt when the accepted Q4_K/Q6_K evidence
  exposes only hash/byte-count descriptors rather than resolvable immutable
  private-package artifacts; leave the real-payload ledger at 59.
- [x] T017-200 Supersede only the blocked 38-read reuse strategy with the
  independently adjudicated 40-fresh-read preparation-contract v2; make the
  accepted Q4_K/Q6_K observations hard identity-confirmation gates, enforce
  retention at creation, authorize DPREFIX-REAL-1 born unconsumed with exact
  partial-read ledger accounting and no downstream chain, and stop for
  adversarial review without checkpoint access at ledger 59.
- [x] T017-201 Run the independently released DPREFIX-REAL-1 preflight and host
  admission checkpoint-free, detect that the reviewed package binds neither a
  candidate executable/source surface nor an instantiated independent-oracle
  package, bank a non-consuming INFRASTRUCTURE result, and stop with zero
  payload reads and ledger 59 rather than create an unreviewed execution path.
- [x] T017-202 Preserve the non-consuming DPREFIX-REAL-1 infrastructure event,
  bind a narrow arm64 native-MLX candidate by complete source surface and exact
  executable identity, instantiate the independent NumPy oracle package,
  qualify their actual-binary ten-repeat/dispatch/lifecycle/retention behavior
  checkpoint-free, publish config/authorization successors for the same
  unconsumed attempt, and stop for adversarial review with ledger 59.
- [x] T017-203 Reconcile the released DPREFIX-REAL-1 numerical evidence surface
  checkpoint-free, prove that the exact reviewed candidate and instantiated
  oracle retain only intermediate hashes while the frozen real Tier-B contract
  requires per-layer and attention error metrics, bank a second non-consuming
  infrastructure result, and stop before payload access with ledger 59.
- [x] T017-204 Close the DPREFIX-REAL-1 Tier-B instantiability blocker
  checkpoint-free by deriving the exact eight-surface producer map from the
  frozen contract, adding numerically neutral paired-value candidate/oracle
  instrumentation, freezing an independent deterministic metric engine and
  strict evidence schema, qualifying the actual successor binary for ten
  production-width repeats, and publishing config/authorization successors for
  the same unconsumed attempt with zero checkpoint access and ledger 59.
- [x] T017-205 Run the independently released DPREFIX-REAL-1 preflight
  checkpoint-free, preserve the exact candidate/oracle/numerical successors,
  detect that no reviewed real-event launcher or material-package builder binds
  the 40 positional reads to oracle-first execution and terminal evidence,
  bank `NOT_EXECUTED / EXECUTION_SURFACE_DRIFT` without resolving a checkpoint
  path, and preserve the same unconsumed attempt with ledger 59.
- [x] T017-206 Bind the checkpoint-free DPREFIX-REAL-1 real-event orchestrator,
  exact 40-read bounded reader, durable partial-ledger journal, event-local
  material builder, fixed decoder dispatch, oracle-first/candidate/metric
  coordination, retention and terminal evidence banking; rehearse failure and
  attack paths and publish successor authorization without consuming the
  attempt or changing ledger 59.
- [x] T017-207 Run the independently released DPREFIX-REAL-1 identity and host
  admission preflight, preserve the exact reviewed execution surfaces, stop
  before consumption when the bound repository-private checkpoint object is
  absent, and bank `NOT_EXECUTED / HOST_ADMISSION` with zero payload reads and
  the real-payload ledger unchanged at 59.
- [x] T017-208 Restore the reviewed checkpoint as the same regular-file objects
  at the bound private mount, execute the still-unconsumed DPREFIX-REAL-1 once,
  record all 40 authorized reads and the 59-to-99 ledger transition, preserve
  exact Q4_K/Q6_K identity confirmations, bank the terminal `NATIVE_RUNTIME /
  NATIVE_CANDIDATE_MATVEC_SHAPE` rejection, and stop without retry, retention,
  representative M1-F0, or downstream execution.
- [x] T017-209 Preserve DPREFIX-REAL-1 as terminal and checkpoint-free close its
  native `attn_k_b` real-shape orientation defect; freeze all 40 real geometry
  and packed identities, persist oracle primary products before candidate
  launch, retain all packed payloads at creation, harden native-failure banking
  and cleanup, qualify the exact-shape successor for ten repeats, and prepare
  the fresh authorized/unconsumed DPREFIX-REAL-2 package at ledger 99.
- [x] T017-210 Execute the independently released DPREFIX-REAL-2 exactly once,
  identity-confirm and durably retain all 40 packed payloads, persist oracle
  Class-A products before the corrected candidate, complete ten deterministic
  repeats and all eight Tier-B comparisons, then fail closed as
  `EVIDENCE_VALIDATION` because the bound success path omitted required
  lifecycle and host-copy accounting; reconcile the consumed terminal attempt
  and real-payload ledger at 139 with no retry or M1-F0 continuation.
- [x] T017-211 Prepare the fresh checkpoint-free DPREFIX-REAL-3 retained-package
  replay: preserve REAL-2 as terminal, repair actual host-copy and success-path
  lifecycle emission in a successor candidate, independently verify and decode
  all 40 immutable packed artifacts, structurally remove checkpoint and payload-
  ledger authority, rehearse the exact-real-geometry 10-repeat success and
  failure paths through one terminal finalizer, bind the zero-read 139-to-139
  config/authorization/attempt package, and stop for adversarial review.
- [x] T017-212 Execute the independently released DPREFIX-REAL-3 replay exactly
  once from the immutable packed package with zero checkpoint authority, bank
  all 40 decoded gates, ten repeats, eight Tier-B rows, concrete success-path
  accounting, and retained Class-A states, then fail closed if the precommitted
  REAL-2 oracle-state identity is not reproduced; reconcile the replay attempt
  while leaving the real-payload ledger byte-consistent at 139 and stop without
  retry or representative M1-F0.
- [x] T017-213 Characterize the REAL-2/REAL-3 BLAS cross-process delta from
  byte-identical retained inputs, reproduce both historical realizations under
  their CPython/NumPy BLAS backends, produce DPREFIX-EXACT-1 bit-identically
  through independent fixed-order C and Rust scaffolds, freeze identity-gate
  contract v2, and fail closed on route insensitivity because the committed v2
  descriptors do not provide the retained layer-3 attention/router bytes or a
  reviewed propagation bound needed for all 1,984 membership inequalities;
  preserve zero checkpoint access and the real-payload ledger at 139.
- [x] T017-214 Freeze routing-contract v3.1 before real ambiguity evaluation:
  bind actual GLM-5.2 routing semantics, implement directed-outward state-box
  propagation through FFN RMSNorm, all router rows, sigmoid/correction-bias
  scores, strict membership differences, safety factors, and ID-keyed selected
  weights; validate only synthetic/adversarial/property fixtures while keeping
  private antecedent values unopened, checkpoint access zero, and ledger 139.
- [x] T017-215 Prepare the separately reviewable canonical expert-output
  recovery authorization: derive the exact 24 gate/up/down expert slices for
  the invariant selected set from committed catalog metadata, freeze one shard
  open and 90,439,680 packed bytes with durable 139-to-163 partial accounting,
  bind DPREFIX-EXACT-1 f32 RMSNorm/SwiGLU/down-projection semantics, immutable
  packed and eight-output retention, deterministic retained-material replay,
  and fail-closed validators while performing zero checkpoint reads, zero shard
  opens, no expert computation, and no aggregate evaluation.
- [x] T017-216 Stop the conditionally released canonical expert-output event
  before checkpoint access because dual-implementation decode agreement was not
  load-bearing; amend the authorization to require same-retained-byte exact f32
  agreement between independent accepted IQ2_XXS/IQ3_XXS decoders for all 24
  payloads, reverify the complete catalog-slice inventory, and return the
  checkpoint-free amendment for renewed adversarial review at ledger 139.
- [x] T017-217 Bind the canonical expert-output recovery execution substrate:
  implement a frozen-inventory one-shot executor, durable execution-start and
  attempt identities, per-read consumption receipts/journal/ledger updates,
  retain-before-decode packed artifacts, same-retained-byte dual decoding,
  one-shard-open and no-retry guards, terminal banking and interrupted-attempt
  terminalization; validate the complete crash/failure matrix with compact
  synthetic fixtures only while keeping checkpoint reads and shard opens zero
  and the real-payload ledger unchanged at 139.
- [x] T017-218 Bind the complete canonical expert-output production recovery
  surface: isolate the sole shard-open/pread capability, connect independent
  Rust and specification-transcription IQ2_XXS/IQ3_XXS decoders, resolve the
  immutable DPREFIX-EXACT-1 input and FFN norm antecedent, implement strict-f32
  RMSNorm/SwiGLU/projection and byte-only fresh-process reproduction, bind
  private retention and public evidence writers, and prove the fixed entrypoint
  resolves all fourteen dependencies in a zero-open/zero-read preflight plus a
  full synthetic integration matrix while leaving ledger 139 and creating no
  real attempt or execution-start record.
- [x] T017-219 Authorize checkpoint-free cross-event reuse of the eight
  canonical expert down-output vectors: bind their terminal recovery,
  manifest, canonical-input and three-weight provenance; verify before/after
  identities plus immutable single-link storage; constrain the distinct
  analytical consumer to the already-frozen weighted-MoE aggregate theorem;
  and preserve zero checkpoint reads, zero shard opens, no aggregate
  evaluation, historical dispositions, and the real-payload ledger at 163.
- [x] T017-220 Evaluate the frozen weighted-MoE aggregate theorem exactly twice
  from the eight authorized canonical expert outputs and immutable ID-keyed
  routing-weight evidence; bank the nominal aggregate plus direct, centered,
  and intersected enclosure identities; preserve max-absolute and RMSE passes
  but fail closed on the frozen cosine budget, leaving membership PASS,
  coefficient qualification FAIL, route invariance unproven, checkpoint reads
  and shard opens zero, and the real-payload ledger unchanged at 163.
- [x] T017-221 Freeze complete-layer aggregate acceptance v2 at the committed
  final-f32 residual-plus-routed-plus-shared surface: use the unchanged R10
  final-output limits, reuse the v1 routed interval without tightening, include
  final-cast transport, freeze the tangent-ball cosine lemma before observing
  the shared output, derive the exact three-payload shared recovery inventory,
  and preserve v1 history, zero checkpoint access, and ledger 163.
- [x] T017-222 Authorize checkpoint-free cross-event reuse of the recovered
  canonical shared-expert f32 `[6144]` output: bind its terminal recovery,
  exact two-process reproduction, immutable single-link persisted authority,
  and three-weight provenance; scope `delta_S=0` only to the frozen routing-
  weight ambiguity proof; bind the distinct complete-layer-v2 analytical
  consumer and unchanged routed dependencies without evaluation or
  recomputation; preserve zero checkpoint reads, zero shard opens, historical
  dispositions, and the real-payload ledger at 166.
- [x] T017-223 Evaluate complete-layer aggregate acceptance v2 exactly three
  fresh times from the authorized residual, routed, and shared point
  authorities; preserve the frozen routed enclosure and all historical
  failures, bank the qualified canonical complete layer only on mathematical
  PASS, and keep checkpoint reads, shard opens, and the real-payload ledger at
  zero, zero, and 166 respectively.
- [x] T017-224 Correct the DPREFIX/v3.1/expert/e942 semantic roles append-only,
  freeze the production layer-3 graph and representative M1-F0 v2 boundary at
  `S0 -> attention -> S1 -> FFN RMSNorm -> router`, derive the exact nine
  hash-only attention payloads and three separately reusable router
  authorities, preserve all historical identities as valid evidence on their
  precise surfaces, and bind the future CPU/no-BLAS, NTFY, one-open,
  166-to-175 event shape without authorizing or executing any read.
- [x] T017-225 Adjudicate the representative M1-F0 RMSNorm epsilon entirely
  from committed checkpoint-free evidence: trace GLM-5.2 configuration,
  production f32 plumbing, accepted historical M1-F0, R9, dense-prefix, and
  boundary-freeze lineages; establish exact `f32(1e-5)` (`0x3727c5ac`) for all
  four representative RMSNorm sites; supersede only the erroneous v1/v2
  declarations append-only; and bind regression tests while preserving zero
  execution authority and the real-payload ledger at 166.
- [x] T017-226 Prepare the representative M1-F0 attention-to-router execution
  authorization for independent adversarial review: bind boundary v3, semantic
  graph v2, exact `f32(1e-5)` fixed-order semantics, the catalog-derived ordered
  nine-read/132,900,864-byte one-open inventory, durable 166-to-175 partial
  accounting, the three separately scoped retained router authorities, exact
  output/replay requirements, and the stop-before-experts boundary; add a
  checkpoint-free validator and mutation suite while leaving execution
  unauthorized and the real-payload ledger unchanged at 166.
- [x] T017-227 Repair the rejected representative M1-F0 authorization
  append-only: bind a dedicated nine-read plus three-retained-authority plus
  canonical-S0 executor with durable attempt/start/receipt/journal/terminal
  accounting, canonical stage names, exact retained before/after identity
  checks, independent production decoders, and stop-before-experts semantics;
  rehearse the complete real geometry in two fresh synthetic processes plus
  fifteen terminal failure paths; harden the schema/validator against payload,
  decoder, F32-identity, retention, receipt, executor, rehearsal, S0, banker,
  vocabulary, ledger, and surface mutations while preserving rejected v1,
  zero checkpoint access, no real execution authority, and ledger 166.
- [x] T017-228 Bank independent review-2 at its operator-prescribed byte
  identity, then repair R1/R2/R3 and N7-N11 append-only: grant the three
  retained router authorities to the exact event consumer, restore ten-run
  retention-only reproduction, front-load ledger/S0/router/decoder/environment/
  storage/destination/shard-object gates, durably retain payloads before
  receipts, bind interrupted-attempt terminalization and single-descriptor
  consumption, rehearse the full real geometry with 29 exact failure paths,
  and publish authorization v3 for independent re-review while leaving real
  execution unauthorized, checkpoint reads and shard opens zero, and ledger
  166.
- [x] T017-229 Prepare the accepted representative M1-F0 authorization-v3
  single-use execution release append-only: bind the exact reviewed code head,
  accepted identities, canonical S0, ordered nine-read inventory, shard,
  pinned CPU environment, storage floor, ledger 166-to-175, stop-before-
  experts boundary, and irrevocable attempt-start consumption semantics; add
  a checkpoint-free semantic validator and mutation suite while leaving the
  release unapproved, real-event authorization false, checkpoint reads and
  shard opens zero, and the real ledger unchanged at 166.
- [x] T017-230 Preserve the release-v1 pre-attempt fail-closed invocation with
  zero consumption, identify its nested `ledger.after` lookup as a consumer
  mismatch against the bound public result's top-level `ledger_after`, bind an
  exact-schema two-authority ledger adapter and append-only wrapper v2, regress
  the former KeyError plus malformed/stale/disagreement cases, and prepare a
  release-v2 control plane that rejects the old token while leaving approval,
  real-event authority, checkpoint reads, shard opens, attempt state, and the
  real ledger unchanged at false, zero, zero, absent, and 166 respectively.
- [x] T017-231 Bank the successful representative M1-F0 route-only event at
  ledger 175 and recover concrete selected IDs and routing weights exactly from
  retained-only reproduction evidence, with zero checkpoint rereads and no
  expert execution.
- [x] T017-232 Prepare and independently accept the representative expert-output
  recovery authorization: bind `router_normalized`, the atomic canonical
  ID/weight order, 24 retained packed payloads totaling 90,439,680 bytes,
  decoder/kernel identities, concrete f32 output artifacts, two fresh-process
  reproduction, and stop-before-aggregate semantics at ledger 175-to-175.
- [x] T017-233 Prepare and independently accept the retained-only single-use
  expert-recovery release after repairing the cycle-1 runtime-environment gate
  and terminalizer output-vocabulary mismatch; bind ledger 175, zero checkpoint
  and shard budgets, durable one-shot state, crash reconciliation, fixed
  destinations, separate approval/token gating, and preserve
  `real_event_authorized=false` with zero real expert executions.
- [x] T017-234 Execute the independently approved retained-only representative
  expert-output recovery release exactly once: preserve ledger 175-to-175 with
  zero checkpoint reads and shard opens, bank eight finite f32 `[6144]`
  canonical expert outputs, pass 2/2 fresh-process exact reproduction, retain
  all 25 input identities unchanged, and stop before aggregate/shared/FFN/S2.
- [x] T017-235 Prepare and independently accept checkpoint-free cross-event
  reuse of the eight representative expert outputs: atomically bind canonical
  ID-weight-output triples, enforce open-once expected/before/consumed/after
  identity and immutable f32 `[6144]` geometry, freeze the analytical binary64
  `math.fsum` aggregate-input contract while separating the production serial-
  f32 policy, bank exact Fable 5 and Extra High composition acceptance, and
  preserve ledger 175 with zero checkpoint, shard, expert, and aggregate work.
- [x] T017-236 Prepare and independently accept the checkpoint-free
  representative routed-aggregate authorization: bind the eight retained
  representative outputs, direct CPython 3.14.6 `math.fsum` binary64
  proof/reference arithmetic, f64 `[6144]` serialization, synthetic
  real-geometry rehearsal, durable one-shot semantics for a future separate
  release, and preserve ledger 175 with zero checkpoint, shard, expert, and
  real aggregate execution.
- [x] T017-237 Prepare and independently accept the checkpoint-free
  representative routed-aggregate single-use release: pin fixed retained-input,
  attempt, output, approval, and token destinations; require exclusive durable
  attempt-start, independent durable aggregate-execution accounting, and
  deterministic interruption reconciliation; publish one f64 `[6144]`
  artifact durably without replacement and confer authority only through a
  matching `COMPLETE` terminal; retain the accepted two-process synthetic
  determinism contract; and preserve ledger 175 with zero real aggregate
  execution and no GO token.

## Phase 36: Convergence

- [x] T017-238 Reconcile the append-only F017 plan/task ledger with the already
  banked routed-aggregate execution/reuse and representative shared-expert
  authorization/release/execution authorities, preserving their actual
  checkpoint-free dispositions and exact committed identities per Constitution
  XII (partial).
- [x] T017-239 Prepare and independently accept checkpoint-free cross-event
  reuse of the banked representative shared-expert output and one future
  proof/reference FFN-composition authorization: bind immutable shared and
  routed inputs, adjudicate routed-plus-shared and later S1 residual semantics,
  implement/rehearse/validate an exact executor without evaluating the real
  FFN or S2, bank exact Fable 5 review bytes, and preserve ledger 175 with zero
  checkpoint, shard, expert, FFN, and S2 execution per the operator's
  shared-output reuse and FFN-boundary request (missing).
