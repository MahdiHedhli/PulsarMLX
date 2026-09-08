# GLM53-Flash tiny scalar oracle equations

Status: preregistered before arithmetic. Concrete inputs and acceptance
criteria are frozen in `fixtures-and-criteria.md`; this document does not
define a competing fixture set.

The oracle is a standard-library binary64 implementation. It never imports the
candidate and shares no disputed numerical helper with it. Finite scalars use
`abs(actual-reference) <= 1e-12 + 1e-10*abs(reference)`. IDs, index order,
shapes, bypass flags, state positions, and reset identity are exact. Every
input and intermediate, including every dot-product product and running sum,
must remain finite. Limits are sequence 16, feature width 32, experts 8, heads
4, and 65,536 numeric elements per call.

## Verified sources

The retained bytes matched the corrected source lock before interpretation.
The corrected lock SHA-256 is
`f7708546c13ea90fc0a4abc0f3152f596f3d8818eae87bc75b3f05e8490f6f11`.

| Role | Identity | File SHA-256 | Cited lines |
| --- | --- | --- | --- |
| Runtime | `PipeNetwork/glm53-flash-mlx@a61a7c7d2fbdf3d218a9909365a24bd794f3a247`, `glm5_next/language.py` | `6de479b6eafc0731e5e965f01f28797a58eecb606e7d5d5657db13642c230196` | 24–174, 252–307, 310–502, 639–690 |
| Parity evidence | same revision, `tests/test_parity.py` | `d7e0a73a51c31d74b7ec887fe21192101a7fc7650f98777258d6446f3937bfc9` | 1–41, 64–84, 135–182 |
| Observed mHC dependency | `Blaizzy/mlx-vlm` main observed at `8d79dbcf82a7885ddfc56fb4a55440fa9c5dfb90` | `141fbe47d99f8eda9ab9a4c78665e5eb439cbf73b53a604c4da2a77845167bb3` | 183–265 |
| Observed gated-delta dependency | same observation | `e15cd83bfc0bfff3de7a9563aa6978f7e39e0e248cc8a55ca9482f1ce18f54d8` | 8–17, 133–175, 221–300 |

The observed dependency revision is design evidence because the runtime
follows mutable `mlx-vlm` main. The runtime imports
`deepseek_v32.language.group_expert_select`, but that file is absent from the
digest-validated evidence. Grouped routing beyond the selected
`n_group=topk_group=1` is omitted. Upstream router and MLX `argsort` tie
stability are unqualified; this toy contract chooses ascending ID for ties.
MLX Conv1d implementation bytes are also absent, so the tap orientation below
is an explicit imported convention awaiting a pinned comparison.

## Public types and APIs

All arrays are rectangular lists or tuples on one sequence. Returned arrays
are tuples. `Dk` and `Dv` are deliberately unequal in the frozen KDA case.

```python
RouteResult(ids[K], raw_scores[E], corrected_scores[E], weights[K])
SparseResult(indices, bypassed, requested, returned)
ConvResult(outputs[T,C], suffix[W-1,C])
KdaResult(outputs[T,Dv], state[Dk,Dv], position, decays[T,Dk], betas[T])
MhcResult(collapsed[D], pre[R], post[R], comb[R,R], mixes[(2+R)R])
MlpWeights(gate[I,D], up[I,D], down[D,I])
MlpTrace(gate[I], up[I], activated[I], output[D])
CompositionResult(output[D], route, selected_traces, shared_trace,
                  routed[D], shared[D], branch[D])

route_tokens(logits, correction_bias, top_k, scaling_factor,
             *, normalize=True) -> RouteResult
route_scores(scores, correction_bias, top_k, scaling_factor,
             *, normalize=True) -> RouteResult
sparse_select(keys, gates, ape, queries, head_weights, valid,
              query_position, top_k, pool_size, *, always_tail=True,
              current_query_valid=True, bypass_short=True) -> SparseResult
causal_conv_silu(inputs, kernels, suffix=None) -> ConvResult
kda_sequence(q, k, v, a, b, A_log, dt_bias, *, lower_bound=-5.0,
             state=None, position=0, l2_eps=1e-6) -> KdaResult
mhc_collapse(streams, fn, scale, base, *, sinkhorn_iters=20,
             norm_eps=1e-5, hc_eps=1e-6) -> MhcResult
mhc_expand(branch, streams, post, comb) -> tuple[R,D]
clamped_swiglu(gate, up, limit=10.0) -> tuple[I]
clamped_mlp(x, gate_weight, up_weight, down_weight,
            limit=10.0) -> MlpTrace
compose_moe_residual(x, residual, logits, correction_bias, experts,
                     shared_expert, top_k, scaling_factor, *,
                     limit=10.0) -> CompositionResult
```

All result and weight records are frozen dataclasses.

The shared domain actually qualified by the frozen fixtures is narrower than
the oracle's reusable validation surface. The candidate accepts only scalar
`A_log`, convolution kernel widths 2 through 4, clamp limit exactly `10.0`, and
`l2_eps` exactly `1e-6`. The oracle additionally accepts vector `A_log`, kernel
widths through 16 (including width 1), any positive finite clamp limit, and any
positive finite `l2_eps`. Those oracle-only domains are untested and
unqualified; agreement is claimed only for the frozen scalar `A_log`, width-4
kernel, limit `10.0`, and `l2_eps=1e-6` cases. Neither implementation's behavior
outside that intersection is evidence about the selected runtime.

## OR-R01: routing

The runtime computes FP32 logits `x @ router_weight.T` and passes them with
the correction bias to the imported selector (`language.py:54–62`). At the
selector boundary:

```text
p[e] = sigmoid(logit[e])
s[e] = p[e] + correction_bias[e]
ids = first K experts by (s descending, expert ID ascending)
w[j] = scaling_factor * p[ids[j]] / sum_m p[ids[m]]
```

With normalization disabled, omit the denominator. Correction affects only
selection; weights use uncorrected sigmoid scores. `route_scores` starts from
supplied `p` so the exact tie fixture does not depend on transcendental
construction. Routed aggregation is `sum_j w[j]*expert(ids[j],x)`
(`language.py:82–88`).

## OR-S01: sparse pooled selection

Shapes are keys and gates `[T,Di]`, APE `[pool_size,Di]`, queries `[H,Di]`,
head weights `[H]`, validity `[T]`, and one absolute query position. This starts
after learned projections and covers `language.py:330–380,382–502`.

Let `f` be the first valid token. Pool `p` contains
`pos=f+p*pool_size+j` and is valid only when every position exists and is
valid. Compression uses a separate softmax across tokens for each feature:

```text
l[p,j,d] = gates[pos,d] + ape[j,d]
a[p,j,d] = softmax_j(l[p,:,d])
pool_key[p,d] = sum_j a[p,j,d]*keys[pos,d]
head_score[h,p] = max(dot(queries[h],pool_key[p])/sqrt(Di),0)
pool_score[p] = sum_h head_weights[h]/sqrt(H)*head_score[h,p]
```

Only complete pools whose last position is `<=query_position` are eligible.
Choose `top_k//pool_size` by `(score descending,pool ID ascending)`, expand
each in pool order into the first `top_k` slots, and use `-1` for unused slots.
If enabled, append the visible partial-pool tail in ascending order, with
`pool_size-1` fixed tail slots. False `current_query_valid` yields only `-1`.
`T<=top_k` returns `bypassed=True` and is not sparse-selection evidence
(`language.py:403–409`). Optimized pool reuse, projections, cache batch
transforms, and MLA attention are omitted.

## OR-C01: causal depthwise convolution

Inputs are `[T,C]`, kernels `[C,W]`, and suffix `[W-1,C]`, oldest to newest.
Tap zero multiplies the oldest element and tap `W-1` the current one:

```text
window = concat(suffix_or_zeros,inputs)
conv[t,c] = sum_j window[t+j,c]*kernels[c,j]
outputs[t,c] = silu(conv[t,c])
new_suffix = last W-1 raw input rows of window
```

This follows `language.py:267–281`. It covers prefix/incremental equivalence
and exact raw suffix state, not projection fusion or masks.

## OR-K01: KDA

Shapes are Q/K/A `[T,Dk]`, V `[T,Dv]`, B `[T]`, `dt_bias[Dk]`, and state
`[Dk,Dv]`. The qualified toy boundary uses scalar `A_log`, broadcast across
`Dk`; the implementation's optional vector form is not exercised or qualified.

```text
qhat = q/sqrt(sum(q^2)+l2_eps)/sqrt(Dk)
khat = k/sqrt(sum(k^2)+l2_eps)
beta = sigmoid(b)
decay[k] = exp(lower_bound*sigmoid(exp(A_log)*(a[k]+dt_bias[k])))
S[k,v] = S[k,v]*decay[k]
memory[v] = sum_k S[k,v]*khat[k]
delta[v] = (value[v]-memory[v])*beta
S[k,v] = S[k,v]+khat[k]*delta[v]
output[v] = sum_k S[k,v]*qhat[k]
```

The public `[Dk,Dv]` state follows the readable local recurrence at
`language.py:136–174`. The observed imported implementation uses `[Dv,Dk]`
(`gated_delta.py:133–175,221–300`); integration requires an explicit transpose.
Unequal frozen `Dk=2,Dv=3` makes this observable. The lower-bound equation is
the actual imported update path (`gated_delta.py:13–17`). Position advances by
T. Fresh `state=None,position=0` creates a new zero state; interleaved owners
require separate states. Masks, grouped-query replication, projections, output
gating, and production FP32 behavior are omitted.

## OR-H01: mHC

Shapes are streams `[R,D]`, `fn[(2+R)R,RD]`, `base[(2+R)R]`, scale `[3]`.

```text
z = flatten(streams)/sqrt(mean(flatten(streams)^2)+norm_eps)
mixes = z@fn.T
pre[r] = sigmoid(mixes[r]*scale[0]+base[r])+hc_eps
post[r] = 2*sigmoid(mixes[R+r]*scale[1]+base[R+r])
L[r,c] = mixes[2R+rR+c]*scale[2]+base[2R+rR+c]
C = row_softmax(L)+hc_eps
C = C/(column_sum(C)+hc_eps)
repeat sinkhorn_iters-1:
    C = C/(row_sum(C)+hc_eps)
    C = C/(column_sum(C)+hc_eps)
collapsed[d] = sum_r pre[r]*streams[r,d]
expanded[dst,d] = post[dst]*branch[d]
                + sum_src C[src,dst]*streams[src,d]
```

This is the actual ops transform at `hyper_connection.py:183–216,219–265`:
RMSNorm, nonzero learned transform, sigmoid pre/post, epsilon-regularized
Sinkhorn, collapse, and transposed-combination expansion. The frozen fixture
cannot pass through a no-op residual substitute.

## OR-F01 and OR-X01: clamps and composition

For each intermediate coordinate (`language.py:24–51`):

```text
gate_c = min(gate,limit)        # no lower gate clamp
up_c = clip(up,-limit,limit)
activated = gate_c*sigmoid(gate_c)*up_c
output = down_weight@activated
```

The frozen vector composition is:

```text
route = route_tokens(logits,correction_bias,...)
selected_traces = clamped_mlp(x,expert[e]) for selected e
routed = sum_j route.weights[j]*selected_traces[j].output
shared_trace = clamped_mlp(x,shared_expert)
shared = shared_trace.output
branch = routed+shared
output = residual+branch
```

The actual mHC residual transform is exercised separately by OR-H01. Every
projection, activation, selected output, route weight, routed sum, shared
output, branch, and residual sum is exposed or asserted. Extreme finite dot
products that overflow are rejected before clamp.

## Required producer-consumer edges

| ID | Producer | Consumer |
| --- | --- | --- |
| `R01` | logits sigmoid plus correction | exact route IDs |
| `R02` | uncorrected selected scores | normalization/scaling |
| `S01` | token gates plus APE | feature-wise pool softmax |
| `S02` | pooled keys and queries | rectified head scores |
| `S03` | pool scores and visibility | exact pool/index order |
| `C01` | suffix plus current inputs | depthwise windows |
| `C02` | convolution values | SiLU; raw inputs update suffix |
| `K01` | Q/K | L2 normalization and Q scaling |
| `K02` | safe gate parameters | vector decay |
| `K03` | state/decay/K/V/beta | new `[Dk,Dv]` state |
| `K04` | new state and Q | output and next-call state |
| `H01` | normalized streams and fn | mHC mixes |
| `H02` | combination logits | iterative Sinkhorn matrix |
| `H03` | pre plus streams | collapse |
| `H04` | branch/post/comb/streams | expansion |
| `X01` | gate/up projections | clamped SwiGLU |
| `X02` | activation/down projection | expert output |
| `X03` | selected outputs/weights | routed sum |
| `X04` | input/shared projections | shared output |
| `X05` | routed/shared/residual | composed output |

The owned implementation is `scripts/research/glm53_flash/oracle.py`.
Arithmetic may run only through the root-owned bounded supervisor.
