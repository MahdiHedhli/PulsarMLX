# Fixed descriptor policy for sealed expert windows

A prepared role borrows its original window plan and owns one freshly opened read-only file description per distinct retained shard object. On macOS the helper opens each name under the retained root, compares the regular file's device, inode, length, modification time and change time at nanosecond precision, then requests the selected setting once. Setup records the actual command, integer argument, return and errno on error. A refusal releases the files already owned. File destruction does not expose the kernel close result.

`PreparedPolicy::prepare` takes the sealed plan, a `Policy` and an additional budget. The requested alignment must equal the supported runtime page size. `PreparedPolicy::minimum_budget` includes the original scratch/control reservation and 65,536 policy-control bytes. Larger retained scratch stays charged in full. The caller retains ownership of logical destination storage. Compact policy reports have a 32,768-byte limit. `PolicyReceipt::encoded_bytes` measures the report.

```rust,ignore
let budget = PreparedPolicy::minimum_budget(&window);
let mut scratch = Scratch::new(&window, budget)?;
let prepared = PreparedPolicy::prepare(&window, Policy::NoCacheRequested, budget)?;
let (filled, transfer) = prepared.read(&mut scratch, destination, budget)?.into_parts();
let verified = filled.into_receipt();
let retired = prepared.retire();
```

Both fixed settings use aligned windows and explicit bounce copies. In-file requests read on the prepared descriptor. An EOF-crossing window uses one whole logical read on the original buffered descriptor. This route never changes either descriptor's policy. All reads retain the original exact-fill hash, stamp, counter and destination ownership checks. Setup observations survive failed later reads. An error from an attempted exact-at read leaves the partial byte count unknown. A completed copy remains charged when a later check refuses publication.

A successful setter establishes acceptance of a per-open request. High-level request alignment says nothing about the number or geometry of internal system calls. Physical cache bypass, device traffic, physical memory and performance remain unobserved. Source support in this experiment applies to CPU reads on admitted synthetic fixtures. Copying remains the shipping default.

The [frozen matrix](matrix.json) specifies the finite role and failure populations. The [host evidence](host-evidence.json) records both builds, independent Python checks, setter counts and the original buffered regression population.
