# Feature 021: bounded Qwen3.8 page admission

Status: design and synthetic admission only, 2026-10-04 UTC. This slice does not load the acquired model or execute checkpoint-supplied Python.

## Problem and outcome

The acquired mixed 4/8-bit checkpoint is 98.924 GiB, larger than the M2 Max's 64 GiB unified memory. Paging only the approximately 32 GB PLE n-gram table still leaves more than physical memory. A full-checkpoint run requires a separate page catalog and scheduler whose demand path preserves the converted checkpoint's exact tensor bytes and whose resource use can be bounded and observed.

This slice admits exact, header-derived file spans for one routed expert (all three affine projection triples) or one PLE shard row block (one affine triple). It exercises demand priority, hint invalidation, in-flight reservation, and GPU lease lifetime on synthetic pages. It provides no model execution path and makes no throughput claim.

## Requirements and exclusion

1. A page key identifies either one expert in one of 48 text layers, or one row block of one of 128 PLE shards in layer 1. Unknown layouts and incomplete affine triples fail closed.
2. Only actual model demand may acquire a page. A hint can schedule I/O but cannot select a route, expert weight, or PLE row.
3. Demand I/O has priority over queued hints. In-flight hint promotion cannot create a duplicate read or permit unrelated hints to overtake its waiting demand.
4. In-flight bytes reserve weight and staging capacity before I/O. Idle resident pages may be evicted; active demand pages and GPU-leased pages cannot. An unsuccessful speculative admission does not evict a useful page.
5. Cancellation invalidates hints and waits for I/O completion to release buffers. A GPU lease cannot be released until completion is acknowledged.
6. Process memory, system headroom, swap growth, and memory pressure are monitored stop conditions. Scheduler counters alone do not prove physical residency or prevent an allocator from overshooting between samples.
7. The stock `mlx_lm.load()`/`generate` path remains blocked on this host. No full-checkpoint inference, checkpoint Python import, package installation, or benchmark belongs to this slice.

## Success evidence

Run the exact header-only catalog admission against the pinned checkpoint and the synthetic contract tests. Report model bytes separately from process bytes and physical SSD reads. Source review and synthetic acceptance do not establish numerical parity, real page residency, SSD attribution, or 20+ tokens/s.
