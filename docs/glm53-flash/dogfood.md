# Dogfood plan: GLM-5.3-Flash with cold experts on NVMe (Flash AN)

**Status: entrypoint written and unit-checked; not yet run on real weights.**

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
