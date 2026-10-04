# Prospective resource accounting and refusal rules

No measurement claim yet. Data bounds are source/shape-derived; process peak RSS
and MLX allocator counters are measured qualification gates. No set_memory_limit
hard-cap claim is permitted. All failures retain the exact attempt.

## Native bounded data

Fixed selected buffers:14,155,776 bytes; bounded header131,072. Original input
16,384. One staged role:4,718,592. Only one role is staged at once; the temporary
down preflight stage is dropped before the down projection stages its buffers.
Each QMM's public data buffers (imports, exact metadata widening, output):
4,194,304 U32 +524,288 BF16 +1,048,576 F32 metadata +24,576 input/output
=5,791,744 bytes. No dense weight array is requested. M1 selects pinned qmv_fast,
which decodes in registers; the explicit graph has no split-K workspace.
Activation has seven 8192-byte vectors plus two scalar F32 buffers=57,352 bytes.
Host readbacks/JSON rational-independent bit arrays are each bounded by4096
values. Authority documents are <=16MiB each and dropped before snapshot load.

Admission enforces exact dimensions, nine lengths and one-role staging. A
conservative tracked working-data acceptance cap is512MiB, with native allocator
active/peak acceptance cap64MiB and cache disabled. The exact graph data above
fits comfortably but this is not evidence that opaque MLX/runtime overhead does.
Process peak RSS (Darwin getrusage, bytes) must be <=1GiB including working data;
this conservatively bounds separately scoped runtime overhead by1GiB without
subtracting aliased unified-memory buffers. Parent also watches child RSS every
100ms and kills its owned process group on excess or deadline. Polling can
overshoot and is not an instantaneous OS memory limit. Allocator/RSS excess
fails qualification even if the candidate values pass numerical gates.

## Independent reference

Snapshot payload<=14,155,776, header<=131,072; 4096 F32 integer units. Original
BF16 and x domain floors bound integer units to72 and88 bits. Affine integer
sums need at most176 bits, with denominator2^94. G/U/Phi/bounds have at most2048
entries per vector; hidden has2048 pairs on2^-256 lattice. Bh denominators divide
128*(2^24-273)*2^94; the LCM cannot grow without bound across rows. Down products
and sums use fixed dyadic endpoints and <=4096 outputs, never millions of
Fractions. The inherited two LRU caches each cap8192 entries; only<=2048 distinct
G/U pairs are introduced by one selected call. Reference process peak RSS must
be <=256MiB. An external owned-process watchdog enforces a100ms sampled RSS
ceiling and900-second deadline; measured maximum and enforcement scope must be
reported. No hard global RAM guarantee is inferred from a sampled ceiling.

Final review must assess this ledger against exact pinned source and build;
observed native/reference peaks must separately pass before resource compliance
for that particular bounded run can be claimed.
