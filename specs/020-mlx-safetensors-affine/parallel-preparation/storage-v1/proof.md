# Bounded synthetic invariants and proof obligations
This is a source argument backed by adversarial host evidence, not a machine-
checked proof, native concurrency proof, or physical memory measurement.

1. Reservation atomicity: reserve derives a local six-term vector, validates
   each u64 operation, category cap, sum cap, source seal, step/boundary and slot
   before changing ledger/entries. It creates no payload buffer and calls no
   read_at. Counter assertions witness every pre-side-effect refusal tested.
2. Accounting: baseline plus each entry's held resident capacity, staging and
   scratch equals the ledger. Capacity is reserved before materialization. Release
   refunds an unused resident reservation for never-published entries immediately;
   published resident storage stays charged until destruction. Return staging after
   admission and scratch after completion/release.
   Ledger audit reconstructs from holdings; corpus vectors supply independent
   literal totals, including immediate refund of unpublished reservations. No logical/dequantized size or allocator guideline is a cap.
3. Exclusive authority: public operations resolve object identity of the current
   token in the bounded slot table, current slot generation, owner and phase.
   Transfer replaces token; eviction removes entry; reuse advances generation.
   Foreign/forged/transferred/reused token tests cover stale acknowledgement too.
   Python private fields are trusted fault seams, not a hardened capability system.
4. Exact capture: checked selection precedes staging, partial reads advance only
   within selected extent, zero/oversized/error/too many interrupts abort without
   resident publication. Descriptor generation is checked before/after reads and
   publication. Captured immutable resident storage survives source closure.
5. Lifetime: release/evict refuse pinned or pending entries. Cancellation during
   read/dispatch marks cancelling without releasing bytes/charges; acknowledgement
   clears pending, returns transient charges and retains pinned resident storage.
   Unpin then returns cancelled residency, except published protected residency
   remains. Unpublished admission copies have no protected-retention privilege;
   cancellation or post-copy descriptor rejection returns every obligation.
   Protected dispatch refusal retains resident storage and releases only transient
   obligations; injected dispatch cancellation obeys explicit cancellation guards.
6. Cleanup: held booleans ensure repeated cleanup returns obligations only once;
   current-token cancellation is idempotent, repeated release/evict refuse. All
   unprotected quiescent traces reconcile to baseline. Protected trunk teardown
   needs a future adapter policy; retained protected storage is explicit ownership,
   not claimed complete cleanup. Mutation witnesses detect a leak, double refund and omission of the unpublished
   reservation refund (which internal held-flag audit alone cannot detect).
7. State ownership: matching request/checkpoint/graph/recipe/epoch/position/count/
   context envelope is required, with exact equality on dispatch and caller-owned
   boundary equality. Receipts bind that envelope; storage owns no advancement,
   resets or model math. Coordinator/state lane must verify true live boundaries
   and apply their own once-only state commit rule.

Six independent literal traces, 24 event permutations and 128 repeat cycles
are finite witnesses, not exhaustive scheduling exploration. Injected failures
include genuine MemoryError exception branches without forcing host OOM. Tiny
source bytes, metadata and test observation copies are outside the modeled
adapter ledger; resident/staging capacity claims are synthetic obligations only.
Real adapters must measure every retained allocation, transient copy and native
resource lifetime. No inference from these tests to real paging or performance.
