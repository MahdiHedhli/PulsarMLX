# F020 bounded expert-range admission

Host storage admission and ownership passed on Studio at source commit
`5973a176412741635ca07f3e924f944f3382fe81`. Independent static source review
accepted that exact source/tree/package with zero blockers before the first real
metadata-only plan. This is a storage and metadata slice, with no real payload,
R1, native or GPU numerical execution. The existing composition branch remains
at `79e5de15`, with [required CI passing](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/37163159678).
Main has not been merged.

The new host-only crate caps config/index at 4 MiB each, one header at 2 MiB,
all headers at 16 MiB, shard count at 32, and one selected expert tuple at 32 MiB.
It reuses the existing descriptor admission, strict metadata catalog and affine
selection arithmetic. It does not use the synthetic whole-checkpoint loader,
whole-shard hashes, mmap or MLX. A sealed plan borrows its exact source; loaded
packed buffers are immutable and outlive the source. Declared semantic roles
belong to the model binder; storage validates their exact module/recipe/geometry.
Inherited computational code and fixtures are unchanged. Workspace membership
and lockfile wiring are changed to add the new crate; this is a separate package
from the previously qualified composition source.

All 17 targeted tests passed with zero sparse skips, including default and mixed
recipes across all experts, packed byte fidelity, source-drop/move lifetime,
budget/path/header/recipe/index refusals, timestamp-visible mutation and truncated
descriptor refusals. The sparse control advertised an 8,589,956,259-byte file,
occupied 40,960 bytes, and requested only 6,912 payload bytes in nine reads.
Large sparse fixtures first probe support with a bounded 16 MiB file. Mutation
tests set distinct timestamps and do not depend on a sleep. Scoped formatting
and strict Clippy passed. The host workspace check and test passed; exact counts,
exclusions and output hashes are in the evidence receipt.

The admitted real metadata-only plan read 790,848 bytes of config/index/header
data and zero payload bytes. It binds layer 3 / expert 0 from the GLM checkpoint:

| Role | Module suffix | Logical shape | Recipe |
| --- | --- | --- | --- |
| Gate | `switch_mlp.gate_proj` | 2048 × 4096 | default 4-bit, group 64, BF16 metadata |
| Up | `switch_mlp.up_proj` | 2048 × 4096 | default 4-bit, group 64, BF16 metadata |
| Down | `switch_mlp.down_proj` | 4096 × 2048 | default 4-bit, group 64, BF16 metadata |

The nine selected ranges total 14,155,776 bytes. They are planned, not loaded.
The complete raw receipt stays in the private Studio audit; the committed
summary contains source and receipt hashes and sanitized observed dimensions.
The metadata identity is scoped to config/index/headers and selected range
descriptions; it is not a whole-checkpoint payload checksum.

Stamp checks detect identity, length and timestamp-visible changes; they are not
an atomic snapshot and do not detect every same-size rewrite within filesystem
timestamp granularity. Selected range hashes identify the captured bytes after a
future bounded load. Read counters count attempts, including failed reads. The
READ-phase OS-failure branch is reviewed but lacks deterministic injection
coverage. The inherited catalog's device-width truncation remains a fail-closed
follow-up. Linux/CUDA execution has not been validated by this Studio result.

## Next gate

Review and perform one bounded selected load, freeze the nine owned range hashes,
then establish independent packed R1 and input/metadata/intermediate-domain
admission before any native execution. The observed real D=4096/H=2048 requires
8,388,608 MACs per projection at M=1. The accepted synthetic population is
D/H=64 or 128 with at most 2^21 MACs per QMM, so a separately reviewed geometry
and MAC-domain extension is required. Keep activation budgets fixed and fail on
inadmissible domains. Do not point the existing synthetic `Source::open` at the
approximately 182 GB checkpoint. No full-model, generation or performance claim
follows from this result.

New branch publication and CI receipts are recorded separately from this frozen
source/evidence snapshot. The source M2 work, model files and published composition
branch remain preserved.
