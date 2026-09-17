# Two-layer stack decode with make_cache caches (Flash AN, Graph 13, slice 1)

The admitted two-layer stack of [decoder-stack.md](decoder-stack.md) is
qualified for prefill-then-decode under the supervised successor harness
(`successor.py stack-decode`): a 2-token prefill and two one-token steps on
the graph-11 fixture, with the caches exactly as `LanguageModel.make_cache()`
returns them (no `prepare`/`left_padding`, as in single-stream generation):
`ArraysCache(size=2)` for the linear layer (its SSM mask is `None`) and
`CacheList(KVCache(), KVCache())` for the sparse layer, whose
`KVCache.make_mask` yields the causal mask at prefill and `None` at decode
through the cache module's own `create_attention_mask` (the binding fixed in
`ad67fc69`). The decode steps take the compiled `_ffn_block` path
(`compile_ffn` at B=1, S=1).

The reference re-slices the frozen stack reference into the schedule (every
stage is causal, so the logits at position t are those of the whole-sequence
reference) and adds the accepted linear-attention reference's per-time cache
states as comparison-only values. Observed on CPU and Metal: logits at every
position (1.4e-7 to 3.0e-7), the linear `ArraysCache` slots after each step
against the reference's `cache0`/`cache1` (atol 1e-4, rtol 1e-5) and the
final cache, `KVCache` offsets 2→3→4 on both latent and indexer caches, the
cache routing by layer type, and that `_ffn_c` is absent after the prefill
and present after the first decode step in both layers.

The 6×1 matrix was filled prospectively from oracle variants; all cells match
on both backends with matching changed-step sets. Two cells are designed
inactive controls (forcing the eager FFN path; recompiling every step): the
reference has no compile distinction, so these establish that the compiled
decode block equals the eager block. Dropping the layer caches kills at the
decode steps only; normalising before the stream mean kills everywhere;
misrouting the cache list and a one-slot linear cache are rejected by the
candidate and unmodelled-by-construction in the reference.

Not covered: padding and batch > 1 (`prepare`/`left_padding`, batch-axis
pool rebuild), multi-token decode chunks, `num_logits_to_keep`, quantized
caches, the 45-layer configuration, and any real-model claim.
