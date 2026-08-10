# Feature 018 Overnight Review

> Post-review status: the required Opus fixes and decisive strict qualification
> are documented in [F018_POST_OPUS_QUALIFICATION.md](F018_POST_OPUS_QUALIFICATION.md).
> The later same-boundary verdict is GO; this overnight report remains the
> immutable pre-review handoff.

## Executive result

Feature 018 qualified a true direct-packed IQ2_XXS Metal GEMV from a synthetic
matrix through one complete real layer and one exact P1. The P1 produced the
frozen prefix `[9703,21615]` with zero CPU fallback, zero complete-f32 Metal
weight materialization, zero protected shared-cache eviction, and normal
resource observations. This is a research boundary, not production readiness,
P2, golden-eight, or steady-state throughput evidence.

The implementation range starts at `1905032b` and the final measured evidence
source is `2f51333e`. The evidence and its generated table were banked at
`f8b779f9`; the closeout documentation is the commit containing this file.

## Kernel design

- Input: packed IQ2_XXS matrix bytes plus one contiguous f32 activation.
- Output: one f32 vector; no complete decoded f32 weight matrix is built.
- Geometry: one logical Metal thread per output row.
- Decode: each thread walks 66-byte blocks representing 256 weights, using the
  frozen magnitude and sign lookup tables.
- Accumulation: sequential f32 multiply-accumulate in row/block order.
- Tails: admitted columns must be divisible by 256; malformed shapes, packed
  lengths, activation lengths, and non-finite activations fail before dispatch.
- Completion: validation mode commits one command buffer, waits for completion,
  checks command status, and records dispatch, GPU interval, synchronization,
  and total call time separately.

The path is direct-quantized under the frozen contract: Metal consumes packed
weights. Small lookup buffers are format metadata, not decoded weights. There
is no hidden CPU fallback inside a successful direct call.

## Numerical contract and results

`specs/018-direct-quantized-metal-runtime/numerical-qualification-contract.md`
was committed before candidate output. Matrix gates use absolute/relative
`0.0005`, cosine `0.999999`, and norm-ratio `[0.9995,1.0005]`; composed gates
use absolute/relative `0.005`, cosine `0.999`, and norm-ratio `[0.995,1.005]`.
Teacher-forced validation remains required after any greedy disagreement.

| Boundary | Classification | Current/reference (s) | Candidate (s) | Max abs error | Result |
| --- | --- | ---: | ---: | ---: | --- |
| Synthetic 64×6144 | numerically qualified, greedy not applicable | n/a | 0.000962 median | 0.000619888 | passed |
| Real layer-3 expert-15 gate | numerically qualified, greedy not applicable | 0.091134 median | 0.001387 median | 2.30968e-7 | passed |
| Real layer-3 expert-15 up | numerically qualified, greedy not applicable | 0.089101 median | 0.001183 median | 2.01166e-7 | passed |
| Complete routed expert | numerically qualified, greedy not applicable | 0.241911 median | 0.137713 median | 3.52884e-10 | passed |
| Top-8 plus shared MoE | numerically qualified, greedy not applicable | 1.701675 median | 0.895945 median | 5.58794e-9 | passed |
| Complete layer 3 | numerically qualified, greedy not applicable | 2.430633 median | 1.688662 median | 9.31323e-9 | passed |
| P1 | exact greedy token gate | 1425.756 historical wall | 1043.248 evidence wall | token exact | passed |

The complete-layer reduction was 0.741972 seconds (30.5%) and therefore met
the predeclared optional-P1 admission gate. Cross-commit P1 wall comparisons
are observations, not a controlled benchmark population.

## P1 result

| Field | Value |
| --- | ---: |
| Exact tokens | `[9703,21615]` |
| Evidence wall | 1043.247634 s |
| Cold prompt stack | 838.497530 s |
| Full-vocabulary logits | 77.573811 s |
| Terminal warm stack | 127.009655 s |
| Direct routed experts | 1184 |
| Explicit reference routed experts | 32 |
| Direct IQ2 GEMVs | 2368 |
| Direct packed bytes read | 7,681,867,776 |
| Direct worker synchronized-call total | 4.286873 s |
| Protected shared-cache hits | 228 |
| Protected shared entries | 228 |
| Protected shared logical bytes | 11,475,615,744 |
| Protected shared evictions / CPU fallbacks | 0 / 0 |

Both 79-layer stacks and both sets of 76 MoE routing records are complete.
Every MoE record contains eight routed experts and shared expert zero. Resource
state was normal at admission and after both stacks. The process peak RSS
observation was 78,646,657,024 bytes; RSS after the terminal stack was
33,715,716,096 bytes. These are process observations, not allocator-overhead
models.

## Setup versus steady state

The gate/up matrix records separate process-first shader compilation and
registration from 30 measured warm calls after three warmups. The P1 worker
compiled once, then issued 2,368 calls. Its cumulative direct timings were
1.518706 seconds of positional reads, 0.088089 seconds of no-copy registration,
2.427512 seconds of GPU command intervals, 3.954250 seconds of synchronization,
and 4.286873 seconds of synchronized call total. GPU interval and
synchronization are not additive.

The two-slot research worker intentionally had no P1 gate/up cache hits and
recorded 2,366 bounded slot evictions. This validates stable reuse and teardown;
it is not the production residency policy.

## Buffer ownership

Feature 018 selectively reused reviewed Feature 017 infrastructure rather than
merging its branch: Rust owns bounded page-aligned slabs; Objective-C++ creates
`newBufferWithBytesNoCopy` resources; Rust lifetimes keep the slab and Metal
context alive through registration and dispatch. A slot retains its stable ID
and address but now exposes a monotonic occupancy generation. Tests cover
cross-context rejection, changed generation after reuse, malformed registration
lengths, deterministic repeats, and 32 complete create/register/dispatch/drop
cycles.

The P1 integration is opt-in (`direct_iq2_gate_up`). It selects direct execution
only when both routed gate and up tensors are IQ2_XXS. Other routed formats use
an explicitly counted reference path; shared experts and IQ3_XXS down remain on
the qualified reference path. The default inference mode is unchanged.

## Failures retained

1. The first P1 launch pointed `PULSARMLX_GLM_GGUF` at shard 1 rather than the
   six-shard directory. Catalog construction then lacked `token_embd.weight`
   and failed before a stack or evidence write. The fresh output path remained
   absent. The corrected directory catalog resolved 1,809 tensors across six
   shards before the sole measured P1.
2. The routed-expert publisher originally rejected legitimate zero-time warm
   storage samples. The semantic summary was corrected to allow nonnegative
   resident samples before the successful record.
3. The first complete-layer publisher selected a historical file without
   layer 3 and failed before publication. It was bound to the committed
   layer-3 stage profile and rerun; no candidate result was promoted from the
   failed publication attempt.

These were harness/admission defects, not numerical divergences. No failed run
was rewritten into a passing record.

## Absolute opportunity and next gate

Direct IQ2 gate/up materially improved the bounded layer and exact P1, but the
remaining reference path dominates. In the routed-expert record, IQ3_XXS down
decode alone had a 0.113225-second median while warm direct gate/up synchronized
calls totaled 0.003357 seconds. In the complete-layer record, routed IQ3 down
decode had a 0.642490-second median; P1 still attributed 740.519160 seconds to
reference-path dequantization across all formats.

The exact next gate is design review of accumulation ordering and no-copy
lifetime, followed by a separately frozen IQ3_XXS-down single-matrix contract
if that review retains direct-quantized Metal as the next measured primitive.
No second kernel, P2, or golden-eight run was started in this sprint.

Feature 017 should reuse the packed request/result contract and stable slab
ownership, but replace the JSON-line Python worker boundary with Rust-native
scheduling and a narrow native Metal bridge. The current P1 proves integration
semantics; it does not establish that subprocess serialization is a shipping
boundary.

## Unresolved risks

- F32 accumulation order is numerically qualified, not bit-identical, against
  the reference matrices.
- One-thread-per-row geometry is inspectable but not proven optimal.
- The two-slot worker rereads every P1 routed gate/up matrix and does not test a
  production residency/prefetch policy.
- Activation and output vectors cross the Python/Rust process boundary as JSON
  bit patterns in the research harness.
- Only IQ2_XXS routed gate/up is direct; IQ3 down, shared experts, attention,
  logits, and other formats remain reference paths.
- P1 is one machine/checkpoint/prompt observation and cannot establish general
  token throughput, long-context correctness, thermal stability, or serving.

## Validation

- Complete checkpoint-free research suite: 455 tests passed.
- Python worker protocol suite: 89 tests passed.
- Cargo workspace check and full workspace tests passed; only documented
  inherited macOS/quant warnings remain.
- Native direct-IQ2 Metal tests: 10 passed, including 100 deterministic repeats,
  cross-context rejection, stale-generation identity, and repeated teardown.
- Native MLX device smoke, seven tensor fixtures, synthetic routed MoE, and the
  Rust-to-Python worker integration passed explicitly.
- Feature 002 schema/package fixture gates remain green and checkpoint-free.
- Every Feature 018 raw record passes duplicate-key, semantic, source/checkpoint,
  fallback, materialization, resource, claims-ledger, reviewer-index, and
  privacy validation.
- All seven Feature 018 Markdown tables regenerate byte-for-byte from their raw
  JSON records.
- `specify check`, `specify integration status`, the Feature 018 prerequisites
  script, and `git diff --check` passed.
- Both Apple Silicon CI jobs passed for validation attestation `25afd71b` in
  run `31358282448`.

The workspace check still reports the inherited `unused_mut` in
`crates/quant/src/iq.rs` and inherited macOS-only unused serve items. They were
not introduced or broadly cleaned in this feature.

## Opus review questions

1. Does sequential f32 accumulation in one Metal thread preserve the intended
   validation semantics, and what numerical contract should govern a later
   parallel reduction without pretending it is bit-exact?
2. Do the Rust borrow, registration-context check, occupancy generation, and
   Objective-C strong references fully cover `newBufferWithBytesNoCopy`
   lifetime, command failure, and teardown hazards?
3. Is the implementation truly direct-quantized given packed matrix input and
   on-kernel lookup/decode, or is any hidden materialization/import cost missing
   from telemetry?
4. Are the 66-byte block layout, expert slab offsets, sign lookup indexing,
   column divisibility, and tail rejection sufficient to rule out layout traps
   across admitted IQ2_XXS matrices?
5. Given the measured absolute profile, should the next frozen candidate be
   IQ3_XXS routed down, or should Feature 017 first remove the subprocess and
   orchestration boundary before another kernel is qualified?

## Reproduction

Checkpoint-free contracts and native fixture:

```sh
uv run --frozen python -m unittest \
  scripts/research/tests/test_f018_numerical_contract.py \
  scripts/research/tests/test_f018_evidence.py
cargo test -p stream --test iq2_xxs_metal
```

Deterministic tables:

```sh
for raw in docs/research/glm52/raw/f018*.json; do
  table="docs/research/glm52/tables/$(basename "${raw%.json}").md"
  PYTHONPATH=scripts/research uv run --frozen python \
    scripts/research/analyze_glm52_iq2_xxs_metal.py \
    --input "$raw" --output "$table" --check
done
```

Tier-3 P1 requires the already admitted six-shard directory and a clean source
commit:

```sh
PULSARMLX_GLM_GGUF='<checkpoint-directory>' \
uv run --frozen python scripts/research/glm52_inference.py \
  --mode inference --n-new 1 --cache-gib 16 \
  --cache-policy decoded_shared_only --decoder-mode numpy_vectorized \
  --dense-read-mode whole_matrix_numpy_q5_q8_q6_head_numpy \
  --expert-execution-mode direct_iq2_gate_up \
  --direct-worker target/debug/iq2-metal-worker \
  --out '<fresh-public-safe-output>.json'
```
