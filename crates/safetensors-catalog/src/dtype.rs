//! The standard Safetensors dtype strings.
//!
//! Support here means exactly two things: the string parses, and its element
//! size in bytes is known. Nothing in this crate decides what a *consumer*
//! may do with a dtype; `mlx-affine`, for instance, admits `U32` packed
//! weights and `F16`/`BF16`/`F32` metadata and refuses the rest.

use std::fmt;

/// Every dtype string the Safetensors format defines.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Dtype {
    Bool,
    U8,
    I8,
    F8E5M2,
    F8E4M3,
    I16,
    U16,
    F16,
    Bf16,
    I32,
    U32,
    F32,
    F64,
    I64,
    U64,
}

impl Dtype {
    /// Parse a Safetensors dtype string. Unknown strings return `None`; the
    /// caller turns that into [`crate::CatalogError::UnsupportedDtype`] with
    /// the tensor name attached.
    pub fn parse(name: &str) -> Option<Self> {
        Some(match name {
            "BOOL" => Self::Bool,
            "U8" => Self::U8,
            "I8" => Self::I8,
            "F8_E5M2" => Self::F8E5M2,
            "F8_E4M3" => Self::F8E4M3,
            "I16" => Self::I16,
            "U16" => Self::U16,
            "F16" => Self::F16,
            "BF16" => Self::Bf16,
            "I32" => Self::I32,
            "U32" => Self::U32,
            "F32" => Self::F32,
            "F64" => Self::F64,
            "I64" => Self::I64,
            "U64" => Self::U64,
            _ => return None,
        })
    }

    /// The canonical Safetensors spelling.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Bool => "BOOL",
            Self::U8 => "U8",
            Self::I8 => "I8",
            Self::F8E5M2 => "F8_E5M2",
            Self::F8E4M3 => "F8_E4M3",
            Self::I16 => "I16",
            Self::U16 => "U16",
            Self::F16 => "F16",
            Self::Bf16 => "BF16",
            Self::I32 => "I32",
            Self::U32 => "U32",
            Self::F32 => "F32",
            Self::F64 => "F64",
            Self::I64 => "I64",
            Self::U64 => "U64",
        }
    }

    /// Bytes per element. `BOOL` is one stored byte, as the format defines it.
    pub fn size_bytes(self) -> u64 {
        match self {
            Self::Bool | Self::U8 | Self::I8 | Self::F8E5M2 | Self::F8E4M3 => 1,
            Self::I16 | Self::U16 | Self::F16 | Self::Bf16 => 2,
            Self::I32 | Self::U32 | Self::F32 => 4,
            Self::F64 | Self::I64 | Self::U64 => 8,
        }
    }

    /// Every dtype, in declaration order. Used by the exhaustiveness tests.
    pub const ALL: [Dtype; 15] = [
        Dtype::Bool,
        Dtype::U8,
        Dtype::I8,
        Dtype::F8E5M2,
        Dtype::F8E4M3,
        Dtype::I16,
        Dtype::U16,
        Dtype::F16,
        Dtype::Bf16,
        Dtype::I32,
        Dtype::U32,
        Dtype::F32,
        Dtype::F64,
        Dtype::I64,
        Dtype::U64,
    ];
}

impl fmt::Display for Dtype {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

#[cfg(test)]
mod tests {
    use super::Dtype;

    #[test]
    fn every_standard_dtype_round_trips() {
        for dtype in Dtype::ALL {
            assert_eq!(Dtype::parse(dtype.as_str()), Some(dtype));
        }
        assert_eq!(Dtype::ALL.len(), 15);
    }

    #[test]
    fn sizes_are_the_format_sizes() {
        assert_eq!(Dtype::Bool.size_bytes(), 1);
        assert_eq!(Dtype::F8E4M3.size_bytes(), 1);
        assert_eq!(Dtype::Bf16.size_bytes(), 2);
        assert_eq!(Dtype::U32.size_bytes(), 4);
        assert_eq!(Dtype::F64.size_bytes(), 8);
    }

    #[test]
    fn unknown_dtype_strings_are_refused() {
        for name in ["", "f32", "F32 ", "MXFP4", "Q4_K", "BF17"] {
            assert!(Dtype::parse(name).is_none(), "{name} must not parse");
        }
    }
}
