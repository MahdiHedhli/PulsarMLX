# PulsarMLX MoE Optimization Sprint Report

## Status

The bounded M1 Ultra MoE study began at `cb1a0e06` on the isolated branch
`codex/glm52-moe-optimization` and passed its optional exact P2 gate at clean
source `c115c7f6`. It did not modify the independent Feature 017 checkout, run
golden-eight, or implement direct quantized Metal.

## Phase 1: post-trunk P1 attribution

The exact P1 schema provides per-layer cache deltas after all eight routed
experts and the shared expert complete. It therefore supports exact layer-level
expert-cache attribution and route identities, but not individual-expert or
projection-level timing.

For the 316.758671-second warm terminal stack, all three shared matrices per
MoE layer were decoded-cache hits. Consequently, every recorded warm storage,
decode, contiguous-buffer, and matrix-build second belongs to the 24 transient
routed matrices per layer. Recorded MLX matvec time combines 24 routed and three
shared matvecs and cannot be split from the existing evidence.

The deterministic attribution record and generated review table are:

- [`raw/post-f016-p1-moe-attribution-0001.json`](raw/post-f016-p1-moe-attribution-0001.json)
- [`tables/post-f016-p1-moe-attribution-0001.md`](tables/post-f016-p1-moe-attribution-0001.md)

The table's top 20 entries are layer top-8 routed-expert sets ranked by complete
expert-cache attributed time. They are not individual-expert hotspots. P1 does
not time MLA versus MoE, gate/up/down, routed versus shared matvec, SwiGLU,
router, aggregation, or cleanup separately. Those are explicit timers for the
next bounded harness; no residual is relabeled as one of those stages.

Reproduce without checkpoint access:

```sh
python3 scripts/research/analyze_glm52_moe_p1.py
python3 scripts/research/analyze_glm52_moe_p1.py --check
python3 -m unittest scripts/research/tests/test_glm52_moe_p1_attribution.py
```

## Phase 2 protocol: bounded expert harness

The opt-in telemetry path leaves default inference behavior unchanged. When a
bounded harness enables it, every gate/up/down event records tensor identity,
expert ID, shared/routed role, quantization, cache disposition, compressed and
decoded bytes, read/decode/buffer time, MLX construction and evaluation time,
matvec time, and transient cleanup time. Expert-level timers additionally
retain SwiGLU activation and route-weight application; the MoE boundary retains
normalization, router projection, route selection, routed/shared aggregation,
and residual-add timers.

The admitted real-checkpoint ladder uses layers 3, 8, 40, and 78 to cover early,
exceptional early, middle, and late quantization layouts. Each residual is a
real checkpoint MLA result from frozen token `9703` at position zero, but is not
described as a sequential full-stack hidden state. One untimed reference,
one process-first observation, three warmups, and ten retained warm samples are
required per layer. Timed and untimed paths must match exact f32 output bits and
routes with normal resource pressure, zero fallback, and zero eviction.

The harness does not execute 79 layers, P1/P2, golden-eight, Rust, or Metal.

## Phase 2 result: bounded expert harness

The clean source at `4879c38b` passed all four admitted real-checkpoint MoE
boundaries. Every one of the ten retained samples per layer matched the
unchanged untimed path at exact f32 output bits and exact routes. All shared
gate/up/down matrices were protected cache hits; CPU fallback, eviction, and
admission rejection stayed zero, and every resource observation was normal.

The deterministic raw record and generated analysis are:

- [`raw/post-f016-moe-stage-profile-0001.json`](raw/post-f016-moe-stage-profile-0001.json)
- [`raw/post-f016-moe-stage-analysis-0001.json`](raw/post-f016-moe-stage-analysis-0001.json)
- [`tables/post-f016-moe-stage-analysis-0001.md`](tables/post-f016-moe-stage-analysis-0001.md)

Median MoE boundary time was 1.711785 s at layer 3, 42.965916 s at layer 8,
1.735408 s at layer 40, and 56.373736 s at layer 78. Routed expert execution
accounted for 42.903692 s and 56.311461 s at the two exceptional layers;
their retained shared expert cost was only 0.007494 s and 0.007482 s.

The newly separated MLX build/eval, matvec, SwiGLU, weighting, aggregation,
cleanup, and residual timers are not the dominant bounded costs. At layer 78,
Q2_K decode had a 31.711137 s median and Q3_K decode 18.114957 s. At layer 8,
IQ2_S decode had a 29.908856 s median and IQ4_XS decode 6.520325 s. The
corresponding MLX build/eval medians were about 0.125 s per complete boundary,
while routed/shared matrix matvec was about 0.164 s at layer 8 and 0.214 s at
layer 78. The evidence therefore selects exact Q2_K decoder qualification as
the next bounded change, followed by the remaining measured scalar formats if
their absolute opportunity remains material. It does not select a Feature 018
Metal kernel.

Reproduce the committed derivation without checkpoint access:

```sh
python3 scripts/research/analyze_glm52_moe_profile.py --check
python3 -m unittest \
  scripts/research/tests/test_glm52_moe_profile_record.py \
  scripts/research/tests/test_glm52_moe_stage_analysis.py
```

## Phase 3 result: exact Q2_K decoder boundary

At clean source `296e8868`, the whole-matrix NumPy Q2_K decoder matched the
committed scalar decoder at exact f32 bits for four complete real layer-78
routed gate/up expert matrices. Deterministic hashes and signed-zero counts
matched, malformed and non-finite synthetic inputs fail closed, one bounded
read replaces 2,048 row reads when integrated, and every resource observation
remained normal.

The checkpoint census contains Q2_K only in the layer-78 routed gate/up tensor
pair, both in shard 6. Cross-layer or cross-shard Q2_K qualification is
therefore impossible for this immutable checkpoint and is not claimed. The
ten-sample gate/expert-242 decode median fell from 2.265407 s scalar to
0.147176 s NumPy, a 15.39x decoder-boundary ratio. This is not yet a complete
expert, MoE, layer, stack, or token speedup.

- [`raw/post-f016-q2-k-numpy-qualification-0001.json`](raw/post-f016-q2-k-numpy-qualification-0001.json)
- [`tables/post-f016-q2-k-numpy-qualification-0001.md`](tables/post-f016-q2-k-numpy-qualification-0001.md)

The exact layer-78 integration then reduced the ten-sample MoE median from
56.373736 s to 22.898163 s (2.46x) against a scalar-reference MoE output and
route. Candidate decode fell to 20.424514 s, buffer handling to 2.002285 s,
MLX construct/eval was 0.142778 s, matvec 0.131529 s, cleanup 0.076882 s, and
SwiGLU 0.002240 s. Q3_K now accounts for a 20.166532-second attributed median,
including 17.969160 s decode, so it is the next bounded decoder gate.

- [`raw/post-f016-moe-layer78-q2-0001.json`](raw/post-f016-moe-layer78-q2-0001.json)
- [`raw/post-f016-moe-layer78-q2-analysis-0001.json`](raw/post-f016-moe-layer78-q2-analysis-0001.json)
- [`tables/post-f016-moe-layer78-q2-0001.md`](tables/post-f016-moe-layer78-q2-0001.md)

## Phase 3 continuation: exact Q3_K decoder boundary

At clean source `0a7e2c61`, the whole-matrix NumPy Q3_K decoder matched the
scalar decoder at exact f32 bits for four complete real layer-78 routed down
matrices, with deterministic hashes, matching signed-zero counts, fail-closed
malformed/non-finite tests, and normal resources. The checkpoint contains one
Q3_K tensor only—layer-78 routed down in shard 6—so broader layer/shard coverage
does not exist and is not claimed. The ten-sample expert-242 decode median fell
from 2.550016 s scalar to 0.135837 s NumPy (18.77x).

- [`raw/post-f016-q3-k-numpy-qualification-0001.json`](raw/post-f016-q3-k-numpy-qualification-0001.json)
- [`tables/post-f016-q3-k-numpy-qualification-0001.md`](tables/post-f016-q3-k-numpy-qualification-0001.md)

Combined exact Q2_K/Q3_K integration reduced the same layer-78 MoE median to
3.828766 s: 14.72x versus the 56.373736-second baseline and 5.98x versus the
Q2_K-only boundary. Median routed decode is now 3.471512 s, MLX construct/eval
0.120354 s, matvec 0.087634 s, cleanup 0.076701 s, and residual 0.003052 s.
The remaining Q2_K and Q3_K vector decode is measurable but layer 8's
42.965916-second scalar IQ2_S/IQ4_XS path is now the larger absolute target.

- [`raw/post-f016-moe-layer78-q2-q3-0001.json`](raw/post-f016-moe-layer78-q2-q3-0001.json)
- [`raw/post-f016-moe-layer78-q2-q3-analysis-0001.json`](raw/post-f016-moe-layer78-q2-q3-analysis-0001.json)
- [`tables/post-f016-moe-layer78-q2-q3-0001.md`](tables/post-f016-moe-layer78-q2-q3-0001.md)

## Phase 3 continuation: exact IQ2_S decoder boundary

At clean source `fd98f89d`, the whole-matrix NumPy IQ2_S decoder matched the
scalar decoder at exact f32 bits for four complete real layer-8 routed gate/up
matrices. Deterministic hashes, signed-zero counts, malformed/non-finite input
tests, and resource gates passed. IQ2_S exists only in the layer-8 routed
gate/up tensor pair, so broader layer/shard coverage is unavailable. The
ten-sample expert-216 gate decode median fell from 2.128742 s scalar to
0.067880 s NumPy (31.36x).

- [`raw/post-f016-iq2-s-numpy-qualification-0001.json`](raw/post-f016-iq2-s-numpy-qualification-0001.json)
- [`tables/post-f016-iq2-s-numpy-qualification-0001.md`](tables/post-f016-iq2-s-numpy-qualification-0001.md)

Exact IQ2_S integration reduced the layer-8 MoE median from 42.965916 s to
10.004603 s (4.29x). Candidate decode was 7.599570 s, buffer handling
1.990244 s, MLX construct/eval 0.142864 s, matvec 0.071304 s, cleanup
0.076885 s, and residual 0.015654 s. IQ4_XS now accounts for 8.722821 s of
median attributed work, including 6.585108 s decode and 1.989881 s buffer
construction, and becomes the next measured decoder gate.

- [`raw/post-f016-moe-layer8-iq2-s-0001.json`](raw/post-f016-moe-layer8-iq2-s-0001.json)
- [`raw/post-f016-moe-layer8-iq2-s-analysis-0001.json`](raw/post-f016-moe-layer8-iq2-s-analysis-0001.json)
- [`tables/post-f016-moe-layer8-iq2-s-0001.md`](tables/post-f016-moe-layer8-iq2-s-0001.md)

## Phase 3 continuation: exact IQ4_XS decoder boundary

At clean source `bf44192a`, whole-matrix NumPy IQ4_XS decoding matched the
scalar decoder at exact f32 bits for complete expert matrices from layers 8,
75, 76, and 77, spanning shards 2 and 6. Deterministic hashes, signed-zero
counts, malformed/non-finite gates, and normal resources passed. The ten-sample
layer-8 expert-216 down decode median fell from 1.052149 s scalar to 0.042700 s
NumPy (24.64x).

- [`raw/post-f016-iq4-xs-numpy-qualification-0001.json`](raw/post-f016-iq4-xs-numpy-qualification-0001.json)
- [`tables/post-f016-iq4-xs-numpy-qualification-0001.md`](tables/post-f016-iq4-xs-numpy-qualification-0001.md)

Combined exact IQ2_S/IQ4_XS integration reduced the layer-8 MoE median to
1.713339 s: 25.08x versus the 42.965916-second baseline and 5.84x versus the
IQ2_S-only boundary. Median routed decode is now 1.364327 s, MLX
construct/eval 0.125503 s, matvec 0.071072 s, cleanup 0.078595 s, and residual
0.003297 s. The exceptional layer-8 scalar decoder hotspot has collapsed.

- [`raw/post-f016-moe-layer8-iq2-s-iq4-xs-0001.json`](raw/post-f016-moe-layer8-iq2-s-iq4-xs-0001.json)
- [`raw/post-f016-moe-layer8-iq2-s-iq4-xs-analysis-0001.json`](raw/post-f016-moe-layer8-iq2-s-iq4-xs-analysis-0001.json)
- [`tables/post-f016-moe-layer8-iq2-s-iq4-xs-0001.md`](tables/post-f016-moe-layer8-iq2-s-iq4-xs-0001.md)

## Phase 7 result: final bounded multi-layer reprofile

At clean source `7b4e51ee`, layers 8, 40, 75, 76, 77, and 78 each passed ten
retained exact scalar-reference output/route comparisons. All 60 samples had
normal resource observations, with zero fallback and eviction. MoE medians are
1.659900 s, 1.720982 s, 1.462585 s, 1.457447 s, 1.449233 s, and 3.845930 s
respectively. The formerly exceptional IQ4_XS layers 75–77 now sit below the
representative layer-40 IQ2_XXS/IQ3_XXS boundary.

Vectorized decode remains the largest bounded stage: 1.10–1.36 s for layers
8/40/75–77 and 3.483794 s for layer 78. MLX build/eval is about 0.12–0.13 s,
matvec 0.07–0.09 s, cleanup 0.08–0.09 s, and retained shared-expert execution
about 0.007 s per boundary. This profile resolves individual expert and
projection costs but is not a full-token population and therefore does not by
itself select a Feature 018 kernel.

- [`raw/post-f016-moe-multilayer-all-vector-0001.json`](raw/post-f016-moe-multilayer-all-vector-0001.json)
- [`raw/post-f016-moe-multilayer-all-vector-analysis-0001.json`](raw/post-f016-moe-multilayer-all-vector-analysis-0001.json)
- [`tables/post-f016-moe-multilayer-all-vector-0001.md`](tables/post-f016-moe-multilayer-all-vector-0001.md)

## Phase 7 result: complete layer-8 gate

At clean source `29c33ba6`, the current all-vector dense and expert paths
passed one complete single-position layer-8 boundary across ten retained
samples. Every sample preserved the exact prior committed attention midpoint,
route `[216,244,206,79,102,188,146,78]`, and final f32 output hash. Resource
observations remained normal, and CPU fallback and cache eviction stayed zero.

The current complete-layer median is **3.511617 s**, split into 1.787092 s of
attention/MLA and 1.728566 s of MoE. The prior committed warm boundary was
44.266072 s with 42.475366 s of MoE, giving cross-commit observations of
12.60x for the complete layer and 24.58x for MoE. These are not a
counterbalanced same-binary population and are not token-latency claims.

The current MoE median includes 1.366600 s of routed matrix decode, 0.122907 s
of MLX matrix construct/evaluation, 0.076787 s of matrix-vector products, and
0.085132 s of cleanup. The protected shared expert remains a cache hit and
costs about 0.007045 s, dominated by its three retained MLX matvecs. Decode is
therefore still the largest bounded expert stage; neither build/import nor the
shared cache policy is the immediate bottleneck.

- [`raw/post-f016-complete-layer8-all-vector-0001.json`](raw/post-f016-complete-layer8-all-vector-0001.json)
- [`raw/post-f016-complete-layer8-all-vector-analysis-0001.json`](raw/post-f016-complete-layer8-all-vector-analysis-0001.json)
- [`tables/post-f016-complete-layer8-all-vector-0001.md`](tables/post-f016-complete-layer8-all-vector-0001.md)

## Phase 4: routed-expert residency economics

The committed P1 and P2 routes exactly match the first two and first three
stacks of the frozen golden-eight trace. Across its eight adjacent stack
intervals, 1,892 of 4,864 routed selections repeat the same expert in the same
layer (38.90%). The interval fraction increases from 9.38% to 53.12%, so the
frozen continuation contains real adjacent-token reuse opportunity, but it is
only one short-context prompt and cannot establish a general hit rate.

A static decoded top-one expert in every MoE layer would retain 76 expert
units, require 10.6875 GiB of logical f32 storage, and turn 428 later expert
uses (1,284 matrices) into decoded hits over the nine-stack trace. A single
global hot pin costs 0.140625 GiB and yields eight later expert hits. Compressed
top-one-per-layer residency costs 0.8108 GiB and avoids reads on the same uses,
but does not avoid decode/build; prior warm evidence already makes storage the
secondary stage. A compressed top-one tier plus eight decoded hot experts uses
1.125 GiB logical f32 for the decoded tier and exposes 171 decoded matrix hits.

These are deterministic route/catalog economics, not allocated RSS results or
latency savings. Observed policy RSS is intentionally recorded as unavailable,
and the 10.6875-GiB candidate remains inadmissible until a bounded real
ownership/lifetime experiment measures allocator overhead. Decoded-all routed
residency is rejected as unsafe.

- [`raw/post-f016-routed-residency-economics-0001.json`](raw/post-f016-routed-residency-economics-0001.json)
- [`tables/post-f016-routed-residency-economics-0001.md`](tables/post-f016-routed-residency-economics-0001.md)

## Phase 5: decoded-buffer and MLX-ready reuse

At clean source `a83276bc`, a process-isolated lifecycle study exercised layer
64 expert 183, the only routed `(layer, expert)` unit selected in all nine
frozen golden-eight stacks. All three candidates produced the same exact f32
output hash across ten retained uses with normal resource pressure.

The current transient lifecycle took 0.248258 s median: 0.211046 s decode,
0.015782 s MLX build/evaluation, 0.010806 s matvec, 0.000275 s SwiGLU, and
0.009364 s cleanup. Retaining decoded host buffers removed reads/decode but
rebuilt MLX matrices, reducing reuse to 0.032086 s (7.74x). Retaining evaluated
MLX matrices reduced reuse to 0.002417 s (102.72x), dominated by 0.002040 s of
matvec. Decode remains the largest transient stage; build/import is measurable
but not dominant.

The 144-MiB logical expert produced setup RSS deltas of about 155 MiB for host
buffers and 251 MiB for MLX-ready matrices. This validates a bounded hot pin
but rejects extrapolation to top-one-per-layer residency without a separate
allocator-aware admission gate. No unbounded routed cache was added.

- [`raw/post-f016-routed-expert-reuse-0001.json`](raw/post-f016-routed-expert-reuse-0001.json)
- [`raw/post-f016-routed-expert-reuse-analysis-0001.json`](raw/post-f016-routed-expert-reuse-analysis-0001.json)
- [`tables/post-f016-routed-expert-reuse-0001.md`](tables/post-f016-routed-expert-reuse-0001.md)

## Phase 6: shared-expert recheck

The complete layer-8 profile retains all three protected shared matrices. Its
shared expert costs about 0.007045 s, with zero read, decode, or build work on
the warm path. The remaining cost is synchronized MLX matvec plus negligible
activation/aggregation. The working shared-cache policy therefore remains
unchanged; redesigning it would not address the current dominant cost.

## Phase 9: exact P2 gate

Material exact improvement at the complete layer admitted one clean-source P2.
At `c115c7f6`, the unchanged frozen prompt produced exact prefix
`[9703,21615,220]` across three complete 79-layer stacks and three complete
76-layer top-8 route traces. Total evidence wall was 1479.009580 s. The cold
stack took 921.235962 s; the two warm stacks took 197.928826 s and 194.063845 s.
Their preceding full-vocabulary logits boundaries took 89.246947 s and
76.430414 s.

All retained resource observations were normal. The run recorded 456 protected
shared-cache hits, 228 resident entries, 4,211,539,968 compressed bytes and
22,951,231,488 decoded bytes avoided, zero CPU fallbacks, zero evictions, and
zero admission rejections. The warm-stack mean/median is 195.996335 s across
two samples; this is an exact correctness gate, not a general steady-state
throughput population.

Warm expert-cache decode was 103.146919 s and 103.904752 s. Expert storage was
9.165052 s and 7.078381 s, MLX build/evaluation 9.032754 s and 9.052198 s,
matvec 8.096326 s and 6.768674 s, and the uninstrumented stack residual
68.448357 s and 67.219210 s. Expert decode remains the largest warm stack
stage; logits and the residual are also material.

- [`raw/post-f016-inference-p2-moe-vector-0001.json`](raw/post-f016-inference-p2-moe-vector-0001.json)
- [`raw/post-f016-inference-p2-moe-vector-analysis-0001.json`](raw/post-f016-inference-p2-moe-vector-analysis-0001.json)
- [`tables/post-f016-inference-p2-moe-vector-0001.md`](tables/post-f016-inference-p2-moe-vector-0001.md)

## Revised bottleneck and Feature 017/018 implications

A deterministic catalog-touch model uses the exact bounded layer medians and
predicts 104.719147 s of warm routed decode, within 1.15% of the observed
103.525836-second two-stack mean. Its largest buckets are IQ2_XXS routed
gate/up at 55.750817 s across 1,184 matrix touches and IQ3_XXS routed down at
43.125401 s across 568 touches. The remaining formats are each below 2.4 s of
modeled warm decode.

The evidence is now sufficient to select **IQ2_XXS routed gate/up** as Feature
018's first direct-quantized Metal candidate by largest measured absolute warm
opportunity. This is candidate selection only; no Metal implementation or
performance claim is made. Feature 017 should prioritize exact whole-slab
IQ2_XXS/IQ3_XXS decode, low-copy evaluated-matrix handoff, and allocator-aware
bounded route residency. The one-expert hot-pin result warrants that native
interface, but not a 76-expert Python cache.

No additional full-model or golden-eight run is required for this sprint.
