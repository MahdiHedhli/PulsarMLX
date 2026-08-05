# Router Parity Contract v1

**Status**: Normative design contract; external-artifact observations remain a
mandatory admission gate until frozen in the Feature 002 tensor manifest.

**Feature**: [Qwen3MoE layer-0 router parity](../spec.md)

This contract defines the only real-checkpoint router operation admitted by
Feature 002. The keywords **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are
normative.

## 1. Contract identity and scope

| Field | Required value |
|---|---|
| Contract ID | `qwen3moe-layer0-router-parity-v1` |
| Backend | `apple-mlx` |
| Requested and selected device | `gpu` |
| Fallback | `false` |
| Architecture | `qwen3moe` |
| Layer | `0` |
| Router tensor | `blk.0.ffn_gate_inp.weight` |
| Hidden width | `2048` |
| Expert count | `128` |
| Selected experts per row | `8` |
| Output logits layout | row-major `[input_row][expert_id]` |
| Selection order | F32 full-softmax probability descending, then expert ID ascending |
| Normalization | full 128-way softmax, then selected-probability renormalization |

The operation ends after complete router logits, full-softmax probabilities,
ordered expert IDs, selected pre-normalization probabilities, and normalized
routing weights. It does not admit an expert projection or any deeper model
boundary.

## 2. Immutable checkpoint admission

The host MUST establish all of the following before starting the MLX worker:

1. Repository `Qwen/Qwen3-30B-A3B-GGUF`.
2. Revision `e4d4bafdfb96a411a163846265362aceb0b9c63a`.
3. File `Qwen3-30B-A3B-Q8_0.gguf`.
4. File size `32,483,931,648` bytes.
5. File SHA-256
   `4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c`.
6. GGUF architecture `qwen3moe`, little-endian storage, embedding length
   `2048`, expert count `128`, and expert-used count `8`.
7. The model is outside the repository, opened as a regular read-only file,
   and inherited by the worker only on the existing fixed descriptor.
8. Automatic download is false and no model path or model bytes enter the
   worker control protocol.

The same open file description MUST be retained through execution. The host
MUST recheck full-file identity and the exact router-tensor range after the
worker exits. A stat-only recheck is insufficient for a passing record.

Any file identity mismatch, mutation, unresolved license/provenance issue,
non-normal memory pressure, or failed resource admission MUST stop execution.

## 3. Exact router tensor contract

The tensor manifest MUST prove exactly one occurrence of
`blk.0.ffn_gate_inp.weight` and zero occurrences of a layer-0 router bias unless
an architecture review explicitly versions a different contract. Version 1
does not admit an implicit or unrecorded bias.

The following values are fixed now:

| Property | Required value |
|---|---|
| GGUF dimensions, fastest axis first | `[2048, 128]` |
| Logical matrix | `[128, 2048]` |
| Logical row | one expert's 2,048 input coefficients |
| Logical element count | `262,144` |
| Orientation | expert-major rows, input columns, no storage transpose |
| Mathematical operation | `hidden_state [N,2048] × weight.T [2048,128]` |

Before the first Apple execution, a notified read-only inspection MUST freeze
these artifact-observed properties in a committed, sanitized tensor manifest:

- GGUF type and quantization identity;
- relative tensor offset and absolute file offset;
- exact encoded byte length and exclusive range end;
- encoded row length and reader shape;
- full encoded tensor SHA-256;
- presence/type/value of `qwen3moe.expert_used_count`;
- presence/type/value of `qwen3moe.expert_weights_scale`;
- absence of a layer-0 router bias, or a stop result;
- proof that the range is wholly inside the immutable file.

No implementation may guess these unresolved artifact observations. Until the
manifest contains exact observed values, real execution is blocked. After they
are frozen, runtime equality is exact; accepting a family of types, offsets,
lengths, or hashes is forbidden.

The observed tensor MUST be `F32`; bytes MUST be decoded as finite IEEE-754
little-endian float32 and dequantization MUST be recorded as `not_applicable`.
Any other observed type, including `Q8_0`, stops Feature 002 and requires a new
reviewed specification and contract version. It MUST NOT be silently converted
or admitted under v1.

The worker MUST read the complete frozen range with positional I/O. It MUST
handle interrupted and partial reads, reject zero-progress reads, and reject
short, overlong, overflowing, or changed ranges before scheduling MLX work.

## 4. Genuine real hidden-state provenance

At least one fixture MUST be a genuine layer-0 router input, specifically the
post-FFN-RMSNorm value consumed by `blk.0.ffn_gate_inp.weight`, not merely a
2,048-element synthetic vector.

The real fixture MUST be captured using an independently pinned CPU-only model
implementation on the same immutable GGUF with GPU layers disabled. Its
manifest MUST record:

- independent project, immutable revision, build command, and capture hook;
- exact direct token IDs `[0,1]`, positions `[0,1]`, input adapter
  `direct_token_ids_v1`, and tokenizer state `not_used_direct_token_ids`;
- proof both token IDs are within the observed vocabulary, plus context, batch,
  and ubatch size `2`, one evaluation thread, and two distinct captured rows;
- captured graph boundary and tensor name;
- input row count, shape `[N,2048]`, float32 dtype, and little-endian byte order;
- every row's exact float32 byte hash and the full fixture hash;
- two independent captures with identical hashes;
- timestamp, clean source commit, and a statement that MLX was not imported or
  called during capture;
- license and redistribution basis for the bounded derived fixture.

The stored fixture MUST contain exact reconstructable float32 values, not only
decimal summaries. It MUST contain no model weights, private path, username,
token, or machine identifier.

The existing Feature 001 SHA-derived 2,048-value probe MAY be retained only as
an explicitly synthetic regression input. It MUST NOT be relabeled as a real
hidden state, tokenization result, embedding, attention result, or verified
prior-layer output.

Required real cases are:

- row 0 as `qwen3moe-layer0-router-token0-row0-v1`; and
- rows 0–1 as `qwen3moe-layer0-router-token0-token1-batch-v1`.

The complete capture MUST be exactly two `[2048]` rows and no more than 16,384
canonical F32 bytes. The two rows MUST differ byte-for-byte. Failure of a token
bounds, size, row-selection, or distinctness check stops real capture.

Every value MUST be finite before MLX is imported or accessed. Shape, byte
length, and SHA-256 MUST match the fixture manifest exactly.

## 5. Independent CPU oracle

The oracle MUST be frozen before the corresponding Apple output is inspected.
The oracle process MUST:

1. run CPU-only;
2. not import MLX, `pulsar_mlx_worker`, or call code used by the Apple router
   implementation;
3. independently resolve and validate the tensor from the immutable GGUF;
4. independently decode its exact storage representation;
5. perform scalar projection in a documented accumulation order;
6. apply the ordering and normalization rules in Sections 6 and 7; and
7. write a sanitized record containing complete logits, full-softmax
   probabilities, ordered IDs, selected probabilities, normalized weights, and
   stable float32 byte hashes.

The oracle record MUST identify its generator source hash, implementation
revision, exact command, tensor and fixture hashes, arithmetic precision, and
non-finite policy. The Apple worker MUST consume the input fixture only; it
MUST NOT load oracle outputs.

Changing an oracle output or tolerance after observing Apple output invalidates
the experiment. An amendment requires preserving the original, documenting the
reason, and rerunning all affected cases from the beginning.

## 6. MLX operation order

For each admitted input batch, the Apple path MUST execute this order:

1. Validate checkpoint, tensor, fixture, resource, device, and fallback fields.
2. Positional-read the complete exact tensor range into owned immutable bytes.
3. Validate byte count, type-specific structure, and finite decoded values.
4. Decode or dequantize to logical float32 matrix `[128,2048]` without changing
   storage orientation.
5. Construct float32 hidden-state array `[N,2048]` and weight array
   `[128,2048]` on the explicit `mx.gpu` stream.
6. Compute complete float32 logits `[N,128]` as hidden state multiplied by the
   mathematical transpose of the expert-major weight matrix.
7. Compute float32 softmax probabilities across all 128 logits using Section 7.
8. Select eight IDs per row from those probabilities using Section 7.
9. Gather the eight selected full-softmax probabilities in selected-ID order.
10. Divide those eight probabilities by their selected sum using Section 7.
11. Explicitly evaluate logits, full probabilities, IDs, selected
    probabilities, and weights; synchronize `mx.gpu`; then and only then stop
    evaluated timing or read values back.

No host-side route selection may substitute for steps 7-10 in the Apple result.
CPU validation after synchronized readback is allowed and required.

## 7. Tie rule, normalization, and scale

For finite full-softmax probabilities `p[e]`, expert `a` ranks before expert
`b` exactly when:

```text
p[a] > p[b] || (p[a] == p[b] && a < b)
```

The first eight ranked IDs are emitted in rank order. IDs MUST be unique within
one row and each MUST be in `[0,128)`.

Any exact F32 probability tie across ranks eight and nine in a real-checkpoint
case stops v1 cross-runtime parity. The lower-ID rule is still exercised by the
synthetic fixture, but it is not used to convert a real cutoff tie into passing
evidence.

Let `m = max(L)`. The complete full-softmax probability for expert `e` is:

```text
p[e] = exp(L[e] - m) / sum(exp(L[j] - m) for j in 0..128)
```

Select the eight IDs from `p` in the rank order above, retain the corresponding
values as `q[i]`, and compute the normalized weight as:

```text
w[i] = q[i] / sum(q)
```

All intermediates and both denominators MUST be finite, each denominator MUST
be positive, and the resulting weights MUST be nonnegative and sum to one
within the predefined weight tolerance. This exact full-softmax sequence is
normative even though a selected-logit softmax is algebraically equivalent in
real arithmetic. The checkpoint's exact expert-weight scale metadata MUST be
recorded. Version 1 admits the observed architecture value only; an absent
value is interpreted as `1.0` only after absence is proven by the tensor
manifest. No router bias, sigmoid, selected-only replacement softmax, or
post-hoc reordering is allowed.

A separate synthetic 128-expert/top-8 fixture MUST cover an exact tie at the
rank-8 boundary and a representable near-tie. It is synthetic evidence only.

## 8. Comparison policy and tolerances

All values use the non-finite policy `reject`. IDs and ordering require exact
equality and zero mismatches.

Numeric matching uses:

```text
abs(candidate - reference)
    <= absolute_tolerance + relative_tolerance * abs(reference)
```

Predeclared v1 tolerances are:

| Quantity | Absolute tolerance | Relative tolerance |
|---|---:|---:|
| Complete router logits | `5e-4` | `5e-4` |
| Complete full-softmax probabilities | `1e-6` | `1e-6` |
| Selected pre-normalization probabilities | `1e-6` | `1e-6` |
| Normalized routing weights | `1e-6` | `1e-6` |

Every comparison MUST report compared count, mismatch count, first mismatch
location and values, maximum absolute error, mean absolute error, RMSE, and
maximum relative error where the reference is nonzero. Relative error at an
exact zero reference is `null`; the absolute criterion still applies.

The report MUST include whole-output metrics and metrics for expert ranges
`0..16` and `64..80`. These are range summaries of the complete router output,
not the Feature 001 expert-tensor prefix and not separate partial execution.

Any expert-ID or ordering mismatch is an immediate failure regardless of
numeric tolerance. Tolerances MUST NOT be widened to repair a failed run.

## 9. Repeatability

Each real single-row and multi-row case MUST have at least five warm-up runs
followed by at least ten measured identical runs in one process. At least one
second clean worker process MUST repeat each major real benchmark.

Across measured repetitions:

- expert IDs and order MUST be exactly identical;
- canonical little-endian float32 hashes of complete logits, complete
  full-softmax probabilities, selected probabilities, and normalized weights
  MUST be identical;
- every repetition MUST independently satisfy the oracle tolerances; and
- no failed, aborted, or excluded repetition may be deleted.

The synthetic tie/near-tie microbenchmark MUST retain at least thirty measured
repetitions after at least five warm-ups.

Bitwise repeatability failure is a stop condition for v1. It MUST be retained
as failed evidence rather than replaced with a looser post-hoc policy.

## 10. Worker protocol

The request is control-only and contains exactly:

```json
{
  "router_case_id": "<committed bounded case ID>",
  "device": "gpu",
  "allow_fallback": false
}
```

The request MUST NOT contain a filesystem path, checkpoint bytes, tensor
values, hidden-state values, oracle values, hashes supplied as authority,
credentials, output-depth selector, warm-up count, or measured-count override.
Those identities and policies are resolved from committed manifests and the
inherited read-only descriptor.

The existing protocol-v1 limits remain binding: request frames MUST be at most
64 KiB and response frames at most 1 MiB. Complete logits for the bounded
published batch are required. Repetitions SHOULD retain one full canonical
output plus per-run hashes, IDs, comparisons, and raw timing observations
rather than duplicating full logits until the response cap is approached.
Crossing the cap is a failure, not permission to truncate required evidence.

## 11. Required result fields

A successful router result MUST contain:

- contract, operation, router-case, fixture, and experiment IDs;
- requested device, selected device, `fallback_used`, `evaluated`, and
  `synchronized`;
- checkpoint repository, revision, filename, size, and SHA-256;
- tensor name, GGUF type, quantization, exact dimensions, reader shape,
  orientation, offsets, encoded length, and encoded SHA-256;
- hidden-state semantic boundary, shape, dtype, per-row hashes, and fixture
  hash;
- batch size, expert count `128`, top-k `8`, tie rule, normalization rule, and
  exact expert-weight scale interpretation;
- complete finite logits `[N,128]` and their canonical float32 SHA-256;
- selected expert IDs `[N,8]`;
- complete full-softmax probabilities `[N,128]` and their canonical float32
  SHA-256;
- selected pre-normalization probabilities `[N,8]`;
- normalized weights `[N,8]` and their canonical float32 SHA-256;
- oracle generator/revision and input/output hashes;
- complete comparison metrics from Section 8;
- warm-up count, measured count, per-run output hashes, IDs, comparisons, and
  pass/fail state;
- every raw timing observation and reproducible statistics;
- component allocation, MLX allocator, process footprint, pressure, and
  non-overlap caveats;
- clean source commit, dirty state, UTC timestamp, sanitized command and
  environment, host/tool versions, and exclusions.

Failed and aborted results MUST use the same schema where fields are available,
identify the failed stage and stable error code, retain all observations made
before failure, and make no verified claim.

## 12. Timing boundary

Timing MUST use `time.perf_counter_ns()` or an equivalently monotonic,
high-resolution source. Raw integer nanoseconds MUST be retained.

The following boundaries MUST be recorded when technically separable:

- checkpoint admission/full-file verification, outside router timing;
- positional tensor read;
- storage validation and F32 decode, with dequantization recorded as
  `not_applicable`;
- host-to-MLX construction/transfer;
- graph construction;
- evaluated projection;
- evaluated top-k;
- evaluated normalization;
- minimally instrumented projection-through-normalization total with one final
  evaluation and GPU synchronization;
- synchronized readback; and
- explicitly labeled end-to-end router command duration.

An instrumented stage duration MUST stop only after evaluation and
`mx.synchronize(mx.gpu)`. Stage barriers perturb a lazy graph, so instrumented
stage values MUST be labeled separately from the minimally instrumented total,
and their sum MUST NOT be asserted equal to that total.

A fresh worker's first read MUST be labeled
`first_read_new_process_os_cache_uncontrolled`. It MUST NOT be called
filesystem-cold unless cache state was controlled and recorded under the
separate `controlled_cold` condition. Warm resident execution and repeated file
reads MUST remain separate series. Minimally instrumented totals use the exact
`minimally_instrumented` instrumentation-mode value.

Every series MUST retain all warm-up and measured observations and publish
median, arithmetic mean, sample standard deviation, minimum, maximum, p5, p25,
p75, p95, and coefficient of variation under the frozen statistical method.
An unavailable or semantically inseparable phase is `not_available` with a
reason; it is never represented as a measured zero.

## 13. Structured failures

Host admission MUST use stable bounded errors for these conditions:

| Condition | Required code |
|---|---|
| Checkpoint repository/revision/name mismatch | `model_identity_mismatch` |
| Checkpoint byte size mismatch | `model_size_mismatch` |
| Checkpoint or frozen range hash mismatch | `model_checksum_mismatch` |
| Missing router tensor | `missing_tensor_role` |
| Duplicate router tensor | `duplicate_tensor_role` |
| Wrong tensor dimensions/type/size | `model_tensor_mismatch` |
| Unsupported frozen tensor type | `unsupported_tensor_quantization` |
| Overflowing/out-of-file tensor range | `invalid_tensor_range` |
| Insufficient disk/memory/headroom | `model_budget_exceeded` |

Worker/protocol failures MUST use the existing stable protocol vocabulary:

| Condition | Required code |
|---|---|
| Extra/missing control fields or invalid scalar types | `malformed_request` |
| Wrong router/case identity or depth promotion | `unsupported_operation` |
| Hidden-state, tensor, logit, ID, or weight shape mismatch | `invalid_shape` |
| Wrong dtype or non-finite decoded input | `invalid_dtype` |
| Ambiguous/wrong orientation | `invalid_layout` |
| Truncated, overlong, or changed inherited range | `invalid_byte_count` |
| CPU selection, fallback request, or unavailable GPU | `device_unavailable` |
| MLX scheduling/evaluation/synchronization failure | `evaluation_failed` |
| Oracle, ID, repeatability, or tolerance failure | `comparison_failed` |
| Pressure, allocation, sample, or protocol bound exceeded | `resource_limit` |
| Invalid internal return type or impossible invariant | `internal_worker_error` |

Validation of model bytes and hidden-state values MUST complete before any
router-specific MLX array construction, scheduling, or evaluation. The existing
worker may import MLX and discover its runtime before reading requests; Feature
002 does not change that startup behavior. Tests MUST prove the router runner is
not called for every pre-execution failure class.

## 14. Feature 001 preservation

Implementation MUST be additive:

- add a separate router module, request, result, parser, and command;
- leave Feature 001's `ModelSliceRequest`, `ModelSliceResult`, slice ID,
  16-row expert tensor constants, comparison record, fixture set, and task list
  unchanged;
- retain the same read-only inherited-descriptor mechanism and strengthen only
  shared immutable-file rechecks;
- keep all Feature 001 tests green; and
- avoid changes to inherited engine, CUDA kernels, Linux `io_uring` selection,
  or serving behavior.

Feature 002 tests and evidence MUST NOT retroactively expand any Feature 001
capability claim.

## 15. Explicit exclusions

This contract does not establish or permit claims for:

- any routed or shared expert MLP;
- expert gate/up/down projections;
- selected-expert execution or weighted aggregation;
- a complete MoE block or transformer layer;
- attention, residual paths, tokenizer, embeddings, or verified prior-layer
  execution by PulsarMLX;
- model-output logits, token selection, generation, or serving;
- full-model or giant-model inference;
- custom Metal kernels or Apple multi-device execution;
- tokens per second, layer throughput, or extrapolated model performance; or
- Linux/CUDA runtime parity for PulsarMLX changes.

A result that omits these exclusions or presents router timing as any excluded
capability is not contract-conformant.
