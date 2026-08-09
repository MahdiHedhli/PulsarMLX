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
