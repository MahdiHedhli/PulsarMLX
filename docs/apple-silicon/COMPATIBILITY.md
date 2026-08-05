# Apple Silicon compatibility matrix

This matrix records only executed PulsarMLX evidence. “Verified” is scoped to
the exact fixture, tensor role, and operation named here; it is not a model-wide
support claim. Evidence records carry their own clean immutable source commit
and are linked below.

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

The committed `routed-moe-v1` fixture passed exact split-shard identities,
deterministic top-2 routing, deduplicated expert selection, evaluated and
synchronized MLX expert work, weighted aggregation, and an independent scalar
comparison. Its routes were `[[1, 2], [3, 1]]`; its four-value output had a
maximum absolute error of `4.759696965450644e-07` under the frozen `1e-5`
tolerance. This is synthetic fixture evidence, not a real GGUF model-loader,
tokenizer, logits, generation, serving, or performance result.

## Platform boundary

- macOS arm64 and MLX 0.32.0: the cases above passed locally.
- Linux/CUDA after shared Q8_0 additions: pending, not run on this Apple host.
- The external Qwen3-30B-A3B Q8_0 artifact's complete size and SHA-256 match
  immutable published values, and the exact required Q8_0 expert tensor role
  passes read-only inventory. The pinned CPU oracle and Apple MLX executed the
  same bounded layer-0 expert-0 gate-projection prefix with zero mismatches
  under the predeclared tolerance. This is bounded real-checkpoint evidence,
  not full-model or giant-model inference.
- No correctness-gated benchmark has been run.

## Post-slice workspace baseline

From clean pushed commit `31ee7e55daadb5d1d7b3d0e278b8ccac114836d9`,
`cargo check --workspace --all-targets` and
`cargo test --workspace --no-fail-fast` both exited zero on arm64 macOS. The
test workspace listed 155 tests: 154 active tests passed, one native MLX smoke
test remained explicitly ignored in the general baseline, and zero failed.
The check/test output retained the inherited `quant` `unused_mut` warning and
13 macOS `serve` dead-code warnings. These gates cover only macOS-selected
targets and do not establish Linux/CUDA compilation or runtime behavior.

## Unsupported claim levels

No committed evidence establishes Qwen tokenization, embeddings, routing over
the checkpoint, a complete expert, attention, a complete transformer layer,
logits, token generation, production serving, full-checkpoint residency or
streaming, giant-model inference, or performance. Synthetic, bounded
real-checkpoint, giant-model, and production-serving claims remain independent.
