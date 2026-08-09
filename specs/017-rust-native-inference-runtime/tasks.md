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

- [ ] T017-30 Implement page-aligned allocator contract with stable slot IDs and bounded max in-use limit.
- [ ] T017-31 Add deterministic reuse policy and reuse counters.
- [ ] T017-32 Add zeroing policy documentation + tests.
- [ ] T017-33 Add telemetry for requested bytes, allocated bytes, alignment, slot-count, reuse-count, peak logical residency.

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

- [ ] T017-50 Add separate timers/counters for:
  - storage/read
  - decode
  - buffer/materialization
  - backend build/import
  - compute
- [ ] T017-51 Ensure layer-level aggregates and fixture events can attribute each bucket independently.
- [ ] T017-52 Add fail-closed behavior if any bucket overflows uninitialized telemetry states.

## Phase 6 — Decoder and numerical boundary

- [x] T017-60 Qualify at least one required format lane with strict criteria.
- [x] T017-61 Add malformed and truncated input rejection coverage.
- [x] T017-62 Add bit-level comparison or documented epsilon contract where exactness is not yet possible.
- [ ] T017-63 Record throughput and allocator impact for qualified formats.

## Phase 7 — Apple bridge spike and native registration

- [x] T017-70 Build native bridge registration spike with deterministic buffer ownership and teardown ordering.
- [x] T017-71 Demonstrate stable address behavior across command submission boundaries.
- [ ] T017-72 Add no-copy or explicit `newBufferWithBytesNoCopy` qualification matrix.
- [ ] T017-73 Add fail-closed teardown and cancellation path tests.

## Phase 8 — Runtime skeleton and mode-aware validation

- [ ] T017-80 Add reusable runtime contracts and GLM plugin boundary stubs.
- [ ] T017-81 Add `teacher_forced_validation` and `golden_strict` result classes.
- [ ] T017-82 Add mismatch classification and deterministic stopping policy.

## Phase 9 — Checkpoint-free fixture ladder

- [ ] T017-90 Implement boundaries 1→11 in strict order and stop on mismatch.
- [ ] T017-91 Validate boundary 2 and 3 on M2 Max using hash-bound local fixtures.
- [ ] T017-92 Capture residual telemetry and memory admission outcomes at every boundary.

## M2 Max safety gate (mandatory)

- [ ] T017-99 Reject dec-trunk residency plans requiring swap-risky memory profiles unless allocator study is complete and green.

## Release-prep

- [ ] T018-00 Send milestone NTFY update after authoritative input incorporation and milestone gates.
