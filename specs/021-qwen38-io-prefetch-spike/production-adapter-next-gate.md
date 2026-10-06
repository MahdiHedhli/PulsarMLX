# Next Qwen production adapter gate

Status: steps 1–3 implemented and accepted on generated fixtures after local source review, 2026-10-06. See the [review/disposition](evidence/adapter-contract-source-review-2026-10-06.md) and [exact source/test evidence](evidence/adapter-contract-validation-2026-10-06.json). The [single local file-admission pass](evidence/bound-admission-local-verification-2026-10-05.md) succeeded and closed its handles. This slice does not authorize another real-checkpoint read, checkpoint Python, dependency installation, MLX execution, numerical runtime probes, inference, benchmarks, external source transmission or push.

## Source contract to implement before execution

The production adapter must accept a live `BoundCheckpoint` and bind its catalog, verified files and lifetime as one session. It must use the bound read API for pageable data, reject closed/poisoned sets, and avoid reopening paths or using a saved JSON result as admission. Keep the fixture-only store's marker and 16 MiB cap intact; create a separate adapter rather than turning that store into a real-checkpoint loader. Fixed text tensor loading also needs an authenticated, bounded route; passing expert/PLE pages alone is insufficient.

The adapter must reserve every owning allocation before I/O or device work: fixed weights, retained pages, pending pages, staging buffers, any host-to-device duplicate and backend retention. A page/segment may be exposed only after its verified read succeeds. On an error, discard the partially filled target, stop new work, drain actual operations, preserve still-used buffers and surface the original failure plus cleanup failures. Logical scheduler counters are one ledger, not proof that all allocations have been released.

Ownership must bind a lease to the original borrow and backend completion object. A synthetic acknowledgement cannot release a real device buffer. A cancellation prevents new requests from adopting old tickets, and draining must cover I/O completion, device completion and all retained host/device owners. Derived Python views were identified as an accounting escape in both source reviews; forbid escaping views at the production API or count their owning allocation until all such views are gone. Select that strategy explicitly before implementing the allocator.

Demand must originate from the model's actual route IDs/weights and PLE lookup rows. Hints can only stage bytes. Bind trace page keys and lengths to the live catalog, and bind I/O and completion events to adapter operations. Useful, late and wasted prefetch bytes must reconcile to all admitted hint bytes, including evictions, cancellation and failure; `invalidated_hint_bytes` alone remains insufficient as a total-waste metric. Logical reads and physical SSD reads need distinct attribution.

## Memory acceptance

| Budget | Required treatment |
| --- | --- |
| 64 GiB physical host | Preserve at least 16 GiB available headroom for macOS and other processes; pressure/swap observations can stop admission earlier. |
| 48 GiB total Qwen process | Reserve prospective allocations and sample independently; stop on overage, unavailable/invalid/stale observations, pressure or swap growth. |
| 40 GiB all resident/in-flight model weights | Includes 5,348,837,400 fixed text bytes; maximum remaining logical expert/PLE allowance is 37,600,835,560 bytes (about 35.02 GiB), before any uncounted ownership cost. |
| 8 GiB other process allocations | Includes runtime, KV, activations and duplicate staging ownership. Never treat this as an extra allowance outside the 48 GiB total. |

Before binding a real allocator, define observation provenance, units, sample timestamps, maximum age and failure behavior. Separate process footprint, MLX allocation/cache, available headroom, pressure, absolute swap and swap delta. Current `Observation` has only process/headroom/swap-delta/pressure fields and no freshness or MLX provenance; extend the contract before claiming an independent production gate. Specify calibration for sampling cadence and allocation overshoot using tiny allocations only after that execution scope is approved. Advisory MLX settings do not replace reservation and observed stops.

## Dependency-ordered acceptance work

| Step | Eligible evidence / completion condition |
| --- | --- |
| 1. Session and ownership interfaces | Source-only implementation and tiny generated fixtures; closed bindings, changed chunks/identity, partial reads, exceptions and close failures stop cleanly without adopting old work. No payload from the real checkpoint. |
| 2. Allocation and observation contract | Tiny synthetic owners and injected observations exercise derived-view retention, duplicate buffers, fixed-weight allowance, stale/missing samples, pressure, swap, boundary budgets and stop/drain behavior. Include a failure before an attempted allocation crosses a reservation. |
| 3. Operation-to-trace binding | Synthetic routes/lookups map to the catalog and exact byte ranges. Reconcile every admitted hint through use, eviction, cancellation or failure; reject forged completions and byte counts. |
| 4. Independent source review | Freeze the exact implementation, fixture tests and proposed execution packet. Use Mahdi's existing Claude/Grok/Gemini review authorization, excluding weights, credentials and unrelated data; honor automatic approval decisions. Retain raw findings, packet digests and local dispositions. |
| 5. Backend and numerical execution gate | Separate approval for a resolved hashed environment and tiny MLX/reference fixtures. Prove actual fences/eviction, affine shapes, converted norm convention, seed 1234, EOS resets, exact DeltaNet q/k L2 normalization and causal sparse prefill across 2048 tokens against independently pinned reference values/tolerances. |
| 6. Real paged correctness gate | Only after earlier evidence and explicit execution authorization: new bound admission plus a no-prefetch paged path, actual memory/swap observations, fixed prompt/token IDs, both stop IDs, routes, layer probes and logits. A stock full-model loader is unsafe on this host. |
| 7. Performance gate | Only after parity and residency pass: controlled cache strata and I/O-only hint comparison; no timing claim based on synthetic events or the digest pass. |

The additive `qwen38_adapter_session.py`, `qwen38_adapter_memory.py` and `qwen38_adapter_trace.py` implement the step 1–3 fixture contracts. The session checks a live catalog/verified-handle binding and authenticated fixture marker, owns fixed and pageable data, rechecks payload identity on acquisition, counts retained exports and duplicates, and emits operation-bound traces with complete hint retirement accounting. The original reviewed modules and 16 MiB fixture boundary are unchanged. The new fixture trace schema is separate from production trace v0.3.

The branch does not supply a Qwen graph, production allocator, real GPU fences, actual independent memory sampler or qualified reference fixtures. Step 4 independent review remains unperformed for this new slice because external transmission is not authorized; the retained audit is explicitly local. Steps 5–7 remain execution gates; their evidence must not be inferred from file hashes or passing trace validators. New source is locally reviewable and requires separate authorization before push.

Constitution check: the proposed work stays additive and Qwen-local, preserves Linux/CUDA and GLM Studio, retains the correctness oracle before optimization, distinguishes synthetic/file/backend evidence, and requires source review and diff/secret/large-file checks before publication.
