# Storage preparation handoff

Assigned branch: `prep/glm53-storage-resource-20261004`.
Base: `bff720bd4ddc83fcf6c41ed4c58a938d8c2c33ef`.
Bounded deliverable: opaque lease/reservation/read/cancel/release proposal,
deterministic packed-byte fixture, independent literal traces and host oracles.
No cache/runtime integration or production qualification.

Reproduce with [quickstart](quickstart.md); observed host evidence and requirement
mapping are in [validation](validation.md). Raw test/failure logs, exact source
manifest, review capsule, verified modelUsage and terminal receipt reside in:
`/Users/mhedhli/Library/Application Support/PulsarMLX-handoff/20261004-parallel-preparation/storage/attempt-02/`.
Content hashes and commit are reported by the private progress/final receipt;
this document avoids self-referential hashes. Only a receipt matching the final
source manifest and capsule, actual claude-opus-5-5 modelUsage, provider success,
exit 0 and terminal ACCEPT/0 establishes independent acceptance. A provider error
or initial review is not an acceptance verdict. Coordinator must independently
check exact package before any integration; no push/merge is authorized here.

## Open production dependencies
- Coordinator reconciliation with model/state lane and accepted numerical owner;
  state commit/reset/epoch changes stay outside storage. Dispatch receipts bind
  before-state envelope but cannot qualify model math or numerical support.
- Real descriptor-bound sealed selection/packed lease adapter and immutable
  captured-content identity. Fixture source stamps do not prove atomic snapshots.
- Measured physical resource accounting: retained slab capacity, alignment,
  fragmentation, allocator caches, staging/copies, scratch, trunk/experts/state/
  fixed overhead, process/Metal overlap and competing allocations. Guidelines
  and logical sizes cannot become hard global caps without these measurements.
- Real async cancellation/completion acknowledgement, pin/borrow lifetimes,
  concurrency synchronization and protected-trunk shutdown policy. Fixture
  payload observation copies are test-only, not a production borrow API.
- Integrated real resource/ownership validation and independently owned real
  numerical/model qualification under later explicit authorization.

real_reads=0; native_gpu_calls=0. No Models/checkpoint/snapshot access, MLX import,
real numerical execution, paging/performance measurement, model switch or full
model load. Christmas 2026 remains an aspiration without a quality waiver.
