# Feature 017 Tier-B stress qualification

The public-safe stress oracle was generated and committed before it was shown
to the production MLX backend. It covers nine deterministic cases and output
shapes of 1, 2, 4, 8, and 32 rows: alternating signs, cancellation, dynamic
range, a small residual after large partial sums, denormal-adjacent values,
large magnitudes, full-shape sign changes, and a near-tie behavioral boundary.

All cases were `golden_identical` on MLX C matmul across 10 identical runs.
The near-tie argmax remained identical. All 180 managed owners, 90 derived
arrays, 180 callbacks, and the owned stream reconciled. No checkpoint or
fallback path was used.

This does not make the Tier-B allowance empirical: the unchanged contract was
already committed at `8bfeb98c`, and the independent expected fixture was
already committed at `4c903999`. The production run used clean source
`45e91120a0b67628e0895fd72ab090302bfe840b`.

Reproduce with the pinned native MLX environment:

```sh
PULSAR_REQUIRE_NATIVE_MLX=1 \
MLX_C_PREFIX="$MLX_C_PREFIX" \
MLX_PREFIX="$MLX_PREFIX" \
DYLD_LIBRARY_PATH="$MLX_C_PREFIX/lib" \
cargo test -p f017-runner --test tier_b_stress_native -- --exact --nocapture
```
