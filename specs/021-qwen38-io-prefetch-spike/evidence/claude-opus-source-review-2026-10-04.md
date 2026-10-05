# Claude Opus source review, frozen Qwen3.8 synthetic pager

Status: external model report, locally triaged in [source-review-disposition-2026-10-04.md](source-review-disposition-2026-10-04.md). Findings below remain untrusted review evidence, not instructions or proof of runtime safety.

- Model: `claude-opus-5-5-medium` through `agy`
- Frozen source commit: `11a4246464fd55f5ce95f287fdee598a1d6a707d`
- Input scope: [independent-review-packet.md](../independent-review-packet.md), 11 verified text files, 94,785 bytes
- Review conversation ID: `10967172-059c-43a9-8e44-f38eeb2dce03`
- CLI status: `SUCCESS`; turns: 1
- No checkpoint weights or bundled checkpoint Python were included. No local code was changed by the reviewer.

## Raw reviewer report

# Review of frozen commit 11a4246 (Qwen3.8 synthetic pager slice)

I reviewed only the text you supplied. I used no tools and executed nothing. Every trigger below comes from tracing the code by hand, not from running it. "Bug" means the code breaks a rule stated in the spec or plan. "Limitation" means the design is narrower than its claim but behaves as written.

## Ranked findings

### 1. Bug (high): an in-flight hint can stop a demand that would otherwise fit
**Where:** `qwen38_bounded_pager.py:221-224` (with `_evict_for`, `183-199`)

- **Trigger:** use `Limits(96, 96, 2, 3, 3, 480, 160)` with the 48-byte synthetic experts.
  1. `demand(E0)`, `complete_io(next_io())`. E0 is now an active demand.
  2. `hint(E1)`, then `t = next_io()`. This reserves 48 bytes of staging.
  3. `demand(E2)`, then `next_io()`.
  - The staging check passes (48 + 48 ≤ 96). Inside `_evict_for`, reserved space is 0 + 48 + 48 = 96, and no page can be evicted, so it calls `_stop("demand page exceeds available weight/staging budget")`.
  - Without the hint, E2 would fit (48 + 48 ≤ 96). Once `t` completes, E1 becomes an evictable hint page.
- **Impact:** a guessed read turns into a fatal stop for real model demand. This breaks demand priority (spec requirement 3/4).
- **Fix:** when a demand cannot be admitted and some pending ticket's key is not in `actual_demands`, return `None` and wait. Only call `_stop` when no reclaimable reservation exists. Add this exact sequence as a test.

### 2. Bug (high, trace contract): demand keys are not tied to route events
**Where:** `qwen38_prefetch_trace_contract.py:80-87, 95-102, 129-138`

- **Trigger:** this trace validates and reports 32 useful bytes:
  - `route selected=[2] executed=[2]`
  - `hint "L1:E5"`, `prefetch_start bytes=32`, `prefetch_io_done`
  - `demand_queued "L1:E5"`, `demand_start`, `prefetch_use`, `prefetch_gpu_done`, `buffer_release`

  Expert E5 was never routed.
- **Impact:** the validator cannot detect a demand that came from a hint. Spec requirement 2 ("Only actual model demand…") goes unchecked. Route events carry no layer or token, so they cannot be matched to keys at all.
- **Fix:** add `layer` (and a token/step index) to `route`. Require every `demand_queued` key to be in the set of routed `(layer, expert)` pairs, or to be a PLE row produced by a declared lookup event.

### 3. Bug (medium, trace contract): demand reads are invisible, so priority and late-byte accounting can contradict the scheduler
**Where:** `trace_contract.py:99-120`

- **Trigger A:** `demand_queued K`, `demand_start K` (no buffer, so a demand read is in flight), `hint J`, `prefetch_start J` → accepted.
  - The pager would block this: `waiting_on_io` at `pager.py:206-209` includes in-flight demand tickets.
- **Trigger B:** `demand_queued K`, `demand_start K`, `hint K`, `prefetch_start K`, `io_done`, `prefetch_use` → accepted as **late** prefetch.
  - The pager rejects a hint for a key that is already demanded (`pager.py:158`).
- **Impact:** priority violations pass, and demand-path reads get relabelled as late prefetch bytes.
- **Fix:** add `demand_io_start` / `demand_io_done` events. Block `prefetch_start` while any started demand lacks a completed read. Reject `hint` for keys in `started_demands`.

### 4. Bug (medium): `release()` drops the lease before releasing the views
**Where:** `qwen38_fixture_io.py:179-184`

- **Trigger:** the caller holds a buffer export of a segment, for example `a = np.frombuffer(borrow.segments[t], np.uint8)`, then calls `gpu_done` and `store.release(borrow)`.
  - `pager.release` succeeds, the lease is gone and the page can be evicted.
  - `view.release()` then raises `BufferError`. `segments.clear()` and `_reconcile()` are skipped.
- **Impact:** the page is unpinned while caller-held views are still alive, and the error surfaces after the state change instead of before it.
- **Fix:** release all views first. If any release fails, raise and keep the lease. Call `pager.release` only after every view is released, then reconcile.

### 5. Bug (medium): a failed observation callback leaves host buffers that the pager has already drained
**Where:** `fixture_io.py:101-106` (the first `_observe` at `139` is outside any `try`)

- **Trigger:** `demand(E1)`, `pump_one()` succeeds. On the next `pump_one()` the sampler raises.
  - The code runs `_reconcile()` first, then `pager.stop()`, which drains E1 and raises `PagerStop`.
  - No reconcile runs after the stop. `store.buffers` still holds 48 bytes while `pager.resident_bytes == 0`.
- **Fix:** run `pager.stop(...)` inside `try/finally: self._reconcile()`. Do the same for the reconcile-mismatch stop at line 94.

### 6. Bug (medium-low): `__exit__` with an outstanding lease hides the original exception and leaks file descriptors
**Where:** `fixture_io.py:186-190, 204-205`

- **Trigger:** inside `with FixturePageStore(...)`, call `borrow(E1)` and then raise `RuntimeError`.
  - `close()` raises `PagerProtocolError("cannot close…")`.
  - File descriptors are never closed, the pager stays open, and the original error appears only as `__context__`.
- **Fix:** close file descriptors and stop the pager unconditionally; the buffers don't need them. Defer only the dropping of buffers for leased pages. Don't raise from `__exit__` when an exception is already propagating.

### 7. Bug (medium-low, accounting): evicted hint pages that were never demanded are not counted as waste
**Where:** `pager.py:196-198`

- **Trigger:** the existing test `test_idle_resident_page_is_evicted_for_demand` (`test_qwen38_bounded_pager.py:140-153`). Hint page E0 is evicted and `invalidated_hint_bytes` stays at 0.
- **Impact:** wasted prefetch bytes are under-reported. Hints can also evict other hint pages (thrashing) without any trace of it.
- **Fix:** in `_evict_for`, add the size to `hint_waste_bytes` when the victim is in `hint_resident`.

### 8. Bug (medium-low, trace contract): memory and stop metrics are unconstrained
**Where:** `trace_contract.py:158-175`

- **Trigger:** a valid trace with `swap_delta_bytes = 2**30`, `peak_footprint_bytes = 0` and any `logical_expert_read_bytes` still validates.
- **Impact:** a trace that breaks the swap stop rule (spec requirement 6) is accepted, and peak memory can be lower than the prefetch bytes actually held.
- **Fix:**
  - Require `swap_delta_bytes == 0`, or mark the trace as a stopped run.
  - Require `peak_footprint_bytes >= max(used_bytes)`.
  - Require `logical_expert_read_bytes >=` the admitted bytes.

### 9. Bug (low): page-key fields are not type-checked
**Where:** `qwen38_page_catalog.py:122-139, 147-157`; `pager.py:118-122`

- **Trigger:** on the synthetic catalog, `page(PageKey("ple",1,0,0.5))` gives `start=2.0` and returns float-offset spans that overlap blocks 0 and 1.
  - The pager accepts this as a separate key and counts the overlapping bytes twice.
  - The fixture rejects it only because of `type(span.offset) is not int` (`fixture_io.py:117`).
  - `ple_rows_per_page` and `global_row` are unchecked in the same way.
- **Fix:** require `type(x) is int` for `layer`, `index`, `block`, `global_row` and `ple_rows_per_page`. Have `_spec` reject non-int offsets and lengths.

### 10. Bug (low): a malformed observation leaves the pager open
**Where:** `pager.py:127-130`

- **Trigger:** the sampler returns `None`. Building the tuple raises `AttributeError` before `_stop`.
- **Impact:** on the pre-read path (`fixture_io.py:139`) the pager stays open. That contradicts the "observation failure stops the pager" claim.
- **Fix:** add an `isinstance(sample, Observation)` check that calls `_stop` on failure.

### 11. Low-severity catalog and admission gaps
- **Receipt check is loose:** `catalog.py:188` accepts any truthy `complete` value. The static admission script requires `is True`.
- **Missing shards are ignored:** `catalog.py:207-209` doesn't require the index's shard set to equal the manifest's. A manifest shard missing from the index is silently skipped. `admit_qwen38_static.py:143` does check this, but the catalog can run without it.
- **Fix:** match both checks.

### 12. Over-strict (rejects valid traces, low)
- `trace_contract.py:96-97` allows one demand per key per request, but real decode demands the same expert many times.
- `trace_contract.py:89-93, 155`: a demand queued before `cancel` can never validate, because cancel doesn't clear `pending_demands`.

## Answers to the specific questions

### Q1: Pager rules, cross-request reuse and late completion
I found no bug where a later request adopts an in-flight read:
- `cancel_request` marks every pending key as cancelled.
- `_accepting_work` blocks new demands and hints until the pending reads and leases drain.
- A late `complete_io` after a cancel or stop goes down the discard branch.
- A stale ticket is rejected as unmatched.

The admission bound (fixed + resident + staging ≤ `weight_bytes`) holds as an invariant. Limitations:
- **No request identity.** Pages that were demanded and completed survive cancellation and are reused by the next request without re-checking the file.
- **Head-of-line blocking.** A hint at the front of the queue that doesn't fit blocks every hint behind it.
- **Draining raises.** `pump_one` raises `PagerProtocolError` during drain instead of returning `None` (`pager.py:203`).

### Q2: Catalog arithmetic and file identity
The span arithmetic is correct for contiguous row-major first-axis slices.

The plan's figures are mutually consistent:
- Experts: 24,576 × 2,764,800 bytes.
- PLE: at most 128 × 306 × 819,200 bytes.
- Plus the fixed and vision tensor bytes.
- That comes within the 98.924 GiB checkpoint size only if PLE tail blocks are short and no expert projection is 8-bit. This is a consistency check, not proof.

Catalog-side limitations:
- `PageSpec` doesn't carry dtype, shape or quantization bits. The 498 8-bit/group-64 and 128 4-bit/group-32 overrides live only in `config.json`.
- Nothing checks that the shapes of `scales`/`biases` match the weight shape and group size.
- The PLE global-row convention is unverified.

Receipt-side limitations (separate from catalog bugs):
- The receipt is a self-attested JSON file in the same writable directory.
- The catalog re-checks only file size and the final path component for symlinks.
- There is no digest re-verification and no time-of-check/time-of-use binding.
- No file identity token passes from the catalog to the I/O layer. The fixture's `file_sizes` come from the caller, not the catalog.

### Q3: Fixture buffers and byte counters
Each retained page is one `bytearray` in `self.buffers`. The lease is pure bookkeeping, because buffers are never reused or mutated. Places where the counters diverge from real process memory:
- **Derived views outlive the counter.** Views derived from a segment (`fixture_io.py:172`), or held by the caller, keep the `bytearray` alive after eviction, cancel, stop or close. The dictionary drop at lines 90-92 lowers `retained_host_buffer_bytes`, but the memory is not freed.
- **Tracebacks pin failed reads.** On a failed read, the traceback frame keeps `buffer` (line 147) and `target` (line 123) alive while the exception exists, for example inside `assertRaises`.
- **Finding 5.** Buffers stay in the dictionary after a stop triggered by the sampler.
- **Finding 4.** Views stay live after the lease is released.
- **Overhead outside the counter:** `memoryview`/`bytearray` object overhead, allocator slack, the OS page cache and kernel buffering.
- **Resident pages are never re-checked** against the file on `borrow`.

### Q4: Trace validator
It can accept sequences that contradict the scheduler's priority rule (finding 3), route authority (finding 2) and the memory stop rule (finding 8). The `prefetch_start` byte counts are self-declared and not tied to catalog page sizes. Buffers are tracked per key string, with no lease IDs. Within that model, useful + late + wasted bytes always sum to admitted bytes.

## Still unproven
Synthetic tests and this review don't establish any of the following:
- That real checkpoint reads return the bytes the headers describe, or that spans and receipt survive a repeat digest check.
- That `complete_io` and `mark_gpu_done` correspond to real MLX or Metal completion fences, or that MLX copies or keeps buffers.
- That process footprint, headroom, swap and pressure are sampled correctly on macOS. Sampling between allocations is still not a hard cap.
- Numerical parity: dequantization semantics, the PLE hash/seed and row convention, and layer-wise and logit tolerances.
- Physical SSD reads, page-cache effects and any throughput or latency number.
