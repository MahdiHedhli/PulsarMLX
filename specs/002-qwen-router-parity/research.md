# Research: Qwen3MoE Layer-0 Router Parity

**Date**: 2026-08-05

**Scope**: Phase 0 design research only. This research inspected committed
Feature 001 evidence, the inherited Pulsar source, and pinned public upstream
source. It did not open the external checkpoint, execute a model command, or
observe any Apple router output.

## Decision 1: Reuse the immutable Feature 001 checkpoint

**Decision**: Feature 002 uses only the already admitted official
`Qwen/Qwen3-30B-A3B-GGUF` artifact at repository revision
`e4d4bafdfb96a411a163846265362aceb0b9c63a`, filename
`Qwen3-30B-A3B-Q8_0.gguf`, byte size `32,483,931,648`, and SHA-256
`4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c`.
The public source remains Apache-2.0. The local file remains external to Git,
is opened read-only, and is never downloaded automatically.

**Rationale**: Feature 001 already proved this immutable source, license,
complete local identity, `qwen3moe` architecture, and one independent bounded
tensor slice. Reusing that identity isolates the new variable to the router
boundary and avoids a second checkpoint, license, quantization, or acquisition
path.

**Alternatives considered**:

- Downloading another Qwen quantization would introduce an unnecessary
  artifact and quantization variable.
- Using a smaller model with a different architecture would not validate the
  route needed by the later selected-expert features.
- Accepting a matching filename without a complete size and SHA-256 gate would
  make tensor offsets and oracle values ambiguous.

**Primary and committed sources**:

- [Immutable official GGUF repository](https://huggingface.co/Qwen/Qwen3-30B-A3B-GGUF/tree/e4d4bafdfb96a411a163846265362aceb0b9c63a)
- [Feature 001 compatibility record](../../docs/validation/models/qwen3-30b-a3b-q8_0-compatibility.json)
- [Feature 001 trusted-reference result](../../docs/validation/models/qwen3-30b-a3b-q8_0-reference-result.json)

## Decision 2: Admit the complete F32 router tensor before execution

**Decision**: The expected layer-0 router tensor contract is:

| Field | Pre-execution expectation |
|---|---|
| GGUF name | `blk.0.ffn_gate_inp.weight` |
| Semantic role | layer-0 routed-expert router projection |
| GGUF dimensions | `[2048, 128]`, fastest axis first |
| Reader shape | `[128, 2048]` |
| Orientation | expert-output row by hidden-input column; no transpose after reader reversal |
| Logical elements | `262,144` |
| Expected storage type | F32, unquantized |
| Expected encoded bytes | `1,048,576` |
| Projection | `logits[row, expert] = W[expert, :] dot hidden[row, :]` |

These are expectations until a newly authorized read-only inventory proves the
exact local occurrence, type, dimensions, range, and hash. The Rust admission
path must reject a missing or duplicate name, any different type or dimensions,
an invalid range, and any byte-count mismatch before the worker can schedule
MLX.

**Rationale**: Pinned llama.cpp constructs Qwen3MoE `ffn_gate_inp` with
dimensions `{n_embd, n_expert}` and gives the standard tensor name
`blk.%d.ffn_gate_inp.weight`. Its quantizer explicitly excludes expert router
weights from quantization. The committed artifact inventory contains only 241
F32 and 338 Q8_0 tensors. Those counts decompose exactly as follows for 48
layers:

- F32: `48 * (attn_norm + q_norm + k_norm + ffn_norm + router) + output_norm
  = 241`.
- Q8_0: `48 * (q + k + v + output + expert_gate + expert_up + expert_down) +
  token_embedding + model_output = 338`.

This is strong evidence for an F32 router, but it is not a substitute for the
exact tensor-specific local inventory and offset required by the feature.

**Alternatives considered**:

- Treating the router as Q8_0 because the artifact is named Q8_0 conflicts with
  the pinned quantizer rule and artifact type inventory.
- Transposing to `[2048, 128]` in the MLX computation would reverse the GGUF
  fastest-axis convention and can produce plausible but wrong values.
- Reading a partial expert-row range cannot establish top-8 routing because
  every decision requires all 128 logits.

**Primary and committed sources**:

- [Pinned Qwen3MoE tensor construction](https://github.com/ggml-org/llama.cpp/blob/b06aa774c03dbbb624e726664b714a57d1f49815/src/models/qwen3moe.cpp#L21-L61)
- [Pinned GGUF tensor-name mapping](https://github.com/ggml-org/llama.cpp/blob/b06aa774c03dbbb624e726664b714a57d1f49815/src/llama-arch.cpp#L390-L398)
- [Pinned router quantization exclusion](https://github.com/ggml-org/llama.cpp/blob/b06aa774c03dbbb624e726664b714a57d1f49815/src/llama-quant.cpp#L289-L309)
- [`TensorInfo` GGUF dimension and byte rules](../../crates/gguf/src/lib.rs)

## Decision 3: Follow the checkpoint's exact softmax and top-8 semantics

**Decision**: For each admitted real input row, the architecture-correct
operation is:

1. consume the 2,048-element layer-0 `ffn_norm` output;
2. compute 128 bias-free F32 router logits;
3. compute F32 softmax over all 128 logits;
4. select exactly the eight largest probabilities;
5. because this checkpoint has `norm_topk_prob=true`, divide the eight selected
   probabilities by their selected sum; and
6. apply router weight scale 1.0, with no correction bias and no shared expert.

Evidence retains all raw logits when bounded publication policy permits,
otherwise their complete stable hash plus bounded spot-check values. It always
retains the eight ordered IDs, the eight selected full-softmax probabilities
before selected-sum normalization, and the eight final normalized weights.
The comparison contract freezes the float accumulation order and absolute plus
relative tolerances before any corresponding Apple output is inspected.

**Rationale**: The immutable official config declares hidden size 2,048, 128
experts, eight active experts, and `norm_topk_prob=true`. Pinned llama.cpp calls
the generic MoE graph with softmax gating and `norm_w=true`. That graph computes
the full expert softmax, selects top-k, gathers the selected probabilities, and
normalizes them by their sum. Selecting on raw logits and applying softmax only
to the eight winners is algebraically equivalent in real arithmetic, but the
frozen CPU oracle uses the explicit full-softmax sequence so implementation
rounding is compared rather than silently redefined.

**Alternatives considered**:

- Sigmoid routing belongs to other inherited model families and is incorrect
  for `qwen3moe`.
- Selecting eight logits without normalizing the selected weights contradicts
  this checkpoint's `norm_topk_prob=true` contract.
- Treating a zero-filled absent bias as a checkpoint tensor would invent a
  model role; the admission record instead proves bias absence.
- Using float64 as the implementation dtype would not match the F32 checkpoint
  router boundary, though float64 remains appropriate for error reporting after
  both F32 outputs are complete.

**Primary and local sources**:

- [Immutable official base-model config](https://huggingface.co/Qwen/Qwen3-30B-A3B/blob/ad44e777bcd18fa416d9da3bd8f70d33ebb85d39/config.json)
- [Pinned Qwen3MoE graph selection](https://github.com/ggml-org/llama.cpp/blob/b06aa774c03dbbb624e726664b714a57d1f49815/src/models/qwen3moe.cpp#L120-L157)
- [Pinned generic MoE softmax, top-k, and normalization](https://github.com/ggml-org/llama.cpp/blob/b06aa774c03dbbb624e726664b714a57d1f49815/src/llama-graph.cpp#L1943-L2072)
- [Inherited Pulsar router selection](../../crates/engine/src/lib.rs)
- [Inherited CUDA algebraic implementation](../../crates/kernels/cuda/pulsar_kernels.cu)

## Decision 4: Make tie behavior deterministic without misattributing it

**Decision**: PulsarMLX ranks F32 full-softmax probabilities descending and
resolves equal probabilities by expert ID ascending. The exact ordered top-8
IDs are part of the contract. A synthetic exact-tie and near-tie fixture
exercises the rule without being presented as checkpoint evidence. Real oracle
evidence records whether any F32 logits or probabilities tie. Any probability
tie across the eighth/ninth boundary stops Feature 002 rather than relying on
an undocumented trusted-runtime ordering or changing the rule after observing
Apple output.

**Rationale**: Qwen specifies top-k but not a portable exact-tie order.
Hugging Face delegates to `torch.topk`, whose documentation states that tied
indices are not guaranteed stable. Pinned llama.cpp CPU argsort uses a
score-only `std::sort` comparator and likewise does not specify a stable tie.
The existing backend-neutral PulsarMLX contract and inherited CUDA selector
both explicitly prefer the lower expert ID, which is reviewable and portable.

**Alternatives considered**:

- Describing lower-ID-first as an official Qwen rule would be unsupported.
- Relying on an undocumented sort implementation could change ordering across
  MLX or operating-system versions.
- Comparing top-8 as an unordered set would weaken downstream expert-slot and
  weight traceability.

**Primary and local sources**:

- [PyTorch `topk` tie warning](https://pytorch.org/docs/stable/generated/torch.topk.html)
- [Backend-neutral deterministic router](../../crates/backend/src/routing.rs)
- [Synthetic MLX router](../../python/pulsar_mlx_worker/moe.py)
- [Inherited CUDA tie comparator](../../crates/kernels/cuda/pulsar_kernels.cu)

## Decision 5: Capture a genuine real router input with pinned CPU llama.cpp

**Decision**: Generate the real hidden-state fixture with CPU-only llama.cpp at
the already trusted immutable revision
`b06aa774c03dbbb624e726664b714a57d1f49815`. Supply direct token IDs `[0,1]`
at positions `[0,1]` without invoking or selecting a tokenizer. Freeze a
two-token context, batch, and ubatch, one evaluation thread, row selection, and
CPU-only device configuration. Token IDs must be proven inside the observed
vocabulary, and the two captured rows must differ. Use
`llama_context_params.cb_eval` to observe and copy `ffn_norm-0`, the layer-0
post-attention residual after FFN RMS normalization. Hash the complete
little-endian F32 capture and commit only the bounded redistributable
fixture/evidence, never model tensor bytes.

The only v1 real case IDs are
`qwen3moe-layer0-router-token0-row0-v1` for row 0 and
`qwen3moe-layer0-router-token0-token1-batch-v1` for rows 0–1. The complete
capture is at most two rows or 16,384 canonical F32 bytes. The input adapter is
recorded as `direct_token_ids_v1`, and tokenizer identity is recorded as
`not_used_direct_token_ids`; no prompt or tokenizer-derived claim is made.

The observer requests only the named boundary. Pinned llama.cpp's callback
return value breaks the current scheduler split rather than promising a global
decode abort, so the helper must not assume that `false` alone is sufficient.
The minimal reproduction freezes CPU-only placement, disables GPU/KQV/op
offload, uses one thread with context, batch, and ubatch all fixed to two
tokens, supplies an all-zero output-selection array, retains `GGML_SCHED_DEBUG`
proof of one CPU split, copies only the fully synchronized `ffn_norm-0` value,
returns false, and sets a CPU abort guard against any later split. A callback
trace must show no router or expert node after the target, and two independently
started captures must have identical canonical hashes. If any part of that
proof fails, real hidden-state capture is blocked; a prompt-derived or random
vector remains synthetic and must not be relabeled as real.

**Rationale**: A real router input is not the embedding or an arbitrary
2,048-element vector. In Qwen3MoE layer 0 it follows token embedding, attention,
the attention residual, and FFN RMS normalization. The pinned scheduler exposes
a public node-observation callback, and the pinned graph names this boundary
`ffn_norm-0`. Capturing it once keeps the Apple feature bounded to the router
while retaining a real, independently generated input from the same checkpoint.

**Alternatives considered**:

- Reusing Feature 001's SHA-256 prompt-derived probe is useful as a supplementary
  model-shaped case but is explicitly not Qwen tokenization, attention, or a
  real hidden state.
- Reconstructing layer-0 attention in the PulsarMLX worker would expand Feature
  002 into the later complete-layer feature and compromise oracle independence.
- Downloading the original BF16 checkpoint for a Transformers capture adds a
  second very large artifact and different tensor representation.
- Letting a CPU oracle run unobserved through expert MLPs violates this
  feature's bounded exclusion and is not an acceptable fallback.

**Primary and committed sources**:

- [Pinned scheduler callback in `llama_context_params`](https://github.com/ggml-org/llama.cpp/blob/b06aa774c03dbbb624e726664b714a57d1f49815/include/llama.h#L364-L385)
- [Pinned callback observation semantics](https://github.com/ggml-org/llama.cpp/blob/b06aa774c03dbbb624e726664b714a57d1f49815/ggml/include/ggml-backend.h#L307-L315)
- [Pinned scheduler callback split behavior](https://github.com/ggml-org/llama.cpp/blob/b06aa774c03dbbb624e726664b714a57d1f49815/ggml/src/ggml-backend.cpp#L1592-L1625)
- [Pinned Qwen3MoE `ffn_norm` graph boundary](https://github.com/ggml-org/llama.cpp/blob/b06aa774c03dbbb624e726664b714a57d1f49815/src/models/qwen3moe.cpp#L108-L157)
- [Feature 001 probe caveat](../../docs/validation/models/qwen3-30b-a3b-q8_0-reference-result.json)

## Decision 6: Freeze a two-part independent CPU fixture and router oracle

**Decision**: Before inspecting Apple output, freeze a CPU-only oracle package
with two independently reviewable parts:

1. the pinned llama.cpp observer produces only the genuine `ffn_norm-0` input
   and proves that cancellation prevents the router and expert graph from
   executing; and
2. a standalone script using pinned llama.cpp `gguf-py` reads the complete F32
   `[128, 2048]` router, consumes the frozen hidden-state bytes, and performs an
   explicit F32 scalar projection, full 128-way softmax, deterministic top-8,
   and selected-sum normalization.

The standalone oracle imports no PulsarMLX worker or backend implementation and
never calls MLX. A NumPy F32 matrix-vector result may cross-check scalar logits,
but explicit scalar accumulation is canonical to avoid a vendor-BLAS-dependent
oracle. It follows the exact sequence frozen in Decision 3: complete logits,
full 128-way softmax, top-8 selection, and selected-probability
renormalization. The comparison policy is frozen at `atol=5e-4, rtol=5e-4`
for complete logits and `atol=1e-6, rtol=1e-6` for complete and selected
full-softmax probabilities and normalized weights. The oracle records hashes
for the model, tensor bytes, hidden input, logits, complete probabilities,
ordered IDs, selected pre-normalization probabilities, normalized weights,
source script, pinned source revision, and raw capture.

**Rationale**: `gguf-py` at this exact revision already served as Feature
001's independent Q8_0 reader. Reusing its parser for a different F32 tensor
preserves source provenance without sharing the MLX implementation. Two
independently started pinned-runtime captures verify the real input's named
graph boundary and repeatability. The scalar router result is instead
cross-checked against a separate NumPy F32 calculation; no callback router node
is executed or treated as oracle output.

**Alternatives considered**:

- Calling worker helpers from the oracle would make the expected result depend
  on the implementation under test.
- Using only NumPy matmul makes the canonical accumulation dependent on the
  installed BLAS and hardware.
- Freezing tolerances or expected IDs after examining Apple output would make
  the comparison circular.

**Primary and committed sources**:

- [Pinned `gguf-py` reader](https://github.com/ggml-org/llama.cpp/blob/b06aa774c03dbbb624e726664b714a57d1f49815/gguf-py/gguf/gguf_reader.py)
- [Feature 001 oracle contract](../../docs/validation/models/qwen3-30b-a3b-q8_0-oracle.json)
- [Feature 001 executed CPU reference](../../docs/validation/models/qwen3-30b-a3b-q8_0-reference-result.json)

## Decision 7: Interpret required row cases at the correct tensor boundary

**Decision**: Every real route decision consumes the complete 128-row router.
Required real cases consist of at least one single hidden-state row and one
bounded multi-row hidden-state batch. Full logits are retained or hashed for
every input row; logits 0 through 15 and at least one non-overlapping expert-ID
range are review spot checks only and never partial inputs to top-8.

Feature 001's 16-row prefix is inapplicable to the router: it is rows 0 through
15 of expert 0 in `blk.0.ffn_gate_exps.weight`, with shape boundary
`[16, 2048]`. It is a different Q8_0 expert-MLP tensor, not the F32
`blk.0.ffn_gate_inp.weight` router. Its deterministic 2,048-element activation
may be reused only as a clearly labeled supplementary probe case. It cannot
satisfy the real hidden-state requirement or establish top-8 selection.

The synthetic suite separately covers exact tie, near tie, non-finite values,
invalid top-k, dimension mismatch, and malformed or truncated byte ranges. Its
results never enter the real-checkpoint claim cell.

**Rationale**: Top-8 selection from only a router prefix can omit the actual
winners and is architecturally invalid. Interpreting non-overlapping ranges as
review windows over a complete result satisfies auditability without changing
the operation. Separating real and synthetic cases preserves exact claim depth.

**Alternatives considered**:

- Selecting top-8 from the first 16 router experts would answer a different and
  misleading question.
- Calling the Feature 001 probe a real hidden state would contradict its frozen
  oracle and published warnings.
- Dropping tie cases because the real checkpoint may have none would leave the
  deterministic ordering contract untested.

**Committed sources**:

- [Feature 001 tensor inventory](../../docs/validation/models/qwen3-30b-a3b-q8_0-compatibility.json)
- [Feature 001 reference tensor and activation](../../docs/validation/models/qwen3-30b-a3b-q8_0-reference-result.json)
- [Feature 001 Apple result](../../docs/validation/qwen3-30b-a3b-q8_0-slice.json)

## Decision 8: Freeze publication and timing methods before measurements

**Decision**: Version the experiment schema and freeze the protocol in a clean
commit before real output or timing collection. Correctness records retain the
required raw values or hashes, exact IDs, error vector or sufficient raw pairs,
maximum and mean absolute error, RMSE, maximum meaningful relative error,
mismatch count, first mismatch, and at least ten identical repetitions.

Timing uses a monotonic high-resolution clock and ends only after explicit MLX
evaluation and GPU synchronization. It records at least five warm-ups and ten
measured costly real repetitions. The schema distinguishes:

- identity/header admission and exact positional read;
- F32 byte ownership and transfer (router dequantization is `not_applicable`,
  not an invented zero-duration phase);
- graph construction/compilation where observable;
- projection;
- top-k;
- normalization; and
- minimally instrumented total evaluated execution.

Instrumented component timings and minimally instrumented totals remain
separate when synchronization or tracing changes the operation. The first read
in a fresh process is labeled
`first_read_new_process_os_cache_uncontrolled`, not guaranteed cold disk,
because the feature does not purge operating-system caches. Same-process
repetitions are labeled `warm`, and instrumentation uses exactly
`minimally_instrumented` or `stage_instrumented`. Every sample, abort,
interference observation, benchmark order, and predefined exclusion decision
is retained. Published statistics are generated from raw evidence rather than
embedded in scripts.

**Rationale**: The router tensor is only about 1 MiB and is likely to be served
from the unified file cache after first access. Claiming a controlled cold-disk
measurement without a safe cache-control mechanism would overstate the
experiment. Separating semantic phases and retaining minimally instrumented
totals prevents profiling overhead from becoming an unreported optimization.

**Alternatives considered**:

- Purging macOS caches would require privileged, system-wide state changes and
  is outside the authorized experiment.
- Reporting only aggregates would prevent audit of variance, interference, or
  cherry-picking.
- Reporting a dequantization duration for an F32 tensor would invent work the
  operation does not perform.
- Extrapolating router latency to tokens per second, expert latency, or full
  layer throughput is explicitly prohibited.

## Decision 9: Preserve backend boundaries and fixture-only CI

**Decision**: Add the bounded router operation beside the inherited Linux/CUDA
path. Do not refactor shared engine selection, replace CUDA routing, or present
macOS results as Linux/CUDA evidence. The local-only external-checkpoint command
performs model identity, memory, workload, and NTFY gates. Hosted CI validates
schemas, evidence fixtures, generators, oracle contracts, malformed cases,
synthetic tie behavior, and capability boundaries without locating or opening a
checkpoint.

**Rationale**: Feature 002 needs one Apple vertical slice, while the inherited
router and expert engine has broader production behavior that cannot be
runtime-validated on this host. Small committed fixtures are sufficient for CI
to reject semantic drift and evidence overclaims without redistributing model
data.

**Alternatives considered**:

- Putting the external 32.5 GB checkpoint in CI violates storage, licensing,
  and repository hygiene constraints.
- Reusing the inherited CUDA implementation through a broad abstraction would
  expand risk before the Apple contract is proved.
- CPU fallback in the Apple command would make an evaluated result ambiguous;
  failure is explicit instead.

## Exact unresolved pre-execution facts

The following facts remain deliberately unresolved because this Phase 0 work
did not access the external checkpoint. They must be recorded from a read-only
inventory after notifying NTFY topic `Mahdi-Dev` and before any Apple result:

- exactly one `blk.0.ffn_gate_inp.weight` occurrence;
- its exact GGUF type, `[2048, 128]` dimensions, absolute offset, encoded
  length, element count, range-inside-file proof, and complete tensor SHA-256;
- typed `qwen3moe.expert_used_count == 8` metadata;
- the presence or absence and effective value of
  `qwen3moe.expert_weights_scale`;
- absence of `blk.0.ffn_gate_inp.bias`, `blk.0.exp_probs_b`, and
  `blk.0.exp_probs_b.bias` or any other router correction tensor;
- proof that direct token IDs `[0,1]` are within the observed vocabulary,
  positions `[0,1]`, context/batch/ubatch `2`, thread count `1`, input adapter
  `direct_token_ids_v1`, tokenizer state `not_used_direct_token_ids`, distinct
  captured rows, and the complete `ffn_norm-0` capture hash;
- whether any real F32 router values tie, especially across rank eight and
  rank nine;
- a conservative current disk, unified-memory, process-footprint, thermal,
  power-mode, and concurrent-workload admission observation; and
- the already frozen numeric tolerances and mismatch policy are copied into the
  executed record without amendment.

No exact tensor offset or real router value is inferred from neighboring tensor
ranges. Absence from this list after execution is a failed evidence record, not
permission to use a default.

## Stop conditions

Stop Feature 002 at the current deepest verified boundary, preserve failing or
aborted evidence, and do not adjust the implementation or oracle to agree when:

- checkpoint source, license, immutable identity, or current local file identity
  differs from Feature 001;
- any unresolved tensor name, occurrence, offset, length, dimensions,
  orientation, type, bias, scale, expert count, or top-k fact cannot be proved;
- the pinned CPU callback cannot produce and hash a genuine `ffn_norm-0`
  fixture without evaluating excluded expert work;
- the standalone CPU oracle cannot remain independent of MLX and PulsarMLX
  worker code;
- any exact F32 full-softmax probability tie across ranks eight and nine;
- expert IDs or ordering differ, numeric tolerances fail, non-finite values
  appear, fallback occurs, or ten-run repeatability fails;
- disk, unified-memory headroom, memory pressure, thermal state, power or
  concurrent workload violates the frozen protocol;
- timing instrumentation materially changes semantics and no minimally
  instrumented synchronized total can be retained;
- clean-checkout reproduction, schema validation, raw-data retention, or claim
  traceability fails; or
- continuing would require expert MLP execution, routed aggregation, a complete
  transformer layer, language-model-head or model-output logits, generation,
  serving, custom Metal, model data in Git, a destructive action, or a
  Linux/CUDA behavior change.

## Resolved decisions and deferred observations

Phase 0 resolves the checkpoint, expected router role and orientation, F32
projection semantics, full-softmax/top-8/renormalization order, deterministic
project tie rule, genuine hidden-state capture method, independent oracle
construction, tolerances, case interpretation, evidence protocol, and CI split.
Exact model inventory, captured inputs, outputs, resource admission, and timing
values remain observations to be frozen or measured at their explicit gates;
none is claimed by this research document.
