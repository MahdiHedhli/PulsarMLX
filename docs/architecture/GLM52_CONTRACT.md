# GLM-5.2 Architecture Contract

**Status**: **KV-FROZEN from shard 00001 metadata** (tensor catalog pending remaining shards)
**Date**: 2026-08-07
**Checkpoint quant**: `UD-IQ2_XXS` (`unsloth/GLM-5.2-GGUF`)
**Upstream donor**: giannisanni/pulsar `glm-dsa` / `Family::Mla` (not copied CUDA memory model)

## Checkpoint identity (in progress)

| Field | Value |
| --- | --- |
| Repo | `unsloth/GLM-5.2-GGUF` |
| Quant | `UD-IQ2_XXS` |
| Form | 6 GGUF shards |
| Expected total bytes | 238,458,632,928 (~222.082 GiB) |
| Env var | `PULSARMLX_GLM_GGUF` → shard directory |

SHA-256 per shard recorded in `docs/validation/glm52-checkpoint.json` after download.

## Architecture KV (from GGUF, shard 00001)

| Key | Value |
| --- | ---: |
| `general.architecture` | `glm-dsa` |
| `general.name` | Glm-5.2 |
| `block_count` | **79** |
| `context_length` | 1,048,576 |
| `embedding_length` | **6144** |
| `feed_forward_length` | 12288 |
| `expert_count` | **256** |
| `expert_used_count` | **8** |
| `expert_shared_count` | **1** |
| `expert_feed_forward_length` | 2048 |
| `attention.head_count` | 64 |
| `attention.head_count_kv` | 1 (MLA latent) |
| `attention.q_lora_rank` | 2048 |
| `attention.kv_lora_rank` | 512 |
| `attention.key_length_mla` | 256 (= nope 192 + rope 64) |
| `attention.value_length_mla` | 256 |
| `attention.indexer.head_count` | 32 |
| `attention.indexer.key_length` | 128 |
| `attention.indexer.top_k` | 2048 |
| `rope.dimension_count` | 64 |
| `rope.freq_base` | 8,000,000 |
| vocab (tokenizer) | 154,880 |

### Derived MLA layout (upstream Pulsar `Family::Mla` for `glm-dsa`)

```
qk_rope  = rope.dimension_count          # 64
qk_nope  = key_length_mla - qk_rope      # 192
value_mla = value_length_mla             # 256
n_lora_q  = q_lora_rank                  # 2048
n_kv_lora = kv_lora_rank                 # 512
```

DSA lightning indexer: top-k **2048** rows per token; enables long context
beyond a naive dense window.

### MoE routing (provisional, align with upstream)

- Lineage: **sigmoid** router (not softmax-only Qwen style), top-8 active.
- **1 shared expert** participates as always-selected slot
  (`n_expert_used` effective may include shared — confirm against graph).
- Expert FFN width 2048; SwiGLU expected (confirm activation).

## Numerical contract

| Mode | Rule |
| --- | --- |
| Architecture oracle | Independent CPU dequant × f32 (or documented) activations |
| MLX path | Same math; Apple GPU execution |
| Not claimed | Fused CUDA bit-parity; llama Q8×Q8 act requant identity |
| Tolerances | Absolute + relative frozen **before** measuring each boundary |

## Streaming / memory contract (M1 Ultra 128 GB)

- Do **not** require full model residency.
- Expert-level addressing, compressed expert cache, eviction, prefetch.
- Attention / MLA stack may be resident-tier; experts stream from internal SSD.
- Performance mode: MLX-only; no CPU-oracle in timers.
- Abort if sustained memory pressure / swap dominates.

### Starting experimental profile

- ~48 GB compressed expert cache
- Stream remaining expert capacity
- ≥24 GB OS/runtime headroom

## Residual graph (to confirm with full tensor names)

Expected modern pre-norm decoder block:

1. RMSNorm → MLA (+ DSA selection) → residual add
2. RMSNorm → MoE (shared + top-k routed) → residual add

Exact op order frozen after tensor-name inspection (GLM-C01 complete).

## Success criteria for “full model”

Claims of full GLM support require:

- GLM-C09 full 79-layer stack
- GLM-C10 full logits
- GLM-C11 ≥8 greedy tokens from tokenizer-driven prompt

## Unsupported until those pass

- full-model support
- generation quality marketing
- production tokens/sec
- GLM-5.2 “ready” language

## Freeze checklist

- [x] Architecture id + layer/expert/MLA/DSA dims from GGUF KV
- [ ] All shard files present + SHA-256
- [ ] Complete tensor catalog (offsets in range)
- [ ] Upstream source revision pin (pulsar `17dac547…` research clone)
- [ ] Residual graph op order confirmed
- [ ] Tolerances published per boundary
