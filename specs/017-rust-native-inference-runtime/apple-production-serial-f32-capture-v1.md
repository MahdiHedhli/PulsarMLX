# F017 Apple Production Serial-F32 Capture Surface v1

## Decision

The representative Apple production surface is Rust orchestration with the
pinned MLX C matvec primitive for decoded binary32 projections and explicit
Rust binary32 scalar operations for reductions, routing, activations,
aggregation, FFN composition, and residual addition. The authoritative entry
point is `apple_serial_f32::run_apple_serial_f32`; the future process entry is
`f017-apple-serial-f32-capture`. This is an Apple production implementation,
not an R9/R10 qualification adapter. The production module has no import of
`layer_qualification` or any proof/reference aggregate/FFN helper.

The implementation is intentionally backend-specific. Projection bytes are
defined by `mlx_matvec` in MLX native 0.32.1 / mlx-c 0.6.0_4 on the pinned Apple
Metal environment. The MLX reduction tree and contraction choices are not
claimed portable across versions, devices, or compilers. They are resolved for
this program by exact environment and API binding and are compared numerically
under the already-frozen pre-execution tolerances. Scalar stages are ordered
source operations with explicit binary32 boundaries.

The native MLX libraries are installed at the default Homebrew prefixes and are
bound by exact version, header, and dylib hashes in the architecture and runtime
contracts. Portable compilation remains synthetic-only and cannot pass the
production gate. Execution preparation requires a release build with
`PULSAR_REQUIRE_NATIVE_MLX=1` plus exact read-back of the bound libraries and
the inert authorization chain before any approval or GO token may exist.

## End-to-end graph

`S0 → attention RMSNorm → Q-A → Q-rank RMSNorm → Q-B → RoPE → KV-A →
compressed-KV RMSNorm → per-head K-B → serial score → one-position softmax →
V-B → attention output → binary32 S1 → FFN RMSNorm → router matvec → binary32
sigmoid+bias → stable top-8 → binary32 selected-probability normalization →
eight gate/up → binary32 SiLU/product/route scaling → down → slot-0-to-7
binary32 aggregate → shared gate/up/SiLU/product/down → one binary32 FFN add →
one binary32 S2 residual add`.

The accepted M1-F0 representative event is a one-position surface. Softmax is
still implemented as max, subtract, scalar `expf`-equivalent Rust `f32::exp`,
serial sum, and serial division; each head receives a one-element list and
therefore produces exactly one. RoPE uses binary32 base/exponent construction,
Rust `f32::powf/sin/cos`, adjacent pairs, and one binary32 rounding after each
source operation. This Apple surface may intentionally differ from CUDA
fast-math and from the closed binary64 proof/reference surface.

## Projection and decoder surface

The runner accepts only fixed package roles. It opens each retained input once
with `O_NOFOLLOW`, checks regular/non-symlink/single-link/read-only policy,
hashes the same descriptor, decodes it, and verifies finite output. The exact
decoders are bound for F32_LE, Q4_K, Q5_K, Q6_K, Q8_0, IQ2_XXS, and IQ3_XXS.
Decoded binary32 matrices are imported into MLX and passed to `mlx_matvec`.
There is no checkpoint, shard, alternate decoder, BLAS, CPU projection, or GPU
fallback interface.

## Capture

Every canonical stage ID is emitted exactly once. Projection capture occurs
after synchronous MLX evaluation and host copy; scalar capture is an immutable
copy of the already-produced vector. Capture does not call a numerical helper,
change operand order, or generate a second result. Canonical serialization is
contiguous little-endian binary32. Each file is created no-replace, mode 0400,
fsynced, hashed, and listed in a final manifest. The future release uses a fixed
capture root and refuses overwrite.

## RN1 and accounting

Wrapper v2 creates the fixed attempt root with exclusive `mkdir`, durably
writes an invocation-owned `owner.json`, and only then writes durable
`attempt-start.json`. The attempt remains consumed after that point. An
exception may terminalize only when the current invocation's exact owner hash
still matches. Neither the wrapper nor terminalizer can repair another
invocation. The terminalizer derives consumed reads from receipt files,
cross-checks `terminal.consumed_reads`, and rejects orphan/inventory drift.
`terminal.json` is never sole accounting authority.

The event is retained-only and starts/ends at ledger 175. Any future advancing
real-payload event must bank its result, receipts, and receipt-derived master
ledger update in the same commit. Schema-based discovery, strict integer
typing, duplicate-key rejection, and strict typed bound-field resolution are
mandatory.

## Recovery and authorization

No live approval or token exists. The two-stage immutable chain is code bytes
→ code manifest → release → later independent review/approval → one machine-
local token. A token cannot authorize different code. Wrapper v1 is an
executable tombstone.

Partial roots are never automatically cleared. The RN3 procedure requires
inventory and owner hash validation, terminal reconciliation, operator
adjudication, and an append-only clearing receipt. Any durable start forbids a
retry even if output is absent.

## Determinism

The later qualification uses ten fresh processes on one pinned machine and
toolchain. Exact stage bytes are required across those ten runs on that pinned
environment. This implementation-specific byte reproducibility is separate
from semantic comparison to the closed proof/reference outputs and from
cross-hardware portability; neither broader claim is implied.

## Stop boundary

This phase performs no production-equivalence comparison, creates no approval,
and creates no GO token. `CHECKPOINT_ACCESS_REQUIRED: NO`. The next safe action
is a separate approval/readiness phase that verifies the pinned MLX runtime,
resolves real machine-local package paths, independently approves the release,
and only then decides whether to mint one token.
