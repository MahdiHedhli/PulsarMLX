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

## Phase B5: per-head Q8_0 NumPy integration

**Result: exact and material; the MLA residual is now directly bounded.**

At clean source `a6f233822dade6096209a165d5085c4234063960`, both modes read one
complete head slab. NumPy decoding reduced one real head median from 0.009862 s
to 0.001535 s (6.43x). Complete layer-3 MLA fell from 2.037030 s to 0.769746 s
(2.65x), with exact f32-bit output.

Across the 128 head operations, decode median fell from 0.980048 s to 0.017462 s.
The newly instrumented residual fell to 0.007187 s, while the four 2-D
projections retained a 0.705703 s median total. The generated table is
[`tables/post-f016-q8-head-numpy-integration-0001.md`](tables/post-f016-q8-head-numpy-integration-0001.md).

Q6_K remains justified because the Phase-A layer-8 attention-output matrix spent
about 46.9 s in scalar decode and the inventory contains five exercised Q6_K
trunk tensors. Q6_K qualification therefore precedes complete-layer and P1 gates.

## Phase B6: Q6_K decoder qualification

**Result: exact for every exercised Q6_K trunk tensor.**

At clean source `06f0ff8ace8b3c38fbb2d344b76ba0d110f28fd9`, all five Q6_K
trunk tensors across layers 0, 1, 2, and 8 matched scalar f32 bits,
deterministic hashes, and signed-zero counts. The bounded layer-8 Q-A timing
population measured a 6.181737 s scalar median and 0.143820 s NumPy median
(42.98x). The layer-8 attention-output first comparison measured 49.118090 s
scalar versus 1.351459 s vector.

The record and table are
[`raw/post-f016-q6-k-numpy-qualification-0001.json`](raw/post-f016-q6-k-numpy-qualification-0001.json)
and
[`tables/post-f016-q6-k-numpy-qualification-0001.md`](tables/post-f016-q6-k-numpy-qualification-0001.md).
This qualifies Q6_K integration; it does not yet establish a layer-8 MLA or
complete transformer-layer result.

## Phase B7: Q6_K dense integration

**Result: exact and material at the layer-8 MLA boundary.**

At clean source `42c38d3ef61a251fc9823bdca0c35afdcdc171c8`, Q5_K and all Q8_0
paths remained vectorized in both modes; only Q6_K changed from the scalar
decoder to the exact-bit NumPy decoder. The complete real layer-8 attention
output matrix median fell from 48.092368 s to 1.426283 s (33.72x). Complete
single-position layer-8 MLA fell from 55.137022 s to 1.762948 s (31.28x), with
exact f32 output bits.

The candidate MLA's 132 retained dense operations comprise 130 vector Q8_0
operations and two vector Q6_K operations, with no scalar operation. Its median
decode time was 1.616308 s and its uninstrumented residual was 0.007253 s. The
raw record retains a legacy summary-label omission for the Q6 operation count;
the validator derives the corrected count from every immutable nested sample.
See
[`tables/post-f016-trunk-q6-integration-0001.md`](tables/post-f016-trunk-q6-integration-0001.md).

This admits the next bounded gate: a complete transformer-layer comparison. It
does not establish a stack, P1, token-generation, Rust, or Metal result.

## Phase C: representative complete layer

**Result: exact and material; P1 is admitted.**

At clean measurement source `7abcce2a3448c63df1226a2594734db630c42d9a`,
the complete single-position layer-8 boundary retained the same MLX expert
decoder, protected shared-cache policy, Q5_K path, Q8_0 paths, prompt embedding,
and arithmetic order. Only dense Q6_K decode changed. Median complete-layer
wall fell from 97.071291 s to 44.266072 s (2.19x). Attention fell from
54.700836 s to 1.758870 s while MoE remained effectively unchanged at
42.436827 s versus 42.475366 s.

The original attempt is preserved with `actual_status: failed`: its compound
harness gate incorrectly required zero cache misses, while eight transient
routed experts necessarily miss three matrices each. Every retained sample had
the correct contract—three protected shared-matrix hits, 24 transient routed
matrix misses, three resident shared entries, identical top-8 routes, exact
attention midpoint and complete-layer f32 hashes, and normal resource pressure.
A deterministic audit corrects only that semantic gate and does not alter or
rerun samples. See
[`tables/post-f016-trunk-complete-layer8-q6-0001.md`](tables/post-f016-trunk-complete-layer8-q6-0001.md).

This representative complete-layer reduction is substantial enough to admit a
single exact P1 full-stack gate after the remaining bounded cleanup and
residency experiments. It is not itself a stack or token-generation claim.
