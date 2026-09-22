//! The MLX affine quantized weight representation, over a Safetensors catalog.
//!
//! This crate says what a checkpoint's quantized modules *are*: which stored
//! tensors form a triple, at what bit width and group size, where each
//! expert's bytes live, and what the packed codes decode to. It does not
//! execute anything, does not allocate residency and knows no model.
//!
//! # Three labelled references
//!
//! *  **R1** -- an independent binary64 implementation written from the format
//!    specification alone. It defines what correct means. It lands with the
//!    qualification commit that follows this one.
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
//! tensor name in this crate and no model's naming convention anywhere in it.

#![forbid(unsafe_code)]

pub mod decode;
pub mod error;
pub mod module;
pub mod spec;

pub use decode::{dequantize_rows, unpack_codes, ScaleDtype};
pub use error::{AffineError, Result};
pub use module::{
    classify_all, classify_module, module_paths, AffineTriple, ByteSlice, ModuleKind, TripleSlice,
};
pub use spec::{Bits, GroupSize, Mode, QuantSpec, QuantizationConfig};
