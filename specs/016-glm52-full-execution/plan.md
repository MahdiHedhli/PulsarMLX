# Implementation Plan: 016-glm52-full-execution

## Status

**Blocked** at Phase 1 (disk admission). Qwen baseline frozen at tag
`v0.2.0-qwen30b-e2e-research` (commit `493234a`).

## Phases

| Phase | Name | Gate |
| --- | --- | --- |
| 0 | Preserve Qwen baseline + tag | Done |
| 1 | Internal SSD disk admission | **Failed** — stop download |
| 2 | Immutable checkpoint acquisition | Blocked on Phase 1 |
| 3 | M1 Ultra streaming runtime | Spec/design may proceed offline |
| 4 | Architecture contract freeze | Offline from upstream + GGUF once present |
| 5 | Correctness ladder C01–C11 | Requires checkpoint |
| 6 | Full execution evidence | Requires C09–C11 |
| 7 | Performance + publication + `v0.3.0` tag | Requires Phase 6 |

## Technical approach (when unblocked)

1. **Acquire** `UD-IQ2_XXS` shards (or single-file DS4 equivalent) to internal
   SSD via atomic `.partial` → validate → rename; set `PULSARMLX_GLM_GGUF`.
2. **Runtime**: positional GGUF reads, expert-level residency, compressed expert
   cache (~48 GB start profile), stream remaining layers, MLX-only performance
   path, CPU oracle for bounded parity only.
3. **Contract**: derive `docs/architecture/GLM52_CONTRACT.md` from GGUF KV +
   upstream Pulsar `glm-dsa` (MLA, DSA indexer, routing, shared experts).
4. **Validate** C01→C11 with per-layer drift metrics; stop on material divergence.
5. **Benchmark** cold/warm TTFT, prefill, decode; publish under `docs/research/glm52/`.

## Initial streaming profile (experimental)

- 48 GB compressed expert cache
- 16 fully streamed layers (tune from evidence)
- ≥24 GB OS/runtime headroom
- Configurable: total UM budget, prefetch depth, max in-flight expert reads

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
