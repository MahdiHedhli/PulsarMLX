# PulsarMLX F017 Canonical Runner Sprint Report

## Executive result

The sprint created a real, dedicated Rust executable and advanced the
checkpoint-free runner ladder from R0 through R5. The highest qualified
compute boundary is a Q8_0 projection executed through the production native
MLX adapter with exact f32-bit agreement, explicit synchronization, no
fallback, and fully reconciled lifecycle counters.

The runner is **not P1-ready**. A rejected R7 experiment established that a
three-projection expert built from the same MLX matvec operation does not meet
the frozen exact-f32 expert contract. The first mismatch was output element 0:
candidate `427909` (`0x48d0f0a0`) versus oracle `427908.5` (`0x48d0f090`).
The experiment exited with the numerical/behavioral failure class and was not
committed as a passing implementation. No tolerance was added or changed.

No GLM checkpoint was opened, hashed, searched for, or executed during this
sprint. No Python process is used as the runner execution engine. Feature 018
kernels are absent.

## Repository

- Starting Feature 017 boundary:
  `a4b08e192e7b7b11549fda7602cc34e153e565fe`
- Branch: `feat/017-real-checkpoint-runner`
- Isolated worktree: symbolic `<f017-runner-worktree>`
- Immutable M1 evidence worktree: unchanged
- Development host observed by the runner sprint: Apple M1 Ultra, not the
  requested ColPanicM2 host
- Feature 017 task state at report drafting: 58 complete, 12 open

Focused commits through the first CI integration commit:

| Commit | Boundary |
| --- | --- |
| `5b47fe49` | Source-backed canonical-runner gap analysis |
| `f8d9096c` | CLI, evidence, and implementation contracts |
| `698e549e` | R0 and R2-R4 runner/store vertical slice |
| `51336a42` | R1 production-adapter preflight |
| `83e4a301` | R5 typed production-MLX projection |
| `366d3dcd` | Complete 79-layer GLM-5.2 tensor map |
| `228dfff9` | Required Apple-native runner projection CI gate |

## Gap analysis

The committed gap analysis is
[`f017-real-checkpoint-runner-gap-analysis.md`](f017-real-checkpoint-runner-gap-analysis.md).
It identifies the checkpoint, architecture, backend, runtime, and executable
gaps at the reviewed source boundary. The implementation did not route around
those gaps through `pulsar-cli`, the Python research runner, or an untyped MLX
API.

## Runner binary and CLI

The workspace now contains the dedicated `f017-glm52-runner` binary in the
`f017-runner` crate. Its CLI implements:

- `--dry-run`
- `--adapter-preflight-only`
- `--checkpoint-identity-only`
- `--fixture-mode <manifest>` at the qualified R5 boundary
- the frozen real-execution option surface, which currently fails closed with
  `p1_not_admitted`

Unknown, duplicate, mixed-mode, malformed, and incomplete options fail with a
stable exit class. A fresh evidence path is mandatory. Real execution cannot
silently select another engine.

## Evidence schema

The versioned canonical-runner schema covers source, environment, checkpoint,
admission, exact token input, stage timing, storage, dispatch, residency,
lifecycle, result class, first failure, and stop reason. The writer uses
create-new plus atomic replace updates. JSON parsing rejects duplicate keys at
any depth.

The current R5 record reports:

- checkpoint accessed: false
- numerical classification: `golden_identical`
- native dispatches: 1
- fallback/error dispatches: 0
- managed arrays: 2 created / 2 destroyed
- derived arrays: 1 created / 1 destroyed
- ownership callbacks: 2
- active context after teardown: 0
- stream counters balanced
- lifecycle reconciled: true

## Tensor store and catalog

The runner checkpoint layer now provides:

- an immutable multi-shard manifest;
- per-shard filename, size, and SHA-256 validation;
- checkpoint-set and catalog SHA-256 validation;
- overflow-safe logical shard bases;
- exact bounded positional tensor reads;
- hard short-read and cancellation errors;
- duplicate and ambiguous tensor rejection;
- symbolic public evidence paths; and
- tiny split-GGUF fixtures for CI.

`--checkpoint-identity-only` hashes and parses the catalog without reading a
tensor payload. The real six-shard identity mode remains an M1 integration
gate and was not run here.

## GLM-5.2 tensor map

The tensor map validates the complete committed `glm-dsa` catalog:

- 79 layers;
- leading dense layers 0 through 2;
- 256 routed experts, top 8, and one shared expert;
- all attention/MLA and DSA/indexer tensors;
- dense and MoE FFN variants;
- embeddings, final norm, and output head; and
- four explicit layer-78 `nextn` auxiliary tensors.

All 1,809 names, dimensions, and accepted quantization families are checked.
Missing, duplicate, unexpected, incorrectly shaped, or unsupported-format
tensors fail before weight execution. The committed public catalog passes the
map test; no private tensor bytes are required.

## Production adapter operations

### Implemented and qualified

- one process-wide MLX context;
- borrowed-default or explicitly owned stream;
- managed f32 import with rank-1 or rank-2 shape validation;
- typed f32 matrix-vector multiplication;
- explicit evaluation and synchronization;
- bounded f32 result extraction;
- source/derived lifetime retention;
- singleton, ownership callback, managed/derived, and stream accounting; and
- shape, context, and result-size failure checks.

The adapter remains a narrow typed Objective-C++ boundary. It does not expose
generic native pointers as an MLX operation API.

### Still missing for GLM-5.2

- deterministic or pre-qualified multi-stage projection accumulation;
- elementwise add and multiply over distinct arrays;
- sigmoid and SiLU graph operations;
- RMSNorm reductions and scaling;
- reshape/transpose and per-head MLA views;
- attention softmax and stateful KV/latent operations;
- output-head execution and bounded logits transfer at production shape; and
- operation-level cancellation across a composed graph.

## CPU/GPU semantic boundary

The qualified R5 path uses Rust CPU code for immutable fixture validation,
hashing, and exact Q8_0 decode. The decoded f32 matrix and activation are then
imported into MLX; matrix-vector compute and synchronization run on the Apple
GPU. Result bytes return to Rust for exact comparison.

Future small router top-k, deterministic aggregation, and final argmax may be
implemented as explicit Rust CPU operations, as permitted by the architecture
contract. They are not yet runner capabilities and cannot be used as hidden
fallback. Full-size projections and expert matvecs remain required production
MLX operations for the first P1.

## Fixture ladder

| Gate | Status | Evidence |
| --- | --- | --- |
| R0 runner/CLI/evidence | Passed | Actual binary and strict schema tests |
| R1 adapter preflight | Passed | Production adapter, zero baseline, reconciled teardown |
| R2 fake multi-shard manifest | Passed | Two-shard fixture and identity failures |
| R3 GGUF catalog | Passed | Merged catalog and duplicate-name rejection |
| R4 exact tensor read/hash | Passed | Exact positional read and short-read failure |
| R5 projection | Passed | Independent Q8_0 oracle, exact f32 bits, native MLX |
| R6 router | Not composed | Explicit Rust CPU boundary still required |
| R7 complete expert | Blocked | MLX accumulation differs from frozen exact-f32 contract |
| R8 top-8 plus shared | Not eligible | Depends on R6 and R7 |
| R9 MLA/dense | Not eligible | Required native operations/state are missing |
| R10 complete layer | Not eligible | Depends on R6-R9 |
| R11 final logits | Not eligible | RMSNorm/output-head path missing |
| R12 tiny end to end | Not eligible | Complete component composition absent |
| R13 local real fixtures | Not started | No local fixture/model access in this sprint |
| R14 M1 identity only | Not started | Requires reviewed runner composition handoff |
| R15 one P1 | Not authorized | Requires R0-R14 and fresh authorization |

The R7 rejection is retained as a development observation, not promoted to a
passing public artifact. The exact contract remains unchanged.

## Tiny end-to-end runner

R12 is not complete. The actual binary does execute its complete current R5
path, including CLI, evidence, independent fixture parsing, decode, production
adapter, synchronization, numerical comparison, and teardown. It does not yet
execute a synthetic multi-layer model, router, expert aggregation, attention
state, or final logits, so describing it as end-to-end inference would be
incorrect.

## Local-only real fixture plan

The next local-fixture manifest must bind, without committing weight bytes:

- checkpoint-set SHA-256 and immutable revision;
- exact tensor name, shard, offset, length, dimensions, and quantization;
- input/output activation hashes;
- source and independent-oracle commit; and
- embedding, early MLA, layer-3 MoE, middle layer, final layer, final norm,
  output-head, and top-k boundaries.

This mechanism remains unimplemented until the checkpoint-free R6-R12 ladder
is green. No model copy or checkpoint download is needed on the development
host.

## Canonical P1 command

A literal P1 command is intentionally not published. The CLI surface is
frozen, but R6-R14 and the two required implementation reviews are incomplete.
Printing a plausible command now would repeat the infrastructure error that
motivated this sprint.

## CI and validation

Local validation completed during the sprint includes:

- all 11 production native MLX bridge tests, including 1,000-cycle stream
  matrices;
- the production-adapter preflight integration test;
- the actual-binary R5 projection test with native MLX required;
- all `f017-runner` unit and integration tests;
- public catalog tensor-map validation;
- fake multi-shard store and exact-read tests;
- duplicate JSON-key and CLI failure tests; and
- `git diff --check` before each focused commit.

The existing inherited `quant::iq` `unused_mut` warning remains unchanged.
The native context-cycle suite also retains the already documented MLX
CoreAnalytics diagnostic while all counters and tests pass.

The Apple workflow now explicitly executes the canonical runner projection
with `PULSAR_REQUIRE_NATIVE_MLX=1`; a skipped native test cannot satisfy that
job. The final workflow run and final report commit status must be recorded
after GitHub reaches a terminal state.

## Review status

- Source-backed internal composition audit: complete through R5.
- Independent adversarial runner review: not requested yet because R6-R12 are
  incomplete.
- Previous adapter review: remains valid for ownership plumbing, but is not a
  runner or P1 review.

No M1 model-time request is justified by this report.

## Exact blocker and next gate

The immediate decision is between two correctness-preserving routes:

1. add a deterministic same-order MLX/Metal-side qualification matvec for the
   exact expert contract; or
2. freeze, independently review, and commit a Tier-B numerical contract for
   MLX tiled matmul before observing further expert outputs.

The current exact contract cannot be weakened after the observed mismatch.
Until that decision is reviewed, R7 is blocked and R8-R15 remain ineligible.
After the numerical boundary is frozen, the next command should rerun only the
checkpoint-free complete-expert fixture—not a real checkpoint, P1, P2, or
golden-eight run.
