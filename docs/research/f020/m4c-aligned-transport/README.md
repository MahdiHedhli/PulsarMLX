# Buffered file windows for a sealed expert role

`read_into::aligned_transport::WindowPlan::new(&plan, role, alignment)` borrows one admitted expert plan, its retained descriptors and the three original component ranges. The only supported alignments are 4,096 and 16,384 bytes. The binding digest includes the metadata snapshot, expert request, role, alignment and descriptor stamps. A serialized receipt grants no read authority.

```rust,ignore
let windows = WindowPlan::new(&expert_plan, ExpertRole::Gate, 4096)?;
let budget = windows.minimum_reservation();
let mut scratch = Scratch::new(&windows, budget)?;
let destination = PlaneDestination::new(weights, scales, biases, expected_sha256);
let (filled, transport) = windows
    .read(Mode::BufferedAlignedWindow, &mut scratch, destination, budget)
    .map_err(|failure| failure.cause)?
    .into_parts();
let verified = filled.into_receipt();
```

`BufferedExact` reads the original components into their exact destinations. `BufferedAlignedWindow` reads each in-file covering window into an aligned interior slice and copies only the logical component. Header or sibling bytes have no payload authority. When rounding would cross EOF, one whole direct component read is classified as `buffered-edge-exact`. A rounded-end overflow refuses the plan. Overlapping requests count independently. Even an already aligned component pays its explicit copy in the window mode.

For a largest candidate request of `C` bytes, both modes initially allocate `C + alignment - 1` bytes. A retained scratch allocation can serve another role when its actual aligned capacity suffices. The ledger charges its complete backing plus 65,536 control bytes. It records alignment head slack, usable capacity and unused tail after the largest active window. Borrowed descriptor metadata and the caller's destination storage stay outside the additional reservation. The control charge covers the retained receipt and expected-hash capacities, including UTF-8 strings and their compact JSON representation. Transport serialization is checked before any payload I/O and bounded at 16,384 bytes. These bounds describe the transport's logical reservation.

The original fill helper verifies destination lengths, expected hashes and retained descriptor stamps. A successful capability keeps the destination exclusively borrowed until consumed. Failures return the original cause with observed effects. Earlier reads, copies and partial destination writes can survive a later failure. A failed exact-at request has an unknown returned length. An unattempted request also has a null length, distinguished by the attempt flag. Logical attempts count entry to the fill closure, including a binding refusal before any raw read. Transfers count component requests. Physical bytes, syscall counts and cache state remain unobserved.

The frozen [corpus](corpus.json) binds 6,161 ordered cases and 19 named limit cases. The [host evidence](host-evidence.json) records the exact test populations, both builds, Python versions, and observed fixture totals. The private return retains per-component success and failure records. These experiments establish payload equivalence and bounds for synthetic buffered host reads. Copying remains the shipping default. Platform cache policy, native and physical qualification, representative traces, and performance measurement require separate decisions.
