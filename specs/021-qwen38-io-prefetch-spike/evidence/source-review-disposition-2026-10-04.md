# Local disposition of Claude source review

The [frozen source review](claude-opus-source-review-2026-10-04.md) covered commit `11a4246464fd55f5ce95f287fdee598a1d6a707d`. This disposition records local checks and synthetic-only changes made afterward. It does not qualify the actual checkpoint or MLX runtime.

| Finding | Disposition |
| --- | --- |
| 1. In-flight hint stops a fit-capable demand | Reproduced and fixed. The scheduler invalidates unpromoted pending hints and waits for their I/O reservation to drain. |
| 2. Demand key lacks route tie | Confirmed. Trace schema v0.3 requires an expert demand to match a route at the same step and layer, or a PLE demand to match a declared lookup. This checks trace consistency, not whether the producer's route or lookup was genuine. |
| 3. Demand I/O invisible | Confirmed. The trace now records demand I/O start/done, blocks speculative I/O behind an unserved demand, and rejects hints for already demanded keys. |
| 4. Fixture drops lease before releasing views | Defensive order changed: validate GPU completion, release parent views, then drop the lease. A derived standard-library `memoryview` did not reproduce the reported `BufferError`; it can outlive the parent and keep the underlying allocation alive after accounting drops. This remains a memory-accounting limitation. |
| 5. Sampler failure retains an idle host buffer | Reproduced and fixed with stop-then-reconcile cleanup. |
| 6. Context exception masks original error and leaves descriptors open | Reproduced for a borrowed page and fixed. Exceptional context exit stops the pager, closes descriptors, and retains leased bytes until acknowledged GPU completion. Ordinary `close()` still refuses outstanding work. |
| 7. Evicted hint omitted from waste | The reported counter is named `invalidated_hint_bytes` and was intentionally narrower than total prefetch waste. A total-waste metric for eviction and other discard paths remains open; do not use this counter as total waste. |
| 8. Trace metrics unconstrained | Successful traces now reject swap growth and peaks below declared live prefetch bytes. `logical_expert_read_bytes` and physical footprint remain producer claims, requiring independent instrumentation. |
| 9. Page coordinate types unchecked | Confirmed and fixed for catalog geometry, page keys, PLE global rows, and scheduler spans. |
| 10. Malformed observation leaves pager open | Reproduced and fixed; malformed samples stop the pager. |
| 11. Loose receipt and missing index shards | Confirmed and fixed: completion must be boolean `true`, and index shard names must equal manifest shard names. This does not replace a repeat digest check. |
| 12. Repeat demand and cancellation trace cases | Confirmed and fixed in trace schema v0.3 with `demand_finish` and cancellation cleanup. |

## Open gates and risks

- The receipt is self-attested in a writable checkpoint directory. The catalog rechecks sizes and headers but not complete file digests, and it does not bind later I/O to a file identity token. Repeat digest verification and an identity-bound runtime adapter are required before real checkpoint reads. Treat replacement or tampering between admission and use as an unresolved security risk.
- Trace events, PLE key derivation, byte sizes, process footprint, swap, and GPU completion are self-reported until an instrumented adapter and independent observation bind them to real operations. Trace validation alone cannot authorize model execution.
- The fixture counts retained `bytearray` payloads, not all host allocations or child views. A production adapter needs measured process and MLX allocations plus explicit buffer ownership through device completion.
- No checkpoint Python, inference, package install, benchmark, or full-model load occurred in this review-remediation slice. The 64 GiB host remains unsuitable for the stock full-model load.
