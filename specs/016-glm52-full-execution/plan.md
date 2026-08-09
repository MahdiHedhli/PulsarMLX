# Implementation Plan: 016-glm52-full-execution

## Status

**Active** at Phase 8 (weekend inference optimization). Qwen remains frozen at
`v0.2.0-qwen30b-e2e-research`; the GLM research baseline is frozen at
`v0.3.0-glm52-e2e-research`.

## Phases

| Phase | Name | Gate |
| --- | --- | --- |
| 0 | Preserve Qwen baseline + tag | Done |
| 1 | Internal SSD disk admission | Done; original stop resolved |
| 2 | Immutable checkpoint acquisition | Done; six shards and hashes frozen |
| 3 | M1 Ultra streaming runtime | Research path done; inference optimization active |
| 4 | Architecture contract freeze | Done |
| 5 | Correctness ladder C01–C11 | Done |
| 6 | Full execution evidence | Done |
| 7 | Research publication + `v0.3.0` tag | Done |
| 8 | Inference optimization | Active; exact-bit decoder qualification precedes the bounded performance ladder and P2 |

## Technical approach

1. **Acquire** `UD-IQ2_XXS` shards (or single-file DS4 equivalent) to internal
   SSD via atomic `.partial` → validate → rename; set `PULSARMLX_GLM_GGUF`.
2. **Runtime**: positional GGUF reads, compact evaluated MLX matrices, protected
   shared-expert residency under a 16-GiB logical cap, transient routed experts,
   and no CPU fallback in inference mode.
3. **Contract**: derive `docs/architecture/GLM52_CONTRACT.md` from GGUF KV +
   upstream Pulsar `glm-dsa` (MLA, DSA indexer, routing, shared experts).
4. **Validate** C01→C11 with per-layer drift metrics; stop on material divergence.
5. **Benchmark** cold/warm TTFT, prefill, decode; publish under `docs/research/glm52/`.

## Active decoder-priority sequence

1. Qualify the NumPy whole-matrix IQ2_XXS decoder against exact scalar f32
   bits on synthetic blocks and complete matrices from multiple real shards.
2. Integrate explicit `scalar_reference` and `numpy_vectorized` modes using one
   bounded matrix read, one contiguous decode, and one evaluated MLX matrix.
3. Benchmark decode, real matrix, routed expert, layer-3 MoE, layer, and P1 in
   that order. **Committed through P1** at `32230e1`; the exact golden prefix
   matched with zero CPU fallback.
4. Inventory mixed quant formats by measured P1 golden-trace time. **Committed
   at `492fcfb`**; IQ3_XXS accounted for 61.78% of the quantified component sum.
5. Qualify and integrate IQ3_XXS at exact scalar f32 bits before re-running the
   affected measured ladder. **Qualification passed** at source `be47a95` for
   four complete matrices across four shards with zero bit mismatches.
6. Rerun affected boundaries in order. **Committed through the real IQ3 down
   matrix** at source `15a8aa2`; the **complete routed expert passed** at source
   `a8a3d71`, so layer-3 top-8 plus shared MoE is next.
7. Re-profile cache value, then retry P2. No new long P2 is eligible earlier.

The eventual Rust-owned runtime and direct quantized Metal path are documented
in [`docs/roadmap/PULSARMLX_STRATEGY.md`](../../docs/roadmap/PULSARMLX_STRATEGY.md).
They remain deferred from Feature 016: this feature first finishes the
vectorized Python/MLX reference ladder and P2 correctness/reuse gate.

## Retained P2 streaming profile (experimental)

- 16 GiB logical decoded shared-expert cache
- routed experts streamed one matrix at a time and released after evaluation
- ≥24 GB OS/runtime headroom
- no prefetch until the two-token reuse gate passes

## Risk register

| Risk | Mitigation |
| --- | --- |
| Insufficient internal free space | Formal admission gate; no external copy |
| Sharded GGUF vs single-file | Prefer single-file if available; else multi-shard reader |
| DSA/MLA semantics mismatch | Freeze contract from source; unit fixtures in CI |
| Memory pressure / swap | Abort benchmark if pressure critical |
| Silent CPU fallback | Explicit backend assertion in performance mode |

## Deferred

- M2 Max 64 GB
- External NVMe RAID comparisons
