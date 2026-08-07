# Contract: GLM-5.2 architecture (draft until checkpoint open)

## Status

**Draft.** Freeze to `docs/architecture/GLM52_CONTRACT.md` only after:

1. disk admission pass,
2. checkpoint open + KV parse,
3. upstream Pulsar `glm-dsa` source revision pin.

## Provisional architecture identity

| Field | Provisional value | Source |
| --- | --- | --- |
| architecture | `glm-dsa` | HF card / upstream |
| params class | ~744–754B | public cards |
| attention | MLA + DSA sparse indexer | upstream README/design notes |
| MoE | routed + shared experts | upstream |
| preferred quant | UD-IQ2_XXS | project pin |

## Numerical contract

- Primary: architecture-level math with documented dequant × activation path.
- Not claimed: fused CUDA bit-parity, llama-style Q8×Q8 act requant identity.
- Tolerances: publish absolute + relative before measuring; do not loosen after.

## Runtime contract

- No full-model resident requirement on 128 GB UM.
- Expert streaming with explicit miss path.
- Performance mode: MLX-only; CPU oracle offline for that timer.

## Unsupported claims until C09–C11 pass

- full-model support
- generation quality beyond deterministic token IDs
- tokens/sec as production SLOs
- GLM-5.2 “ready” marketing language
