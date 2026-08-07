# GLM-5.2 golden baseline (research path)

**Tag**: `v0.3.0-glm52-e2e-research`  
**Frozen HEAD at tag**: see `git rev-parse v0.3.0-glm52-e2e-research`  
**Path**: architecture research path (CPU dequant + optional MLX matmul helpers)  
**Not claimed**: optimized tokens/sec, production serving, MLX-only incremental decode

## Checkpoint

| Field | Value |
| --- | --- |
| Env | `PULSARMLX_GLM_GGUF` |
| Identity | `docs/validation/glm52-checkpoint.json` |
| Set SHA-256 | `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee` |
| Total bytes | 238,458,632,928 |
| Quant | UD-IQ2_XXS multi-shard (6 files) |

## Architecture contract

See `docs/architecture/GLM52_CONTRACT.md`.

- architecture: `glm-dsa`
- layers: **79**
- experts: **256**, used **8**, shared **1**
- embd: **6144**
- MLA + DSA

## Frozen P-MIN

| Field | Value |
| --- | --- |
| Text | `Hello` |
| Token IDs | `[9703]` |
| Source | `docs/research/glm52/raw/f016-frozen-prompts-0001.json` |

## C11 eight-token greedy sequence (golden)

```text
prompt:     [9703]
generated:  [21615, 220, 16, 13, 16, 16, 15, 15]
full:       [9703, 21615, 220, 16, 13, 16, 16, 15, 15]
```

| Evidence | Path |
| --- | --- |
| C09 depth ladder | `docs/research/glm52/raw/f016-c09-depth-0001.json` |
| C10 logits | `docs/research/glm52/raw/f016-c10-logits-0001.json` |
| C11 generation | `docs/research/glm52/raw/f016-c11-generation-0001.json` |

C11 wall time (research path): **48730.7 s** (~13.5 h).

## Acceptance for optimizations

Any optimized inference path (MLX-only, incremental state, expert cache) must **bit-for-bit match** the greedy token IDs above for the same checkpoint, prompt, and greedy argmax policy before its performance numbers are accepted.
