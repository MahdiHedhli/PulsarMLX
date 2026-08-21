# F017 Production Serial-F32 Equivalence Specification v1

Status: `PREPARED_FOR_INDEPENDENT_REVIEW`

This specification freezes the first, non-executing phase of the F017 production serial-f32 equivalence program. It does not reopen the closed representative M1-F0 proof/reference program and does not claim that any production comparison has run.

## Authority and scope

The accepted closure declaration at `db60f6bd4aeffe6d2f85530ddf5e3bb0e1ebbf71` is the immutable comparison baseline. Its routed aggregate, FFN, and S2 are proof/reference surfaces, not production serial-f32 results.

The extant full production graph is the inherited Linux/CUDA path `crates/engine/src/lib.rs::Model::eval_layer`, dispatched through `State::forward_rows` and the kernels in `crates/kernels/cuda/pulsar_kernels.cu` and `mla_kernels.inc`. It is `AUTHORITATIVE_PRODUCTION` for the current executable production semantics it implements. The Apple `f017-glm52-runner` is the canonical F017 runner, but its current production adapter substitutes MLX only for projection matvecs; `run_r9_with_matvec` and `run_r10_with_matvec` retain scalar qualification semantics, and R10 deliberately uses the proof/reference binary64 route/aggregate/FFN surface. It is therefore a `SUPPORTED_ALTERNATE` for projection qualification and `REFERENCE_ONLY` for full-layer composition, not an authoritative production serial-f32 S0-to-S2 implementation.

No full Apple production serial-f32 entry point currently instantiates every row below. Direct Metal expert kernels remain planned work. Consequently the comparison execution status is `BLOCKED`, even though the production inventory and comparison policy are frozen.

## Exact vocabulary

Intended relationship has exactly four values:

- `BYTE_EQUIVALENCE_REQUIRED`: canonical bytes, dtype, shape, and endianness must match; a tolerance cannot substitute.
- `NUMERICAL_EQUIVALENCE_REQUIRED`: all frozen numeric predicates must pass and structural predicates remain exact.
- `INTENTIONAL_DISTINCTION_EXPECTED`: the compared surfaces are intentionally different; the later result may be `INTENTIONALLY_DISTINCT`, never inferred before execution.
- `UNRESOLVED_PRODUCTION_SEMANTICS`: a production arithmetic detail is not sufficiently specified to execute a valid comparison.

Execution status has exactly four values: `NOT_EXECUTED`, `EXECUTION_AUTHORIZATION_REQUIRED`, `READY_FOR_EXECUTION_PREPARATION`, and `BLOCKED`.

Observed result is reserved for the later execution phase and has exactly four values: `BYTE_EQUIVALENT`, `NUMERICALLY_EQUIVALENT_WITHIN_FROZEN_TOLERANCE`, `INTENTIONALLY_DISTINCT`, and `FAILED_FROZEN_EQUIVALENCE_CONTRACT`. Every row in this specification has a null observed result.

## Production graph and arithmetic

All tensor payloads are finite and contiguous. Production activations are binary32 unless stated otherwise. CUDA is built with `-O3 --use_fast_math`; device `expf`, `rsqrtf`, contraction, and per-kernel reduction topology are implementation-specific. Those facts are part of the implementation identity, not portable IEEE promises.

| Stage | Authoritative source/symbol | Input → output | Accumulation, order, rounding | Intended relationship |
|---|---|---|---|---|
| attention input normalization | `engine::Model::eval_layer` → `pulsar_rms_norm` | f32[6144] → f32[6144] | 256-lane strided f32 sums, binary-tree shared reduction, `rsqrtf(sum/n+eps)`, f32 multiplies | NUMERICAL_EQUIVALENCE_REQUIRED |
| Q rank projection | `eval_layer` → `matmul_q8_0` | f32[6144], quantized Q5_K → f32[1536] | quantized CUDA matmul; tile/dequant/FMA details kernel/toolchain-bound | UNRESOLVED_PRODUCTION_SEMANTICS |
| Q rank normalization | `eval_layer` → `pulsar_rms_norm` | f32[1536] → f32[1536] | same 256-lane tree RMSNorm | NUMERICAL_EQUIVALENCE_REQUIRED |
| Q projection | `eval_layer` → `matmul_q8_0` | f32[1536], Q5_K → f32[64,256] | quantized CUDA matmul; kernel order | UNRESOLVED_PRODUCTION_SEMANTICS |
| KV-A projection | `eval_layer` → `matmul_q8_0` | f32[6144], Q5_K → f32[576] | quantized CUDA matmul; kernel order | UNRESOLVED_PRODUCTION_SEMANTICS |
| compressed-KV normalization | `eval_layer` → `pulsar_mla_kv_lora_rms_norm` | f32[512] → f32[512] | CUDA f32 partials/tree; epsilon f32 | NUMERICAL_EQUIVALENCE_REQUIRED |
| RoPE | `eval_layer` → `pulsar_mla_rope_tail` | f32 query/rope tail → f32 | CUDA `powf`/trig, f32 multiply/add; toolchain implementation-bound | UNRESOLVED_PRODUCTION_SEMANTICS |
| low-rank K projection | `eval_layer` → `pulsar_mla_qk_lowrank` | f32 query, quantized K-B → f32 | CUDA quantized/tiled dot products | UNRESOLVED_PRODUCTION_SEMANTICS |
| attention scores | `eval_layer` → `pulsar_mla_attention` | f32 query/cache → f32 scores | lane-strided f32 dots then fixed XOR warp reduction; latent and rope partials joined in f32 | NUMERICAL_EQUIVALENCE_REQUIRED |
| softmax | `pulsar_mla_attention` | f32 scores → f32 weights | f32 max tree, `expf`, f32 sum tree, denominator clamp 1e-20 | UNRESOLVED_PRODUCTION_SEMANTICS |
| value accumulation | `pulsar_mla_attention` | f32 weights/values → f32 heads | CUDA serial/tiled f32 per output with cache-format dequantization | UNRESOLVED_PRODUCTION_SEMANTICS |
| attention output projection | `eval_layer` → `matmul_q8_0` | f32 heads, quantized output → f32[6144] | quantized CUDA matmul | UNRESOLVED_PRODUCTION_SEMANTICS |
| S1 residual | `eval_layer` → `kernels::add` | f32 S0 + f32 attention → f32[6144] | one binary32 add per coordinate | NUMERICAL_EQUIVALENCE_REQUIRED |
| FFN RMSNorm | `eval_layer` → `pulsar_rms_norm` | f32 S1 → f32[6144] | 256-lane f32 tree RMSNorm | NUMERICAL_EQUIVALENCE_REQUIRED |
| router logits | `eval_layer` → `matmul_f32` | f32[6144], f32[256,6144] → f32[256] | lane-strided f32 products and 256-lane tree reduction | NUMERICAL_EQUIVALENCE_REQUIRED |
| sigmoid and correction bias | `router_select_kernel` | f32 logits/bias → f32 probabilities/scores | branch-stable f32 sigmoid using `expf`; one f32 bias add | UNRESOLVED_PRODUCTION_SEMANTICS |
| ranking/top-k | `router_select_kernel::router_better` | 256 f32 scores → 8 ids | descending score; exact ties prefer lower expert id; repeated warp selection | BYTE_EQUIVALENCE_REQUIRED |
| routing normalization | `router_select_kernel` | 8 f32 probabilities → 8 f32 weights | rank-order f32 sum, clamp 2^-14, divide then multiply scale in f32 | NUMERICAL_EQUIVALENCE_REQUIRED |
| routed gate/up projections | `eval_layer` → `moe_pair_swiglu` | f32 F_norm, IQ2_XXS weights → f32 intermediates | CUDA quantized expert kernel, tile/FMA/compiler-bound | UNRESOLVED_PRODUCTION_SEMANTICS |
| SiLU | `moe_pair_swiglu` | f32 gate → f32 | CUDA sigmoid/SiLU approximation and f32 rounding | UNRESOLVED_PRODUCTION_SEMANTICS |
| gate/up product | `moe_pair_swiglu` | f32 gate/up → f32 | one implementation f32 multiplication after SiLU | NUMERICAL_EQUIVALENCE_REQUIRED |
| routed down projection | `eval_layer` → `moe_down` | f32[2048], IQ3_XXS → f32[6144] per slot | CUDA quantized dot and warp reduction | UNRESOLVED_PRODUCTION_SEMANTICS |
| routed aggregate | `eval_layer` → `moe_slot_sum` | 8 f32 expert slots → f32[6144] | selected-slot rank-order serial binary32 left fold, slot 0 through 7 | INTENTIONAL_DISTINCTION_EXPECTED |
| shared expert | `eval_layer` shared `matmul_q8_0`/`swiglu` | f32 F_norm, Q5_K/Q6_K → f32[6144] | CUDA quantized projections, f32 SiLU/product; kernel-dependent reductions | UNRESOLVED_PRODUCTION_SEMANTICS |
| routed plus shared FFN | `eval_layer` → `kernels::add` | f32 routed + f32 shared → f32[6144] | one binary32 add per coordinate, routed operand first | INTENTIONAL_DISTINCTION_EXPECTED |
| S2 residual | `eval_layer` → `kernels::add` | f32 S1 + f32 FFN → f32[6144] | one final binary32 add per coordinate | INTENTIONAL_DISTINCTION_EXPECTED |

## Frozen comparison policy

Structural checks are conjunctive: exact stage identity, canonical little-endian encoding, dtype, shape, finite values, and retained-authority SHA must pass before numeric metrics.

- Route membership and route order must both match exactly. Production order is not canonicalized away. Score ties are resolved by lower expert id.
- Routing weights must satisfy both the accepted mathematical interval and `max_abs_error <= 1e-5`; the engineering half-interval diagnostic is `max_abs_error <= 5e-6`. Membership or order failure fails routing irrespective of weight error.
- Expert projection coordinates use the operand-conditioned bound in `production-expert-tier-b-v1`: `2*gamma(2*n)*sum_abs_products + 4*n*2^-149`, with no NaN/Inf and exact signed-zero agreement where the bound requires it.
- The routed aggregate may use `max_abs <= 0.015625`, `RMSE <= 0.0078125`, and cosine similarity `>= 0.9999` only after exact route membership/order passes. This threshold is inherited from the accepted R10 aggregate qualification.
- Final S2 may use `max_abs <= 0.0625`, `RMSE <= 0.03125`, and cosine similarity `>= 0.999` only after every upstream structural gate passes. This threshold is inherited from the accepted complete-layer aggregate qualification.
- Relative error is deliberately disabled: it is unstable near zero and adds no soundness beyond the per-coordinate absolute/operand-conditioned predicates. No hidden relative threshold is permitted.
- NaN or infinity is always an immediate failure. Byte-required stages require signed-zero byte identity. Numeric stages record signed-zero mismatches; expert-bound stages require zero such mismatches.
- R9 fixture thresholds are not promoted to full real geometry. Stages whose only available behavior is compiler/kernel dependent remain blocked; no convenient tolerance is invented.

## Retained reuse and checkpoint decision

The retained matrix in the machine contract binds S0, all accepted attention/router stages, S1, F_norm, route, eight expert outputs, routed aggregate, shared output, FFN, S2, and their reuse/evidence authorities. Neutral inputs and model weights may feed a future production run. Proof/reference outputs are expected/comparison surfaces only and must never be relabeled as production outputs.

`CHECKPOINT_ACCESS_REQUIRED: NO`. The accepted retained attention, router, routed-expert, shared-expert, S1, and neutral-input authorities contain the inputs and weight payloads needed for a retained-only comparison. The blocker is the absence of a fully accepted production serial-f32 Apple entry point and unresolved kernel-specific arithmetic, not missing checkpoint data. Any later discovery of a missing tensor invalidates this decision and requires a separate authorization; ledger 175 cannot move in this phase.

## Master ledger reconciliation

Repository inspection confirmed the post-closure COUNT finding. The immutable master ledger v1 ends at 166 after canonical shared-expert weight recovery. The later accepted representative M1-F0 attention/route event contains nine unique durable receipts with ordinals 0..8 and consecutive `ledger_after` values 167..175; their packed-byte total is 132,900,864, the event terminal is COMPLETE, and both closure authorities record 175. This is a stale master accounting surface, not an ambiguous event conflict.

The append-only authoritative master ledger v2 preserves v1 byte-for-byte as its historical prefix and appends the SHA-bound representative event and exact receipt chain. It resolves to 175 with zero gaps, overlaps, duplicate receipts, or unexplained increments. This reconciliation consumed zero payloads and performed zero checkpoint reads, shard opens, or numerical executions.

Beginning after the reconciliation base, every future real-payload event result that advances receipt accounting must update the master ledger in the same commit. The post-event count must be derived from validated receipts. A manually repeated count is not an authority. `terminal.consumed_reads` must equal the validated receipt count, and terminal JSON is never the sole accounting authority.

## Mechanical authority resolution

The generic bound-authority resolver now enforces every new F017 `path` + `sha256` + `field`/`json_path` declaration by loading duplicate-key-hardened committed JSON, verifying bytes, resolving the exact field, and comparing it with the declared expected value. The serial-f32 contract uses it for master ledger v2, closure package/declaration ledger values, RMSNorm epsilon, and top-k.

Executable numeric bindings mechanically extract the production router denominator clamp, attention softmax denominator clamp, RMS epsilon metadata key, and expert-count metadata key from the exact source bytes. RMS epsilon and top-k values are runtime metadata, so their concrete representative values are separately bound to the accepted boundary and selection contracts. Device `expf`/`rsqrtf`, contraction, tile topology, and runtime metadata loading cannot be reduced to static constants; those limitations remain explicit and block execution rather than being represented as executable bindings.

## Future execution ownership gate and rebind backlog

The retained-only specification is not blocked by an absent execution wrapper, but the next execution-capable generation must close RN1 before authorization: acquire an exclusive owned lock before authority, durably record ownership, terminalize only an attempt this invocation owns, derive consumed reads from receipts, cross-check terminal counts, and retain the one-terminal/one-invocation restriction until independent acceptance.

The next natural rebinds are: terminalizer orphan-hash-to-inventory binding at the next terminalizer contract; restored decoder-binding declarations at the next decoder consumer; gate self-SHA at the next execution gate; a committed RN3 partial-root clearing procedure before the next single-use release; and wrapper-v1 tombstoning in the next wrapper supersession package. None is load-bearing for this non-executing specification, and all become mandatory at the named execution-capable boundary.

## Future execution roadmap

1. Human approval is required to implement and independently qualify a retained-only production capture runner. It must expose no checkpoint path and must satisfy the RN1 ownership gate.
2. Bind exact source head, compiler, CUDA/Metal/runtime, device, fast-math flags, kernel hashes, and fixed thread/device configuration.
3. Preflight all retained inputs by descriptor with expected/before/consumed/after identity and prove ledger 175 with zero reads/opens.
4. Capture canonical bytes at every frozen stage without changing the production call graph.
5. Run exact membership/order checks before weight metrics, then compare stages in graph order.
6. Require ten same-environment deterministic repetitions; distinguish semantic numerical equivalence from implementation-specific byte reproducibility and make no hardware/toolchain portability claim.
7. Bank the event result, receipts, and master ledger update in the same commit, plus journal, environment identity, stage hashes, metric vectors, and terminal state. Any failure is terminal and cannot weaken thresholds.
8. Independent Fable 5 review is required before any result claim.

Termination is `BLOCKED` until the full production entry point and every `UNRESOLVED_PRODUCTION_SEMANTICS` row acquire committed implementation authority and defensible pre-execution tolerances. No production-equivalence execution is authorized by this specification.
