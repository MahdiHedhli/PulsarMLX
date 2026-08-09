# Implementation Plan: 016-glm52-full-execution

## Status

**Active** at Phase 8 closeout (weekend inference optimization). Qwen remains frozen at
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
| 8 | Inference optimization | Active closeout; golden eight and derived profile passed, design remains |

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
   `a8a3d71`, and **layer-3 top-8 plus shared MoE passed** at source `b675365`.
   The **complete transformer layer passed** at source `a589dcf`; the faster P1
   **full-stack golden-token run passed** at source `99751b9`.
7. Re-profile cache value. **Passed**: Q6_K is now the leading quantified
   format, while all 228 protected shared matrices hit in the warm stack and
   avoided 11.476 GB of decoded materialization. The cache remains enabled.
8. Retry P2. **Passed** at source `d5e1cf3`: exact `[9703,21615,220]`,
   228 shared hits per warm stack, and zero CPU fallbacks.
9. Run the full golden eight. **Passed** at source `1a2ca76`: exact full
   sequence, nine complete 79-layer stacks, 1,824 shared hits, zero CPU
   fallbacks, and normal retained resource states.
10. Derive cold/warm observations and expert-cache-only quant deltas, quantify
    the uninstrumented trunk residual, resolve prefetch by evidence, then
    publish the final optimization report and Rust boundary design. **Derived
    profile passed**: eight snapshots, seven monotonic warm intervals, no
    counter resets, 87.18% median warm trunk residual, and 0.20% mean warm
    storage share. Prefetch is therefore deferred and Feature 018 remains
    profile-neutral pending trunk fixture measurements.

The eventual Rust-owned runtime and direct quantized Metal path are documented
in [`docs/roadmap/PULSARMLX_STRATEGY.md`](../../docs/roadmap/PULSARMLX_STRATEGY.md).
They remain deferred from Feature 016: this feature closes the vectorized
Python/MLX golden-eight reference evidence and its measured follow-up.

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
