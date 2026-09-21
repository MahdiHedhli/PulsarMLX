# Sparse attention with lightning indexer (Flash AN, Graph 10, slice 1)

`Glm5NextSparseAttention` (NoPE MLA with `q_lora`/`kv_lora` latents, `embed_q`/
`unembed_out` head projections and the `Glm5NextIndexer` top-k selector) is
qualified as one prefill forward pass under the supervised successor harness
(`successor.py sparse`) against an independent stdlib oracle
(`scripts/research/glm53_flash/decoder_sparse/oracle.py`). The capsule holds
the upstream indexer class unchanged and the attention class renamed only
(canonical-AST equality for both). `MultiLinear` is taken whole from the
retained mlx-vlm `mla.py` and `scaled_dot_product_attention` from the retained
mlx-vlm `base.py` (pinned `8d79dbcf`, sha256 `da01333e…` and `9f1e42ad…`),
each by canonical-AST identity with a global census. `QuantizedMultiLinear`,
the TurboQuant cache classes, `_turboquant_attention_applies` and
`quantized_scaled_dot_product_attention` are refused stubs whose refusal is
asserted; with no cache the executed attention is
`mx.fast.scaled_dot_product_attention` with the model's boolean causal mask
(`create_causal_mask(N)`, rebuilt in the controls as `linds >= rinds`).

Two fixtures at hidden 8, 2 heads of dim 4, latents of rank 4, 2 indexer heads
of dim 4, `index_kpool` 2, `index_topk` 4, always-select-tail on:
`sparse-bypass-s4` (S=4 <= topk: the indexer bypasses and attention is dense
causal) and `sparse-kpool2-topk4-s7` (S=7: three complete pools and one
partial pool; top-2-of-3 pool selection from t=5; the tail is the only route
to t=0's own key and to token 6 at t=6). Selection margins 0.094 and 0.053
(minimum required 0.02). Observed boundaries: the normalised query latent, the
normalised kv latent, the indexer's token indices (exact, including the -1
padding and the bypass), the attention concat entering `o_proj` and the
output; all within the 1e-4 allowance on CPU and Metal (measured 1.4e-7 to
2.8e-7).

The kill matrix was filled prospectively: for each of six capsule mutants the
equivalent edit was applied to the frozen oracle text (recorded in the
fixture as `oracle_variants`) and classified with the controls' thresholds
before any candidate run; the offline CI module re-derives every cell from
those variants. All twelve cells match on both backends, and the observed
kill magnitudes agree with the oracle-variant predictions to three or four
digits (e.g. relu omitted 0.4433 vs 0.44329; sparse mask ignored 0.2866 vs
0.28664). `indexer-scale-omitted` is a designed inactive control (a positive
scale cannot change pool ordering through ReLU). For `tail-selection-omitted`
the oracle variant rejects the fixture (t=0 has an empty attention row) while
MLX's fused attention returns a finite value for a fully masked row; both are
kills, and the difference is noted here rather than hidden.

Not covered: decode (L=1, absorbed queries, `KVCache` latent cache, the
indexer cache and its incremental `_pool`), padding masks, batch > 1,
`index_kpool_compress=False`, RoPE MLA (refused upstream), quantized or
TurboQuant caches, and any real-model claim.
