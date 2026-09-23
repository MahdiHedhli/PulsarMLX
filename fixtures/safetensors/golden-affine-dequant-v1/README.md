# golden-affine-dequant-v1

A golden fixture for MLX affine dequantization, in two blocks.

## `adopted` — seven quantized cases, origin outside this repository

The block comes from `crates/mlx-safetensors/tests/data/golden_mlx_dequant.json`,
an **untracked** file in the shared checkout `/Users/mhedhli/Documents/Coding/PulsarMLX`
(20,460 bytes, mtime 2026-09-21 18:13,
sha256 `88acea83f0ca4826e5cfae71abadb3cb17ad1b21db43433c2ea38e8b6a1c0a17`).
It was read read-only and copied; nothing in the shared checkout was modified.
The original file had no generator, no schema field, no MLX version and no
commit binding, so under this project's evidence rules its *authority* was
unestablished even though its *content* is self-consistent.

What it now carries instead: Phase 0 worker W1 reconstructed all nine of its
cases independently in Python on 2026-09-22 and reported them self-consistent,
and `scripts/research/generate_golden_affine_dequant_v1.py` re-derives every
case through the R1 reference on every `--check`. That makes it a **regression
baseline**, not an upstream oracle.

The original's `f16` and `bf16` entries are not quantization cases; they are
vectors of binary32 values that happen to be exactly representable in those
half formats. They are carried through as `conversion_vectors` and that
property is what the checker asserts about them.

Gaps W1 recorded in the original, and which the `extended` block closes:
`cols == group` in every case (so nothing pins the multi-group metadata
layout), no `group_size` 128, and no `quantized_matmul`/`gather_qmm` case. The
last of those stays open: matmul is out of scope for Slice 1.

## `extended` — eight generated cases

Produced by `scripts/research/generate_golden_affine_dequant_v1.py` from the
R1 encoder in `scripts/research/mlx_affine_reference_v1.py`, which implements
the *written specification* of MLX's encoder (signed scale, larger-magnitude
group edge as the bias, scale snapped so zero quantizes exactly). **MLX was not
run to produce them.** Whether the pinned MLX agrees is a separate, labelled
observation made by `scripts/ci/mlx_affine_compat_v1.py`.

They add: rows spanning four groups; `group_size` 128; 8 bits at group 64 and
at group 32; BF16, F16 and F32 metadata; groups whose signed scale comes out
negative and groups whose scale comes out positive; a group that is entirely
zero, which exercises the encoder's `q0 == 0` branch where the bias is exactly
0.0; and a stacked three-expert tensor flattened to rows.

## Encoding

Every floating-point quantity is the IEEE-754 **binary32 bit pattern** of its
value, stored as a JSON integer — the right choice for an exactness fixture.
`metadata_dtype` says what a checkpoint would store the scales and biases in;
when it is `BF16` or `F16` the stored binary32 pattern is exactly
representable in that format, and the checker asserts it.

## Regenerating and checking

```
python3 scripts/research/generate_golden_affine_dequant_v1.py --check
python3 scripts/research/generate_golden_affine_dequant_v1.py --write
```
