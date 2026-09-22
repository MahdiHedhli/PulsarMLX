# F020 native Safetensors status — current pointer

**Last updated 2026-09-22. Slice 1 only.** This is a current-pointer document:
it says what is qualified today, what is not, and where to read the detail. It
deliberately claims nothing about a real checkpoint.

## What Slice 1 qualified

Two model-neutral crates, on synthetic fixtures, with no model weights, no
downloads and no model execution.

* **`crates/safetensors-catalog`** — Safetensors header and index parsing, a
  deterministic tensor catalog with a stable sha256 digest, checked byte-range
  arithmetic, bounded `pread` reads, explicit shard hashing, and a header-only
  mode that builds the same catalog with no file system at all. Rules:
  [`specs/020-mlx-safetensors-affine/contracts/catalog-contract.md`](../../specs/020-mlx-safetensors-affine/contracts/catalog-contract.md).
* **`crates/mlx-affine`** — the MLX affine packed-weight representation:
  weight/scales/biases association, bit width and group size, global and
  per-module override resolution, fail-closed refusal of anything unsupported
  or ambiguous, checked slicing arithmetic for one expert or one row, and the
  decoder. Rules:
  [`specs/020-mlx-safetensors-affine/spec.md`](../../specs/020-mlx-safetensors-affine/spec.md).

**90 Rust tests and 34 Python tests**, all passing.
[Evidence](reviews/evidence/f020-slice1-numerics-results-v1.json).

## R1, R2, R3

| Arm | What it is | What it establishes | What it never establishes |
|---|---|---|---|
| **R1** | independent binary64 references, written from the format specification alone: `crates/mlx-affine/src/reference.rs` and `scripts/research/mlx_affine_reference_v1.py` | the correct interpretation of the format and of the affine quantization | performance; compatibility with any upstream build |
| **R2** | the pinned upstream MLX, driven by `scripts/ci/mlx_affine_compat_v1.py` | compatibility with the selected upstream execution | **correctness** — a defect shared by MLX and by a native path that calls MLX is invisible to it |
| **R3** | the native candidate, `crates/mlx-affine/src/decode.rs` | correct integration, when compared against R1 under the frozen contract | anything by itself |

The Python R1 was written first, before either Rust file existed. The Rust R1
has no `use` statements at all, names neither `crate::` nor `super::`, shares
no function name with the decoder, and admits bit widths the decoder refuses so
it can check a case the candidate declines. `crates/mlx-affine/tests/independence.rs`
reads both sources and asserts this.

## The frozen contract and its results

[`contracts/numerics-v1.json`](../../specs/020-mlx-safetensors-affine/contracts/numerics-v1.json)
was written before any R3 or R2 number existed.

| Check | Kind | Result |
|---|---|---|
| `C-CODES` | exact invariant | PASS |
| `C-DEQUANT-HALF` — `R3 == round_to_f32(R1)` for BF16 and F16 metadata | exact invariant | PASS, bit for bit |
| `C-DEQUANT-SINGLE` — the two-rounding bound for F32 metadata | prospectively justified bound | PASS; largest observed difference 2.384e-7, and 0.88 of the product term alone |
| `C-SHAPE` | exact invariant | PASS |
| `C-SLICE` | exact invariant | PASS |
| `C-DETERMINISM` | exact invariant | PASS |
| `C-R2-COMPAT` | compatibility observation | agreement; codes exact and values bit-identical after rounding, on 13 modules under MLX 0.32.0 on Metal |

**One correction is recorded rather than hidden.** `C-DEQUANT-SINGLE` first
bounded the F32-metadata difference by one ulp of the *result*. That is wrong
under cancellation: the first rounding happens at the magnitude of the product.
The adopted golden case `experts` has an element where R1 gives 8.94e-8, R3
gives exactly 0, and one ulp of the result is 7.1e-15. The replacement is
derived from the dtypes, not fitted to the observation, and both the superseded
form and the reason are in the contract's `correction` block.

### Acceptance criteria

All nine of `acceptance_criteria_slice_1` hold; see the contract for their
text and the evidence file for where each was exercised.

## What is not claimed

* **No real-checkpoint Q0.** No shard payload of any released checkpoint has
  been read or hashed by this work. The Flash metadata observation, when it
  exists, is a *compatibility observation* and is labelled as such.
* **No model execution.** Neither GLM-5.3 nor GLM-5.3-Flash was run.
* **No quantized matmul.** `quantized_matmul` and `gather_qmm` have no contract
  in this slice, and `gather_qmm`'s `sorted_indices` kernel-selection hazard is
  untouched.
* **No performance claim.** Nothing here was timed and nothing should be.
* **No quality claim.** What a 4-bit or 8-bit checkpoint retains against the
  original BF16 or FP8 model is a separate evaluation track.
* **No residency.** The slicing arithmetic gives a residency layer the
  provenance it will need; the layer itself does not exist.

## Admitted quantization

Bits 4 and 8. Group sizes 32, 64 and 128. Mode `affine`. Everything else is
refused, including MLX's own 2, 3, 5 and 6 bits, which use a different
bit-serial layout across the 32-bit word; a decoder that admitted a layout it
does not implement would mis-decode silently. See
[ADR 0007](decisions/0007-safetensors-affine-format-scope.md).

## Fixtures

[`fixtures/safetensors/`](../../fixtures/safetensors/README.md): three positive
checkpoints and 26 negative cases, about 180 KB, regenerated byte for byte by
`scripts/research/generate_safetensors_fixtures_v1.py`, plus
`golden-affine-dequant-v1` with its own provenance. Every negative case names
the error variant it expects on the first line of its README, and the tests
read that line.
[Manifest evidence](reviews/evidence/f020-slice1-fixture-manifest-v1.json).

## CI

Two required steps in `apple-mlx-small-fixtures`, added deliberately and made
mandatory by advancing the measurement-scope doctor's frozen resolution:
`Qualify MLX affine compatibility (synthetic, pinned MLX wheel)` and `Test MLX
affine representation`. The required-step census moved from 10 to 12. The
mechanism and both constants are recorded in
[`docs/research/f017/historical-measurement-current-ci.md`](../research/f017/historical-measurement-current-ci.md).

The compatibility step fails closed: an unusable MLX or an unavailable Metal
with `PULSAR_REQUIRE_NATIVE_MLX=1` is a failure, not a skip.

## Next

Slice 2 is not started. The smallest honest next boundary is the real-metadata
census on already-verified local headers — no payload, no download — and
nothing beyond it is authorized.
