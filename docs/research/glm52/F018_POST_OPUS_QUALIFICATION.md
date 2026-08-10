# PulsarMLX F018 Post-Opus Qualification Sprint

## Executive result

The post-Opus IQ2_XXS gate/up qualification verdict is **GO**. On the same
bound layer-3 expert-15 gate matrix, the authoritative strict sequential Metal
scaffold measured a 0.001352563-second warm median versus 0.091565000 seconds
for the optimized NumPy-plus-MLX reference, a 67.70× bounded ratio and
0.090212437 seconds of median work recovered. Both populations contain 30
retained samples after warmup.

The candidate is `numerically_qualified_greedy_identical`, not bit exact. It
had zero frozen-tolerance mismatches, zero signed-zero mismatches, maximum
absolute error `2.3096799850463867e-7`, RMSE
`2.5522323593914772e-8`, cosine similarity `0.9999999999989305`, and norm
ratio `1.0000000124169286`. No parallel IQ2 kernel, IQ3-down implementation,
P1, P2, or golden-eight run was started during this qualification.

The review started from clean branch source `5978aa63`. The authoritative
strict matrix evidence source is `5e4056cb`; the committed three-way decision
is `b5f40325`. The final validation-attestation commit and CI run are recorded
in the Feature 018 task closeout and repository history.

## Reference model and numerical contract

The bit-exact oracle is the scalar IQ2_XXS decoder followed by same-order,
sequential-column f32 accumulation. The optimized MLX tiled matmul is a Tier B
numerical comparator and is not the bit-exact oracle.

The current one-thread-per-output-row Metal implementation is retained as the
deterministic qualification scaffold. A future SIMD-group or threadgroup
implementation would be a separate candidate because parallel reduction may
change accumulation order; it must pass the already frozen Tier B gates and
teacher-forced validation rather than being described as bit exact.

## Metal compiler semantics

Qualification builds use explicit `MTLCompileOptions`:

- `fastMathEnabled = NO`
- `mathMode = MTLMathModeSafe`
- `mathFloatingPointFunctions = MTLMathFloatingPointFunctionsPrecise`
- `languageVersion = MTLLanguageVersion3_2`
- pipeline identity `iq2_xxs_sequential_scaffold_v1`

The settings are emitted in native telemetry and required by the strict
evidence validator. Library compilation and pipeline creation are timed
separately. The strict synthetic scaffold also passed 100 deterministic
repetitions under the frozen Tier B contract; it was not f32-bit identical.

## Validation dispatch accounting

The committed P1 contains two complete 79-layer stacks. Each stack issued 592
direct routed-expert executions and 16 explicit reference executions. Across
the full P1 this is 1,184 direct and 32 explicit reference executions.

The 16 reference executions per stack are completely explained:

| Layer | Experts | Gate/up quantization | Reason | Classification |
| ---: | ---: | --- | --- | --- |
| 8 | 8 routed experts | IQ2_S | outside the admitted IQ2_XXS gate/up scope | intentional explicit reference dispatch |
| 78 | 8 routed experts | Q2_K | outside the admitted IQ2_XXS gate/up scope | intentional explicit reference dispatch |

The machine-readable inventory records every layer, expert ID, tensor name,
role, quantization, selected-expert shape, and reason code. It reports zero
capability misses, runtime errors, fallbacks, and direct errors. “Explicit
reference dispatch” is selected before candidate invocation; “fallback” means
a selected direct operation failed. Validation mode now fails closed on the
latter and cannot pass by silently recovering to the reference implementation.
Any future production fallback policy must remain explicit and observable.

## In-flight lifetime safety

Every submitted command acquires a native in-flight use. The completion
handler strongly retains the registration and releases that use only after the
command buffer completes. Destruction marks the registration as closing and
waits for the in-flight count to reach zero. Rust borrows prevent dropping,
mutating, or reusing the page-aligned slab while a registration exists, and
the occupancy generation protects stable-slot reuse.

Native and Rust tests cover submit/wait/destroy, repeated
register/use/release, reuse after completion, cross-context and stale-generation
rejection, error paths, and compile-fail attempts to drop or mutate an owned
slab early. The safety mechanism is enforced in code; it is not caller
discipline documented only in comments.

## Lookup-table address-space result

Moving the IQ2 magnitude/sign lookup tables from device to constant address
space preserved the candidate output hash but did not improve this bounded
scaffold. The 100-sample constant median was 0.000927521 seconds versus
0.000718312 seconds for the device control, a 1.29125 constant/device ratio.
The device address space remains in the implementation. These are sequential
synthetic populations, not a counterbalanced real-matrix performance claim.

## Decisive three-way matrix benchmark

The common binding is `blk.3.ffn_gate_exps.weight`, layer 3, expert 15,
IQ2_XXS, shape `[2048,6144]`. Packed bytes and the activation are fixed by
SHA-256 in the raw record. All three variants use the same input and output
boundary; neither direct variant materializes a complete f32 weight matrix.

| Variant | Role | Samples | Median (s) | Mean (s) | Std dev (s) | Min (s) | Max (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A. optimized NumPy + MLX | authoritative optimized reference | 30 | 0.091565000 | 0.092062499 | 0.003104476 | 0.089110792 | 0.107949375 |
| B. default-options direct | historical context only | 30 | 0.001387167 | 0.001397043 | 0.000045128 | 0.001320834 | 0.001495916 |
| C. strict direct Metal | authoritative qualification candidate | 30 | 0.001352563 | 0.001463389 | 0.000364009 | 0.001252666 | 0.002702625 |

Variant B used unversioned `options:nil` compiler defaults and is not a
controlled current-source population. Variant C is the decision input.

Strict first-use/setup telemetry records one 3,244,032-byte checkpoint read in
0.003825292 seconds, library compilation in 0.000707792 seconds, pipeline
creation in 0.047232625 seconds, registration in 0.000029083 seconds, and a
0.003205834-second first synchronized call. GPU kernel interval and
synchronization overlap and are not added together. The strict candidate
records zero CPU fallback, direct error, and complete-f32 materialization;
resource state was normal before and after.

## P1 correction and scope

The already committed P1 remains exact `[9703,21615]`: 838.497530 seconds for
the cold stack, 77.573811 seconds for full-vocabulary logits, 127.009655
seconds for the terminal warm stack, and 1043.247634 seconds evidence wall.
The earlier 196.163-second warm figure is rejected; it mixed incompatible
boundaries. P1 was not rerun for this review, and its cross-commit wall delta
is not the decisive same-boundary benchmark.

## Feature boundary

Feature 017 owns reusable stable slabs, registration and in-flight lifecycle,
generic backend telemetry, native-ready residency, generic direct/reference
dispatch, and validation fail-closed semantics. Feature 018 owns the IQ2
packed layout and kernel, format-specific dispatch and numerical evidence, and
any future IQ3 candidate. The detailed boundary is in
`docs/architecture/F017_F018_RUNTIME_BOUNDARY.md`.

## Final verdict and next gate

The result is **GO** because numerical qualification, fail-closed behavior,
in-flight lifetime safety, strict compiler semantics, and the bounded material
performance gate all pass. A parallel IQ2 performance kernel was therefore
not built; the sequential scaffold remains the permanent same-order Metal-side
comparator.

IQ3-down was not started. After the final repository and CI closeout, the exact
next experiment is to freeze a distinct IQ3_XXS-down single-matrix numerical
and layout contract, then qualify one real layer-3 expert-15 down projection
through synthetic, real-matrix, repeated-warm, and composed expert gates. It
must preserve the strict compiler, ownership, telemetry, and validation
semantics established here.

## Evidence and reproduction

- Three-way decision: `raw/f018-post-opus-qualification-0001.json` and
  `tables/f018-post-opus-qualification-0001.md`
- Strict real matrix: `raw/f018-iq2-xxs-gate-matrix-strict-0001.json` and
  `tables/f018-iq2-xxs-gate-matrix-strict-0001.md`
- Strict synthetic: `raw/f018-iq2-xxs-synthetic-strict-0001.json`
- Dispatch inventory: `raw/f018-p1-reference-dispatch-inventory-0001.json`
- Lookup experiment: `raw/f018-iq2-lookup-address-space-0001.json` and
  `tables/f018-iq2-lookup-address-space-0001.md`
- Contract: `specs/018-direct-quantized-metal-runtime/numerical-qualification-contract.md`

```sh
uv run --frozen python scripts/research/analyze_f018_post_opus.py --check
uv run --frozen python scripts/research/analyze_f018_lookup_address_space.py --check
uv run --frozen python -m unittest scripts/research/tests/test_f018_evidence.py
cargo test -p stream --test iq2_xxs_metal -- --nocapture
cargo test -p stream --doc
```

This qualification is one matrix, one checkpoint, and one M1 Ultra. It does
not establish an IQ3 kernel, full-model performance, general tokens/second,
long-context behavior, serving, or production readiness.
