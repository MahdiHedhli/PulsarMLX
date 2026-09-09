# Source-bound causal convolution and state composition

The current tiny successor has a `convolution` operation. It executes eleven
selected statements from PipeNetwork's retained `Glm5NextLinearAttention`
constructor/caller through explicit research function seams. The provenance
record binds the original commit, whole-file digest, byte spans, statement
digests and equal ASTs. Runtime rechecks that correspondence before compiling
only the capsule. No full upstream model module is imported or constructed.

The constructor slice creates the actual admitted MLX depthwise `nn.Conv1d`,
with NLC input, weights `[C,K,1]`, no bias, zero operator padding, and groups C.
The caller slice reads `cache[0]` or creates zeros, prepends that state, stores
the final K−1 positions using `mx.contiguous`, applies convolution and SiLU,
then executes the source q/k/v split and reshapes. There is no separate
prefill/decode branch in this selected convolution slice; chunks use the same
transition. Its saved state is written before the convolution call.

The executed scope is **SOURCE_SLICE_EXECUTED with RESEARCH_ADAPTER**. The
retained artifact index contains no actual `ArraysCache` definition. A small
inert adapter directly supplies indexed slots; it neither calculates outputs
nor substitutes an expected state. Slot zero is written by the source slice,
and slot one remains an identity marker. The real `ArraysCache`, its lifecycle,
KDA state, `cache[1]` updates and `cache.advance` remain **NOT_EXECUTED**.
Reset means replacing a research adapter with a fresh one; no upstream reset
method is invented. Distinct stream adapters own distinct slot lists. Array
immutability, physical storage independence and production cache teardown are
not claimed.

Research seams supply the tiny scalar dimensions and the already-projected,
already-masked mixed input. Projection, masking, full construction, fused input
paths and TextConfig translation are not executed. A transparent observer
delegates to the constructed real Conv1d and captures raw output and the state
visible at its call boundary. It evaluates the observed lazy arrays explicitly.
A wrong raw shape fails after actual operator evaluation, before SiLU/reshape.
An intentionally failing observer separately demonstrates update-before-callee-
failure ordering; that is not an upstream numerical-error guarantee.

## Finite generation and controls

The immutable generation uses FP32, batch at most two, sequence at most seven,
three or six channels, and K2/K3/K4. Signed quarter inputs/states and asymmetric
eighth weights give at most four depthwise terms. Raw sums in the fixed domain
are exactly representable in FP32. The retained scalar tolerances are raw
`atol=2e-5, rtol=2e-6` and SiLU `atol=4e-5, rtol=4e-6`; fixtures include the
conservative error analysis. State shape and values compare exactly.

The K4 geometry reflects the retained metadata field
`text_config.linear_attn_config.short_conv_kernel_size=4`. Executing its
translation into the source constructor's `linear_conv_kernel_dim` property
is a separate, unqualified boundary. Full q/k/v sanitation also calls an
unexecuted predecessor sanitizer. The source split/reshape is exercised here;
checkpoint weight layout and full sanitation remain **NOT_QUALIFIED**.

Whole prefill, every-token decode, nonuniform chunks, and prefill-to-decode
transitions compare every raw/activated output and saved state with an
independent scalar chronological-history equation. K3/K4 include nonempty
chunks shorter than K−1. That subcase is not applicable to K2. Empty chunks are
not executed or qualified. Interleaved streams and adapter replacement exercise
the saved-state-to-next-call boundary. Same-device fresh-process confirmations
are compared exactly; scalar tolerance and partition composition are separate
claims.

Eight controls target reversed taps, transposed channel/kernel axes on a square
kernel, wrong padding, wrong suffix values, wrong suffix length, omitted fresh
cache replacement, cross-stream aliasing, and stale prefill state. Every control
requires normal → mutant → restored, an exact declared mismatch code after
actual convolution evaluation, and restored input/weight/source identity. Wrong
exception type, wrong message or missing required evaluation is a harness
failure, not a detected mutant. Raw mutant observations remain in the output.

The source's K1 suffix expression evaluates `-0` and retains the entire input.
The one-call diagnostic records that behavior and its difference from a
conceptual empty state. It does not repair the source or qualify K1 multi-step
empty-state composition. Research input validation rejects malformed,
nonfinite or out-of-bound data before constructing the next input array or
invoking the source; these stronger refusals are not upstream API guarantees.

## Entry and evidence

Use the explicit source/environment/upstream/identity roles in
[the successor entry guide](successor-entry.md). Keep the existing router
fixture role; the new immutable convolution fixture is a separately manifested
file within the source checkout at
`fixtures/research/glm53-flash-convolution-state-v1/fixtures.json`.

After deriving the current input manifest from the admitted environment and
source bytes, invoke the existing entry with operation `doctor`, then
`convolution`, the separate `--manifest` and `--manifest-sha` arguments, and a
fresh output directory. Choose `--backend cpu` or `--backend metal`. A manifest
describes already-admitted inputs; it is not permission to replace the pinned
runtime. The command requires no old phase prompt checksum.

The real producer must complete all six named checks with no failures or skips.
Its actual request, capture, stop, doctor and input records enter the ordinary
portable-parts archive. This operation requires the distinct
`successor-convolution-state-layout-v1` tag. The generic reader checks the tag
against the archived request and performs a fresh data-only readback. Its
source/import absence fields remain static path assertions, not a runtime
import census. No physical I/O, cold-cache, native BF16, quantized weight,
full-forward or model-performance claim is made.

The extracted statements retain Apache-2.0 attribution and license under
`scripts/research/glm53_flash/convolution_state/`. Old router math, fixtures,
historical guards/runners and their limits are unchanged. The existing drive
protection limitation, historical missing captures/reaping and lack of trusted
external pre-observation timestamps remain unchanged. Shared-method acceptance
and any later KDA or model phase remain separate parent decisions.
