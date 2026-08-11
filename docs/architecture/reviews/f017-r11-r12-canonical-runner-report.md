# PulsarMLX F017 R11/R12 Canonical Runner Report

## Executive result

Checkpoint-free R11 and R12 pass. R11 qualifies final RMSNorm, a representative
Q4_K output head, full logits, stable top-k ordering, and argmax. R12 executes a
two-layer synthetic `glm-dsa` model through the actual `f017-glm52-runner`
binary, split checkpoint store, validated tensor map, production `MlxContext`,
layer loop, evidence writer, and lifecycle accounting.

This result does **not** access or qualify the real GLM-5.2 checkpoint. It does
not admit M1-C, P1, Feature 018 kernels, or output-head residency. The next gate
is independent adversarial review of the canonical runner, followed by staged
M1-A/M1-B revalidation if the review accepts the composition.

## Repository boundary

- Starting runner head: `43339bfb11270ca15862443de6f5f9349d17f259`
- R11 production source: `3e10cecf67c2bff9634edaac4e621f09ca764f46`
- R12 exact source: `4c2728c21ececee687fe88192f45188ca0168cd2`
- R12 production source: `8263200c3d4ad77a12e5556ea8484048a6a18197`
- Development branch: `feat/017-real-checkpoint-runner`
- External checkpoint accessed: no
- Feature 018 kernel integration: absent
- Native-ready output-head residency: absent

## R11 independent oracle

The independent generator is
[`scripts/research/generate_f017_r11_oracle.py`](../../../scripts/research/generate_f017_r11_oracle.py).
Its SHA-256 is
`970fdcf76d166a0a32bd2006fcdf25f225df059a08eec2991938109cf5524275`.
The frozen fixture is
[`f017-r11-final-output-oracle-v1.json`](../../../specs/017-rust-native-inference-runtime/fixtures/f017-r11-final-output-oracle-v1.json).

The fixture uses a 256-wide hidden state, 16-row Q4_K output head, and eight-way
top-k. It retains canonical IEEE-754 bytes for final hidden state, norm scale,
normalized state, decoded output head, logits, and top-k scores. It was produced
without Rust candidate code, MLX, or external checkpoint access.

The R11 contract was frozen before production execution in
[`production-r11-tier-b-v1.json`](../../../specs/017-rust-native-inference-runtime/contracts/production-r11-tier-b-v1.json).
Greedy applicability is `applicable`; a changed top-k order or argmax is a hard
`numerically_failed` result even if logit-error bounds pass.

## R11 results

The exact qualification scaffold is golden-identical, including logits,
top-k IDs, and argmax. The production adapter ran ten deterministic repeats and
classified `numerically_qualified_greedy_identical`:

| Measure | Result |
| --- | ---: |
| Logit bit mismatches | 14 of 16 |
| Maximum absolute error | 0.00000762939453125 |
| RMSE | 0.0000033122167562126646 |
| Cosine similarity | 0.9999999999999626 |
| Top-k IDs | `[7, 4, 12, 13, 9, 8, 1, 3]` |
| Argmax | `7` |
| Top-1 / top-2 margin | 3.2963104248046875 |
| Native dispatches | 10 |
| Unexpected fallbacks / backend errors | 0 / 0 |
| First-use wall | 0.013575667 s |
| Warm median | 0.000455208 s |
| Warm range | 0.000425167–0.000612625 s |

Ownership reconciled at 20 managed creates/destroys, 10 derived
creates/destroys, 20 callbacks, and one owned stream create/free. No context,
in-flight work, or stale generation remained. The machine-readable result is
[`f017-r11-final-output-production-v1.json`](evidence/f017-r11-final-output-production-v1.json).

Independent top-k stress covers exact ties, one-ULP near ties, positive and
negative ties, large and near-zero logits, repeated values, and margins below
typical numerical error. The stable rule is descending IEEE total order with
the lower index first on exact equality.

## R12 model and execution path

The independent generator is
[`scripts/research/generate_f017_r12_tiny_model.py`](../../../scripts/research/generate_f017_r12_tiny_model.py),
SHA-256
`1ef0c1aed0c286461a3ca65eceee54c6d8bed30be12eba4769701066924f4176`.
The public-safe fixture directory is
[`f017-r12-tiny-model`](../../../specs/017-rust-native-inference-runtime/fixtures/f017-r12-tiny-model/).

The fixture contains two synthetic GGUF-v3 shards and 105 tensor contracts. It
uses two layers, width 256, vocabulary 16, 12 routed experts per layer, exact
top-8 routing, and one shared expert. It exercises embedding, MLA/DSA state,
router, routed experts, shared expert, residual composition, final RMSNorm,
Q4_K output head, logits, stable top-k, and token selection.

Fixture mode selects synthetic model data and a fixture-specific composition.
Both modes use the canonical CLI, evidence writer, `RunnerTensorStore`,
production `MlxContext` adapter, semantic components, dispatch policy, and
lifecycle code. R12 uses `TinyRuntime` and `Glm52FixtureTensorMap`; the future
real checkpoint path will use the production map/runtime composition, so this
report does not claim a shared production runtime abstraction. Production
mode uses the production MLX adapter for all large matrix-vector operations;
small deterministic norm, activation, routing, aggregation, and selection
operations remain explicit Rust CPU semantics. No Python process is part of
runner execution.

## R12 exact and production results

The exact scaffold ran ten deterministic repeats and selected token `10` with
exact routing, logits, top-k, and argmax. It recorded 690 explicit qualification
dispatches, zero fallback/errors, and reconciled zero-state lifecycle evidence.

The production adapter also ran ten deterministic repeats and selected token
`10`. Its final-logit classification is
`numerically_qualified_greedy_identical`:

| Measure | Exact scaffold | Production MLX |
| --- | ---: | ---: |
| Complete fixture wall | 1.116313333 s | 0.831120958 s |
| Repeated execution wall | 0.523472708 s | 0.225207250 s |
| Storage/decode/materialization setup | 0.276347792 s | 0.265569833 s |
| Layer 0 mean | 0.0232786792 s | 0.0118180627 s |
| Layer 1 mean | 0.0233389790 s | 0.0103502125 s |
| Backend import | not applicable | 0.013920283 s |
| Compute/sync/readback | not applicable | 0.195533543 s |
| Output-head Q4_K decode | 0.000647999 s | 0.000648290 s |
| Orchestration | not separately attributed | 0.015105134 s |
| Native / scaffold dispatches | 0 / 690 | 690 / 0 |
| Fallback / errors | 0 / 0 | 0 / 0 |

Final-logit production metrics were 15 bit mismatches, maximum absolute error
0.000018596649169921875, RMSE 0.000009562227353043248, and cosine similarity
0.9999999999997703. Top-k and argmax were exact. The 81 decoded tensors were
bounded fixture-resident entries with 81 first-use misses and zero evictions;
this is not an output-head-residency result.

Production lifecycle reconciled at 1,380 managed creates/destroys, 690 derived
creates/destroys, 1,380 callbacks, and one owned stream create/free. Context
state was measured at zero after teardown. Registration, generation,
in-flight, and owner-token domains are explicitly `not_applicable` for this
fixture rather than being reported as measured zero.

Evidence:

- [`f017-r12-tiny-model-exact-v2.json`](evidence/f017-r12-tiny-model-exact-v2.json)
- [`f017-r12-tiny-model-production-v2.json`](evidence/f017-r12-tiny-model-production-v2.json)

The v2 production record does not run the qualification scaffold. It compares
the candidate against the already-frozen independent outputs and records 690
native, zero scaffold, zero explicit-reference, zero fallback, and zero error
dispatches. Both v2 records bind the complete inherited contract set: expert
v1, R9 v2, R10 v2, and R11 v1, including exact contract hashes.

## Failure and cancellation coverage

The actual binary fails closed for duplicate-key/malformed manifests, missing
tensor contracts, wrong shapes, unsupported quantization, truncated shards,
pre-layer cancellation, between-layer cancellation, and injected adapter
failure. Failure evidence cannot be classified PASS. The production adapter
error path synchronizes and tears down the context before returning; its owned
stream and singleton accounting reconcile. Existing evidence-writer tests cover
fresh-output enforcement and atomic-write failures.

## Evidence schema

The canonical schema version 1.3.0 records source and environment identity, synthetic
checkpoint identity, input token, expected token, numerical mode, layer
progress, stage timings, greedy applicability, exact top-k/argmax identity,
dispatch/fallback/error counts, bounded residency, lifecycle, result class, and
first failure. Parsing rejects duplicate keys, public evidence uses symbolic or
repository-relative identities, and earlier frozen contracts remain immutable.

## Validation and CI

Local validation completed on the M1 Ultra:

- 373 Python research/oracle/evidence tests;
- deterministic R11 and R12 oracle regeneration;
- all F017 runner tests with pinned native MLX required;
- all 11 native MLX ownership/stream tests and the Metal registration test;
- `cargo check --workspace --all-targets`;
- `cargo test --workspace --no-fail-fast`;
- Spec Kit prerequisite and integration checks;
- duplicate-key, privacy/path, generated-artifact, link, and `git diff --check`
  gates.

GitHub Actions run
[`31539889918`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31539889918)
passed on implementation/evidence head
`fef0f87fa55b8bd18ff9bd16e17c9e4639d0bffb`. The Apple Silicon workspace job
passed in 1m33s. The Apple-native MLX job passed in 8m44s with native execution
required; no skipped native test satisfied the R11/R12 gate.

## Limitations and review status

- R11/R12 are synthetic, checkpoint-free evidence.
- The output-head fixture is representative Q4_K, not the full 8+ GiB real
  output matrix.
- Production currently materializes decoded f32 matrices before MLX matvec.
- Production matvec is qualified under frozen Tier B, not bit-identical.
- CPU/GPU composition and 69 native dispatches per tiny-model repeat may expose
  integration issues at real shape.
- Real tensor ranges, unsupported real quantizations, memory admission, and
  full-model lifecycle remain untested.
- No canonical P1 command is published.

Adversarial review question:

> Is the canonical runner now real enough to begin staged M1 checkpoint
> integration at M1-A/B/C without hiding behind synthetic/reference paths?

Until that review answers yes, real checkpoint access and P1 remain blocked.

## Next gate

Obtain the internal implementation review and independent adversarial
canonical-runner review. If accepted, re-run M1-A adapter preflight and M1-B
checkpoint identity, then request a separately bounded M1-C real tensor-read
gate. Do not jump to P1.
