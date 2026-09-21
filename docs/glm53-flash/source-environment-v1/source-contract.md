# Source-bound selector and convolution research contract

This contract is banked before installing the new runtime or observing its
boundary outputs. It leaves the predecessor's files, fixtures and criteria
unchanged. Source reading and extracted/operator execution are separate claims.

## Exact source and execution boundaries

PipeNetwork/glm53-flash-mlx at
`a61a7c7d2fbdf3d218a9909365a24bd794f3a247`, language.py SHA-256
`6de479b6eafc0731e5e965f01f28797a58eecb606e7d5d5657db13642c230196`,
imports the deepseek_v32 module and MoEGate at lines 13–14. Its
Glm5NextMoEGate calls group_expert_select at lines 54–62 after FP32 projection.
That projection and the full module import are source-read only.

The selected dependency is Blaizzy/mlx-vlm at
`8d79dbcf82a7885ddfc56fb4a55440fa9c5dfb90`. Its deepseek_v32/language.py
SHA-256 is `cd210c73ce3e569ab5270a47a92941cd5ec1450c6ff7b55b8be57c51263f4cb6`.
Lines 233–265, including `@mx.compile`, are extracted without edits. Capsule
SHA-256 is `4efab08404da68c50faa1f2a4ebe3235436a1b2aa09bac6e77e20dc0fba35ad9`.
AST analysis finds exactly one external global, `mx`, bound only to the admitted
mlx.core. No imports, removed decorators, full upstream module loading or model
construction are part of this extraction. The source's requirements.txt declares
mlx>=0.32.2; the proposed 0.32.2 wheel satisfies that range. The rest of that
requirements file is not installed.

MLX v0.32.2 resolves at the official upstream tag to
`1f8e74e3f12f31365464a6867c6579f0e9b29d85`. The older v0.32.0 reference remains
`7a1d4f5c12ac82f4b4d0a6e71538d89ca0605247`; it is not relabeled as the new runtime.
Wheel/source correspondence is RELEASE_DECLARED_NOT_BUILD_VERIFIED. All runtime
claims name the wheel, device and FP32 dtype. The full release-source file lock
and quoted relevant passages are retained in the private phase packet.

## Selector equations and domains

For logits g and correction bias b, uncorrected score s_i=sigmoid(float32(g_i));
selection score c_i=s_i+b_i. With n_group>1, reshape contiguous expert coordinates
into groups, score each group by the sum of its two largest c values, and use
argpartition to identify the n_group-topk_group lowest groups. Their selection
scores become **zero**, not negative infinity. Select top_k expert coordinates
through argpartition(-c), gather their **uncorrected** s values, normalize their
sum only if top_k>1 and norm_topk_prob, then multiply by routed_scaling_factor.
MoEGate parameter ownership is source-read at dependency lines 268–291.

MLX release python/src/ops.cpp lines 3145–3163 declares within-partition order
undefined, and lines 3218–3232 likewise do not promise sorted topk output.
Tests preserve raw ID order and weight pairing. For separated scores, ID sets
are exact and weights compare by ID. Ties allow any unique IDs at the threshold
provided all strictly greater scores are included; stable repeats are empirical,
not an ordering guarantee. Generic grouped cases require at least two experts
per group, 1<=topk_group<n_group<=4 and at most eight experts. Ungrouped generic
cases have at most eight experts. Only the selected-config selector case may
use up to 512 scalar scores, with no expert matrices instantiated.

The zero-mask diagnostic uses all-negative corrected scores. It will record
whether zeroed groups outrank retained negative values, as the source predicts.
That is a source-mask finding about exclusion intent, not an idealized selector
replacement or a generic group-exclusion PASS. The selected-config branch is
qualified separately when its retained metadata is admitted.

## Convolution axes and state

Release python/mlx/nn/layers/convolution.py lines 9–84 declares NLC input,
weight [C_out,K,C_in/groups], and calls mlx.core.conv1d with the module's stride,
padding, dilation and groups. The CPU implementation's slow_conv_1D at lines
71–98 accumulates input[output_position + tap] times weight[tap] for flip=false.
The public conv1d dispatch passes false to the general convolution. Thus this
operator is cross-correlation in increasing tap order. A release-source path is
not proof of which internal wheel kernel is selected on a particular device.

The research wrapper uses groups=C_in=C_out, stride=dilation=1, zero operator
padding, and no bias. It prepends [B,K-1,C] state to [B,T,C] input, applies the
real admitted MLX nn.Conv1d, exposes raw output, then calls the admitted nn.silu.
Its independent scalar equation is y[b,t,c]=sum_j(state||input)[b,t+j,c]*w[c,j,0].
New state is the final K-1 input positions, including earlier state when a chunk
is shorter than K-1. State belongs to the caller, and fresh=None means explicit
zeros. Pure-function fresh-call equality is not production cache teardown.

PipeNetwork language.py lines 191–199 construct the depthwise operator; lines
267–276 prepend state, save the final suffix and apply SiLU. Lines 780–811 fuse
q/k/v convolution weights and conditionally move their axes during sanitation.
Those upstream construction, sanitation and cache paths remain
NOT_EXECUTED_NOT_QUALIFIED. New wrappers are research reimplementations. SiLU's
release source at activations.py lines 138–145 is x*sigmoid(x).

## Changed-boundary inventory

| Edge | Producer → consumer | Planned disposition |
| --- | --- | --- |
| R1 | synthetic FP32 logits/bias → exact selector capsule | biased/unbiased and grouped cases |
| R2 | capsule returned IDs and paired weights → independent keyed comparison | exact sets, threshold ties, keyed weight checks |
| R3 | capsule weights/IDs → predecessor fictional expert values → weighted MLX sum | composition with four experts; order-independent assertion |
| R4 | selected artifact router parameters → selector-only capsule | admitted retained config only, otherwise explicitly unqualified |
| C1 | [B,T,C] input and [B,K-1,C] state → real MLX Conv1d | asymmetric impulses/ramps and channel-distinct kernels |
| C2 | raw convolution → admitted nn.silu | separately compared raw and activated values |
| C3 | saved suffix → next research-wrapper call | token/chunk, prefix, fresh-state and interleaved streams |
| C4 | predecessor seven-channel fixture → weight-axis adapter → wrapper | width-4 convolution/state bridge only; no KDA update qualification |
| T1 | pinned template and inert JSON messages → Jinja sandbox text | conditional on retained template admission; no tokenization or tools |

Nonfinite inputs reject before numerical construction; nonfinite outputs or
intermediate normalization outcomes cannot count as passing finite values.
Source-hash/global/origin mutations and arithmetic wiring mutations are counted
separately from expected source-domain diagnostics. The forthcoming frozen case
file specifies individual fixtures, bounds, tolerances and mutation expectations
before the first boundary launch.

The implementation uses repository MIT terms. Extracted dependency text and MLX
source are MIT; PipeNetwork design attribution is Apache-2.0. Required licenses
and exact provenance accompany any copied source. No upstream test/setup script
or full model module is executed. PulsarMLX derives from
[Pulsar](https://github.com/giannisanni/pulsar); upstream does not maintain or
endorse this independent addition.
