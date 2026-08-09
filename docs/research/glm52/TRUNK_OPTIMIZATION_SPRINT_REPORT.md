# PulsarMLX Trunk Optimization Sprint Report

## Status

The post-Feature-016 bounded trunk study is active on branch
`codex/glm52-trunk-optimization`, isolated from the independent Feature 017
checkout. No full-model inference, golden-eight rerun, Feature 018 work, or
direct Metal implementation is part of this study.

## Phase A: whole-matrix read only

**Result: qualified, exact, and insufficient by itself.**

At clean source `bf697033b2288f92f8659f0e8e2b10b04b3e17f6`, the experiment changed
only positional-read granularity. The scalar decoder, row order, contiguous f32
materialization, synchronized MLX matrix construction, and MLX matvec remained
unchanged. Three warm-ups and ten counterbalanced measured samples per mode were
retained.

The complete record is
[`raw/post-f016-trunk-bulk-read-0001.json`](raw/post-f016-trunk-bulk-read-0001.json),
with a generated review table at
[`tables/post-f016-trunk-bulk-read-0001.md`](tables/post-f016-trunk-bulk-read-0001.md).

| Boundary | Read requests | Median total, row (s) | Median total, bulk (s) | Change | Exact f32 bits |
| --- | ---: | ---: | ---: | ---: | --- |
| layer-3 attention output, Q5_K | 6,144 -> 1 | 11.128198 | 11.195878 | +0.608% | yes |
| layer-3 Q-B projection, Q8_0 | 16,384 -> 1 | 2.758256 | 2.761927 | +0.133% | yes |
| layer-8 attention output, Q6_K | 6,144 -> 1 | 48.312671 | 48.097612 | -0.445% | yes |
| layer-8 complete single-position MLA, four 2-D projections | 25,152 -> 4 | 59.777971 | 59.546396 | -0.387% | yes |

The MLA storage median fell from 0.027867 s to 0.007772 s, while scalar decode
remained about 55 s. Request collapse is therefore useful plumbing and exact,
but storage calls were not the material boundary cost in this warm population.
No speedup is inferred from the request-reduction factor.

## Next measured gate

Phase B may retain the qualified whole-matrix read path while changing exactly
one additional variable: decoder implementation. Formats will be selected from
the committed trunk inventory together with these measured scalar costs. Each
NumPy decoder must retain the scalar oracle, exact f32-bit comparison where the
contract permits it, malformed-input tests, real matrices from multiple layers,
and split read/decode/buffer/MLX timings.

No P1 run is admitted until representative MLA and complete transformer-layer
boundaries show a substantial exact-output improvement.

## Phase B1: Q5_K decoder qualification

**Result: exact and admitted for dense-path integration.**

The trunk inventory ranks Q5_K first by exercised compressed bytes: 6.384 GB
across 162 tensors. At clean source `b5ad0059eae9f989c3f24fe7f6208e798fb66a4a`,
whole-matrix NumPy decoding matched scalar-oracle f32 bits for complete
attention-output matrices from layers 3, 20, 40, and 60 across four checkpoint
shards. Deterministic repeats and signed-zero counts also matched.

The retained 10-sample decode-only population measured a 12.232673 s scalar
median and 0.391463 s NumPy median, a 31.25x ratio. The record and generated
table are
[`raw/post-f016-q5-k-numpy-qualification-0001.json`](raw/post-f016-q5-k-numpy-qualification-0001.json)
and
[`tables/post-f016-q5-k-numpy-qualification-0001.md`](tables/post-f016-q5-k-numpy-qualification-0001.md).

This qualifies decoder integration only. The next gate measures one complete
Q5_K read/decode/MLX-build/matvec boundary and representative MLA execution;
it does not yet justify P1.

## Phase B2: Q5_K dense integration

**Result: exact and material at the MLA boundary.**

At clean source `f6446a07d62118672d6d593d536f834786ad2b54`, both modes used one
bounded matrix read. The candidate changed only Q5_K decode; non-Q5 formats
remained scalar. One complete real Q5_K matrix improved from an 11.080288 s
median to 0.547885 s (20.22x), with exact MLX output bits.

Complete layer-3 MLA vectorized its two captured Q5_K projections and retained
two non-Q5 scalar projections. Its median changed from 17.983298 s to 5.317590 s
(3.38x), again with exact output bits. The generated component table is
[`tables/post-f016-trunk-q5-integration-0001.md`](tables/post-f016-trunk-q5-integration-0001.md).

The remaining 3.091203 s median captured decode and 1.577387 s uninstrumented
residual justify measuring the next inventory-supported format before a P1
decision. No complete-layer or token claim is made from this MLA boundary.

## Phase B3: Q8_0 decoder qualification

**Result: exact for complete 2-D matrices.**

At clean source `d24549193e3f9718c34e34b70904a5273af5978c`, four complete real
`attn_q_b` matrices from layers 3, 20, 40, and 60 matched scalar-oracle f32
bits, deterministic hashes, and signed-zero counts. The retained decode-only
population measured a 3.056227 s scalar median and 0.040342 s NumPy median
(75.76x).

The evidence and generated table are
[`raw/post-f016-q8-0-numpy-qualification-0001.json`](raw/post-f016-q8-0-numpy-qualification-0001.json)
and
[`tables/post-f016-q8-0-numpy-qualification-0001.md`](tables/post-f016-q8-0-numpy-qualification-0001.md).
Per-head 3-D Q8_0 remains scalar and row-read; it is not included in this claim.

## Phase B4: 2-D Q8_0 dense integration

**Result: exact and material; 3-D Q8_0 is now the next bounded gate.**

At clean source `15a358de4a48387e9c0d9d1b1da1d781be1a3c08`, Q5_K remained
vectorized in both modes and only captured 2-D Q8_0 changed. The real Q8 matrix
median fell from 2.754374 s to 0.137694 s (20.00x). Complete layer-3 MLA fell
from 5.253066 s to 2.057474 s (2.55x), with exact f32-bit output.

The candidate MLA retained a 1.326647 s median uninstrumented residual, 64.5%
of median boundary wall by ratio of medians. Because per-head 3-D Q8_0 remains
row-read and scalar inside that residual, it must be isolated before Q6_K or P1.
The generated table is
[`tables/post-f016-trunk-q8-2d-integration-0001.md`](tables/post-f016-trunk-q8-2d-integration-0001.md).

## Phase A supplement: per-head Q8_0 bulk reads

**Result: exact plumbing, not a material wall improvement.**

At clean source `0f38f1d4448789b5a938ed9db3baa659c797ecf0`, the scalar Q8_0
decoder and MLX path were unchanged. One read per head slab reduced complete
layer-3 MLA head-path requests from 49,152 to 128 and storage median from
0.025127 s to 0.000754 s. MLA median changed only from 2.073939 s to 2.062230 s
(1.006x). Scalar head decode remained about 0.985 s.

The exact storage-only result is retained in
[`tables/post-f016-q8-head-bulk-scalar-0001.md`](tables/post-f016-q8-head-bulk-scalar-0001.md).
It supports the next one-variable experiment—NumPy head-slab decode—but does
not justify a storage-prefetch project or a token-speed claim.
