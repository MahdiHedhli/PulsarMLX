# PulsarMLX Feature 017 fixture provenance audit

## Historical claim state before independent regeneration

Classification at `b7585de`: **PARTIALLY INDEPENDENT**. The seven-boundary
checkpoint-free scaffold passed against scalar Rust reference functions, but
no independent Python/NumPy oracle generated those expected values. It must
not be cited as independent-oracle parity. The existing fixtures are retained
as historical structural/reference artifacts.

## Conclusion

Final classification: **INDEPENDENT** for the seven v2 checkpoint-free
boundaries. Expected values are generated entirely by Python/NumPy outside the
Rust/native candidate path.

- Generator: `scripts/research/generate_f017_independent_oracle.py`
- Generator source SHA: `a9779097de029f26be1cb9fde3543cc517ff153e`
- Environment: CPython `3.13.13`, NumPy `2.4.5`, resolved by `uv.lock`
- Deterministic seed: `17017`; fixture values are fixed and regeneration is
  byte deterministic
- Oracle artifact:
  `specs/017-rust-native-inference-runtime/fixtures/f017-independent-oracle-v1.json`
- Oracle artifact SHA-256:
  `16ca1e412dbf98d59e19b685b86549567de043ea7e728b254a952540aa783960`
- Fixture source SHA: `60145f8f18531e169e9fbfb676d1754efbfc4873`
- Checkpoint-set identity:
  `0b38dfc3b79bf6dd3eac3c80cd2b62cb6eb46b2f84e3e51c1a340ad1876c1a42`

The generator does not call Rust, Rust `reference_*` functions, FFI, MLX, or
checkpoint code. Packed Q8_0 bytes and all expected semantic values are
constructed and evaluated in the Python module. The candidate remains
`crates/engine/src/f017_parity.rs::run_*` plus
`quant::decode_q8_0_matrix`. No implementation code is shared across the
oracle/candidate boundary.

## Boundary mapping

- Projection: INDEPENDENT, exact f32 bits for decode and output.
- Router: INDEPENDENT, absolute tolerance `1e-12`, deterministic lowest-ID tie
  break, selected IDs, weights, and aggregate output.
- Complete expert: INDEPENDENT, exact f32 bits through gate/up, SiLU, down, and
  final output.
- Top-8 plus shared: INDEPENDENT, absolute tolerance `1e-12`, ordered routes,
  weights, shared contribution, residual, and aggregate output.
- MLA/dense: INDEPENDENT, absolute tolerance `1e-14`, positional rotation,
  attention scores/weights, output projection, residual, and output.
- Complete layer: INDEPENDENT, exact f64 bits after the ordered component
  ladder and residual output.
- Final norm/logits/top-k: INDEPENDENT, absolute tolerance `1e-14`, stable
  top-k/argmax ordering, and frozen top-1 margin.

The generated Rust constants are derived from the same committed JSON and are
the sole candidate-side acceptance authority. Retained scalar Rust
`reference_*` helpers are historical scaffolding and do not determine v2
pass/fail. The old portable v1 manifests are marked `independent: false`; the
validated set contains only `portable-fixture-independent-v2.json`. No model
weight bytes or private paths are committed.

## Edge-distribution coverage

The independent bundle adds Q8_0 f16 maximum, minimum-normal, and
minimum-subnormal scales; zero/near-zero activations; signed quant-grid
extremes; exact and one-ULP router ties; cancellation-sensitive residual sums;
signed zero; top-k ordering; and final-logit margin evidence. Tolerances were
frozen in the generator before Rust comparison.

## Limitation carried to P1

Synthetic/checkpoint-free fixtures still do not exhaust real GLM-5.2 value
distributions. Although explicit f16 scale, denormal-adjacent, grid/sign,
near-zero, cancellation, tie, and top-k edge cases are present, uncommon
combinations and real-checkpoint distribution tails remain underrepresented.
The first M1 Ultra P1 is the first real-checkpoint integration gate. Passing
this ladder is not real-checkpoint proof and must not be promoted to a
shipping-runtime or real-checkpoint determinism claim.
