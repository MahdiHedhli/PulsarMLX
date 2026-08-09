# Research Notes: 016-glm52-full-execution

## Checkpoint candidates (2026-08-07)

### Preferred quant: `GLM-5.2-UD-IQ2_XXS`

**Remote**: `unsloth/GLM-5.2-GGUF` path `UD-IQ2_XXS/`

| Shard | Bytes (HF LFS) |
| --- | ---: |
| `…-00001-of-00006.gguf` | 9,423,744 |
| `…-00002-of-00006.gguf` | 49,105,028,960 |
| `…-00003-of-00006.gguf` | 49,143,176,640 |
| `…-00004-of-00006.gguf` | 49,143,176,640 |
| `…-00005-of-00006.gguf` | 49,143,176,640 |
| `…-00006-of-00006.gguf` | 41,914,650,304 |
| **Total** | **238,458,632,928** (~222.082 GiB) |

Architecture metadata (HF card): `glm-dsa`, ~754B params.

**Local**: the six admitted shards are present on the internal SSD. Their exact
sizes, per-file SHA-256 values, and checkpoint-set hash are frozen in
`docs/validation/glm52-checkpoint.json`. The remote revision was not recorded
at acquisition. A later metadata-only check established that all six local
hashes match the six LFS etags at immutable revision
`abc55e72527792c6e77069c99b4cb7de16fa9f23`; the append-only binding is
`docs/validation/glm52-revision-binding.json`.

### Single-file note (upstream README)

Upstream Pulsar README also references a single-file antirez build
`GLM-5.2-UD-IQ2_XXS_RoutedIQ2XXS_blk78Q2K.gguf` (~197 GB class). Evaluate only
if disk gate passes and identity/hash can be pinned. Do not switch to Unsloth
11-shard Q4.

## Original disk admission (internal APFS; superseded)

| Metric | Value |
| --- | --- |
| Free before cleanup | ~338.4 GiB |
| Safe cleanup | ~7.3 GiB (Qwen `.partial` + Rust `target/`) |
| Free after cleanup | ~345.8 GiB |
| Required before download | **500 GiB** |
| Required after checkpoint | **250 GiB** |
| Projected free after 222 GiB download | ~124 GiB |
| **Initial result** | **failed; later resolved and passed** |

The initial stop was preserved as evidence. A later safe space-clearance pass
met the gate without weakening it; acquisition then completed.

## Architecture (from public upstream notes; freeze after GGUF open)

- **Attention**: MLA (multi-head latent attention) with compact KV.
- **Sparse**: DSA “lightning indexer” — top-k row selection; contexts beyond
  naive dense ceilings.
- **MoE**: routed experts + shared experts (exact counts from GGUF KV).
- **Quant**: UD-IQ2_XXS dynamic 2-bit style; mixed expert tensors possible.
- **Runtime implication**: expert streaming + attention residency budgeting;
  model >> 128 GiB UM → must not load all experts resident.

## Independent oracle policy

- Bounded primitives: pure CPU / NumPy dequant + matmul, no MLX imports.
- Full-model: independent captures and/or trusted external reference engine;
  never define reference as copy of MLX output.
- Implementation-specific fused differences → root-cause + document (F008 style).

## Resolved architecture questions

The shared-expert layout, routing normalization, and DSA tensor/state contract
were resolved by C01–C11 and are frozen in `docs/architecture/GLM52_CONTRACT.md`.
The alternate single-file build was not downloaded and remains out of scope.
