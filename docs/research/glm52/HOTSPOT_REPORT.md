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
