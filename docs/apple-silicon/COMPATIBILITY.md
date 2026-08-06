# Apple Silicon compatibility matrix

This matrix records only executed PulsarMLX evidence. “Verified” is scoped to
the exact fixture, tensor role, and operation named here; it is not a model-wide
support claim. Evidence records carry their own clean immutable source commit
and are linked below.

## Architecture, quantization, and evidence depth

Each cell is independent. **Verified** means that the exact cell has a linked,
executed, passing record. **Unsupported** means that the cell is outside the
implemented or evidenced scope described in its explanation. No row or column
has promotion semantics: scalar evidence does not imply MLX execution,
synthetic evidence does not imply checkpoint execution, and a bounded
checkpoint slice does not imply giant-model execution or production serving.

| Architecture and exact scope | Quantization | Deterministic scalar fixture | Evaluated MLX tensor fixture | Synthetic routed-MoE fixture | Bounded real-checkpoint slice | Giant-model execution | Production serving |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Architecture-independent dense primitive fixtures | f32 | **Verified** — independent expected values in [`mlx-tensor-fixtures.json`](../validation/mlx-tensor-fixtures.json) | **Verified** — six evaluated, synchronized dense/routing GPU cases in [`mlx-tensor-fixtures.json`](../validation/mlx-tensor-fixtures.json) | **Unsupported** — isolated primitive cases do not execute the routed expert graph | **Unsupported** — primitive cases do not open a checkpoint | **Unsupported** — no model execution occurs | **Unsupported** — no serving path is involved |
| Architecture-independent strict Q8_0 primitive | GGUF Q8_0, complete 32-element/34-byte blocks | **Verified** — malformed-input, decode, and scalar matvec cases recorded in [`mlx-tensor-fixtures.json`](../validation/mlx-tensor-fixtures.json) | **Verified** — one evaluated, synchronized two-block decode/dot case in [`mlx-tensor-fixtures.json`](../validation/mlx-tensor-fixtures.json) | **Unsupported** — no synthetic routed graph uses Q8_0 expert weights | **Unsupported** — the primitive record does not open a checkpoint | **Unsupported** — no model execution occurs | **Unsupported** — no serving path is involved |
| Architecture-independent `synthetic-routed-moe-v1` | f32 dense expert weights | **Verified** — independent scalar routes, weights, and aggregate in [`synthetic-moe-v1.json`](../validation/synthetic-moe-v1.json) | **Verified** — evaluated and synchronized MLX expert graph in [`synthetic-moe-v1.json`](../validation/synthetic-moe-v1.json) | **Verified** — exact split-shard payloads, top-2 routes, normalized weights, and aggregate in [`synthetic-moe-v1.json`](../validation/synthetic-moe-v1.json) | **Unsupported** — the fixture contains generated synthetic weights, not a checkpoint | **Unsupported** — no checkpoint is loaded or executed | **Unsupported** — tokenizer, generation, and server paths are excluded |
| Generated Feature 002 complete-router fixtures, `generated-qwen3moe-router-{single-row,two-row}-v1` | f32 generated expert-major `[128,2048]` weights | **Verified** — the committed [`router-v1` manifest](../../fixtures/research/router-v1/manifest.json) and expected results retain all 128 logits and full-softmax probabilities, ordered top-8 IDs, selected probabilities, normalized weights, and canonical f32le hashes | **Verified** — the [worker router contract](../../python/pulsar_mlx_worker/tests/test_router.py) executed the one-row and two-row complete f32 projection, full 128-way softmax, deterministic top-8, and selected-probability renormalization on explicit MLX GPU with evaluation, synchronization, and no fallback | **Unsupported** — the operation stops at router outputs and executes no expert | **Unsupported** — no external checkpoint or real hidden-state fixture was accessed | **Unsupported** — generated router dimensions do not establish checkpoint or giant-model execution | **Unsupported** — no serving path is involved |
| `qwen3moe`, exact `blk.0.ffn_gate_exps.weight` expert-0 gate-projection rows 0–15 | GGUF Q8_0; identity and exact tensor inventory in [`qwen3-30b-a3b-q8_0-compatibility.json`](../validation/models/qwen3-30b-a3b-q8_0-compatibility.json) | **Unsupported** — generic Q8_0 scalar fixtures are prerequisites, while the pinned CPU checkpoint oracle belongs to the bounded real-slice cell rather than a separate architecture-level scalar fixture | **Unsupported** — generic two-block Q8_0 MLX parity is a prerequisite, not an executed Qwen graph at this evidence level | **Unsupported** — the routed fixture uses synthetic f32 weights and does not execute Qwen routing or Q8_0 experts | **Verified** — the trusted reference and evaluated Apple result match for the exact 34,816-byte prefix in [`qwen3-30b-a3b-q8_0-reference-result.json`](../validation/models/qwen3-30b-a3b-q8_0-reference-result.json) and [`qwen3-30b-a3b-q8_0-slice.json`](../validation/qwen3-30b-a3b-q8_0-slice.json) | **Unsupported** — no complete tensor, expert, layer, or model was executed | **Unsupported** — no logits, tokens, generation, HTTP, or MCP serving was executed |

The official Qwen artifact is a large checkpoint, but its size does not promote
the bounded prefix result into giant-model execution evidence. Likewise, the
f32 synthetic route demonstrates routing semantics only for its committed
fixture; it is not Qwen3MoE routing or Q8_0 routed-expert evidence.

## Dense and routing operations

| Operation | Input / accumulation / output | Apple MLX evidence | Boundary |
| --- | --- | --- | --- |
| Elementwise fused multiply-add | f32 / f32 / f32 | Verified, evaluated and synchronized | One bounded `[2,3]` fixture |
| Matrix multiplication | f32 / f32 / f32 | Verified, evaluated and synchronized | One orientation-visible `[2,3] @ [3,2]` fixture |
| Embedding gather | f32 table / f32 / f32 | Verified, evaluated and synchronized | Bounded valid IDs; invalid IDs rejected before scheduling |
| RMS normalization | f32 / f32 / f32 | Verified, evaluated and synchronized | One weighted `[2,4]` fixture, epsilon `1e-5` |
| Residual addition | f32 / f32 / f32 | Verified, evaluated and synchronized | Exact-shape bounded fixture |
| Router top-k plus selected-score softmax | f32 / f32 / f32 | Verified, evaluated and synchronized | Two tokens, four experts, top-2; tie order `[1,2,3,0]` |

All seven fixture cases use explicit `apple-mlx` / `gpu`, forbid fallback,
call `mx.eval`, synchronize the GPU, perform bounded readback, and compare with
precommitted independent values. Exact actual values and error metrics are in
[`../validation/mlx-tensor-fixtures.json`](../validation/mlx-tensor-fixtures.json).

## Q8_0 by tensor role and evidence level

| Q8_0 role | Scalar Rust evidence | Evaluated MLX evidence | Status |
| --- | --- | --- | --- |
| Complete-row decode, 32 elements / 34 bytes per block | Verified across zero, positive, negative, extrema, and two-scale blocks | Verified for one two-block row | Fixture-only verified |
| Row-major matrix by f32 vector | Verified for complete rows with checked dimensions and f32 logical-order accumulation | One decoded-row by f32-vector dot verified | Scalar matvec verified; MLX one-row fixture verified |
| Qwen3-MoE layer-0 expert-0 gate projection, output rows 0–15 | Verified by the pinned llama.cpp `gguf-py`/NumPy reference | Verified by an evaluated and synchronized MLX GPU matvec over the same admitted 34,816 encoded bytes | One bounded real-checkpoint intermediate verified |
| Dense attention projection weights | Not run | Not run | Unsupported / unverified |
| Embedding weights | Not run | Not run | Unsupported / unverified |
| Complete routed expert gate/up/down tensors | Not run | Not run | Unsupported / unverified |
| Output / language-model head | Not run | Not run | Unsupported / unverified |
| Full GGUF model execution | Not run | Not run | Unsupported / unverified |

The MLX Q8_0 fixture validates encoded bytes on the host, creates bounded
scale/quant arrays, evaluates their dequantization expression and dot on MLX,
and checks the decoded row and output. It is not a custom compressed MLX or
Metal kernel and does not establish zero-copy GGUF execution.

The bounded real-checkpoint evidence is in
[`../validation/models/qwen3-30b-a3b-q8_0-reference-result.json`](../validation/models/qwen3-30b-a3b-q8_0-reference-result.json)
and
[`../validation/qwen3-30b-a3b-q8_0-slice.json`](../validation/qwen3-30b-a3b-q8_0-slice.json).
It covers one named tensor, one expert, one projection, 16 output rows, and one
deterministic 2,048-element activation. It does not imply that the complete
tensor, another expert or projection, routing, a transformer layer, or the
checkpoint as a whole is executable.

## Synthetic routed-MoE boundary

The committed [`routed-moe-v1` evidence](../validation/synthetic-moe-v1.json)
passed exact split-shard identities, deterministic top-2 routing, deduplicated
expert selection, evaluated and synchronized MLX expert work, weighted
aggregation, and an independent scalar comparison. Its routes were
`[[1, 2], [3, 1]]`; its four-value output had a maximum absolute error of
`4.759696965450644e-07` under the frozen `1e-5` tolerance. This is synthetic
fixture evidence, not a real GGUF model-loader, tokenizer, logits, generation,
serving, or performance result.

## Feature 002 offline complete-router seam

The Feature 002 worker now accepts a control-only request for one of two
committed generated cases. The request contains only the case ID, explicit
`gpu` device, and `allow_fallback: false`; it contains no path, checkpoint
bytes, tensor values, hidden-state values, oracle values, or caller-selected
measurement counts. The worker reconstructs only the committed generated
fixture, evaluates the complete f32 projection and router operation, retains
all 128 logits and full-softmax probabilities per row, returns ordered top-8
IDs plus selected and normalized probabilities, and supplies canonical f32le
hashes and bounded memory gauges.

For this raw worker result, `passed: true` has a deliberately narrow meaning:
the requested and selected device are both `gpu`, fallback was not used, and
the returned arrays were explicitly evaluated and synchronized. It does not
mean that a real checkpoint was admitted, that a genuine Qwen hidden state was
used, or that an independent real-model oracle comparison passed. The current
independent expected values are generated-fixture values only.

The following model-free commands were executed from the repository root for
the current offline slice:

| Command | Actual result |
| --- | --- |
| `cargo test -p backend --test routing_contract` | 8 passed, 0 failed |
| `cargo test -p mlx-backend --test router_contract` | 6 passed, 0 failed |
| `cargo test -p mlx-backend --lib` | 9 passed, 0 failed |
| `cargo test -p mlx-backend --bin pulsar-mlx` | 9 passed, 0 failed |
| `PULSARMLX_MODEL_GGUF='' PYTHONPATH=python uv run python -m unittest python/pulsar_mlx_worker/tests/test_router.py -v` | 9 passed, 0 failed |
| `PULSARMLX_MODEL_GGUF='' cargo test -p mlx-backend --test router_worker_integration real_python_worker_two_row_router_matches_committed_golden -- --ignored --exact` | 1 passed, 0 failed |
| `PULSARMLX_MODEL_GGUF='' python3 -m unittest scripts/research/tests/test_router_oracle.py -v` | 12 passed, 0 failed |
| `PULSARMLX_MODEL_GGUF='' python3 -m unittest discover -s scripts/research/tests -v` | 53 passed, 0 failed |
| `python3 fixtures/research/router-v1/golden/generate.py --check` | 4 generated files were byte-identical |
| `PULSARMLX_MODEL_GGUF='' python3 scripts/research/validate_evidence.py --schema-dir schemas/research/v1 --input fixtures/research/router-v1/evidence` | passed |
| `PULSARMLX_MODEL_GGUF='' python3 scripts/research/verify_package.py --feature 002-qwen-router-parity --fixture-only` | passed |

Every command in the table above kept the external-model variable empty or
operated only on committed generated data. Separately, gated Feature 002 work
admitted the immutable external checkpoint, committed the bounded real input
and independent CPU oracle, and produced two unadmitted Apple router
candidates. Neither candidate passed independent sanitization/publication, so
there is still no verified Apple checkpoint-parity result.

## Platform boundary

- macOS arm64 and MLX 0.32.0: the cases above passed locally.
- Feature 002 complete-router execution is verified only for its two generated
  f32 cases. Real `blk.0.ffn_gate_inp.weight` admission, genuine `ffn_norm-0`
  inputs, and the independent CPU oracle are bounded and committed. Apple
  checkpoint parity, repeatability evidence, and router timing remain
  unverified.
- Linux/CUDA after shared Q8_0 additions: pending, not run on this Apple host.
- The external Qwen3-30B-A3B Q8_0 artifact's complete size and SHA-256 match
  immutable published values, and the exact required Q8_0 expert tensor role
  passes read-only inventory. The pinned CPU oracle and Apple MLX executed the
  same bounded layer-0 expert-0 gate-projection prefix with zero mismatches
  under the predeclared tolerance. This is bounded real-checkpoint evidence,
  not full-model or giant-model inference.
- No correctness-gated benchmark has been run.

## Post-slice workspace baseline

The historical first post-slice gate at clean pushed commit
`31ee7e55daadb5d1d7b3d0e278b8ccac114836d9`,
`cargo check --workspace --all-targets` and
`cargo test --workspace --no-fail-fast` both exited zero on arm64 macOS. The
test workspace listed 155 tests: 154 active tests passed, one native MLX smoke
test remained explicitly ignored in the general baseline, and zero failed.
The check/test output retained the inherited `quant` `unused_mut` warning and
13 macOS `serve` dead-code warnings. These gates cover only macOS-selected
targets and do not establish Linux/CUDA compilation or runtime behavior.

The later T076 and T077 local gates passed the same exact commands with 171
active tests, zero failures, and one ignored native smoke; the smoke passed
when explicitly selected. Push-triggered arm64 CI run
[`31026431975`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31026431975)
at commit `5a43cf0` repeated 171 passed, zero failed, and one ignored in the
Cargo job, while the separate frozen-environment fixture job passed 44 Python
worker tests, one native device smoke, seven tensor cases, and the synthetic
routed-MoE case. No CI job accessed the external checkpoint, and no result
establishes Linux/CUDA runtime parity, full or giant model inference, serving,
or performance.

## Unsupported claim levels

No committed evidence establishes Qwen tokenization, embeddings, routing over
the checkpoint, a complete expert, attention, a complete transformer layer,
logits, token generation, production serving, full-checkpoint residency or
streaming, giant-model inference, or performance. Synthetic, bounded
real-checkpoint, giant-model, and production-serving claims remain independent.
