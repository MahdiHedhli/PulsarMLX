# GLM inference path design (weekend sprint)

## Separation

| Path | Role |
| --- | --- |
| **research** | Golden C09–C11; instrumented; architecture dequant; oracle-friendly |
| **inference** | MLX-oriented hot path; expert slab cache; same math; no dual oracle |

Research remains the correctness source of truth (`GOLDEN_BASELINE_C11.md`).

## Incremental state (already required for C11)

Per-layer `CompactKVCache` stores:

- `kv_lora[pos]` (512)
- `k_rope[pos]` unrotated (64)

Decode appends position; Q is rebuilt per token with RoPE at `pos`. This is **MLA compact-KV**, not classical multi-head K/V pages.

DSA: short context uses range-fill (`visible <= top_k`). Long-context indexer selection reuse is deferred.

## Expert residency

`ExpertSlabCache` (Python research runtime):

- key: `tensor_name#expert_id`
- value: dequantized f32 rows
- policy: deterministic LRU under byte budget
- matvec: MLX when available

Maps ssd-llm **layer** LRU idea onto **expert slabs** (GLM-appropriate).

## Prefetch (planned)

Only after golden match:

- after router, issue async loads for selected expert IDs (next layer optional)
- bounded in-flight reads
- cancel if budget exceeded

## Acceptance

```text
generate(P-MIN, n_new=8, mode=inference) == GOLDEN C11 sequence
```

before any tokens/sec publication.

## CLI (planned)

```text
pulsar-mlx run $PULSARMLX_GLM_GGUF --prompt Hello --max-new 8 --greedy \
  --expert-cache-gib 8 --mode inference
```

Current entry: `scripts/research/glm52_inference.py`.
