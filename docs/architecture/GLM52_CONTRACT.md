# GLM-5.2 Architecture Contract

**Status**: **KV-FROZEN + upstream-mapped** (full tensor catalog pending complete shards)
**Date**: 2026-08-07
**Upstream donor pin**: `giannisanni/pulsar` @ `17dac547898e0e65bb073f13444708daf68edc3d`
**Family**: `glm-dsa` → Pulsar `Family::Mla` with DSA indexer
**Quant**: `UD-IQ2_XXS` multi-shard (Unsloth)

## Do not claim yet

- Full-model support, generation quality, production tok/s
- Bit-parity with fused CUDA
- Residual op order final until C01 name walk on complete catalog

## Checkpoint

| Field | Value |
| --- | --- |
| Repo | `unsloth/GLM-5.2-GGUF` |
| Path | `UD-IQ2_XXS/` (6 shards) |
| Expected total bytes | 238,458,632,928 |
| Env | `PULSARMLX_GLM_GGUF` |

## GGUF KV (shard 00001)

| Key | Value |
| --- | ---: |
| architecture | `glm-dsa` |
| block_count | **79** |
| context_length | 1,048,576 |
| embedding_length | **6144** |
| feed_forward_length | 12288 |
| expert_count | **256** |
| expert_used_count | **8** |
| expert_shared_count | **1** |
| expert_feed_forward_length | 2048 |
| attention.head_count | 64 |
| attention.head_count_kv | 1 |
| attention.q_lora_rank | 2048 |
| attention.kv_lora_rank | 512 |
| attention.key_length_mla | 256 |
| attention.value_length_mla | 256 |
| attention.indexer.head_count | 32 |
| attention.indexer.key_length | 128 |
| attention.indexer.top_k | 2048 |
| rope.dimension_count | 64 |
| rope.freq_base | 8e6 |
| vocab | 154880 |

### Derived MLA

```
qk_rope = 64
qk_nope = 192   # key_length_mla - rope
value_mla = 256
n_lora_q = 2048
n_kv_lora = 512
```

Source: Pulsar `Shape::from_gguf` for `Family::Mla` (`crates/engine/src/lib.rs` ~445–462).

## End-to-end graph (from upstream + KV)

Hypothesis level: **H1** confirmed in source structure; **H2** name-level pending full catalog.

| Stage | Behavior | Source / note |
| --- | --- | --- |
| Embed | `token_embd.weight` | Pulsar loads `token_embd` |
| Residual stream | width `n_embd=6144` | KV |
| Pre-attn norm | RMSNorm `blk.N.attn_norm` | LayerW.attn_norm |
| MLA | q_a/q_b LoRA, kv_a MQA, latent KV, rope on rope-tail | Family::Mla |
| DSA indexer | top-k **2048** rows; full indexer on leading dense + every 4th from layer 6 (GLM policy) | `uses_full_indexer` ~920–923 |
| Attn residual | `stream += attn_out` | classic residual path |
| Pre-FFN norm | RMSNorm `blk.N.ffn_norm` | LayerW.ffn_norm |
| Router | **sigmoid** lineage (not softmax-all); top-k over experts | Shape.softmax_router=false for GLM lineage |
| Shared expert | `expert_shared_count=1` as always-selected sink slot; `n_expert_used += n_shexp` | ~437–439 |
| Routed experts | gate/up/down slabs; SwiGLU (confirm activation) | expert FFN width 2048 |
| MoE residual | `stream += moe_out` | residual |
| Final | `output_norm` + `output` / tied embd | standard |

### Tensor name patterns (expected)

From Pulsar load paths / stream expert addressing:

```
token_embd.weight
output_norm.weight
output.weight                    # or embd-tied
blk.{i}.attn_norm.weight
blk.{i}.ffn_norm.weight
blk.{i}.ffn_gate_inp.weight      # router (may be F32)
blk.{i}.ffn_gate_exps.weight     # [*,*,n_expert]
blk.{i}.ffn_up_exps.weight
blk.{i}.ffn_down_exps.weight
blk.{i}.ffn_gate_shexp.weight    # shared
blk.{i}.ffn_up_shexp.weight
blk.{i}.ffn_down_shexp.weight
# MLA (names exact TBD from catalog — H2)
blk.{i}.attn_q_a.weight / attn_q_b.weight / attn_kv_a_mqa.weight / ...
# DSA indexer
blk.{i}.indexer.* or model-level indexer.*
```

**H2**: Exact MLA/DSA tensor names must be filled from C01 complete catalog — do not invent.

### Expert slab addressing (stream)

For 3D expert tensors `dims[2]==n_expert`:

```
expert_bytes = row_bytes * dims[1]
offset_e = tensor_base + e * expert_bytes
```

Source: `crates/stream/src/lib.rs` `expert_reads`.

### DSA layer policy (GLM)

```text
full indexer: leading dense layers + every 4th layer starting from 6
intervening layers: reuse last indexer selection
```

Source: `uses_full_indexer` comment “verbatim from ds4” for GLM-5.2.

## Numerical contract

See frozen table in `docs/research/glm52/EXPERIMENT_PROTOCOL.md` §5.

## Streaming / memory contract

- Expert streaming + optional attention residency
- Default budgets (configurable): 48 GiB compressed expert cache; 24 GiB headroom
- Fail closed on silent CPU fallback / full materialization beyond budget

## Open items (need C01 catalog)

- [x] Exact MLA tensor names per layer (`attn_q_a/b`, `attn_kv_a_mqa`, `attn_k_b`, `attn_v_b`, …)
- [x] Exact indexer tensor names (`indexer.attn_k/q_b`, `indexer.k_norm`, `indexer.proj`)
- [x] Mixed quant type histogram (C01: Q8_0/Q5_K/F32/IQ2_XXS/…)
- [ ] `leading_dense_block_count`
- [ ] Whether lm_head is tied to embd
- [ ] RMSNorm epsilon exact KV key

## Freeze checklist

- [x] Arch id, layers, experts, MLA/DSA dims from GGUF KV
- [x] Upstream revision pin
- [x] Router family (sigmoid + shared sink) from source
- [x] Expert slab address formula
- [x] Complete tensor catalog (1809 tensors, 0 bad offsets)
- [ ] Residual op order verified against real forward
