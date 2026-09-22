//! The MLX affine quantized weight representation, over a Safetensors catalog.
//!
//! This crate says what a checkpoint's quantized modules *are*: which stored
//! tensors form a triple, at what bit width and group size, where each
//! expert's bytes live, and what the packed codes decode to. It does not
//! execute anything, does not allocate residency and knows no model.
//!
//! # Three labelled references
//!
//! *  **R1** ([`reference`]) -- an independent binary64 implementation written
//!    from the format specification alone. It defines what correct means.
//! *  **R2** -- pinned upstream Python/MLX (`mx.dequantize`), exercised by
//!    `scripts/ci/mlx_affine_compat_v1.py`. It establishes compatibility with
//!    the selected upstream execution and **never** correctness: a defect
//!    shared by MLX and by a native path that calls MLX is invisible to it.
//!  * **R3** ([`decode`]) -- the native single-precision candidate.
//!
//! The frozen contract in `specs/020-mlx-safetensors-affine/contracts/numerics-v1.json`
//! states the relations between them before any of them was run.
//!
//! # Fail closed
//!
//! Every unsupported, ambiguous or self-contradictory configuration is a
//! refusal with its own [`AffineError`] variant. Bit widths other than 4 and
//! 8, group sizes other than 32, 64 and 128, modes other than `affine`,
//! incomplete triples, overrides that contradict the stored shapes, overrides
//! for modules without scales, and scales without a configuration are all
//! errors. Nothing is guessed.
//!
//! # Model neutrality
//!
//! Module paths are opaque strings. There is no regular expression over a
//! tensor name in this **library** crate and no model's naming convention in
//! it. The claim is about the library, not about every file in the tree:
//! `examples/header_census.rs` categorizes names, and it takes those rules
//! from a caller-supplied JSON file that lives above these crates, so the
//! meaning of a prefix stays outside.

#![forbid(unsafe_code)]

pub mod decode;
pub mod error;
pub mod module;
pub mod reference;
pub mod spec;

pub use decode::{dequantize_rows, unpack_codes, ScaleDtype};
pub use error::{AffineError, Result};
pub use module::{
    classify_all, classify_module, module_paths, validate_catalog, AffineTriple, ByteSlice,
    ModuleKind, TripleSlice,
};
pub use spec::{Bits, GroupSize, Mode, QuantSpec, QuantizationConfig};
