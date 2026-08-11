# Feature 017 R7 production mismatch attribution

## Result

The original R7 difference begins at the production MLX down-projection
matmul. The independent oracle and `f017-exact-f32-sequential-v1` scaffold are
bit-identical at gate, up, activated-hidden, down, and final boundaries. The
production MLX path is bit-identical through gate, up, and SwiGLU; 24 of the
32 down-projection outputs then differ.

This is a boundary attribution, not a claim about MLX's undocumented internal
reduction tree. Sequential FMA, two pairwise trees, and four- and eight-chunk
sequential reductions were tested as diagnostics; none reproduced the MLX
output exactly. The supported conclusion is therefore that the difference is
introduced by the production MLX down-matmul arithmetic or reduction
semantics. Q8_0 decode, input materialization, gate, up, and activation are
excluded for this fixture.

## Frozen original difference

| Field | Oracle / scaffold | Production MLX |
| --- | ---: | ---: |
| First output | `427908.5` | `427909.0` |
| f32 bits | `0x48d0f090` | `0x48d0f0a0` |
| Absolute difference | — | `0.5` |

Across the complete 32-element down output, the maximum absolute error was
`1.375`, maximum relative error over nonzero oracle values was
`3.911221529240683e-6`, RMSE was `0.693598660294626`, and cosine similarity
was `0.9999999999999881`. These observations do not define or tune a pass
threshold.

## Determinism and lifecycle

Ten identical production executions returned the same f32 bits. The run used
the production MLX C adapter with an owned GPU stream. All 60 managed owners,
30 derived arrays, 60 callbacks, and the owned stream reconciled; no context
remained active. No checkpoint was accessed and no fallback was available.

The first attempted native invocation failed before fixture execution because
the dynamic loader path was absent. It was retained as an infrastructure
launch failure and was not treated as numerical evidence. The qualifying run
used the already pinned MLX native 0.31.2 / MLX C 0.6.0 environment.

## Reproduction

```sh
PULSAR_REQUIRE_NATIVE_MLX=1 \
MLX_C_PREFIX="$MLX_C_PREFIX" \
MLX_PREFIX="$MLX_PREFIX" \
DYLD_LIBRARY_PATH="$MLX_C_PREFIX/lib" \
cargo test -p f017-runner --test r7_production_attribution -- --exact --nocapture
```

The clean-source run is bound to
`e140a5acbb83f4575ac400ca0eef8a319c7f9d8c`. Machine-readable results are in
`specs/017-rust-native-inference-runtime/fixtures/f017-r7-production-attribution-v1.json`.
Tier B remained undefined while this attribution was collected; R8 therefore
remains blocked.
