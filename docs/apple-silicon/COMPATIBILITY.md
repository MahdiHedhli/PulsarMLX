# Apple Silicon compatibility matrix

This matrix records only executed PulsarMLX evidence. “Verified” is scoped to
the exact fixture, tensor role, and operation named here; it is not a model-wide
support claim. The current evidence commit is
`c53f21e7c98bfa2288690a3662c6f6e10857a685`.

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
| Dense attention projection weights | Not run | Not run | Unsupported / unverified |
| Embedding weights | Not run | Not run | Unsupported / unverified |
| Routed expert gate/up/down weights | Not run | Not run | Unsupported / unverified |
| Output / language-model head | Not run | Not run | Unsupported / unverified |
| Full GGUF tensor ingestion | Not run | Not run | Unsupported / unverified |

The MLX Q8_0 fixture validates encoded bytes on the host, creates bounded
scale/quant arrays, evaluates their dequantization expression and dot on MLX,
and checks the decoded row and output. It is not a custom compressed MLX or
Metal kernel and does not establish zero-copy GGUF execution.

## Platform boundary

- macOS arm64 and MLX 0.32.0: the cases above passed locally.
- Linux/CUDA after shared Q8_0 additions: pending, not run on this Apple host.
- No model architecture or checkpoint is marked compatible yet.
- No correctness-gated benchmark has been run.
