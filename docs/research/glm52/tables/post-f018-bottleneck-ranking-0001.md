# Post-IQ3 bottleneck ranking

> Scopes overlap and are not additive. Matrix and bounded-layer medians are separated from the single exact P1 warm-stack observation.

## Complete layer 3

Median `0.992020` s (sample stddev `0.022535` s): attention/MLA `0.750135` s, MoE `0.211920` s, and boundary/orchestration `0.028962` s.

## Ranked measured boundaries

| Rank | Operation | Scope | Seconds | Current path | Likely class |
| ---: | --- | --- | ---: | --- | --- |
| 1 | `full-vocabulary output.weight` | one logits matrix boundary | 72.534284 | Q4_K scalar decode -> f32 materialization -> MLX import -> matvec | reuse/residency |
| 2 | `complete layer 78` | one exact P1 warm-stack layer | 4.748120 | dense MLA plus intentional reference experts | distributed; profile format-specific references before a kernel |
| 3 | `complete layer 8` | one exact P1 warm-stack layer | 3.571900 | Q6_K dense MLA plus IQ2_S/IQ4_XS reference experts | mixed dense reuse and explicit-reference formats |
| 4 | `blk.8.attn_output.weight` | one dense matrix boundary | 1.438365 | Q6_K NumPy decode -> f32 MLX | reuse/residency, subject to bounded hot-set admission |
| 5 | `layer 3 attention/MLA` | one complete-layer sub-boundary | 0.750135 | vectorized dense decode -> f32 MLX | vectorized decode or bounded reuse |
| 6 | `blk.78.attn_output.weight` | one dense matrix boundary | 0.532297 | Q5_K NumPy decode -> f32 MLX | reuse/residency, but all-layer retention is unsafe |

## Dense residency/reuse

| Tensor | Quant | Decoded GiB | Transient (s) | Host rebuild (s) | MLX-ready (s) | RSS delta GiB | Pressure |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `output.weight` | Q4_K | 3.545 | 72.534284 | 0.467045 | 0.006228 | 8.469 | normal |
| `blk.78.attn_output.weight` | Q5_K | 0.375 | 0.532297 | 0.052926 | 0.002786 | 1.363 | normal |
| `blk.8.attn_output.weight` | Q6_K | 0.375 | 1.389852 | — | 0.002910 | 1.521 | normal |

## Decision

Outcome **B**: decoded/native-ready output-head residency with bounded admission.

The exact output boundary is token-scale and setup-dominated, while measured MLX-ready reuse preserves the output hash and reduces repeated use to milliseconds under normal pressure. This measured lower-risk target precedes a Q4_K direct kernel.

Next experiment: Host output.weight as one identity-bound native-ready resident entry, run exact final-logits fixtures, then one clean P1 only if the bounded runtime integration passes.

No fresh P1, P2, golden-eight run, or third kernel was started.
