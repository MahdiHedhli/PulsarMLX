# Storage-v1 proposal under immutable integration v1

Frozen authority: `/Users/mhedhli/Library/Application Support/PulsarMLX-handoff/20261004-parallel-preparation/integration-contract-v1.md`.
No revision of v1 or model operation/state semantics is made here. Proposed adapter
must receive coordinator review before integration.

## Opaque boundary
`reserve(source, selection, step, boundary, owner, *, category='experts', scratch=0,
scratch_override=None, protected=False, cancelled=False)` checks
source seal/descriptor/identity, u64 bounds, <=4096 fixture extent, slot bound and
all ledger terms atomically, then returns opaque PackedTensorLease. Reservation
causes no payload allocation/read. Category accepts only `trunk` or `experts`.
`protected` is a bool set immutably at reservation; it protects published storage
from cancellation/eviction. `cancelled` is the before-reservation cancellation
flag. `scratch_override` is a test-only u64 overflow seam; when present it replaces
`scratch`, without changing admission limits. `begin_read(lease, owner)` allocates staging;
`read(lease, owner)` advances one injected partial positional read; complete read
publishes nothing until `admit(lease, owner)` verifies identity and copies packed
bytes to independent resident storage. That copy is unpublished until the
post-copy descriptor check and cancel barrier pass; rejected unpublished copies
return every entry obligation even when protected. Full resident capacity + staging capacity
are reserved simultaneously, including publication copy peak. Scratch is reserved
through dispatch completion, even if not materialized by this fixture.

`transfer(lease, owner, new_owner)` returns a new capability, invalidating the old
one, without copying bytes or changing ledger totals. `pin/unpin` are explicit,
non-nesting fixture borrows. `payload` is a test-only bounded observation copy outside the modeled ledger; it
works only after complete admission and refuses cancelled tokens. Production
adapters must expose a lifetime-guarded pinned borrow instead. Observation copies
are not resident storage accounting or a production lease interface. `dispatch(lease, owner, step, boundary)` checks exact
step and current explicit request/epoch/position boundary before issuing a simulated operation.
`acknowledge(lease, owner)` means external work has stopped touching its bytes;
returns a receipt binding the original step and completed/cancelled status.
Storage never advances positions or epochs; lane owning state commits separately.
Completed or cancelled operations cannot dispatch again. Receipt has
`state_advance_owned_by_storage=false`. Cancellation/refusal retains caller's
before epoch/position; no hidden reset. Late/mismatched capabilities cannot ack.

`cancel(lease, owner)` is idempotent while that current token remains cancelled
or cancelling. Before read/admission/dispatch it prevents new side effects.
During read or dispatch it retains charges and bytes until `read`/`acknowledge`
observes the cancellation and acknowledges quiescence. Admission's deterministic
cancel barrier discards its unpublished copy synchronously. A cancelled pin keeps
resident charge until unpin, then frees it. `release` consumes the exclusive
owner only when unpinned and no operation is pending; it frees unused transient
obligations. For a never-published entry (reserved, read_complete or unpublished
cancelled), it also returns the unused resident capacity reservation immediately;
no resident storage exists to retain. For published residency, release retains
resident bytes and capacity until explicit eviction (or permitted cancellation). `evict` requires owner released or
cancelled, unpinned, quiescent, and unprotected resident storage. A protected resident also refuses
explicit cancellation; its owner must retain it. Dispatch error cleanup retains protected resident capacity while returning
transients. The injected dispatch-cancel seam applies the same Protected guard
as explicit cancel, before submission; acknowledgement of any pending cancellation
also retains protected resident storage. Full protected-resource teardown
is outside this fixture and requires an integrated adapter policy. Eviction destroys
resident storage and returns capacity, invalidating the token. Freed slots get
new generations; stale/foreign/forged capabilities refuse. Closed source after
capture does not invalidate owned bytes; before capture it refuses.

## Refusal and resource rules
Distinct fixture codes: Identity, Stale, Range, Overflow, Budget, Slots, Owner,
Phase, Pinned, InFlight, Protected, Cancelled, ShortRead, Read, ReaderCount,
InterruptLimit, Allocation, Admission, Dispatch. Validation precedence is token/generation, owner identity/ownership, cancellation,
then operation phase and guards. Release/evict/ack/unpin/read/cancel deliberately accept
cancelled tokens so cleanup can proceed; release/evict check in-flight and pins
before owner-state guards. Read after quiescence refuses Phase; cancel is
idempotent for a current cancelled token. Refusal is atomic unless a
read/admission/dispatch operation already began: errors then unwind all of that
entry's obligations and publish no partial data. Pinned resident cancellation
retains storage until unpin. No fallback widens reads, recipe or capacity.
Resource vector order: trunk, experts, state, scratch, io, overhead. Logical bytes
are never charged as capacity. Fixed baseline and category/aggregate caps are
synthetic obligations, not Python heap, physical RAM, MLX allocator limits or
Metal/global memory caps. A real adapter must account retained allocator capacity
and transient copies; lease release alone cannot subtract retained pool memory.

## Synthetic boundary and prospective production gates
Proof scope: deterministic serial event orders and injected faults, small authored
byte stores. No threads, model math, real reads, paging, performance, native
pointers or GPU calls. Production requires descriptor/snapshot authority adapter,
resource measurement incl fragmentation/allocator caches/process/Metal overlap,
real asynchronous read/cancel/completion/pin lifetime, and coordinator reconciliation
with state lane. Storage receipts cannot qualify numerics or the full model.

Fixture source simplification: only the latest Selection is valid; a second
select supersedes its earlier selection without changing the byte store. Several
reservations may share the same current selection. A real adapter must preserve
the accepted ability to retain multiple sealed plans against one admitted source.
