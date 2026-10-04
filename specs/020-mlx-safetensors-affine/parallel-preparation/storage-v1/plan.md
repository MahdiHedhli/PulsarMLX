# Implementation Plan: Bounded storage preparation
Branch `prep/glm53-storage-resource-20261004`; date 2026-10-04; [spec](spec.md).

## Summary
Prepare a storage-only contract and deterministic executable fixture model. It
is an integration proposal under frozen v1, not a cache implementation.

## Technical Context
Python 3 stdlib only; synthetic in-memory bytes; unittest host validation.
Single-threaded bounded event seam, four concurrent fixture slots, <=4096 bytes
per source; synthetic slot capacity rounded to 8 bytes. No performance targets.
No Rust changes: Cargo workspace/GPU/lifecycle tests are excluded by authorization.

## Constitution Check
Before research and after design: I/III explicit invariants and exact evidence;
II/V shared sources unchanged and model-neutral opaque identities; IV separated
capacity terms and native dependencies; VI no model math/kernels; VII no benchmark
claim; VIII synthetic-only compatibility; IX inherited licensing untouched;
X focused tested change; XI no secrets/weights; XII artifacts and handoff together.
No constitution exception. User restrictions override skill instructions to
persist `.specify/feature.json`, dispatch agents or update agent context. Setup
uses manual template application and direct artifact inspection as shown in
quickstart.md. A historical normal prerequisite-script invocation unexpectedly
persisted shared feature.json; its exact original HEAD bytes were restored and
the incident retained privately. A later paths-only invocation was read-only,
but direct file inspection supersedes script invocation as this lane procedure.
No extensions.yml exists, so all hooks are skipped.

## Project Structure
Documentation in `specs/020-mlx-safetensors-affine/parallel-preparation/storage-v1/`:
spec, checklist, plan, research, data-model, contracts/interface, quickstart,
tasks, private analysis, proof, validation and handoff. Fixture implementation in
`scripts/research/glm53_flash/native_preparation_storage_v1/fixture.py`;
independently specified trace corpus in that prefix's `adversarial.json`;
separate reference accounting/transition oracle and mutation witnesses in
`scripts/research/tests/test_glm53_native_preparation_storage_v1.py`.
Private raw failures, host output, review capsule and receipts in attempt-02 audit.

## Phases
0. Read accepted catalog/range and stream ownership sources. Record decisions.
1. Define entity/state and opaque reserve/read/cancel/release interface.
2. Generate story tasks and perform read-only spec/plan/task analysis.
3. Write adversarial tests before fixture implementation, retain initial failures.
4. Validate host properties, mutation witnesses, exact diff and ownership scope.
5. Freeze source/capsule hashes; authorized tool-free Opus review; repair recoverable
   findings and re-review exact final package. Coordinator check stays external.
