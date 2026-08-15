# F017 Dense-Prefix and Decoded-Reuse Internal Review

## Scope and phase controls

This review covers checkpoint-free preparation only. The reviewed starting authority is
`8031020f2e9480712ff185a53b2e565d25dc6a24`; the stale unpublished `dd52d38`
identifier is explicitly non-authoritative. No checkpoint payload was read, and the
cumulative ledger remains 57.

## A. Decoded reuse

- The v2 reuse contract binds checkpoint, catalog, map, the ordered tensor allowlist,
  packed and decoded identities, decoder contracts, canonical representation, creation
  tooling, read-only leases, and before/after hashes.
- Relocation before use preserves content identity; relocation after execution start,
  mutation, symlink escape, descriptor drift, ordering drift, and writable aliasing fail
  closed.
- Disposition is `MIXED_POLICY`: independent oracle consumers may share the immutable
  canonical byte source; production candidates require a separately hashed import/copy
  with lifecycle evidence; decoder A/B/C qualification never reuses decoded truth.
- The contract is ready only for a later, separate authorization. It does not revive the
  retired random-normal or correlated ladders.

## B. Dense-prefix boundary

- Layers 0–2 are dense; the boundary is honestly named `F017 M1-F(-1) REAL
  DENSE-PREFIX LAYER-3 ENTRY-STATE BOUNDARY` and executes embedding plus all three
  complete dense layers.
- P-MIN `Hello`, token 9703, position 0, and `range_fill([0])` were selected from
  pre-existing accepted provenance without route or hidden-state observation.
- Independent catalog/map reconstruction yields exactly 40 non-router, non-expert,
  non-layer-3, non-output-head tensors in one shard: 1,431,263,232 packed bytes and
  8,504,653,824 decoded-f32 bytes.
- The conservative host floor is 27 GiB. It bounds packed bytes, a complete CPU-decoded
  package, a complete decoded-equivalent MLX residency, a fixed 4 GiB activation/cache/
  workspace reserve, then applies a 1.25 engineering multiplier and GiB ceiling. Runtime
  telemetry must remain below the floor and cannot lower it post-observation.
- The independent Python/NumPy source surface and pre-candidate package contract are
  frozen. The real Tier-B contract is composed from prior R9/R10 bounds, not fitted to a
  future candidate. The real-shaped structured synthetic integration passes 10/10 and is
  explicitly not substituted for the real oracle.

## C. Quantization prerequisites

- Inventory is F32 12, Q8_0 12, Q5_K 12, Q6_K 3, Q4_K 1. F32, Q8_0, and Q5_K have
  reusable real-byte lineage; Q4_K and Q6_K remain real-byte gates.
- Mechanical targets are `token_embd.weight` for Q4_K and
  `blk.0.ffn_down.weight` for Q6_K. One real payload per family is sufficient for the
  format contract when combined with exact A/B/C decoding and synthetic block-pattern
  coverage; later tensors still require their own packed identities.
- The legacy Q6_K Python implementation had a checkpoint-free q2/q3 logical-group bug.
  It was reproduced (118/256 differences), minimally repaired, and now matches both
  independent Python structures and the Rust reference exactly. This does not claim
  real-byte qualification.
- Sequence is Q4_K then Q6_K: embedding is the first computational dependency and the
  accepted Q4_K format lineage can later support M1-G, subject to output tensor identity.
  Each real event remains separately authorized.

## D. Downstream readiness

- Typed config and evidence schemas fail closed on incomplete authorization identities,
  decoder contracts, access budget, oracle package, numerical/dispatch/retention
  contracts, attempt identity, and evidence destination.
- Attempt consumption begins at `EXECUTION_STARTED`, immediately before the first
  authorized payload access; no automatic retry is permitted.
- The retained layer-3 hidden state is canonical private little-endian f32 bytes plus a
  public descriptor, not hash-only evidence.
- The representative M1-F0 handoff binds that exact retained state and forbids alternate
  prompt/hidden substitution. It requires routing v3 membership, H=2, and ID-keyed weight
  qualification, and does not authorize M1-F.
- Route-independent M1-F and M1-G/P1 scaffolds remain prepared and non-authorizing.
  Actual route inventory, real native dispatch count, M1-G output-head identity, and P1
  authorization remain future gates.

## False-pass and historical-risk audit

The synthetic mutation suites cover package mutation, relocation, symlink/path escape,
candidate/oracle aliasing, tensor inventory defects, decoder divergence, incomplete
execution bindings, hidden-state substitution, dispatch reconciliation, and attempt-state
confusion. Historical v1/v2/v3 evidence and the payload ledger are unchanged. No accepted
historical false-PASS path was found.

## Verdict

`GO FOR DENSE-PREFIX PACKAGE ADVERSARIAL REVIEW`
