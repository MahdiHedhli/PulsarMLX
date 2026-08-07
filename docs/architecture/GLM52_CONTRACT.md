# GLM-5.2 Architecture Contract

**Status**: **DRAFT — not frozen**
**Blocked on**: disk admission + checkpoint open
**Date**: 2026-08-07

This document will become the frozen source of truth for PulsarMLX GLM-5.2
correctness once the immutable checkpoint is admitted and GGUF metadata is
parsed. Until then, values below are provisional research notes only.

## Do not claim

- Full-model GLM support
- Generation quality
- Tokens/sec production performance
- Bit-parity with any fused CUDA path

## Provisional structure (to be confirmed from GGUF KV)

| Topic | Provisional | Confirm via |
| --- | --- | --- |
| Arch id | `glm-dsa` | `general.architecture` |
| Attention | MLA (latent KV) | attn_* tensor shapes |
| Sparse | DSA lightning indexer, top-k rows | indexer tensors + graph |
| FFN | MoE experts + shared | ffn_*_exps, expert_count |
| Quant | UD-IQ2_XXS mixed IQ blocks | tensor types |
| Layers | ~79 class (upstream notes) | `*.block_count` |

## Residual form (hypothesis)

Pre-norm style residual around attention and MoE similar to modern decoder
blocks; exact order must match the checkpoint graph (upstream Pulsar
`glm-dsa` donor, not Qwen3MoE).

## Numerical contract (planned)

- Architecture path: dequant weights to compute dtype × f32 (or documented)
  activations for independent CPU oracle.
- Accepted tolerances: freeze before measurement.
- Implementation-specific fused differences: root-cause and ledger (F008 pattern).

## Streaming contract (planned)

- Expert-level addressing and eviction
- Bounded compressed expert cache
- No silent full-model materialization
- No silent CPU fallback in performance mode

## Freeze checklist

- [ ] Checkpoint SHA set recorded
- [ ] All KV keys extracted
- [ ] Tensor catalog complete
- [ ] Upstream source revision pinned
- [ ] Tolerances published
- [ ] Status flipped to **frozen** with commit SHA
