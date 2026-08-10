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
