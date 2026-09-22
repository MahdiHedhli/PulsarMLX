# ADR 0007: Safetensors and MLX affine are a new format scope, not an extension of ADR 0006

- **Status**: Accepted for Feature 020, Slice 1
- **Date**: 2026-09-22
- **Supersedes**: ADR 0006's *scope rule* as it applies to non-GGUF formats. ADR 0006 remains in force for GGUF k-quant and i-quant decoder work.

## Context

ADR 0006 says decoder work must be "justified by the current GLM52 checkpoint
inventory or by a versioned public-safe/local-only fixture that binds the
format to a runtime boundary". That rule was written when every checkpoint in
the project was GGUF and the only question was which k-quant or i-quant to
implement next.

An MLX affine decoder is justified by neither clause as written. It does not
appear in the GLM-5.2 inventory — that inventory is GGUF end to end — and at
the time this work began there was no fixture on `main` binding the format to
any runtime boundary, because `crates/mlx-safetensors` was two empty
directories and one untracked JSON file. Arguing that ADR 0006 already covers
it would be reading the rule backwards.

## Decision

Safetensors container parsing and MLX affine quantization are a **new format
scope**, admitted on their own terms:

1. **Justification is the target checkpoints, not the GLM-5.2 inventory.** The
   `PipeNetwork GLM-5.3-MLX-mixed-4_8bit` and `…-Flash-…` releases store every
   quantized module as a `weight`/`scales`/`biases` triple in Safetensors
   shards. No GGUF inventory can justify or refuse that work.

2. **Nothing is ported from `crates/quant`.** MLX affine shares no block layout
   with GGUF k-quants or i-quants. The decoder is new, small and integer-exact,
   and the 4,000-line k-quant crate is untouched.

3. **The format layer is model-neutral, and that is a requirement rather than a
   preference.** `crates/safetensors-catalog` and `crates/mlx-affine` contain no
   model's tensor names, no architecture constants and no regular expression
   over a name. Module paths are opaque strings supplied by the caller. Any
   GLM-specific mapping belongs in a layer above these crates. The synthetic
   fixtures use paths (`block.N....`) that belong to no model, and a test
   asserts that no model-specific token appears in them, so a parser cannot
   pass by recognising a name.

4. **Admission is narrower than MLX's.** Bits 4 and 8 only, group sizes 32, 64
   and 128 only, `affine` mode only. MLX also defines 2, 3, 5 and 6 bits, but
   uses a different bit-serial layout across the 32-bit word for the widths
   that do not divide 32. A decoder that admitted a width whose layout it does
   not implement would mis-decode silently, so those widths are refused. The
   independent reference implements the general layout precisely so that it can
   check a case the production decoder declines.

5. **Qualification is against an independent reference, never against the
   upstream one.** ADR 0002 keeps Python as a reference oracle; this ADR adds
   the distinction that matters for a format shared with MLX. R1 is an
   independent binary64 implementation written from the format specification.
   R2 is the pinned upstream MLX. R3 is the native candidate. A correctness
   claim requires R3 against R1 under a prospectively frozen contract. R3
   against R2 is a compatibility observation and may not be promoted to a
   correctness oracle, because a defect shared by MLX and by a native path that
   calls MLX is invisible to it.

6. **The evidence obligations of ADR 0006 carry over unchanged.** Synthetic
   blocks, malformed and truncated input, no partial writes, overflow-safe
   lengths, exact comparison where the mathematics supports it, and a stated
   bound where it does not. Slice 1 adds one obligation ADR 0006 did not have:
   every negative case names the exact error variant it expects, in a file the
   test reads.

## Consequences

- ADR 0006's deferral table for Q2_K, Q3_K, IQ2_S and IQ4_XS is unaffected;
  those remain GGUF questions under the GGUF rule.
- A future non-GGUF format is admitted by this ADR's pattern: name the target
  checkpoints, write an independent reference first, freeze a numerical
  contract before observing anything, and keep the container layer free of any
  model's names.
- The `f017-native` temporal-successor contract's frozen files are untouched by
  this scope. A Safetensors runtime path is new code implementing the same
  traits, exactly as `temporal.rs` was added, never an edit to `model.rs`,
  `executor.rs`, `contract.rs`, `loader.rs` or `bin/bounded_p1.rs`.
- Slice 1 claims nothing about a real checkpoint. Real-checkpoint payload
  identity (Q0) and numerical qualification are separately authorized later
  work.
