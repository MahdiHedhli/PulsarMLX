# PulsarMLX Post-IQ3 Bottleneck and Integration Report

## Executive result

The qualified direct IQ2_XXS gate/up plus IQ3_XXS down path remains numerically
green. A fresh ten-sample complete layer-3 population measured a `0.992020 s`
median versus `2.451145 s` for the optimized reference at the same boundary.
The next measured target is **B: bounded decoded/native-ready output-head
residency**, not a third Metal kernel.

The decisive observation is token-scale rather than a matrix-only speedup. The
existing exact P1 spent `77.987068 s` in logits. A bounded profile of the real
`output.weight` boundary measured `72.534284 s` median, of which `59.195961 s`
was scalar Q4_K decode/materialization and `11.387966 s` was MLX build/eval.
Exact MLX-ready reuse reduced repeated use of that matrix to `0.006228 s`
median. This does not remove its expensive first-use setup.

No third kernel, fresh P1, P2, or golden-eight run was started.

## Repository boundary

- Sprint start: `6db38f1c937b9ad48321586be85cc558fb48e815`
- Feature branch: `feat/018-direct-quantized-metal-runtime`
- Feature 017 revision reviewed: `c2021e304f146afb9e1ccde86c252f341ab8ef78`
- Checkpoint set: immutable GLM-5.2 UD-IQ2_XXS binding already committed
- Machine class: Apple Silicon M1 Ultra

## Complete layer 3

The fresh source was clean, the midpoint and output hashes matched the frozen
reference, the route remained exact, and the result retained the existing
`numerically_qualified_greedy_identical` classification.

| Boundary | Median (s) | Sample stddev (s) | Notes |
| --- | ---: | ---: | --- |
| Complete direct layer | 0.992020 | 0.022535 | 10 measured samples |
| Optimized reference layer | 2.451145 | 0.022885 | same matrix/input/output boundary |
| Attention / MLA | 0.750135 | 0.021351 | top-level layer phase |
| MoE | 0.211920 | 0.005563 | top-level layer phase |
| Boundary / orchestration | 0.028962 | 0.001671 | top-level remainder |

The following stage timers are nested and must not be added to the top-level
phase timers: dense storage `0.011545 s`, decode `0.682103 s`, contiguous buffer
`0.003135 s`, MLX build `0.038566 s`, and MLX matvec `0.048107 s`. Within MoE,
router time was `0.051138 s`; synchronized IQ2 and IQ3 direct totals were
`0.026583 s` and `0.007960 s`; shared reference execution was `0.002411 s`;
routed activation plus aggregation was `0.003624 s`.

## Additional dense / trunk layers

The same current dense path was measured at layers 3, 8, 40, and 78. Each
candidate matched its scalar-oracle output hash exactly. These are MLA
boundaries, not complete transformer-layer populations.

| Layer | MLA wall median (s) | Dense attributed (s) | Orchestration / other (s) |
| ---: | ---: | ---: | ---: |
| 3 | 0.814805 | 0.807909 | 0.006938 |
| 8 | 1.818843 | 1.811255 | 0.007437 |
| 40 | 0.855689 | 0.847190 | 0.008498 |
| 78 | 0.857837 | 0.849645 | 0.008522 |

The exact combined P1 supplies complete warm-layer observations for comparison:
layer 78 was `4.748120 s`, layer 8 was `3.571900 s`, and the typical fully
direct layers were about `0.8–0.9 s`. Those are single P1 observations and are
not part of the ten-sample MLA population.

## Dense / trunk hotspot and materialization audit

| Operation | Quant | Total (s) | Storage (s) | Decode / materialize (s) | MLX build (s) | Matvec (s) | Interpretation |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `output.weight` | Q4_K | 72.534284 | 0.059747 | 59.195961 + 1.692246 buffer | 11.387966 | 0.153218 | setup dominates |
| `blk.8.attn_output.weight` | Q6_K | 1.438365 | 0.008828 | 1.370043 | 0.036418 | 0.019929 | decode dominates |
| `blk.78.attn_output.weight` | Q5_K | 0.559816 | 0.007783 | 0.498197 | 0.039209 | 0.013795 | decode dominates |
| representative `attn_q_b` | Q8_0 | 0.132–0.144 | small | 0.114–0.125 | small | small | smaller distributed cost |

The current dense path remains compressed bytes → CPU decode → contiguous f32
materialization → MLX import/build → compute. Storage is not the dominant
measured stage. A third kernel could eventually remove Q4_K materialization,
but an exact lower-risk reuse result is already available and should be
integrated first.

## Residency and reuse study

Each candidate was process-isolated, synchronized, deterministic, and retained
the exact output hash across lifecycles. Memory pressure remained normal.

| Tensor | Quant | Logical decoded GiB | Transient median (s) | Host-buffer rebuild (s) | MLX-ready (s) | MLX-ready RSS delta GiB |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `output.weight` | Q4_K | 3.545 | 72.534284 | 0.467045 | 0.006228 | 8.469 |
| `blk.78.attn_output.weight` | Q5_K | 0.375 | 0.532297 | 0.052926 | 0.002786 | 1.363 |
| `blk.8.attn_output.weight` | Q6_K | 0.375 | 1.389852 | not measured | 0.002910 | 1.521 |

The output-head MLX-ready setup took `82.506219 s`; it included the same scalar
decode plus host conversion and a one-time evaluated matrix build. Its process
peak RSS was `43,499,241,472` bytes and setup RSS delta was `9,093,480,448`
bytes. These observations admit one identity-bound output-head entry on the
measured 128 GB machine under the observed load. They do not admit decoded-all
trunk residency, nor do they establish MLX allocator overhead for a larger hot
set.

Q5_K and Q6_K reuse is individually compelling, but those matrices are
layer-specific. Retaining every attention matrix would recreate the unsafe
decoded-all/decoded-attention budget. Any later dense hot set needs measured
route/touch reuse and bounded admission, not a global cache.

## P1 attribution and deferral

The already committed exact P1 recorded:

- `833.188530 s` cold stack;
- `77.987068 s` logits;
- `78.446275 s` terminal warm stack;
- 1,136 direct routed expert executions and 80 intentional reference
  executions across both stacks;
- 228 protected shared-cache hits on the warm stack;
- zero fallback, direct error, eviction, CPU fallback, or admission rejection.

A fresh P1 would only repeat the unchanged runtime. The bounded evidence and
the existing exact P1 already answer the attribution question, so the optional
run was deferred. One new P1 becomes useful only after output-head residency is
integrated and passes bounded final-logits validation.

## Ranked remaining bottlenecks

The generated ranking is in
`tables/post-f018-bottleneck-ranking-0001.md`. Its scopes overlap and must not
be summed.

1. `output.weight` Q4_K: `72.534284 s` bounded median and most of the measured
   logits stage; setup/materialization dominated.
2. Complete warm P1 layer 78: `4.748120 s`; mixed dense work plus intentional
   reference experts.
3. Complete warm P1 layer 8: `3.571900 s`; Q6_K dense work plus IQ2_S/IQ4_XS
   intentional reference experts.
4. Layer-8 Q6_K attention output: `1.438365 s` matrix median.
5. Layer-3 attention/MLA: `0.750135 s` complete-layer phase median.
6. Late-layer Q5_K attention output: about `0.53–0.56 s` per matrix population.

## Selected outcome and third-kernel admission

**Outcome B — dense/trunk residency/reuse target.** The bounded next target is
one checkpoint- and tensor-identity-bound MLX-ready `output.weight` entry with
conservative admission, explicit lifetime/teardown, and exact final-logits
validation.

A third kernel is **not admitted in this sprint**. Q4_K output is now the
leading future direct-kernel candidate by absolute measured opportunity, but
the already-qualified reuse path should establish how much warm-token work is
left after runtime integration. IQ2/IQ3 contracts remain unchanged.

## Feature 017 / Feature 018 integration

The concrete format-neutral deltas are documented in
`../../architecture/F017_F018_POST_IQ3_HANDOFF.md`. In short, F017 still needs:

- a typed per-kernel capability key, rather than global format lists;
- an identity- and generation-bound native buffer/range request;
- a trunk-native-ready residency entry, not only expert-native-ready policy;
- explicit direct, intentional-reference, fallback, and error dispositions;
- one in-flight completion lease that mechanically retains owner,
  registration, immutability, and slot generation;
- telemetry that separates registration, compile/pipeline, dispatch, kernel,
  synchronization, and residency events.

Feature 018 continues to own IQ2/IQ3 packed layouts, shaders, format-specific
parameters, dispatch validation, and numerical evidence. No format-specific
code was copied into Feature 017 and no branch merge was performed.

## Exact next experiment

Implement the format-neutral native-ready tensor handle and admission contract
in Feature 017, host one decoded/evaluated output-head entry through that
contract, and run checkpoint-free lifecycle tests plus the existing final-output
fixture on the M2 Max. Then integrate the reviewed contract on the M1 Ultra,
run the bounded real output/logits gate, and admit one P1 only if exactness,
teardown, pressure, and fail-closed dispatch all pass.

Another full-model run is not required before that bounded integration gate.
