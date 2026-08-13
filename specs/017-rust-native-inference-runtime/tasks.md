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
- [ ] T017-173 Execute exactly one separately authorized M1-E real-expert
  attempt from the immutable execution config, then stop before M1-F.
