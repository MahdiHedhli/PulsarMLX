//! Every way this crate refuses a quantization configuration or a module.
//!
//! The rule everywhere is fail closed: an unsupported combination, an
//! ambiguous one and a self-contradictory one are all refusals, never a
//! silently chosen default. A checkpoint that this crate cannot describe
//! exactly is one it declines to describe at all.

use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
#[non_exhaustive]
pub enum AffineError {
    /// A bit width, group size or mode outside the admitted set.
    UnsupportedQuantization { detail: String },
    /// The configuration object exists but has no top-level `bits`/`group_size`.
    MissingDefaultSpec { detail: String },
    /// `quantization` and `quantization_config` are both present and differ.
    InconsistentConfig,
    /// The configuration carries an override for a module path that resolves
    /// to no quantized module in the catalog. A rule nothing matches is a
    /// statement about a checkpoint that is not the one in hand.
    UnresolvedOverride { module: String },
    /// A per-module entry is not an object carrying `bits` and `group_size`.
    /// In particular `false`, which the upstream Python loader treats as
    /// "do not quantize", is refused rather than reinterpreted.
    UnsupportedOverrideValue { module: String, detail: String },
    /// The configuration JSON is malformed.
    InvalidConfigJson { detail: String },
    /// The configuration declares the same member twice, at any depth.
    DuplicateConfigKey { path: String },
    /// There is no `quantization` object at all.
    NoQuantizationConfig,
    /// One or two of `weight`/`scales`/`biases` are present, or the weight is
    /// packed `U32` without both companions.
    IncompleteTriple { module: String, detail: String },
    /// `scales` and `biases` disagree in dtype or shape.
    ScalesBiasesMismatch { module: String, detail: String },
    /// A module carries an explicit override but has no `.scales`.
    OverrideWithoutScales { module: String },
    /// A module has `.scales` but the checkpoint declares no quantization.
    AmbiguousQuantization { module: String },
    /// The resolved spec contradicts the stored shapes.
    InconsistentOverride {
        module: String,
        implied_bits: Option<u32>,
        detail: String,
    },
    /// A checked multiplication or addition overflowed.
    Overflow { module: String, detail: String },
    /// The module is not present in the catalog at all.
    UnknownModule { module: String },
    /// A slice index is outside the tensor's leading dimensions.
    IndexOutOfBounds { module: String, detail: String },
    /// A decoder call's buffers do not match the declared geometry.
    GeometryMismatch { detail: String },
}

impl fmt::Display for AffineError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UnsupportedQuantization { detail } => {
                write!(f, "unsupported quantization: {detail}")
            }
            Self::MissingDefaultSpec { detail } => {
                write!(f, "quantization object without a default spec: {detail}")
            }
            Self::InconsistentConfig => {
                write!(
                    f,
                    "quantization and quantization_config are both present and differ"
                )
            }
            Self::UnresolvedOverride { module } => {
                write!(
                    f,
                    "the configuration overrides {module}, which no module in the catalog matches"
                )
            }
            Self::UnsupportedOverrideValue { module, detail } => {
                write!(f, "override for {module}: {detail}")
            }
            Self::InvalidConfigJson { detail } => write!(f, "invalid configuration JSON: {detail}"),
            Self::DuplicateConfigKey { path } => {
                write!(f, "duplicate configuration member {path:?}: two readings")
            }
            Self::NoQuantizationConfig => write!(f, "the configuration declares no quantization"),
            Self::IncompleteTriple { module, detail } => {
                write!(f, "module {module}: incomplete affine triple: {detail}")
            }
            Self::ScalesBiasesMismatch { module, detail } => {
                write!(f, "module {module}: scales and biases disagree: {detail}")
            }
            Self::OverrideWithoutScales { module } => {
                write!(
                    f,
                    "module {module}: explicit override but no .scales tensor"
                )
            }
            Self::AmbiguousQuantization { module } => {
                write!(
                    f,
                    "module {module}: .scales present but the configuration is silent"
                )
            }
            Self::InconsistentOverride {
                module,
                implied_bits,
                detail,
            } => match implied_bits {
                Some(bits) => write!(f, "module {module}: shapes imply {bits} bits: {detail}"),
                None => write!(
                    f,
                    "module {module}: shapes imply no whole bit width: {detail}"
                ),
            },
            Self::Overflow { module, detail } => {
                write!(
                    f,
                    "module {module}: checked arithmetic overflowed: {detail}"
                )
            }
            Self::UnknownModule { module } => write!(f, "module {module} is not in the catalog"),
            Self::IndexOutOfBounds { module, detail } => {
                write!(f, "module {module}: {detail}")
            }
            Self::GeometryMismatch { detail } => write!(f, "geometry mismatch: {detail}"),
        }
    }
}

impl std::error::Error for AffineError {}

pub type Result<T> = std::result::Result<T, AffineError>;
