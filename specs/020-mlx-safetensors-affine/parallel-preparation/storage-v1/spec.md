# Feature Specification: Bounded storage preparation

**Feature Branch**: `prep/glm53-storage-resource-20261004`
**Created**: 2026-10-04
**Status**: Preparation specification
**Input**: Independently reviewed synthetic bounded storage, ownership, eviction,
cancellation and memory-ledger contracts for GLM-5.3-Flash.

## User Scenarios & Testing

### User Story 1 — Refuse unsafe admission (Priority: P1)
An integrator needs all resource obligations checked before reading or allocating
selected packed payloads. Independent test: compare exact category totals and
read/allocation counters at, below and above a small synthetic budget.

Acceptance scenarios:
1. Given insufficient aggregate or category capacity, reservation refuses with
   zero payload reads and zero payload allocations and unchanged ledger.
2. Given admitted opaque identities and bounded extents, partial reads assemble
   exactly the selected packed bytes without decoding; logical size is separate.
3. Given stale descriptors, recipes or extents, admission refuses and cleans up.

### User Story 2 — Preserve ownership (Priority: P1)
An integrator needs exclusive ownership, explicit transfer and release, and
refusal of eviction during a borrow or outstanding operation. Independent test:
transfer a lease, reject the old token, pin/unpin, dispatch/acknowledge and evict.

Acceptance scenarios:
1. Given a transferred lease, the previous owner cannot read, release or evict it.
2. Given pinned or in-flight bytes, release and eviction refuse without change.
3. Given released bytes, explicit eviction returns resident capacity once only;
   lease lifetime is independent of source closure after capture.

### User Story 3 — Cancel and recover without leaks (Priority: P1)
An integrator needs cancellation at every boundary with explicit epoch/position
retention, and bounded repeated operation. Independent test: adversarial traces,
error injection and mutation checks return all nonbaseline charges to zero after
unprotected quiescent cleanup. Published protected storage retains explicit
ownership and charges until a later integrated shutdown policy permits release.

Acceptance scenarios:
1. Cancellation before reservation, read, admission and dispatch prevents the
   next forbidden side effect; cancellation during a pending operation retains
   ownership and charges until acknowledgement.
2. Cancellation is idempotent for a current cancelled token; stale tokens refuse.
3. Short reads, interrupted reads, injected I/O/allocation/dispatch errors and
   repeated reserve/evict cycles never publish partial data or double release.
4. Step receipts bind explicit checkpoint, recipe, request, epoch, position,
   count and context; storage never advances model state.

### Edge Cases
Zero/negative/overflow extents, huge logical sizes, equal-capacity budgets,
multiple outstanding reservations, cross-manager handles, forged plans, reused
slots, cancellation while pinned, stale completion, metadata change mid-read,
readers reporting too many bytes, bounded interrupt exhaustion and teardown.

## Requirements

### Functional Requirements
- **FR-001**: Separate resident trunk, experts, state, scratch, I/O staging and
  fixed overhead, and distinguish reserved capacity from logical payload size.
- **FR-002**: Validate total/category bounds and checked arithmetic before any
  payload allocation/read; no implicit eviction or cap widening.
- **FR-003**: Preserve selected packed bytes and opaque tensor/role/layer/expert/
  recipe identity; reject forged/stale plans and descriptor changes.
- **FR-004**: Enforce exclusive lease tokens, explicit transfer/release,
  source-independent captured lifetime and stale-generation refusal.
- **FR-005**: Refuse eviction while owned and not cancelled, while pinned or
  in-flight, or while published-protected; refuse release while pinned or
  in-flight. A quiescent unpinned cancelled entry may be evicted without a
  separate release, unless its published storage is protected. Charge
  retained resident storage until explicit destruction, including cancelled pins.
- **FR-006**: Define and test idempotent cancellation at reservation, read,
  admission and dispatch; acknowledge pending work before freeing its bytes.
- **FR-007**: Inject partial/short/failed/oversized/interrupted reads and
  allocation/admission/dispatch failures; clean errors without partial publication.
- **FR-008**: Bind explicit epoch/position step identities and report completed
  or cancelled receipts without changing model state; reject mismatched boundaries.
- **FR-009**: Provide adversarial synthetic state-machine fixtures, bounded host
  tests, repeated cycles and mutation witnesses for leaks and double release.
- **FR-010**: Preserve immutable integration contract and accepted sources; deliver
  exact hashes, targeted host evidence, independent terminal ACCEPT/0 and handoff.
- **FR-011**: Identify real resource/native adapter dependencies and make no real
  paging, performance, numerical or model-support claim.

### Key Entities
Resource ledger; descriptor-bound selection; packed lease; exclusive owner;
operation acknowledgement; explicit step envelope; cancellation receipt.

## Success Criteria
- **SC-001**: Every FR has an identified task and host evidence or review artifact.
- **SC-002**: All requested unsafe transitions refuse with unchanged obligations;
  all unprotected quiescent cleanup traces return to their initial resource totals.
  Published protected storage remains charged under its explicit lifetime policy.
- **SC-003**: Independent review accepts the exact final source package with zero
  findings, verified reviewer identity, and reproducible content hashes.
- **SC-004**: Handoff clearly separates synthetic proofs from all open production
  dependencies; zero real payload reads and zero native GPU calls in this lane.

## Assumptions
Single-threaded deterministic event fixtures explore ordering, not scheduler or
native memory safety. Synthetic capacity obligations model a future adapter;
Python object sizes, OS/Metal residency and allocator guidelines are not global
physical caps. Synthetic bytes are authored here, at most 4096 per source.
No checkpoint/snapshot/Models access, MLX imports or Cargo/workspace changes.
Only owned prefixes change. Coordinator alone may authorize integration.

## Constitution compliance
Constitution I–XII: see [plan.md Constitution Check](plan.md). No exception.
Bounded synthetic proof and host evidence precede claims; inherited/shared sources,
model math and native execution remain outside this preparation.
