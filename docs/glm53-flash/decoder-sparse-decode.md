# Sparse attention decode with caches (Flash AN, Graph 12, slice 1)

The same admitted `Glm5NextSparseAttention`/`Glm5NextIndexer` capsule as
[decoder-sparse.md](decoder-sparse.md) is qualified for decode under the
supervised successor harness (`successor.py sparse-decode`): a 2-token prefill
with the causal mask and a fresh `CacheList(KVCache(), KVCache())` (the
admitted cache classes, see [decoder-stack.md](decoder-stack.md)), then five
one-token steps with mask `None` (what `KVCache.make_mask` returns for N=1).
The latent cache is fetched and attended through the absorbed-query form
(`embed_q(q)` against the cached latents, then `unembed_out`); the indexer
cache holds the packed key/gate/valid rows; the indexer's pool state
(`cache._pool`) follows the incremental rule (complete pools kept, the suffix
recomputed from `s0 = (t_prev // kpool) * kpool` with indices offset).

The reference (`scripts/research/glm53_flash/decoder_sparse_decode/oracle.py`)
models that cache and pool state explicitly. The fixture (kpool 2, topk 2,
S=7, prefill 2) makes the prefill a bypass, the first decode step a full
pooling, and the later steps incremental with suffix pools selected at t=3 and
t=6 and `-1` padding at t=3 and t=5. The generator and the offline CI test
assert, row by row, that the incremental reference equals the frozen prefill
reference on the whole sequence (indices, allowed sets and outputs to 1e-12):
the incremental rule is proven equivalent to full pooling on this fixture
independently of the candidate.

Observed per step on CPU and Metal: qr and kv latent, the exact token indices
(or bypass), the attention concat entering `o_proj`, the output, and after
every non-bypass step the candidate's `_pool` against the reference's pool
state (indices and validity exact, keys within 1e-4) plus a candidate-internal
check that the incremental `_pool` equals a full `_pooled_states`
recomputation over the cache (within 1e-6). All within the 1e-4 allowance
(measured 6e-8 to 2e-7); both caches end at offset 7.

The 7×1 matrix was filled prospectively from oracle variants over the whole
schedule, including which steps each variant changes; all seven cells match
on both backends and the changed-step sets match for five of the seven.
Two nuances are recorded rather than tuned away: the `decode-unembed-omitted`
oracle variant was coarser than the capsule mutant (it also altered the
prefill rows, which the L=1-only mutant cannot touch), and
`stale-partial-pool-kept` is rejected by the candidate (an `argmax` over an
empty suffix) where the reference variant produced a wrong value; both are
kills. Two cells are designed inactive controls (recomputing one extra stable
pool; disabling the incremental path).

Not covered: padding masks (`_no_pad` False), batch > 1 and the batch-axis
`_pool` rebuild, multi-token decode chunks, `bypass_short` False, quantized
caches, and any real-model claim.
