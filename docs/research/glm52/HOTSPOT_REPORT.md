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
- Primary wins: expert residency of dequantized slabs, faster dequant, MLX-only hot path without research instrumentation.

Raw: `docs/research/glm52/raw/f016-hotspot-profile-0001.json`
