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

Legacy P1 `ExpertSlabCache` (Python research runtime):

- key: `tensor_name#expert_id`
- value: dequantized f32 rows
- policy: deterministic LRU under byte budget
- matvec: MLX when available

P1 recorded 0 hits across two complete stacks because one stack is 2052
48-MiB decoded slabs (96.1875 GiB) while the 8-GiB LRU retained only 170. The
cache lifetime spans tokens; sequential early-layer misses evict every retained
late-layer slab before reuse. Budgets through 48 GiB retain the same cyclic
failure under identical replay.

The current P2 design protects only decoded shared-expert matrices:

- 228 gate/up/down slabs across 76 MoE layers
- 10.6875 GiB logical f32 payload
- guaranteed reuse on every later token
- routed experts bypass the decoded tier until measured routing history
  justifies a separate policy
- cache values are compact evaluated MLX/f32 matrices rather than Python
  float/list graphs
- inference mode fails closed on missing MLX instead of silently selecting CPU
- routed and over-budget matrices are synchronized, dereferenced, and followed
  by explicit MLX transient-cache release instead of accumulating residency
- storage hits, decoded hits, reads, redequants, MLX evaluation, and memory are
  recorded separately

## Decoder modes

The inference cache exposes two explicit decoder modes for the qualified
IQ2_XXS and IQ3_XXS formats:

- `scalar_reference` retains row-by-row positional reads and the unchanged
  scalar Python decoder;
- `numpy_vectorized` performs one bounded positional read for a complete
  selected IQ2_XXS or IQ3_XXS expert matrix, one whole-matrix vector decode into
  contiguous f32 storage, one synchronized MLX matrix build, and the existing
  MLX matvec.

Other mixed-quant matrices retain their existing scalar reference decoder until
profiling establishes another dominant format. Unknown types,
dimensions, expert IDs, truncated reads, and non-contiguous/wrong-dtype vector
outputs fail closed. Evidence records storage read, dequant, contiguous-buffer
verification, MLX build/evaluation, matvec, and per-quant totals separately.
The default remains `scalar_reference`; optimized experiments must select
`--decoder-mode numpy_vectorized` explicitly.

The simulator and machine-readable policy evidence are
`scripts/research/glm52_cache_simulator.py` and
`docs/research/glm52/raw/f016-cache-simulation-0001.json`. Its identical C09
route replay tests policy mechanics only; P1 did not retain its route IDs.

Maps ssd-llm **layer** LRU idea onto **expert slabs** (GLM-appropriate).

## Prefetch (planned)

Only after the two-token golden and reuse gate:

- after router, issue async loads for selected expert IDs (next layer optional)
- bounded in-flight reads
- cancel if budget exceeded

## Acceptance

```text
generate(P-MIN, n_new=8, mode=inference) == GOLDEN C11 sequence
```

before any tokens/sec publication.

## Current Tier-3 CLI

```sh
.venv/bin/python scripts/research/glm52_inference.py --mode inference \
  --n-new 2 --cache-gib 16 --cache-policy decoded_shared_only \
  --out docs/research/glm52/raw/f016-inference-p2-token2.json
```

The output is source/checkpoint bound and atomically checkpointed after each
completed stack. P2 must pass exact `[9703, 21615, 220]` parity and record at
least 228 decoded hits in the first generated-token stack before eight-token
execution or prefetch work is eligible.
