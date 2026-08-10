# PulsarMLX MoE Optimization Sprint Report

## Status

The bounded M1 Ultra MoE study begins at `cb1a0e06` on the isolated branch
`codex/glm52-moe-optimization`. It does not modify the independent Feature 017
checkout, run golden-eight, or implement direct quantized Metal.

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
