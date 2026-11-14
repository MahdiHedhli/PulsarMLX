# Known-work host staging

This opt-in path stages expert tuples for the already-admitted call. One owner thread manages the real copied cache, its admission table, and all consumer callbacks. One I/O worker reads through an Arc to the same admitted `BoundedSource`. The source must compile as Send + Sync. Each job moves exclusive ownership of both raw staging banks through a capacity-one request channel. A separate capacity-one channel returns the banks. No worker receives a victim slot, cache lease or numerical consumer.

| Path | Current wave | Immediately following wave |
| --- | --- | --- |
| Direct copied cache | Read into the selected resident victim, then publish | Begin after current leases retire |
| Staged Serial | Read into banks, verify the whole job, then copy into the cache | Submit after successful current consumption and lease release |
| Staged Overlap | Same verified read and explicit copy as Serial | Submit after the current wave is ready and leased, before its callbacks |

A wave contains at most two distinct expert identities. A future job contains only its missing identities in first-occurrence order, with no request across a call boundary. All-hit waves need no reader job. The worker can finish early. The owner checks a completion only at the point its wave can execute. Before installing either tuple, the owner matches the outstanding job exactly, validates every staged role, rehashes all nine components, checks the current descriptors and protects every resident hit. Victim selection then sees the final recency of the preceding successful callbacks. Staging data carries no residency credit.

A ticket binds cache owner, invocation, cancellation epoch, wave, bank index and generation to an exact demand, content commitment, nine lengths and nine hashes. Reader role success requires the unchanged `read_plane_into` receipt and its source, role, range, length, hash and attempt bindings. A successful materialization adds nine logical reads and nine explicit component copies. The inherited direct path adds no staging copies. Activity reports distinguish requested bytes (including failed attempts), verified role/byte totals, actual stage-to-resident copies and issued bytes discarded without installation. None of those counters represents physical storage transactions.

## Standing charge and ownership

Let S be the total of the nine measured component capacities and M the path-sensitive source metadata charge. The inherited charge is two resident tuples, M, the original control allowance and workspace. Direct fill reports that original charge. Both staged modes use the same additional charge:

```text
W_pipeline = W_cache + 2*S + 2 MiB control + 2 MiB requested reader stack
W_executor = W_pipeline + 4 KiB in the test adapter
```

The two raw banks use exactly the admitted component capacities. They move between worker and owner without enlarging the resident cache. The control ledger reserves 64 KiB plus 96 maximum-name buffers (including 32 spare bytes each) for plans, names and receipt checks. Channel, Arc, class and message bookkeeping use another 64 KiB plus eight completion/ticket-set sizes. The latest-call journal reserves 2,048 fixed-size records; each miss can emit at most four transitions. One live serialized report has a 1 MiB allowance. The constructor checks the sum against 2 MiB before allocating banks or spawning. The test adapter independently checks six demand keys, SHA-256 context, output descriptor/payload, request identity and fixed overhead against its 4 KiB ceiling. It supplies the combined charge once to the real coordinator.

The charge persists through idle time and quarantine. A short construction budget refuses before staging allocation. The coordinator’s one-byte-short refusal precedes its input read and any reader request. The worker stack size is a standard-library request. These logical capacities are separate from RSS and elapsed time.

## Failures and shutdown

The reader checks cancellation between roles and bounded state transitions. A cancellation cannot interrupt a synchronous OS read already in progress. The owner drains outstanding work, closes both channel routes and joins before returning to the coordinator. A late completion cannot warm another call. An unsuccessful staging read job preserves prior resident entries. The direct path can already have evicted a victim before its own read fails.

Consumer refusal preserves successful prior consumption. An owner panic quarantines the cache and resumes unwinding only after reader cleanup. A worker panic or invalid completion prevents publication and quarantines the wrapper. Reader or lease cleanup errors are recorded separately from foreground failure. Refusal leaves observed reads and discarded bytes visible even when no generation commit occurred. The external test supervisor watches fault-cleanup markers for five seconds and reaps its own test process if cleanup cannot be observed. The reusable library performs an ordinary join. It makes no bounded OS I/O completion promise.

## Compatibility and host evidence

The inherited `CopiedResidency::new` now stores an Arc. `run` delegates wave boundaries to `split_wave`. `wave` uses the shared hit-protection and consumption routines. `fill` shares victim selection, generation allocation and publication through `begin_fill` and `commit_fill`. `fill_parts` accepts the exact component buffers and a per-verified-role callback. Direct fill uses an empty observer. `residents()` is a read-only slot/recency snapshot. The admission table, source readers, coordinator and Rust021 AdmitAll model retain their original source. The source inventory compares complete old function fragments in addition to protected file hashes.

The frozen workload includes 120 words of lengths one through four over A/B/C. Two call partitions and two copied recipes yield 480 combinations, each compared on all three paths. Six named schedules per recipe add 36 arm cases. Controls also refuse empty and 65-occurrence calls. Each callback checks the original manifest’s nine component hashes. The unchanged Rust021 model independently predicts slot, generation, recency, hit/fill/eviction and read totals. Its existing regression compares against the frozen independent-reference digest. No reference regeneration is needed.

The ordering control uses channels on a reader-side verified role and an active non-Send owner callback. The fault controls retain actual attempted/discarded reads for cancellation, partial component-hash mismatch and retained descriptor drift. A previously accepted low-level injected partial-I/O control runs independently. The coordinator returns an owned hash over fixture activation and consumed bytes, commits once despite a deliberately lost delivery and replays the same retained object with no new worker, read, copy or callback. [Measured host results](host-evidence.json)

This is CPU-only host qualification. Authentic traces remain unadmitted and provenance recovery is closed. Native attachment, end-to-end numerical qualification on the changed cache source and physical overlap benefit need separate decisions. M2 and M3 retain their original copied synthetic scopes. Copying remains the shipping default.
