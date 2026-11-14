# Copied host residency

`residency::CopiedResidency` owns one `BoundedSource` and exactly two complete, initialized expert tuples. A serial executor can keep this immutable weight cache between successful or failed steps. Generation position, tokens, KV state, activations and returned outputs belong to other owners.

## Admission and use

1. Open a bounded synthetic checkpoint through the retained-descriptor reader. Supply `ContentAuthority` with the admitted checkpoint name, metadata SHA-256, independent content identity and one `TupleHashes` array per expert. Hashes are 32-byte values. Use `parse_hash` for canonical hexadecimal input.
2. Pass a declared routed layer and `ExpertRequest` class to `CopiedResidency::new`, together with the available logical envelope and required executor workspace. The reader validates the three distinct module names, expert count, D/H, per-role bits, group size, dtypes, shapes and component lengths. The constructor checks rank before cloning tensor shapes, validates plans for every admitted expert, and allocates the slots after memory admission.
3. Obtain a `Demand` for each routed key. Its digest binds the layer, independent content identity, all nine expected hashes and serialized sealed plan. That plan includes the checkpoint, metadata snapshot, complete request, roles, module names, shard/tensor names and byte ranges. A binding can be compared across requests. It cannot change a key's admitted content.
4. Call `consume(&demand, cancelled, consumer)` with 1–64 ordered occurrences. The consumer receives a `TupleView` with nine borrowed slices, expected hashes, key, slot and occupancy generation. Role order is gate/up/down. Component order is packed U32 weights, BF16 scales and BF16 biases. Complete all host use before the callback returns. Safe borrowing prevents a slice outliving its lease.
5. Call `finish()` during executor cleanup. The executor separately releases its staged demand and output on every path. Call `quarantine()` if external cleanup cannot establish ownership. A quarantined cache rejects demand and retains its standing charge until destruction.

Before any reads or mutation, the cache validates the entire demand against its immutable binding table. Each maximal contiguous wave contains at most two distinct identities. The cache leases all current hits before assigning misses in first-occurrence order. Free slots come first. LRU uses successful consumer occurrences, with lowest slot ID breaking a tie. A future wave cannot reserve a slot in advance. Private capabilities bind owner, slot, generation, complete demand and lease epoch. Generation and epoch exhaustion refuse before reuse.

On a miss, the cache invalidates any victim and uses `ExpertPlan::read_plane_into` directly into the selected slot. It consumes and checks each receipt. Full success, including the final cancellation and source checks, publishes one `CompressedResident` table entry. Hits revalidate descriptor stamps before exposure. Synchronous read errors retain attempted I/O counters. A failed fill returns the slot to Free and withholds its bytes. A wave error releases acquired leases and retains completed entries. Uncertain cleanup preserves the primary and cleanup errors and quarantines the cache. A callback unwind also quarantines the owner.

`stats()` counts complete fills, occurrences consumed from residency, evictions and successful consumptions. `read_calls()` and `requested_bytes()` are the sealed source's original attempt counters. For the cold demand `A B A C B A`, the waves are `[A B A] [C B] [A]`. B stays protected in the second wave. Four fills read 36 components. Two resident occurrences add zero reads.

## Memory accounting

`working_bytes()` returns the stored constant `2*S + M + C + X`. Charge this amount once through the host executor's existing coordinator budget. Keep packed weights out of the eagerly loaded request inputs. The coordinator continues to charge its own activations, scratch, output and token history.

- **S** is the sum of nine checked lengths in one tuple, positive and at most 32 MiB. Each initialized vector has exactly its admitted capacity. Both slots stay allocated even at zero occupancy. `resident_bytes()` reports the occupied tuple payload.
- **M** is the source's allocation-free logical metadata ledger, limited to 24 MiB. It includes the inline owner, identity and root names, shard provenance/headers/file options, both copies of tensor records and names/shapes, header metadata, index map, parsed overrides, retained descriptors, and the full JSON configuration. JSON containers charge the inline child entries and recursively charge child strings, keys and containers to depth 64. The root value is already inline. Metadata I/O bytes are separate.
- **C** reserves 1 MiB for cache control. Admission checks a conservative bound of 64 KiB of fixed bookkeeping, 96 bounded name buffers of maximum name length plus 32 bytes, and the actual binding-vector capacity times the fixed binding size. At most one plan and one role receipt are needed at a time. Waves keep two lease records on the stack. Input demand is borrowed. No request-sized payload staging tuple is allocated.
- **X** reserves 64 KiB for additional executor workspace. Executors must bound their own transient payload with `check_workspace` and account for request-owned buffers through the coordinator. Idle, error and quarantine retain the same W.

The ledger excludes allocator rounding, hidden spare capacity of inherited containers, tree-node layout, parser temporaries, OS/driver state and process RSS. Source parsing precedes cache admission. The bound concerns logical retained payload.

## Attachment boundary

The host integration fixture runs the real step coordinator over generated activations and computes an owned digest from every component of every demand occurrence. Independent fixture bytes and the allocating reader verify storage and order. A later copied native importer still requires an owner-thread MLP consumer, copied tensor lifetimes through evaluation/completion, cancellation and native numerical qualification. The current shipping path uses copying. The completed Studio005 M1b result is inconclusive and its timing claim is spent.

## Opt-in host staging

Rust022 adds `residency::overlap::StagedResidency`. Construct it from an admitted `CopiedResidency`, a scheduling mode and an available byte budget. The wrapper owns two separate raw tuple banks and uses the original cache’s two resident slots. Both staged modes read the same admitted component ranges into the banks and explicitly copy verified bytes into the resident cache. Direct `CopiedResidency::consume` remains the default.

`Mode::Overlap` can submit the immediately following wave of the current call before the owner consumes the present wave. `Mode::Serial` submits after the current leases have retired. Each admitted call uses one joined I/O thread. Consumers run on the caller and may borrow non-Send state. Use `working_bytes()`, `ledger()`, `activity()` and `events()` to inspect the standing charge, real read/copy effects and latest admitted call’s bounded journal. [Host staging mechanism, controls and limits](../../docs/research/f020/m4b-host-staging/README.md)
