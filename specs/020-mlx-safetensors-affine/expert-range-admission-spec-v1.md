# F020 bounded expert range admission

This additive slice qualifies host storage admission and ownership before any
real expert numerical execution. The accepted synthetic composition package is
unchanged. No MLX, GPU, full-file hashing, mmap, decompression or dense weight
construction is part of this slice.

A bounded source admits the root and every file with the existing descriptor
based `RootDirectory` mechanism. Read config/index and each shard's prefix and
header under explicit limits: config/index <= 4 MiB each, <= 32 shards, individual
header <= 2 MiB, aggregate shard prefix/header <= 16 MiB. Existing strict catalog
and affine parsers validate duplicate keys, header tiling, dtype, index membership,
shape and checked expert-slice arithmetic. Metadata and descriptor handles remain
owned for the source lifetime. No call to `hash_shards`, `Source::open`, or an
entire-tensor payload read is allowed.

The caller supplies an ordered gate/up/down module binding, E/D/H, one expert
index, each role's expected 4/8-bit recipe and group size 64. The layer that knows
the model owns the semantic role names; this model-neutral storage layer validates
the exact declared module strings, recipes and complementary matrix geometry.
Selection derives all nine ranges from the admitted catalog and resolved affine
triples. A sealed plan borrows its source. No caller can substitute a range or
load the plan from a different source. The complete selected byte sum must be
<= 32 MiB before the first payload allocation or read.

Loading checks descriptor metadata stamps before, during and after reads. It
reads exactly the nine selected contiguous ranges into immutable owned buffers,
retaining packed U32/BF16 bytes without decoding. Ownership survives dropping the
source and moving the returned tuple. The receipt binds the metadata identity,
declared roles, recipes, ranges and each owned range's SHA-256. This identity is
scoped to metadata and selected content; it is not a whole-checkpoint checksum.
Descriptor stamp checks detect identity, length and timestamp-visible changes,
not an atomic filesystem snapshot. Same-size rewrites within filesystem timestamp
granularity and an adversarial writer able to bypass metadata are outside that
detection claim. Selected-range SHA-256 values identify the captured bytes. Before
future candidate execution, freeze the selected owned content and its receipt.

Refuse wrong geometry, recipe, dtype, index rank/range, arithmetic overflow,
budget overflow, path escape/nonregular files, malformed metadata, truncation,
descriptor stamp changes and a failed range read. A failed load returns no tuple.
No fallback may widen the budget, read a whole shard, or infer a missing recipe.

Host tests must exercise packed byte fidelity for every expert and mixed recipe,
source-drop/move lifetime, pre-read budget refusal, symlink/path confinement,
same-size mutation, truncation, malformed header/index/config, expert/geometry/
recipe refusal and a sparse shard with a huge advertised length. The sparse test
must place the selected expert behind a large unrelated gap represented by a
separate tiled tensor, read only selected ranges, and verify the exact byte count.
The test creates sparse storage privately and removes it through ordinary test
fixture lifetime; it does not copy model data.
Large sparse fixtures require a small bounded sparse-support probe first and
report an explicit skip on unsupported filesystems. Deterministic mutation tests
set a distinct modification time rather than depending on clock tick granularity.
The READ-phase OS-error branch is source-reviewed; deterministic mid-read I/O
failure injection is not claimed by this test population.

The first real metadata-only binding targets layer 3's
`language_model.model.layers.3.mlp.switch_mlp.{gate_proj,up_proj,down_proj}`,
expert 0, expected E=288, D=4096, H=2048, default 4-bit/group-64/BF16, as declared
by the local checkpoint config/index. Verify these claims against admitted
headers before acceptance. Record zero payload reads for the metadata census.
Real selected payload loading and native execution remain subsequent gates:
storage review/tests first, then an explicit bounded load, then independent input
domain/R1 admission and exact reviewed native integration. Synthetic success is
not real-model execution support.

Constitution: additive Rust host slice, no shared parser or inherited native
changes; exact source review and targeted plus portable workspace tests; no
credentials, model weights, generated binaries or performance claims committed.
Linux/CUDA execution validation remains unclaimed until supported CI provides it.
