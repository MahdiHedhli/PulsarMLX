# GLM research path hotspot report

Probe: layer 3, token 9703 (P-MIN).

| Block | seconds |
| --- | ---: |
| `moe_top8_plus_shared` | 50.776 |
| `mla_layer3_pos0` | 18.933 |
| `shared_expert` | 10.019 |
| `single_routed_expert` | 5.035 |
| `router_layer3` | 0.060 |
| `embed_token` | 0.010 |
| `output_norm` | 0.001 |

## Empirical C11

- decode stack ≈ 5335.0 s
- logits ≈ 79.0 s
- full 8-token gen ≈ 48730.7 s

## Conclusions

- Dominant cost is expert SwiGLU dequant+matvec (×9 experts per MoE layer).
- MLA is second-order but material (~seconds–tens of seconds).
- C11 research path does not dual-run CPU oracle; cost is pure architecture forward.
- Prefix is not re-embedded for old tokens, but each new token still walks all 79 layers (correct for decode); KV is CompactKVCache append-only.
- Whole-matrix NumPy IQ2_XXS decoding passed exact-bit qualification and the
  integration ladder through vectorized P1 reproduced the golden prefix.
- The committed P1 per-quant inventory ranks measured component time rather
  than global tensor count. IQ3_XXS is first at 1791.414 seconds (61.78% of the
  quantified component sum), followed by Q6_K at 475.308 seconds and Q5_K at
  225.687 seconds.
- IQ3_XXS therefore became the next decoder candidate. It subsequently passed
  exact-bit qualification for four complete matrices at source `be47a95`; the
  ranking itself remains only the reason for that selection, not a speedup
  claim.
- Current order: rerun the affected bounded rungs to establish end-to-end
  benefit, then re-profile shared residency before P2.

Raw: `docs/research/glm52/raw/f016-hotspot-profile-0001.json` and
`docs/research/glm52/raw/f016-p1-quant-hotspot-ranking-0001.json`

## Revised P1 profile after IQ3_XXS vectorization

The clean P1 at source `99751b9` reproduced `[9703,21615]` in 4582.511032
seconds. Its regenerated ranking contains the same nine exercised formats but
reduces the quantified component sum from 2899.499809 to 1185.470056 seconds.
IQ3_XXS moved from first at 1791.413883 seconds to fourth at 101.107184 seconds.

Q6_K is now first at 468.856301 seconds (39.55%), followed by Q5_K at
225.731846 seconds (19.04%). The warm stack reported all 228 decoded
shared-cache hits and avoided 2,105,769,984 compressed bytes plus
11,475,615,744 decoded bytes. The retained cache therefore has measured reuse
value and remains enabled for P2. Q6_K is the next candidate for any later
exact-bit decoder work, but it does not block the two-token correctness/reuse
gate because the admitted warm shared matrices are already resident.

Raw: `docs/research/glm52/raw/f016-p1-iq3-quant-hotspot-ranking-0001.json`

## Golden-eight cold/warm profile

The final profile is generated from the committed golden-eight record plus a
public-safe witness for eight passively archived, SHA-deduplicated snapshots.
The watcher began after the cold and first warm stacks, so it supports seven
one-stack warm deltas (completed stack counts 2→3 through 8→9), not a cold
per-quant table. Every cumulative interval was monotonic; no reset was hidden.

The cold prompt stack took 2569.174 seconds. Its bounded component ranking was:

1. uninstrumented trunk residual: 1636.636 seconds (63.70%)
2. expert-cache dequantization: 836.066 seconds
3. expert-cache contiguous buffers: 74.588 seconds
4. expert-cache MLX matrix build: 11.018 seconds
5. expert-cache MLX matvec: 8.909 seconds
6. expert-cache storage: 1.957 seconds

The eight warm stacks had a 1921.882-second median. Their mean bounded ranking
was 1670.730 seconds of uninstrumented trunk residual, 206.003 seconds of
expert-cache dequantization, 77.778 seconds of separately recorded logits,
18.173 seconds of expert-cache contiguous buffers, 9.615 seconds of matrix
build, 7.972 seconds of matvec, and 3.872 seconds of storage. The median residual
fraction was 87.18%; it is not assigned to any quantization.

The warm quantization ranking is **EXPERT-CACHE PATH ONLY**, not whole-token
cost: IQ2_XXS 69.672 mean seconds, IQ3_XXS 50.304, Q2_K 36.153, IQ4_XS 34.654,
IQ2_S 33.964, Q3_K 20.391, Q5_K 0.813, Q6_K 0.378, and Q8_0 0.014. This reverses
the earlier inference that Q6_K dominated the complete warm token: that claim
was valid only for the earlier instrumented P1 expert path.

Storage averaged 0.20% of warm stack wall, so Feature 016 defers prefetch rather
than adding an unmeasured mechanism. The residual is too large to select the
first direct-quantized kernel by expert format alone. Provisional Feature 018
therefore remains profile-neutral pending M2 Max fixtures for MLA/attention
projections, dense pre/post-attention transforms, embeddings if material,
final norm/output projection, and any Q6_K tensors in those trunk paths.

Raw: `docs/research/glm52/raw/f016-golden8-derived-profile-0001.json`; generated
table: `docs/research/glm52/tables/f016-golden8-derived-profile.md`.
