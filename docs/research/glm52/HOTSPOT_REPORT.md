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
- IQ3_XXS is therefore the next decoder candidate. This ranking is not an
  IQ3_XXS speedup claim; it must pass its own exact-bit qualification first.
- Current order: qualify and integrate IQ3_XXS, rerun bounded rungs needed to
  establish benefit, then re-profile shared residency before P2.

Raw: `docs/research/glm52/raw/f016-hotspot-profile-0001.json` and
`docs/research/glm52/raw/f016-p1-quant-hotspot-ranking-0001.json`
