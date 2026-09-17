# 45-layer topology at tiny width (Flash AN, Graph 16, slice 1) — structural only

This graph has **no numeric reference** and is not an oracle qualification.
It instantiates the admitted `LanguageModel` with the retained GLM-5.3-Flash
config's real layer pattern (45 layers; `linear_attention` everywhere except
`deepseek_sparse_attention` at 3, 7, 11, …, 43; dense `ClampedMLP` for the
first three layers and `Glm5NextMoE` for the other 42; `hc_mult` 4,
`hc_sinkhorn_iters` 20, the real router and indexer fields), every width
tiny (hidden 8, vocab 16, 4 experts top-2, 2 heads, latent rank 8, indexer
kpool 4 / topk 8), with 1,315 parameters drawn by the candidate's `mx.random`
from the frozen init recipe, under the supervised successor harness
(`successor.py topology`).

What it establishes, on CPU and Metal: construction with the expected
per-layer attention and MLP types; `make_cache()` returns 45 caches routed
by type; logits are finite; a 5-token prefill followed by five one-token
steps equals ten single-token steps at every position within 3.7e-6 (CPU) and 1.6e-6 (Metal) in the supervised runs — causal
self-consistency through all 45 layers, both cache kinds, the indexer's
sparse regime (reached at T ≥ 9 in every sparse layer, pools at T=10) and
the compiled decode FFN on every layer (compilation is real on Metal only:
under the fence the CPU JIT is inert, see decoder-stack-decode.md); the linear layers' cache slots are
populated and every `KVCache` ends at offset 10. Two structural controls:
swapping the mask routing is rejected (the linear layer cannot consume the
attention mask), and dropping the layer caches breaks the equivalence
(3.28).

The schedule keeps every call inside the admitted linear-attention Metal
kernel domain (S ≤ 5 per call); the first version scheduled a 6-token and a
10-token prefill and was rejected at first Metal contact
(`MODULE_KERNEL_DOMAIN`), so the comparison is prefill 5 + decode 5 against
stepwise 10 rather than against a single 10-token prefill (recorded in the
fixture's `revision`; on CPU the v1 schedule had already shown the same
equivalence at 2.4e-6 before the change).

Not established: any numerical correctness beyond self-consistency; the real
widths; the linear reference domain at deeper layers (which is why no oracle
composes here); padding or batch > 1; any real-model claim.
