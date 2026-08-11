# Feature 017 R7 exact qualification scaffold

## Result

The permanent qualification scaffold `f017-exact-f32-sequential-v1` reproduces
the frozen independent complete-expert fixture exactly. Gate, up,
activated-hidden, down, and final-output f32 hashes match across 10 identical
executions. The classification is `golden_identical`.

This proof was run from clean source
`57736aaaabba494ab8d1ac7ed7d536bec3ec658f`. It used no checkpoint, MLX
operation, Python process, hidden fallback, or Feature 018 kernel.

## Arithmetic contract

The scaffold:

- iterates rows in increasing order;
- accumulates columns strictly from `0` through `columns - 1`;
- performs multiplication and addition as separate rounded f32 operations;
- does not use fused multiply-add, reassociation, vectorized/tiled reduction,
  parallel reduction, or fast math;
- writes into caller-owned buffers and performs no internal allocation; and
- keeps SiLU and the gate/up multiplication at explicit f32 rounding
  boundaries matching the independent oracle.

The implementation is deliberately named and isolated as qualification-only.
It cannot be silently selected as the production MLX path.

## Exact boundary results

| Boundary | Expected SHA-256 | Actual SHA-256 | Bit mismatches |
| --- | --- | --- | ---: |
| Gate | `188a782b…345f6` | `188a782b…345f6` | 0 |
| Up | `65d93ab6…31fba8` | `65d93ab6…31fba8` | 0 |
| Activated hidden | `dd111ed9…7e7d0` | `dd111ed9…7e7d0` | 0 |
| Down/final output | `7f0358e4…9d5f6` | `7f0358e4…9d5f6` | 0 |

The first final output is exactly `427908.5` (`0x48d0f090`). This proves the
frozen fixture and its complete-expert semantic composition are internally
consistent. It does not yet attribute or qualify the production MLX result.

## Reproduction

```sh
cargo test -p f017-runner --test r7_exact_scaffold -- --exact --nocapture
```

The machine-readable result is
`specs/017-rust-native-inference-runtime/fixtures/f017-r7-exact-scaffold-v1.json`.
R8 remains blocked until the production mismatch is attributed, Tier B is
frozen independently, and production R7 passes that unchanged contract.
