# GLM-5.3-Flash tiny reference mini-contract

Status: scoped research contract, predeclared before arithmetic execution.

This contract covers only the checkpoint-free toy cases named below. It does not
claim model support, real-checkpoint parity, production storage layout, BF16/MLX
arithmetic parity, or a complete 45-layer execution graph. The accompanying
source inventory is complete only at the already-validated indexed-name/pattern
level: 2,998 indexed names, language layers 0 through 44, and vision blocks 0
through 23. The executable graph here is deliberately smaller.

The retained source-lock was mechanically corrected and validated at SHA-256
`f7708546c13ea90fc0a4abc0f3152f596f3d8818eae87bc75b3f05e8490f6f11`.
The source bytes used for this contract match the listed digests: selected
config `3ed164a8f60c96dc81d5742b952b7823335fa7656fe0bbcf69c7ea05a4179d1d`,
selected index `5e0a3768db6fb795c4846bed713785a17d336f4cc4494b4f6b28f75082314383`,
runtime `language.py` `6de479b6eafc0731e5e965f01f28797a58eecb606e7d5d5657db13642c230196`,
mHC dependency `141fbe47d99f8eda9ab9a4c78665e5eb439cbf73b53a604c4da2a77845167bb3`,
and gated-delta dependency
`e15cd83bfc0bfff3de7a9563aa6978f7e39e0e248cc8a55ca9482f1ce18f54d8`.
No model payload or safetensors header supplied any shape in this document.

## Frozen equations

All arithmetic is scalar Python `float` (binary64). Inputs must be finite. Shape,
index, identity, and reset assertions are exact. Numeric comparisons use
`abs(actual-expected) <= 1e-12 + 1e-10*abs(expected)`.

`EQ-ROUTE` follows `Glm5NextMoEGate.__call__` and its
`group_expert_select` boundary. For hidden vector `x` and router rows `W_e`,
`logit_e=sum_i x_i W_ei`, `score_e=sigmoid(logit_e)`, and selection ranks
`score_e+bias_e`. The correction bias changes selection only. The returned
weight for each selected expert is its uncorrected score divided by the selected
uncorrected-score sum, then multiplied by 2.5. The tiny tie rule is increasing
expert index. This rule is frozen for the toy API because the retained imported
group-selection implementation is unavailable; it is an uncertainty rather
than a production-source claim.

`EQ-SPARSE` follows `Glm5NextIndexer._pooled_states`, `_visible_tail`, and
`__call__`. Pool size is two and selected token count is four in the toy case.
Each complete pool softmax-compresses `key` using `gate+ape` across the pool.
Candidate scores are `max(dot(query_head,pool_key)/sqrt(head_width),0)`, mixed
across index heads using `weights/sqrt(head_count)`, and ranked descending with
the same increasing-index tie rule. Selected pools expand in pool order to token
indices. Up to one visible incomplete-tail index is appended; invalid slots are
`-1`. A sequence of length at most four returns the distinct dense-bypass
`SparseResult` with `bypassed=true` and empty indices. The live fixture uses
sequence length seven, so top-k is smaller than
the sequence; the separate bypass fixture has length three. One leading invalid
token transfers the source's shifted-origin behavior. Interior validity holes
are explicitly rejected by the toy API. Incremental pool-cache reuse, general
padding, chunking beyond 512, and MLA gather/unembed are outside this toy API.

`EQ-KDA-GATE` follows `Glm5NextForgetGate.__call__` with the configured lower
bound: `g=-5*sigmoid(exp(A_log)*(a+dt_bias))`. `beta=sigmoid(b)`.

`EQ-KDA` follows the runtime's readable `recurrent_kimi_delta`: normalize query
and key by `v/sqrt(sum(v^2)+1e-6)`, scale query by `1/sqrt(Dk)`, decay the state
by `exp(g)`, compute `memory=sum_Dk(state*k)`, update with
`outer(k,(value-memory)*beta)`, then read with `sum_Dk(state*query)`. The toy
state has axes `[batch,head,key_width,value_width]` and uses unequal
`key_width=2`, `value_width=3`. The imported gated-delta dependency instead
documents `[batch,head,value_width,key_width]`; candidate adapters must transpose
at that boundary and tests must reject an unmarked convention change. The
convolution suffix owns the previous `kernel-1=3` projected tokens separately
from recurrent state. `EQ-CONV` follows the linear-attention boundary: prepend
the suffix (or zeros), apply channel-wise causal convolution, apply SiLU, and
retain the last three unactivated input tokens as the next suffix. Empty state,
two or more steps, prefix/incremental parity,
fresh reset, and interleaved independent streams are required.

`EQ-MHC` follows `_hc_split_sinkhorn_ops`, `_hc_ops`, and `hc_expand`. For
`C=4`, RMS-normalize the flattened four-stream residual with `rms_norm_eps=1e-5`,
project to 24 mixes, compute
`pre=sigmoid(mix[0:C]*scale[0]+base[0:C])+1e-6`,
`post=2*sigmoid(mix[C:2C]*scale[1]+base[C:2C])`, and reshape the remaining
16 values to a `C by C` matrix after applying `scale[2]` and `base`. Apply a
row softmax plus `1e-6`, normalize columns, then perform 19 further row/column
normalization pairs. Collapse is the pre-weighted sum over residual streams.
Expansion is `post*branch + transpose(comb)@residual`. The fixture uses a
non-identity transform.

`EQ-SWIGLU` follows `ClampedSwiGLU.__call__`:
`silu(min(gate,10))*clip(up,-10,10)`. Gate has only an upper clamp. Fixtures
include values below, at, and above both gate/up limits.

`EQ-COMPOSE` follows `Glm5NextMoE.__call__` and the decoder FFN boundary. Each
selected routed expert applies gate/up projections, `EQ-SWIGLU`, and a down
projection. `EQ-ROUTE` weights and sums those outputs. One independently
evaluated shared expert is added, then the residual is added. The test asserts
each producer-consumer handoff. It is one toy composition boundary, not a full
decoder layer.

## Typed edge contract

The machine-readable contract maps every tiny public API input and output to at
least one `source -> boundary -> test` edge. Each equation lists its edges, each
edge lists its tests, and each test reciprocally lists those edge and API IDs.
The validator rejects a missing or one-way mapping, duplicate IDs, unknown
ports, or an API without a test. Shapes use only the declared symbols and are
checked against batch <=2, sequence <=16, feature <=32, experts <=8, heads <=4,
and <=65,536 total elements. Group size 64 is forbidden in arithmetic shapes and
reserved for the separate storage contract.

Every `tiny_*_ceiling` constant is a local admission ceiling, not a report of
the dimensions exercised by every fixture. Exact exercised dimensions are on
the individual tensor-boundary records. Renaming these fields does not change
their values, the frozen fixture, or the numerical criteria.

The tensor metadata is a small role inventory for only these cases. Layer 0 is
used for KDA; layer 3 is used for sparse attention and MoE. The validator checks
those coordinates against the retained layer sets and rejects layer 45. It also
rejects unknown fields, roles, tensor names, source functions, state ownership,
precision descriptors, and quantized companions. No field receives a default.
Indexed tensor shapes are labeled `source-derived-logical`; they are never
presented as observed stored shapes or offsets.

Precision remains part of the boundary: routed gate/up/down are selected 4-bit
affine with group-64 scale/bias companions. The selected index has only the
router gate weight and its protected FP32 correction bias, without scale/bias
companions; the retained aggregate reconciliation classifies that weight as an
original-precision-sensitive BF16 role. Runtime `quant_predicate` requests
8-bit if a future conversion quantizes `mlp.gate`, which is a policy boundary,
not selected-artifact storage evidence. The toy API starts at logits and does
not execute that matmul. Shared and other quantized toy projections are 8-bit
affine. mHC base/scale and KDA
`A_log`/`dt_bias` are protected FP32; mHC `fn`, convolution, norms, raw indexer
pool tensors, and vision are original-precision-sensitive unquantized roles.
Vision is BF16 in the retained aggregate reconciliation and is not exercised.

## Predeclared tests and seeds

The fixed semantic seed is `20260908`; the independent-stream and deterministic
metadata-mutation seed is `20260909`. Tests do not use ambient randomness.

- `T-CONTRACT-VALID`: canonical JSON validates and every API, equation, edge,
  tensor boundary, and test has a reciprocal mapping.
- `T-CONTRACT-REJECT`: deterministic single mutations reject extra/missing
  fields, duplicate IDs, unknown roles/names/functions/ports, unsupported
  precision or companion sets, layer-role mismatch, layer 45, shape overflow,
  and one-way mappings. Errors must name the failing JSON path.
  The added cases reach `$.apis[*].test_ids` for missing reciprocity,
  `$.apis[route_scores].outputs` for an uncovered port, and the indexed KDA
  tensor's `.layer` path for a mismatched coordinate. A layer-45 indexed name
  is rejected first at its `.name` path because this version's exact name
  allowlist intentionally makes the later 0-through-44 coordinate guard
  unreachable for an invented tensor name.
- `T-ROUTE`: correction changes selected IDs while gathered weights remain the
  uncorrected scores; exact tie order and IDs; non-ties exceed the rounding
  margin; normalized weights sum to 2.5 within the frozen tolerance.
- `T-SPARSE`: length-seven live selection at query positions 3, 4, and 6 with
  pool size two, top-k four, complete pools and tail; exact index order and
  `-1`; leading-invalid transfer and separate length-three bypass.
- `T-KDA`: empty state, convolution suffix length three, nonzero recurrence,
  at least two steps, incremental/prefix parity, fresh reset identity, and two
  interleaved independent sequences; exact state shape with unequal widths.
- `T-MHC`: non-identity collapse/expand, Sinkhorn normalization, and configured
  epsilons; finite rejection.
- `T-SWIGLU`: below/at/above clamp boundaries and nonfinite rejection.
- `T-COMPOSE`: routed and shared gate/up/SwiGLU/down paths plus residual, with
  explicit producer-consumer checks.

Any fixture-construction failure is recorded separately from a semantic
failure. Thresholds and seeds are immutable for this version and must not be
changed after outputs are observed.

## Source facts and open limits

Retained config/source facts are: 45 language layers; 34 KDA layers; 11 sparse
layers; dense MLP layers 0-2 and MoE layers 3-44; 288 routed experts with top-8,
one shared expert, normalized sigmoid routing scaled by 2.5; `hc_eps=1e-6`,
`hc_sinkhorn_iters=20`, `rms_norm_eps=1e-5`, indexer LayerNorm epsilon `1e-6`,
KDA L2 epsilon `1e-6`, KDA lower bound `-5`, and clamp limit 10.

The config contains `num_nextn_predict_layers=1` and
`index_share_for_mtp_iteration=true`, but the validated index census contains no
`mtp`, `nextn`, `next_n`, or `predict` name, and layer IDs stop at 44. MTP is
therefore omitted from this slice; the configuration fields are recorded as an
unresolved control-plane discrepancy, not used to invent layer 45 or weights.
Exact stored tensor shapes, dtypes, offsets, word ordering, producer version,
and production tie behavior remain unknown under the no-header/no-unretained-
source boundary.
