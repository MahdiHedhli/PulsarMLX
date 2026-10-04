# Research decisions

- Decision: accepted `mlx-expert-ranges::BoundedSource`/`ExpertPlan` selection
  precedes payload access; `OwnedExpertTuple` preserves U32/BF16 bytes and source
  independent ownership. Rationale: sealed authority, checked ranges and recipe
  identity already exist. Alternative: caller-supplied mutable ranges rejected.
  Its stamps identify metadata-visible mutations, not atomic filesystem snapshots.
- Decision: retain exact partial-read semantics from `stream::positional`
  (`ExpertSource`, non-Clone `OwnedSlab`, injected `PositionalRead`). Add bounded
  interrupt exhaustion in fixtures. Alternative: accepting a short read rejected.
  This fixture does not execute or qualify the Rust reader.
- Decision: separate logical bytes, rounded capacity and ledger obligations.
  `stream::residency` labels candidates as logical; `stable_slab` retains allocated
  capacity after release and rounds 128 to 4096 in its source test. Alternative:
  subtracting logical bytes on release would undercount storage.
- Decision: explicit eviction after exclusive owner release, plus pin/in-flight
  guards, inspired by `expert_residency` occupancy generations. No implicit fallback,
  native-ready policy or model-specific expert semantics are imported.
- Decision: pending cancellation requires operation acknowledgement before freeing.
  `apple_lifecycle` provides generation/state vocabulary but queued cancellation
  alone cannot prove a native callback stopped touching bytes. Alternative: immediate
  free on cancel is unsafe. No GPU/lifecycle tests are run.
- Decision: frozen integration v1 defines explicit step envelope and separates
  model/state operations. Storage checks caller-supplied boundaries and returns
  receipts, never commits/reset/advances model state. Real adapter acknowledgement,
  physical allocator and process/Metal memory measurements remain open.

Read source set: CONTRIBUTING.md; constitution; catalog lib/checkpoint read
interfaces and catalog contract; mlx-expert-ranges/src/lib.rs; stream/src/
{positional,residency,expert_residency,stable_slab,apple_lifecycle}.rs.
No source inspection opened real checkpoint or snapshot data. All unknowns for
synthetic design resolved; production measurements remain dependencies.
