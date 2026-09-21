# Two-layer model stack and make_cache (Flash AN, Graph 11, slice 1)

`Glm5NextDecoderLayer` and `Glm5NextModel` (unchanged) and `LanguageModel`
(renamed only; canonical-AST equality for all three) are qualified as one
prefill forward pass through a two-layer stack under the supervised successor
harness (`successor.py stack`): embedding → hyper-connection broadcast →
layer 0 (`linear_attention`, dense `ClampedMLP`) → layer 1
(`deepseek_sparse_attention` with the lightning indexer, `Glm5NextMoE`) →
mean over the residual streams → final `RMSNorm` → `lm_head` → logits. Every
constructor the capsule reaches is an already-admitted class from the
linear-attention, sparse-attention, MoE, dense-FFN and cache tracks; `KVCache`,
`CacheList` and `create_causal_mask` are taken whole from the retained mlx-vlm
`cache.py`, and `create_attention_mask`, `create_ssm_mask` and
`LanguageModelOutput` from the retained mlx-vlm `base.py`, each by
canonical-AST identity with a global census. `DSV32Model.sanitize`, the batch
and quantized cache classes and `KVCache.to_quantized` are refused stubs whose
refusal is asserted.

The oracle (`scripts/research/glm53_flash/decoder_stack/oracle.py`) is a
composition of the accepted references only: the decoder-layer reference for
layer 0 (which itself calls the accepted linear-attention and dense-FFN
references), the decoder-layer reference's hyper-connection arithmetic for
layer 1, the sparse-attention reference and the MoE reference (over the
accepted router selection); it adds only the embedding gather, the mask
routing (`None` for the linear layer, causal for the sparse layer), the
stream mean, the final norm and the `lm_head` projection. One fixture at
vocab 8, hidden 4, two residual streams, four tokens, with layer-0
parameters drawn from the decoder-layer generator's accepted family and
embeddings as one-negative-lane sign patterns so the first attention input is
inside the linear reference's domain; the sparse layer runs at kpool 1 /
topk 2 (it selects `[[0],[0,1],[0,1],[0,2]]`), the MoE at 4 experts top-2;
the clamp is active in both layers (10 and 28 elements).

Observed boundaries: layer-0 output streams, layer-1 attention-input norm,
the indexer's token indices (exact), the attention output, the x1 streams
(observed at the `_ffn_block` entry), the FFN-input norm, the MoE output, the
layer-1 output streams, the pooled state, the final norm and the logits
(both the wrapped `lm_head` output and the returned `LanguageModelOutput`);
all within the 1e-4 allowance on CPU and Metal (measured 1.4e-7 to 1.1e-6).
`make_cache()` on the real `LanguageModel` returns
`[ArraysCache(size=2), CacheList(KVCache(), KVCache())]` with the admitted
classes, matching the layer types.

The 6×1 kill matrix was filled prospectively from oracle variants recorded in
the fixture; all cells match on both backends and the kill magnitudes agree
with the predictions to three or four digits (stream-0 pooling 0.4607 vs
0.46068; final norm omitted 1.385 vs 1.38548; tied head 3.178 vs 3.17837).
Two cells are designed inactive controls: sum-instead-of-mean pooling is
absorbed by the final RMSNorm, and intersecting the sparse mask with the
causal mask is a no-op because the indexer only selects causally visible
positions. Giving the linear layer the attention mask is rejected by the
candidate (a concatenate shape error) and unmodelled by the reference: both
kills.

Not covered: decode (the compiled decode-step FFN gate, `KVCache` and indexer
caches in use, the `ArraysCache` across steps at model level), padding,
batch > 1, `num_logits_to_keep`, `sanitize`/weight loading, the MTP head,
quantized paths, and any real-model claim. This is a two-layer synthetic
stack; the 45-layer configuration is not instantiated.
