# Dogfood plan: GLM-5.3-Flash with cold experts on NVMe (Flash AN)

**Status: run on real weights on both target machines (2026-09-17); numbers below.**

The model is 320B/18B-active; the unpruned mixed-4/8 build is 169.4 GiB:
~159.5 GiB of routed experts (42 layers × 288 experts × 14.2 MB at 4-bit/g64
with bf16 scales) and ~10 GiB of 8-bit resident weights. It does not fit any
Mac's memory in this range; it runs by paging experts (graphs 18–19): the
retained mlx-vlm `repack` splits each MoE layer's experts into one file, the
`ExpertStore` mmaps them and keeps a byte-budgeted LRU of hot experts, and
`OffloadedSwitchGLU` computes only the selected experts.

| Machine | Expert budget¹ | Hot experts | Decode misses/token² | NVMe read/token | Decode floor at 3–6 GB/s |
|---|---|---|---|---|---|
| Mac Studio M1 Ultra 128 GB | ~77 GiB | ~5,800 (48%) | ~175 | ~2.5 GB | 0.4–0.8 s/token |
| MacBook Pro M2 Max 64 GB | ~38 GiB | ~2,900 (24%) | ~255 | ~3.6 GB | 0.6–1.2 s/token |

¹ The store's rule: 0.8 × recommended working set (≈75% of unified memory by
default) − resident − 8 GB KV reserve. ² Random-routing upper bound; real
routing is skewed toward hot experts, so hit rates will be higher.

**Prefill** is the expensive part of this design: every prefill chunk bulk-
loads each MoE layer's whole expert file (42 × 4.1 GB ≈ 171 GB of reads per
chunk), so a long prompt costs minutes regardless of RAM. Keep
`prefill_step_size` bounded (the lazy graph otherwise pins every expert).

**Required configuration (graph 19 finding):** `OffloadedSwitchGLU`
host-evaluates the routing indices, which `mx.compile` forbids; the decoder
layer compiles its FFN at B=1,S=1. After loading, every patched layer must
run the eager FFN path (`layer.compile_ffn = False`). Neither pinned upstream
applies this; `scripts/research/glm53_flash/dogfood/run_offload.py` does.

**Pins:** mlx-vlm `8d79dbcf…`, pipenetwork glm5_next `a61a7c7d…` (both
retained under the evidence tree). **Disk:** the build (182 GB on disk) and
the offload directory (~same) coexist during repack (~2× the build free).

**What is and is not qualified.** Qualified at tiny geometry under the
supervised harness: every layer type, decode with caches, sanitize/strict
load, the quantized expert kernels, the offload store and module, and the
loading path (graphs 9–19). Not qualified: `nn.quantize` of the resident
weights (a mixed build's 8-bit linears), the container-level prefix
mapping, the tokenizer/chat template, throughput. The first real run is
therefore a dogfood measurement, not a claim.

**Run:**
```bash
python scripts/research/glm53_flash/dogfood/run_offload.py \
  --build /path/GLM-5.3-Flash-MLX-mixed-4_8bit --offload /path/GLM-5.3-Flash-offload \
  --max-tokens 64 --prefill-step-size 256 --log dogfood-run.json
```

## Measured (2026-09-17, unpruned mixed-4/8, greedy, one short prompt, 96 tokens)

Prompt: "What is the capital of France? Answer in one short sentence." Every
run below produced the identical text (the model reasons, then answers
"The capital of France is Paris.").

| Machine | Offload dir | Budget | Store | Decode | Prompt | Hit rate | Peak |
|---|---|---|---|---|---|---|---|
| MacBook Pro M2 Max 64 GB | external NVMe | 32 GB | upstream LRU | 0.590 tok/s | 0.62 tok/s | 57.8% | 45.4 GB |
| MacBook Pro M2 Max 64 GB | external NVMe | 32 GB | Pulsar v2 cold / warm | 0.616 / 0.620 | 0.62 | 59.1% / 62.3% | 45.4 GB |
| Mac Studio M1 Ultra 128 GB | internal SSD | 70 GB | upstream LRU (×2) | 3.00 / 3.01 | 1.16–2.44 | 77.8% | 83.4 GB |
| Mac Studio M1 Ultra 128 GB | internal SSD | 70 GB | Pulsar v2 cold (×2) | 3.02 / 2.98 | 2.28–2.45 | 77.8% | 83.4 GB |
| Mac Studio M1 Ultra 128 GB | internal SSD | 70 GB | Pulsar v2 warm (×4) | 2.14–2.35 | 1.32–2.69 | 85.1% | 83.4 GB |
| Mac Studio M1 Ultra 128 GB | internal SSD | 50 GB | LRU / Pulsar cold / Pulsar warm | 1.50 / 1.66 / 1.50 | 1.8–2.4 | 68% / 70% / 74% | — |
| MacBook Pro M2 Max 64 GB | **internal NVMe** | 32 GB | upstream LRU | 0.951 | 1.42 | 57.8% | 45.4 GB |
| MacBook Pro M2 Max 64 GB | **internal NVMe** | 32 GB | Pulsar cold / warm (graph 22, bounded clearing) | 1.109 / 1.139 | 1.6–2.0 | 59.1% / 62.3% | 45.4 GB |
| Mac Studio M1 Ultra 128 GB | internal SSD | 70 GB | Pulsar cold / warm (graph 22, bounded clearing, ×2) | 3.16–3.46 / 2.65–2.67 | 1.5–2.9 | 77.8% / 85.1% | 83.4 GB |

The Studio's prompt tok/s varies with the page-cache state left by the
previous run (prefill bulk-loads every expert file per chunk); the 70 GB
budget on a 128 GB host that also carries ~20 GB of other applications
leaves ~12 GB of page cache during decode. Repack to the internal SSD took
569 s for 170 GB; re-admitting a 70 GB warm state takes 17–20 s.

Two effects measured with a per-token probe (private evidence
`dogfood/studio-ab.json`): (1) `mx.clear_cache()` after every eviction —
upstream `ExpertStore` behaviour that `PulsarExpertStore` inherited — costs
10–13% once the store is full (3.03 → 3.35 cold, 2.32 → 2.62 warm with the
call stubbed); (2) the per-miss cost is 2.4–3.1 ms in cold runs at 70 GB but
7.4–9.7 ms in warm runs and 5.8–7.9 ms for every store at 50 GB, so the cold
70 GB numbers are partly a 96-token transient (the store fills over the first
quarter of decode and the last quarter already runs at 0.37–0.39 s/token
against the warm runs' 0.43–0.45). See `pulsar-expert-store.md` for the
store-level reading and graph 22's bounded clearing.

**Where the time goes (and what 20–30 tok/s would take).** Per token the
model touches 42 × 8 routed experts (4.8 GB at 4-bit) plus ~10 GB of 8-bit
resident weights. Fully resident, that is ~15 GB of memory traffic per token:
~19 ms on an M1 Ultra (800 GB/s), ~37 ms on an M2 Max (400 GB/s) — a 25–50
tok/s bandwidth ceiling, before compute. Paged, every miss costs a 14.2 MB
read: at 78% hits on the Studio that is ~74 misses ≈ 1 GB per token from
the SSD (≥ 0.2 s at 5 GB/s), so no residency policy reaches 20 tok/s on the
unpruned build with 160 GB of experts and 128 GB of RAM: it would need
≥ 95% hits *with* the reads fully overlapped, or ≥ 99.5% without. On top of
that the current offload path has an all-hit cost of ~0.16–0.22 s per token
(the eager per-expert loop with one host sync per layer — the intercept of
the per-token fits), which alone caps it near 5 tok/s. The routes to a
usable rate are therefore: (a) a fully resident build on the Studio (REAP50,
96 GB, fits 128 GB with the compiled path and no store); (b) for paged
tiers, replace the per-expert loop with a gather-matmul over a stacked
resident buffer per layer (routing stays on the GPU) and overlap miss reads
with compute — that lifts the paged ceiling toward the bandwidth bound but
stays below 20 tok/s whenever misses per token exceed a handful.

## The ladder to a usable rate (graph 23 onward)

1. **Fully resident REAP50 on the Studio** (`run_resident.py`): pipenetwork's
   saliency-pruned build keeps 144 of 288 experts per MoE layer (96.3 GB,
   revision `63114f52…`, `reap` block in its config). The pinned loader
   sizes `SwitchGLU`, the router and `e_score_correction_bias` from
   `text_config.n_routed_experts`, so no loader change is needed; the
   strict load is the shape check. Every weight is materialized before the
   first token (`lazy=False`), no offload patching, compiled FFN path.
   ```bash
   PYTHONPATH=/path/glm53-flash-mlx-a61a7c7d python scripts/research/glm53_flash/dogfood/run_resident.py \
     --model /path/GLM-5.3-Flash-REAP50-MLX-mixed-4_8bit --max-tokens 96 --log reap50.json
   ```
   **Measured (Studio, 2026-09-17, three runs):** load 24–27 s from the
   internal SSD (96.3 GB materialized), **decode 22.6 / 22.5 / 22.4 tok/s**
   (96, 96 and 256 tokens), peak 100.2–100.5 GB, coherent text on both
   prompts. Prefill is the new blocker: 0.66, 2.0 and 6.0 tok/s (25, 25 and
   67 prompt tokens; the first run also paid for the host's swapping —
   1.47 M page-outs — because ~20 GB of unrelated applications were resident
   on the Studio). A 1,000-token prompt at that rate is minutes, so the next
   rung is profiling the resident prefill path (per-layer: linear attention
   under the S≤5 kernel domain, the DSA indexer/MLA prefill, the MoE path).
2. **Paged tiers**: gather-matmul over a stacked per-layer resident buffer
   (routing stays on the GPU; removes the ~0.2 s all-hit intercept) plus
   miss reads overlapped with compute.
3. **Prefill served from the store** instead of bulk-loading every expert
   file per chunk.
