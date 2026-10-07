# Feature 021: bounded Qwen3.8 page admission

Status: design, synthetic admission, and one separately authorized real-file digest admission, 2026-10-05 UTC. The [local evidence](evidence/bound-admission-local-verification-2026-10-05.md) qualifies file integrity and catalog binding only. This slice does not load the acquired model or execute checkpoint-supplied Python.

## Problem and outcome

The acquired mixed 4/8-bit checkpoint is 98.924 GiB, larger than the M2 Max's 64 GiB unified memory. Paging only the approximately 32 GB PLE n-gram table still leaves more than physical memory. A full-checkpoint run requires a separate page catalog and scheduler whose demand path preserves the converted checkpoint's exact tensor bytes and whose resource use can be bounded and observed.

This slice admits exact, header-derived file spans for one routed expert (all three affine projection triples) or one PLE shard row block (one affine triple). It exercises demand priority, hint invalidation, in-flight reservation, and GPU lease lifetime on synthetic pages. A fixture-only adapter performs real `preadv` calls against tiny synthetic files and retains host page buffers. It provides no checkpoint or MLX execution path and makes no throughput claim.

## Requirements and exclusion

1. A page key identifies either one expert in one of 48 text layers, or one row block of one of 128 PLE shards in layer 1. Unknown layouts and incomplete affine triples fail closed.
2. Only actual model demand may acquire a page. A hint can schedule I/O but cannot select a route, expert weight, or PLE row.
3. Demand I/O has priority over queued hints. In-flight hint promotion cannot create a duplicate read or permit unrelated hints to overtake its waiting demand.
4. In-flight bytes reserve weight and staging capacity before I/O. Idle resident pages may be evicted; active demand pages and GPU-leased pages cannot. An unsuccessful speculative admission does not evict a useful page.
5. Cancellation invalidates hints and waits for I/O completion to release buffers. A GPU lease cannot be released until completion is acknowledged.
6. Process memory, system headroom, swap growth, and memory pressure are monitored stop conditions. Scheduler counters alone do not prove physical residency or prevent an allocator from overshooting between samples.
7. The fixture I/O adapter refuses directories without a marker, symlinked or changed files, out-of-bounds spans, short reads, and accounting divergence. It admits only synthetic test files; its memory callback is injected and does not qualify a macOS production monitor.
8. The stock `mlx_lm.load()`/`generate` path remains blocked on this host. No full-checkpoint inference, checkpoint Python import, package installation, or benchmark belongs to this slice.

## Success evidence

Run the exact header-only catalog admission against the pinned checkpoint and the synthetic contract tests. Report model bytes separately from process bytes and physical SSD reads. Source review and synthetic acceptance do not establish numerical parity, real page residency, SSD attribution, or 20+ tokens/s.

## Authorized adapter contract slice, 2026-10-06

This continuation implements steps 1–3 of `production-adapter-next-gate.md` on generated fixtures only. The prior real-file admission is historical evidence; do not repeat that read in this slice. No packages, backend/MLX execution, model downloads, external source transmission or push are authorized.

- **US1 (P1): Bound session and owning leases.** A caller can consume a live catalog/verified-handle binding through a separate synthetic adapter, with authenticated fixed/page bytes and original-object ticket/completion identity. Cancellation and failure drain operations, close all file handles, preserve retained views/owners, and never adopt previous-request work.
- **US2 (P1): Reservation and fresh observation.** Before explicit payload allocations, reserve all fixed/page/device duplicates, staging and runtime scratch; validate independent injected process/MLX/runtime/headroom/swap observations, byte units, provenance, monotonic sample sequence/time and maximum age. Preserve the 48/40/16 GiB stops and 8 GiB other-process allowance. Derived views keep owners counted until they no longer export the buffer. These injected observations do not qualify a real sampler.
- **US3 (P1): Operation-bound trace.** Actual deterministic synthetic route and PLE operations alone create demand. Trace exact catalog spans, real verified reads, owning leases and synthetic completion objects. Every admitted hint ends as useful, late or wasted, including eviction, cancellation and failure. Reject forged operations, tickets/completions, altered keys/spans/byte counts and incomplete terminal accounting. Physical SSD attribution remains unavailable.

Acceptance uses tiny generated cross-file data, malformed/freshness/boundary samples, retained child views, read/cleanup failures, demand/hint interleavings and independent trace replay against the synthetic operation table and immutable catalog snapshot. Local source review established the initial fixture contract; a [later independent static review and repair](evidence/adapter-contract-independent-review-2026-10-07.md) covered this slice. Production backend review and qualification remain future gates. Preserve existing reviewed Qwen modules and frozen evidence; additions must not relax the fixture marker or 16 MiB cap.
