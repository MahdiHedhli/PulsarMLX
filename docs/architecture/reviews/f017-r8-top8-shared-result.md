# Feature 017 R8 top-8 plus shared result

R8 passed checkpoint-free at clean source
`88a46e813f47c4047644d736c82a926ea2f1abd8`. The production MLX path selected
experts `[7, 6, 5, 4, 3, 2, 1, 0]`, matched the independent router contract,
and qualified all eight routed experts plus one shared expert under the frozen
`f017-production-expert-tier-b-v1` contract.

## Numerical result

- Gate, up, and activated-hidden boundaries were bit-identical for every
  expert.
- The largest down-projection absolute error across the nine experts was
  `3.25`; the largest down RMSE was `1.362962220908929`.
- Routed aggregation had maximum absolute error `1.0466281566768885` and RMSE
  `0.5017068808668702`.
- The shared-plus-routed residual output had maximum absolute error
  `3.175311913713813` and RMSE `1.5592101279929471`.
- Both aggregate boundaries stayed within propagated frozen bounds, including
  the independently bounded router-weight transport difference.
- Ten identical executions produced deterministic output bits.
- Classification: `numerically_qualified_greedy_identical`.

## Dispatch and lifecycle

The retained result records 288 native MLX dispatches, 27 exact-scaffold
dispatches used only for qualification, zero explicit-reference dispatches,
and zero unexpected fallbacks. All 576 managed owners, 288 derived arrays, 576
callbacks, and the owned stream reconciled. The context was inactive after
teardown.

No checkpoint was accessed. Timings are fixture diagnostics only and are not
model performance evidence.

## Evidence

- Independent oracle v2:
  `specs/017-rust-native-inference-runtime/fixtures/f017-r8-top8-shared-oracle-v2.json`
- Production result:
  `docs/architecture/reviews/evidence/f017-r8-top8-shared-production-v1.json`
- Production result SHA-256:
  `427a3f2caf76bcb8e54cb5d8a853c0e26e4ec5989cb8afb612e76c98644ac4e4`

The original v1 oracle remains committed as the rejected decimal-only f64
transport record. It was rejected before candidate execution because two
routing weights reconstructed one ULP differently across Python and Rust.
Version 2 carries canonical little-endian IEEE-754 bytes and preserves the
same independently generated values.

## Reproduction

```sh
PULSAR_REQUIRE_NATIVE_MLX=1 \
MLX_C_PREFIX="$MLX_C_PREFIX" \
MLX_PREFIX="$MLX_PREFIX" \
DYLD_LIBRARY_PATH="$MLX_C_PREFIX/lib" \
cargo test -p f017-runner --test r8_top8_shared_native -- --nocapture
```

R9 MLA/dense is the next eligible checkpoint-free runner gate. This result
does not authorize R9 in the R7 sprint, any real checkpoint, or M1 model time.
